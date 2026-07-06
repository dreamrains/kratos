from __future__ import annotations

import json

from data_agent.agent.analysis_plan_contracts import STAGE3C0B_CONTRACT_VERSION
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.execution_scope import ensure_dataset_allowed_for_current_task
from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks
from data_agent.session.task_manager import TaskManager
from data_agent.session.workspace import Workspace


def _artifact_result(kind: str, payload: dict) -> dict:
    return {"type": kind, "saved": f"memory/{kind}.json", "payload": payload}


def _state(session_id: str, project_name: str = "p1") -> AnalysisSessionState:
    state = AnalysisSessionState(session_id=session_id, project_name=project_name)
    state.dataset_contracts = [
        {"dataset": "orders", "id": "contract_orders", "quality_status": "ready"},
        {"dataset": "retention", "id": "contract_retention", "quality_status": "ready"},
    ]
    return state


def _synthesis_plan(plan_id: str = "plan_current") -> dict:
    return {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "id": plan_id,
        "goal": "Synthesize current evidence.",
        "method_plan": [
            {
                "step_id": "step_synthesis",
                "goal": "Synthesize verified evidence only.",
                "dataset_inputs": [],
                "combination_mode": "synthesis",
                "expected_output": "Evidence-backed answer with limitations.",
                "evidence_requirements": ["answer_coverage"],
            },
        ],
        "visualization_strategy": [],
    }


def _replenishment_plan(plan_id: str = "plan_current") -> dict:
    return {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "id": plan_id,
        "goal": "Replenish missing revenue evidence.",
        "method_plan": [
            {
                "step_id": "step_orders_revenue",
                "goal": "Calculate revenue per user for the missing material claim.",
                "dataset_inputs": ["orders"],
                "combination_mode": "independent",
                "expected_output": "EvidenceRecord for revenue_per_user.",
                "evidence_requirements": ["revenue_per_user"],
            },
        ],
        "visualization_strategy": [],
    }


def _two_claim_replenishment_plan(plan_id: str = "plan_current") -> dict:
    return {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "id": plan_id,
        "goal": "Replenish two missing material claims.",
        "method_plan": [
            {
                "step_id": "step_orders_revenue",
                "goal": "Calculate revenue per user.",
                "dataset_inputs": ["orders"],
                "combination_mode": "independent",
                "expected_output": "EvidenceRecord for revenue_per_user.",
                "evidence_requirements": ["revenue_per_user"],
            },
            {
                "step_id": "step_retention_d7",
                "goal": "Calculate day seven retention.",
                "dataset_inputs": ["retention"],
                "combination_mode": "independent",
                "expected_output": "EvidenceRecord for day7_retention.",
                "evidence_requirements": ["day7_retention"],
            },
            {
                "step_id": "step_synthesis",
                "goal": "Synthesize verified evidence only.",
                "dataset_inputs": [],
                "combination_mode": "synthesis",
                "required_evidence_step_ids": ["step_orders_revenue", "step_retention_d7"],
                "expected_output": "Evidence-backed answer with limitations.",
                "evidence_requirements": ["answer_coverage"],
            },
        ],
        "visualization_strategy": [],
    }


def _evidence(
    *,
    plan_id: str = "plan_current",
    step_id: str = "step_orders_revenue",
    dataset: str = "orders",
    contract_id: str = "contract_orders",
    requirement: str = "revenue_per_user",
) -> dict:
    return {
        "plan_id": plan_id,
        "step_id": step_id,
        "claim_key": requirement,
        "claim": f"{requirement} is supported by current data.",
        "dataset": dataset,
        "dataset_contract_id": contract_id,
        "method": "bounded aggregate calculation",
        "tool_calls": [{"name": "run_python", "args": {"dataset": dataset}}],
        "result_summary": f"{requirement}=12.50",
        "sample_size": 2400,
        "limitations": ["descriptive evidence only"],
        "confidence": "high",
        "evidence_requirement": requirement,
        "measurements": [
            {
                "metric": requirement,
                "definition": "Bounded replenishment metric.",
                "value": 12.5,
                "unit": "ratio",
                "grain": "dataset",
                "population_scope": "loaded test rows",
                "time_scope": "current extract",
                "method": "aggregate calculation",
                "denominator": "rows",
                "limitations": ["descriptive evidence only"],
            }
        ],
    }


def _install_task_manager(monkeypatch, manager: TaskManager) -> None:
    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.task_tools as task_tools

    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    monkeypatch.setattr(task_tools, "task_manager", manager)


def _install_artifact_stubs(monkeypatch, state: AnalysisSessionState) -> None:
    import data_agent.tools.analysis_flow as analysis_flow

    monkeypatch.setattr(analysis_flow, "_write_analysis_artifact", _artifact_result)
    monkeypatch.setattr(state, "save", lambda: None)


def _start_synthesis(manager: TaskManager, *, session_id: str, project_name: str) -> dict:
    result = project_plan_to_workflow_tasks(
        manager,
        _synthesis_plan(),
        session_id=session_id,
        project_name=project_name,
        source="analysis_plan",
    )
    assert result["created"] == 1
    synthesis = manager.get(result["task_ids"][0])
    manager.update(synthesis["id"], status="in_progress")
    return manager.get(synthesis["id"])


def test_bounded_replenishment_loop_projects_independent_task_and_completes_from_evidence(
    tmp_path,
    monkeypatch,
):
    import data_agent.tools.analysis_flow as analysis_flow

    session_id = "replenish_happy"
    project_name = "p1"
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    state = _state(session_id, project_name)
    state.analysis_plan = _synthesis_plan()
    state.analysis_spec = _synthesis_plan()
    _install_task_manager(monkeypatch, manager)
    _install_artifact_stubs(monkeypatch, state)
    synthesis = _start_synthesis(manager, session_id=session_id, project_name=project_name)

    blocked = ensure_dataset_allowed_for_current_task(
        manager,
        session_id,
        project_name,
        dataset="orders",
    )
    assert blocked.allowed is False
    assert blocked.error_type == "synthesis_cannot_read_raw_dataset"

    ctx = AgentContext(session_id=session_id, project_name=project_name, workspace=Workspace(), analysis_state=state)
    with use_agent_context(ctx):
        plan_result = json.loads(
            analysis_flow.record_analysis_plan(json.dumps(_replenishment_plan()))
        )

    assert plan_result["workflow"]["created"] == 1
    assert manager.get_active_plan_id(session_id, project_name) == synthesis["plan_id"]
    active_tasks = manager.list_active_for_scope(session_id=session_id, project_name=project_name)
    independent = next(task for task in active_tasks if task["step_id"] == "step_orders_revenue")
    assert independent["combination_mode"] == "independent"
    assert independent["dataset_inputs"] == ["orders"]
    assert manager.get(synthesis["id"])["status"] == "in_progress"

    manager.update(synthesis["id"], status="blocked")
    manager.update(independent["id"], status="in_progress")
    allowed = ensure_dataset_allowed_for_current_task(
        manager,
        session_id,
        project_name,
        dataset="orders",
    )
    outside_scope = ensure_dataset_allowed_for_current_task(
        manager,
        session_id,
        project_name,
        dataset="retention",
    )
    assert allowed.allowed is True
    assert outside_scope.allowed is False
    assert outside_scope.error_type == "dataset_outside_current_task_scope"

    with use_agent_context(ctx):
        evidence_result = json.loads(
            analysis_flow.record_evidence_record(json.dumps(_evidence()))
        )

    assert evidence_result["completed_task_ids"] == [independent["id"]]
    assert state.evidence_records[0]["evidence_requirement"] == "revenue_per_user"
    completed = manager.get(independent["id"])
    assert completed["status"] == "completed"
    assert completed["completed_by"] == "evidence"

    manager.update(synthesis["id"], status="in_progress")
    still_blocked = ensure_dataset_allowed_for_current_task(
        manager,
        session_id,
        project_name,
        dataset="orders",
    )
    assert still_blocked.error_type == "synthesis_cannot_read_raw_dataset"
    assert state.evidence_records[0]["id"] in completed["evidence_ids"]


def test_replenishment_failure_isolates_only_the_missing_claim(tmp_path):
    session_id = "replenish_failure"
    project_name = "p1"
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    synthesis = _start_synthesis(manager, session_id=session_id, project_name=project_name)
    active_plan_id = manager.get_active_plan_id(session_id, project_name)

    projected = project_plan_to_workflow_tasks(
        manager,
        _two_claim_replenishment_plan(),
        session_id=session_id,
        project_name=project_name,
        source="synthesis_replenishment",
    )

    assert projected["created"] == 2
    assert projected["reused"] == 1
    assert manager.get_active_plan_id(session_id, project_name) == active_plan_id

    tasks = manager.list_active_for_scope(session_id=session_id, project_name=project_name)
    revenue = next(task for task in tasks if task["step_id"] == "step_orders_revenue")
    retention = next(task for task in tasks if task["step_id"] == "step_retention_d7")
    synthesis = manager.get(synthesis["id"])
    assert set(synthesis["blockedBy"]) == {revenue["id"], retention["id"]}

    completed = manager.complete_matching_tasks_from_evidence(
        session_id=session_id,
        evidence=_evidence(),
        analysis_spec_id="plan_current",
    )
    manager.update(
        retention["id"],
        status="failed",
        result_summary="Retention extract is missing the day seven column.",
        limitations="day7_retention remains unsupported.",
    )

    assert completed == [revenue["id"]]
    assert manager.get(revenue["id"])["status"] == "completed"
    assert manager.get(retention["id"])["status"] == "failed"
    assert manager.get(synthesis["id"])["status"] == "in_progress"
    assert manager.get(synthesis["id"])["blockedBy"] == [retention["id"]]
    assert manager.get(revenue["id"])["evidence_ids"]
    assert all(task["status"] != "superseded" for task in manager.list_active_for_scope(session_id=session_id, project_name=project_name))
