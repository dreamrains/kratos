from __future__ import annotations

import json

from tests.support.plan_inputs import bind_plan_fixture
from tests.test_trusted_publication_semantics import engine

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
        "requirement_revision": 0,
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
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'interpretation',
                    'label': 'Synthesize verified evidence only.: Evidence-backed answer with limitations.'
                , "scope": {}}],
                "evidence_requirements": ["answer_coverage"],
            },
        ],
        "visualization_strategy": [],
    }


def _replenishment_plan(plan_id: str = "plan_current") -> dict:
    return {
        "requirement_revision": 0,
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
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'measurement',
                    'label': 'Calculate revenue per user for the missing material claim.: EvidenceRecord for revenue_per_user.'
                , "scope": {"datasets": ['orders'], "metrics": ["revenue_per_user"], "quantity": "mean"}}],
                "evidence_requirements": ["revenue_per_user"],
            },
        ],
        "visualization_strategy": [],
    }


def _two_claim_replenishment_plan(plan_id: str = "plan_current") -> dict:
    return {
        "requirement_revision": 0,
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
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'measurement',
                    'label': 'Calculate revenue per user.: EvidenceRecord for revenue_per_user.'
                , "scope": {"datasets": ['orders'], "metrics": ["revenue_per_user"], "quantity": "mean"}}],
                "evidence_requirements": ["revenue_per_user"],
            },
            {
                "step_id": "step_retention_d7",
                "goal": "Calculate day seven retention.",
                "dataset_inputs": ["retention"],
                "combination_mode": "independent",
                "expected_output": "EvidenceRecord for day7_retention.",
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'measurement',
                    'label': 'Calculate day seven retention.: EvidenceRecord for day7_retention.'
                , "scope": {"datasets": ['retention'], "metrics": ["day7_retention"], "quantity": "mean"}}],
                "evidence_requirements": ["day7_retention"],
            },
            {
                "step_id": "step_synthesis",
                "goal": "Synthesize verified evidence only.",
                "dataset_inputs": [],
                "combination_mode": "synthesis",
                "required_evidence_step_ids": ["step_orders_revenue", "step_retention_d7"],
                "expected_output": "Evidence-backed answer with limitations.",
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'interpretation',
                    'label': 'Synthesize verified evidence only.: Evidence-backed answer with limitations.'
                , "scope": {}}],
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


def test_bounded_replenishment_loop_projects_independent_task_and_completes_from_evidence(tmp_path,monkeypatch,engine):
    import pandas as pd
    import data_agent.tools.analysis_flow as analysis_flow
    from data_agent.tools.registry import registry
    from tests.test_trusted_publication_semantics import execute
    from data_agent.session.task_manager import task_manager as manager
    loop,_=engine;state=loop.context.analysis_state
    from data_agent.tools.data_io import load_data,reload_data
    from data_agent.agent.artifact_refs import hydrate_refs
    source=tmp_path/"orders.csv";pd.DataFrame({"revenue_per_user":[12.5]*24}).to_csv(source,index=False)
    loaded=reload_data(str(source),"orders");assert not str(loaded).startswith("Error"),loaded
    contract_id=next(c["id"] for c in hydrate_refs(state.dataset_contracts) if c["dataset"]=="orders")
    plan=_two_claim_replenishment_plan();plan["method_plan"].pop(1)
    plan["method_plan"][-1]["required_evidence_step_ids"]=["step_orders_revenue"]
    result=json.loads(registry.execute("record_analysis_plan",{"plan_json":bind_plan_fixture(state,plan)}).summary)
    assert "error" not in result,result
    from data_agent.session.history import load_canonical_history
    loop.messages=load_canonical_history(loop.session_id).messages
    loop._last_jsonl_idx=len(loop.messages)
    tasks=manager.list_active_for_scope(session_id=loop.session_id)
    independent=next(t for t in tasks if t["step_id"]=="step_orders_revenue")
    # Interpretation is a final-answer obligation, not a second calculation task.
    assert all(t["step_id"]!="step_synthesis" for t in tasks)
    assert any(d["kind"]=="interpretation" for r in state.answer_requirements for d in r["necessary_deliveries"])
    annotation=json.loads(analysis_flow.record_evidence_record(json.dumps(_evidence(contract_id=contract_id))))
    assert "error" not in annotation and not annotation.get("completed_task_ids")
    assert manager.get(independent["id"])["status"]=="in_progress"
    assert ensure_dataset_allowed_for_current_task(manager,loop.session_id,dataset="retention").allowed is False
    loop._AgentLoop__context_operation("refresh")
    execute(loop,"describe_dataset",{"name":"orders"})
    from data_agent.agent.publication.runtime import snapshot_for_turn
    (tmp_path/"replenishment-projection.json").write_text(json.dumps(dict(snapshot=snapshot_for_turn(loop).as_dict(),contracts=state.dataset_contracts,receipts=state.tool_receipts,tasks=manager.list_active_for_scope(session_id=loop.session_id)),ensure_ascii=False,indent=2),encoding="utf-8")
    assert manager.get(independent["id"])["status"]=="completed"
    assert all(t["step_id"]!="step_synthesis" for t in manager.list_active_for_scope(session_id=loop.session_id))
    assert state.evidence_records[0]["evidence_requirement"]=="revenue_per_user"
    from data_agent.agent.publication.runtime import snapshot_for_turn
    host=snapshot_for_turn(loop).as_dict()
    assert host["requirements"][0]["claim_ids"] and host["requirements"][0]["gap"] is None
    assert state.accepted_answers == []  # Calculation completion does not synthesize or publish an answer.
    assert any(c["value"]==12.5 and c["id"] in host["requirements"][0]["claim_ids"] for c in host["claims"])


def test_replenishment_failure_isolates_only_the_missing_claim(tmp_path,engine):
    import pandas as pd
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from tests.test_trusted_publication_semantics import execute
    from data_agent.session.task_manager import task_manager as manager
    loop,_=engine;state=loop.context.analysis_state
    from data_agent.tools.data_io import load_data,reload_data
    from data_agent.agent.artifact_refs import hydrate_refs
    source=tmp_path/"orders.csv";pd.DataFrame({"revenue_per_user":[12.5]*24}).to_csv(source,index=False)
    loaded=reload_data(str(source),"orders");assert not str(loaded).startswith("Error"),loaded
    contract_id=next(c["id"] for c in hydrate_refs(state.dataset_contracts) if c["dataset"]=="orders")
    source=tmp_path/"retention.csv";pd.DataFrame({"day7_retention":[.2]*24}).to_csv(source,index=False)
    load_data(str(source),"retention")
    result=json.loads(registry.execute("record_analysis_plan",{"plan_json":bind_plan_fixture(state,_two_claim_replenishment_plan())}).summary)
    assert "error" not in result,result
    from data_agent.session.history import load_canonical_history
    loop.messages=load_canonical_history(loop.session_id).messages
    loop._last_jsonl_idx=len(loop.messages)
    tasks=manager.list_active_for_scope(session_id=loop.session_id)
    revenue=next(t for t in tasks if t["step_id"]=="step_orders_revenue")
    retention=next(t for t in tasks if t["step_id"]=="step_retention_d7")
    # Interpretation is a final-answer obligation, not a second calculation task.
    assert all(t["step_id"]!="step_synthesis" for t in tasks)
    assert any(d["kind"]=="interpretation" for r in state.answer_requirements for d in r["necessary_deliveries"])
    assert manager.complete_matching_tasks_from_evidence(loop.session_id,_evidence(contract_id=contract_id))==[]
    loop._AgentLoop__context_operation("refresh")
    execute(loop,"describe_dataset",{"name":"orders"})
    from data_agent.agent.publication.runtime import snapshot_for_turn
    (tmp_path/"replenishment-projection.json").write_text(json.dumps(dict(snapshot=snapshot_for_turn(loop).as_dict(),contracts=state.dataset_contracts,receipts=state.tool_receipts,tasks=manager.list_active_for_scope(session_id=loop.session_id)),ensure_ascii=False,indent=2),encoding="utf-8")
    assert manager.get(revenue["id"])["status"]=="completed"
    manager.update(retention["id"],status="failed",result_summary="Retention extract is missing the day seven column.",limitations="day7_retention remains unsupported.")
    assert manager.get(retention["id"])["status"]=="failed"
    # Mirror the normal loop refresh after the explicitly simulated task failure.
    loop._AgentLoop__context_operation("refresh")
    assert loop.context.workspace_scope.phase=="synthesis"
    assert all(t["step_id"]!="step_synthesis" for t in manager.list_active_for_scope(session_id=loop.session_id))
    host=snapshot_for_turn(loop).as_dict()
    assert host["requirements"][0]["claim_ids"] and host["requirements"][0]["gap"]["status"]=="not_computed"
    assert {c["scope"]["dataset"] for c in host["claims"]}=={"orders"}
    assert any(c["id"] in host["requirements"][0]["claim_ids"] and c["value"]==12.5 for c in host["claims"])
