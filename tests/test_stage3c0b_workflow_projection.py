from data_agent.agent.analysis_plan_contracts import (
    ANALYSIS_PLAN_CONTRACT_VERSION,
    validate_analysis_plan_contract,
)
from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks
from data_agent.session.task_manager import TaskManager


def _validated_plan():
    result = validate_analysis_plan_contract(
        {
            "contract_version": ANALYSIS_PLAN_CONTRACT_VERSION,
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


def test_projector_distinguishes_same_subject_steps_by_step_id(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    result = validate_analysis_plan_contract(
        {
            "contract_version": ANALYSIS_PLAN_CONTRACT_VERSION,
            "goal": "Analyze two independent files.",
            "method_plan": [
                {
                    "step_id": "step_banner",
                    "goal": "Analyze conversion metrics.",
                    "dataset_inputs": ["banner"],
                    "combination_mode": "independent",
                    "expected_output": "Banner conversion evidence",
                    "evidence_requirements": ["conversion_rate"],
                },
                {
                    "step_id": "step_shop",
                    "goal": "Analyze conversion metrics.",
                    "dataset_inputs": ["shop"],
                    "combination_mode": "independent",
                    "expected_output": "Shop conversion evidence",
                    "evidence_requirements": ["conversion_rate"],
                },
            ],
        },
        dataset_contracts=[
            {"dataset": "banner", "id": "contract_banner"},
            {"dataset": "shop", "id": "contract_shop"},
        ],
    )
    assert result.ok

    projected = project_plan_to_workflow_tasks(
        manager,
        result.plan,
        session_id="s1",
        project_name="p1",
    )

    assert projected["created"] == 2
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    banner = next(task for task in tasks if task["step_id"] == "step_banner")
    shop = next(task for task in tasks if task["step_id"] == "step_shop")
    assert banner["id"] != shop["id"]
    assert banner["dataset_inputs"] == ["banner"]
    assert banner["dataset_contract_ids"] == ["contract_banner"]
    assert shop["dataset_inputs"] == ["shop"]
    assert shop["dataset_contract_ids"] == ["contract_shop"]


def test_projector_translates_required_evidence_to_task_dependencies(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()

    project_plan_to_workflow_tasks(manager, plan, session_id="s1", project_name="p1")
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    banner = next(task for task in tasks if task["step_id"] == "step_banner")
    synthesis = next(task for task in tasks if task["step_id"] == "step_synthesis")

    assert synthesis["blockedBy"] == [banner["id"]]
    assert banner["blocks"] == [synthesis["id"]]


def test_projector_reuses_existing_tasks_for_same_stage3c0b_plan(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()

    first = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )
    assert first["created"] == 2

    second = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )

    assert second["created"] == 0
    assert second["reused"] == 2
    assert second["task_ids"] == first["task_ids"]
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    assert len(tasks) == 2
    assert len([task for task in tasks if task["task_kind"] == "plan_task"]) == 2


def test_projector_rejects_malformed_stage3c0b_without_superseding_active_plan(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()
    first = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )
    active_plan_id = manager.get_active_plan_id("s1", "p1")

    malformed = project_plan_to_workflow_tasks(
        manager,
        {
            "contract_version": ANALYSIS_PLAN_CONTRACT_VERSION,
            "goal": "Malformed plan",
        },
        session_id="s1",
        project_name="p1",
    )

    assert malformed["created"] == 0
    assert malformed["error"] == "missing_method_plan"
    assert manager.get_active_plan_id("s1", "p1") == active_plan_id
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    assert [task["id"] for task in tasks] == first["task_ids"]


def test_projector_rejects_non_object_steps_without_superseding_active_plan(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()
    first = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )
    active_plan_id = manager.get_active_plan_id("s1", "p1")

    malformed = project_plan_to_workflow_tasks(
        manager,
        {
                "contract_version": ANALYSIS_PLAN_CONTRACT_VERSION,
            "goal": "Malformed plan",
            "method_plan": ["not an object"],
        },
        session_id="s1",
        project_name="p1",
    )

    assert malformed == {
        "created": 0,
        "reused": 0,
        "task_ids": [],
            "error": "invalid_step",
    }
    assert manager.get_active_plan_id("s1", "p1") == active_plan_id
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    assert [task["id"] for task in tasks] == first["task_ids"]


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
