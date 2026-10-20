"""Expected publication behavior through canonical requests and actual tools."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import hashlib
import json

import pandas as pd
import pytest

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.session.history import CanonicalHistorySnapshot, _history_sha256


def history(*contents):
    messages=[{"role":"user","content":c,"request_id":source_ref(c)} for c in contents]
    return CanonicalHistorySnapshot(messages,4,_history_sha256(messages),len(messages))


def source_ref(content):
    return "msg_"+hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def change(content,span,kind="result",op="add",**extra):
    start=content.index(span)
    return dict(op=op,start=start,end=start+len(span),kind=kind,**extra)


def test_nine_requirements_are_not_truncated_and_replay_is_idempotent():
    from data_agent.agent.publication.requirements import update_requirements, project_requirements
    content="；".join("指标"+str(i) for i in range(9))
    state=AnalysisSessionState("s1")
    proposals=[change(content,"指标"+str(i)) for i in range(9)]
    ids=update_requirements(state,history(content),source_ref(content),proposals,expected_revision=0)
    assert len(ids)==9 and state.requirement_revision==1
    assert update_requirements(state,history(content),source_ref(content),proposals,expected_revision=1)==ids
    assert state.requirement_revision==1
    bindings={rid:{"claim_ids":["c"+str(i)]} for i,rid in enumerate(ids[:8])}
    projected=project_requirements(state,history(content),bindings)
    assert len(projected)==9 and projected[-1]["gap"]["status"]=="not_computed"
    assert all(r["source_turn"]==source_ref(content) for r in projected)


@pytest.mark.parametrize("fault",["revision","summary","digest","duplicate_message","assistant","offset","unknown_target","unknown_field"])
def test_invalid_requirement_change_is_atomic_and_cannot_create_completion(fault):
    from data_agent.agent.publication.requirements import update_requirements
    state=AnalysisSessionState("s1")
    content="计算收入并解释方法"
    snap=history(content)
    proposed=change(content,"收入")
    expected=0
    if fault=="revision": expected=2
    if fault=="summary": snap=SimpleNamespace(**vars(snap))
    if fault=="digest": snap=replace(snap,sha256="bad")
    if fault=="duplicate_message": snap=history(content,content)
    if fault=="assistant":
        messages=[{"role":"assistant","content":content}]
        snap=CanonicalHistorySnapshot(messages,4,_history_sha256(messages),1)
    if fault=="offset": proposed["end"]=999
    if fault=="unknown_target": proposed.update(op="replace",target_id="absent")
    if fault=="unknown_field": proposed["answered"]=True
    with pytest.raises(ValueError):
        update_requirements(state,snap,source_ref(content),[change(content,"方法","knowledge"),proposed],expected_revision=expected)
    assert state.answer_requirements==[] and state.requirement_revision==0


def test_replacement_and_withdrawal_keep_original_sources_without_reviving_old_obligations():
    from data_agent.agent.publication.requirements import update_requirements, project_requirements
    state=AnalysisSessionState("s1")
    first="计算7日收入和复购率"
    ids=update_requirements(state,history(first),source_ref(first),[change(first,"7日收入"),change(first,"复购率")],expected_revision=0)
    second="窗口改为30日收入，不再要求复购率"
    updated=update_requirements(state,history(first,second),source_ref(second),[
        change(second,"30日收入",op="replace",target_id=ids[0]),
        change(second,"不再要求复购率",op="withdraw",target_id=ids[1])],expected_revision=1)
    rows=project_requirements(state,history(first,second),{})
    assert state.requirement_revision==2 and len(updated)==1
    assert [r["withdrawn"] for r in rows]==[True,True,False]
    assert rows[-1]["text"]=="30日收入" and rows[-1]["source_turn"]==source_ref(second)
    assert state.answer_requirements[0]["retired_by"]["source_message_ref"]==source_ref(second)


@pytest.fixture
def engine(tmp_path,monkeypatch):
    from data_agent.config import get_config
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import AgentLoop
    from data_agent.tools import discover_tools
    discover_tools()
    from data_agent.session.task_manager import task_manager
    cfg=get_config()
    monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions")
    monkeypatch.setattr(cfg,"workspace_dir",tmp_path/"workspace")
    monkeypatch.setattr(task_manager,"_dir",cfg.workspace_resolved/"tasks")
    monkeypatch.setattr(task_manager,"_next_id_val",0)
    loop=AgentLoop(client=object(),session_id="native_contract")
    loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-09-01",periods=12),"amount":[10]*6+[20]*6}))
    with use_agent_context(loop.context): yield loop,cfg


def execute(loop,tool,args):
    from data_agent.tools.registry import registry
    plan=loop.context.analysis_state.analysis_plan or {}
    from data_agent.session.task_manager import task_manager
    fixture_plan=bool(plan.get("method_plan") and plan["method_plan"][0].get("step_id")=="fixture")
    isolated=not plan or (fixture_plan and not task_manager.get_active_plan_id(loop.session_id,loop.context.project_name or ""))
    # Unit-isolation binding is explicit BEFORE execution. It never signs off
    # the normal AgentLoop/app path, which must pass its own real task guard.
    if not isolated:
        error=loop._current_task_scope_guard(tool,args)
        assert not error,error
    binding=loop._capture_tool_execution_binding(tool,args)
    if isolated and fixture_plan:
        step=plan["method_plan"][0]
        binding.update(plan_id=plan["id"],plan_sha256=plan["plan_sha256"],step_id=step["step_id"],
            requirement_ids=step["requirement_ids"],required_delivery_ids=[d["id"] for d in step["required_deliveries"]])
    result=registry.execute(tool,args)
    try: structured=result.data or json.loads(result.summary)
    except ValueError: structured=None
    rid=loop._record_turn_tool_result(tool,result.summary,args,tool+"-call-"+str(len(loop.context.analysis_state.tool_receipts)),structured,execution_binding=binding)
    assert rid, result.summary
    if structured is not None: assert loop.context.analysis_state.tool_receipts[-1]["detail_ref"]["sha256"],result.summary
    return rid,structured


def test_actual_describe_and_compare_are_combined_without_builder_precedence(engine):
    from data_agent.agent.publication.native import resolve_native_claims
    from data_agent.agent.publication.contracts import HostSnapshot
    from data_agent.agent.publication.service import PublicationService
    loop,_=engine
    describe,_=execute(loop,"describe_dataset",{"name":"orders"})
    comparison,_=execute(loop,"compare_periods",{"name":"orders","date_col":"day","metrics":"amount",
        "period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"})
    facts=resolve_native_claims(session_id=loop.session_id,receipt_id=describe)+resolve_native_claims(session_id=loop.session_id,receipt_id=comparison)
    values={c["label"]:c["value"] for c in facts}
    assert values["记录数"]==12 and values["观测日期含首尾日数"]==12
    assert values["amount：前期"]==60 and values["amount：后期"]==120 and values["amount：差值"]==60
    assert next(c for c in facts if c["label"]=="amount：差值")["unit"] is None
    req={"id":"r1","text":"当前概览与两期比较","source_turn":"user1","claim_ids":[c["id"] for c in facts],
        "open_purposes":[],"artifact_ids":[],"gap":None,"withdrawn":False}
    snap=HostSnapshot.freeze(session_id=loop.session_id,turn_id="t1",history_revision=1,requirement_revision=1,mode="analysis",
        requirements=[req],claims=facts,artifacts=[],data_identities={"orders":loop.context.workspace.get_data_identity("orders")})
    answer=PublicationService(snap).publish('{}').as_dict()
    assert answer["requirement_outcomes"][0]["status"]=="answered"
    assert {r["ref"] for r in answer["render_trace"] if r["kind"]=="claim"}=={c["id"] for c in facts}


@pytest.mark.parametrize("fault",["wrong_diff","wrong_pct","wrong_days","old_version","wrong_dataset"])
def test_native_comparison_cannot_authorize_inconsistent_arithmetic_or_scope(engine,fault):
    from data_agent.agent.publication.native import resolve_native_claims
    loop,cfg=engine
    rid,result=execute(loop,"compare_periods",{"name":"orders","date_col":"day","metrics":"amount",
        "period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"})
    receipt=loop.context.analysis_state.tool_receipts[-1]
    if fault=="wrong_diff": result["metrics"]["amount"]["diff"]=999
    if fault=="wrong_pct": result["metrics"]["amount"]["change_pct"]=0.277
    if fault=="wrong_days": result["period_a"]["day_count"]=5
    if fault=="old_version": loop.context.workspace.add("orders",pd.DataFrame({"amount":[9]}))
    if fault=="wrong_dataset": receipt["arguments"]["name"]="other"
    if fault.startswith("wrong_") and fault!="wrong_dataset":
        path=cfg.sessions_resolved/loop.session_id/receipt["detail_ref"]["path"]
        path.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
        receipt["detail_ref"]["sha256"]="sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
        receipt["structured_result_sha256"]="sha256:"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    with pytest.raises(ValueError): resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"flat","old_version","causal","fake_status","wrong_metric","unregistered","duplicate_receipt"])
def test_hypothesis_publication_recomputes_status_from_original_measurements(engine,fault):
    from data_agent.agent.publication.native import resolve_hypothesis_claims
    loop,_=engine
    if fault=="flat": loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-09-01",periods=12),"amount":[20]*12}))
    from tests.test_trusted_publication_runtime import request
    request(loop,"核当前描述假设",{'kind':'hypothesis','scope':{'datasets':['orders'],'metrics':['amount']}})
    plan_id=loop.context.analysis_state.analysis_plan["id"]
    rid,result=execute(loop,"analyze_time_series",{"name":"orders","date_col":"day","value_col":"amount"})
    receipt=loop.context.analysis_state.tool_receipts[-1]
    hypothesis_set={"id":"hs1","plan_id":plan_id,"dataset":"orders","hypotheses":[{
        "id":"h1","claim":"amount changes","claim_type":"descriptive","status":"supported",
        "verification_level":"verifiable","decision_rule":{"predicate":"changed","metrics":["amount"]}}]}
    record={"id":"ev1","plan_id":plan_id,"dataset":"orders","claim":"unrelated phrasing",
        "tool_receipt_ids":[rid],"result_bindings":[{"receipt_id":rid,"result_sha256":receipt["structured_result_sha256"],"data_identities":receipt["data_identities"]}]}
    if fault=="old_version": loop.context.workspace.add("orders",pd.DataFrame({"amount":[20]*12}))
    if fault=="causal": hypothesis_set["hypotheses"][0]["claim_type"]="causal"
    if fault=="fake_status": record["result_bindings"]=[]
    if fault=="wrong_metric": hypothesis_set["hypotheses"][0]["decision_rule"]["metrics"]=["cost"]
    from data_agent.agent.hypotheses import persist_hypothesis_set
    registered=persist_hypothesis_set(loop.session_id,hypothesis_set)
    if fault!="unregistered": loop.context.analysis_state.add_hypothesis_set_ref(registered)
    if fault=="duplicate_receipt": loop.context.analysis_state.tool_receipts.append(deepcopy(receipt))
    if fault=="unregistered":
        with pytest.raises(ValueError):
            resolve_hypothesis_claims(session_id=loop.session_id,hypothesis_set=hypothesis_set,evidence_records=[record])
        return
    claims,gaps=resolve_hypothesis_claims(session_id=loop.session_id,hypothesis_set=hypothesis_set,evidence_records=[record])
    if fault not in (None,"flat"):
        assert claims==[] and gaps and gaps[0]["status"]=="evidence_insufficient"
    else:
        assert claims[0]["value"]==("refuted" if fault=="flat" else "supported") and claims[0]["basis_refs"][0]["receipt_id"]==rid
        assert "仅描述" in claims[0]["limitations"][0]
        from data_agent.agent.publication.contracts import HostSnapshot
        from data_agent.agent.publication.service import PublicationService
        req={"id":"h-rq","text":"检验当前变化假设","source_turn":"user1","claim_ids":[claims[0]["id"]],"artifact_ids":[],"open_purposes":[],"gap":None,"withdrawn":False}
        snap=HostSnapshot.freeze(session_id=loop.session_id,turn_id="h1",history_revision=1,requirement_revision=1,plan_id=plan_id,mode="analysis",requirements=[req],claims=claims,artifacts=[],data_identities=receipt["data_identities"])
        answer=PublicationService(snap).publish('{}').as_dict()
        assert ("反驳" if fault=="flat" else "支持") in answer["body"]
        assert answer["requirement_outcomes"][0]["status"]=="answered"


@pytest.mark.parametrize("fault",[None,"skipped","pending","old_version","wrong_scope","wrong_option","corrupt"])
def test_confirmation_reference_is_durable_scoped_and_never_a_numeric_fact(engine,fault):
    from data_agent.agent.publication.requirements import resolve_confirmation
    from data_agent.agent.confirmation.models import ConfirmationRequest,ConfirmationRecord,ConfirmationOption,ConfirmationEvent,ConfirmationStatus,AnswerMode
    from data_agent.agent.confirmation.store import ConfirmationStore
    loop,cfg=engine
    request=ConfirmationRequest(confirmation_id="cf1",session_id=loop.session_id,turn_id="t1",decision_key="cost-window-1",
        source="ask_user_question",operation="business_scope",question="成本口径？",decision_impact="改变净收益口径",
        answer_mode=AnswerMode.SINGLE_SELECT,options=(ConfirmationOption("含渠道成本","cost_b"),),blocking_surfaces=("analysis_execution",),
        skippable=True,resolution_action="record_confirmation_answer",resolution_params={"decision_kind":"metric_definition"},data_version="v1",spec_version="plan1")
    store=ConfirmationStore(cfg.sessions_resolved,loop.session_id)
    record=ConfirmationRecord.from_request(request,now="2026-10-01T00:00:00Z")
    store.append(ConfirmationEvent.requested(record,event_id="req1"))
    if fault!="pending":
        record=replace(record,status=ConfirmationStatus.SKIPPED if fault=="skipped" else ConfirmationStatus.RESOLVED,
            response="unknown" if fault=="wrong_option" else "cost_b",response_id="response1",version=2)
        store.append(ConfirmationEvent(event_id="answer1",confirmation_id="cf1",session_id=loop.session_id,event_type="resolved",version=2,occurred_at=record.updated_at,record=record))
    if fault=="corrupt": store.events_path.write_text('broken',encoding="utf-8")
    current=replace(request,data_version="v2") if fault=="old_version" else replace(request,decision_key="other") if fault=="wrong_scope" else request
    if fault:
        with pytest.raises(ValueError): resolve_confirmation(current)
    else:
        ref=resolve_confirmation(current)
        assert ref["response"]=="cost_b" and ref["response_id"]=="response1"
        assert "value" not in ref and "claim_ids" not in ref


@pytest.mark.parametrize("a,b",[(0.000001,0.000002),(0.123456,0.234567),(0,20),(-10,-20)])
def test_native_comparison_uses_original_precision_not_display_rounding(engine,a,b):
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-09-01",periods=12),"amount":[a]*6+[b]*6}))
    rid,result=execute(loop,"compare_periods",{"name":"orders","date_col":"day","metrics":"amount",
        "period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"})
    facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    values={c["label"]:c["value"] for c in facts}
    assert values["amount：前期"]==pytest.approx(a*6,rel=1e-14,abs=0)
    assert values["amount：后期"]==pytest.approx(b*6,rel=1e-14,abs=0)
    assert values["amount：差值"]==pytest.approx((b-a)*6,rel=1e-14,abs=0)
    assert values["amount：相对变化"]==(None if a==0 else round((b-a)/abs(a)*100,2))
    if a==0.000001:
        assert result["metrics"]["amount"]["period_a"]==0
        assert values["amount：前期"]>0


def test_missing_historical_origin_limits_only_that_requirement():
    from data_agent.agent.publication.requirements import update_requirements, project_requirements
    state=AnalysisSessionState("s1")
    old,new="计算旧窗口收入","计算当前记录数"
    old_id=update_requirements(state,history(old),source_ref(old),[change(old,"旧窗口收入")],expected_revision=0)[0]
    new_id=update_requirements(state,history(old,new),source_ref(new),[change(new,"当前记录数")],expected_revision=1)[0]
    rows=project_requirements(state,history(new),{old_id:{"claim_ids":["old-claim"]},new_id:{"claim_ids":["current-claim"]}})
    assert rows[0]["gap"]["status"]=="evidence_insufficient" and rows[0]["claim_ids"]==[]
    assert rows[0]["artifact_ids"]==[] and rows[0]["open_purposes"]==[]
    assert rows[1]["claim_ids"]==["current-claim"] and rows[1]["gap"] is None


def test_withdrawn_requirement_history_does_not_exhaust_current_publication_budget():
    from data_agent.agent.publication.requirements import update_requirements
    state=AnalysisSessionState("long_chat")
    messages=[];previous=None
    for number in range(130):
        content="改为第"+str(number)+"个窗口"
        ref="long_request_"+str(number)
        messages.append({"role":"user","content":content,"request_id":ref})
        snapshot=CanonicalHistorySnapshot(list(messages),number+1,_history_sha256(messages),len(messages))
        proposal={"op":"replace" if previous else "add","start":0,"end":len(content),"kind":"result"}
        if previous:proposal["target_id"]=previous
        previous=update_requirements(state,snapshot,ref,[proposal],expected_revision=state.requirement_revision)[0]
    assert len(state.answer_requirements)==130 and state.requirement_revision==130
    assert [r["id"] for r in state.answer_requirements if r["lifecycle_status"]=="active"]==[previous]
    assert all(r.get("retired_by") for r in state.answer_requirements[:-1])



def test_style_replacement_preserves_unfinished_facts_and_chart_delivery():
    from data_agent.agent.publication.requirements import update_requirements
    state=AnalysisSessionState("s1")
    first="计算收入；展示六图；给分析师说明"
    ids=update_requirements(state,history(first),source_ref(first),[
        change(first,"计算收入"),
        change(first,"展示六图","presentation",presentation_style="analyst",presentation_role="delivery"),
        change(first,"给分析师说明","presentation",presentation_style="analyst",presentation_role="style",presentation_scope="session")],expected_revision=0)
    second="改用大白话"
    update_requirements(state,history(first,second),source_ref(second),[
        change(second,second,"presentation",presentation_style="plain",presentation_role="style",presentation_scope="session")],expected_revision=1)
    status={r["id"]:r["lifecycle_status"] for r in state.answer_requirements}
    assert status[ids[0]]==status[ids[1]]=="active"
    assert status[ids[2]]=="withdrawn"
    assert state.answer_requirements[-1]["presentation_style"]=="plain"


def test_targets_complete_original_question_without_minting_facts(engine):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.requirements import record_execution_targets,bind_requirements
    from data_agent.agent.publication.runtime import collect_products
    from data_agent.session.history import load_canonical_history
    loop,_=engine;state=loop.context.analysis_state
    request(loop,"请计算订单金额均值并解释方法",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}})
    req=state.answer_requirements[0];req["purposes"]=["interpretation"]
    before=deepcopy(req);did=req["necessary_deliveries"][0]["id"]
    assert bind_requirements(state,[])[req["id"]]["gap"]["status"]=="not_computed"
    execute(loop,"describe_dataset",{"name":"orders"})
    claims,_,_,_,_=collect_products(state,loop.session_id)
    bound=bind_requirements(state,claims)[req["id"]]
    assert [c["value"] for c in claims if c["id"] in bound["claim_ids"]]==[15]
    result=record_execution_targets(state,load_canonical_history(loop.session_id),loop.context.workspace,{"requirement_revision":state.requirement_revision,"bindings":[{"delivery_id":did,"catalogue_ids":bound["claim_ids"]}]})
    assert result["status"]=="host_verified_bindings"
    assert state.answer_requirements[0]["original_text"]==before["original_text"]
    assert bound["open_purposes"]==["interpretation"]
    changed=deepcopy(claims)
    for c in changed:
        for proof in c["basis_refs"]:proof["data_identities"]["orders"]["version_id"]="another-version"
    assert bind_requirements(state,changed)[req["id"]]["gap"]


@pytest.mark.parametrize("timing", ["before_plan", "other_delivery"])
def test_explicit_target_adopts_verified_existing_native_fact_without_reexecuting(engine, timing):
    from tests.support.publication_runtime import request, draft
    from data_agent.agent.publication.requirements import record_execution_targets, bind_requirements
    from data_agent.agent.publication.runtime import collect_products, snapshot_for_turn, publish, model_publication_context
    from data_agent.session.history import load_canonical_history

    loop, _ = engine
    state = loop.context.analysis_state
    if timing == "other_delivery":
        request(loop, "先报告均值", {"kind":"measurement", "scope":{"datasets":["orders"], "metrics":["amount"], "quantity":"mean"}})
    execute(loop, "describe_dataset", {"name":"orders"})
    request(loop, "报告原金额合计", {"kind":"measurement", "scope":{"datasets":["orders"], "metrics":["amount"], "quantity":"sum"}})
    req = state.answer_requirements[-1]
    did = req["necessary_deliveries"][0]["id"]
    claims, _, _, _, _ = collect_products(state, loop.session_id)
    claim = next(c for c in claims if c["target"].get("metric") == "amount" and c["target"].get("statistic") == "sum")
    assert bind_requirements(state, claims)[req["id"]]["gap"]
    receipts = deepcopy(state.tool_receipts)
    before = snapshot_for_turn(loop)
    view = model_publication_context(before, state, budget=10**9, measure=lambda v: 1)
    assert claim["id"] in {r[0] for r in view["claims"]}
    assert any(r["id"] == claim["id"] and did in r["delivery_ids"] for r in view["reusable_products"])
    record_execution_targets(state, load_canonical_history(loop.session_id), loop.context.workspace,
        {"requirement_revision":state.requirement_revision, "bindings":[{"delivery_id":did, "catalogue_ids":[claim["id"]]}]})
    snapshot = snapshot_for_turn(loop)
    body, error = publish(loop, draft(snapshot))
    assert error is None and "180" in body
    assert next(r for r in loop._accepted_answer["requirement_outcomes"] if r["requirement_id"] == req["id"])["status"] == "answered"
    assert state.tool_receipts == receipts
    assert {c["id"] for c in collect_products(state, loop.session_id)[0]} == {c["id"] for c in claims}


@pytest.mark.parametrize("fault", ["version", "dataset", "quantity", "window", "tampered", "python_scope"])
def test_explicit_adoption_never_grants_new_source_or_retrospective_python_scope(engine, fault):
    from tests.support.publication_runtime import request
    from data_agent.agent.publication.requirements import record_execution_targets
    from data_agent.agent.publication.runtime import collect_products
    from data_agent.agent.publication.deliveries import catalogue, matches
    from data_agent.session.history import load_canonical_history
    loop, cfg = engine
    execute(loop,"describe_dataset",{"name":"orders"})
    state=loop.context.analysis_state
    scope={"datasets":["orders"],"metrics":["amount"],"quantity":"sum"}
    if fault=="dataset":
        loop.context.workspace.add("foreign",pd.DataFrame({"amount":[180]}));scope["datasets"]=["foreign"]
    if fault=="quantity":scope["quantity"]="mean"
    if fault=="window":scope["parameters"]={"period_a":"2026-09-01~2026-09-02"}
    request(loop,"必须采用当前范围原合计",{"kind":"measurement","scope":scope})
    claims=collect_products(state,loop.session_id)[0]
    claim=next(c for c in claims if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")
    req=state.answer_requirements[-1];did=req["necessary_deliveries"][0]["id"]
    if fault=="python_scope":
        row=next(r for r in catalogue(claims) if r["id"]==claim["id"])
        row["requires_execution_binding"]=True
        assert not matches(req["necessary_deliveries"][0],row,req["source_data_identities"],explicit=True)
        return
    if fault=="version":loop.context.workspace.add("orders",pd.DataFrame({"amount":[180]}))
    if fault=="tampered":
        from pathlib import Path
        (cfg.sessions_resolved/loop.session_id/state.tool_receipts[0]["detail_ref"]["path"]).write_text("tampered",encoding="utf-8")
    before=deepcopy(state.answer_requirements)
    with pytest.raises(ValueError):record_execution_targets(state,load_canonical_history(loop.session_id),loop.context.workspace,
        {"requirement_revision":state.requirement_revision,"bindings":[{"delivery_id":did,"catalogue_ids":[claim["id"]]}]})
    assert state.answer_requirements==before


@pytest.mark.parametrize("fault",["revision","boolean_revision","duplicate","unknown","withdrawn","knowledge","tool","dataset","extra_fact","origin","save"])
def test_target_batch_rejects_atomically_without_changing_canonical_demand(engine,monkeypatch,fault):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.requirements import record_execution_targets
    from data_agent.agent.publication.runtime import collect_products
    from data_agent.session.history import load_canonical_history
    loop,_=engine;state=loop.context.analysis_state
    request(loop,"计算均值",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}})
    execute(loop,"describe_dataset",{"name":"orders"})
    claims,_,_,_,_=collect_products(state,loop.session_id)
    claim=next(c for c in claims if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="mean")
    did=state.answer_requirements[0]["necessary_deliveries"][0]["id"]
    rows=[{"delivery_id":did,"catalogue_ids":[claim["id"]]}];revision=state.requirement_revision;snap=load_canonical_history(loop.session_id)
    if fault=="revision":revision-=1
    if fault=="boolean_revision":revision=True
    if fault=="duplicate":rows.append(deepcopy(rows[0]))
    if fault in {"unknown","knowledge"}:rows[0]["delivery_id"]="foreign-or-knowledge"
    if fault=="withdrawn":state.answer_requirements[0]["lifecycle_status"]="withdrawn"
    if fault in {"tool","dataset"}:rows[0]["catalogue_ids"]=["outside-session"]
    if fault=="extra_fact":rows[0]["value"]=999
    if fault=="origin":snap=history("tampered")
    if fault=="save":monkeypatch.setattr(state,"save",lambda: (_ for _ in ()).throw(OSError("cannot persist")))
    before=deepcopy(state.answer_requirements);oldrev=state.requirement_revision
    with pytest.raises((ValueError,OSError)):record_execution_targets(state,snap,loop.context.workspace,{"requirement_revision":revision,"bindings":rows})
    assert state.answer_requirements==before and state.requirement_revision==oldrev


def test_target_tool_uses_same_session_history_and_updates_revision(engine):
    from tests.test_trusted_publication_runtime import request
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.runtime import collect_products
    loop,_=engine;state=loop.context.analysis_state
    request(loop,"计算订单金额均值",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}})
    execute(loop,"describe_dataset",{"name":"orders"})
    claims,_,_,_,_=collect_products(state,loop.session_id)
    claim=next(c for c in claims if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="mean")
    output=registry.execute("record_answer_targets",{"target_json":{"requirement_revision":state.requirement_revision,"bindings":[{"delivery_id":state.answer_requirements[0]["necessary_deliveries"][0]["id"],"catalogue_ids":[claim["id"]]}]}})
    assert json.loads(output.summary)["status"]=="host_verified_bindings",output.summary
    assert loop.context.requirement_revision==2 and len(state.tool_receipts)==1


def test_target_completion_cannot_retarget_an_existing_metric(engine):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.requirements import record_execution_targets
    from data_agent.agent.publication.runtime import collect_products
    from data_agent.session.history import load_canonical_history
    loop,_=engine;state=loop.context.analysis_state
    request(loop,"计算订单金额均值",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}})
    execute(loop,"describe_dataset",{"name":"orders"})
    claims,_,_,_,_=collect_products(state,loop.session_id)
    other=next(c for c in claims if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")
    before=deepcopy(state.answer_requirements)
    with pytest.raises(ValueError):record_execution_targets(state,load_canonical_history(loop.session_id),loop.context.workspace,{"requirement_revision":state.requirement_revision,"bindings":[{"delivery_id":before[0]["necessary_deliveries"][0]["id"],"catalogue_ids":[other["id"]]}]})
    assert state.answer_requirements==before and state.requirement_revision==1


@pytest.mark.parametrize("fault", [None, "unknown", "kind", "changed_scope", "withdrawn"])
def test_equivalent_continuation_reuses_canonical_business_goal_atomically(fault):
    from data_agent.agent.publication.requirements import update_requirements, project_requirements
    material = json.loads(__import__("pathlib").Path("tests/fixtures/p5-contract-reset-20261009.json").read_text(encoding="utf-8"))["m03_delivery_collection"]
    first, continuation = material["prompts"][0], material["continuation"]["content"]
    state = AnalysisSessionState("offline_original_m03")
    scope = {"datasets": ["M03-source-1"]}
    rid = update_requirements(state, history(first), source_ref(first), [change(first, first, business_scope=scope)], expected_revision=0)[0]
    proposal = change(continuation, continuation, op="reuse", target_id=rid)
    if fault == "unknown": proposal["target_id"] = "invented"
    if fault == "kind": proposal["kind"] = "knowledge"
    if fault == "changed_scope": proposal["business_scope"] = {"datasets":["foreign"]}
    if fault == "withdrawn": state.answer_requirements[0]["lifecycle_status"] = "withdrawn"
    before = deepcopy(state.answer_requirements)
    if fault:
        with pytest.raises(ValueError): update_requirements(state, history(first, continuation), source_ref(continuation), [proposal], expected_revision=1)
        assert state.answer_requirements == before and state.requirement_revision == 1
        return
    assert update_requirements(state, history(first, continuation), source_ref(continuation), [proposal], expected_revision=1) == [rid]
    assert len(state.answer_requirements) == 1
    req = state.answer_requirements[0]
    assert req["original_text"] == first and req["business_scope"] == scope
    assert req["continuation_refs"][0]["original_text"] == continuation
    assert update_requirements(state, history(first, continuation), source_ref(continuation), [proposal], expected_revision=2) == [rid]
    assert state.requirement_revision == 2 and len(req["continuation_refs"]) == 1
    assert project_requirements(state, history(first, continuation), {})[0]["gap"]["status"] == "not_computed"
    assert project_requirements(state, history(first, "changed"), {})[0]["gap"]["status"] == "evidence_insufficient"


def test_independent_goals_keep_individual_coverage_without_text_conflict(engine):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.requirements import bind_requirements
    from data_agent.agent.publication.runtime import collect_products
    loop,_=engine;state=loop.context.analysis_state
    for content,q in [("报告金额均值","mean"),("解释金额均值用于评估哪个范围","mean"),("报告最大值","max")]:
        request(loop,content,{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":q}})
    state.answer_requirements[1]["purposes"]=["interpretation"]
    execute(loop,"describe_dataset",{"name":"orders"})
    claims,_,_,_,_=collect_products(state,loop.session_id);bindings=bind_requirements(state,claims);ids=[r["id"] for r in state.answer_requirements]
    assert all(bindings[i].get("claim_ids") and not bindings[i].get("gap") for i in ids)
    assert bindings[ids[0]]["claim_ids"]==bindings[ids[1]]["claim_ids"]!=bindings[ids[2]]["claim_ids"]
    assert bindings[ids[1]]["open_purposes"]==["interpretation"] and len(ids)==3


@pytest.mark.parametrize("fault", [None, "changed_statistic", "changed_window", "unrelated_dataset"])
def test_execution_refines_technical_candidate_without_changing_business_bounds(engine,fault):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.requirements import record_execution_targets,bind_requirements
    from data_agent.agent.publication.runtime import collect_products
    from data_agent.session.history import load_canonical_history
    loop,_=engine;state=loop.context.analysis_state
    periods={"period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"}
    request(loop,"比较2026年9月前后两期金额变化",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"difference","parameters":periods}})
    args={"name":"orders","date_col":"day","metrics":"amount",**periods}
    if fault=="changed_window":args["period_b"]=periods["period_a"]
    if fault=="unrelated_dataset":loop.context.workspace.add("other",pd.DataFrame({"day":[pd.Timestamp("2026-09-01"),pd.Timestamp("2026-09-07")],"amount":[999,999]}));args["name"]="other"
    execute(loop,"compare_periods",args)
    claims,_,_,_,_=collect_products(state,loop.session_id)
    selected=[c["id"] for c in claims if c.get("target",{}).get("metric")=="amount" and c["basis_refs"][0]["result_path"][-1]==("change_pct" if fault=="changed_statistic" else "diff")]
    payload={"requirement_revision":state.requirement_revision,"bindings":[{"delivery_id":state.answer_requirements[0]["necessary_deliveries"][0]["id"],"catalogue_ids":selected}]}
    before=deepcopy(state.answer_requirements)
    if fault:
        with pytest.raises(ValueError):record_execution_targets(state,load_canonical_history(loop.session_id),loop.context.workspace,payload)
        assert state.answer_requirements==before;return
    record_execution_targets(state,load_canonical_history(loop.session_id),loop.context.workspace,payload)
    assert state.answer_requirements[0]["original_text"]=="比较2026年9月前后两期金额变化"
    assert not bind_requirements(state,claims)[before[0]["id"]].get("gap")


@pytest.mark.parametrize("mode,fault", [(m,f) for m in ["file_new","file_reload","sql_new"] for f in ["raw","analysis","meta","trust","state","bundle","understanding"] if not (m=="sql_new" and f in {"bundle","understanding"})])
def test_ingestion_persistence_failure_restores_memory_disk_and_trust(engine, monkeypatch, tmp_path, mode, fault):
    from copy import deepcopy
    import sqlite3
    from pathlib import Path
    from data_agent.tools.registry import registry
    from data_agent.tools import data_io
    from data_agent.session.workspace import Workspace
    from data_agent.agent.analysis_state import AnalysisSessionState
    loop, cfg = engine
    ws = loop.context.workspace
    source = tmp_path / "current.csv"; source.write_text("amount\n10\n20\n", encoding="utf-8")
    if mode == "file_reload":
        assert not registry.execute("load_data", {"source":str(source),"name":"loaded"}).summary.startswith('{"error"')
        source.write_text("amount\n100\n200\n",encoding="utf-8")
    if mode == "sql_new":
        db=tmp_path/"query.sqlite"
        with sqlite3.connect(db) as con:
            con.execute("CREATE TABLE observations(amount INTEGER)"); con.execute("INSERT INTO observations VALUES (7)")
        args={"name":"loaded","connection_string":"sqlite:///"+str(db.resolve()),"query":"SELECT * FROM observations"}
    else: args={"name":"loaded","source":str(source)}
    before=deepcopy(ws.list_datasets()); history=deepcopy(ws.get_transform_log()); state=deepcopy(loop.context.analysis_state.to_dict())
    own=cfg.sessions_resolved/loop.session_id
    def files(): return {str(p.relative_to(own)):p.read_bytes() for p in own.rglob("*") if p.is_file()}
    disk=files(); frames={n:ws.get(n) for n in before}
    owner,method=(Workspace,"persist_dataset") if fault in {"raw","analysis"} else (Workspace,"save_meta") if fault=="meta" else (AnalysisSessionState,"save") if fault=="state" else (data_io,{"trust":"_persist_trust_record","bundle":"_register_loaded_data_bundle","understanding":"_record_data_understanding_bundle"}[fault])
    original=getattr(owner,method);calls=[]
    def fail(*a,**kw):
        value=original(*a,**kw);calls.append(True)
        if fault=="raw" and len(calls)!=1: return value
        if fault=="analysis" and len(calls)!=2: return value
        raise OSError("injected failure AFTER durable write")
    with monkeypatch.context() as patch:
        patch.setattr(owner,method,fail)
        result=registry.execute("load_sql" if mode=="sql_new" else "reload_data" if mode=="file_reload" else "load_data",args)
    assert calls
    assert result.summary.startswith(("Error",'{"error"')),result.summary
    assert ws.list_datasets()==before
    assert ws.get_transform_log()==history
    assert loop.context.analysis_state.to_dict()==state
    assert files()==disk
    for n,frame in frames.items(): pd.testing.assert_frame_equal(ws.get(n),frame)
    if mode=="file_reload":
        restored=Workspace(); assert restored.restore_persisted_snapshot(loop.session_id,"loaded")
        pd.testing.assert_frame_equal(restored.get("loaded"),frames["loaded"])
    else: assert not Workspace().restore_persisted_snapshot(loop.session_id,"loaded")


@pytest.mark.parametrize("phase", ["planning", "execution", "synthesis", "error"])
def test_ingestion_commit_does_not_bypass_scope(engine, phase):
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
    loop,_=engine
    called=[]
    with loop.context.bind_workspace_scope(WorkspaceScopeSnapshot(phase=phase)):
        if phase == "execution":
            with pytest.raises(ValueError,match="ingestion_scope"):
                loop.context.workspace.commit_ingestion(lambda: called.append(True))
        else:
            assert loop.context.workspace.commit_ingestion(lambda: called.append(True)).startswith("Error:")
    assert called==[]


def test_ingestion_disk_rollback_failure_is_explicit_and_memory_restores(engine, monkeypatch, tmp_path):
    from data_agent.utils import atomic_files
    from data_agent.tools.registry import registry
    loop,cfg=engine;ws=loop.context.workspace
    source=tmp_path/"current.csv";source.write_text("amount\n10\n20\n",encoding="utf-8")
    registry.execute("load_data",{"source":str(source),"name":"loaded"})
    before=ws.get_data_identity("loaded"); original=atomic_files.replace_file
    source.write_text("amount\n100\n200\n",encoding="utf-8")
    calls=[]
    def fail(source,destination,**kw):
        if destination.name=="loaded.pkl" or destination.name=="loaded.parquet":
            calls.append(True)
            if len(calls)==1:
                original(source,destination,**kw)
                raise OSError("write committed, then device unavailable")
            raise OSError("rollback device unavailable")
        return original(source,destination,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(atomic_files,"replace_file",fail)
        result=registry.execute("reload_data",{"source":str(source),"name":"loaded"})
    assert "rollback incomplete" in result.summary
    assert ws.get_data_identity("loaded")==before
    assert not ws.exists("loaded__history")


def test_explicit_adoption_cannot_reuse_an_old_write_as_a_new_operation():
    from data_agent.agent.publication.deliveries import matches
    operation={"action":"create_skill","arguments":{"name":"approved-old-write"}}
    row={"kind":"operation","operation":operation,"declared_delivery_ids":["old"],"metrics":[],"quantity":None,"hypothesis_ids":[],"parameters":{},"data_identities":{}}
    old={"id":"old","kind":"operation","scope":{"operation":operation}}
    new={**old,"id":"new"}
    assert matches(old,row,{},explicit=True)
    assert not matches(new,row,{}) and not matches(new,row,{},explicit=True)


@pytest.mark.parametrize("withdrawn",[False,True])
def test_one_native_curve_receipt_across_sections_has_one_complete_visible_product(engine,withdrawn):
    from data_agent.agent.publication.native import resolve_native_claims
    from data_agent.agent.publication.contracts import HostSnapshot
    from data_agent.agent.publication.service import PublicationService
    from tests.test_trusted_publication_pipeline import accept_all
    loop,_=engine
    loop.context.workspace.add("retention",pd.DataFrame({'day':range(1,8),'value':[.55,.42,.31,.24,.18,.13,.10]}))
    rid,_=execute(loop,"curve_fitting",{"name":"retention","x_col":"day","y_col":"value","scenario_points":[30]})
    facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    selected=[c for c in facts if c['basis_refs'][0]['result_path'] in [['points'],['fits'],['scenarios']]
              or len(c['basis_refs'][0]['result_path'])==3 and c['basis_refs'][0]['result_path'][0]=='points']
    r1={'id':'observed','text':'交付全部观测及拟合','source_turn':'user1','claim_ids':[c['id'] for c in selected if c['basis_refs'][0]['result_path']!=['scenarios']],
        'open_purposes':['interpretation'],'artifact_ids':[],'gap':None,'withdrawn':False}
    r2={**r1,'id':'scenario','text':'交付D30未验证情景','claim_ids':[c['id'] for c in selected if c['basis_refs'][0]['result_path']==['scenarios']],
        'open_purposes':[],'withdrawn':withdrawn}
    snap=HostSnapshot.freeze(session_id=loop.session_id,turn_id='curve',history_revision=1,requirement_revision=1,mode='analysis',
        requirements=[r1,r2],claims=selected,artifacts=[],data_identities={'retention':loop.context.workspace.get_data_identity('retention')})
    sections=[{'requirement_ids':[r['id']],'parts':[{'kind':'claim','ref':cid} for cid in r['claim_ids']]+(
        [{'kind':'text','purpose':'interpretation','text':'仅说明当前观测；情景未验证。','claim_refs':r['claim_ids']}] if r['id']=='observed' else [])} for r in [r1,r2]]
    answer=PublicationService(snap,auditor=accept_all).publish(json.dumps({'schema':'answer_bindings.v2','snapshot_digest':snap.digest,'sections':sections})).as_dict()
    assert answer['body'].count(selected[0]['limitations'][0])==1
    assert answer['body'].split('\n\n').count('实际观测')==1 and answer['body'].split('\n\n').count('拟合模型与误差')==1
    assert ('| 30 |' in answer['body']) is not withdrawn
    active=set(r1['claim_ids']+([] if withdrawn else r2['claim_ids']))
    traces=[t for t in answer['render_trace'] if t['kind']=='claim' and t['disposition']=='accepted']
    assert {t['ref'] for t in traces}==active
    for t in traces:
        assert answer['body'][t['start']:t['end']]==t['rendered_text']
    assert len({(t['start'],t['end']) for t in traces})==1


@pytest.mark.parametrize('fault',[None,'receipt','hash','version','parameters','unit','display','scope','metric','value'])
def test_curve_leaf_reuses_only_its_exact_original_product(fault):
    from tests.test_trusted_publication_pipeline import claim
    from data_agent.agent.publication.renderer import Renderer
    parent=claim('parent',[{'x':1,'y':120}]);parent['basis_refs'][0]['result_path']=['points']
    parent['target']={'tool':'curve_fitting','metric':'amount','parameters':{'x_col':'x','y_col':'amount'}}
    leaf=deepcopy(parent);leaf.update(id='leaf',label='leaf',value=120);leaf['basis_refs'][0]['result_path']=['points',0,'y']
    leaf['scope']['time_scope']=''
    if fault=='receipt':leaf['basis_refs'][0]['receipt_id']='other'
    if fault=='hash':leaf['basis_refs'][0]['result_sha256']='sha256:'+'b'*64
    if fault=='version':leaf['basis_refs'][0]['data_identities']['orders']['version_id']='v2'
    if fault=='parameters':leaf['target']['parameters']['zero_values']='exclude'
    if fault=='unit':leaf['unit']='USD'
    if fault=='display':leaf['target']['curve_display']={'basis':'plan_declaration','value_scale':'fraction'}
    if fault=='scope':leaf['scope']['time_scope']='another-window'
    if fault=='metric':leaf['target']['metric']='cost'
    if fault=='value':leaf['value']=999
    renderer=Renderer();renderer.bind_curve_products([parent,leaf])
    for c in [parent,leaf]:renderer.add_claim(c,part_id=c['id'],ref=c['id'],requirement_ids=[c['id']])
    body=renderer.body
    assert len({(t['start'],t['end']) for t in renderer.trace})==(1 if fault is None else 2)
    assert all(body[t['start']:t['end']]==t['rendered_text'] for t in renderer.trace)
