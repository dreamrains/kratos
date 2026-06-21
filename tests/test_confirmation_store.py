import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from data_agent.agent.confirmation import (
    AnswerMode,
    ConfirmationEvent,
    ConfirmationOption,
    ConfirmationRecord,
    ConfirmationRequest,
)
from data_agent.agent.confirmation.store import (
    ConfirmationStore,
    StoreIntegrityError,
)


def _record(index=1):
    request = ConfirmationRequest(
        confirmation_id=f"cf_{index}",
        session_id="session_1",
        turn_id="turn_1",
        decision_key=f"decision_{index}",
        source="question_detector",
        operation="period_compare",
        question="Which metric?",
        decision_impact="The metric changes the result.",
        answer_mode=AnswerMode.SINGLE_SELECT,
        options=(ConfirmationOption("Revenue", "revenue"),),
        blocking_surfaces=("analysis_execution",),
        skippable=False,
        resolution_action="choose_metric",
    )
    return ConfirmationRecord.from_request(
        request,
        now="2026-06-21T00:00:00Z",
    )


def _event(index=1):
    return ConfirmationEvent.requested(_record(index), event_id=f"event_{index}")


def test_store_appends_event_and_rebuilds_snapshot(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")
    record = _record()
    store.append(ConfirmationEvent.requested(record, event_id="event_1"))

    assert store.load_records()[record.confirmation_id] == record
    store.snapshot_path.unlink()
    assert store.load_records()[record.confirmation_id] == record
    assert store.snapshot_path.exists()


def test_truncated_tail_preserves_valid_events_and_marks_integrity_failure(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")
    store.append(_event())
    with store.events_path.open("ab") as handle:
        handle.write(b'{"event_id":"broken"')

    result = store.load()

    assert result.integrity_status == "truncated_tail"
    assert "cf_1" in result.records


def test_mid_log_corruption_fails_closed(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")
    store.append(_event(1))
    with store.events_path.open("ab") as handle:
        handle.write(b"{broken}\n")
        handle.write((json.dumps(_event(2).to_dict()) + "\n").encode("utf-8"))

    result = store.load()

    assert result.integrity_status == "corrupt"
    assert result.records == {}
    with pytest.raises(StoreIntegrityError):
        store.load_records()


def test_duplicate_event_id_is_idempotent(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")
    event = _event()

    store.append(event)
    store.append(event)

    assert store.load().event_ids == ("event_1",)


def test_duplicate_event_id_with_different_payload_is_rejected(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")
    store.append(_event(1))
    conflicting = ConfirmationEvent.requested(_record(2), event_id="event_1")

    with pytest.raises(StoreIntegrityError, match="event_id"):
        store.append(conflicting)


def test_append_fsyncs_event_and_snapshot_and_leaves_no_temp_file(tmp_path):
    synced = []
    store = ConfirmationStore(
        tmp_path,
        "session_1",
        sync_file=lambda descriptor: synced.append(descriptor),
    )

    store.append(_event())

    assert len(synced) == 2
    assert not store.snapshot_path.with_suffix(".json.tmp").exists()


def test_concurrent_appends_do_not_lose_records(tmp_path):
    store = ConfirmationStore(tmp_path, "session_1")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: store.append(_event(index)), range(1, 21)))

    result = store.load()
    assert result.integrity_status == "ok"
    assert len(result.records) == 20
    assert len(result.event_ids) == 20


def test_store_rejects_event_for_another_session(tmp_path):
    store = ConfirmationStore(tmp_path, "another_session")

    with pytest.raises(StoreIntegrityError, match="session"):
        store.append(_event())
