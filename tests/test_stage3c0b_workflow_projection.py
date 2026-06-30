from data_agent.agent.analysis_plan_contracts import (
    STAGE3C0B_CONTRACT_VERSION,
    validate_analysis_plan_contract,
)
from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks
from data_agent.session.task_manager import TaskManager


def _validated_plan():
    result = validate_analysis_plan_contract(
        {
            "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Analyze independent game files.",
            "method_plan": [
                {
                    "step_id": "step_banner",
                    "goal": "Analyze banner metrics.",
                    "dataset_inputs": ["banner"],
                    "combination_mode": "independent",
                    "expected_output": "Banner evidence",
                    "evidence_requirements": ["click_rate"],
                },
                {
                    "step_id": "step_synthesis",
                    "goal": "Synthesize verified evidence.",
                    "dataset_inputs": [],
                    "combination_mode": "synthesis",
                    "expected_output": "Synthesis",
                    "evidence_requirements": ["summary"],
                    "required_evidence_step_ids": ["step_banner"],
                },
            ],
        },
        dataset_contracts=[{"dataset": "banner", "id": "contract_banner"}],
    )
    assert result.ok
    return result.plan


def test_projector_carries_stage3c0b_bindings(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()

    result = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
        source="analysis_plan",
    )

    assert result["created"] == 2
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    banner = next(task for task in tasks if task["step_id"] == "step_banner")
    assert banner["analysis_plan_id"] == plan["id"]
    assert banner["dataset_inputs"] == ["banner"]
    assert banner["dataset_contract_ids"] == ["contract_banner"]
    assert banner["combination_mode"] == "independent"
    assert banner["evidence_requirements"] == ["click_rate"]


def test_projector_translates_required_evidence_to_task_dependencies(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()

    project_plan_to_workflow_tasks(manager, plan, session_id="s1", project_name="p1")
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    banner = next(task for task in tasks if task["step_id"] == "step_banner")
    synthesis = next(task for task in tasks if task["step_id"] == "step_synthesis")

    assert synthesis["blockedBy"] == [banner["id"]]
    assert banner["blocks"] == [synthesis["id"]]


def test_task_manager_accepts_failed_terminal_status(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    task = manager.create("analysis", session_id="s1", step_id="step_a")

    updated = manager.update(
        task["id"],
        status="failed",
        result_summary="Dataset contract is stale",
    )

    assert updated["status"] == "failed"
    assert updated["completed_at"] == ""
