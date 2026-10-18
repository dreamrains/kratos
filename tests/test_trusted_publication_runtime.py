from tests.support.rendered_text import has_numeric_literal
from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: runtime. Shared fixtures have one owner."""
from data_agent.agent.publication.contracts import encode
from pathlib import Path
from tests.test_trusted_publication_semantics import execute
from types import SimpleNamespace
import json
import pytest
from tests.support.publication_runtime import AppClient, _NativeProductModel, draft, intent_for_app, request

"""Application publication contract against actual session/history facilities."""


def test_registered_tool_through_snapshot_publish_cas_and_reload(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop)
    body,error=publish(loop,draft(snapshot))
    assert error is None and "12" in body
    assert commit(loop,{"role":"assistant"},body) is None
    saved=load_session(loop.session_id)
    message=saved["messages"][-1]
    accepted=read_answer(loop.session_id,message["answer_ref"])
    assert accepted["body"]==message["content"]==body
    assert accepted["requirement_outcomes"][0]["status"]=="answered"
    assert loop.context.analysis_state.accepted_answers==[message["answer_ref"]]


@pytest.mark.parametrize("fault",["history_revision","requirement_revision","data_version","plan_identity","save_failure"])
def test_commit_failure_exposes_no_success_and_preserves_prior_history(engine,monkeypatch,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.session.history import load_canonical_history,push_messages
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    if fault=="history_revision": push_messages(loop.session_id,[{"role":"user","content":"新需求","request_id":"new"}])
    if fault=="requirement_revision": loop.context.analysis_state.requirement_revision+=1
    if fault=="plan_identity": loop.context.analysis_state.analysis_plan={"id":"new-plan"}
    if fault=="data_version":
        import pandas as pd
        loop.context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
    if fault=="save_failure":
        import data_agent.session.history as store
        monkeypatch.setattr(store,"save_session",lambda *a,**kw: (_ for _ in ()).throw(OSError("injected save failure")))
    before=load_canonical_history(loop.session_id)
    assert commit(loop,{"role":"assistant"},body)
    assert load_canonical_history(loop.session_id).messages==before.messages
    assert loop.context.analysis_state.accepted_answers==[]


def test_pure_knowledge_remains_empty_facts_with_loaded_data(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    execute(loop,"describe_dataset",{"name":"orders"})
    request(loop,"什么是回归分析？",kind="knowledge")
    snapshot=snapshot_for_turn(loop)
    assert snapshot.as_dict()["claims"]==[]
    rid=snapshot.as_dict()["requirements"][0]["id"]
    body,error=publish(loop,encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,"sections":[{"requirement_ids":[rid],"parts":[{"kind":"text","purpose":"knowledge","text":"回归描述变量间的条件关系，不证明因果。","claim_refs":[]}]}]}))
    assert error is None and "回归" in body and loop._accepted_answer["audit_status"]=="not_applicable"


def test_requirement_original_source_survives_actual_compaction_and_tamper_is_local(engine):
    from data_agent.agent.compact import compact_history,CompactState
    from data_agent.session.history import save_session,load_canonical_history
    from data_agent.agent.publication.requirements import project_requirements
    loop,cfg=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    for i in range(12):
        loop.messages.extend([{"role":"assistant","content":"已说明"},{"role":"user","content":"后续咨询"+str(i),"request_id":"later_"+str(i)}])
    fake=SimpleNamespace(chat=lambda *a,**kw:SimpleNamespace(text="已讨论方法，无新结论。"))
    compacted=compact_history(loop.session_id,fake,loop.messages,CompactState())
    save_session(compacted,loop.session_id,merge_protect=False)
    projected=project_requirements(loop.context.analysis_state,load_canonical_history(loop.session_id),{})
    assert projected[0]["gap"]["status"]=="not_computed"
    reference=compacted[0]["canonical_transcript"]
    archive=cfg.sessions_resolved/loop.session_id/"transcripts"/reference["filename"]
    archive.write_text("tampered",encoding="utf-8")
    projected=project_requirements(loop.context.analysis_state,load_canonical_history(loop.session_id),{})
    assert projected[0]["gap"]["status"]=="evidence_insufficient"


@pytest.mark.parametrize("streaming",[False,True])
@pytest.mark.parametrize("kind",["knowledge","result"])
def test_actual_sync_stream_terminal_owns_same_saved_answer_and_export(engine,monkeypatch,streaming,kind):
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    from data_agent.agent.workbench_view import build_workbench_view
    from data_agent.session.public_messages import assistant_replies
    loop,cfg=engine
    content="什么是回归分析？" if kind=="knowledge" else "计算当前记录数"
    scope=None if kind=="knowledge" else {"datasets":["orders"],"quantity":"rows"}
    intent_for_app(monkeypatch,kind,content,scope)
    loop.client=AppClient(loop,None if kind=="knowledge" else "describe_dataset",{"name":"orders"})
    if streaming:
        events=list(loop.stream_turn(content))
        assert not [e for e in events if e["type"] in {"error","suspended"}],events
        body="".join(e["text"] for e in events if e["type"]=="text_delta")
    else:
        body=loop.run_turn_structured(content).content
    stored=load_session(loop.session_id)
    terminal=stored["messages"][-1]
    assert terminal["content"]==body
    assert "answer_ref" in terminal,body
    accepted=read_answer(loop.session_id,terminal["answer_ref"])
    assert accepted["body"]==body and accepted["requirement_outcomes"][0]["status"]=="answered"
    assert loop.client.called==(1 if kind=="knowledge" else 2)
    assert accepted["audit_status"]=="not_applicable"
    replies=assistant_replies(stored["messages"],loop.session_id)
    result=export_assistant_reply(loop.session_id,body,reply_id=replies[-1]["reply_id"])
    assert result["status"]=="exported",result
    path=cfg.sessions_resolved/loop.session_id/"reports"/result["artifact_path"].split("/")[-1]
    assert accepted["answer_id"] in path.read_text(encoding="utf-8") and body in path.read_text(encoding="utf-8")
    view=build_workbench_view(loop.context.analysis_state)
    assert {c["id"] for c in view["verified_conclusions"]}=={t["ref"] for t in accepted["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}


def test_old_session_is_readonly_at_api_manager_and_direct_loop(engine):
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import save_session,load_canonical_history
    from data_agent.agent.publication.runtime import ReadOnlySessionError
    loop,_=engine
    save_session([{"role":"user","content":"原问题"},{"role":"assistant","content":"原回答"}],loop.session_id,merge_protect=False)
    before=load_canonical_history(loop.session_id)
    manager=AgentManager(client_factory=lambda **kw: (_ for _ in ()).throw(AssertionError("No client created for old session")))
    with pytest.raises(ReadOnlySessionError): manager.get_or_create(loop.session_id)
    with pytest.raises(ReadOnlySessionError): loop.run_turn_structured("继续")
    app=create_app();app.config["agent_manager"]=manager
    with app.test_client() as client:
        response=client.get("/api/sessions/"+loop.session_id)
        assert response.status_code==200 and response.json["read_only"]
        response=client.post("/api/chat",json={"session_id":loop.session_id,"message":"继续"})
        assert response.status_code==409 and response.json["error_type"]=="legacy_session_readonly"
    assert load_canonical_history(loop.session_id)==before


def test_repeated_commit_is_one_terminal_one_reference(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.session.history import load_canonical_history
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    first=load_canonical_history(loop.session_id)
    assert commit(loop,{"role":"assistant"},body) is None
    assert load_canonical_history(loop.session_id)==first and len(loop.context.analysis_state.accepted_answers)==1


def test_group_comparison_preserves_all_groups_including_new_group(engine):
    import pandas as pd
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":pd.to_datetime(["2026-09-01"]*4+["2026-09-07"]*5),"group":["A","B","C","D","A","B","C","D","NEW"],"amount":[1,2,3,999,2,4,6,1998,8]}))
    rid,result=execute(loop,"compare_periods",{"name":"orders","date_col":"day","metrics":"amount","dimensions":"group","period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"})
    facts=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    assert len(result["comparisons"])==5 and len([c for c in facts if c.get("target",{}).get("metric")=="amount"])==20
    assert next(row for row in result["comparisons"] if row["dimension"]=="NEW")["amount"]["exact_aggregates"]=={"a":None,"b":8,"diff":None}


@pytest.mark.parametrize("response,unit,shown",[("fraction","proportion","10%"),("percentage_points","percent","0.1%"),("skipped",None,"单位未知")])
def test_actual_curve_points_use_only_current_durable_scale(engine,response,unit,shown):
    from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.session.history import load_canonical_history
    from data_agent.agent.publication.native import resolve_native_claims
    from data_agent.agent.publication.renderer import claim_text
    import pandas as pd
    loop,cfg=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":range(1,8),"retention":[.55,.42,.31,.24,.18,.13,.1]}))
    request(loop,"解释留存序列",{'kind': 'series', 'scope': {'datasets': ['orders'], 'metrics': ['retention']}})
    current=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=current,source_message_ref=current.messages[-1]["request_id"],exact_span="留存序列",dataset="orders",column="retention",x_column="day",x_start=1,x_end=7)
    assert candidate is not None
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry())
    service.request(candidate);version=service.checkpoint(loop.session_id).version
    if response=="skipped": service.skip(loop.session_id,candidate.confirmation_id,version,"scale_skip")
    else: service.respond(loop.session_id,candidate.confirmation_id,response,version,"scale_answer")
    rid,_=execute(loop,"curve_fitting",{"name":"orders","x_col":"day","y_col":"retention"})
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    point=next(c for c in claims if c["basis_refs"][0]["result_path"]==["points",6,"y"])
    assert point["value"]==.1 and point["unit"]==unit and shown in claim_text(point)
    loop.context.workspace.add("orders",pd.DataFrame({"day":range(1,8),"retention":[.5]*7}))
    with pytest.raises(ValueError): resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("streaming",[False,True])
@pytest.mark.parametrize("answer",["raw","skipped","cancelled"])
def test_actual_business_confirmation_resume_publishes_once_and_replay_does_not_execute(engine,monkeypatch,streaming,answer):
    from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.session.history import load_canonical_history,load_session
    loop,cfg=engine
    request(loop,"确认金额口径并计算记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    current=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=current,source_message_ref=current.messages[-1]["request_id"],exact_span="金额口径",dataset="orders",column="amount")
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry())
    service.request(candidate);record=service.checkpoint(loop.session_id)
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"})
    loop.context.turn_intent=SimpleNamespace(intent_type="data_operation")
    def resume(response=answer,key="business_answer"):
        if streaming:
            events=list(loop.resume_turn_streaming(record.confirmation_id,response,expected_version=record.version,idempotency_key=key))
            assert not [e for e in events if e["type"]=="error"],events
            return "".join(e["text"] for e in events if e["type"]=="text_delta")
        return loop.resume_turn(record.confirmation_id,response,expected_version=record.version,idempotency_key=key).content
    body=resume()
    message=load_session(loop.session_id)["messages"][-1]
    assert message["content"]==body and message.get("answer_ref"),body
    saved=load_canonical_history(loop.session_id)
    calls=loop.client.called
    assert resume()==body and loop.client.called==calls and load_canonical_history(loop.session_id)==saved
    # A different operation is validated by the same confirmation kernel, never cached as success.
    if not streaming:
        assert resume("unconfirmed","different_answer").startswith("Error:")
        assert loop.client.called==calls and load_canonical_history(loop.session_id)==saved


def test_actual_chart_receipt_binds_artifact_and_missing_file_fails_commit(engine,monkeypatch):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.session.history import load_canonical_history
    import plotly.graph_objects as go
    monkeypatch.setattr(go.Figure,"to_image",lambda *a,**kw: (_ for _ in ()).throw(RuntimeError("first static failure")))
    loop,cfg=engine
    request(loop,"画当前金额趋势",{'kind': 'chart', 'scope': {'datasets': ['orders']}},kind="result")
    rid,result=execute(loop,"create_chart",{"data":"orders","chart_type":"line","x_col":"day","y_col":"amount","purpose":"exploratory"})
    snapshot=snapshot_for_turn(loop);host=snapshot.as_dict()
    assert len(host["artifacts"])==1 and host["requirements"][0]["artifact_ids"]==[host["artifacts"][0]["id"]]
    body,error=publish(loop,draft(snapshot));assert error is None and "charts/" in body
    before=load_canonical_history(loop.session_id)
    artifact=cfg.sessions_resolved/loop.session_id/host["artifacts"][0]["path"]
    artifact.unlink()
    assert commit(loop,{"role":"assistant"},body)
    assert load_canonical_history(loop.session_id)==before and loop.context.analysis_state.accepted_answers==[]


def test_forecast_status_without_forecast_does_not_complete_requirement(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    request(loop,"预测未来三期金额",{'kind': 'forecast', 'scope': {'datasets': ['orders'], 'metrics': ['amount']}})
    execute(loop,"forecast",{"name":"orders","target_col":"amount","date_col":"day","periods":3})
    snapshot=snapshot_for_turn(loop)
    body,error=publish(loop,draft(snapshot));assert error is None
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="evidence_insufficient"
    assert "实际预测序列" in body


def test_different_result_goals_cannot_share_one_identical_candidate_mapping(engine):
    from data_agent.agent.publication.requirements import update_requirements,bind_requirements,project_requirements
    from tests.test_trusted_publication_semantics import history,source_ref,change
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine
    # The blanket original-text conflict rule is retired. Independent goals
    # must each match their actual delivery, never infer equivalence from text.
    content="金额均值和最大值"
    scope={"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}
    state=loop.context.analysis_state
    update_requirements(state,history(content),source_ref(content),[change(content,"金额均值",business_scope=scope),change(content,"最大值",business_scope=dict(scope,quantity="max"))],expected_revision=0)
    from tests.support.plan_inputs import declare_goal_deliveries
    declare_goal_deliveries(loop,[(r["id"],"measurement",r["business_scope"]) for r in state.answer_requirements])
    rid,_=execute(loop,"describe_dataset",{"name":"orders"})
    facts=[c for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid) if c.get("target",{}).get("statistic")!="max"]
    projected=project_requirements(state,history(content),bind_requirements(state,facts))
    assert projected[0]["claim_ids"] and projected[0]["gap"] is None
    assert not projected[1]["claim_ids"] and projected[1]["gap"]["status"]=="not_computed"


def test_rewording_uses_exact_original_answer_and_its_current_receipts(engine,monkeypatch):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,register_request
    from data_agent.agent.intent import TurnIntent
    loop,_=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    original=loop._accepted_answer
    text="给业务同事简短解释"
    loop.messages.append({"role":"user","content":text,"request_id":"reword_current"})
    intent=TurnIntent("result_followup","clear","data_loaded","follow_up","answer_directly",requested_outputs=[{"kind":"presentation","exact_span":text}])
    register_request(loop,text,intent);loop.context.turn_intent=intent
    new=snapshot_for_turn(loop).as_dict()
    req=next(r for r in new["requirements"] if r["text"]==text)
    assert set(req["claim_ids"])=={t["ref"] for t in original["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    assert loop.context.analysis_state.answer_requirements[-1]["source_answer_id"]==original["answer_id"]
    # Deleting only the referenced accepted object cannot choose another latest answer.
    ref=loop.messages[-2]["answer_ref"]
    (loop._publication_runtime[1].as_dict())
    from data_agent.config import get_config
    (get_config().sessions_resolved/loop.session_id/ref["path"]).unlink()
    new=snapshot_for_turn(loop).as_dict()
    req=next(r for r in new["requirements"] if r["text"]==text)
    assert req["gap"]["status"]=="evidence_insufficient"


def test_workbench_api_after_restart_reads_same_answer_and_original_saved_data(engine,monkeypatch):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.web.app import create_app
    loop,cfg=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    app=create_app()
    # Request under another context is the same no-loop-on-server-restart path.
    from data_agent.agent.context import AgentContext,use_agent_context
    from data_agent.session.workspace import Workspace
    with use_agent_context(AgentContext(session_id="other",workspace=Workspace())):
        with app.test_client() as client:
            response=client.get("/api/sessions/"+loop.session_id+"/trust")
            assert response.status_code==200,response.json
            assert {c["id"] for c in response.json["workbench"]["verified_conclusions"]}=={t["ref"] for t in loop._accepted_answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
            data=cfg.sessions_resolved/loop.session_id/"data"/"orders.parquet"
            if not data.exists(): data=data.with_suffix(".pkl")
            data.unlink()
            response=client.get("/api/sessions/"+loop.session_id+"/trust")
            assert response.json["workbench"]["verified_total"]==0


def test_workbench_invalidates_only_claims_using_changed_source(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.agent.workbench_view import build_workbench_view
    import pandas as pd
    loop,_=engine
    loop.context.workspace.add("independent",pd.DataFrame({"value":[1,2,3]}))
    request(loop,"计算两个来源各自的记录数",[{"kind":"measurement","scope":{"datasets":[n],"quantity":"rows"}} for n in ["orders","independent"]])
    execute(loop,"describe_dataset",{"name":"orders"})
    execute(loop,"describe_dataset",{"name":"independent"})
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    initial=build_workbench_view(loop.context.analysis_state)
    independent={c["id"] for c in initial["verified_conclusions"] if c["dataset"]=="independent"}
    orders={c["id"] for c in initial["verified_conclusions"] if c["dataset"]=="orders"}
    assert independent and orders
    loop.context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
    view=build_workbench_view(loop.context.analysis_state)
    assert {c["id"] for c in view["verified_conclusions"]}==independent
    assert {r["id"] for r in view["pending_findings"] if r["status"]=="stale"}==orders


def test_curve_scale_original_confirmation_survives_compaction(engine):
    from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.agent.compact import compact_history,CompactState
    from data_agent.session.history import load_canonical_history,save_session
    from data_agent.agent.publication.native import resolve_native_claims
    import pandas as pd
    loop,cfg=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":range(1,8),"retention":[.55,.42,.31,.24,.18,.13,.1]}))
    request(loop,"解释留存序列",{'kind': 'series', 'scope': {'datasets': ['orders'], 'metrics': ['retention']}})
    current=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=current,source_message_ref=current.messages[-1]["request_id"],exact_span="留存序列",dataset="orders",column="retention",x_column="day",x_start=1,x_end=7)
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry());service.request(candidate)
    service.respond(loop.session_id,candidate.confirmation_id,"fraction",service.checkpoint(loop.session_id).version,"scale_answer")
    for i in range(12): loop.messages.extend([{"role":"assistant","content":"已说明"},{"role":"user","content":"后续咨询"+str(i),"request_id":"later_"+str(i)}])
    compacted=compact_history(loop.session_id,SimpleNamespace(chat=lambda *a,**kw:SimpleNamespace(text="只保留方法摘要。")),loop.messages,CompactState())
    save_session(compacted,loop.session_id,extra_meta={"publication_schema":"answer_bindings.v2"},merge_protect=False)
    loop.messages[:]=compacted;loop._last_jsonl_idx=len(compacted)
    rid,_=execute(loop,"curve_fitting",{"name":"orders","x_col":"day","y_col":"retention"})
    point=next(c for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid) if c["basis_refs"][0]["result_path"]==["points",6,"y"])
    assert point["unit"]=="proportion" and point["value"]==.1
    archive=cfg.sessions_resolved/loop.session_id/"transcripts"/compacted[0]["canonical_transcript"]["filename"]
    archive.write_text("tampered",encoding="utf-8")
    point=next(c for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid) if c["basis_refs"][0]["result_path"]==["points",6,"y"])
    assert point["unit"] is None and point["value"]==.1


@pytest.mark.parametrize("fault",[None,"save_failure"])
def test_actual_http_sse_terminal_agrees_with_accepted_body_and_durable_run(engine,monkeypatch,fault):
    from data_agent.web.app import create_app
    from data_agent.web.run_state import RunStates
    from data_agent.session.history import load_session
    loop,_=engine
    content="Compute current row count"
    intent_for_app(monkeypatch,"result",content,{"datasets":["orders"],"quantity":"rows"})
    class IntermediateClient(AppClient):
        def chat(self,*args,**kwargs):
            response=super().chat(*args,**kwargs)
            if response.has_tool_calls: response.text="Unaccepted intermediate assertion: 999 rows."
            return response
    loop.client=IntermediateClient(loop,"describe_dataset",{"name":"orders"})
    if fault:
        import data_agent.session.history as store
        original=store.commit_accepted_answer
        def fail(*a,**kw): raise OSError("injected durable commit failure")
        monkeypatch.setattr(store,"commit_accepted_answer",fail)
    runs=RunStates()
    manager=SimpleNamespace(get_or_create=lambda **kwargs:loop,runs=runs)
    app=create_app();app.config["agent_manager"]=manager
    with app.test_client() as client:
        response=client.post("/api/chat",json={"session_id":loop.session_id,"message":content})
        assert response.status_code==200
        events=[]
        for block in response.get_data(as_text=True).split("\n\n"):
            if block.startswith("event:"):
                event,data=block.split("\ndata: ",1)
                events.append((event[7:],json.loads(data)))
    terminals=[data for event,data in events if event=="turn_end"]
    assert len(terminals)==1 and runs.snapshot(loop.session_id)["turn_id"]==terminals[0]["turn_id"]
    body="".join(data["text"] for event,data in events if event=="text_delta")
    assert not has_numeric_literal(body, '999') and "answer_bindings.v2" not in body
    assert terminals[0]["status"]==runs.snapshot(loop.session_id)["status"]==("failed" if fault else "completed")
    saved=load_session(loop.session_id)["messages"]
    if fault:
        assert body=="" and loop.context.analysis_state.accepted_answers==[]
        assert not [m for m in saved if m.get("answer_ref")]
    else:
        terminal=next(m for m in reversed(saved) if m.get("answer_ref"))
        assert terminal["content"]==body==terminals[0]["reply_content"]
        assert len(loop.context.analysis_state.accepted_answers)==1


def test_pure_consultation_after_accepted_analysis_keeps_old_answer_without_reopening_it(engine,monkeypatch):
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    loop,_=engine
    first="Compute current row count"
    intent_for_app(monkeypatch,"result",first,{"datasets":["orders"],"quantity":"rows"})
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"})
    original=loop.run_turn_structured(first).content
    first_ref=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    current="Explain regression as general knowledge"
    intent_for_app(monkeypatch,"knowledge",current)
    loop.client=AppClient(loop)
    response=loop.run_turn_structured(current).content
    ref=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    accepted=read_answer(loop.session_id,ref)
    assert accepted["source_snapshot"]["claims"]==[] and len(accepted["requirement_outcomes"])==1
    assert accepted["requirement_outcomes"][0]["status"]=="answered"
    assert accepted["audit_status"]=="not_applicable" and loop.client.called==1
    assert read_answer(loop.session_id,first_ref)["body"]==original
    assert first not in response and len(loop.context.analysis_state.answer_requirements)==2


def test_actual_requirement_withdrawal_publishes_one_terminal_without_reviving_old_values(engine,monkeypatch):
    from data_agent.agent.intent import TurnIntent
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    import data_agent.agent.intent as intent
    loop,_=engine
    first="Compute current row count"
    intent_for_app(monkeypatch,"result",first,{"datasets":["orders"],"quantity":"rows"})
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"})
    loop.run_turn_structured(first)
    rid=loop.context.analysis_state.answer_requirements[0]["id"]
    current="Withdraw row count requirement"
    withdrawal=TurnIntent("data_operation","clear","data_loaded","execute","execute_operation",execution_readiness="ready",requested_outputs=[{"kind":"result","op":"withdraw","target_id":rid,"exact_span":current}])
    monkeypatch.setattr(intent,"plan_turn_intent",lambda *a,**kw:withdrawal)
    loop.client=AppClient(loop)
    events=list(loop.stream_turn(current))
    assert not [e for e in events if e["type"]=="error"],events
    terminal=load_session(loop.session_id)["messages"][-1]
    accepted=read_answer(loop.session_id,terminal["answer_ref"])
    assert accepted["body"] and accepted["body"]=="".join(e["text"] for e in events if e["type"]=="text_delta")
    assert accepted["source_snapshot"]["claims"]==[] and accepted["requirement_outcomes"][0]["status"]=="withdrawn"
    assert loop.context.analysis_state.answer_requirements[0]["lifecycle_status"]=="withdrawn"


@pytest.mark.parametrize("statistic,expected",[("mean",15.0),("max",20),("profit",None)])
def test_describe_statistics_keep_exact_field_identity_and_do_not_invent_other_statistics(engine,statistic,expected):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    if expected is None:
        with pytest.raises(ValueError):request(loop,"请求 amount 的 "+statistic,{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":statistic}})
        assert not loop.context.analysis_state.answer_requirements
        return
    request(loop,"请求 amount 的 "+statistic,{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': statistic}})
    _,original=execute(loop,"describe_dataset",{"name":"orders"})
    snap=snapshot_for_turn(loop);host=snap.as_dict()
    req=host["requirements"][0]
    owned=[c for c in host["claims"] if c["id"] in req["claim_ids"]]
    body,error=publish(loop,draft(snap))
    assert error is None
    if expected is None:
        assert not owned and loop._accepted_answer["requirement_outcomes"][0]["status"]!="answered"
    else:
        assert len(owned)==1 and owned[0]["value"]==expected
        assert owned[0]["basis_refs"][0]["result_path"]==["field_statistics",1,"stats",statistic]
        assert original["field_statistics"][1]["stats"][statistic]==expected
        assert owned[0]["unit"] is None


@pytest.mark.parametrize("status",["supported","inconclusive","causal","old_version","precommit_artifact","postcommit_artifact"])
def test_requested_hypothesis_state_and_gap_are_public_and_cannot_be_replaced_by_slope(engine,status):
    import pandas as pd
    from pathlib import Path
    from data_agent.agent.hypotheses import persist_hypothesis_set
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.agent.workbench_view import build_workbench_view
    loop,_=engine
    request(loop,"检验当前假设 h1",{'kind': 'hypothesis', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'hypothesis_ids': ['h1']}})
    rid,result=execute(loop,"analyze_time_series",{"name":"orders","date_col":"day","value_col":"amount"})
    receipt=loop.context.analysis_state.tool_receipts[-1]
    state=loop.context.analysis_state
    plan_id=state.analysis_plan["id"]
    hypothesis={"id":"hs1","plan_id":plan_id,"dataset":"orders","hypotheses":[{"id":"h1","claim":"amount changes","claim_type":"causal" if status=="causal" else "descriptive","status":"inconclusive","verification_level":"verifiable","decision_rule":{"predicate":"changed","metrics":["amount"]}}]}
    state.hypothesis_sets=[persist_hypothesis_set(loop.session_id,hypothesis)]
    state.evidence_records=[{"id":"ev1","plan_id":plan_id,"dataset":"orders","claim":"candidate wording","tool_receipt_ids":[rid],"result_bindings":[{"receipt_id":rid,"result_sha256":receipt["structured_result_sha256"],"data_identities":receipt["data_identities"]}]}] if status!="inconclusive" else []
    if status=="old_version": loop.context.workspace.add("orders",pd.DataFrame({"amount":[1,1]}))
    snap=snapshot_for_turn(loop);req=snap.as_dict()["requirements"][0]
    body,error=publish(loop,draft(snap));assert error is None
    accepted=loop._accepted_answer
    if status in {"supported","precommit_artifact","postcommit_artifact"}:
        owned=[c for c in snap.as_dict()["claims"] if c["id"] in req["claim_ids"]]
        assert len(owned)==1 and owned[0]["value"]=="supported" and "支持" in body
        assert accepted["requirement_outcomes"][0]["status"]=="answered"
    else:
        assert not req["claim_ids"] and req["gap"]["status"]=="evidence_insufficient"
        assert accepted["requirement_outcomes"][0]["status"]=="evidence_insufficient" and req["gap"]["reason"] in body
    artifact=Path(state.hypothesis_sets[0]["artifact_path"])
    if status=="precommit_artifact":
        artifact.write_text("{}",encoding="utf-8")
        assert commit(loop,{"role":"assistant"},body) and not state.accepted_answers
        return
    assert commit(loop,{"role":"assistant"},body) is None
    if status=="postcommit_artifact": artifact.write_text("{}",encoding="utf-8")
    view=build_workbench_view(state)
    if status=="postcommit_artifact":
        hypothesis_ids={c["id"] for c in snap.as_dict()["claims"] if c.get("target",{}).get("hypothesis_id")=="h1"}
        assert hypothesis_ids and hypothesis_ids.isdisjoint({c["id"] for c in view["verified_conclusions"]})
        assert hypothesis_ids.issubset({p["id"] for p in view["pending_findings"] if p["status"]=="stale"})
    elif status!="supported": assert any(p["status"]=="evidence_insufficient" and p["gap"]==req["gap"]["reason"] for p in view["pending_findings"])


def _s3_distribution_id_save(name,value):
 import os
 from data_agent.config import get_config
 root=Path(os.environ.get('DATA_AGENT_S3_DISTRIBUTION_ID_EVIDENCE',str(get_config().sessions_resolved/'distribution_id_evidence')))
 root.mkdir(parents=True,exist_ok=True)
 with (root/(name+'.json')).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,default=str)

