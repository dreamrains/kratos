from __future__ import annotations

import sqlite3

from data_agent.agent.analysis_run_coordinator import AnalysisRunCoordinator
from data_agent.session.analysis_run_store import AnalysisRunStore


def _coordinator(tmp_path):
    root = tmp_path / "run-state"
    return AnalysisRunCoordinator(
        AnalysisRunStore(root / "analysis-runs.sqlite3", state_root=root)
    )


def _tasks(plan_id="plan-1"):
    return [
        {
            "id": 101,
            "subject": "relationship analysis",
            "plan_id": plan_id,
            "analysis_plan_id": "analysis-plan-1",
            "step_id": "step-1",
            "dataset_inputs": ["data"],
            "dataset_contract_ids": ["contract-1"],
            "combination_mode": "single",
            "required_capability": "analysis.relationship",
        },
        {
            "id": 102,
            "subject": "synthesis",
            "plan_id": plan_id,
            "analysis_plan_id": "analysis-plan-1",
            "step_id": "step-2",
            "dataset_inputs": [],
            "combination_mode": "synthesis",
        },
    ]


def test_materialized_run_owns_current_scope_and_legacy_projection(tmp_path):
    coordinator = _coordinator(tmp_path)
    run = coordinator.materialize_plan(
        session_id="session-a",
        project_name="project-a",
        plan_id="plan-1",
        tasks=_tasks(),
    )

    scope = coordinator.current_scope(
        session_id="session-a", project_name="project-a"
    )

    assert scope["run_id"] == run.run_id
    assert scope["task_id"] == 101
    assert scope["step_id"] == "step-1"
    assert scope["allowed_datasets"] == ["data"]
    assert coordinator.legacy_projection(run) == {
        101: "in_progress",
        102: "pending",
    }


def test_completed_evidence_advances_run_without_model_task_update(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.materialize_plan(
        session_id="session-a",
        project_name="project-a",
        plan_id="plan-1",
        tasks=_tasks(),
    )

    run = coordinator.advance_completed_tasks(
        session_id="session-a",
        completed_task_ids=[101],
        idempotency_key="evidence-1",
    )
    scope = coordinator.current_scope(
        session_id="session-a", project_name="project-a"
    )

    assert coordinator.legacy_projection(run) == {
        101: "completed",
        102: "in_progress",
    }
    assert scope["task_id"] == 102
    assert scope["phase"] == "synthesis"


def test_current_scope_recovers_zero_current_step_from_store(tmp_path):
    coordinator = _coordinator(tmp_path)
    run = coordinator.materialize_plan(
        session_id="session-a",
        project_name="project-a",
        plan_id="plan-1",
        tasks=_tasks(),
    )
    with sqlite3.connect(coordinator.store.path) as connection:
        connection.execute(
            "UPDATE analysis_steps SET status = 'completed' WHERE step_id = ?",
            (run.current_step.step_id,),
        )

    scope = coordinator.current_scope(
        session_id="session-a", project_name="project-a"
    )

    assert scope["task_id"] == 102
    assert scope["phase"] == "synthesis"


def test_replan_terminates_previous_run_before_materializing_new_one(tmp_path):
    coordinator = _coordinator(tmp_path)
    first = coordinator.materialize_plan(
        session_id="session-a",
        project_name="project-a",
        plan_id="plan-1",
        tasks=_tasks(),
    )
    second = coordinator.materialize_plan(
        session_id="session-a",
        project_name="project-a",
        plan_id="plan-2",
        tasks=_tasks("plan-2"),
    )

    assert second.run_id != first.run_id
    assert coordinator.store.get_run(first.run_id).status == "terminated"


def test_completed_run_has_explicit_terminal_scope_not_missing_current_error(tmp_path):
    coordinator = _coordinator(tmp_path)
    run = coordinator.materialize_plan(
        session_id="session-a",
        project_name="project-a",
        plan_id="plan-1",
        tasks=[_tasks()[0]],
    )
    coordinator.advance_completed_tasks(
        session_id="session-a",
        completed_task_ids=[101],
        idempotency_key="complete-run",
    )

    scope = coordinator.current_scope(
        session_id="session-a", project_name="project-a"
    )

    assert scope["phase"] == "terminal"
    assert scope["task_id"] == 0
    assert scope["allowed_datasets"] == []
