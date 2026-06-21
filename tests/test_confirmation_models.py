import pytest

from data_agent.agent.confirmation import (
    AnswerMode,
    ConfirmationContractError,
    ConfirmationEvent,
    ConfirmationOption,
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationStatus,
)


def _valid_request(**overrides):
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
            ConfirmationOption("Revenue", "revenue", "Compare collected revenue."),
            ConfirmationOption("Orders", "orders", "Compare paid order count."),
        ),
        "blocking_surfaces": ("analysis_execution", "report_generation"),
        "skippable": False,
        "resolution_action": "choose_metric",
        "resolution_params": {"analysis_spec_id": "spec_1"},
        "data_version": "data_v1",
        "spec_version": "spec_v1",
    }
    values.update(overrides)
    return ConfirmationRequest(**values)


def test_request_requires_actionable_question():
    with pytest.raises(ConfirmationContractError, match="question"):
        _valid_request(question="")


def test_single_select_requires_unique_option_values():
    duplicate = (
        ConfirmationOption("Revenue", "revenue"),
        ConfirmationOption("Revenue again", "revenue"),
    )
    with pytest.raises(ConfirmationContractError, match="unique"):
        _valid_request(options=duplicate)


def test_select_modes_require_options():
    with pytest.raises(ConfirmationContractError, match="options"):
        _valid_request(options=())


def test_free_text_mode_rejects_fixed_options():
    with pytest.raises(ConfirmationContractError, match="free_text"):
        _valid_request(answer_mode=AnswerMode.FREE_TEXT)


def test_request_requires_blocking_surfaces_and_resolution_action():
    with pytest.raises(ConfirmationContractError, match="blocking_surfaces"):
        _valid_request(blocking_surfaces=())
    with pytest.raises(ConfirmationContractError, match="resolution_action"):
        _valid_request(resolution_action="")


def test_record_and_event_json_round_trip():
    request = _valid_request()
    record = ConfirmationRecord.from_request(request, now="2026-06-21T00:00:00Z")
    event = ConfirmationEvent.requested(record, event_id="event_1")

    assert record.status == ConfirmationStatus.PENDING
    assert ConfirmationRecord.from_dict(record.to_dict()) == record
    assert ConfirmationEvent.from_dict(event.to_dict()) == event


def test_from_dict_ignores_unknown_forward_compatible_fields():
    record = ConfirmationRecord.from_request(
        _valid_request(),
        now="2026-06-21T00:00:00Z",
    )
    payload = record.to_dict()
    payload["future_field"] = {"enabled": True}

    assert ConfirmationRecord.from_dict(payload) == record


def test_invalid_status_fails_during_deserialization():
    record = ConfirmationRecord.from_request(
        _valid_request(),
        now="2026-06-21T00:00:00Z",
    )
    payload = record.to_dict()
    payload["status"] = "not_a_status"

    with pytest.raises(ValueError, match="not_a_status"):
        ConfirmationRecord.from_dict(payload)


def test_multi_select_round_trip_preserves_tuple_contracts():
    request = _valid_request(answer_mode=AnswerMode.MULTI_SELECT)
    restored = ConfirmationRequest.from_dict(request.to_dict())

    assert restored == request
    assert isinstance(restored.options, tuple)
    assert isinstance(restored.blocking_surfaces, tuple)
