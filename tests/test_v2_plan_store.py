from __future__ import annotations

import pytest

from data_agent.v2.plan_store import (
    DurablePlanStatus,
    PlanConflict,
    PlanStore,
)
from data_agent.v2.planner import AnalysisPlan, AnalysisKind, PlanStatus


def _context() -> dict:
    return {
        "filename": "sales.csv",
        "source_fingerprint": "sha256:" + "a" * 64,
        "row_count": 3,
        "columns": [{"name": "sales", "dtype": "int64", "role": "numeric"}],
    }


def _ready(question: str = "平均销售额？") -> AnalysisPlan:
    return AnalysisPlan(
        status=PlanStatus.READY,
        user_question=question,
        analysis_kind=AnalysisKind.DESCRIPTIVE,
        parameters={"metric": "sales"},
        rationale="描述当前指标。",
        questions=(),
        maximum_claim_class="descriptive",
        planner_invocations=1,
        model_id="fake-planner",
    )


def test_plan_store_persists_request_before_ready_and_restores(tmp_path):
    store = PlanStore(tmp_path, "session_plan")
    requested = store.request(
        client_request_id="client_plan",
        question="平均销售额？",
        dataset_context=_context(),
        provider_authorization_ref="user:explicit:plan-one",
        provider_calls_authorized=1,
    )
    ready = store.complete(requested.plan_id, _ready())

    restored = PlanStore(tmp_path, "session_plan").get(requested.plan_id)
    assert requested.status is DurablePlanStatus.REQUESTED
    assert ready.status is DurablePlanStatus.READY
    assert restored == ready
    assert restored.provider_calls == 1


def test_plan_request_is_idempotent_but_incomplete_request_cannot_be_reused(tmp_path):
    store = PlanStore(tmp_path, "session_plan_idempotent")
    first = store.request(
        client_request_id="client_same",
        question="平均销售额？",
        dataset_context=_context(),
        provider_authorization_ref="auth_one",
        provider_calls_authorized=1,
    )
    repeated = store.request(
        client_request_id="client_same",
        question="平均销售额？",
        dataset_context=_context(),
        provider_authorization_ref="auth_one",
        provider_calls_authorized=1,
    )
    assert repeated == first
    with pytest.raises(PlanConflict, match="incomplete planning request"):
        store.require_replayable(first.plan_id)
    with pytest.raises(PlanConflict, match="different planning content"):
        store.request(
            client_request_id="client_same",
            question="不同问题",
            dataset_context=_context(),
            provider_authorization_ref="auth_one",
            provider_calls_authorized=1,
        )


def test_provider_authorization_ref_cannot_fund_two_planning_requests(tmp_path):
    store = PlanStore(tmp_path, "session_plan_authorization")
    store.request(
        client_request_id="client_authorization_one",
        question="平均销售额？",
        dataset_context=_context(),
        provider_authorization_ref="auth_single_use",
        provider_calls_authorized=1,
    )

    with pytest.raises(PlanConflict, match="already used"):
        store.request(
            client_request_id="client_authorization_two",
            question="销售额范围？",
            dataset_context=_context(),
            provider_authorization_ref="auth_single_use",
            provider_calls_authorized=1,
        )


def test_planning_input_can_derive_only_one_new_plan_request(tmp_path):
    store = PlanStore(tmp_path, "session_plan_input")
    first = store.request(
        client_request_id="client_input_one",
        question="比较表现",
        dataset_context=_context(),
        provider_authorization_ref="auth_input_one",
        provider_calls_authorized=1,
        parent_plan_id="plan_needs_input",
        planning_input_id="planning_input_once",
    )

    assert first.parent_plan_id == "plan_needs_input"
    assert first.planning_input_id == "planning_input_once"
    with pytest.raises(PlanConflict, match="already derived"):
        store.request(
            client_request_id="client_input_two",
            question="比较表现",
            dataset_context=_context(),
            provider_authorization_ref="auth_input_two",
            provider_calls_authorized=1,
            parent_plan_id="plan_needs_input",
            planning_input_id="planning_input_once",
        )


def test_failed_derived_plan_allows_explicit_retry_with_new_authorization(tmp_path):
    store = PlanStore(tmp_path, "session_plan_input_retry")
    failed = store.request(
        client_request_id="client_input_failed",
        question="比较表现",
        dataset_context=_context(),
        provider_authorization_ref="auth_input_failed",
        provider_calls_authorized=1,
        parent_plan_id="plan_needs_input",
        planning_input_id="planning_input_retry",
    )
    store.fail(failed.plan_id, error_code="provider_error", message="unavailable")

    retried = store.request(
        client_request_id="client_input_retry",
        question="比较表现",
        dataset_context=_context(),
        provider_authorization_ref="auth_input_retry",
        provider_calls_authorized=1,
        parent_plan_id="plan_needs_input",
        planning_input_id="planning_input_retry",
    )

    assert retried.plan_id != failed.plan_id
    assert retried.status is DurablePlanStatus.REQUESTED
    with pytest.raises(PlanConflict, match="already derived"):
        store.request(
            client_request_id="client_input_hidden_retry",
            question="比较表现",
            dataset_context=_context(),
            provider_authorization_ref="auth_input_hidden_retry",
            provider_calls_authorized=1,
            parent_plan_id="plan_needs_input",
            planning_input_id="planning_input_retry",
        )


def test_ready_plan_consumption_is_target_bound_and_idempotent(tmp_path):
    store = PlanStore(tmp_path, "session_plan_consume")
    requested = store.request(
        client_request_id="client_consume",
        question="平均销售额？",
        dataset_context=_context(),
        provider_authorization_ref="auth_consume",
        provider_calls_authorized=1,
    )
    store.complete(requested.plan_id, _ready())

    consumed = store.consume(requested.plan_id, target_turn_id="turn_target")
    repeated = store.consume(requested.plan_id, target_turn_id="turn_target")

    assert consumed.status is DurablePlanStatus.CONSUMED
    assert consumed.target_turn_id == "turn_target"
    assert repeated == consumed
    with pytest.raises(PlanConflict, match="different target"):
        store.consume(requested.plan_id, target_turn_id="turn_other")


def test_non_ready_plan_cannot_be_consumed(tmp_path):
    store = PlanStore(tmp_path, "session_plan_non_ready")
    requested = store.request(
        client_request_id="client_non_ready",
        question="因果影响？",
        dataset_context=_context(),
        provider_authorization_ref="auth_non_ready",
        provider_calls_authorized=1,
    )
    store.fail(requested.plan_id, error_code="provider_error", message="unavailable")

    with pytest.raises(PlanConflict, match="cannot consume failed"):
        store.consume(requested.plan_id, target_turn_id="turn_target")


def test_plan_store_persists_sanitized_failure_diagnostic_without_exposing_it_publicly(
    tmp_path,
):
    store = PlanStore(tmp_path, "session_plan_diagnostic")
    requested = store.request(
        client_request_id="client_plan_diagnostic",
        question="平均销售额？",
        dataset_context=_context(),
        provider_authorization_ref="auth_diagnostic",
        provider_calls_authorized=1,
    )
    diagnostic = {
        "failure_stage": "plan_compilation",
        "finish_reason": "tool_calls",
        "tool_call_count": 1,
        "tool_names": ["submit_analysis_plan"],
        "tool_argument_types": ["dict"],
        "argument_top_level_fields": ["analysis_kind", "finding", "parameters"],
        "metadata_truncated": False,
        "recognized_status": "ready",
        "analysis_kind_present": True,
        "parameters_empty_object": False,
        "questions_present": True,
        "recognized_analysis_kind": "descriptive",
        "recognized_parameter_fields": ["horizon", "metric"],
        "missing_required_parameter_fields": [],
        "unexpected_recognized_parameter_fields": ["horizon"],
        "unknown_parameter_field_count": 1,
        "invalid_parameter_fields": [],
        "parameter_metadata_truncated": False,
    }

    failed = store.fail(
        requested.plan_id,
        error_code="PlannerContractError",
        message="planner invocation or contract validation failed",
        error_reason_code="plan_parameter_fields_unexpected",
        failure_stage="plan_compilation",
        diagnostic=diagnostic,
    )
    restored = PlanStore(tmp_path, "session_plan_diagnostic").get(requested.plan_id)

    assert restored == failed
    assert restored.error_reason_code == "plan_parameter_fields_unexpected"
    assert restored.failure_stage == "plan_compilation"
    assert restored.diagnostic == diagnostic
    public = restored.to_dict()
    assert public["error_reason_code"] == "plan_parameter_fields_unexpected"
    assert public["failure_stage"] == "plan_compilation"
    assert "diagnostic" not in public


def test_unsupported_plan_is_terminal_without_an_executable_route(tmp_path):
    store = PlanStore(tmp_path, "session_plan_unsupported")
    requested = store.request(
        client_request_id="client_unsupported",
        question="识别因果影响？",
        dataset_context=_context(),
        provider_authorization_ref="auth_unsupported",
        provider_calls_authorized=1,
    )
    result = AnalysisPlan(
        status=PlanStatus.UNSUPPORTED,
        user_question="识别因果影响？",
        analysis_kind=None,
        parameters={},
        rationale="当前方法目录不支持因果识别。",
        questions=(),
        maximum_claim_class="",
        planner_invocations=1,
        model_id="fake-planner",
    )

    terminal = store.complete(requested.plan_id, result)

    assert terminal.status is DurablePlanStatus.UNSUPPORTED
    assert terminal.analysis_kind == ""
    with pytest.raises(PlanConflict, match="cannot consume unsupported"):
        store.consume(requested.plan_id, target_turn_id="turn_target")
