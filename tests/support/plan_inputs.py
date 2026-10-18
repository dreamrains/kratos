"""Plan fixtures register a real canonical user goal before invoking the tool."""
from copy import deepcopy
import uuid
from data_agent.agent.publication.requirements import update_requirements
from data_agent.session.history import push_message, load_canonical_history


def bind_plan_fixture(state, plan):
    plan = deepcopy(plan)
    reference = "plan-fixture-" + uuid.uuid4().hex
    existing = next((r for r in state.answer_requirements if r.get("source_message_ref", "").startswith("plan-fixture-")), None)
    if existing is None:
        content = plan["goal"]
        push_message(state.session_id, {"role": "user", "content": content, "request_id": reference})
        history = load_canonical_history(state.session_id)
        rid = update_requirements(state, history, reference, [{"op": "add", "start": 0, "end": len(content), "kind": "result"}], expected_revision=state.requirement_revision)[0]
    else:
        rid = existing["id"]
    plan["requirement_revision"] = state.requirement_revision
    for step in plan["method_plan"]:
        for delivery in step["required_deliveries"]:
            if set(delivery)=={"id"}: continue
            delivery["requirement_id"] = rid
            if "scope" not in delivery:
                from data_agent.agent.publication.deliveries import OPEN_KINDS
                delivery["scope"]={} if delivery["kind"] in OPEN_KINDS else {"datasets":step["dataset_inputs"]}
                if delivery["kind"]=="measurement": delivery["scope"]["quantity"]="rows"
    return plan


def declare_goal_deliveries(loop, specs):
    """Tests declare their independent business oracle before executing tools.

    Each spec is (canonical requirement ID, typed delivery kind, business scope).
    This setup uses the actual plan validator and current host source identity;
    it does not convert an old runtime selector or infer goals from results.
    """
    from data_agent.agent.analysis_plan_contracts import validate_analysis_plan_contract
    from data_agent.agent.publication.requirements import target_datasets
    state=loop.context.analysis_state
    declarations=[{"requirement_id":rid,"kind":kind,"scope":deepcopy(scope),"label":rid+" / "+", ".join(scope.get("datasets",[]))+" / "+str(i)} for i,(rid,kind,scope) in enumerate(specs)]
    existing=[d for r in state.answer_requirements if r.get("lifecycle_status")=="active" for d in r.get("necessary_deliveries",[])]
    declarations=existing+declarations
    datasets=sorted({n for d in declarations for n in d["scope"].get("datasets",[])})
    # Pure fixture planning does not create tasks; real dispatch integration
    # tests exercise the registered plan tool and authoritative task projection.
    raw={"contract_version":"stage3c0b.v2","requirement_revision":state.requirement_revision,"goal":"Explicit test business deliveries",
        "method_plan":[{"step_id":"fixture", "goal":"Measure declared test goals","expected_output":"Declared deliveries",
            "dataset_inputs":datasets,"combination_mode":"independent" if datasets else "synthesis",
            "evidence_requirements":["receipt"],"required_deliveries":declarations}],"visualization_strategy":[]}
    result=validate_analysis_plan_contract(raw,answer_requirements=state.answer_requirements,requirement_revision=state.requirement_revision)
    assert result.ok, result
    state.answer_requirements=result.requirements
    state.analysis_plan=result.plan
    for req in state.answer_requirements:
        expected=req.setdefault("source_data_identities",{})
        for name in target_datasets(req):
            identity=loop.context.workspace._publication_data_identity(name)
            if identity and name not in expected: expected[name]=identity
    return [d for d in result.plan["method_plan"][0]["required_deliveries"] if d["id"] not in {e["id"] for e in existing}]
