import json

import pytest

from data_agent.agent.analysis_plan_contracts import (
    STAGE3C0B_CONTRACT_VERSION,
    validate_analysis_plan_contract,
)
from data_agent.tools.analysis_flow import record_analysis_plan


def _contract(dataset: str, contract_id: str) -> dict:
    return {"dataset": dataset, "id": contract_id, "quality_status": "ready"}


def test_valid_stage3c0b_plan_is_reviewed_and_executable():
    plan = {
        "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Compare the independent performance evidence for uploaded game files.",
        "method_plan": [
            {
                "step_id": "step_banner",
                "goal": "Analyze banner exposure and click performance.",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "Banner evidence",
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'measurement',
                    'label': 'Analyze banner exposure and click performance.: Banner evidence'
                , "scope": {"datasets": ['banner'], "quantity": "rows"}}],
                "evidence_requirements": ["impressions", "click_rate"],
            },
            {
                "step_id": "step_synthesis",
                "goal": "Synthesize verified evidence across game files.",
                "dataset_inputs": [],
                "combination_mode": "synthesis",
                "expected_output": "Cross-file synthesis",
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'interpretation',
                    'label': 'Synthesize verified evidence across game files.: Cross-file synthesis'
                , "scope": {}}],
                "evidence_requirements": ["comparative_summary"],
                "required_evidence_step_ids": ["step_banner"],
            },
        ],
    }

    result = validate_analysis_plan_contract(
        plan,
        dataset_contracts=[_contract("banner", "contract_banner")],
    )

    assert result.ok is True
    assert result.plan["review_status"] == "executable"
    assert result.plan["method_plan"][0]["plan_id"] == result.plan["id"]
    assert result.plan["method_plan"][0]["dataset_contract_ids"] == ["contract_banner"]
    assert result.plan["method_plan"][0]["combination_mode"] == "independent"


def test_rejects_legacy_or_missing_contract_version_for_execution():
    result = validate_analysis_plan_contract(
        {"goal": "legacy", "method_plan": [{"step_id": "s1"}]},
        dataset_contracts=[],
    )

    assert result.ok is False
    assert result.error_type == "legacy_plan_display_only"
    assert "contract_version" in result.message


def test_rejects_join_hidden_as_executable_stage3c0b_mode():
    plan = {
        "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Join orders and users.",
        "method_plan": [
            {
                "step_id": "step_join",
                "goal": "Join the datasets.",
                "dataset_inputs": ["orders", "users"],
                "combination_mode": "join",
                "expected_output": "Joined table",
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'measurement',
                    'label': 'Join the datasets.: Joined table'
                , "scope": {"datasets": ['orders', 'users'], "quantity": "rows"}}],
                "evidence_requirements": ["joined_rows"],
            }
        ],
    }

    result = validate_analysis_plan_contract(plan, dataset_contracts=[
        _contract("orders", "contract_orders"),
        _contract("users", "contract_users"),
    ])

    assert result.ok is False
    assert result.error_type == "unsupported_combination_mode"
    assert "join" in result.message


def test_rejects_independent_step_with_missing_dataset_contract():
    plan = {
        "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Analyze a missing dataset.",
        "method_plan": [
            {
                "step_id": "step_missing",
                "goal": "Analyze the missing dataset.",
                "dataset_inputs": ["missing"],
                "combination_mode": "independent",
                "expected_output": "Evidence",
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'measurement',
                    'label': 'Analyze the missing dataset.: Evidence'
                , "scope": {"datasets": ['missing'], "quantity": "rows"}}],
                "evidence_requirements": ["metric"],
            }
        ],
    }

    result = validate_analysis_plan_contract(
        plan,
        dataset_contracts=[_contract("banner", "contract_banner")],
    )

    assert result.ok is False
    assert result.error_type == "missing_dataset_contract"
    assert result.details["dataset_inputs"] == ["missing"]


def test_rejects_oversize_execution_batch_instead_of_truncating():
    steps = [
        {
            "step_id": f"step_{i}",
            "goal": f"Analyze dataset {i}.",
            "dataset_inputs": [f"ds_{i}"],
            "combination_mode": "independent",
            "expected_output": "Evidence",
            "required_deliveries": [{
                'requirement_id': 'rq_plan_fixture',
                'kind': 'measurement',
                'label': f'Analyze dataset {i}.' + ': ' + 'Evidence'
            , "scope": {"datasets": [f'ds_{i}'], "quantity": "rows"}}],
                "evidence_requirements": ["metric"],
        }
        for i in range(13)
    ]
    contracts = [_contract(f"ds_{i}", f"contract_{i}") for i in range(13)]

    result = validate_analysis_plan_contract(
        {
            "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Analyze all datasets.",
            "method_plan": steps,
        },
        dataset_contracts=contracts,
    )

    assert result.ok is False
    assert result.error_type == "execution_batch_too_large"
    assert result.details["max_executable_steps_per_batch"] == 12


def test_rejects_synthesis_with_too_many_hard_dependencies():
    result = validate_analysis_plan_contract(
        {
            "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Synthesize a large batch.",
            "method_plan": [
                {
                    "step_id": "step_synthesis",
                    "goal": "Synthesize evidence.",
                    "dataset_inputs": [],
                    "combination_mode": "synthesis",
                    "expected_output": "Synthesis",
                    "required_deliveries": [{
                        'requirement_id': 'rq_plan_fixture',
                        'kind': 'interpretation',
                        'label': 'Synthesize evidence.: Synthesis'
                    , "scope": {}}],
                "evidence_requirements": ["summary"],
                    "required_evidence_step_ids": [f"step_{i}" for i in range(9)],
                }
            ],
        },
        dataset_contracts=[],
    )

    assert result.ok is False
    assert result.error_type == "too_many_required_evidence_dependencies"


def test_record_analysis_plan_rejects_legacy_stage3c0b_execution(monkeypatch):
    monkeypatch.setattr("data_agent.tools.analysis_flow._current_state", lambda: None)
    monkeypatch.setattr(
        "data_agent.tools.analysis_flow._write_analysis_artifact",
        lambda kind, payload: {"saved": "artifact.json", "type": kind, "payload": payload},
    )

    result = json.loads(record_analysis_plan(json.dumps({
        "goal": "Analyze files",
        "method_plan": [{"step_id": "s1"}],
        "visualization_strategy": "none",
    })))

    assert result["error_type"] == "legacy_plan_display_only"


def test_record_analysis_plan_persists_valid_stage3c0b_plan(monkeypatch):
    monkeypatch.setattr("data_agent.tools.analysis_flow._current_state", lambda: None)
    monkeypatch.setattr(
        "data_agent.tools.analysis_flow._write_analysis_artifact",
        lambda kind, payload: {"saved": "artifact.json", "type": kind, "payload": payload},
    )

    payload = {
        "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Analyze banner independently.",
        "method_plan": [
            {
                "step_id": "step_banner",
                "goal": "Analyze banner.",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "Banner evidence",
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'measurement',
                    'label': 'Analyze banner.: Banner evidence'
                , "scope": {"datasets": ['banner'], "quantity": "rows"}}],
                "evidence_requirements": ["click_rate"],
            }
        ],
        "visualization_strategy": [],
    }

    result = json.loads(record_analysis_plan(json.dumps(payload)))

    assert result["analysis_plan_id"]
    assert result["state_stage"] if "state_stage" in result else True
    assert "error" not in result


def _dependency_plan(graph: dict[str, list[str]]) -> dict:
    return {
        "requirement_revision": 0,
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Analyze independent sources, then synthesize their evidence.",
        "visualization_strategy": [],
        "method_plan": [
            {
                "step_id": step_id,
                "goal": "Produce evidence for " + step_id,
                "expected_output": "Bound evidence",
                "required_deliveries": [{
                    'requirement_id': 'rq_plan_fixture',
                    'kind': 'interpretation' if 'synthesis' == ('synthesis' if dependencies else 'independent') else 'measurement',
                    'label': 'Produce evidence for ' + step_id + ': ' + 'Bound evidence',
                    'scope': {} if dependencies else {'datasets':[step_id], 'quantity':'rows'}
                }],
                "evidence_requirements": ["metric"],
                "combination_mode": "synthesis" if dependencies else "independent",
                "dataset_inputs": [] if dependencies else [step_id],
                "required_evidence_step_ids": dependencies,
            }
            for step_id, dependencies in graph.items()
        ],
    }


@pytest.mark.parametrize(("graph", "error_type"), [
    ({"summary": ["absent"]}, "unknown_evidence_dependency"),
    ({"summary": ["summary"]}, "cyclic_evidence_dependencies"),
    ({"summary": ["a"], "a": ["b"], "b": ["a"], "independent": []},
     "cyclic_evidence_dependencies"),
])
def test_dependency_graph_rejects_unexecutable_plan(graph, error_type):
    result = validate_analysis_plan_contract(_dependency_plan(graph))
    assert not result.ok
    assert result.error_type == error_type
    assert not result.plan


@pytest.mark.parametrize("dependencies", ["a", [None], [""]])
def test_dependency_graph_does_not_silently_drop_invalid_references(dependencies):
    plan = _dependency_plan({"summary": ["a"], "a": []})
    plan["method_plan"][0]["required_evidence_step_ids"] = dependencies
    result = validate_analysis_plan_contract(plan)
    assert not result.ok
    assert result.error_type == "invalid_evidence_dependencies"


def test_dependency_graph_accepts_forward_references_and_independent_fan_in():
    graph = {"summary": ["a", "b"], "a": [], "b": []}
    plan = _dependency_plan(graph)
    result = validate_analysis_plan_contract(plan, dataset_contracts=[
        _contract("a", "contract_a"), _contract("b", "contract_b"),
    ])
    assert result.ok
    assert result.plan["review_status"] == "executable"
    assert {step["step_id"]: step["required_evidence_step_ids"]
            for step in result.plan["method_plan"]} == graph
    assert plan["method_plan"][0]["required_evidence_step_ids"] == ["a", "b"]


def test_registered_plan_rejects_missing_dependency_before_writing(monkeypatch):
    from data_agent.tools.registry import registry

    writes = []
    monkeypatch.setattr("data_agent.tools.analysis_flow._current_state", lambda: None)
    monkeypatch.setattr("data_agent.tools.analysis_flow._write_analysis_artifact",
                        lambda *args: writes.append(args) or {})
    monkeypatch.setattr("data_agent.tools.task_tools.create_workflow_tasks_from_spec",
                        lambda *args: writes.append(args) or {})
    result = registry.execute("record_analysis_plan", {
        "plan_json": _dependency_plan({"summary": ["absent"]}),
    })
    payload = json.loads(result.summary)
    assert payload.get("error_type") == "unknown_evidence_dependency", payload
    assert writes == []


@pytest.fixture
def bound_goal_plan(tmp_path, monkeypatch):
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.config import get_config
    from tests.support.plan_inputs import bind_plan_fixture
    monkeypatch.setattr(get_config(), "sessions_dir", tmp_path / "sessions")
    state = AnalysisSessionState(session_id="typed-plan")
    plan = bind_plan_fixture(state, _dependency_plan({"a": [], "summary": ["a"]}))
    return state, plan


def _validate_bound(state, plan):
    from data_agent.session.history import load_canonical_history
    return validate_analysis_plan_contract(
        plan, answer_requirements=state.answer_requirements,
        requirement_revision=state.requirement_revision,
        canonical_history=load_canonical_history(state.session_id),
    )


def test_plan_retains_all_six_necessary_chart_deliveries_before_any_result(bound_goal_plan):
    from copy import deepcopy
    state, plan = bound_goal_plan
    rid = state.answer_requirements[0]["id"]
    step = plan["method_plan"][0]
    plan["method_plan"] = [step]
    step["required_deliveries"] = [
        {"requirement_id": rid, "kind": "chart", "label": f"Source {i} chart", "scope":{"datasets":["a"],"parameters":{"chart_type":f"view_{i}"}}}
        for i in range(1, 7)
    ]
    before = deepcopy(state.answer_requirements)
    result = _validate_bound(state, plan)
    assert result.ok
    assert state.answer_requirements == before  # Validation does not commit.
    deliveries = result.requirements[0]["necessary_deliveries"]
    assert len(deliveries) == len({d["id"] for d in deliveries}) == 6
    assert state.tool_receipts == []
    assert not any("claim_ids" in d or "completed" in d for d in deliveries)
    state.answer_requirements = result.requirements
    step["required_deliveries"].pop()
    rejected = _validate_bound(state, plan)
    assert rejected.error_type == "necessary_delivery_change"
    assert len(state.answer_requirements[0]["necessary_deliveries"]) == 6


@pytest.mark.parametrize("mutation,error_type", [
    ("unknown", "unknown_plan_requirement"),
    ("withdrawn", "unknown_plan_requirement"),
    ("source", "invalid_plan_requirement_origin"),
    ("revision", "requirement_revision"),
    ("selector", "invalid_required_delivery"),
    ("old_contract", "legacy_plan_display_only"),
])
def test_plan_rejects_invalid_binding_without_mutating_the_goal(bound_goal_plan, mutation, error_type):
    from copy import deepcopy
    state, plan = bound_goal_plan
    if mutation == "unknown": plan["method_plan"][0]["required_deliveries"][0]["requirement_id"] = "rq_unknown"
    if mutation == "withdrawn": state.answer_requirements[0]["lifecycle_status"] = "withdrawn"
    if mutation == "source": state.answer_requirements[0]["original_text"] = "changed source"
    if mutation == "revision": plan["requirement_revision"] += 1
    if mutation == "selector": plan["method_plan"][0]["required_deliveries"][0]["result_path"] = ["invented"]
    if mutation == "old_contract": plan["contract_version"] = "stage3c0b.v1"
    before = deepcopy(state.answer_requirements)
    result = _validate_bound(state, plan)
    assert not result.ok
    assert result.error_type == error_type
    assert state.answer_requirements == before
    assert state.analysis_plan is None


def test_plan_identity_survives_unrelated_revision_and_round_trip(bound_goal_plan):
    from copy import deepcopy
    state, plan = bound_goal_plan
    original = deepcopy(plan)
    first = _validate_bound(state, plan)
    assert first.ok
    assert plan == original
    repeated = _validate_bound(state, first.plan)
    assert repeated.ok
    state.requirement_revision += 1
    plan["requirement_revision"] = state.requirement_revision
    later = _validate_bound(state, plan)
    assert (first.plan["id"], first.plan["plan_sha256"]) == (repeated.plan["id"], repeated.plan["plan_sha256"]) == (later.plan["id"], later.plan["plan_sha256"])
    changed = deepcopy(plan)
    changed["method_plan"][0]["dataset_inputs"] = ["other"]
    other = _validate_bound(state, changed)
    assert not other.ok and other.error_type=="undeclared_step_input"
    assert state.analysis_plan is None


def test_plan_tool_commits_once_and_rolls_back_a_failed_goal_save(bound_goal_plan, tmp_path, monkeypatch):
    from copy import deepcopy
    from data_agent.agent.context import AgentContext, use_agent_context
    from data_agent.session.workspace import Workspace
    from data_agent.session.task_manager import TaskManager
    import data_agent.tools.task_tools as task_tools
    state, plan = bound_goal_plan
    state.dataset_contracts = [_contract("a", "contract_a")]
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    monkeypatch.setattr(task_tools, "task_manager", manager)
    monkeypatch.setattr("data_agent.session.task_manager.task_manager", manager)
    ctx = AgentContext(session_id=state.session_id, analysis_state=state, workspace=Workspace())
    revision = state.requirement_revision
    with use_agent_context(ctx):
        first = json.loads(record_analysis_plan(plan))
        assert "error" not in first, first
        assert len(first["required_deliveries"]) == 2
        assert state.requirement_revision == revision + 1
        plan["requirement_revision"] = state.requirement_revision
        second = json.loads(record_analysis_plan(plan))
        assert "error" not in second, second
        assert first["analysis_plan_id"] == second["analysis_plan_id"]
        assert first["workflow"]["task_ids"] == second["workflow"]["task_ids"]
        assert state.requirement_revision == revision + 1
        tasks = manager.list_active_for_scope(session_id=state.session_id, project_name="")
        assert all(t["plan_sha256"] == first["plan_sha256"] and t["required_delivery_ids"] for t in tasks)
        before = deepcopy((state.answer_requirements, state.requirement_revision, state.analysis_plan, state.analysis_spec, state.goal, state.stage))
        task_bytes={p.name:p.read_bytes() for p in manager.dir.glob("*.json")}
        plan["goal"] = "Different presentation of the same execution"
        monkeypatch.setattr(state, "save", lambda: (_ for _ in ()).throw(OSError("simulated disk error")))
        with pytest.raises(OSError, match="simulated disk error"):
            record_analysis_plan(plan)
        assert (state.answer_requirements, state.requirement_revision, state.analysis_plan, state.analysis_spec, state.goal, state.stage) == before
        assert {p.name:p.read_bytes() for p in manager.dir.glob("*.json")}==task_bytes


@pytest.mark.parametrize("kind", ["knowledge", "presentation"])
def test_plan_preserves_consultation_and_style_goal_roles(bound_goal_plan, kind):
    state, plan = bound_goal_plan
    state.answer_requirements[0]["semantic_kind"] = kind
    rejected = _validate_bound(state, plan)
    assert rejected.error_type == ("consultation_delivery_change" if kind == "knowledge" else "presentation_delivery_change")
    for step in plan["method_plan"]:
        step["required_deliveries"][0]["kind"] = "knowledge" if kind == "knowledge" else "interpretation"
    accepted = _validate_bound(state, plan)
    assert accepted.ok



def test_required_delivery_declaration_cannot_inherit_completion_from_old_selectors(bound_goal_plan):
    from data_agent.agent.publication.requirements import bind_requirements
    state, plan = bound_goal_plan
    result = _validate_bound(state, plan)
    assert result.ok
    state.answer_requirements = result.requirements
    req = state.answer_requirements[0]
    req["delivery_targets"] = [{"dataset": "a", "tool": "describe_dataset"}]
    claim = {"id": "current-observation", "value": 12,
        "target": {"dataset": "a", "tool": "describe_dataset"},
        "scope": {"dataset": "a"}, "basis_refs": [{"receipt_id":"unplanned","result_path":["shape","rows"],"data_identities": {"a": {"version_id": "current"}}}]}
    binding = bind_requirements(state, [claim])[req["id"]]
    assert not binding.get("claim_ids")
    assert binding["gap"]["status"] == "not_computed"
    assert all(d["label"] in binding["gap"]["reason"] for d in req["necessary_deliveries"] if d["kind"] not in {"knowledge","interpretation","limitation","conditional_action"})



def test_replan_references_host_delivery_ids_without_repeating_the_business_label(bound_goal_plan):
    state, plan = bound_goal_plan
    first = _validate_bound(state, plan)
    assert first.ok
    state.answer_requirements = first.requirements
    for step, normalized in zip(plan["method_plan"], first.plan["method_plan"]):
        step["required_deliveries"] = [{"id": d["id"]} for d in normalized["required_deliveries"]]
    reused = _validate_bound(state, plan)
    assert reused.ok
    assert reused.plan["plan_sha256"] == first.plan["plan_sha256"]
    plan["method_plan"][0]["required_deliveries"][0]["id"] = "dl_unknown"
    assert _validate_bound(state, plan).error_type == "unknown_required_delivery"


@pytest.mark.parametrize("count",[1,4,16])
def test_independent_explicit_bounded_inputs_bind_every_current_contract(count):
    names=["source_"+str(i) for i in range(count)]
    plan={"contract_version":STAGE3C0B_CONTRACT_VERSION,"requirement_revision":0,"goal":"Joint business calculation","method_plan":[{"step_id":"joint","goal":"Calculate declared inputs","expected_output":"Joint table","combination_mode":"independent","dataset_inputs":names,"evidence_requirements":["actual_reads"],"required_deliveries":[{"requirement_id":"rq_joint","kind":"table","label":"Joint business table","scope":{"datasets":names}}]}],"visualization_strategy":[]}
    result=validate_analysis_plan_contract(plan,dataset_contracts=[_contract(n,"contract_"+n) for n in names])
    assert result.ok,result
    assert result.plan["method_plan"][0]["dataset_contract_ids"]==["contract_"+n for n in names]


@pytest.mark.parametrize("fault",["too_many","duplicate","undeclared","synthesis_raw"])
def test_bounded_input_contract_rejects_hidden_or_unbounded_reader_authority(fault):
    names=["orders","users"]
    if fault=="too_many":names=["source_"+str(i) for i in range(17)]
    if fault=="duplicate":names=["orders","orders"]
    scope=names[:1] if fault=="undeclared" else names
    plan={"contract_version":STAGE3C0B_CONTRACT_VERSION,"requirement_revision":0,"goal":"Joint calculation","method_plan":[{"step_id":"joint","goal":"Calculate","expected_output":"Table","combination_mode":"synthesis" if fault=="synthesis_raw" else "independent","dataset_inputs":names,"evidence_requirements":["actual_reads"],"required_deliveries":[{"requirement_id":"rq_joint","kind":"table","label":"Joint table","scope":{"datasets":scope}}]}],"visualization_strategy":[]}
    result=validate_analysis_plan_contract(plan,dataset_contracts=[_contract(n,"contract_"+n) for n in set(names)])
    assert not result.ok
    if fault=="undeclared":assert result.error_type=="undeclared_step_input"


def test_display_analysis_spec_cannot_replace_executable_plan(bound_goal_plan,tmp_path,monkeypatch):
    from copy import deepcopy
    from data_agent.agent.context import AgentContext,use_agent_context
    from data_agent.session.workspace import Workspace
    from data_agent.tools.analysis_flow import record_analysis_spec
    state,plan=bound_goal_plan
    state.analysis_plan={"id":"sealed","plan_sha256":"sha256:original","contract_version":STAGE3C0B_CONTRACT_VERSION}
    before=deepcopy(state.analysis_plan)
    with use_agent_context(AgentContext(session_id=state.session_id,analysis_state=state,workspace=Workspace())):
        response=json.loads(record_analysis_spec(json.dumps({"goal":"Display only","question_type":"description","metrics":[],"dimensions":[],"required_data":[],"method_plan":[],"limitations":[]})))
        assert response["workflow"]["created"]==0 and state.analysis_plan==before
        rejected=json.loads(record_analysis_spec(json.dumps(dict(plan,question_type="description",metrics=[],dimensions=[],required_data=[],limitations=[]))))
        assert rejected["error_type"]=="analysis_spec_display_only" and state.analysis_plan==before


@pytest.mark.parametrize("count,accepted", [(32, True), (33, False), (65, False)])
def test_delivery_limits_bound_each_original_goal_and_execution_step(bound_goal_plan, count, accepted):
    state, plan = bound_goal_plan
    rid = state.answer_requirements[0]["id"]
    step = plan["method_plan"][0]
    plan["method_plan"] = [step]
    step["required_deliveries"] = [
        {"requirement_id": rid, "kind": "chart", "label": f"View {i}",
         "scope": {"datasets": ["a"], "parameters": {"chart_type": f"view_{i}"}}}
        for i in range(count)
    ]
    result = _validate_bound(state, plan)
    assert result.ok is accepted
    assert state.tool_receipts == []


# S1 cross-interface oracles are independent of host delivery matching.
@pytest.mark.parametrize("scope", [
    {"datasets":["orders"],"quantity":"median"},
    {"datasets":["orders"],"quantity":"mean","parameters":{"periods":3}},
    {"datasets":["orders"],"quantity":"mean","parameters":{"window_days":"seven"}},
    {"datasets":["orders"],"quantity":"mean","surprise":True},
])
def test_s1_public_schema_rejects_the_same_invalid_business_scope(scope):
    from jsonschema import Draft7Validator
    from data_agent.tools import discover_tools
    from data_agent.tools.registry import registry
    discover_tools()
    schema=registry.get("record_analysis_plan").parameters["properties"]["plan_json"]
    plan={"contract_version":STAGE3C0B_CONTRACT_VERSION,"requirement_revision":0,"goal":"Amount mean","visualization_strategy":[],"method_plan":[{"goal":"Amount mean","expected_output":"Mean","evidence_requirements":["receipt"],"dataset_inputs":["orders"],"required_deliveries":[{"requirement_id":"rq_mean","kind":"measurement","label":"Amount mean","scope":scope}]}]}
    assert list(Draft7Validator(schema).iter_errors(plan)), scope
    assert not validate_analysis_plan_contract(plan).ok


def test_s1_same_scope_append_preserves_original_delivery_and_history(bound_goal_plan):
    from copy import deepcopy
    state,plan=bound_goal_plan
    initial=_validate_bound(state,plan)
    assert initial.ok,initial
    state.answer_requirements=initial.requirements
    before=deepcopy(state.answer_requirements)
    candidate=deepcopy(initial.plan)
    # A new business product, with every original obligation explicitly retained.
    step=candidate["method_plan"][0]
    step["required_deliveries"]=[{"id":d["id"]} for d in step["required_deliveries"]]+[{"requirement_id":state.answer_requirements[0]["id"],"kind":"table","label":"Original source table","scope":{"datasets":["a"]}}]
    result=_validate_bound(state,candidate)
    assert result.ok,result
    assert state.answer_requirements==before
    old={d["id"] for r in before for d in r["necessary_deliveries"]}
    new={d["id"] for r in result.requirements for d in r["necessary_deliveries"]}
    assert old < new


@pytest.mark.parametrize("fault",[None,"visualization_string","unknown_step","wire_string"])
def test_s1_public_whole_plan_shape_matches_host_contract(bound_goal_plan,fault):
    from copy import deepcopy
    from jsonschema import Draft7Validator
    from data_agent.tools import discover_tools
    from data_agent.tools.registry import registry
    discover_tools()
    state,original=bound_goal_plan
    plan=deepcopy(original)
    if fault=="visualization_string": plan["visualization_strategy"]="none"
    if fault=="unknown_step": plan["method_plan"][0]["unknown"]=True
    if fault=="wire_string": plan=json.dumps(plan)
    schema=registry.get("record_analysis_plan").parameters["properties"]["plan_json"]
    assert bool(list(Draft7Validator(schema).iter_errors(plan))) == (fault is not None)
    if fault!="wire_string": assert _validate_bound(state,plan).ok == (fault is None)
    else:
        result=registry.execute("record_analysis_plan",{"plan_json":plan}).data
        assert result["error_type"]=="invalid_tool_arguments"


@pytest.mark.parametrize("kind",["measurement","table","series","fit","forecast","scenario","hypothesis","chart","artifact","knowledge","interpretation","limitation","conditional_action"])
def test_s1_each_declared_delivery_kind_has_the_same_public_structure_and_host_result(kind):
    from jsonschema import Draft7Validator
    from data_agent.agent.analysis_plan_contracts import analysis_plan_schema
    scope={"datasets":["orders"]}
    if kind=="measurement":scope.update(metrics=["amount"],quantity="mean")
    plan={"contract_version":"stage3c0b.v2","requirement_revision":0,"goal":"Business delivery","method_plan":[{"goal":"Produce declared product","expected_output":"Product","evidence_requirements":["receipt"],"dataset_inputs":["orders"],"required_deliveries":[{"requirement_id":"rq_original","kind":kind,"label":"Original obligation","scope":scope}]}]}
    assert not list(Draft7Validator(analysis_plan_schema()).iter_errors(plan))
    assert validate_analysis_plan_contract(plan).ok
