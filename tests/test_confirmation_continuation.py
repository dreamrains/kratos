import json

import pytest

from data_agent.agent.confirmation.continuation import (
    ContinuationIntegrityError,
    ContinuationRecord,
    ContinuationStatus,
    ContinuationStore,
)


def _continuation(**overrides):
    values = {
        "confirmation_id": "cf_metric_1",
        "session_id": "session_1",
        "turn_id": "turn_1",
        "message_version": 12,
        "completed_tool_call_ids": ("tool_1", "tool_2"),
        "blocked_operation": "period_compare",
        "request_identity": "sha256:request",
        "status": ContinuationStatus.SUSPENDED,
    }
    values.update(overrides)
    return ContinuationRecord(**values)


def test_continuation_round_trip_preserves_completed_tools(tmp_path):
    store = ContinuationStore(tmp_path, "session_1")
    continuation = _continuation()

    store.save(continuation)

    assert store.load("cf_metric_1") == continuation


def test_continuation_rejects_duplicate_completed_tool_ids():
    with pytest.raises(ValueError, match="unique"):
        _continuation(completed_tool_call_ids=("tool_1", "tool_1"))


def test_continuation_detects_payload_tampering(tmp_path):
    store = ContinuationStore(tmp_path, "session_1")
    store.save(_continuation())
    path = store.path_for("cf_metric_1")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["message_version"] = 99
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ContinuationIntegrityError, match="checksum"):
        store.load("cf_metric_1")


def test_continuation_rejects_confirmation_id_mismatch(tmp_path):
    store = ContinuationStore(tmp_path, "session_1")
    store.save(_continuation())

    with pytest.raises(ContinuationIntegrityError, match="not found"):
        store.load("cf_other")


def test_store_rejects_continuation_for_another_session(tmp_path):
    store = ContinuationStore(tmp_path, "session_2")

    with pytest.raises(ContinuationIntegrityError, match="session"):
        store.save(_continuation())


def test_continuation_supports_terminal_statuses():
    assert _continuation(status=ContinuationStatus.RESUMED).status == ContinuationStatus.RESUMED
    assert _continuation(status=ContinuationStatus.CANCELLED).status == ContinuationStatus.CANCELLED
    assert _continuation(status=ContinuationStatus.FAILED).status == ContinuationStatus.FAILED


def test_save_fsyncs_and_atomically_replaces_file(tmp_path):
    synced = []
    store = ContinuationStore(
        tmp_path,
        "session_1",
        sync_file=lambda descriptor: synced.append(descriptor),
    )

    store.save(_continuation())

    assert len(synced) == 1
    assert not store.path_for("cf_metric_1").with_suffix(".json.tmp").exists()
