import pytest

from data_agent.agent.confirmation.actions import (
    InvalidResolutionAnswer,
    ResolutionActionFailed,
    ResolutionActionRegistry,
    ResolutionConflict,
    ResolutionContext,
    UnknownResolutionAction,
)


def _context(**overrides):
    values = {
        "session_id": "session_1",
        "confirmation_id": "cf_metric_1",
        "parameters": {"analysis_spec_id": "spec_1"},
    }
    values.update(overrides)
    return ResolutionContext(**values)


def test_registry_rejects_unknown_action():
    with pytest.raises(UnknownResolutionAction):
        ResolutionActionRegistry().apply(
            "missing",
            _context(),
            "yes",
            "resolution_1",
        )


def test_action_receipt_makes_repeated_apply_idempotent():
    calls = []
    registry = ResolutionActionRegistry()
    registry.register(
        "choose_metric",
        lambda context, answer: calls.append(answer) or {"metric": answer},
    )

    first = registry.apply(
        "choose_metric", _context(), "revenue", "resolution_1"
    )
    second = registry.apply(
        "choose_metric", _context(), "revenue", "resolution_1"
    )

    assert first == second
    assert first.status == "succeeded"
    assert dict(first.output) == {"metric": "revenue"}
    assert calls == ["revenue"]


def test_resolution_id_cannot_be_reused_for_different_answer():
    registry = ResolutionActionRegistry()
    registry.register("choose_metric", lambda context, answer: {"metric": answer})
    registry.apply("choose_metric", _context(), "revenue", "resolution_1")

    with pytest.raises(ResolutionConflict):
        registry.apply("choose_metric", _context(), "orders", "resolution_1")


def test_answer_validator_runs_before_handler():
    calls = []
    registry = ResolutionActionRegistry()
    registry.register(
        "choose_metric",
        lambda context, answer: calls.append(answer) or {"metric": answer},
        validator=lambda context, answer: answer in {"revenue", "orders"},
    )

    with pytest.raises(InvalidResolutionAnswer):
        registry.apply("choose_metric", _context(), "unknown", "resolution_1")
    assert calls == []


def test_failed_handler_is_receipted_and_not_reexecuted():
    calls = []

    def fail(context, answer):
        calls.append(answer)
        raise RuntimeError("database unavailable")

    registry = ResolutionActionRegistry()
    registry.register("choose_metric", fail)

    with pytest.raises(ResolutionActionFailed) as first:
        registry.apply("choose_metric", _context(), "revenue", "resolution_1")
    with pytest.raises(ResolutionActionFailed) as second:
        registry.apply("choose_metric", _context(), "revenue", "resolution_1")

    assert first.value.receipt == second.value.receipt
    assert first.value.receipt.status == "failed"
    assert "database unavailable" in first.value.receipt.error
    assert calls == ["revenue"]


def test_registry_rejects_duplicate_action_registration():
    registry = ResolutionActionRegistry()
    registry.register("choose_metric", lambda context, answer: {})

    with pytest.raises(ValueError, match="already registered"):
        registry.register("choose_metric", lambda context, answer: {})
