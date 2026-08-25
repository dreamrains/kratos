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

    def chat_once(self, messages, tools=None, system=None, response_format=None):
        self.calls.append({"messages": messages, "tools": tools, "system": system, "response_format": response_format})
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
    }
    assert result["results"][1]["status"] == "passed"


def test_executor_records_a_transport_failure_then_runs_remaining_frozen_scenarios_once(tmp_path, monkeypatch):
    path = _write_manifest(tmp_path)
    frozen = {"ready": True, "source_digest": "sha256:source", "model_id": "test/model", "total_call_budget": 2, "scenarios": []}
    monkeypatch.setattr(gate_c, "preflight", lambda *args, **kwargs: frozen)
    client = _FakeOnceClient([RuntimeError("network failure"), _valid_response("two", "f2")])

    def request_once(messages, tools=None, system=None, response_format=None):
        value = next(client.responses)
        client.calls.append({"messages": messages, "tools": tools, "system": system, "response_format": response_format})
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
        def chat_once(self, messages, tools=None, system=None, response_format=None):
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            assert persisted["calls_made"] == len(self.calls)
            assert persisted["in_flight_scenario_id"] in {"one", "two"}
            return super().chat_once(messages, tools=tools, system=system, response_format=response_format)

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
