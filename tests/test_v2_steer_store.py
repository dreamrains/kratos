from __future__ import annotations

import pytest

from data_agent.v2.steer import SteerConflict, SteerStatus, SteerStore


def _payload(question: str = "原问题") -> dict:
    return {
        "analysis_kind": "descriptive",
        "filename": "sales.csv",
        "metric": "sales",
        "question": question,
    }


def test_latest_steer_supersedes_prior_message_and_survives_restore(tmp_path):
    store = SteerStore(tmp_path, "session_steer")
    first = store.enqueue(
        source_turn_id="turn_source",
        source_run_id="run_source",
        client_request_id="client_one",
        message="先看中位数",
        resume_payload=_payload(),
    )
    second = store.enqueue(
        source_turn_id="turn_source",
        source_run_id="run_source",
        client_request_id="client_two",
        message="改为看分布范围",
        resume_payload=_payload(),
    )

    restored = SteerStore(tmp_path, "session_steer")
    assert restored.get(first.steer_id).status is SteerStatus.SUPERSEDED
    assert restored.get(second.steer_id).status is SteerStatus.QUEUED
    assert restored.queued_for_run("run_source").steer_id == second.steer_id
    assert [item.status for item in restored.list_for_turn("turn_source")] == [
        SteerStatus.SUPERSEDED,
        SteerStatus.QUEUED,
    ]


def test_enqueue_is_idempotent_by_client_request_and_conflicts_on_new_content(tmp_path):
    store = SteerStore(tmp_path, "session_idempotent")
    first = store.enqueue(
        source_turn_id="turn_source",
        source_run_id="run_source",
        client_request_id="client_same",
        message="下一轮问题",
        resume_payload=_payload(),
    )
    repeated = store.enqueue(
        source_turn_id="turn_source",
        source_run_id="run_source",
        client_request_id="client_same",
        message="下一轮问题",
        resume_payload=_payload(),
    )

    assert repeated == first
    with pytest.raises(SteerConflict, match="client_request_id"):
        store.enqueue(
            source_turn_id="turn_source",
            source_run_id="run_source",
            client_request_id="client_same",
            message="不同问题",
            resume_payload=_payload(),
        )


def test_consume_binds_target_turn_and_is_idempotent(tmp_path):
    store = SteerStore(tmp_path, "session_consume")
    queued = store.enqueue(
        source_turn_id="turn_source",
        source_run_id="run_source",
        client_request_id="client_consume",
        message="下一轮问题",
        resume_payload=_payload(),
    )

    consumed = store.consume(queued.steer_id, target_turn_id="turn_target")
    repeated = store.consume(queued.steer_id, target_turn_id="turn_target")

    assert consumed.status is SteerStatus.CONSUMED
    assert consumed.target_turn_id == "turn_target"
    assert repeated == consumed
    with pytest.raises(SteerConflict, match="different target"):
        store.consume(queued.steer_id, target_turn_id="turn_other")


def test_projection_rejects_transition_after_terminal_state(tmp_path):
    store = SteerStore(tmp_path, "session_invalid_transition")
    queued = store.enqueue(
        source_turn_id="turn_source",
        source_run_id="run_source",
        client_request_id="client_invalid_transition",
        message="下一轮问题",
        resume_payload=_payload(),
    )
    store.consume(queued.steer_id, target_turn_id="turn_target")
    store._append(
        {
            "event_id": "steer_event_invalid_terminal_transition",
            "steer_id": queued.steer_id,
            "event_type": "superseded",
            "reason": "invalid_test_transition",
        }
    )

    with pytest.raises(SteerConflict, match="transition after consumed"):
        store.list_all()
