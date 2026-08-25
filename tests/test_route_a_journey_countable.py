from __future__ import annotations

import json

import pytest

from data_agent.llm.client import Response, ToolCall
from data_agent.tools import discover_tools

discover_tools()

from scripts.acceptance import route_a_gate_c_journey as journey
from scripts.acceptance.route_a_gate_c_journey import CountableJourneyClient, JourneyStructureError


class _FakeOnceLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat_once(self, messages, tools=None, system=None, response_format=None, max_tokens=None):
        self.calls.append({
            "messages": messages,
            "tools": tools,
            "system": system,
            "response_format": response_format,
            "max_tokens": max_tokens,
        })
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def _tool_round(*names):
    return Response(
        tool_calls=[ToolCall(id=f"c_{name}", name=name, arguments={}) for name in names],
        finish_reason="tool_calls",
    )


def _final_round(text):
    return Response(text=text, finish_reason="stop")


def test_each_round_makes_exactly_one_call_and_never_escalates_tool_rounds():
    once = _FakeOnceLLM([_tool_round("load_data"), _final_round("answer 71")])
    client = CountableJourneyClient(round_cap=2, ladder=[2000, 8000, 32000], once_client=once)
    first = client.chat([{"role": "user", "content": "q"}], tools=[{"name": "load_data"}], system="s")
    assert [tc.name for tc in first.tool_calls] == ["load_data"]
    events = list(client.stream_chat_structured([], tools=None, system="s"))
    assert [type(event).__name__ for event in events] == ["StreamTextDelta", "StreamComplete"]
    assert client.calls_made == 2
    assert [call["max_tokens"] for call in once.calls] == [2000, 2000]
    assert client.rounds_served == 2


def test_zero_text_truncation_climbs_the_round_ladder_and_stops_at_success():
    once = _FakeOnceLLM([
        Response(text="", finish_reason="length"),
        Response(text="", finish_reason="length"),
        _final_round("recovered"),
    ])
    client = CountableJourneyClient(round_cap=1, ladder=[2000, 8000, 32000], once_client=once)
    response = client.chat([{"role": "user", "content": "q"}])
    assert response.text == "recovered"
    assert client.calls_made == 3
    assert [call["max_tokens"] for call in once.calls] == [2000, 8000, 32000]
    assert [attempt["max_tokens"] for attempt in client.round_receipts[0]] == [2000, 8000, 32000]


def test_partial_text_truncation_also_climbs_because_nothing_was_published():
    # Unlike the streaming product client, a countable round is one
    # non-streaming request whose body is published only after it completes,
    # so ANY finish_reason=length response can be safely re-issued larger.
    once = _FakeOnceLLM([Response(text="partial", finish_reason="length"), _final_round("complete")])
    client = CountableJourneyClient(round_cap=1, ladder=[2000, 8000, 32000], once_client=once)
    response = client.chat([{"role": "user", "content": "q"}])
    assert response.text == "complete"
    assert client.calls_made == 2
    assert [call["max_tokens"] for call in once.calls] == [2000, 8000]


def test_truncated_tool_call_round_also_climbs_the_ladder():
    once = _FakeOnceLLM([
        Response(tool_calls=[ToolCall(id="c1", name="load_data", arguments={})], finish_reason="length"),
        _tool_round("load_data"),
    ])
    client = CountableJourneyClient(round_cap=1, ladder=[2000, 8000], once_client=once)
    response = client.chat([{"role": "user", "content": "q"}])
    assert response.finish_reason == "tool_calls"
    assert client.calls_made == 2


def test_exhausted_ladder_returns_the_last_truncated_response_sanitized():
    once = _FakeOnceLLM([Response(text="", finish_reason="length")] * 3)
    client = CountableJourneyClient(round_cap=1, ladder=[2000, 8000, 32000], once_client=once)
    response = client.chat([{"role": "user", "content": "q"}])
    assert response.finish_reason == "length"
    assert client.calls_made == 3
    serialized = json.dumps(client.round_receipts, default=str)
    assert "text" not in json.loads(serialized)[0][0]
    assert set(json.loads(serialized)[0][0]) >= {"max_tokens", "finish_reason"}


def test_round_cap_is_enforced_and_sticky():
    once = _FakeOnceLLM([_final_round("done")] * 5)
    client = CountableJourneyClient(round_cap=1, ladder=[2000], once_client=once)
    client.chat([])
    with pytest.raises(JourneyStructureError, match="round_cap_exceeded"):
        client.chat([])
    # The loop's sync fallback re-invokes the client after a streaming
    # failure; a terminated journey must refuse again without inflating the
    # round count or consuming another slot.
    with pytest.raises(JourneyStructureError, match="round_cap_exceeded"):
        client.chat([])
    assert client.rounds_served == 2
    assert once.calls.__len__() == 1


def test_real_loop_completes_the_r07_journey_through_the_countable_client():
    once = _FakeOnceLLM([
        Response(tool_calls=[ToolCall(
            id="c1", name="load_data",
            arguments={"source": "reference/test_doc/省钱卡订单.xlsx", "name": "r07_orders"},
        )], finish_reason="tool_calls"),
        Response(tool_calls=[ToolCall(
            id="c2", name="compare_periods",
            arguments={"name": "r07_orders", "date_col": "支付时间", "metrics": "售价",
                        "period_a": "2026-04-07~2026-04-21", "period_b": "2026-04-22~2026-05-06"},
        )], finish_reason="tool_calls"),
        _final_round("结论：前 15 天收入 1818，后 15 天收入 684，总计 71 笔订单覆盖 30 个自然日。边界：描述性趋势，不能解释原因。"),
    ])
    report = journey.execute_authorized_journey(
        journey.ROOT / "tests" / "acceptance" / "route_a_gate_c_journey_r07_candidate.json",
        authorized_source_digest="sha256:source",
        once_client=once,
        source_digest=lambda root: "sha256:source",
    )
    assert report["status"] == "passed", report
    assert report["provider_calls"] == 3
    assert report["rounds_used"] == 3
    assert report["tool_calls_executed"] == ["load_data", "compare_periods"]
    assert all(entry["prompt_sha256"].startswith("sha256:") for entry in report["structure"])
    assert report["contract_verdicts"]["final_answer_numeric_anchors_present"] is True


def _current_digest() -> str:
    return journey.journey_preflight(
        journey.ROOT / "tests" / "acceptance" / "route_a_gate_c_journey_r07_candidate.json",
        source_digest=lambda root: "sha256:source",
    )["source_digest"]


def test_preflight_freezes_the_journey_request_and_worst_case_budget():
    report = journey.journey_preflight(
        journey.ROOT / "tests" / "acceptance" / "route_a_gate_c_journey_r07_candidate.json",
        source_digest=lambda root: "sha256:source",
    )
    assert report["ready"] is True, report["errors"]
    assert report["max_call_budget"] == 24
    assert report["request"]["max_tokens_ladder"] == [2000, 8000, 32000]
    assert report["request"]["round_cap"] == 8
    assert report["model_id"] == "openai/deepseek-v4-flash"
    assert report["data"][0]["sha256"].startswith("sha256:")


def test_preflight_rejects_invalid_journeys(tmp_path):
    payload = {
        "schema_version": "route_a_journey_candidate.v1",
        "journey_id": "broken",
        "session_id": "foreign_session",
        "question": "q",
        "data": [{"id": "savings_card_orders", "sha256": "9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3"}],
        "request": {
            "model_id": "test/model",
            "temperature": 0.2,
            "timeout_seconds": 120,
            "max_tokens_ladder": [8000, 2000],
            "round_cap": 0,
        },
        "contract": {"required_tool_calls": [], "final_answer_numeric_anchors": []},
    }
    target = tmp_path / "broken.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    report = journey.journey_preflight(target, source_digest=lambda root: "sha256:source")
    assert report["ready"] is False
    errors = " ".join(report["errors"])
    assert "temperature must be 0.0 or omitted" in errors
    assert "strictly ascending" in errors
    assert "round_cap must be a positive integer" in errors
    assert "session_id must be dedicated" in errors


def test_executor_refuses_a_digest_mismatch_without_any_call():
    once = _FakeOnceLLM([])
    report = journey.execute_authorized_journey(
        journey.ROOT / "tests" / "acceptance" / "route_a_gate_c_journey_r07_candidate.json",
        authorized_source_digest="sha256:other",
        once_client=once,
        source_digest=lambda root: "sha256:source",
    )
    assert report["status"] == "failed"
    assert "source digest" in " ".join(report["errors"])
    assert report["provider_calls"] == 0


def test_executor_fails_the_journey_when_anchors_are_missing():
    once = _FakeOnceLLM([
        Response(tool_calls=[ToolCall(
            id="c1", name="load_data",
            arguments={"source": "reference/test_doc/省钱卡订单.xlsx", "name": "r07_orders"},
        )], finish_reason="tool_calls"),
        _final_round("无法给出数值结论。"),
    ])
    report = journey.execute_authorized_journey(
        journey.ROOT / "tests" / "acceptance" / "route_a_gate_c_journey_r07_candidate.json",
        authorized_source_digest="sha256:source",
        once_client=once,
        source_digest=lambda root: "sha256:source",
    )
    assert report["status"] == "failed"
    assert report["contract_verdicts"]["final_answer_numeric_anchors_present"] is False
    assert report["contract_verdicts"]["required_tools_present"] is True
