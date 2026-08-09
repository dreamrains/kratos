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
                    "evidence_requirements": ["metric", "sample_size"],
                    "required_claim_keys": ["impressions", "click_rate"],
                },
                {
                    "step_id": "step_synthesis",
                    "goal": "Synthesize verified evidence.",
                    "dataset_inputs": [],
                    "combination_mode": "synthesis",
                    "expected_output": "Synthesis",
                    "evidence_requirements": ["limitations"],
                    "required_claim_keys": ["comparative_summary"],
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
    assert banner["evidence_requirements"] == ["metric", "sample_size"]
    assert banner["required_claim_keys"] == ["impressions", "click_rate"]
    assert banner["analysis_requirement_ids"] == [
        "req_step_banner_metric",
        "req_step_banner_sample_size",
    ]


def test_projector_activates_exactly_one_first_ready_canonical_task(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()

    projected = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )

    tasks = [manager.get(task_id) for task_id in projected["task_ids"]]
    banner = next(task for task in tasks if task["step_id"] == "step_banner")
    synthesis = next(task for task in tasks if task["step_id"] == "step_synthesis")
    assert banner["status"] == "in_progress"
    assert synthesis["status"] == "pending"
    assert [task["id"] for task in tasks if task["status"] == "in_progress"] == [
        banner["id"]
    ]


def test_projector_preserves_state_owned_compiler_snapshot(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()
    plan["analysis_requirements"]["step_banner"][0]["trigger"] = (
        "profile-derived compiler snapshot"
    )

    result = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )

    assert "error" not in result
    assert result["created"] == 2


def test_projected_task_requires_each_exact_claim_key_before_completion(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()
    projected = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )
    banner = manager.get(projected["task_ids"][0])
    base_evidence = {
        "plan_id": plan["id"],
        "step_id": "step_banner",
        "dataset_contract_id": "contract_banner",
        "requirement_ids": list(banner["analysis_requirement_ids"]),
        "result_summary": "business output calculated",
    }

    first = manager.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence={**base_evidence, "id": "ev_impressions", "claim_key": "impressions"},
    )
    masquerading = manager.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence={
            **base_evidence,
            "id": "ev_wrong_claim",
            "claim_key": "impressions",
            "evidence_requirement": "click_rate",
        },
    )

    assert first == []
    assert masquerading == []
    assert manager.get(banner["id"])["status"] == "in_progress"
    assert manager.get(banner["id"])["satisfied_claim_keys"] == ["impressions"]

    completed = manager.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence={**base_evidence, "id": "ev_click_rate", "claim_key": "click_rate"},
    )

    assert completed == [banner["id"]]
    assert manager.get(banner["id"])["satisfied_claim_keys"] == ["impressions", "click_rate"]
    synthesis = next(
        task
        for task in manager.list_active_for_scope(session_id="s1", project_name="p1")
        if task["step_id"] == "step_synthesis"
    )
    assert manager.get(synthesis["id"])["status"] == "in_progress"


def test_projected_task_requires_canonical_requirement_ids_when_present(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = _validated_plan()
    projected = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )
    banner = manager.get(projected["task_ids"][0])
    evidence = {
        "plan_id": plan["id"],
        "step_id": "step_banner",
        "dataset_contract_id": "contract_banner",
        "claim_key": "impressions",
        "result_summary": "impressions calculated",
    }

    missing = manager.complete_matching_tasks_from_evidence(session_id="s1", evidence=evidence)
    wrong = manager.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence={**evidence, "requirement_ids": ["req_step_banner_limitations"]},
    )

    assert missing == []
    assert wrong == []
    assert manager.get(banner["id"])["evidence_ids"] == []


def test_projector_uses_requirement_ids_compiled_during_its_validation(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    raw_plan = {
        "contract_version": ANALYSIS_PLAN_CONTRACT_VERSION,
        "id": "plan_raw_projection",
        "goal": "Analyze banner metrics.",
        "method_plan": [{
            "step_id": "step_banner",
            "goal": "Analyze banner metrics.",
            "dataset_inputs": ["banner"],
            "dataset_contract_ids": ["contract_banner"],
            "combination_mode": "independent",
            "expected_output": "Banner evidence",
            "evidence_requirements": ["metric"],
            "required_claim_keys": ["click_rate"],
        }],
    }

    projected = project_plan_to_workflow_tasks(
        manager,
        raw_plan,
        session_id="s1",
        project_name="p1",
    )

    task = manager.get(projected["task_ids"][0])
    assert task["dataset_contract_ids"] == ["contract_banner"]
    assert task["analysis_requirement_ids"] == ["req_step_banner_metric"]


def test_projector_uses_exact_validated_unsafe_step_identity_for_requirement_enforcement(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    raw_plan = {
        "contract_version": ANALYSIS_PLAN_CONTRACT_VERSION,
        "id": "plan_exact_spaced_step",
        "goal": "Analyze an exact custom step identity.",
        "method_plan": [{
            "step_id": "Revenue  Trend",
            "goal": "Analyze revenue per user.",
            "dataset_inputs": ["orders"],
            "dataset_contract_ids": ["contract_orders"],
            "combination_mode": "independent",
            "expected_output": "Revenue per user evidence",
            "evidence_requirements": ["metric"],
            "required_claim_keys": ["  revenue_per_user  "],
        }],
    }

    projected = project_plan_to_workflow_tasks(
        manager,
        raw_plan,
        session_id="s1",
        project_name="p1",
    )

    task = manager.get(projected["task_ids"][0])
    assert task["step_id"] == "Revenue  Trend"
    assert task["dataset_contract_ids"] == ["contract_orders"]
    assert task["required_claim_keys"] == ["revenue_per_user"]
    assert len(task["analysis_requirement_ids"]) == 1
    assert task["analysis_requirement_ids"][0].startswith("req_unsafe_")
    assert task["analysis_requirement_ids"][0].endswith("_metric")

    completed = manager.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence={
            "id": "ev_missing_requirement_id",
            "plan_id": raw_plan["id"],
            "step_id": "Revenue  Trend",
            "dataset_contract_id": "contract_orders",
            "claim_key": "revenue_per_user",
            "result_summary": "revenue_per_user=12.5",
        },
    )

    assert completed == []
    assert manager.get(task["id"])["evidence_ids"] == []


def test_projector_preserves_exact_spaced_step_identity_in_dependencies(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    plan = validate_analysis_plan_contract(
        {
            "contract_version": ANALYSIS_PLAN_CONTRACT_VERSION,
            "id": "plan_spaced_dependency",
            "goal": "Analyze then synthesize exact custom steps.",
            "method_plan": [
                {
                    "step_id": "Revenue  Trend",
                    "goal": "Analyze revenue.",
                    "dataset_inputs": ["orders"],
                    "combination_mode": "independent",
                    "expected_output": "Revenue evidence",
                    "evidence_requirements": ["metric"],
                    "required_claim_keys": ["revenue_per_user"],
                },
                {
                    "step_id": "step_synthesis",
                    "goal": "Synthesize revenue evidence.",
                    "dataset_inputs": [],
                    "combination_mode": "synthesis",
                    "expected_output": "Synthesis",
                    "evidence_requirements": ["limitations"],
                    "required_claim_keys": ["summary"],
                    "required_evidence_step_ids": ["Revenue  Trend"],
                },
            ],
        },
        dataset_contracts=[{"dataset": "orders", "id": "contract_orders"}],
    ).plan

    projected = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )

    tasks = [manager.get(task_id) for task_id in projected["task_ids"]]
    revenue = next(task for task in tasks if task["step_id"] == "Revenue  Trend")
    synthesis = next(task for task in tasks if task["step_id"] == "step_synthesis")
    assert synthesis["required_evidence_step_ids"] == ["Revenue  Trend"]
    assert synthesis["blockedBy"] == [revenue["id"]]


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
