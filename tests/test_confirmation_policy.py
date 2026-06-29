from dataclasses import replace

from data_agent.agent.confirmation import (
    AnswerMode,
    ConfirmationOption,
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationStatus,
    QuestionCandidate,
    QuestionPolicy,
    RequestDisposition,
)
from data_agent.agent.confirmation_policy import (
    OBSOLETE_CONFIRMATION_TYPES,
    is_actionable_pending_confirmation,
    pending_confirmation_gate,
)
from data_agent.agent.analysis_state import AnalysisSessionState


def _candidate(**overrides):
    values = {
        "confirmation_id": "cf_metric_1",
        "session_id": "session_1",
        "turn_id": "turn_1",
        "decision_key": "session_1:choose_metric:revenue:v1",
        "source": "question_detector",
        "operation": "period_compare",
        "question": "Which metric should be compared?",
        "decision_impact": "The selected metric changes every reported value.",
        "answer_mode": AnswerMode.SINGLE_SELECT,
        "options": (
            ConfirmationOption("Revenue", "revenue"),
            ConfirmationOption("Orders", "orders"),
        ),
        "blocking_surfaces": ("analysis_execution", "report_generation"),
        "skippable": False,
        "resolution_action": "choose_metric",
        "resolution_params": {"analysis_spec_id": "spec_1"},
        "data_version": "data_v1",
        "spec_version": "spec_v1",
    }
    values.update(overrides)
    return QuestionCandidate(**values)


def _resolved_record(**overrides):
    candidate = _candidate(**overrides)
    request = ConfirmationRequest.from_candidate(candidate)
    pending = ConfirmationRecord.from_request(request, now="2026-06-21T00:00:00Z")
    return replace(
        pending,
        status=ConfirmationStatus.RESOLVED,
        version=5,
        updated_at="2026-06-21T00:05:00Z",
        response="revenue",
        response_id="answer_1",
    )


def test_policy_accepts_material_operation_decision():
    result = QuestionPolicy().evaluate(_candidate())

    assert result.disposition == RequestDisposition.CONFIRMATION
    assert result.request is not None
    assert result.request.operation == "period_compare"


def test_policy_downgrades_general_uncertainty_to_advisory():
    result = QuestionPolicy().evaluate(
        _candidate(operation="", blocking_surfaces=()),
        allow_advisory=True,
    )

    assert result.disposition == RequestDisposition.ADVISORY
    assert result.request is None


def test_policy_reuses_matching_resolved_decision():
    resolved = _resolved_record()
    result = QuestionPolicy().evaluate(_candidate(), existing=(resolved,))

    assert result.disposition == RequestDisposition.REUSED
    assert result.reused_confirmation_id == resolved.confirmation_id


def test_policy_does_not_reuse_answer_after_spec_version_changes():
    resolved = _resolved_record(spec_version="spec_v1")
    result = QuestionPolicy().evaluate(
        _candidate(spec_version="spec_v2"),
        existing=(resolved,),
    )

    assert result.disposition == RequestDisposition.CONFIRMATION


def test_policy_downgrades_declared_safe_default():
    result = QuestionPolicy().evaluate(
        _candidate(safe_default="Use the documented daily revenue metric."),
        allow_advisory=True,
    )

    assert result.disposition == RequestDisposition.ADVISORY


def test_policy_downgrades_speculative_file_relationship():
    result = QuestionPolicy().evaluate(
        _candidate(
            source="file_relationship",
            operation="",
            blocking_surfaces=(),
        ),
        allow_advisory=True,
    )

    assert result.disposition == RequestDisposition.ADVISORY


def test_policy_rejects_non_actionable_candidate_when_advisory_is_disabled():
    result = QuestionPolicy().evaluate(
        _candidate(operation="", blocking_surfaces=()),
        allow_advisory=False,
    )

    assert result.disposition == RequestDisposition.REJECTED


def test_policy_rejects_unanswerable_select_candidate():
    result = QuestionPolicy().evaluate(_candidate(options=()))

    assert result.disposition == RequestDisposition.REJECTED
    assert "options" in result.reason


def test_obsolete_confirmation_types_are_centralized_and_not_actionable():
    assert OBSOLETE_CONFIRMATION_TYPES == frozenset({
        "file_relationship_confirmation",
        "file_exclusion_confirmation",
        "join_logic_confirmation",
    })

    for confirmation_type in OBSOLETE_CONFIRMATION_TYPES:
        assert not is_actionable_pending_confirmation({
            "status": "pending",
            "confirmation_type": confirmation_type,
        })


def test_only_pending_non_obsolete_confirmation_is_actionable():
    assert is_actionable_pending_confirmation({
        "status": "pending",
        "confirmation_type": "method_confirmation",
    })
    assert not is_actionable_pending_confirmation({
        "status": "resolved",
        "confirmation_type": "method_confirmation",
    })


def test_untyped_legacy_pending_shapes_are_not_actionable():
    legacy_items = [
        {"status": "pending", "operation": "join_logic_confirmation"},
        {"status": "pending", "action": "resolve_file_relationship"},
        {"status": "pending", "resolution_action": "resolve_file_relationship"},
        {
            "status": "pending",
            "state_updates": {
                "file_relationship_confirmation": {"relationship_id": "rel_dict"},
            },
        },
        {
            "status": "pending",
            "state_updates": (
                '{"file_relationship_confirmation": '
                '{"relationship_id": "rel_json"}}'
            ),
        },
    ]

    assert all(not is_actionable_pending_confirmation(item) for item in legacy_items)


def test_pending_confirmation_gate_skips_obsolete_records_and_finds_real_gate():
    state = AnalysisSessionState(session_id="confirmation_policy")
    state.pending_confirmations = [
        {
            "status": "pending",
            "confirmation_type": "join_logic_confirmation",
            "question": "Legacy relationship question",
        },
        {
            "status": "pending",
            "confirmation_type": "metric_scope",
            "question": "Which metric?",
        },
    ]

    gate = pending_confirmation_gate(state)

    assert gate is not None
    assert gate["confirmation_type"] == "metric_scope"
    assert gate["question"] == "Which metric?"


def test_pending_confirmation_gate_is_clear_when_only_obsolete_records_remain():
    state = AnalysisSessionState(session_id="confirmation_policy")
    state.pending_confirmations = [
        {"status": "pending", "confirmation_type": confirmation_type}
        for confirmation_type in OBSOLETE_CONFIRMATION_TYPES
    ]

    assert pending_confirmation_gate(state) is None
