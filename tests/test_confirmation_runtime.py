import pytest

from data_agent.agent.confirmation import (
    AnswerMode,
    ConfirmationContractError,
)
from data_agent.agent.loop import UserConfirmationRequired


def test_direct_question_candidate_uses_stable_identity():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    request = UserConfirmationRequired(
        question="Which metric should be used?",
        options=[
            {"label": "Revenue", "value": "revenue"},
            {"label": "Orders", "value": "orders"},
        ],
        confirmation_type="metric_scope",
        blocking_reason="Metric choice changes the calculation.",
        related_spec_id="spec_1",
    )

    first = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=3,
        request=request,
    )
    second = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=3,
        request=request,
    )

    assert first.confirmation_id == second.confirmation_id
    assert first.decision_key == second.decision_key
    assert first.operation == "direct_user_question"
    assert first.resolution_action == "record_confirmation_answer"
    assert first.blocking_surfaces == ("agent_turn",)
    assert first.options[0].label == "Revenue"
    assert first.options[0].value == "revenue"
    assert first.decision_impact == "Metric choice changes the calculation."
    assert first.resolution_params["confirmation_type"] == "metric_scope"
    assert first.resolution_params["related_spec_id"] == "spec_1"


def test_multi_select_candidate_uses_multi_select_answer_mode():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    candidate = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=UserConfirmationRequired(
            question="Pick analyses",
            options=[{"label": "Trend", "value": "trend"}],
            multi_select=True,
            confirmation_type="follow_up_choice",
        ),
    )

    assert candidate.answer_mode == AnswerMode.MULTI_SELECT


def test_free_text_candidate_uses_free_text_mode_without_options():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    candidate = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=UserConfirmationRequired(
            question="Describe the business rule.",
            options=[],
            confirmation_type="scope_confirmation",
        ),
    )

    assert candidate.answer_mode == AnswerMode.FREE_TEXT
    assert candidate.options == ()


def test_free_text_candidate_rejects_missing_question():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    with pytest.raises(ConfirmationContractError):
        build_direct_question_candidate(
            session_id="session_1",
            turn_id="turn_1",
            message_version=1,
            request=UserConfirmationRequired(question="", options=[]),
        )


def test_candidate_identity_changes_with_message_version():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    request = UserConfirmationRequired(
        question="Which metric should be used?",
        options=[{"label": "Revenue", "value": "revenue"}],
        confirmation_type="metric_scope",
    )

    first = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=request,
    )
    second = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=2,
        request=request,
    )

    assert first.confirmation_id != second.confirmation_id


def test_runtime_registers_record_confirmation_answer_action():
    from data_agent.agent.confirmation.actions import ResolutionContext
    from data_agent.agent.confirmation.runtime import build_action_registry

    registry = build_action_registry()

    receipt = registry.apply(
        "record_confirmation_answer",
        ResolutionContext("session_1", "cf_1", {"question": "Metric?"}),
        "revenue",
        "cf_1:answer_1",
    )
    repeated = registry.apply(
        "record_confirmation_answer",
        ResolutionContext("session_1", "cf_1", {"question": "Metric?"}),
        "revenue",
        "cf_1:answer_1",
    )

    assert receipt == repeated
    assert receipt.status == "succeeded"
    assert receipt.output["answer"] == "revenue"
    assert receipt.output["question"] == "Metric?"


def test_runtime_rejects_unsafe_state_update_action():
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate

    candidate = build_direct_question_candidate(
        session_id="session_1",
        turn_id="turn_1",
        message_version=1,
        request=UserConfirmationRequired(
            question="Proceed?",
            options=[{"label": "Yes", "value": "yes"}],
            state_updates='{"arbitrary": {"nested": "write"}}',
        ),
    )

    assert candidate.resolution_action == "record_confirmation_answer"
    assert candidate.resolution_params["state_updates"] == {}
