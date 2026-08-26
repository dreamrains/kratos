from __future__ import annotations

import json

import pytest

from data_agent.tools import discover_tools

discover_tools()

from scripts.acceptance import route_a_gate_c_journey as journey


def test_scripted_client_serves_rounds_in_order_and_records_structure():
    client = journey.ScriptedJourneyClient(
        rounds=[
            {"tool_calls": [{"name": "load_data", "arguments": {"source": "x.xlsx"}}]},
            {"text": "final answer 71"},
        ],
        round_cap=2,
    )
    first = client.chat([{"role": "user", "content": "q"}], tools=[{"name": "load_data"}], system="s")
    assert [tc.name for tc in first.tool_calls] == ["load_data"]
    second = list(client.stream_chat_structured([], tools=None, system="s"))
    assert [type(event).__name__ for event in second] == ["StreamTextDelta", "StreamComplete"]
    assert second[0].text == "final answer 71"
    assert second[-1].response.text == "final answer 71"
    assert [entry["round"] for entry in client.structure] == [1, 2]
    assert client.structure[0]["scripted_tool_calls"] == ["load_data"]
    assert client.structure[0]["scripted_final_text"] is False
    assert client.structure[1]["scripted_final_text"] is True
    assert client.structure[0]["prompt_sha256"].startswith("sha256:")
    assert client.structure[0]["tools_count"] == 1
    assert client.structure[0]["tools_sha256"].startswith("sha256:")


def test_scripted_client_refuses_rounds_beyond_the_frozen_cap():
    client = journey.ScriptedJourneyClient(rounds=[{"text": "done"}], round_cap=1)
    client.chat([])
    with pytest.raises(journey.JourneyStructureError, match="round_cap_exceeded"):
        client.chat([])


def test_r07_replay_measures_the_real_loop_structure_without_provider_calls():
    report = journey.run_journey_replay(
        journey.ROOT / "tests" / "acceptance" / "route_a_gate_c_journey_r07_replay.json"
    )
    assert report["status"] == "passed", report
    assert report["provider_calls"] == 0
    assert report["rounds_used"] == 3
    assert report["rounds_scripted"] == 3
    assert [entry["round"] for entry in report["structure"]] == [1, 2, 3]
    assert all(entry["prompt_sha256"].startswith("sha256:") for entry in report["structure"])
    assert all(entry["tools_count"] > 0 for entry in report["structure"])
    assert report["tool_calls_executed"] == ["load_data", "compare_periods"]
    verdicts = report["contract_verdicts"]
    assert verdicts["required_tools_present"] is True
    assert verdicts["final_answer_numeric_anchors_present"] is True
    assert verdicts["tool_oracle_matches"] is True
    assert verdicts["no_error_events"] is True
    assert verdicts["rounds_match_script"] is True
    assert report["tool_oracle"]["observed"] == [
        {"tool": "compare_periods", "path": "period_a.rows", "actual": 47, "expected": 47},
        {"tool": "compare_periods", "path": "period_b.rows", "actual": 24, "expected": 24},
        {"tool": "compare_periods", "path": "period_a.day_count", "actual": 15, "expected": 15},
        {"tool": "compare_periods", "path": "period_b.day_count", "actual": 15, "expected": 15},
        {"tool": "compare_periods", "path": "metrics.售价.period_a", "actual": 1818.0, "expected": 1818.0},
        {"tool": "compare_periods", "path": "metrics.售价.period_b", "actual": 684.0, "expected": 684.0},
    ]


def test_replay_fails_when_the_final_answer_misses_frozen_anchors(tmp_path):
    source = journey.ROOT / "tests" / "acceptance" / "route_a_gate_c_journey_r07_replay.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["session_id"] = "gate_c_journey_replay_anchor_miss"
    payload["contract"]["final_answer_numeric_anchors"] = ["999999"]
    target = tmp_path / "anchor_miss.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    report = journey.run_journey_replay(target)
    assert report["status"] == "failed"
    assert report["contract_verdicts"]["final_answer_numeric_anchors_present"] is False


def test_replay_fails_when_the_real_tool_output_misses_the_frozen_oracle(tmp_path):
    source = journey.ROOT / "tests" / "acceptance" / "route_a_gate_c_journey_r07_replay.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["session_id"] = "gate_c_journey_replay_oracle_miss"
    payload["contract"]["tool_oracle"]["assertions"][0]["equals"] = 999
    target = tmp_path / "oracle_miss.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    report = journey.run_journey_replay(target)
    assert report["status"] == "failed"
    assert report["contract_verdicts"]["tool_oracle_matches"] is False
    assert any("tool oracle mismatch compare_periods.period_a.rows" in error for error in report["errors"])


def test_replay_refuses_unknown_data_or_foreign_session_ids(tmp_path):
    payload = {
        "schema_version": "route_a_journey_replay.v1",
        "journey_id": "broken",
        "session_id": "real_user_session",
        "question": "q",
        "data": [{"id": "savings_card_orders", "sha256": "wrong"}],
        "script": {"rounds": [{"text": "x"}]},
    }
    target = tmp_path / "broken.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    report = journey.run_journey_replay(target)
    assert report["status"] == "failed"
    assert any("data hash mismatch" in error for error in report["errors"])
    assert any("session_id" in error for error in report["errors"])
    assert report["provider_calls"] == 0
