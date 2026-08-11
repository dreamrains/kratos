from __future__ import annotations

import sqlite3

import pytest

from data_agent.session.analysis_run_models import StepSpec, StepStatus
from data_agent.session.analysis_run_store import AnalysisRunStore
from data_agent.session.task_manager import TaskManager


def _store(tmp_path, store_type=AnalysisRunStore):
    state_root = tmp_path / "run-state"
    return store_type(
        state_root / "analysis-runs.sqlite3",
        state_root=state_root,
    )


def _run(store: AnalysisRunStore):
    return store.create_run(
        session_id="session-a",
        idempotency_key="create-run",
        steps=[StepSpec("first"), StepSpec("second")],
    )


def _commit_projection(store: AnalysisRunStore, run, **overrides):
    arguments = {
        "run_id": run.run_id,
        "session_id": "session-a",
        "step_id": run.steps[0].step_id,
        "tool_call_id": "tool-call-1",
        "tool_name": "compare_groups",
        "tool_state": "committed",
        "capability": "analysis.compare",
        "computation": {
            "computation_ref_id": "cr_exact",
            "artifact_path": "sessions/session-a/tool_outputs/tool-call-1.json",
            "output_digest": "sha256:" + "a" * 64,
            "projection_status": "projected",
        },
        "evidence_links": [
            {"evidence_id": "evidence-1", "claim_key": "group_difference"},
        ],
        "complete_step": True,
        "idempotency_key": "commit-tool-call-1",
    }
    arguments.update(overrides)
    return store.commit_computation_projection(**arguments)


def test_existing_evidence_link_table_is_migrated_for_replay_payloads(tmp_path):
    state_root = tmp_path / "legacy-run-state"
    state_root.mkdir()
    database = state_root / "analysis-runs.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE analysis_evidence_links (
                link_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_id TEXT,
                computation_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                claim_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, evidence_id, claim_key)
            )"""
        )

    AnalysisRunStore(database, state_root=state_root)

    with sqlite3.connect(database) as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(analysis_evidence_links)"
            ).fetchall()
        }
    assert "evidence_json" in columns


def test_computation_evidence_and_next_step_commit_in_one_transaction(tmp_path):
    store = _store(tmp_path)
    run = _run(store)

    receipt = _commit_projection(store, run)

    persisted = store.get_run(run.run_id, session_id="session-a")
    assert receipt["computation_id"]
    assert receipt["tool_outcome_id"]
    assert receipt["completed_step_id"] == run.steps[0].step_id
    assert receipt["next_step_id"] == run.steps[1].step_id
    assert [step.status for step in persisted.steps] == [
        StepStatus.COMPLETED,
        StepStatus.IN_PROGRESS,
    ]
    assert store.computation_count(run.run_id) == 1
    assert store.evidence_link_count(run.run_id) == 1
    assert store.tool_outcome_count(run.run_id) == 1


def test_crash_rolls_back_computation_evidence_outcome_and_step_advance(tmp_path):
    class CrashingStore(AnalysisRunStore):
        crash = False

        def _before_commit(self):
            if self.crash:
                raise RuntimeError("simulated transaction crash")

    store = _store(tmp_path, CrashingStore)
    run = _run(store)
    store.crash = True

    with pytest.raises(RuntimeError, match="simulated transaction crash"):
        _commit_projection(store, run)

    persisted = store.get_run(run.run_id, session_id="session-a")
    assert [step.status for step in persisted.steps] == [
        StepStatus.IN_PROGRESS,
        StepStatus.PENDING,
    ]
    assert store.computation_count(run.run_id) == 0
    assert store.evidence_link_count(run.run_id) == 0
    assert store.tool_outcome_count(run.run_id) == 0


def test_computation_projection_replay_is_idempotent(tmp_path):
    store = _store(tmp_path)
    run = _run(store)

    first = _commit_projection(store, run)
    replay = _commit_projection(store, run)

    assert replay == first
    assert store.computation_count(run.run_id) == 1
    assert store.evidence_link_count(run.run_id) == 1
    assert store.tool_outcome_count(run.run_id) == 1


def test_unbound_computation_is_replayable_without_advancing_the_step(tmp_path):
    store = _store(tmp_path)
    run = _run(store)

    receipt = _commit_projection(
        store,
        run,
        computation={
            "computation_ref_id": "cr_unbound",
            "artifact_path": "sessions/session-a/tool_outputs/unbound.json",
            "output_digest": "sha256:" + "b" * 64,
            "plan_id": "",
            "step_id": "",
            "binding_error_type": "analysis_step_not_found",
            "projection_status": "pending_binding",
        },
        evidence_links=[],
        complete_step=False,
        idempotency_key="commit-unbound",
    )

    persisted = store.get_run(run.run_id, session_id="session-a")
    replayable = store.list_replayable_computations(
        run_id=run.run_id,
        session_id="session-a",
    )
    assert receipt["completed_step_id"] == ""
    assert [step.status for step in persisted.steps] == [
        StepStatus.IN_PROGRESS,
        StepStatus.PENDING,
    ]
    assert [item["computation_id"] for item in replayable] == [
        receipt["computation_id"]
    ]


def test_replayable_computation_can_bind_evidence_and_advance_once(tmp_path):
    store = _store(tmp_path)
    run = _run(store)
    committed = _commit_projection(
        store,
        run,
        computation={
            "computation_ref_id": "cr_unbound",
            "artifact_path": "sessions/session-a/tool_outputs/unbound.json",
            "output_digest": "sha256:" + "b" * 64,
            "plan_id": "",
            "step_id": "",
            "binding_error_type": "analysis_step_not_found",
            "projection_status": "pending_binding",
        },
        evidence_links=[],
        complete_step=False,
        idempotency_key="commit-unbound",
    )

    reconciled = store.reconcile_computation_projection(
        run_id=run.run_id,
        session_id="session-a",
        step_id=run.steps[0].step_id,
        computation_id=committed["computation_id"],
        evidence_links=[
            {"evidence_id": "evidence-1", "claim_key": "group_difference"},
        ],
        complete_step=True,
        idempotency_key="reconcile-unbound",
    )
    replay = store.reconcile_computation_projection(
        run_id=run.run_id,
        session_id="session-a",
        step_id=run.steps[0].step_id,
        computation_id=committed["computation_id"],
        evidence_links=[
            {"evidence_id": "evidence-1", "claim_key": "group_difference"},
        ],
        complete_step=True,
        idempotency_key="reconcile-unbound",
    )

    persisted = store.get_run(run.run_id, session_id="session-a")
    assert replay == reconciled
    assert [step.status for step in persisted.steps] == [
        StepStatus.COMPLETED,
        StepStatus.IN_PROGRESS,
    ]
    assert store.evidence_link_count(run.run_id) == 1
    assert store.list_replayable_computations(
        run_id=run.run_id,
        session_id="session-a",
    ) == []


def test_task_manager_facade_projects_transaction_back_to_legacy_tasks(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = manager.create_plan(
        session_id="session-a",
        project_name="project-a",
        goal="compare groups",
        source="analysis_plan",
    )
    first = manager.create(
        "first",
        session_id="session-a",
        project_name="project-a",
        plan_id=plan["id"],
        plan_version=plan["version"],
        task_kind="plan_task",
        analysis_plan_id="analysis-plan-a",
        step_id="external-step-1",
        required_claim_keys=["group_difference"],
        analysis_requirement_ids=["requirement-1"],
    )
    second = manager.create(
        "second",
        session_id="session-a",
        project_name="project-a",
        plan_id=plan["id"],
        plan_version=plan["version"],
        task_kind="plan_task",
        analysis_plan_id="analysis-plan-a",
        step_id="external-step-2",
    )
    manager.materialize_analysis_run(
        session_id="session-a",
        project_name="project-a",
        plan_id=plan["id"],
        tasks=[first, second],
    )
    binding = manager.get_analysis_run_tool_binding(
        session_id="session-a",
        project_name="project-a",
        external_step_id="external-step-1",
    )

    receipt = manager.commit_analysis_computation_projection(
        session_id="session-a",
        binding=binding,
        tool_call_id="tool-call-1",
        tool_name="compare_groups",
        tool_state="committed",
        capability="analysis.compare",
        computation_ref={
            "computation_ref_id": "cr_exact",
            "artifact_path": "sessions/session-a/tool-call-1.json",
            "projection_status": "projected",
        },
        evidence_records=[
            {
                "id": "evidence-1",
                "claim_key": "group_difference",
                "requirement_ids": ["requirement-1"],
                "result_summary": "group difference is 3.5",
                "confidence": "medium",
            }
        ],
        complete_step=True,
    )

    assert receipt["completed_step_id"] == binding["step_id"]
    assert manager.get(first["id"])["status"] == "completed"
    assert manager.get(first["id"])["completed_by"] == "evidence"
    assert manager.get(first["id"])["evidence_ids"] == ["evidence-1"]
    assert manager.get(second["id"])["status"] == "in_progress"
    coordinator = manager._analysis_run_coordinator(create=False)
    persisted_evidence = coordinator.store.list_evidence_records(
        run_id=receipt["run_id"],
        session_id="session-a",
    )
    assert persisted_evidence == [{
        "id": "evidence-1",
        "claim_key": "group_difference",
        "requirement_ids": ["requirement-1"],
        "result_summary": "group difference is 3.5",
        "confidence": "medium",
    }]


def test_stale_tool_binding_cannot_resurrect_superseded_plan_tasks(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    old_plan = manager.create_plan(
        session_id="session-a",
        project_name="project-a",
        goal="auto compiled plan",
        source="analysis_plan",
    )
    old_task = manager.create(
        "old step",
        session_id="session-a",
        project_name="project-a",
        plan_id=old_plan["id"],
        plan_version=old_plan["version"],
        task_kind="plan_task",
        analysis_plan_id="analysis-plan-old",
        step_id="old-step",
    )
    manager.materialize_analysis_run(
        session_id="session-a",
        project_name="project-a",
        plan_id=old_plan["id"],
        tasks=[old_task],
    )
    stale_binding = manager.get_analysis_run_tool_binding(
        session_id="session-a",
        project_name="project-a",
        external_step_id="old-step",
    )

    replacement = manager.create_plan(
        session_id="session-a",
        project_name="project-a",
        goal="explicit replacement plan",
        source="analysis_plan",
    )
    replacement_task = manager.create(
        "replacement step",
        session_id="session-a",
        project_name="project-a",
        plan_id=replacement["id"],
        plan_version=replacement["version"],
        task_kind="plan_task",
        analysis_plan_id="analysis-plan-replacement",
        step_id="replacement-step",
    )
    manager.materialize_analysis_run(
        session_id="session-a",
        project_name="project-a",
        plan_id=replacement["id"],
        tasks=[replacement_task],
    )

    receipt = manager.commit_analysis_computation_projection(
        session_id="session-a",
        binding=stale_binding,
        tool_call_id="stale-tool-call",
        tool_name="record_analysis_plan",
        tool_state="committed",
        capability="artifact.analysis_plan",
        computation_ref={
            "computation_ref_id": "cr_stale",
            "artifact_path": "sessions/session-a/stale-tool-call.json",
            "binding_error_type": "analysis_step_not_found",
            "projection_status": "pending_binding",
        },
        evidence_records=[],
        complete_step=False,
    )

    assert receipt is not None
    assert manager.get(old_task["id"])["status"] == "superseded"
    assert manager.get(old_task["id"])["plan_status"] == "superseded"
    assert manager.get(replacement_task["id"])["status"] == "in_progress"
