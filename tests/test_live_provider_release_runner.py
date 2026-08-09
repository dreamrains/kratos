"""Contract tests for the three-run real-provider release gate."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import replay_analysis_reliability  # noqa: E402
from acceptance.live_provider_gate_contract import (  # noqa: E402
    evaluate_live_provider_run,
    validate_live_provider_gate_receipt,
)
from data_agent.agent.answer_quality import render_audited_analysis_answer  # noqa: E402
from replay_analysis_reliability import (  # noqa: E402
    ProviderConfigurationUnavailable,
    _latest_final_audit,
    _material_publication_actions,
    _repeated_failure_max,
    _session_tool_outcomes,
    _unresolved_fallback_blocked_calls,
    _verified_material_claim_count,
    build_live_provider_receipt,
    run_live_provider_acceptance,
    write_live_provider_receipt,
)


def _passing_run(index: int) -> dict:
    return {
        "run_id": f"live_{index}",
        "status": "PASS",
        "reason_codes": [],
        "upload_contract_active": True,
        "tool_calls": 4,
        "data_quality_computations": 1,
        "structured_computations": 2,
        "projected_evidence": 2,
        "final_audit_status": "pass",
        "publication_actions": {"claim_1": "verified"},
        "publication_length": 1200,
        "publication_language": "zh",
        "has_findings": True,
        "has_recommendations": True,
        "has_limitations": True,
        "generic_warning_present": False,
        "progress_before_final": True,
        "persisted_matches_streamed": True,
        "repeated_failure_max": 1,
        "unresolved_fallback_blocked_calls": 0,
        "verified_material_claims": 1,
        "measurement_bookkeeping_scheduled_analysis": False,
        "requirements": {
            "data_quality": "satisfied",
            "descriptive": "satisfied",
            "relationship": "satisfied",
            "limitations": "satisfied",
        },
    }


def _passing_receipt() -> dict:
    return build_live_provider_receipt(
        source_digest="sha256:" + "a" * 64,
        source_commit="a" * 40,
        provider_model="configured-model",
        runs=[_passing_run(index) for index in range(1, 4)],
    )


def test_mixed_tier_limited_completion_retains_verified_core_for_gate_f():
    draft = "已验证核心：样本量为 125。\n另一个结论尚未独立验证。"
    audit = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_mixed_limited",
        "status": "blocked",
        "public_text": draft,
        "claims": [
            {
                "id": "claim_core",
                "text": "已验证核心：样本量为 125。",
                "claim_type": "numeric",
                "material": True,
            },
            {
                "id": "claim_other",
                "text": "另一个结论尚未独立验证。",
                "claim_type": "descriptive",
                "material": True,
            },
        ],
        "claim_checks": [
            {"claim_id": "claim_core", "status": "passed", "reason_codes": []},
            {
                "claim_id": "claim_other",
                "status": "failed",
                "reason_codes": [
                    "missing_evidence_identity",
                    "evidence_check_failed",
                ],
            },
        ],
    }
    publication = render_audited_analysis_answer(
        draft=draft,
        audit=audit,
        completion=SimpleNamespace(status="complete_with_limits"),
        mode="tiered",
    )
    run = _passing_run(1)
    run["final_audit_status"] = "blocked"
    run["publication_actions"] = _material_publication_actions(
        audit,
        publication.actions,
    )
    run["verified_material_claims"] = _verified_material_claim_count(
        audit,
        publication.actions,
    )

    result = evaluate_live_provider_run(run)

    assert publication.actions == {
        "claim_core": "verified",
        "claim_other": "unsupported",
    }
    assert result["status"] == "PASS", result


def test_verified_material_claim_count_ignores_nonmaterial_verified_actions():
    audit = {
        "claims": [
            {"id": "claim_heading", "material": False},
            {"id": "claim_core", "material": True},
            {"id": "claim_other", "material": True},
        ],
    }
    actions = {
        "claim_heading": "verified",
        "claim_core": "verified",
        "claim_other": "exploratory",
    }

    assert _material_publication_actions(audit, actions) == {
        "claim_core": "verified",
        "claim_other": "exploratory",
    }
    assert _verified_material_claim_count(audit, actions) == 1


def test_latest_final_audit_hydrates_persisted_artifact(tmp_path):
    audit = {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_hydrated",
        "status": "blocked",
        "public_text": "已验证核心。",
        "claims": [
            {
                "id": "claim_core",
                "text": "已验证核心。",
                "claim_type": "descriptive",
                "material": True,
            }
        ],
        "claim_checks": [
            {"claim_id": "claim_core", "status": "passed", "reason_codes": []}
        ],
    }
    artifact = tmp_path / "final_audit.json"
    raw = json.dumps(audit, ensure_ascii=False).encode("utf-8")
    artifact.write_bytes(raw)
    ref = {
        "contract_version": "final_answer_audit.v1",
        "id": audit["id"],
        "status": audit["status"],
        "artifact_path": str(artifact),
        "artifact_digest": hashlib.sha256(raw).hexdigest(),
    }
    state = SimpleNamespace(verification_reports=[ref])

    hydrated = _latest_final_audit(state)

    assert hydrated["claims"] == audit["claims"]
    assert hydrated["claim_checks"] == audit["claim_checks"]


def test_live_receipt_rejects_unknown_top_level_fields():
    receipt = _passing_receipt()
    receipt["raw_prompt"] = "private prompt must never enter a receipt"

    result = validate_live_provider_gate_receipt(
        receipt,
        expected_source_digest="sha256:" + "a" * 64,
    )

    assert result.status == "FAIL"
    assert "unsafe_live_receipt_field" in result.reason_codes


def test_live_receipt_rejects_unknown_run_fields():
    receipt = _passing_receipt()
    receipt["runs"][0]["raw_answer"] = "private answer must never enter a receipt"

    result = validate_live_provider_gate_receipt(
        receipt,
        expected_source_digest="sha256:" + "a" * 64,
    )

    assert result.status == "FAIL"
    assert "unsafe_live_run_field" in result.reason_codes


@pytest.mark.parametrize("status", ["FAIL", "BLOCKED"])
def test_nonpassing_live_receipt_still_rejects_unknown_run_fields(status):
    receipt = _passing_receipt()
    receipt.update({
        "status": status,
        "accepted": False,
        "overall_status": status,
        "live_provider_status": status,
        "reason_codes": ["synthetic_failure"],
    })
    receipt["runs"][0]["raw_rows"] = [{"private_value": "must not persist"}]

    result = validate_live_provider_gate_receipt(
        receipt,
        expected_source_digest="sha256:" + "a" * 64,
    )

    assert result.status == "FAIL"
    assert "unsafe_live_run_field" in result.reason_codes


def test_live_receipt_rejects_unknown_publication_actions():
    receipt = _passing_receipt()
    receipt["runs"][0]["publication_actions"] = {
        "claim_1": "raw model reasoning",
    }

    result = validate_live_provider_gate_receipt(
        receipt,
        expected_source_digest="sha256:" + "a" * 64,
    )

    assert result.status == "FAIL"
    assert "unsafe_live_publication_action" in result.reason_codes


def test_live_receipt_writer_validates_before_atomic_overwrite(tmp_path):
    receipt_path = tmp_path / "analysis_live_provider_gate.v1.json"
    safe = _passing_receipt()
    write_live_provider_receipt(safe, receipt_path)
    unsafe = copy.deepcopy(safe)
    unsafe["raw_prompt"] = "private prompt must never enter a receipt"

    with pytest.raises(ValueError, match="unsafe_live_receipt_field"):
        write_live_provider_receipt(unsafe, receipt_path)

    assert json.loads(receipt_path.read_text(encoding="utf-8")) == safe


def test_live_receipt_writer_does_not_persist_unsafe_blocked_run(tmp_path):
    receipt_path = tmp_path / "analysis_live_provider_gate.v1.json"
    safe = _passing_receipt()
    write_live_provider_receipt(safe, receipt_path)
    unsafe = copy.deepcopy(safe)
    unsafe.update({
        "status": "BLOCKED",
        "accepted": False,
        "overall_status": "BLOCKED",
        "live_provider_status": "BLOCKED",
        "reason_codes": ["provider_timeout"],
    })
    unsafe["runs"][0]["raw_answer"] = "private answer must never enter a receipt"

    with pytest.raises(ValueError, match="unsafe_live_run_field"):
        write_live_provider_receipt(unsafe, receipt_path)

    assert json.loads(receipt_path.read_text(encoding="utf-8")) == safe


def test_live_gate_requires_exactly_three_passing_runs():
    receipt = build_live_provider_receipt(
        source_digest="sha256:" + "a" * 64,
        source_commit="a" * 40,
        provider_model="configured-model",
        runs=[_passing_run(1), _passing_run(2)],
    )

    assert receipt["status"] == "FAIL"
    assert "live_run_count_mismatch" in receipt["reason_codes"]


def test_one_shallow_or_empty_run_fails_entire_live_gate():
    runs = [_passing_run(1), _passing_run(2), _passing_run(3)]
    runs[1]["publication_length"] = 0
    runs[1]["requirements"]["relationship"] = "missing"

    receipt = build_live_provider_receipt(
        source_digest="sha256:" + "a" * 64,
        source_commit="a" * 40,
        provider_model="configured-model",
        runs=runs,
    )

    assert receipt["status"] == "FAIL"
    assert "live_run_failed" in receipt["reason_codes"]
    assert receipt["runs"][1]["status"] == "FAIL"
    assert "publication_too_short" in receipt["runs"][1]["reason_codes"]
    assert "relationship_requirement_missing" in receipt["runs"][1]["reason_codes"]


def test_missing_provider_is_blocked_not_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(
        replay_analysis_reliability,
        "_run_one_live_provider_analysis",
        Mock(
            side_effect=ProviderConfigurationUnavailable(
                "provider_credentials_unavailable"
            )
        ),
    )
    monkeypatch.setattr(
        replay_analysis_reliability,
        "get_config",
        lambda: SimpleNamespace(model_id="configured-model"),
    )

    receipt = run_live_provider_acceptance(tmp_path, runs=3)

    assert receipt["status"] == "BLOCKED"
    assert receipt["reason_codes"] == ["provider_credentials_unavailable"]


def test_credentialless_provider_is_attempted_instead_of_preblocked(
    monkeypatch,
    tmp_path,
):
    runner = Mock(side_effect=[_passing_run(1), _passing_run(2), _passing_run(3)])
    monkeypatch.setattr(
        replay_analysis_reliability,
        "_run_one_live_provider_analysis",
        runner,
    )
    monkeypatch.setattr(
        replay_analysis_reliability,
        "get_config",
        lambda: SimpleNamespace(
            model_id="local/credentialless",
            api_key=None,
            api_base="http://127.0.0.1:9000/v1",
        ),
    )

    receipt = run_live_provider_acceptance(tmp_path, runs=3)

    assert runner.call_count == 3
    assert receipt["status"] == "PASS"
    assert receipt["provider_model"] == "local/credentialless"


def test_live_observer_accumulates_tools_across_resumed_segments():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_load",
                "function": {"name": "load_data", "arguments": "{}"},
            }],
        },
        {"role": "tool", "tool_call_id": "call_load", "content": "loaded"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_correlation",
                "function": {"name": "correlation_analysis", "arguments": "{}"},
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "call_correlation",
            "content": '{"error": "missing plan", "error_type": "scope_error"}',
        },
    ]

    outcomes = _session_tool_outcomes(messages)

    empty_hash = hashlib.sha1(b"{}").hexdigest()[:12]
    assert outcomes == [
        {
            "tool_name": "load_data",
            "success": True,
            "error_category": "",
            "arguments_hash": empty_hash,
            "fallback_resolution_blocked": False,
        },
        {
            "tool_name": "correlation_analysis",
            "success": False,
            "error_category": "scope_error",
            "arguments_hash": empty_hash,
            "fallback_resolution_blocked": False,
        },
    ]


def _tool_failure_messages(*calls):
    messages = []
    for index, (tool_name, arguments, error_category) in enumerate(calls, 1):
        call_id = f"call_{index}"
        messages.extend([
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": call_id,
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(
                            arguments,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    },
                }],
            },
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps({
                    "error": "bounded failure",
                    "error_type": error_category,
                }),
            },
        ])
    return messages


def test_different_arguments_are_not_one_repeated_failure():
    messages = _tool_failure_messages(
        ("preview_data", {"name": "a"}, "budget_exceeded"),
        ("preview_data", {"name": "b"}, "budget_exceeded"),
        ("preview_data", {"name": "c"}, "budget_exceeded"),
    )

    outcomes = _session_tool_outcomes(messages)

    assert _repeated_failure_max(outcomes) == 1
    assert len({outcome["arguments_hash"] for outcome in outcomes}) == 3


def test_identical_call_failure_three_times_is_rejected():
    messages = _tool_failure_messages(
        *[("preview_data", {"name": "a"}, "budget_exceeded")] * 3
    )

    outcomes = _session_tool_outcomes(messages)

    assert _repeated_failure_max(outcomes) == 3
    assert len({outcome["arguments_hash"] for outcome in outcomes}) == 1


def test_fallback_resolution_block_is_counted_separately():
    messages = _tool_failure_messages(
        ("preview_data", {"name": "main"}, "budget_exceeded"),
    )
    messages[-1]["content"] = json.dumps({
        "error": (
            "Fallback Python result must be resolved into evidence, limitations, "
            "task state, or user confirmation before more exploration."
        ),
        "error_type": "budget_exceeded",
    })

    outcomes = _session_tool_outcomes(messages)

    assert outcomes[0]["fallback_resolution_blocked"] is True


def test_successful_resolution_clears_prior_fallback_block_from_unresolved_count():
    messages = _tool_failure_messages(
        ("preview_data", {"name": "main"}, "budget_exceeded"),
    )
    messages[-1]["content"] = json.dumps({
        "error": (
            "Fallback Python result must be resolved into evidence, limitations, "
            "task state, or user confirmation before more exploration."
        ),
        "error_type": "budget_exceeded",
    })
    messages.extend([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_resolution",
                "function": {
                    "name": "record_evidence_record",
                    "arguments": json.dumps({"record_json": "{}"}),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "call_resolution",
            "content": json.dumps({"evidence_id": "ev_current"}),
        },
    ])

    outcomes = _session_tool_outcomes(messages)

    assert _unresolved_fallback_blocked_calls(outcomes) == 0


def test_failed_resolution_keeps_prior_fallback_block_unresolved():
    messages = _tool_failure_messages(
        ("preview_data", {"name": "main"}, "budget_exceeded"),
    )
    messages[-1]["content"] = json.dumps({
        "error": (
            "Fallback Python result must be resolved into evidence, limitations, "
            "task state, or user confirmation before more exploration."
        ),
        "error_type": "budget_exceeded",
    })
    messages.extend(_tool_failure_messages(
        ("record_evidence_record", {"record_json": "{}"}, "invalid_parameter"),
    ))

    outcomes = _session_tool_outcomes(messages)

    assert _unresolved_fallback_blocked_calls(outcomes) == 1


def test_success_text_cannot_create_fallback_resolution_block_signal():
    message = (
        "Fallback Python result must be resolved into evidence, limitations, "
        "task state, or user confirmation before more exploration."
    )
    outcomes = _session_tool_outcomes([
        {
            "role": "assistant",
            "tool_calls": [{
                "id": "call_success",
                "function": {"name": "preview_data", "arguments": "{}"},
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "call_success",
            "content": message,
        },
    ])

    assert outcomes[0]["success"] is True
    assert outcomes[0]["fallback_resolution_blocked"] is False


def test_invalid_argument_json_gets_deterministic_bounded_hash():
    raw_arguments = "{not-json"
    expected_raw = json.dumps(
        {"raw": raw_arguments},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    outcomes = _session_tool_outcomes([
        {
            "role": "assistant",
            "tool_calls": [{
                "id": "call_invalid",
                "function": {
                    "name": "preview_data",
                    "arguments": raw_arguments,
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "call_invalid",
            "content": '{"error":"invalid","error_type":"invalid_parameter"}',
        },
    ])

    assert outcomes[0]["arguments_hash"] == hashlib.sha1(
        expected_raw.encode("utf-8")
    ).hexdigest()[:12]


def test_unresolved_fallback_cascade_fails_live_run():
    run = _passing_run(1)
    run["unresolved_fallback_blocked_calls"] = 1

    result = replay_analysis_reliability._evaluate_live_run(run)

    assert result["status"] == "FAIL"
    assert "unresolved_fallback_cascade" in result["reason_codes"]


def test_fixed_live_scenario_requires_verified_material_claim():
    run = _passing_run(1)
    run["verified_material_claims"] = 0
    run["publication_actions"] = {"claim_1": "exploratory"}

    result = replay_analysis_reliability._evaluate_live_run(run)

    assert result["status"] == "FAIL"
    assert "verified_material_claim_missing" in result["reason_codes"]


def test_verified_material_claim_count_must_match_publication_actions():
    run = _passing_run(1)
    run["verified_material_claims"] = 2

    result = replay_analysis_reliability._evaluate_live_run(run)

    assert result["status"] == "FAIL"
    assert "verified_material_claim_count_mismatch" in result["reason_codes"]


@pytest.mark.parametrize("status", ["FAIL", "BLOCKED"])
@pytest.mark.parametrize("field", ["arguments", "code", "answer", "error_message"])
def test_nonpassing_receipt_rejects_raw_content_fields(status, field):
    receipt = _passing_receipt()
    receipt.update({
        "status": status,
        "accepted": False,
        "overall_status": status,
        "live_provider_status": status,
        "reason_codes": ["synthetic_failure"],
    })
    receipt["runs"][0][field] = "must not persist"

    result = validate_live_provider_gate_receipt(
        receipt,
        expected_source_digest="sha256:" + "a" * 64,
    )

    assert result.status == "FAIL"
    assert "unsafe_live_run_field" in result.reason_codes
