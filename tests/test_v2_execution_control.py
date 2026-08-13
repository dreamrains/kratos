from __future__ import annotations

from dataclasses import asdict
import threading

import pytest

from data_agent.v2.execution_control import ActiveRunRegistry, StopRequestConflict
from data_agent.v2.models import (
    AnswerBlockDraft,
    AnswerBlockType,
    ClaimClass,
    Commitment,
    CommitmentPriority,
    EventType,
    FindingKind,
)
from data_agent.v2.slice1 import RuntimeEvent
from data_agent.v2.store import TurnPublicationBlocked, V2FactStore


def _commitment() -> Commitment:
    return Commitment(
        commitment_id="commitment_stop",
        priority=CommitmentPriority.CORE,
        question="平均销售额是多少？",
        dataset_version_ids=("dv_sales",),
        accepted_result_kinds=(FindingKind.ESTIMATE,),
        accepted_method_capabilities=("analysis.describe",),
    )


def _block() -> AnswerBlockDraft:
    return AnswerBlockDraft(
        block_id="block_final",
        block_type=AnswerBlockType.EXECUTIVE_ANSWER,
        headline="结论",
        narrative="不应在停止后发布。",
        support_refs=("finding_sales",),
        claim_class=ClaimClass.DESCRIPTIVE,
    )


@pytest.mark.parametrize("status", ["draft", "failed", "finalized"])
def test_stop_request_wins_atomic_gate_and_blocks_non_interrupt_status(
    tmp_path, status
):
    store = V2FactStore(tmp_path, "session_stop")

    assert store.request_turn_interrupt("turn_stop", "run_stop") == "stop_requested"
    with pytest.raises(TurnPublicationBlocked):
        store.write_turn_blocks("turn_stop", [_block()], status=status)


def test_completed_turn_wins_atomic_gate_and_rejects_late_stop(tmp_path):
    store = V2FactStore(tmp_path, "session_complete")
    store.write_turn_blocks("turn_complete", [_block()], status="finalized")

    assert store.request_turn_interrupt("turn_complete", "run_complete") == "completed"
    assert store.read_turn_blocks("turn_complete")["status"] == "finalized"


def test_active_stop_is_durable_and_closes_generator_at_safe_boundary(tmp_path):
    store = V2FactStore(tmp_path, "session_active")
    commitment = _commitment()
    store.write_commitments([commitment])
    advanced: list[str] = []

    def source():
        yield RuntimeEvent(
            "turn_started",
            {"session_id": "session_active", "turn_id": "turn_active", "run_id": "run_active"},
        )
        yield RuntimeEvent("commitment_snapshot", {"commitments": [asdict(commitment)]})
        yield RuntimeEvent("tool_started", {"name": "describe_numeric"})
        advanced.append("runtime_advanced_after_stop")
        yield RuntimeEvent("turn_completed", {"status": "completed"})

    registry = ActiveRunRegistry()
    active = registry.register(
        store=store,
        session_id="session_active",
        turn_id="turn_active",
        request_context={
            "analysis_kind": "descriptive",
            "filename": "sales.csv",
            "metric": "sales",
            "question": "平均销售额是多少？",
        },
    )
    controlled = active.stream(source())

    assert next(controlled).event == "turn_started"
    assert next(controlled).event == "commitment_snapshot"
    assert next(controlled).event == "tool_started"
    receipt = registry.request_stop("session_active", "turn_active")
    remaining = list(controlled)

    assert receipt.status == "interrupted"
    assert advanced == []
    assert [item.event for item in remaining] == ["outcome_snapshot", "turn_interrupted"]
    restored = store.read_turn_blocks("turn_active")
    assert restored["status"] == "interrupted"
    interruptions = [
        item for item in store.read_events() if item.event_type is EventType.USER_INTERRUPTED
    ]
    assert len(interruptions) == 1
    assert interruptions[0].run_id == "run_active"
    assert interruptions[0].commitment_id == "commitment_stop"


def test_registry_rejects_concurrent_run_in_same_session(tmp_path):
    registry = ActiveRunRegistry()
    store = V2FactStore(tmp_path, "session_single")
    registry.register(
        store=store,
        session_id="session_single",
        turn_id="turn_1",
        request_context={},
    )

    with pytest.raises(StopRequestConflict, match="already has an active run"):
        registry.register(
            store=store,
            session_id="session_single",
            turn_id="turn_2",
            request_context={},
        )


def test_runtime_status_race_waits_for_durable_interrupt_instead_of_failing(
    tmp_path, monkeypatch
):
    store = V2FactStore(tmp_path, "session_race")
    commitment = _commitment()
    store.write_commitments([commitment])

    def source():
        yield RuntimeEvent(
            "turn_started",
            {"session_id": "session_race", "turn_id": "turn_race", "run_id": "run_race"},
        )
        yield RuntimeEvent("commitment_snapshot", {"commitments": [asdict(commitment)]})
        yield RuntimeEvent("tool_started", {"name": "date_transform"})
        store.write_turn_blocks("turn_race", [], status="draft")
        yield RuntimeEvent("user_input_required", {})

    registry = ActiveRunRegistry()
    active = registry.register(
        store=store,
        session_id="session_race",
        turn_id="turn_race",
        request_context={"analysis_kind": "date_transformation"},
    )
    controlled = active.stream(source())
    assert [next(controlled).event for _ in range(3)] == [
        "turn_started",
        "commitment_snapshot",
        "tool_started",
    ]

    append_entered = threading.Event()
    release_append = threading.Event()
    original_append = store.append_event

    def delayed_append(event):
        if event.event_type is EventType.USER_INTERRUPTED:
            append_entered.set()
            assert release_append.wait(timeout=5)
        return original_append(event)

    monkeypatch.setattr(store, "append_event", delayed_append)
    stop_result: list[object] = []
    terminal_result: list[object] = []
    stop_thread = threading.Thread(
        target=lambda: stop_result.append(
            registry.request_stop("session_race", "turn_race")
        )
    )
    stop_thread.start()
    assert append_entered.wait(timeout=5)
    terminal_thread = threading.Thread(
        target=lambda: terminal_result.append(next(controlled))
    )
    terminal_thread.start()
    release_append.set()
    stop_thread.join(timeout=5)
    terminal_thread.join(timeout=5)

    assert stop_result[0].status == "interrupted"
    assert terminal_result[0].event == "outcome_snapshot"
    assert next(controlled).event == "turn_interrupted"
    assert store.read_turn_blocks("turn_race")["status"] == "interrupted"
