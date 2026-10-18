from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: statistics. Shared fixtures have one owner."""
from data_agent.agent.publication.contracts import encode
from tests.test_trusted_publication_semantics import execute
from types import SimpleNamespace
import hashlib
import json
import pytest
from tests.support.publication_runtime import AppClient, draft, intent_for_app, request

@pytest.mark.parametrize("values,total",[([10]*12,120),([22400,0.051,0.01417],22400.06517),([9007199254740993,1],9007199254740994),([9000000000000000000,9000000000000000000],18000000000000000000),([None,None],None)])
def test_descriptive_total_is_measured_by_original_tool_without_rounding_or_missing_value_grant(engine,values,total):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    column=pd.Series(values,dtype="float64") if total is None else pd.Series(values)
    loop.context.workspace.add("orders",pd.DataFrame({"amount":column}))
    request(loop,"金额原值合计",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}})
    _,original=execute(loop,"describe_dataset",{"name":"orders"})
    measured=original["field_statistics"][0]["stats"]["sum"]
    assert measured==pytest.approx(total,rel=0,abs=1e-10) if type(total) is float else measured==total
    snap=snapshot_for_turn(loop);req=snap.as_dict()["requirements"][0]
    owned=[c for c in snap.as_dict()["claims"] if c["id"] in req["claim_ids"]]
    body,error=publish(loop,draft(snap));assert error is None
    if total is None:
        assert not owned and loop._accepted_answer["requirement_outcomes"][0]["status"]=="not_computed"
        assert any(c["label"]=="记录数" and c["value"]==2 for c in snap.as_dict()["claims"])
    else:
        assert len(owned)==1 and owned[0]["value"]==measured and type(owned[0]["value"]) is type(measured) and owned[0]["unit"] is None
        assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"


def test_uncomputed_selected_cost_and_insufficient_incremental_effect_have_distinct_public_gaps(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.agent.publication.requirements import update_requirements
    from data_agent.session.history import load_canonical_history
    from data_agent.agent.workbench_view import build_workbench_view
    loop,_=engine
    text="计算所选成本口径下净收益；判断促销增量"
    request(loop,text,{'kind': 'table', 'scope': {'datasets': ['orders'], 'metrics': ['net_profit']}})
    state=loop.context.analysis_state
    update_requirements(state,load_canonical_history(loop.session_id),loop.messages[-1]["request_id"],[{"op":"add","start":text.index("判断"),"end":len(text),"kind":"gap"}],expected_revision=state.requirement_revision)
    execute(loop,"describe_dataset",{"name":"orders"})
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    statuses={r["status"] for r in loop._accepted_answer["requirement_outcomes"]}
    assert statuses=={"not_computed","evidence_insufficient"}
    assert any(c["target"].get("statistic")=="sum" and c["value"]==180 for c in snap.as_dict()["claims"])
    assert commit(loop,{"role":"assistant"},body) is None
    assert {p["status"] for p in build_workbench_view(state)["pending_findings"]}==statuses


@pytest.mark.parametrize("values,statistic,expected",[([0.051,0.01417],"min",0.01417),([0.051,0.01417],"mean",0.032585),([9007199254740993,9007199254740994],"min",9007199254740993)])
def test_original_description_statistics_do_not_round_or_float_cast_observed_endpoints(engine,values,statistic,expected):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"amount":values}))
    request(loop,"该指标的原统计值",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': statistic}})
    _,result=execute(loop,"describe_dataset",{"name":"orders"})
    value=result["field_statistics"][0]["stats"][statistic]
    assert value==pytest.approx(expected,rel=0,abs=1e-16) if type(expected) is float else value==expected
    if type(expected) is int: assert type(value) is int
    snap=snapshot_for_turn(loop).as_dict();req=snap["requirements"][0]
    owned=[c for c in snap["claims"] if c["id"] in req["claim_ids"]]
    assert len(owned)==1 and owned[0]["value"]==value and type(owned[0]["value"]) is type(value)


@pytest.mark.parametrize("streaming",[False,True])
def test_mixed_consultation_keeps_explicit_result_obligation(engine,monkeypatch,streaming):
    """The nine route labels cannot erase an explicit same-turn calculation."""
    from data_agent.agent.intent import TurnIntent
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    import data_agent.agent.intent as intent
    loop,_=engine
    content="Explain the mean; calculate amount mean on orders"
    mixed=TurnIntent("analysis_consultation","clear","data_loaded","execute","run_analysis",execution_readiness="ready",requested_outputs=[
        {"kind":"knowledge","exact_span":"Explain the mean"},
        {"kind":"result","exact_span":"calculate amount mean on orders",'business_scope':{'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'mean'}}])
    monkeypatch.setattr(intent,"plan_turn_intent",lambda *a,**kw:mixed)
    class MixedClient(AppClient):
        def chat(self,messages,system="",tools=None,**kw):
            from data_agent.llm.client import Response
            from data_agent.agent.publication.runtime import snapshot_for_turn
            if system.startswith("审核数据相关开放片段"):
                audit=json.loads(messages[0]["content"])
                return Response(text=encode({"schema":"publication_audit.v2","snapshot_digest":audit["snapshot_digest"],"draft_digest":audit["draft_digest"],"decisions":[{"part_id":p["part_id"],"disposition":"accept","reason":"scripted mechanism only","evidence_refs":p["requirement_ids"]} for p in audit["parts"]]}))
            if self.called==0: return super().chat(messages,system=system,tools=tools,**kw)
            self.called+=1
            snap=snapshot_for_turn(self.loop);host=snap.as_dict()
            sections=[]
            for req in host["requirements"]:
                parts=([{"kind":"text","purpose":"knowledge","text":"A mean divides a total by the observation count.","claim_refs":[]}] if req["open_purposes"] else [{"kind":"claim","ref":cid} for cid in req["claim_ids"]])
                sections.append({"requirement_ids":[req["id"]],"parts":parts})
            return Response(text=encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":sections}))
    loop.client=MixedClient(loop,"describe_dataset",{"name":"orders"})
    if streaming:
        events=list(loop.stream_turn(content))
        assert not [e for e in events if e["type"]=="error"],events
        body="".join(e["text"] for e in events if e["type"]=="text_delta")
    else: body=loop.run_turn_structured(content).content
    ref=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    accepted=read_answer(loop.session_id,ref)
    assert [o["status"] for o in accepted["requirement_outcomes"]]==["answered","answered"]
    result=next(r for r in accepted["source_snapshot"]["requirements"] if r["text"].startswith("calculate"))
    values=[c["value"] for c in accepted["source_snapshot"]["claims"] if c["id"] in result["claim_ids"]]
    assert values==[15.0] and "15" in body and "A mean" in body
    assert accepted["audit_status"]=="reviewed" and loop.client.called==2


@pytest.mark.parametrize("choice,expected",[("coupon",96),("both",86),("skipped",None),("unconfirmed",None),("changed_data",None)])
@pytest.mark.parametrize("streaming",[False,True])
def test_confirmed_accounting_formula_uses_only_original_group_sums(engine,monkeypatch,choice,expected,streaming):
    import pandas as pd
    from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.session.history import load_canonical_history,load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,cfg=engine
    loop.context.workspace.add("orders",pd.DataFrame({"group":["a"]*6+["b"]*6,"amount":[10]*12,"coupon":[2]*12,"channel":[1]*10+[0]*2}))
    request(loop,"计算账面净收益",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['账面净收益'], 'quantity': 'value'}})
    history=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=history,source_message_ref=history.messages[-1]["request_id"],exact_span="账面净收益",dataset="orders",column="amount",cost_scopes=[["coupon"],["coupon","channel"]])
    assert candidate is not None
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry());service.request(candidate);record=service.checkpoint(loop.session_id)
    response="skipped" if choice=="skipped" else "unconfirmed" if choice=="unconfirmed" else candidate.options[0 if choice=="coupon" else 1].value
    if choice=="changed_data": loop.context.workspace.add("orders",pd.DataFrame({"group":["c"],"amount":[100],"coupon":[2],"channel":[1]}))
    args={"name":"orders","operation":"group_aggregate","group_by":["group"],"aggregations":[{"column":col,"functions":["sum"]} for col in ["amount","coupon","channel"]]}
    loop.client=AppClient(loop,"transform_data",args)
    if streaming:
        events=list(loop.resume_turn_streaming(record.confirmation_id,response,expected_version=record.version,idempotency_key="accounting_choice"))
        errors=[e for e in events if e["type"]=="error"]
        if choice=="changed_data":
            assert errors and "formal_plan_required" in errors[0]["message"]
            assert not any(r["tool_name"]=="transform_data" for r in loop.context.analysis_state.tool_receipts)
        else: assert not errors,events
        body="".join(e["text"] for e in events if e["type"]=="text_delta")
    else: body=loop.resume_turn(record.confirmation_id,response,expected_version=record.version,idempotency_key="accounting_choice").content
    terminal=load_session(loop.session_id)["messages"][-1]
    accepted=read_answer(loop.session_id,terminal["answer_ref"])
    owned=[c for c in accepted["source_snapshot"]["claims"] if c.get("target",{}).get("statistic")=="accounting_net"]
    if expected is None:
        assert not owned and accepted["requirement_outcomes"][0]["status"]!="answered"
    else:
        assert len(owned)==1 and float(owned[0]["value"])==expected
        assert owned[0]["derivation"]["confirmation_id"]==record.confirmation_id
        assert owned[0]["derivation"]["response_id"]=="accounting_choice"
        assert owned[0]["unit"] is None and owned[0]["label"]=="账面净收益"
        assert len(owned[0]["basis_refs"])==2*(2 if choice=="coupon" else 3)
        assert accepted["requirement_outcomes"][0]["status"]=="answered" and str(expected) in body, [m.get("content") for m in loop.messages if m.get("role")=="tool"]
    assert accepted["body"]==body


def test_repeated_accounting_choices_keep_distinct_user_sources(engine):
    import pandas as pd
    from data_agent.agent.confirmation.runtime import build_measurement_mapping_candidate,build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.session.history import load_canonical_history
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.requirements import update_requirements
    loop,cfg=engine
    loop.context.workspace.add("orders",pd.DataFrame({"group":["a","b"],"amount":[60,60],"coupon":[12,12],"channel":[5,5]}))
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry())
    previous=None
    for i,content in enumerate(["首次账面净收益","重新计算账面净收益"]):
        request(loop,content,{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['账面净收益'], 'quantity': 'value'}})
        history=load_canonical_history(loop.session_id);source=history.messages[-1]["request_id"]
        if previous:
            update_requirements(loop.context.analysis_state,history,source,[{"op":"withdraw","start":0,"end":len(content),"kind":"result","target_id":previous}],expected_revision=loop.context.analysis_state.requirement_revision)
        current=next(r for r in loop.context.analysis_state.answer_requirements if r["source_message_ref"]==source and r["lifecycle_status"]=="active")
        previous=current["id"]
        candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="choice"+str(i),workspace=loop.context.workspace,canonical_history=history,source_message_ref=source,exact_span="账面净收益",dataset="orders",column="amount",cost_scopes=[["coupon"],["coupon","channel"]])
        service.request(candidate);version=service.checkpoint(loop.session_id).version
        service.respond(loop.session_id,candidate.confirmation_id,candidate.options[i].value,version,"choice"+str(i))
    execute(loop,"transform_data",{"name":"orders","operation":"group_aggregate","group_by":["group"],"aggregations":[{"column":col,"functions":["sum"]} for col in ["amount","coupon","channel"]]})
    snap=snapshot_for_turn(loop);host=snap.as_dict()
    current_req=next(r for r in host["requirements"] if r["id"]==previous)
    owned=[c for c in host["claims"] if c["id"] in current_req["claim_ids"]]
    assert len(owned)==1 and float(owned[0]["value"])==86
    assert owned[0]["derivation"]["response_id"]=="choice1"
    assert len({c["id"] for c in host["claims"]})==len(host["claims"])


@pytest.mark.parametrize("route,kind,needs_data",[("simple_response","knowledge",False),("knowledge_qa","knowledge",False),("analysis_consultation","knowledge",False),("data_requirement","knowledge",False),("intent_negotiation","knowledge",False),("directed_analysis","result",True),("knowledge_qa","result",True)])
def test_no_data_prompt_preserves_consultation_route(engine,monkeypatch,route,kind,needs_data):
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    loop=AgentLoop(client=object(),session_id="no-data-consultation")
    with use_agent_context(loop.context):
        request(loop,"Explain a method" if kind=="knowledge" else "Compute a current amount",kind=kind)
        loop.context.turn_intent=SimpleNamespace(intent_type=route)
        monkeypatch.setattr(loop,"_build_retrieval_query",lambda *a:"")
        prompt=loop._build_system_prompt()
    assert ("<no_data_recovery>" in prompt) is needs_data


def test_confirmation_record_change_before_commit_preserves_prior_history(engine):
    from dataclasses import replace
    from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.agent.confirmation.models import ConfirmationEvent,ConfirmationOption
    from data_agent.session.history import load_canonical_history
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine
    request(loop,"确认金额后计算记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    history=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=history,source_message_ref=history.messages[-1]["request_id"],exact_span="金额",dataset="orders",column="amount")
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry());service.request(candidate)
    service.respond(loop.session_id,candidate.confirmation_id,"raw",service.checkpoint(loop.session_id).version,"original_choice")
    execute(loop,"describe_dataset",{"name":"orders"})
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    record=service.get(loop.session_id,candidate.confirmation_id)
    changed=replace(record,version=record.version+1,options=record.options+(ConfirmationOption("changed scope","other"),))
    ConfirmationStore(cfg.sessions_resolved,loop.session_id).append(ConfirmationEvent(event_id="changed_scope",confirmation_id=record.confirmation_id,session_id=loop.session_id,event_type="changed",version=changed.version,occurred_at=record.updated_at,record=changed))
    before=load_canonical_history(loop.session_id)
    assert commit(loop,{"role":"assistant"},body)
    assert load_canonical_history(loop.session_id)==before and not loop.context.analysis_state.accepted_answers


@pytest.mark.parametrize("prior_message",[False,True])
@pytest.mark.parametrize("streaming",[False,True])
def test_actual_question_tool_generates_host_accounting_options_and_resumes_same_obligation(engine,monkeypatch,streaming,prior_message):
    import pandas as pd
    from data_agent.tools import interaction  # Register the original question tool in this isolated harness.
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"group":["a","b"],"amount":[60,60],"coupon":[12,12],"channel":[5,5]}))
    content="计算账面净收益"
    intent_for_app(monkeypatch,"result",content,{"datasets":["orders"],"metrics":["账面净收益"],"quantity":"value"})
    mapping={"exact_span":"账面净收益","dataset":"orders","column":"amount","cost_scopes":[["coupon"],["coupon","channel"]]}
    if prior_message:
        from data_agent.session.history import save_session
        loop.messages.append({"role":"user","content":content,"request_id":"msg_prior_accounting"})
        save_session(loop.messages,loop.session_id,extra_meta={"publication_schema":"answer_bindings.v2"},merge_protect=False)
    loop.client=AppClient(loop,"ask_user_question",{"question":"确认账面计算公式","options":[],"measurement_mapping":encode(mapping)})
    if streaming:
        events=list(loop.stream_turn(content))
        assert len([e for e in events if e["type"]=="suspended"])==1, [m.get("content") for m in loop.messages if m.get("role")=="tool"]
        assert not [e for e in events if e["type"]=="text_delta"]
        record=loop._confirmation_runtime().checkpoint(loop.session_id)
    else:
        suspended=loop.run_turn_structured(content)
        assert isinstance(suspended,SuspendedForConfirmation), [m.get("content") for m in loop.messages if m.get("role")=="tool"]
        record=loop._confirmation_runtime().get(loop.session_id,suspended.confirmation_id)
    current_source=next(m["request_id"] for m in reversed(loop.messages) if m.get("role")=="user")
    assert record.resolution_params["measurement_mapping"]["source_message_ref"]==current_source
    assert current_source!="msg_prior_accounting"
    chosen=record.options[1]
    assert json.loads(chosen.value)["cost_columns"]==["coupon","channel"] and "SUM" in chosen.description
    loop.client=AppClient(loop,"transform_data",{"name":"orders","operation":"group_aggregate","group_by":["group"],"aggregations":[{"column":col,"functions":["sum"]} for col in ["amount","coupon","channel"]]})
    if streaming:
        events=list(loop.resume_turn_streaming(record.confirmation_id,chosen.value,expected_version=record.version,idempotency_key="actual_question_choice"))
        assert not [e for e in events if e["type"]=="error"],events
        body="".join(e["text"] for e in events if e["type"]=="text_delta")
    else: body=loop.resume_turn(record.confirmation_id,chosen.value,expected_version=record.version,idempotency_key="actual_question_choice").content
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert answer["body"]==body and "86" in body and answer["requirement_outcomes"][0]["status"]=="answered"
    assert len(loop.context.analysis_state.answer_requirements)==1


@pytest.mark.parametrize("marker,tool,kind",[
    ("B01-DESCRIBE","describe_dataset","result"),
    ("B05-PY","run_python","result"),
    ("B01-ACTION","compare_periods","conditional_action"),
    ("B01-ACTION-MULTI-RISK","compare_periods","conditional_action"),
    ("B01-ACTION-MULTI-NEG","compare_periods","conditional_action"),
])
def test_existing_rehearsal_emits_only_current_draft_and_bounded_audit(engine,marker,tool,kind):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures
    from data_agent.agent.publication.runtime import publication_prompt,publish,commit,read_answer
    from data_agent.agent.publication.contracts import parse_draft
    from data_agent.session.history import load_session
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True)
    _write_fixtures(cfg.workspace_resolved.parent)
    trace=RunTrace(cfg.workspace_resolved.parent)
    client=ScriptedClient(trace); loop.client=client;loop.auxiliary_llm_client=client
    dataset="action_sales" if kind=="conditional_action" else "f_sales"
    request(loop,"【"+marker+"】"+ ("有条件行动建议" if kind=="conditional_action" else "当前原始金额和记录数"),None if kind=="conditional_action" else {"kind":"measurement" if marker=="B01-DESCRIBE" else "table","scope":{"datasets":[dataset],**({"quantity":"rows"} if marker=="B01-DESCRIBE" else {})}},kind=kind)
    for _ in range(8):
        response=client._next(marker,loop.messages,publication_prompt(loop))
        if not response.tool_calls: break
        for call in response.tool_calls:
            execute(loop,call.name,call.arguments)
    else: pytest.fail("rehearsal did not reach a final draft")
    snapshot=loop._publication_runtime[1]
    parsed=parse_draft(response.text,snapshot.digest)
    assert parsed["schema"]=="answer_bindings.v2"
    body,error=publish(loop,response.text)
    assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert answer["body"]==body and answer["source_snapshot"]["claims"]
    if marker=="B01-DESCRIBE":
        assert any(c["label"]=="记录数" and c["value"]==12 for c in answer["source_snapshot"]["claims"])
        assert any(c["value"]==120 for c in answer["source_snapshot"]["claims"])
        assert answer["requirement_outcomes"][0]["status"]=="answered",answer["requirement_outcomes"]
    elif marker=="B05-PY":
        values=[c["value"] for c in answer["source_snapshot"]["claims"] if c["target"]["tool"]=="run_python"]
        assert {"rows":12,"amount_sum":120.0,"date_min":"2026-09-01 00:00:00","date_max":"2026-09-12 00:00:00"} in values
    elif marker=="B01-ACTION":
        assert "否则暂停增加预算并复核" in body
        assert answer["requirement_outcomes"][0]["status"]=="answered"
    elif marker.endswith("RISK"):
        assert "现在必须立即暂停增加预算" not in body
        assert any(t["kind"]=="text" and t["disposition"]=="reject" for t in answer["render_trace"])
    else:
        assert any(i["code"]=="unknown_claim_ref" for i in answer["issues"])
    events=[json.loads(line) for line in trace.path.read_text(encoding="utf-8").splitlines()]
    assert sum(e["event"]=="scripted_semantic_audit" for e in events)<=1
    assert not any(e["event"]=="forbidden_provider_transport" for e in events)


@pytest.mark.parametrize("compressed",[False,True])
def test_current_branch_inherits_chat_and_continues_with_independent_authority(engine,compressed):
    from data_agent.session.history import branch_session,load_session,load_canonical_history,list_branches,save_session
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,require_writable,read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.web.agent_manager import AgentManager
    from data_agent.agent.publication.requirements import project_requirements
    loop,cfg=engine
    request(loop,"计算父会话记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    parent_answer=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    if compressed:
        from data_agent.agent.compact import compact_history,CompactState
        for i in range(12):
            loop.messages.extend([{"role":"user","content":"历史讨论"+str(i),"request_id":"parent_later_"+str(i)},{"role":"assistant","content":"历史说明"}])
        summary=SimpleNamespace(chat=lambda *a,**kw:SimpleNamespace(text="父会话已讨论统计概念。"))
        loop.messages=compact_history(loop.session_id,summary,loop.messages,CompactState())
        save_session(loop.messages,loop.session_id,extra_meta={"publication_schema":"answer_bindings.v2"},merge_protect=False)
    parent_root=cfg.sessions_resolved/loop.session_id
    before={p.relative_to(parent_root).as_posix():p.read_bytes() for p in parent_root.rglob("*") if p.is_file()}
    result=branch_session(loop.session_id,"继续讨论")
    assert result["success"]
    child_id=result["session_id"]
    saved=load_session(child_id)
    assert saved["publication_schema"]=="answer_bindings.v2"
    assert saved["forked_from"]==loop.session_id and saved["data_file"]==""
    require_writable(child_id)
    assert any(b["session_id"]==child_id for b in list_branches(loop.session_id))
    assert not any(m.get("answer_ref") for m in saved["messages"])
    if not compressed:
        inherited=saved["messages"][-1]
        assert inherited["content"]==body and inherited["inherited_answer_ref"]["session_id"]==loop.session_id
        assert inherited["inherited_answer_ref"]["answer_id"]==parent_answer["answer_id"]
    child=AgentManager(client_factory=lambda **kw:object()).get_or_create(child_id)
    state=child.context.analysis_state
    assert not state.accepted_answers and not state.tool_receipts and not state.evidence_records and not state.answer_requirements
    with use_agent_context(child.context):
        assert child.context.workspace.list_datasets()=={}
        request(child,"解释相关与因果的区别",kind="knowledge")
        current=snapshot_for_turn(child);host=current.as_dict()
        assert host["claims"]==[] and host["mode"]=="consultation"
        rid=host["requirements"][0]["id"]
        raw=encode({"schema":"answer_bindings.v2","snapshot_digest":current.digest,"sections":[{"requirement_ids":[rid],"parts":[{"kind":"text","purpose":"knowledge","text":"相关关系不能独自识别因果。","claim_refs":[]}]}]})
        text,error=publish(child,raw);assert error is None and commit(child,{"role":"assistant"},text) is None
        assert read_answer(child_id,load_session(child_id)["messages"][-1]["answer_ref"])["source_snapshot"]["claims"]==[]
        assert load_session(child_id)["forked_from"]==loop.session_id
        if compressed:
            # Copied canonical transcripts preserve chat provenance, not data authority.
            original=loop.context.analysis_state.answer_requirements
            projection=project_requirements(SimpleNamespace(answer_requirements=original),load_canonical_history(child_id),{})
            assert projection[0]["gap"]["status"]=="not_computed"
        import pandas as pd
        child.context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
        request(child,"计算分支记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
        execute(child,"describe_dataset",{"name":"orders"})
        current=snapshot_for_turn(child)
        assert any(c["label"]=="记录数" and c["value"]==1 for c in current.as_dict()["claims"])
    assert before=={p.relative_to(parent_root).as_posix():p.read_bytes() for p in parent_root.rglob("*") if p.is_file()}


def test_branch_cannot_promote_tampered_parent_answer_or_legacy_runtime(engine):
    from data_agent.session.history import branch_session,load_session,save_session
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,require_writable
    loop,cfg=engine
    request(loop,"计算父会话记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    current=snapshot_for_turn(loop);body,error=publish(loop,draft(current));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    ref=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    (cfg.sessions_resolved/loop.session_id/ref["path"]).write_text("tampered",encoding="utf-8")
    result=branch_session(loop.session_id)
    assert not result["success"] and "source" in result["error_type"]
    save_session([{"role":"user","content":"旧咨询"},{"role":"assistant","content":"旧原始答案"}],"old_branch_parent")
    old=branch_session("old_branch_parent")
    assert old["success"] and load_session(old["session_id"])["messages"][-1]["content"]=="旧原始答案"
    with pytest.raises(ValueError):require_writable(old["session_id"])


@pytest.mark.parametrize("streaming",[False,True])
@pytest.mark.parametrize("tool,args",[("describe_dataset",{"name":"orders"}),("run_python",{"code":"get_dataset('orders')['amount'].sum()"})])
def test_pure_consultation_blocks_unrequested_execution_before_registry(engine,monkeypatch,streaming,tool,args):
    from data_agent.tools.registry import registry
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,_=engine
    content="只解释相关与因果，不计算我的数据"
    intent_for_app(monkeypatch,"knowledge",content)
    executed=[]
    original=registry.execute
    def spy(name,parameters):
        executed.append(name)
        return original(name,parameters)
    monkeypatch.setattr(registry,"execute",spy)
    loop.client=AppClient(loop,tool,args)
    if streaming:
        events=list(loop.stream_turn(content))
        assert not [e for e in events if e["type"] in {"error","suspended"}],events
        assert len([e for e in events if e["type"]=="text_delta"])==1
    else:
        assert loop.run_turn_structured(content).content
    assert executed==[], "model suggested an execution, but pure consultation did not authorize it"
    ref=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    answer=read_answer(loop.session_id,ref)
    assert not answer["source_snapshot"]["claims"] and answer["audit_status"]=="not_applicable"
    assert answer["requirement_outcomes"][0]["status"]=="answered"


@pytest.mark.parametrize("case,loaded", [(case,False) for case in ("CONS-01","CONS-01-EN","CONS-02","CONS-02-EN")]
    + [(case,True) for case in ("CONS-01","CONS-01-EN","CONS-02","CONS-02-EN","CONS-03","CONS-04","CONS-05","INTENT-01","INTENT-03")])
def test_rehearsal_consultation_uses_actual_intent_loop_and_current_answer(engine,case,loaded):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures,P4_REQUESTS
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer,snapshot_for_turn,publish,commit
    loop,cfg=engine
    if not loaded:
        loop.context.workspace.remove("orders")
        assert not loop.context.workspace.list_datasets()
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True)
    _write_fixtures(cfg.workspace_resolved.parent)
    trace=RunTrace(cfg.workspace_resolved.parent);client=ScriptedClient(trace)
    loop.client=client;loop.auxiliary_llm_client=client
    if case=="CONS-04":
        request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
        execute(loop,"describe_dataset",{"name":"orders"})
        snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
        assert commit(loop,{"role":"assistant"},body) is None
        prior=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    receipts_before=len(loop.context.analysis_state.tool_receipts)
    text,route,_=P4_REQUESTS[case]
    events=list(loop.stream_turn(f"【{case}】{text}"))
    assert not [e for e in events if e["type"] in {"error","suspended"}],events
    stored=load_session(loop.session_id);ref=stored["messages"][-1]["answer_ref"]
    answer=read_answer(loop.session_id,ref)
    assert answer["body"]=="".join(e["text"] for e in events if e["type"]=="text_delta")
    # The existing clear fast route is retained while auxiliary output spans
    # enrich it. Calculation is a legal data_operation; a missing prior result
    # may be an uncomputed analysis. Assert their delivery/isolation below.
    allowed_routes = {route}
    if case == "INTENT-01": allowed_routes.add("data_operation")
    assert loop.context.turn_intent.intent_type in allowed_routes
    if case.startswith("CONS-"):
        assert len(loop.context.analysis_state.tool_receipts)==receipts_before
        if case=="CONS-04":
            current_req=next(r for r in loop.context.analysis_state.answer_requirements if r["original_text"]==text)
            assert current_req["source_answer_id"]==prior["answer_id"]
            assert any(c["value"]==12 for c in answer["source_snapshot"]["claims"])
        elif case=="CONS-05":
            assert not answer["source_snapshot"]["claims"]
            assert any(o["status"]!="answered" for o in answer["requirement_outcomes"])
        else:
            assert answer["source_snapshot"]["claims"]==[] and answer["audit_status"]=="not_applicable"
            assert all(o["status"]=="answered" for o in answer["requirement_outcomes"])
    elif case=="INTENT-01":
        assert all(o["status"]=="answered" for o in answer["requirement_outcomes"])
        assert any(c["value"]==120 for c in answer["source_snapshot"]["claims"])
    else:
        assert [o["status"] for o in answer["requirement_outcomes"]]==["answered","answered"]
        changes=[c for c in answer["source_snapshot"]["claims"] if c["target"]["tool"]=="compare_periods"]
        assert any(c["value"]==100 for c in changes) and any(c["value"]==120 for c in changes)
        assert any(c["value"]==20 for c in changes)
    logged=[json.loads(line) for line in trace.path.read_text('utf-8').splitlines()]
    assert not any(e["event"]=="forbidden_provider_transport" for e in logged)
    assert sum(e["event"]=="scripted_semantic_audit" for e in logged)<=1


@pytest.mark.parametrize("marker,content,dataset,tool", [
    ("B01-DESCRIBE", "描述当前订单的记录数、amount 原值和日期范围。", "f_sales", "describe_dataset"),
    ("B02", "分析留存序列，保留未知单位和外推缺口。", "ret_a", "curve_fitting"),
    ("B05-PY", "计算当前订单记录数、amount 原值和日期范围。", "f_sales", "run_python"),
    ("B05-PY-NOROW", "计算当前订单原值和日期范围。", "f_sales", "run_python"),
    ("B01-EDGE", "按 channel 计算 amount 的 sum、count、size、nunique，保留缺失值。", "edge_sales", "transform_data"),
])
def test_rehearsal_result_requirement_binds_actual_tool_family(engine,marker,content,dataset,tool):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True)
    _write_fixtures(cfg.workspace_resolved.parent)
    trace=RunTrace(cfg.workspace_resolved.parent);client=ScriptedClient(trace)
    loop.client=client;loop.auxiliary_llm_client=client
    events=list(loop.stream_turn(f"【{marker}】{content}"))
    assert not [e for e in events if e["type"] in {"error","suspended"}],events
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert answer["body"]=="".join(e["text"] for e in events if e["type"]=="text_delta")
    assert [o["status"] for o in answer["requirement_outcomes"]]==["answered"]
    assert any(d["scope"]["datasets"]==[dataset] for d in loop.context.analysis_state.answer_requirements[-1]["necessary_deliveries"])
    accepted={t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    assert any(c["id"] in accepted and c["target"]["dataset"]==dataset and c["target"]["tool"]==tool for c in answer["source_snapshot"]["claims"])


@pytest.mark.parametrize("path,expected",[( ["result_data","inclusive_days"],12),(["result_data","missing_days"],None),(["stdout"],None),(["dataset_reads",0],None)])
def test_actual_python_selected_field_cannot_be_satisfied_by_container_or_metadata(engine,path,expected):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    loop,_=engine
    request(loop,"订单日期天数",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":[path[-1] if len(path)>1 and isinstance(path[-1],str) else "unavailable-field"],"quantity":"value"}})
    request(loop,"订单金额原值",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount_sum'], 'quantity': 'value'}})
    rid,result=execute(loop,"run_python",{"code":"df=get_dataset('orders')\nresult={'amount_sum':int(df['amount'].sum()),'inclusive_days':int((df['day'].max().date()-df['day'].min().date()).days)+1}\nresult"})
    assert result["result_data"]["inclusive_days"]==12
    snap=snapshot_for_turn(loop);host=snap.as_dict()
    selected=host["requirements"][0]
    owned=[c for c in host["claims"] if c["id"] in selected["claim_ids"]]
    if expected is None:
        assert not owned and selected["gap"]["status"]=="not_computed"
    else:
        assert len(owned)==1 and owned[0]["value"]==expected
        assert owned[0]["basis_refs"][0]["receipt_id"]==rid and owned[0]["basis_refs"][0]["result_path"]==path
    assert host["requirements"][1]["claim_ids"] and host["requirements"][1]["gap"] is None
    body,error=publish(loop,draft(snap));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert [o["status"] for o in answer["requirement_outcomes"]]==["not_computed" if expected is None else "answered","answered"]


@pytest.mark.parametrize("path",[[],[True],[False],[-1],[1.5],[None],["x"]*17,[""]])
def test_selected_result_path_validation_is_atomic(engine,path):
    loop,_=engine
    with pytest.raises(ValueError):
        request(loop,"日期天数",{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"value","result_path":path}})
    assert not loop.context.analysis_state.answer_requirements


def test_selected_python_field_rewording_retains_exact_original_receipt(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,_=engine
    request(loop,"计算金额",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount_sum'], 'quantity': 'value'}})
    execute(loop,"run_python",{"code":"{'amount_sum':int(get_dataset('orders')['amount'].sum())}"})
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    original={t["ref"] for t in loop._accepted_answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.publication.runtime import register_request
    text="只保留金额原值重述"
    loop.messages.append({"role":"user","content":text,"request_id":"msg_field_reword"})
    intent=TurnIntent("result_followup","clear","data_loaded","follow_up","answer_directly",requested_outputs=[{"kind":"presentation","exact_span":text}])
    register_request(loop,text,intent);loop.context.turn_intent=intent
    host=snapshot_for_turn(loop).as_dict()
    assert original.issubset({c["id"] for c in host["claims"]})
    assert set(host["requirements"][-1]["claim_ids"])==original


def test_inferred_trend_rehearsal_uses_current_hypothesis_plan_across_reload(engine,monkeypatch):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True)
    _write_fixtures(cfg.workspace_resolved.parent)
    client=ScriptedClient(RunTrace(cfg.workspace_resolved.parent));loop.client=client;loop.auxiliary_llm_client=client
    prompts=["分析 hyp 当前 amount 竞争假设和描述性趋势，保留原测量和错误目标拒绝边界。","更新版本后保留旧关系的失效边界。","重新分析当前版本的 amount 竞争假设和描述性趋势。"]
    plans=[];identities=[]
    for content in prompts:
        events=list(loop.stream_turn("【B04-INFER】"+content))
        assert not [e for e in events if e["type"] in {"error","suspended"}],events
        state=loop.context.analysis_state;plan=(state.analysis_plan or {}).get("id");plans.append(plan)
        assert any(ref["plan_id"]==(plan or plans[0]) and ref["dataset"]=="hyp" for ref in state.hypothesis_sets)
        identities.append(loop.context.workspace.get_data_identity("hyp"))
        accepted=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
        relations=[c for c in accepted["source_snapshot"]["claims"] if c.get("target",{}).get("hypothesis_id")]
        assert all(c["target"]["metric"]=="amount" for c in relations)
        assert all(p["data_identities"]["hyp"]==identities[-1] for c in relations for p in c["basis_refs"])
        assert [c["value"] for c in relations]==(["supported"] if len(plans)==1 else [] if len(plans)==2 else ["refuted"])
        if len(plans)!=2:
            from pathlib import Path
            payload=json.loads(Path(next(ref["artifact_path"] for ref in reversed(state.hypothesis_sets) if ref["plan_id"]==plan and ref["dataset"]=="hyp")).read_text("utf-8"))
            assert any(r.get("reason")=="metric_not_target" for h in payload["hypotheses"] for r in h.get("relation_candidates",[]))
    assert plans[0] and plans[1] is None and plans[2] and plans[2]!=plans[0]
    assert identities[0]!=identities[1] and identities[1]==identities[2]
    assert len([r for r in state.tool_receipts if r["tool_name"]=="analyze_time_series"])==2
    assert len(state.evidence_records)==2


@pytest.mark.parametrize("current,proposed,expected",[("plan_current","plan_current","plan_current"),("plan_current","plan_old",""),("plan_current","foreign_plan",""),("","plan_old","")])
def test_fast_analysis_route_continues_only_exact_current_plan(current,proposed,expected):
    from data_agent.agent.intent import plan_turn_intent
    from data_agent.llm.client import Response
    client=SimpleNamespace(chat=lambda *a,**k:Response(text=json.dumps({"intent_type":"directed_analysis","ambiguities":[],"continuation_of_plan_id":proposed})))
    intent=plan_turn_intent("重新分析当前版本的 amount 竞争假设和描述性趋势。","hyp: 3 rows x 2 cols",llm_client=client,current_plan_id=current,enrich_requested_outputs=True)
    assert intent.clarity=="clear" and intent.continuation_of_plan_id==expected


@pytest.mark.parametrize("fmt",["csv","json","excel"])
def test_actual_data_export_binds_immutable_current_download_and_not_analysis(engine,fmt):
    from pathlib import Path
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    from data_agent.web.app import create_app
    loop,cfg=engine
    request(loop,"只导出当前表",{'kind': 'artifact', 'scope': {'datasets': ['orders']}})
    _,result=execute(loop,"export_data",{"name":"orders","path":"output/current."+{"excel":"xlsx"}.get(fmt,fmt),"fmt":fmt})
    assert result["shape"]=={"rows":12,"columns":2}
    file=cfg.sessions_resolved.parent/result["artifact_path"]
    assert file.is_file() and "sha256:"+hashlib.sha256(file.read_bytes()).hexdigest()==result["sha256"]
    values=pd.read_csv(file) if fmt=="csv" else pd.read_json(file) if fmt=="json" else pd.read_excel(file)
    assert len(values)==12 and values["amount"].sum()==180
    snap=snapshot_for_turn(loop);assert snap.as_dict()["requirements"][0]["artifact_ids"]
    host=snap.as_dict();raw=encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":[host["requirements"][0]["id"]],"parts":[{"kind":"artifact","ref":a["id"]} for a in host["artifacts"]]}]})
    body,error=publish(loop,raw);assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert answer["requirement_outcomes"][0]["status"]=="answered"
    download=create_app().test_client().get("/api/files/"+result["artifact_path"])
    assert download.status_code==200 and download.data==file.read_bytes()
    Path(result["destination"]).write_text("overwritten working export",encoding="utf-8")
    assert read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])["body"]==body
    assert [r["tool_name"] for r in loop.context.analysis_state.tool_receipts]==["export_data"]


@pytest.mark.parametrize("fault",["other_session","traversal","missing_dataset","tampered_download","changed_source"])
def test_data_export_failure_cannot_grant_current_delivery(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine
    request(loop,"只导出当前表",{'kind': 'artifact', 'scope': {'datasets': ['orders']}})
    if fault in {"other_session","traversal","missing_dataset"}:
        from data_agent.tools.registry import registry
        args={"name":"missing" if fault=="missing_dataset" else "orders","path":"sessions/other/output/data.csv" if fault=="other_session" else "../escape.csv" if fault=="traversal" else "output/current.csv"}
        result=registry.execute("export_data",args)
        structured=result.data or json.loads(result.summary)
        assert "error" in structured
        before=list(loop.context.analysis_state.tool_receipts)
        assert not loop._record_turn_tool_result("export_data",result.summary,args,"export-rejected",structured)
        assert loop.context.analysis_state.tool_receipts==before
        assert not snapshot_for_turn(loop).as_dict()["artifacts"]
    else:
        _,result=execute(loop,"export_data",{"name":"orders","path":"output/current.csv"})
        snap=snapshot_for_turn(loop)
        host=snap.as_dict();raw=encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":[host["requirements"][0]["id"]],"parts":[{"kind":"artifact","ref":a["id"]} for a in host["artifacts"]]}]})
        body,error=publish(loop,raw);assert error is None
        if fault=="tampered_download": (cfg.sessions_resolved.parent/result["artifact_path"]).write_text("tampered",encoding="utf-8")
        else:
            import pandas as pd
            loop.context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
        assert commit(loop,{"role":"assistant"},body)
        assert not loop.context.analysis_state.accepted_answers


def test_export_only_rehearsal_uses_current_intent_and_no_analysis(engine):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures,P4_REQUESTS
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True);_write_fixtures(cfg.workspace_resolved.parent)
    client=ScriptedClient(RunTrace(cfg.workspace_resolved.parent));loop.client=client;loop.auxiliary_llm_client=client
    events=list(loop.stream_turn("【INTENT-02】"+P4_REQUESTS["INTENT-02"][0]))
    assert not [e for e in events if e["type"] in {"error","suspended"}],events
    assert loop.context.turn_intent.intent_type=="data_operation"
    assert [r["tool_name"] for r in loop.context.analysis_state.tool_receipts]==["load_data","record_analysis_plan","export_data"]
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert answer["source_snapshot"]["artifacts"] and answer["requirement_outcomes"][0]["status"]=="answered"

