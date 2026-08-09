from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from data_agent.session.analysis_run_models import RunStatus, StepSpec, StepStatus
from data_agent.session.analysis_run_store import (
    AnalysisRunOwnershipError,
    AnalysisRunStore,
)


def _store(tmp_path, store_type=AnalysisRunStore):
    state_root = tmp_path / "run-state"
    return store_type(state_root / "analysis-runs.sqlite3", state_root=state_root)


def test_concurrent_run_creation_uses_collision_safe_ids(tmp_path):
    store = _store(tmp_path)

    def create(index: int):
        return store.create_run(
            session_id=f"session-{index}",
            idempotency_key="create",
            steps=[StepSpec("analyze")],
        ).run_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        run_ids = list(executor.map(create, range(24)))

    assert len(set(run_ids)) == 24


def test_database_enforces_one_in_progress_step_per_run(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("first"), StepSpec("second")],
    )

    with sqlite3.connect(store.path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE analysis_steps SET status = 'in_progress' WHERE step_id = ?",
            (run.steps[1].step_id,),
        )


def test_completing_current_step_atomically_activates_next(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("first"), StepSpec("second")],
    )

    advanced = store.complete_and_activate_next(
        run_id=run.run_id,
        step_id=run.steps[0].step_id,
        session_id="session-a",
        idempotency_key="complete-first",
    )

    assert [step.status for step in advanced.steps] == [
        StepStatus.COMPLETED,
        StepStatus.IN_PROGRESS,
    ]
    assert advanced.current_step == advanced.steps[1]


def test_failure_before_commit_rolls_back_both_step_changes(tmp_path):
    class CrashingStore(AnalysisRunStore):
        crash = False

        def _before_commit(self):
            if self.crash:
                raise RuntimeError("simulated crash")

    store = _store(tmp_path, CrashingStore)
    run = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("first"), StepSpec("second")],
    )
    store.crash = True

    with pytest.raises(RuntimeError, match="simulated crash"):
        store.complete_and_activate_next(
            run_id=run.run_id,
            step_id=run.steps[0].step_id,
            session_id="session-a",
            idempotency_key="complete-first",
        )

    persisted = store.get_run(run.run_id, session_id="session-a")
    assert [step.status for step in persisted.steps] == [
        StepStatus.IN_PROGRESS,
        StepStatus.PENDING,
    ]


def test_idempotency_replay_does_not_duplicate_run_or_transition(tmp_path):
    store = _store(tmp_path)
    first = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("first"), StepSpec("second")],
    )
    replay = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("ignored")],
    )
    assert replay.run_id == first.run_id

    advanced = store.complete_and_activate_next(
        run_id=first.run_id,
        step_id=first.steps[0].step_id,
        session_id="session-a",
        idempotency_key="complete-first",
    )
    replayed = store.complete_and_activate_next(
        run_id=first.run_id,
        step_id=first.steps[0].step_id,
        session_id="session-a",
        idempotency_key="complete-first",
    )

    assert replayed == advanced
    assert store.event_count(first.run_id) == 2


def test_session_cannot_read_or_mutate_another_sessions_run(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("first")],
    )

    with pytest.raises(AnalysisRunOwnershipError):
        store.get_run(run.run_id, session_id="session-b")
    with pytest.raises(AnalysisRunOwnershipError):
        store.complete_and_activate_next(
            run_id=run.run_id,
            step_id=run.steps[0].step_id,
            session_id="session-b",
            idempotency_key="foreign-complete",
        )


def test_last_step_completion_marks_run_terminal(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("only")],
    )

    completed = store.complete_and_activate_next(
        run_id=run.run_id,
        step_id=run.steps[0].step_id,
        session_id="session-a",
        idempotency_key="complete-only",
    )

    assert completed.status == RunStatus.COMPLETED
    assert completed.current_step is None


def test_database_path_must_stay_inside_assigned_state_root(tmp_path):
    with pytest.raises(ValueError, match="assigned state root"):
        AnalysisRunStore(
            tmp_path / "interactive" / "analysis.sqlite3",
            state_root=tmp_path / "test-state",
        )


def test_recovery_activates_pending_step_without_model_task_update(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("first"), StepSpec("second")],
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE analysis_steps SET status = 'completed' WHERE step_id = ?",
            (run.steps[0].step_id,),
        )

    recovered = store.recover_current_step(
        run_id=run.run_id,
        session_id="session-a",
        idempotency_key="recover-current",
    )

    assert recovered.current_step is not None
    assert recovered.current_step.subject == "second"
    replayed = store.recover_current_step(
        run_id=run.run_id,
        session_id="session-a",
        idempotency_key="recover-current",
    )
    assert replayed == recovered


def test_committed_tool_outcome_is_idempotent_and_bound_to_run_step(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        session_id="session-a",
        idempotency_key="create",
        steps=[StepSpec("first")],
    )

    first = store.record_tool_outcome(
        run_id=run.run_id,
        session_id="session-a",
        step_id=run.steps[0].step_id,
        tool_name="record_evidence_record",
        state="committed_with_warning",
        artifact_id="evidence-71aa",
        payload={"warning": "current_task_missing"},
        idempotency_key="tool-call-1",
    )
    replay = store.record_tool_outcome(
        run_id=run.run_id,
        session_id="session-a",
        step_id=run.steps[0].step_id,
        tool_name="ignored-on-replay",
        state="failed",
        idempotency_key="tool-call-1",
    )

    assert replay["outcome_id"] == first["outcome_id"]
    assert replay["state"] == "committed_with_warning"
    assert replay["artifact_id"] == "evidence-71aa"
    assert store.tool_outcome_count(run.run_id) == 1


def test_tool_outcome_rejects_step_from_another_run(tmp_path):
    store = _store(tmp_path)
    first = store.create_run(
        session_id="session-a",
        idempotency_key="create-a",
        steps=[StepSpec("first")],
    )
    store.complete_and_activate_next(
        run_id=first.run_id,
        step_id=first.steps[0].step_id,
        session_id="session-a",
        idempotency_key="complete-a",
    )
    second = store.create_run(
        session_id="session-b",
        idempotency_key="create-b",
        steps=[StepSpec("second")],
    )

    with pytest.raises(AnalysisRunOwnershipError):
        store.record_tool_outcome(
            run_id=first.run_id,
            session_id="session-a",
            step_id=second.steps[0].step_id,
            tool_name="run_python",
            state="committed",
            idempotency_key="foreign-step",
        )
