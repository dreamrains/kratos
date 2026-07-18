from concurrent.futures import ThreadPoolExecutor

import pytest

from data_agent.agent.confirmation import (
    AnswerMode,
    ConfirmationEvent,
    ConfirmationOption,
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationStatus,
    QuestionCandidate,
    RequestDisposition,
)
from data_agent.agent.confirmation.actions import ResolutionActionRegistry
from data_agent.agent.confirmation.service import (
    ConfirmationAnswerError,
    ConfirmationResolutionFailed,
    ConfirmationService,
    ConfirmationVersionConflict,
    InvalidConfirmationTransition,
    SkipNotAllowed,
)
from data_agent.agent.confirmation.store import ConfirmationStore, StoreIntegrityError


def _candidate(index=1, **overrides):
    values = {
        "confirmation_id": f"cf_{index}",
        "session_id": "session_1",
        "turn_id": "turn_1",
        "decision_key": f"decision_{index}",
        "source": "question_detector",
        "operation": "period_compare",
        "question": "Which metric should be compared?",
        "decision_impact": "The metric changes every reported value.",
        "answer_mode": AnswerMode.SINGLE_SELECT,
        "options": (
            ConfirmationOption("Revenue", "revenue"),
            ConfirmationOption("Orders", "orders"),
        ),
        "blocking_surfaces": ("analysis_execution",),
        "skippable": False,
        "resolution_action": "choose_metric",
        "resolution_params": {"analysis_spec_id": "spec_1"},
        "data_version": "data_v1",
        "spec_version": "spec_v1",
    }
    values.update(overrides)
    return QuestionCandidate(**values)


def _service(tmp_path, *, fail_action=False):
    calls = []
    registry = ResolutionActionRegistry()

    def choose_metric(context, answer):
        calls.append(answer)
        if fail_action:
            raise RuntimeError("state update failed")
        return {"metric": answer}

    registry.register("choose_metric", choose_metric)
    sequence = iter(range(1, 1000))
    service = ConfirmationService(
        tmp_path,
        action_registry=registry,
        clock=lambda: "2026-06-21T00:00:00Z",
        id_factory=lambda prefix: f"{prefix}_{next(sequence)}",
    )
    return service, registry, calls


def _append_obsolete_id_collision(tmp_path):
    candidate = _candidate(
        confirmation_id="cf_1",
        operation="metric_scope",
        resolution_action="resolve_file_relationship",
        resolution_params={"confirmation_type": "metric_scope"},
    )
    record = ConfirmationRecord.from_request(
        ConfirmationRequest.from_candidate(candidate),
        now="2026-06-20T00:00:00Z",
    )
    ConfirmationStore(tmp_path, "session_1").append(
        ConfirmationEvent.requested(record, event_id="event_obsolete_collision")
    )
    return record


def test_service_allows_only_one_suspended_confirmation(tmp_path):
    service, _, _ = _service(tmp_path)
    first = service.request(_candidate(1))
    second = service.request(_candidate(2))

    active = service.checkpoint("session_1")

    assert active.confirmation_id == first.record.confirmation_id
    assert service.checkpoint("session_1") == active
    assert service.get("session_1", second.record.confirmation_id).status == ConfirmationStatus.PENDING


def test_response_uses_expected_version_and_applies_once(tmp_path):
    service, _, calls = _service(tmp_path)
    service.request(_candidate())
    active = service.checkpoint("session_1")

    resolved = service.respond(
        "session_1",
        active.confirmation_id,
        answer="revenue",
        expected_version=active.version,
        idempotency_key="answer_1",
    )
    repeated = service.respond(
        "session_1",
        active.confirmation_id,
        answer="revenue",
        expected_version=active.version,
        idempotency_key="answer_1",
    )

    assert resolved.status == ConfirmationStatus.RESOLVED
    assert repeated == resolved
    assert calls == ["revenue"]


def test_dataset_transformation_approval_records_only_compact_identity(tmp_path):
    from data_agent.agent.confirmation.runtime import build_action_registry

    service = ConfirmationService(tmp_path, action_registry=build_action_registry())
    candidate = _candidate(
        confirmation_id="transform_1",
        decision_key="dataset-transformation-1",
        operation="dataset_transformation",
        options=(ConfirmationOption("Approve", "approve"), ConfirmationOption("Reject", "reject")),
        resolution_action="approve_dataset_transformation",
        resolution_params={
            "proposal_id": "proposal_1",
            "artifact_path": "sessions/session_1/tool_outputs/proposal_1_detail.json",
            "data_version": "dataset:orders_v1:source",
            "spec_version": "transformation:one",
            "candidate_fingerprint": "sha256:candidate",
        },
        data_version="dataset:orders_v1:source",
        spec_version="transformation:one",
    )
    service.request(candidate)
    active = service.checkpoint("session_1")
    resolved = service.respond("session_1", active.confirmation_id, "reject", active.version, "reject_1")

    assert resolved.response == "reject"
    assert resolved.resolution_params["proposal_id"] == "proposal_1"
    assert resolved.resolution_params["candidate_fingerprint"] == "sha256:candidate"
    assert "DataFrame" not in repr(resolved.resolution_params)


def test_pending_confirmation_cannot_be_answered_before_suspension(tmp_path):
    service, _, _ = _service(tmp_path)
    pending = service.request(_candidate()).record

    with pytest.raises(InvalidConfirmationTransition):
        service.respond(
            "session_1",
            pending.confirmation_id,
            "revenue",
            pending.version,
            "answer_1",
        )


def test_stale_version_is_rejected_without_action(tmp_path):
    service, _, calls = _service(tmp_path)
    service.request(_candidate())
    active = service.checkpoint("session_1")

    with pytest.raises(ConfirmationVersionConflict):
        service.respond(
            "session_1",
            active.confirmation_id,
            "revenue",
            active.version - 1,
            "answer_1",
        )
    assert calls == []


def test_invalid_option_keeps_question_suspended(tmp_path):
    service, _, calls = _service(tmp_path)
    service.request(_candidate())
    active = service.checkpoint("session_1")

    with pytest.raises(ConfirmationAnswerError):
        service.respond(
            "session_1",
            active.confirmation_id,
            "unknown",
            active.version,
            "answer_1",
        )

    assert service.get("session_1", active.confirmation_id) == active
    assert calls == []


def test_record_only_single_select_accepts_free_text_answer(tmp_path):
    """ask_user_question-style confirmations accept a custom free-text answer,
    mirroring the CLI "或直接输入回答" affordance. Regression for the web error
    "answer must match one available option" when a user types instead of picking
    an option. Only record-only actions allow this; state-driving actions stay strict.
    """
    from data_agent.agent.confirmation.runtime import build_action_registry

    sequence = iter(range(1, 1000))
    service = ConfirmationService(
        tmp_path,
        action_registry=build_action_registry(),
        clock=lambda: "2026-06-21T00:00:00Z",
        id_factory=lambda prefix: f"{prefix}_{next(sequence)}",
    )
    service.request(
        _candidate(resolution_action="record_confirmation_answer", skippable=True)
    )
    active = service.checkpoint("session_1")

    resolved = service.respond(
        "session_1",
        active.confirmation_id,
        answer="我直接把链接发给你",  # free text, not a predefined option value
        expected_version=active.version,
        idempotency_key="answer_1",
    )

    assert resolved.status == ConfirmationStatus.RESOLVED
    assert resolved.response == "我直接把链接发给你"


def test_record_only_multi_select_accepts_free_text_answer(tmp_path):
    """MULTI_SELECT record-only confirmations accept custom free-text answers
    (parity with single-select and the CLI). State-driving multi-select must
    keep requiring exact option values."""
    from data_agent.agent.confirmation.runtime import build_action_registry

    sequence = iter(range(1, 1000))
    service = ConfirmationService(
        tmp_path,
        action_registry=build_action_registry(),
        clock=lambda: "2026-06-21T00:00:00Z",
        id_factory=lambda prefix: f"{prefix}_{next(sequence)}",
    )
    service.request(
        _candidate(
            answer_mode=AnswerMode.MULTI_SELECT,
            resolution_action="record_confirmation_answer",
            skippable=True,
        )
    )
    active = service.checkpoint("session_1")

    resolved = service.respond(
        "session_1",
        active.confirmation_id,
        answer=["我直接发链接", "另外补充一条说明"],  # not predefined option values
        expected_version=active.version,
        idempotency_key="answer_1",
    )

    assert resolved.status == ConfirmationStatus.RESOLVED
    assert resolved.response == ["我直接发链接", "另外补充一条说明"]


def test_state_driving_multi_select_rejects_free_text_answer(tmp_path):
    """State-driving MULTI_SELECT confirmations stay strict: an answer with a
    non-option value is rejected (no silent no-op on the state update)."""
    service, _, _ = _service(tmp_path)
    service.request(
        _candidate(
            answer_mode=AnswerMode.MULTI_SELECT,
            resolution_action="choose_metric",
            skippable=True,
        )
    )
    active = service.checkpoint("session_1")

    with pytest.raises(ConfirmationAnswerError):
        service.respond(
            "session_1",
            active.confirmation_id,
            answer=["revenue", "anything not an option"],
            expected_version=active.version,
            idempotency_key="answer_1",
        )


def test_skip_requires_explicit_permission(tmp_path):
    service, _, _ = _service(tmp_path)
    service.request(_candidate())
    active = service.checkpoint("session_1")

    with pytest.raises(SkipNotAllowed):
        service.skip("session_1", active.confirmation_id, active.version, "skip_1")


def test_skippable_confirmation_transitions_to_skipped(tmp_path):
    service, _, _ = _service(tmp_path)
    service.request(_candidate(skippable=True))
    active = service.checkpoint("session_1")

    skipped = service.skip(
        "session_1", active.confirmation_id, active.version, "skip_1"
    )

    assert skipped.status == ConfirmationStatus.SKIPPED
    assert skipped.response_id == "skip_1"


def test_cancel_active_confirmation_releases_next_queue_item(tmp_path):
    service, _, _ = _service(tmp_path)
    service.request(_candidate(1))
    service.request(_candidate(2))
    active = service.checkpoint("session_1")

    cancelled = service.cancel(
        "session_1", active.confirmation_id, active.version, "cancel_1"
    )
    next_active = service.checkpoint("session_1")

    assert cancelled.status == ConfirmationStatus.CANCELLED
    assert next_active.confirmation_id == "cf_2"


def test_pending_confirmation_can_expire(tmp_path):
    service, _, _ = _service(tmp_path)
    pending = service.request(_candidate()).record

    expired = service.expire(
        "session_1", pending.confirmation_id, pending.version, "spec replaced"
    )

    assert expired.status == ConfirmationStatus.EXPIRED
    assert expired.failure_reason == "spec replaced"


def test_action_failure_persists_failed_state(tmp_path):
    service, _, calls = _service(tmp_path, fail_action=True)
    service.request(_candidate())
    active = service.checkpoint("session_1")

    with pytest.raises(ConfirmationResolutionFailed) as exc:
        service.respond(
            "session_1",
            active.confirmation_id,
            "revenue",
            active.version,
            "answer_1",
        )

    assert exc.value.record.status == ConfirmationStatus.FAILED
    assert service.get("session_1", active.confirmation_id).status == ConfirmationStatus.FAILED
    assert calls == ["revenue"]


def test_failed_resolution_blocks_next_queue_item(tmp_path):
    service, _, _ = _service(tmp_path, fail_action=True)
    service.request(_candidate(1))
    service.request(_candidate(2))
    active = service.checkpoint("session_1")
    with pytest.raises(ConfirmationResolutionFailed):
        service.respond(
            "session_1", active.confirmation_id, "revenue", active.version, "answer_1"
        )

    blocker = service.checkpoint("session_1")

    assert blocker.status == ConfirmationStatus.FAILED
    assert blocker.confirmation_id == "cf_1"
    assert service.get("session_1", "cf_2").status == ConfirmationStatus.PENDING


def test_service_restores_active_confirmation_from_disk(tmp_path):
    service, registry, _ = _service(tmp_path)
    service.request(_candidate())
    active = service.checkpoint("session_1")
    restored_service = ConfirmationService(tmp_path, action_registry=registry)

    assert restored_service.restore("session_1") == active


def test_safe_default_is_returned_as_advisory_without_record(tmp_path):
    service, _, _ = _service(tmp_path)

    result = service.request(_candidate(safe_default="Use daily revenue."))

    assert result.disposition == RequestDisposition.ADVISORY
    assert result.record is None


def test_matching_resolved_decision_is_reused(tmp_path):
    service, _, _ = _service(tmp_path)
    service.request(_candidate(1, decision_key="shared_decision"))
    active = service.checkpoint("session_1")
    service.respond(
        "session_1", active.confirmation_id, "revenue", active.version, "answer_1"
    )

    result = service.request(_candidate(2, decision_key="shared_decision"))

    assert result.disposition == RequestDisposition.REUSED
    assert result.record is None
    assert result.reused_confirmation_id == "cf_1"


def test_matching_open_decision_is_not_queued_twice(tmp_path):
    service, _, _ = _service(tmp_path)
    first = service.request(_candidate(1, decision_key="shared_decision"))

    repeated = service.request(_candidate(2, decision_key="shared_decision"))

    assert repeated.record == first.record
    assert service.checkpoint("session_1").confirmation_id == "cf_1"


def test_obsolete_record_id_collision_gets_deterministic_replacement_and_reuses_it(tmp_path):
    service, _, _ = _service(tmp_path)
    obsolete = _append_obsolete_id_collision(tmp_path)
    candidate = _candidate(
        confirmation_id="cf_1",
        operation="metric_scope",
        resolution_action="choose_metric",
        resolution_params={"confirmation_type": "metric_scope"},
    )

    first = service.request(candidate)
    repeated = service.request(candidate)

    assert first.disposition == RequestDisposition.CONFIRMATION
    assert first.record is not None
    assert first.record.confirmation_id != obsolete.confirmation_id
    assert first.record.confirmation_id.startswith("cf_1_")
    assert repeated.record == first.record
    assert service.get("session_1", "cf_1") == obsolete
    records = service._store("session_1").load_records()
    assert set(records) == {"cf_1", first.record.confirmation_id}


def test_user_operations_reject_obsolete_record_without_writing_events(tmp_path):
    service, _, _ = _service(tmp_path)
    obsolete = _append_obsolete_id_collision(tmp_path)
    events_path = tmp_path / "session_1" / "confirmations" / "events.jsonl"
    before_events = events_path.read_bytes()

    operations = (
        lambda: service.respond(
            "session_1", obsolete.confirmation_id, "revenue", obsolete.version, "answer_old"
        ),
        lambda: service.skip(
            "session_1", obsolete.confirmation_id, obsolete.version, "skip_old"
        ),
        lambda: service.cancel(
            "session_1", obsolete.confirmation_id, obsolete.version, "cancel_old"
        ),
    )
    for operation in operations:
        with pytest.raises(InvalidConfirmationTransition, match="obsolete"):
            operation()

    assert service.get("session_1", obsolete.confirmation_id) == obsolete
    assert events_path.read_bytes() == before_events


def test_internal_expire_can_archive_obsolete_record(tmp_path):
    service, _, _ = _service(tmp_path)
    obsolete = _append_obsolete_id_collision(tmp_path)

    expired = service.expire(
        "session_1",
        obsolete.confirmation_id,
        obsolete.version,
        "retired confirmation workflow",
    )

    assert expired.status == ConfirmationStatus.EXPIRED
    assert expired.failure_reason == "retired confirmation workflow"


def test_reused_confirmation_id_rejects_a_different_contract(tmp_path):
    service, _, _ = _service(tmp_path)
    service.request(_candidate())

    with pytest.raises(ConfirmationVersionConflict, match="confirmation_id"):
        service.request(_candidate(decision_key="another_decision"))
    assert service.checkpoint("session_1").confirmation_id == "cf_1"


def test_empty_response_id_is_rejected_without_transition(tmp_path):
    service, _, calls = _service(tmp_path)
    service.request(_candidate())
    active = service.checkpoint("session_1")

    with pytest.raises(ConfirmationAnswerError, match="idempotency_key"):
        service.respond(
            "session_1", active.confirmation_id, "revenue", active.version, ""
        )

    assert service.get("session_1", active.confirmation_id) == active
    assert calls == []


def test_repeated_skip_with_same_key_returns_terminal_record(tmp_path):
    service, _, _ = _service(tmp_path)
    service.request(_candidate(skippable=True))
    active = service.checkpoint("session_1")
    skipped = service.skip(
        "session_1", active.confirmation_id, active.version, "skip_1"
    )

    repeated = service.skip(
        "session_1", active.confirmation_id, active.version, "skip_1"
    )

    assert repeated == skipped


def test_store_corruption_blocks_service_transition(tmp_path):
    service, _, _ = _service(tmp_path)
    service.request(_candidate())
    events_path = tmp_path / "session_1" / "confirmations" / "events.jsonl"
    with events_path.open("ab") as handle:
        handle.write(b"not-json\n")

    with pytest.raises(StoreIntegrityError):
        service.checkpoint("session_1")


def test_concurrent_answers_apply_only_one_resolution(tmp_path):
    service, _, calls = _service(tmp_path)
    service.request(_candidate())
    active = service.checkpoint("session_1")

    def answer(value):
        try:
            return service.respond(
                "session_1",
                active.confirmation_id,
                value,
                active.version,
                f"answer_{value}",
            )
        except (ConfirmationVersionConflict, InvalidConfirmationTransition):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(answer, ("revenue", "orders")))

    assert sum(result is not None for result in results) == 1
    assert len(calls) == 1
