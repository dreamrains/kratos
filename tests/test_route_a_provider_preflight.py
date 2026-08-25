from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from data_agent.llm.client import LLMClient, Response
from scripts.acceptance import route_a_provider_preflight as gate_c


def _manifest() -> dict:
    return {
        "schema_version": gate_c.MANIFEST_SCHEMA,
        "model_id": "test/model",
        "request": {"temperature": 0.0, "max_tokens": 1000, "timeout_seconds": 120, "response_format": {"type": "json_object"}},
        "total_call_budget": 2,
        "scenarios": [
            {
                "id": "one",
                "call_budget": 1,
                "tools_allowed": False,
                "data_ids": ["d1"],
                "question": "q1",
                "fact_packet": [{"id": "f1", "value": "v1"}],
            },
            {
                "id": "two",
                "call_budget": 1,
                "tools_allowed": False,
                "data_ids": ["d2"],
                "question": "q2",
                "fact_packet": [{"id": "f2", "value": "v2"}],
            },
        ],
    }


def _write_manifest(tmp_path):
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    return path


def test_preflight_freezes_data_prompt_model_and_exact_budget_without_provider_call(tmp_path):
    path = _write_manifest(tmp_path)
    report = gate_c.preflight(
        path,
        reference_hashes={"d1": "hash-1", "d2": "hash-2"},
        current_model_id="test/model",
        source_digest=lambda root: "sha256:source",
    )
    assert report["ready"] is True
    assert report["total_call_budget"] == 2
    assert [item["call_budget"] for item in report["scenarios"]] == [1, 1]
    assert all(item["prompt_sha256"].startswith("sha256:") for item in report["scenarios"])


def test_prompt_contains_an_exact_nonempty_response_schema_scaffold():
    scenario = _manifest()["scenarios"][0]
    prompt = gate_c._prompt_for(scenario)
    assert '"scenario_id": "one"' in prompt
    assert '"fact_ids_used": ["f1"]' in prompt
    assert '"method_limitations": ["至少一条来自冻结事实的限制"]' in prompt
    assert '"prohibited_inference_acknowledged": true' in prompt
    assert "不得删除、改名或留空任一字段" in prompt
    assert "至少一个原样数字" in prompt


def test_preflight_rejects_model_or_budget_drift_without_provider_call(tmp_path):
    path = _write_manifest(tmp_path)
    payload = _manifest()
    payload["total_call_budget"] = 3
    payload["request"]["temperature"] = 0.2
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = gate_c.preflight(path, reference_hashes={"d1": "h1", "d2": "h2"}, current_model_id="other", source_digest=lambda root: "sha256:source")
    assert report["ready"] is False
    assert "configured model_id does not match frozen model_id" in report["errors"]
    assert "total_call_budget does not equal the sum of scenario budgets" in report["errors"]
    assert "request.temperature must be exactly 0.0" in report["errors"]


def test_transport_canary_is_a_separate_one_call_frozen_contract_without_provider_call():
    path = gate_c.ROOT / "tests" / "acceptance" / "route_a_gate_c_transport_canary.json"
    report = gate_c.preflight(
        path,
        reference_hashes={"savings_card_before_after": "hash-before-after"},
        current_model_id="openai/deepseek-v4-flash",
        source_digest=lambda root: "sha256:source",
    )
    assert report["ready"] is True
    assert report["total_call_budget"] == 1
    assert report["scenarios"] == [{
        "id": "C01_transport_contract",
        "call_budget": 1,
        "data": [{"id": "savings_card_before_after", "sha256": "hash-before-after"}],
        "prompt_sha256": gate_c._prompt_hash(gate_c._read_manifest(path)["scenarios"][0]),
    }]


def test_r03_truncation_canary_freezes_only_the_failed_scenario_with_an_explicit_larger_budget():
    path = gate_c.ROOT / "tests" / "acceptance" / "route_a_gate_c_r03_truncation_canary.json"
    report = gate_c.preflight(
        path,
        reference_hashes={"game_cross_promotion": "hash-cross-promotion"},
        current_model_id="openai/deepseek-v4-flash",
        source_digest=lambda root: "sha256:source",
    )
    assert report["ready"] is True
    assert report["total_call_budget"] == 1
    assert report["request"] == {
        "temperature": 0.0,
        "max_tokens": 2000,
        "timeout_seconds": 120,
        "response_format": {"type": "json_object"},
    }
    assert report["scenarios"][0]["id"] == "R03_dirty_cross_promotion"
    assert report["scenarios"][0]["prompt_sha256"] == "sha256:980727a4567acc13a8d0227a477f1e2771f3e88a7bae9542f994622e95be4b9c"


def test_main_batch_uses_the_r03_canarys_verified_token_budget():
    path = gate_c.ROOT / "tests" / "acceptance" / "route_a_gate_c_candidates.json"
    manifest = gate_c._read_manifest(path)
    assert manifest["request"]["max_tokens"] == 2000
    report = gate_c.preflight(
        path,
        reference_hashes={
            "savings_card_before_after": "h-before-after",
            "game_cross_promotion": "h-cross-promotion",
            "game_a_rewarded_video": "h-video",
            "game_a_in_app_purchase": "h-iap",
            "game_a_banner": "h-banner",
            "savings_card_orders": "h-orders",
            "game_b_retention": "h-retention",
            "savings_card_user_payments": "h-payments",
        },
        current_model_id="openai/deepseek-v4-flash",
        source_digest=lambda root: "sha256:source",
    )
    assert report["ready"] is True
    assert report["total_call_budget"] == 7
    assert report["request"]["max_tokens"] == 2000


def test_chat_once_makes_one_call_and_never_retries():
    calls = []

    def fail_once(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("transport failure")

    with patch("data_agent.llm.client.completion", fail_once):
        with pytest.raises(RuntimeError, match="transport failure"):
            LLMClient(model_id="test/model").chat_once(
                [{"role": "user", "content": "q"}], response_format={"type": "json_object"}
            )
    assert len(calls) == 1
    assert calls[0]["num_retries"] == 0
    assert calls[0]["response_format"] == {"type": "json_object"}


class _FakeOnceClient:
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
        return next(self.responses)


def _valid_response(scenario_id, fact_id):
    return Response(text=json.dumps({
        "scenario_id": scenario_id,
        "decision": f"bounded decision {fact_id[-1]}",
        "fact_ids_used": [fact_id],
        "method_limitations": ["observational"],
        "prohibited_inference_acknowledged": True,
        "next_action": "collect the missing comparison data",
    }))


def test_executor_makes_exactly_one_no_tool_call_per_successful_scenario(tmp_path, monkeypatch):
    path = _write_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 2, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    client = _FakeOnceClient([_valid_response("one", "f1"), _valid_response("two", "f2")])
    result = gate_c.execute_authorized_batch(path, authorized_source_digest="sha256:source", client=client)
    assert result["status"] == "passed"
    assert result["calls_made"] == 2
    assert len(client.calls) == 2
    assert all(call["tools"] is None for call in client.calls)
    assert all(call["response_format"] == {"type": "json_object"} for call in client.calls)
    assert result["results"][0]["response_summary"] == {
        "fact_ids_used": ["f1"],
        "method_limitations_count": 1,
        "prohibited_inference_acknowledged": True,
        "decision_characters": 18,
        "next_action_characters": 35,
        "json_envelope": "direct",
        "response_shape": "direct_object",
        "response_length_bucket": "1_to_256",
        "response_reasoning_length_bucket": "empty_or_non_string",
        "response_finish_reason": "stop",
    }


def test_executor_records_a_failed_response_then_runs_remaining_frozen_scenarios_once(tmp_path, monkeypatch):
    path = _write_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 2, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    client = _FakeOnceClient([Response(text="not json"), _valid_response("two", "f2")])
    result = gate_c.execute_authorized_batch(path, authorized_source_digest="sha256:source", client=client)
    assert result["status"] == "completed_with_failures"
    assert result["calls_made"] == 2
    assert len(client.calls) == 2
    assert result["results"][0] == {
        "id": "one",
        "status": "failed",
        "failure_stage": "provider_response_validation",
        "error_code": "response_not_json",
        "response_shape": "no_json_object_start",
        "response_length_bucket": "1_to_256",
        "response_reasoning_length_bucket": "empty_or_non_string",
        "response_finish_reason": "stop",
    }
    assert result["results"][1]["status"] == "passed"


def test_executor_records_a_transport_failure_then_runs_remaining_frozen_scenarios_once(tmp_path, monkeypatch):
    path = _write_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 2, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    client = _FakeOnceClient([RuntimeError("network failure"), _valid_response("two", "f2")])

    def request_once(messages, tools=None, system=None, response_format=None, max_tokens=None):
        value = next(client.responses)
        client.calls.append({"messages": messages, "tools": tools, "system": system, "response_format": response_format, "max_tokens": max_tokens})
        if isinstance(value, Exception):
            raise value
        return value

    client.chat_once = request_once
    result = gate_c.execute_authorized_batch(path, authorized_source_digest="sha256:source", client=client)
    assert result["status"] == "completed_with_failures"
    assert result["calls_made"] == 2
    assert len(client.calls) == 2
    assert result["results"][0]["failure_stage"] == "provider_request"
    assert result["results"][0]["error_code"] == "provider_request_error"
    assert result["results"][0]["exception_type"] == "RuntimeError"


def test_response_rejects_template_echo_and_requires_a_frozen_numeric_anchor():
    scenario = _manifest()["scenarios"][0]
    scenario["fact_packet"] = [{"id": "f1", "value": "61 matched users"}]
    echoed = Response(text=json.dumps({
        "scenario_id": "one",
        "decision": "基于冻结事实的有边界判断",
        "fact_ids_used": ["f1"],
        "method_limitations": ["observational"],
        "prohibited_inference_acknowledged": True,
        "next_action": "collect a control group",
    }))
    with pytest.raises(gate_c.ProviderResponseValidationError, match="placeholder_decision"):
        gate_c._validate_response(scenario, echoed)

    ungrounded = Response(text=json.dumps({
        "scenario_id": "one",
        "decision": "a bounded decision",
        "fact_ids_used": ["f1"],
        "method_limitations": ["observational"],
        "prohibited_inference_acknowledged": True,
        "next_action": "collect a control group",
    }))
    with pytest.raises(gate_c.ProviderResponseValidationError, match="decision_missing_frozen_numeric_anchor"):
        gate_c._validate_response(scenario, ungrounded)


@pytest.mark.parametrize("envelope", [
    lambda payload: f"```json\n{payload}\n```",
    lambda payload: f"JSON follows:\n{payload}",
    lambda payload: f"展示前缀 {{不是 JSON}}。\n{payload}\n展示后缀。",
])
def test_response_accepts_one_wrapped_json_object_without_retaining_wrapper(envelope):
    scenario = _manifest()["scenarios"][0]
    payload = json.dumps({
        "scenario_id": "one",
        "decision": "bounded decision 1",
        "fact_ids_used": ["f1"],
        "method_limitations": ["observational"],
        "prohibited_inference_acknowledged": True,
        "next_action": "collect a control group",
    })
    summary = gate_c._response_summary(gate_c._validate_response(scenario, Response(text=envelope(payload))))
    assert summary["json_envelope"] in {"fenced", "embedded"}
    assert summary["response_shape"] in {"fenced_object", "embedded_unique_object"}
    assert "response" not in summary


@pytest.mark.parametrize(("text", "finish_reason", "code", "shape"), [
    ("", "stop", "response_not_json", "empty"),
    ("plain prose only", "stop", "response_not_json", "no_json_object_start"),
    ("{not valid json", "stop", "response_not_json", "invalid_json_object"),
    ("[]", "stop", "response_not_json_object", "direct_non_object"),
])
def test_response_failure_records_only_safe_transport_shape(text, finish_reason, code, shape):
    scenario = _manifest()["scenarios"][0]
    with pytest.raises(gate_c.ProviderResponseValidationError) as error:
        gate_c._validate_response(scenario, Response(text=text, finish_reason=finish_reason))
    assert error.value.code == code
    assert error.value.diagnostics == {
        "response_shape": shape,
        "response_length_bucket": "empty_or_non_string" if not text else "1_to_256",
        "response_reasoning_length_bucket": "empty_or_non_string",
        "response_finish_reason": finish_reason,
    }


def test_response_length_is_a_truncation_even_if_partial_text_looks_structured():
    scenario = _manifest()["scenarios"][0]
    response = Response(
        text=json.dumps({"scenario_id": "one"}),
        finish_reason="length",
        reasoning_content="internal reasoning" * 30,
    )
    with pytest.raises(gate_c.ProviderResponseValidationError, match="response_truncated") as error:
        gate_c._validate_response(scenario, response)
    assert error.value.diagnostics == {
        "response_shape": "truncated_before_complete",
        "response_length_bucket": "1_to_256",
        "response_reasoning_length_bucket": "257_to_1024",
        "response_finish_reason": "length",
    }


def test_response_rejects_multiple_independent_json_objects_without_selecting_one():
    scenario = _manifest()["scenarios"][0]
    payload = json.dumps({
        "scenario_id": "one",
        "decision": "bounded decision 1",
        "fact_ids_used": ["f1"],
        "method_limitations": ["observational"],
        "prohibited_inference_acknowledged": True,
        "next_action": "collect a control group",
    })
    with pytest.raises(gate_c.ProviderResponseValidationError, match="response_ambiguous_json_objects") as error:
        gate_c._validate_response(scenario, Response(text=f"{payload}\n{payload}"))
    assert error.value.diagnostics["response_shape"] == "multiple_json_objects"


def test_executor_persists_safe_transport_diagnostics_but_never_provider_text(tmp_path, monkeypatch):
    path = _write_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 2, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    result = gate_c.execute_authorized_batch(
        path,
        authorized_source_digest="sha256:source",
        client=_FakeOnceClient([Response(text="secret provider prose"), _valid_response("two", "f2")]),
    )
    failure = result["results"][0]
    assert failure["response_shape"] == "no_json_object_start"
    assert "secret provider prose" not in json.dumps(result)
    assert "text" not in failure


def test_execution_report_is_atomic_sanitized_and_limited_to_audit_directory(tmp_path, monkeypatch):
    audit_root = tmp_path / "docs" / "audit"
    audit_root.mkdir(parents=True)
    monkeypatch.setattr(gate_c, "ROOT", tmp_path)
    report = {
        "source_digest": "sha256:source",
        "status": "passed",
        "results": [{"id": "one", "response_summary": {"decision_characters": 18}}],
    }
    path = gate_c.write_execution_report(audit_root / "batch.json", report)
    assert json.loads(path.read_text(encoding="utf-8")) == report
    assert not (audit_root / ".batch.json.tmp").exists()
    with pytest.raises(gate_c.ProviderPreflightError, match="forbidden raw-response"):
        gate_c.write_execution_report(audit_root / "unsafe.json", {"response": "uncontrolled"})
    with pytest.raises(gate_c.ProviderPreflightError, match="docs/audit"):
        gate_c.write_execution_report(tmp_path / "outside.json", report)


def test_executor_persists_in_flight_and_each_completed_call(tmp_path, monkeypatch):
    path = _write_manifest(tmp_path)
    audit_root = tmp_path / "docs" / "audit"
    audit_root.mkdir(parents=True)
    report_path = audit_root / "batch.json"
    monkeypatch.setattr(gate_c, "ROOT", tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 2, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)

    class RecordingClient(_FakeOnceClient):
        def chat_once(self, messages, tools=None, system=None, response_format=None, max_tokens=None):
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            assert persisted["calls_made"] == len(self.calls)
            assert persisted["in_flight_scenario_id"] in {"one", "two"}
            return super().chat_once(messages, tools=tools, system=system, response_format=response_format, max_tokens=max_tokens)

    client = RecordingClient([_valid_response("one", "f1"), _valid_response("two", "f2")])
    result = gate_c.execute_authorized_batch(
        path,
        authorized_source_digest="sha256:source",
        client=client,
        report_path=report_path,
    )
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["status"] == "passed"
    assert persisted == result
    assert "in_flight_scenario_id" not in persisted
    with pytest.raises(gate_c.ProviderPreflightError, match="already exists"):
        gate_c.initialize_execution_report(report_path, result)


def _ladder_manifest() -> dict:
    return {
        "schema_version": gate_c.MANIFEST_SCHEMA,
        "model_id": "test/model",
        "request": {
            "temperature": 0.0,
            "timeout_seconds": 120,
            "response_format": {"type": "json_object"},
            "max_tokens_ladder": [2000, 8000, 32000],
        },
        "total_call_budget": 3,
        "scenarios": [
            {
                "id": "one",
                "call_budget": 3,
                "tools_allowed": False,
                "data_ids": ["d1"],
                "question": "q1",
                "fact_packet": [{"id": "f1", "value": "v1"}],
            }
        ],
    }


def _write_ladder_manifest(tmp_path):
    path = tmp_path / "ladder.json"
    path.write_text(json.dumps(_ladder_manifest()), encoding="utf-8")
    return path


def test_preflight_freezes_the_budget_ladder_and_its_worst_case_budget(tmp_path):
    report = gate_c.preflight(
        _write_ladder_manifest(tmp_path),
        reference_hashes={"d1": "h1"},
        current_model_id="test/model",
        source_digest=lambda root: "sha256:source",
    )
    assert report["ready"] is True
    assert report["total_call_budget"] == 3
    assert report["request"]["max_tokens_ladder"] == [2000, 8000, 32000]


def test_preflight_rejects_invalid_budget_ladders(tmp_path):
    def errors_for(request_overrides, scenario_overrides=None):
        payload = _ladder_manifest()
        payload["request"].update(request_overrides)
        if scenario_overrides:
            payload["scenarios"][0].update(scenario_overrides)
        path = tmp_path / "invalid.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        report = gate_c.preflight(
            path,
            reference_hashes={"d1": "h1"},
            current_model_id="test/model",
            source_digest=lambda root: "sha256:source",
        )
        return " ".join(report["errors"])

    assert "max_tokens and max_tokens_ladder are mutually exclusive" in errors_for({"max_tokens": 2000})
    assert "strictly ascending" in errors_for({"max_tokens_ladder": [8000, 2000]})
    assert "1 to 3" in errors_for({"max_tokens_ladder": []})
    assert "1 to 3" in errors_for({"max_tokens_ladder": [1, 2, 3, 4]})
    assert "must be between 100 and 128000" in errors_for({"max_tokens_ladder": [50, 8000]})
    assert "call_budget must equal the max_tokens_ladder length" in errors_for(
        {"max_tokens_ladder": [2000, 8000, 32000]}, {"call_budget": 1},
    )


def _truncated() -> Response:
    return Response(text="", finish_reason="length")


def test_executor_climbs_the_ladder_only_on_truncation_and_stops_at_success(tmp_path, monkeypatch):
    path = _write_ladder_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 3, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    client = _FakeOnceClient([_truncated(), _truncated(), _valid_response("one", "f1")])
    result = gate_c.execute_authorized_batch(path, authorized_source_digest="sha256:source", client=client)
    assert result["status"] == "passed"
    assert result["calls_made"] == 3
    assert [call["max_tokens"] for call in client.calls] == [2000, 8000, 32000]
    scenario_result = result["results"][0]
    assert scenario_result["status"] == "passed"
    assert scenario_result["max_tokens_used"] == 32000
    assert [attempt["max_tokens"] for attempt in scenario_result["max_tokens_attempts"]] == [2000, 8000]
    assert scenario_result["max_tokens_attempts"][0]["error_code"] == "response_truncated"


def test_executor_does_not_escalate_semantic_failures(tmp_path, monkeypatch):
    path = _write_ladder_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 3, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    client = _FakeOnceClient([Response(text="not json")])
    result = gate_c.execute_authorized_batch(path, authorized_source_digest="sha256:source", client=client)
    assert result["calls_made"] == 1
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["error_code"] == "response_not_json"


def test_executor_reports_failure_after_exhausting_the_ladder(tmp_path, monkeypatch):
    path = _write_ladder_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 3, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    client = _FakeOnceClient([_truncated(), _truncated(), _truncated()])
    result = gate_c.execute_authorized_batch(path, authorized_source_digest="sha256:source", client=client)
    assert result["status"] == "completed_with_failures"
    assert result["calls_made"] == 3
    failure = result["results"][0]
    assert failure["error_code"] == "response_truncated"
    assert [attempt["max_tokens"] for attempt in failure["max_tokens_attempts"]] == [2000, 8000, 32000]


def test_executor_does_not_escalate_transport_errors(tmp_path, monkeypatch):
    path = _write_ladder_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 3, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    client = _FakeOnceClient([RuntimeError("network failure")])

    def request_once(messages, tools=None, system=None, response_format=None, max_tokens=None):
        value = next(client.responses)
        client.calls.append({"messages": messages, "max_tokens": max_tokens})
        if isinstance(value, Exception):
            raise value
        return value

    client.chat_once = request_once
    result = gate_c.execute_authorized_batch(path, authorized_source_digest="sha256:source", client=client)
    assert result["calls_made"] == 1
    assert result["results"][0]["error_code"] == "provider_request_error"


def test_r05_budget_ladder_canary_freezes_the_ladder_against_the_failed_call():
    path = gate_c.ROOT / "tests" / "acceptance" / "route_a_gate_c_r05_budget_ladder_canary.json"
    report = gate_c.preflight(
        path,
        reference_hashes={
            "savings_card_orders": "h-orders",
            "savings_card_user_payments": "h-payments",
        },
        current_model_id="openai/deepseek-v4-flash",
        source_digest=lambda root: "sha256:source",
    )
    assert report["ready"] is True
    assert report["total_call_budget"] == 3
    assert report["request"]["max_tokens_ladder"] == [2000, 8000, 32000]
    assert "max_tokens" not in report["request"]
    scenario = report["scenarios"][0]
    assert scenario["id"] == "R05_relationship_scope"
    # The prompt stays byte-identical to the failed main-batch call; the only
    # delta is the frozen escalation ladder.
    main = gate_c._read_manifest(gate_c.ROOT / "tests" / "acceptance" / "route_a_gate_c_candidates.json")
    main_r05 = next(item for item in main["scenarios"] if item["id"] == "R05_relationship_scope")
    assert scenario["prompt_sha256"] == gate_c._prompt_hash(main_r05)
    assert scenario["prompt_sha256"] == "sha256:2f3103f89767535d9509c9b931eb4cad652f3412c4e6f2a63de3ed903c41694d"


def _reference_hash_map():
    return {
        "savings_card_before_after": "h-before-after",
        "game_cross_promotion": "h-cross-promotion",
        "game_a_rewarded_video": "h-video",
        "game_a_in_app_purchase": "h-iap",
        "game_a_banner": "h-banner",
        "savings_card_orders": "h-orders",
        "game_b_retention": "h-retention",
        "savings_card_user_payments": "h-payments",
    }


def test_main_ladder_batch_freezes_identical_prompts_with_ladder_semantics():
    path = gate_c.ROOT / "tests" / "acceptance" / "route_a_gate_c_main_ladder.json"
    report = gate_c.preflight(
        path,
        reference_hashes=_reference_hash_map(),
        current_model_id="openai/deepseek-v4-flash",
        source_digest=lambda root: "sha256:source",
    )
    assert report["ready"] is True
    assert report["total_call_budget"] == 21
    assert report["request"]["max_tokens_ladder"] == [2000, 8000, 32000]
    assert "max_tokens" not in report["request"]
    assert all(item["call_budget"] == 3 for item in report["scenarios"])
    assert len(report["scenarios"]) == 7

    # Prompts stay byte-identical to the scalar main batch...
    legacy = gate_c._read_manifest(gate_c.ROOT / "tests" / "acceptance" / "route_a_gate_c_candidates.json")
    legacy_hashes = {item["id"]: gate_c._prompt_hash(item) for item in legacy["scenarios"]}
    assert {item["id"]: item["prompt_sha256"] for item in report["scenarios"]} == legacy_hashes
    # ...and to the executed 2000-token batch receipt (single-variable delta).
    executed = json.loads(
        (gate_c.ROOT / "docs" / "audit" / "2026-08-25-gate-c-main-model-r01-r07-2000-batch-report.json")
        .read_text(encoding="utf-8")
    )
    executed_hashes = {item["id"]: item["prompt_sha256"] for item in executed["scenarios"]}
    assert {item["id"]: item["prompt_sha256"] for item in report["scenarios"]} == executed_hashes
