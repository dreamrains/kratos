import json
from copy import deepcopy
from tests.test_trusted_publication_semantics import engine
from data_agent.agent.analysis_plan_contracts import (
    STAGE3C0B_CONTRACT_VERSION,
    validate_analysis_plan_contract,
)
from data_agent.agent.workflow_projection import project_plan_to_workflow_tasks
from data_agent.session.task_manager import TaskManager


def _validated_plan():
    result = validate_analysis_plan_contract(
        {
            "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Analyze independent game files.",
            "method_plan": [
                {
                    "step_id": "step_banner",
                    "goal": "Analyze banner metrics.",
                    "dataset_inputs": ["banner"],
                    "combination_mode": "independent",
                    "expected_output": "Banner evidence",
                    "required_deliveries": [{
                        'requirement_id': 'rq_plan_fixture',
                        'kind': 'measurement',
                        'label': 'Analyze banner metrics.: Banner evidence'
                    , "scope": {"datasets": ['banner'], "quantity": "rows"}}],
                "evidence_requirements": ["click_rate"],
                },
                {
                    "step_id": "step_synthesis",
                    "goal": "Synthesize verified evidence.",
                    "dataset_inputs": [],
                    "combination_mode": "synthesis",
                    "expected_output": "Synthesis",
                    "required_deliveries": [{
                        'requirement_id': 'rq_plan_fixture',
                        'kind': 'interpretation',
                        'label': 'Synthesize verified evidence.: Synthesis'
                    , "scope": {}}],
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

    assert result["created"] == 1
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    banner = next(task for task in tasks if task["step_id"] == "step_banner")
    assert banner["analysis_plan_id"] == plan["id"]
    assert banner["dataset_inputs"] == ["banner"]
    assert banner["dataset_contract_ids"] == ["contract_banner"]
    assert banner["combination_mode"] == "independent"
    assert banner["evidence_requirements"] == ["click_rate"]
    assert len(tasks) == 1
    assert plan["method_plan"][1]["required_deliveries"][0]["kind"] == "interpretation"
    assert result["started_task_id"] == banner["id"]
    assert result["current_step"] == {
        "step_id": "step_banner", "dataset_inputs": ["banner"],
        "combination_mode": "independent",
    }
    assert banner["status"] == "in_progress"



def test_projector_starts_exactly_one_of_multiple_ready_steps(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    result = validate_analysis_plan_contract(
        {
            "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Analyze two independent files.",
            "method_plan": [
                {
                    "step_id": "step_a",
                    "goal": "Analyze A.",
                    "dataset_inputs": ["a"],
                    "combination_mode": "independent",
                    "expected_output": "A evidence",
                    "required_deliveries": [{
                        'requirement_id': 'rq_plan_fixture',
                        'kind': 'measurement',
                        'label': 'Analyze A.: A evidence'
                    , "scope": {"datasets": ['a'], "quantity": "rows"}}],
                "evidence_requirements": ["a_metric"],
                },
                {
                    "step_id": "step_b",
                    "goal": "Analyze B.",
                    "dataset_inputs": ["b"],
                    "combination_mode": "independent",
                    "expected_output": "B evidence",
                    "required_deliveries": [{
                        'requirement_id': 'rq_plan_fixture',
                        'kind': 'measurement',
                        'label': 'Analyze B.: B evidence'
                    , "scope": {"datasets": ['b'], "quantity": "rows"}}],
                "evidence_requirements": ["b_metric"],
                },
            ],
        },
        dataset_contracts=[
            {"dataset": "a", "id": "contract_a"},
            {"dataset": "b", "id": "contract_b"},
        ],
    )
    assert result.ok

    projected = project_plan_to_workflow_tasks(
        manager, result.plan, session_id="s1", project_name="p1",
    )
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")

    assert projected["started_task_id"] == tasks[0]["id"]
    assert len([task for task in tasks if task["status"] == "in_progress"]) == 1


def test_evidence_completion_atomically_advances_to_next_ready_step(engine):
    from tests.test_trusted_publication_runtime import request
    from tests.test_trusted_publication_semantics import execute
    from data_agent.tools.data_io import _record_trust_workflow
    from data_agent.tools.registry import registry
    from data_agent.session.task_manager import task_manager as manager
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;state=loop.context.analysis_state
    request(loop,"计算记录数和均值",[{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}},{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}}])
    _record_trust_workflow(session_id=loop.session_id,state=state,dataset="orders",df=loop.context.workspace.get("orders"),applied=[],needs_confirm=[],quality={},interpretation_data={},detail_path="")
    plan=deepcopy(state.analysis_plan);first=plan["method_plan"][0];deliveries=first["required_deliveries"]
    first["required_deliveries"]=[{"id":deliveries[0]["id"]}]
    second=deepcopy(first);second["step_id"]="second";second["required_deliveries"]=[{"id":deliveries[1]["id"]}];second["required_evidence_step_ids"]=["fixture"]
    plan["method_plan"].append(second);plan["requirement_revision"]=state.requirement_revision
    output=json.loads(registry.execute("record_analysis_plan",{"plan_json":plan}).summary)
    assert "error" not in output,output
    tasks=manager.list_active_for_scope(session_id=loop.session_id);a,b=sorted(tasks,key=lambda t:t["id"])
    assert manager.complete_matching_tasks_from_evidence(loop.session_id,{"claim":"completed","confidence":"high"})==[]
    assert manager.update(a["id"],status="completed") is None and manager.update(b["id"],status="in_progress") is None
    execute(loop,"describe_dataset",{"name":"orders"})
    assert manager.get(a["id"])["status"]=="completed" and manager.get(b["id"])["status"]=="in_progress"
    assert snapshot_for_turn(loop).as_dict()["requirements"][0]["gap"]
    execute(loop,"describe_dataset",{"name":"orders"})
    assert manager.get(b["id"])["status"]=="completed"
    assert snapshot_for_turn(loop).as_dict()["requirements"][0]["gap"] is None


def test_projector_distinguishes_same_subject_steps_by_step_id(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path)
    result = validate_analysis_plan_contract(
        {
            "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Analyze two independent files.",
            "method_plan": [
                {
                    "step_id": "step_banner",
                    "goal": "Analyze conversion metrics.",
                    "dataset_inputs": ["banner"],
                    "combination_mode": "independent",
                    "expected_output": "Banner conversion evidence",
                    "required_deliveries": [{
                        'requirement_id': 'rq_plan_fixture',
                        'kind': 'measurement',
                        'label': 'Analyze conversion metrics.: Banner conversion evidence'
                    , "scope": {"datasets": ['banner'], "quantity": "rows"}}],
                "evidence_requirements": ["conversion_rate"],
                },
                {
                    "step_id": "step_shop",
                    "goal": "Analyze conversion metrics.",
                    "dataset_inputs": ["shop"],
                    "combination_mode": "independent",
                    "expected_output": "Shop conversion evidence",
                    "required_deliveries": [{
                        'requirement_id': 'rq_plan_fixture',
                        'kind': 'measurement',
                        'label': 'Analyze conversion metrics.: Shop conversion evidence'
                    , "scope": {"datasets": ['shop'], "quantity": "rows"}}],
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
    delivery = plan["method_plan"][1]["required_deliveries"][0]
    delivery.update(kind="hypothesis", scope={"datasets":["banner"]})
    delivery.pop("id")
    checked=validate_analysis_plan_contract(plan,dataset_contracts=[{"dataset":"banner","id":"contract_banner"}])
    assert checked.ok, checked
    plan=checked.plan

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
    assert first["created"] == 1

    second = project_plan_to_workflow_tasks(
        manager,
        plan,
        session_id="s1",
        project_name="p1",
    )

    assert second["created"] == 0
    assert second["reused"] == 1
    assert second["task_ids"] == first["task_ids"]
    tasks = manager.list_active_for_scope(session_id="s1", project_name="p1")
    assert len(tasks) == 1
    assert len([task for task in tasks if task["task_kind"] == "plan_task"]) == 1


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
            "contract_version": STAGE3C0B_CONTRACT_VERSION,
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
            "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
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
        "error": "invalid_method_plan_step",
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
