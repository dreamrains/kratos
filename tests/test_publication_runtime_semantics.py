from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: semantics. Shared fixtures have one owner."""
from copy import deepcopy
from data_agent.agent.publication.contracts import encode
from tests.test_trusted_publication_semantics import execute
from types import SimpleNamespace
import json
import pytest
from tests.support.publication_runtime import AppClient, draft, intent_for_app, request

@pytest.mark.parametrize("marker",["INTENT-04","INTENT-04-REORDER"])
def test_original_nine_card_outputs_keep_eight_measurements_one_missing_denominator_and_order(engine,tmp_path,marker):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures,P4_REQUESTS,P4_CARD_METRICS
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True);_write_fixtures(cfg.workspace_resolved.parent)
    client=ScriptedClient(RunTrace(cfg.workspace_resolved.parent));loop.client=client;loop.auxiliary_llm_client=client
    events=list(loop.stream_turn(f"【{marker}】"+P4_REQUESTS[marker][0]))
    assert not [e for e in events if e["type"] in {"error","suspended"}],events
    accepted=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    reqs=accepted["source_snapshot"]["requirements"]
    claims={c["id"]:c for c in accepted["source_snapshot"]["claims"]}
    outcomes={o["requirement_id"]:o for o in accepted["requirement_outcomes"]}
    expected={"最终收益":124.0,"复购率":2/3,"购买偏好":{"A":50.0,"B":50.0},"付费频次":{"u1":2,"u2":1,"u3":2},"人均付费金额":100/3,"日均付费金额":100/3,"单次付费金额":20.0,"金额区间分布":{"[0,20)":2,"[20,40)":3}}
    metric_reqs=[r for r in reqs if r["text"] in P4_CARD_METRICS]
    assert [r["text"] for r in metric_reqs]==sorted(P4_CARD_METRICS,key=P4_REQUESTS[marker][0].index)
    for req in metric_reqs:
        if req["text"]=="付费ARPU":
            assert not req["claim_ids"] and outcomes[req["id"]]["status"]=="not_computed"
        else:
            assert outcomes[req["id"]]["status"]=="answered",(req,outcomes,[m.get("content") for m in loop.messages if m.get("role")=="tool"])
            assert len(req["claim_ids"])==1
            claim=claims[req["claim_ids"][0]]
            assert claim["value"]==expected[req["text"]]
            assert claim["basis_refs"][0]["result_path"]==["result_data",req["text"]]
    effect=next(r for r in reqs if r["text"]=="判断连续付费是否因省钱卡刺激提升")
    assert not effect["claim_ids"] and outcomes[effect["id"]]["status"]=="evidence_insufficient"
    assert set(loop.context.workspace.list_datasets()) >= {"card_users","card_coupons","card_before","card_after"}
    assert [r["tool_name"] for r in loop.context.analysis_state.tool_receipts]==["load_data"]*4+["record_analysis_plan","run_python"]
    # Independent original method obligations; a fixed model is only a channel oracle.
    expected_methods={'最终收益':'card_after.amount合计+card_users.card_amount合计-card_coupons.coupon_cost合计',
        '复购率':'至少两笔支付的user_id数/card_users中不同user_id数','购买偏好':'按category汇总card_after.amount',
        '付费频次':'按user_id计card_after支付记录数','付费ARPU':'当前缺全体有效用户分母',
        '人均付费金额':'支付额/当前不同付费user_id数','日均付费金额':'最大与最小支付日期相差天数加1（含首尾）',
        '单次付费金额':'支付额/支付记录数','金额区间分布':'[0,20)、[20,40)统计支付记录数'}
    for metric,method in expected_methods.items():assert metric in accepted['body'] and method in accepted['body']
    assert '第一种顺序' not in accepted['body'] and '无对照不能证明省钱卡刺激效果' in accepted['body']
    message=next(m for m in reversed(load_session(loop.session_id)['messages']) if m.get('answer_ref'))
    from data_agent.tools.report import export_assistant_reply
    exported=export_assistant_reply(loop.session_id,accepted['body'],'md',reply_id=message['reply_id'])
    assert exported['status']=='exported'
    md=cfg.sessions_resolved/loop.session_id/'reports'/exported['artifact_path'].split('/')[-1]
    assert accepted['body'] in md.read_text(encoding='utf-8')
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    app=create_app();app.config['agent_manager']=AgentManager(client_factory=lambda **kw:object(),auxiliary_client_factory=lambda:object())
    with app.test_client() as http:cold=http.get('/api/sessions/'+loop.session_id).get_json()
    assert any(m.get('answer_ref')==message['answer_ref'] and m['content']==accepted['body'] for m in cold['messages'])
    assert read_answer(loop.session_id,message['answer_ref'])==accepted
    (tmp_path/'nine-original-methods-local.json').write_text(json.dumps(dict(answer=accepted,expected_methods=expected_methods,cold=cold,export=exported,Provider=0,natural_semantics='unassessed'),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize("choice,net",[(0,96),(1,86),(None,None)])
def test_rehearsal_accounting_uses_host_cost_options_actual_sums_and_skip_gap(engine,choice,net):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures,P4_REQUESTS
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True);_write_fixtures(cfg.workspace_resolved.parent)
    client=ScriptedClient(RunTrace(cfg.workspace_resolved.parent));loop.client=client;loop.auxiliary_llm_client=client
    events=list(loop.stream_turn("【M06-TYPED】"+P4_REQUESTS["M06-TYPED"][0]))
    assert len([e for e in events if e["type"]=="suspended"])==1,events
    record=loop._confirmation_runtime().checkpoint(loop.session_id)
    assert [json.loads(o.value)["cost_columns"] for o in record.options if o.value!="unconfirmed"]==[["coupon_cost"],["coupon_cost","channel_cost"]]
    assert record.resolution_params["measurement_mapping"]["dataset"]=="ic_promo"
    value=record.options[choice].value if choice is not None else "skipped"
    events=list(loop.resume_turn_streaming(record.confirmation_id,value,expected_version=record.version,idempotency_key="cost-choice"))
    assert not [e for e in events if e["type"]=="error"],events
    accepted=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    req=accepted["source_snapshot"]["requirements"][0]
    owned=[c for c in accepted["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    if net is None:
        assert not owned and accepted["requirement_outcomes"][0]["status"]!="answered"
    else:
        assert len(owned)==1 and float(owned[0]["value"])==net
        assert owned[0]["basis_refs"] and accepted["requirement_outcomes"][0]["status"]=="answered"


def test_rehearsal_accounting_reuses_same_data_and_reasks_after_real_reload(engine):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures,P4_REQUESTS
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True);_write_fixtures(cfg.workspace_resolved.parent)
    client=ScriptedClient(RunTrace(cfg.workspace_resolved.parent));loop.client=client;loop.auxiliary_llm_client=client
    list(loop.stream_turn("【M06-TYPED】"+P4_REQUESTS["M06-TYPED"][0]))
    first=loop._confirmation_runtime().checkpoint(loop.session_id)
    list(loop.resume_turn_streaming(first.confirmation_id,first.options[1].value,expected_version=first.version,idempotency_key="first"))
    events=list(loop.stream_turn("【M06-TYPED-REUSE】"+P4_REQUESTS["M06-TYPED-REUSE"][0]))
    assert not [e for e in events if e["type"] in {"error","suspended"}],events
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert any(c["target"].get("statistic")=="accounting_net" and float(c["value"])==86 for c in answer["source_snapshot"]["claims"])
    events=list(loop.stream_turn("【M06-TYPED-CHANGE】"+P4_REQUESTS["M06-TYPED-CHANGE"][0]))
    assert len([e for e in events if e["type"]=="suspended"])==1,events
    current=loop._confirmation_runtime().checkpoint(loop.session_id)
    assert current.data_version!=first.data_version and current.confirmation_id!=first.confirmation_id
    events=list(loop.resume_turn_streaming(current.confirmation_id,current.options[1].value,expected_version=current.version,idempotency_key="new-version"))
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert any(c["target"].get("statistic")=="accounting_net" and float(c["value"])==96 for c in answer["source_snapshot"]["claims"]),events


def test_rehearsal_window_replacement_withdrawal_compaction_and_followup_keep_source_identity(engine):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures,P4_REQUESTS
    from data_agent.agent.compact import compact_history,CompactState
    from data_agent.session.history import load_session,save_session,load_canonical_history
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.publication.requirements import project_requirements
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True);_write_fixtures(cfg.workspace_resolved.parent)
    client=ScriptedClient(RunTrace(cfg.workspace_resolved.parent));loop.client=client;loop.auxiliary_llm_client=client
    for marker in ["INTENT-05","INTENT-05-CHANGE"]:
        events=list(loop.stream_turn(f"【{marker}】"+P4_REQUESTS[marker][0]))
        assert not [e for e in events if e["type"] in {"error","suspended"}],events
        if marker=="INTENT-05":
            loaded_revision=loop.context.analysis_state.requirement_revision
            initial=loop.context.analysis_state.answer_requirements
            assert loaded_revision==2  # canonical request plus first loaded-version binding
            assert all(r.get("source_data_identities") for r in initial if r.get("delivery_targets"))
    state=loop.context.analysis_state
    assert state.requirement_revision==loaded_revision+2  # atomic replacement, then necessary-delivery registration
    retired=[r for r in state.answer_requirements if r["lifecycle_status"]=="withdrawn"]
    current=[r for r in state.answer_requirements if r["lifecycle_status"]=="active"]
    assert [r["original_text"] for r in retired]==["7日收入","复购率"] and [r["original_text"] for r in current]==["30日收入"]
    original=[(r["id"],r["source_message_ref"],r["source_start"],r["source_end"]) for r in state.answer_requirements]
    reference=load_session(loop.session_id)["messages"][-1]["answer_ref"]
    accepted=read_answer(loop.session_id,reference)
    assert [o["status"] for o in accepted["requirement_outcomes"]].count("withdrawn")==2
    owned=next(r for r in accepted["source_snapshot"]["requirements"] if r["id"]==current[0]["id"])["claim_ids"]
    assert len(owned)==1 and next(c["value"] for c in accepted["source_snapshot"]["claims"] if c["id"]==owned[0])==120
    compacted=compact_history(loop.session_id,SimpleNamespace(chat=lambda *a,**kw:SimpleNamespace(text="已经改变窗口；摘要不能恢复旧需求。")),loop.messages,CompactState())
    save_session(compacted,loop.session_id,extra_meta={"publication_schema":"answer_bindings.v2"},merge_protect=False)
    loop.messages=load_canonical_history(loop.session_id).messages
    projected=project_requirements(state,load_canonical_history(loop.session_id),{})
    assert [r["withdrawn"] for r in projected]==[True,True,False]
    events=list(loop.stream_turn("【INTENT-05-FOLLOW】"+P4_REQUESTS["INTENT-05-FOLLOW"][0]))
    assert not [e for e in events if e["type"] in {"error","suspended"}],events
    latest=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert all(not r["withdrawn"] for r in latest["source_snapshot"]["requirements"])
    assert next(r for r in state.answer_requirements if r["semantic_kind"]=="presentation")["source_answer_id"]==accepted["answer_id"]
    assert original==[(r["id"],r["source_message_ref"],r["source_start"],r["source_end"]) for r in state.answer_requirements[:3]]
    assert read_answer(loop.session_id,reference)["body"]==accepted["body"]


@pytest.mark.parametrize("fault",["none","unread_source","changed_dependency","tampered_receipt"])
def test_multi_input_python_field_uses_all_actual_dependencies_and_cannot_claim_unread_source(engine,fault):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine
    loop.context.workspace.add("costs",pd.DataFrame({"cost":[10,20]}))
    loop.context.workspace.add("unread",pd.DataFrame({"amount":[999]}))
    request(loop,"计算当前净额",{'kind': 'measurement', 'scope': {'datasets': ['unread'] if fault == 'unread_source' else ['orders','costs'], 'metrics': ['net'], 'quantity': 'value'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    rid,result=execute(loop,"run_python",{"code":"sales=get_dataset('orders')\ncosts=get_dataset('costs')\nresult={'net':float(sales['amount'].sum()-costs['cost'].sum())}\nresult"})
    if fault=="changed_dependency": loop.context.workspace.add("costs",pd.DataFrame({"cost":[99]}))
    if fault=="tampered_receipt":
        receipt=loop.context.analysis_state.tool_receipts[-1]
        from data_agent.tools.file_ops import _safe_path
        _safe_path(receipt["detail_ref"]["path"]).write_text("{}",encoding="utf-8")
    snap=snapshot_for_turn(loop);host=snap.as_dict();req=host["requirements"][0]
    body,error=publish(loop,draft(snap));assert error is None
    if fault=="none":
        owned=[c for c in host["claims"] if c["id"] in req["claim_ids"]]
        assert len(owned)==1 and owned[0]["value"]==150
        assert set(owned[0]["basis_refs"][0]["data_identities"])=={"orders","costs"}
        assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"
    else:
        assert not req["claim_ids"] and loop._accepted_answer["requirement_outcomes"][0]["status"]!="answered"
        assert any(c["value"]==180 and c["target"].get("statistic")=="sum" for c in host["claims"])


@pytest.mark.parametrize("fault",["none","missing_source","changed_source","foreign_claim"])
def test_one_multisource_requirement_needs_every_current_source_and_retains_partial_facts(engine,fault):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine
    datasets=["orders","second","third"]
    for name,value in [("second",2),("third",3)]: loop.context.workspace.add(name,pd.DataFrame({"amount":[value]}))
    request(loop,"分别计算三个来源的金额",[{"kind":"measurement","scope":{"datasets":[n],"metrics":["amount"],"quantity":"sum"}} for n in datasets])
    for name in datasets:
        if name!="third" or fault!="missing_source": execute(loop,"describe_dataset",{"name":name})
    if fault=="changed_source": loop.context.workspace.add("third",pd.DataFrame({"amount":[99]}))
    snap=snapshot_for_turn(loop);req=snap.as_dict()["requirements"][0]
    raw=draft(snap)
    if fault=="foreign_claim":
        value=json.loads(raw);value["sections"][0]["parts"].append({"kind":"claim","ref":"foreign"});raw=encode(value)
    body,error=publish(loop,raw)
    if fault=="foreign_claim":
        assert error is None
        assert any(t["ref"]=="foreign" and t["disposition"]=="rejected" for t in loop._accepted_answer["render_trace"])
        assert not any(t["ref"]=="foreign" and t["disposition"]=="accepted" for t in loop._accepted_answer["render_trace"])
        assert {c["value"] for c in snap.as_dict()["claims"] if c["id"] in req["claim_ids"]}=={180,2,3}
        return
    assert error is None
    owned=[c for c in snap.as_dict()["claims"] if c["id"] in req["claim_ids"]]
    assert {c["target"]["dataset"] for c in owned}==set(datasets if fault=="none" else datasets[:2])
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]==("answered" if fault=="none" else "partial")
    if fault!="none": assert "third" in req["gap"]["reason"] and any(c["value"]==180 for c in owned)


@pytest.mark.parametrize("datasets",[[],["orders","orders"],["orders",False],[""],[str(i) for i in range(17)]])
def test_multisource_selector_rejects_invalid_source_lists_atomically(engine,datasets):
    from data_agent.agent.publication.contracts import ContractError
    loop,_=engine
    with pytest.raises(ContractError): request(loop,"分别比较来源",{'kind': 'measurement', 'scope': {'datasets': datasets, 'quantity': 'rows'}})
    assert not loop.context.analysis_state.answer_requirements


def test_actual_compaction_restores_public_reply_export_without_expanding_model_history(engine, monkeypatch):
    from data_agent.agent.publication.runtime import snapshot_for_turn, publish, commit
    from data_agent.agent.compact import CompactState, compact_history
    from data_agent.session.history import save_session, load_canonical_history, load_session, branch_session
    from data_agent.session.public_messages import public_messages, assistant_replies
    from data_agent.tools.report import export_assistant_reply
    loop, cfg = engine
    request(loop, "计算当前记录数", {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop, "describe_dataset", {"name": "orders"})
    body, error = publish(loop, draft(snapshot_for_turn(loop)))
    assert error is None
    message = {"role": "assistant"}
    assert commit(loop, message, body) is None
    # Keep a complete long analysis and a short second turn, as in six-source B03.
    first = load_canonical_history(loop.session_id).messages
    messages = first[:-1] + [{"role": "system", "content": "execution detail"}] * 12 + first[-1:] + [
        {"role": "user", "content": "好的，继续。", "request_id": "short-followup"},
        {"role": "assistant", "content": "No new computation.", "reply_id": "short-reply"},
    ]
    save_session(messages, loop.session_id, extra_meta={"publication_schema": "answer_bindings.v2"}, merge_protect=False)
    before = load_canonical_history(loop.session_id)
    client = SimpleNamespace(chat=lambda **kw: SimpleNamespace(text="describe_dataset 已执行。"))
    compacted = compact_history(loop.session_id, client, before.messages, CompactState())
    save_session(compacted, loop.session_id, extra_meta={"publication_schema": "answer_bindings.v2"}, merge_protect=False)
    current = load_canonical_history(loop.session_id)
    assert len(current.messages) == 4 and current.message_count < before.message_count
    assert load_session(loop.session_id)["summary"] == "计算当前记录数"
    public = public_messages(load_session(loop.session_id)["messages"], loop.session_id)
    assert public == public_messages(before.messages, loop.session_id)
    reply = next(r for r in assistant_replies(public, loop.session_id) if r.get("answer_ref"))
    exported = export_assistant_reply(loop.session_id, reply_id=reply["reply_id"])
    assert body in (cfg.sessions_resolved.parent / exported["artifact_path"]).read_text("utf-8")
    from data_agent.tools.report import export_conversation
    monkeypatch.setattr("data_agent.tools.report._session_id", lambda: loop.session_id)
    whole = json.loads(export_conversation(format="markdown"))
    whole_text = (cfg.sessions_resolved.parent / whole["artifact_path"]).read_text("utf-8")
    assert body in whole_text and "计算当前记录数" in whole_text
    assert "Context compressed at turn boundary" not in whole_text
    assert load_canonical_history(loop.session_id) == current
    child = branch_session(loop.session_id)
    assert child["success"]
    child_public = public_messages(load_session(child["session_id"])["messages"], child["session_id"])
    assert any(m.get("content") == body for m in child_public)
    assert not any(m.get("answer_ref") for m in child_public)
    archive = cfg.sessions_resolved / loop.session_id / "transcripts" / compacted[0]["canonical_transcript"]["filename"]
    archive.write_text("tampered", encoding="utf-8")
    invalid = public_messages(load_session(loop.session_id)["messages"], loop.session_id)
    assert not any(m.get("answer_ref") for m in invalid)
    assert invalid[-1]["content"] == "No new computation."
    assert "历史归档不可核" in invalid[0]["content"]


@pytest.mark.parametrize("loaded",[False,True])
def test_natural_consultation_question_is_nonblocking_and_old_results_not_transported(engine,loaded):
    from pathlib import Path
    from data_agent.agent.loop import AgentLoop
    from data_agent.llm.client import Response,ToolCall
    from data_agent.session.history import load_session
    fixture=json.loads((Path(__file__).parent/"fixtures/p5-classification-20261008.json").read_text(encoding="utf-8"))
    archived=next(c for c in fixture["cases"] if c["case"]=="M01")
    aux=SimpleNamespace(manages_request_timeout=True,chat=lambda *a,**k:Response(text=archived["visible_json"]))
    class Consultation:
        def __init__(self):self.calls=[]
        def chat(self,messages,system="",**kw):
            self.calls.append(deepcopy((messages,system)))
            if len(self.calls)==1:
                return Response(tool_calls=[ToolCall("consult_question","ask_user_question",{"question":"选择留存口径","confirmation_type":"scope_confirmation","blocking_reason":"选择口径后才提供方案"})])
            from data_agent.agent.publication.runtime import snapshot_for_turn
            snapshot=snapshot_for_turn(loop)
            return Response(text=encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,"sections":[{"requirement_ids":[r["id"] for r in snapshot.as_dict()["requirements"] if not r["withdrawn"]],"parts":[{"kind":"text","purpose":"knowledge","text":"先准备用户唯一标识、订单时间与业务事件字段；按首单或活跃口径分别构建cohort，比较观察窗口，注意未成熟队列与因果限制。","claim_refs":[]}]}]}))
    main=Consultation()
    loop=engine[0] if loaded else AgentLoop(client=main,session_id="empty_consultation",auxiliary_llm_client=aux)
    loop.client=main;loop.auxiliary_llm_client=aux
    loop.messages=[{"role":"assistant","content":"旧数据结果 amount_sum=120，D30=999"}]
    result=loop.run_turn_structured(archived["input"])
    assert hasattr(result,"content") and "用户唯一标识" in result.content
    assert len(main.calls)==2
    assert all("amount_sum=120" not in json.dumps(messages,ensure_ascii=False) and "D30=999" not in system for messages,system in main.calls)
    assert all("orders" not in system for _,system in main.calls)
    assert not loop.context.analysis_state.pending_confirmations
    assert loop._accepted_answer["source_snapshot"]["mode"]=="consultation"
    assert loop._accepted_answer["source_snapshot"]["claims"]==[]
    assert load_session(loop.session_id)["messages"][-1]["context_kind"]=="knowledge"
    assert loop.messages[0]["content"].startswith("旧数据结果")


def test_consultation_projection_retains_only_host_marked_knowledge_rounds(engine):
    loop,_=engine
    loop.messages=[{"role":"user","content":"知识问题","context_kind":"knowledge","request_id":"k0"},
                   {"role":"assistant","content":"允许的知识说明","context_kind":"knowledge"},
                   {"role":"assistant","content":"旧分析数值999"},
                   {"role":"user","content":"解释这个概念","request_id":"k1"}]
    loop.context.turn_intent=SimpleNamespace(intent_type="knowledge_qa")
    projected=loop._provider_messages()
    assert [m["content"] for m in projected]==["知识问题","允许的知识说明","解释这个概念"]
    assert len(loop.messages)==4


@pytest.mark.parametrize("streaming",[False,True])
def test_semantic_mapping_schedules_current_formula_before_any_model_computation(engine,monkeypatch,streaming):
    import pandas as pd
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.agent.publication.contracts import encode
    loop,cfg=engine
    loop.context.workspace.add("orders",pd.DataFrame({"amount":[110],"coupon":[14],"channel":[10]}))
    content="请先确认当前版本的账面净收益公式，再计算"
    intent=TurnIntent("data_operation","clear","data_loaded","execute","execute_operation",requested_outputs=[{
        "exact_span":content,"kind":"result",'business_scope':{'datasets': ['orders'], 'metrics': ['账面净收益'], 'quantity': 'value'}}],
        measurement_mappings=[{"exact_span":"账面净收益","dataset":"orders","column":"amount","cost_scopes":[["coupon"],["coupon","channel"]]}])
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent",lambda *a,**kw:intent)
    loop.auxiliary_llm_client=object()
    monkeypatch.setattr("data_agent.agent.analysis_flow_controller.AnalysisFlowController.prepare_turn",lambda *a,**kw:None)
    class NoMainCall:
        def chat(self,*a,**kw):pytest.fail("Formula question must precede main model computation")
        def stream_chat_structured(self,*a,**kw):pytest.fail("Formula question must precede main model computation")
    loop.client=NoMainCall()
    if streaming:
        events=list(loop.stream_turn(content));assert len([e for e in events if e["type"]=="suspended"])==1
        record=loop._confirmation_runtime().checkpoint(loop.session_id)
    else:
        result=loop.run_turn_structured(content);assert isinstance(result,SuspendedForConfirmation)
        record=loop._confirmation_runtime().get(loop.session_id,result.confirmation_id)
    formulas=[json.loads(o.value) for o in record.options if o.value!="unconfirmed"]
    assert formulas[1]["cost_columns"]==["coupon","channel"]
    assert record.data_version==loop.context.workspace.get_data_identity("orders")["version_id"]
    assert not loop.context.analysis_state.tool_receipts


def test_compacted_knowledge_continuity_uses_original_marked_history_not_mixed_summary(engine):
    from data_agent.agent.compact import compact_history,CompactState
    loop,_=engine
    loop.messages=[{"role":"user","content":"咨询：解释观察与因果区别","request_id":"k1","context_kind":"knowledge"},
        {"role":"assistant","content":"观察不能证明因果，下一步讨论对照方案。","context_kind":"knowledge"},
        {"role":"user","content":"原分析数据","request_id":"a1"},
        {"role":"assistant","content":"历史金额210和231，不是咨询事实"}]
    for i in range(16):loop.messages.extend([{"role":"user","content":"知识追问"+str(i),"request_id":"k"+str(i+2),"context_kind":"knowledge"},
        {"role":"assistant","content":"说明"+str(i),"context_kind":"knowledge"}])
    loop.messages=compact_history(loop.session_id,SimpleNamespace(chat=lambda *a,**kw:SimpleNamespace(text="混合摘要含210和231")),loop.messages,CompactState())
    loop.messages.append({"role":"user","content":"继续讨论对照方案","request_id":"current"})
    loop.context.turn_intent=SimpleNamespace(intent_type="analysis_consultation")
    projected=encode(loop._provider_messages())
    assert "观察不能证明因果" in projected and "继续讨论对照方案" in projected
    assert "210" not in projected and "231" not in projected and "混合摘要" not in projected


def test_style_followup_cannot_execute_unrequested_totals_and_only_publishes_original_facts(engine,monkeypatch):
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    from data_agent.agent.intent import TurnIntent
    loop,_=engine;first="报告当前订单数"
    intent_for_app(monkeypatch,"result",first,{"datasets":["orders"],"quantity":"rows"})
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"});loop.run_turn_structured(first)
    original=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    current="好的，继续解释"
    proposed=TurnIntent("result_followup","clear","data_loaded","follow_up","answer_directly",requested_outputs=[{
        "exact_span":current,"kind":"presentation","presentation_role":"explanation","source_answer_id":original["answer_id"]}])
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent",lambda *a,**kw:proposed)
    loop.client=AppClient(loop,"run_python",{"code":"result_data={'unrequested_total':999}"})
    before=len(loop.context.analysis_state.tool_receipts)
    loop.run_turn_structured(current)
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert len(loop.context.analysis_state.tool_receipts)==before
    assert any("followup_execution_not_requested" in str(m.get("content")) for m in loop.messages if m.get("role")=="tool")
    assert {c["id"] for c in answer["source_snapshot"]["claims"]}=={t["ref"] for t in original["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    assert "999" not in answer["body"]


@pytest.mark.parametrize("ambiguous,restart,explicit",[(False,False,False),(True,False,False),(True,True,False),(True,False,True),(True,True,True)])
def test_http_upload_alias_formula_resume_and_version_reconfirmation_use_same_objects(engine,monkeypatch,ambiguous,restart,explicit):
    import io
    from data_agent.agent.intent import TurnIntent
    from data_agent.web.app import create_app
    from data_agent.web.run_state import RunStates
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,cfg=engine
    def events(response):
        assert response.status_code==200,response.get_data(as_text=True)
        return [(block.split("\n",1)[0][7:],json.loads(block.split("\ndata: ",1)[1]))
                for block in response.get_data(as_text=True).split("\n\n") if block.startswith("event:")]
    app=create_app();app.config["agent_manager"]=SimpleNamespace(get_or_create=lambda **kw:loop,get=lambda sid:loop,runs=RunStates())
    loop.auxiliary_llm_client=object();previous=None
    with app.test_client() as client:
        for index,(amount,expected) in enumerate([(110,86),(120,96)]):
            if index and ambiguous:
                from data_agent.web.blueprints.uploads import bind_uploads_to_session,ingest_bound_uploads
                from data_agent.agent.context import use_agent_context
                other=client.post("/api/upload",data={"file":(io.BytesIO(b"amount\n9\n"),"other-object.csv")},content_type="multipart/form-data").get_json()
                ingest_bound_uploads(loop,bind_uploads_to_session(loop.session_id,[other]))
                with use_agent_context(loop.context):
                    loop._bind_current_uploads("加载为 other",[{"upload_id":other["upload_id"],"dataset":"other","relation":"new","exact_span":"加载为 other"}])
            filename="promo-input.csv" if index==0 else "M06-promo-v2.csv" if explicit else "unrelated-file-name.csv"
            uploaded=client.post("/api/upload",data={"file":(io.BytesIO(f"group,incremental_revenue,coupon_cost,channel_cost\nall,{amount},14,10\n".encode()),filename)},content_type="multipart/form-data").get_json()
            user="请加载为 m06_promo，并先确认账面净收益公式" if index==0 else "新上传文件是同一业务对象新版，请重新确认账面净收益公式"
            if index and explicit:
                from pathlib import Path
                user=json.loads(Path("tests/fixtures/p5-contract-reset-20261009.json").read_text(encoding="utf-8"))["m06_explicit_replacement"]["user_input"]
            intent=TurnIntent("data_operation","clear","data_loaded","execute","execute_operation",requested_outputs=[{
                "exact_span":user,"kind":"result",'business_scope':{'datasets': ['m06_promo'], 'metrics': ['账面净收益'], 'quantity': 'value'}}],
                upload_bindings=[{"upload_id":uploaded["upload_id"],"dataset":"m06_promo","relation":"new" if index==0 else "replace","exact_span":user}],
                measurement_mappings=[{"exact_span":"账面净收益","dataset":"m06_promo","column":"incremental_revenue","cost_scopes":[["coupon_cost"],["coupon_cost","channel_cost"]]}])
            if index and explicit:
                intent.upload_bindings[0]["object_span"]="m06_promo"
            if index and ambiguous and not explicit:
                intent.upload_bindings[0]["dataset"]="other"
                intent.requested_outputs[0]["business_scope"]["datasets"]=["other"]
                intent.measurement_mappings[0]["dataset"]="other"
            monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent",lambda *a,**kw:intent)
            loop.client=AppClient(loop)
            suspended=events(client.post("/api/chat",json={"session_id":loop.session_id,"message":user,"uploads":[uploaded]}))
            terminal=[d for e,d in suspended if e=="turn_end"];assert len(terminal)==1 and terminal[0]["status"]=="suspended"
            record=loop._confirmation_runtime().checkpoint(loop.session_id)
            if index and ambiguous and not explicit:
                assert record.resolution_action=="bind_uploaded_objects"
                assert not loop.context.analysis_state.answer_requirements[-1].get("source_data_identities",{}).get("other")
                from data_agent.agent.context import use_agent_context
                with use_agent_context(loop.context):
                    assert loop.context.workspace.get_data_identity("m06_promo")["version_id"]==previous.data_version
                if restart:
                    from data_agent.web.agent_manager import AgentManager
                    manager=AgentManager(client_factory=lambda **kw:object(),auxiliary_client_factory=object)
                    loop=manager.get_or_create(session_id=loop.session_id)
                    app.config["agent_manager"]=manager
                loop.client=AppClient(loop)
                choice=next(o.value for o in record.options if json.loads(o.value)[0]["dataset"]=="m06_promo")
                mapped=events(client.post("/api/chat/resume",json={"session_id":loop.session_id,"confirmation_id":record.confirmation_id,"user_response":choice,"expected_version":record.version,"idempotency_key":"object_choice"}))
                terminal=[d for e,d in mapped if e=="turn_end"];assert len(terminal)==1 and terminal[0]["status"]=="suspended",mapped
                record=loop._confirmation_runtime().checkpoint(loop.session_id)
                assert record.resolution_action=="record_confirmation_answer"
            assert record.resolution_params["measurement_mapping"]["dataset"]=="m06_promo"
            if previous:assert record.data_version!=previous.data_version and record.confirmation_id!=previous.confirmation_id
            previous=record
            chosen=next(o for o in record.options if o.value!="unconfirmed" and len(json.loads(o.value)["cost_columns"])==2)
            loop.client=AppClient(loop,"transform_data",{"name":"m06_promo","operation":"group_aggregate","group_by":["group"],"aggregations":[{"column":c,"functions":["sum"]} for c in ["incremental_revenue","coupon_cost","channel_cost"]]})
            resumed=events(client.post("/api/chat/resume",json={"session_id":loop.session_id,"confirmation_id":record.confirmation_id,"user_response":chosen.value,"expected_version":record.version,"idempotency_key":"version_"+str(index)}))
            terminal=[d for e,d in resumed if e=="turn_end"];assert len(terminal)==1 and terminal[0]["status"]=="completed",resumed
            answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
            facts=[c for c in answer["source_snapshot"]["claims"] if c.get("target",{}).get("statistic")=="accounting_net"]
            assert len(facts)==1 and facts[0]["value"]==str(expected)
            assert all("因果" in " ".join(c["limitations"]) for c in facts)
            assert answer["body"]==terminal[0]["reply_content"]


def test_unfinished_original_target_cannot_silently_bind_new_version(engine,monkeypatch):
    import pandas as pd
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.publication.runtime import snapshot_for_turn,read_answer
    from data_agent.session.history import load_session
    loop,_=engine;first="计算均值并解释限制"
    proposal=TurnIntent("data_operation","clear","data_loaded","execute","execute_operation",requested_outputs=[{
        "exact_span":first,"kind":"result",'business_scope':{'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'mean'},"purposes":["interpretation"]}])
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent",lambda *a,**kw:proposal)
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"});loop.run_turn_structured(first)
    original=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    old_req=loop.context.analysis_state.answer_requirements[0]
    assert old_req["source_data_identities"]["orders"]==loop.context.workspace._publication_data_identity("orders")
    loop.prepare_for_bound_upload()
    loop.context.workspace.add("orders",pd.DataFrame({"amount":[999]}))
    current="计算新版记录数"
    intent_for_app(monkeypatch,"result",current,{"datasets":["orders"],"quantity":"rows"})
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"});loop.run_turn_structured(current)
    latest=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    projected=next(r for r in latest["source_snapshot"]["requirements"] if r["id"]==old_req["id"])
    assert projected["claim_ids"]==[] and projected["gap"]["status"]=="evidence_insufficient"
    reference=next(m["answer_ref"] for m in load_session(loop.session_id)["messages"] if m.get("answer_id")==original["answer_id"])
    assert read_answer(loop.session_id,reference)["body"]==original["body"]


@pytest.mark.parametrize("restart",[False,True])
def test_all_material_mappings_are_confirmed_serially_before_computation(engine,monkeypatch,restart):
    import pandas as pd
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.loop import SuspendedForConfirmation
    from data_agent.web.agent_manager import AgentManager
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"amount":[10,20],"count":[1,2]}))
    user="先确认金额与次数的尺度，再报告各自均值"
    intent=TurnIntent("data_operation","clear","data_loaded","execute","execute_operation",
        requested_outputs=[{"exact_span":span,"kind":"result",'business_scope':{'datasets': ['orders'], 'metrics': [column], 'quantity': 'mean'}} for span,column in [("金额","amount"),("次数","count")]],
        measurement_mappings=[{"exact_span":span,"dataset":"orders","column":column} for span,column in [("金额","amount"),("次数","count")]])
    calls=[]
    def classify(*a,**kw):calls.append(a[0]);return intent
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent",classify)
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"})
    first=loop.run_turn_structured(user);assert isinstance(first,SuspendedForConfirmation)
    assert not loop.context.analysis_state.tool_receipts
    record=loop._confirmation_runtime().checkpoint(loop.session_id)
    assert record.resolution_params["measurement_mapping"]["column"]=="amount"
    assert "publication_context" not in record.resolution_params
    if restart:
        manager=AgentManager(client_factory=lambda **kw:object(),auxiliary_client_factory=object)
        loop=manager.get_or_create(session_id=loop.session_id)
        loop.client=AppClient(loop,"describe_dataset",{"name":"orders"})
    second=loop.resume_turn(record.confirmation_id,"raw",expected_version=record.version,idempotency_key="first_mapping")
    assert isinstance(second,SuspendedForConfirmation)
    assert not loop.context.analysis_state.tool_receipts
    record=loop._confirmation_runtime().checkpoint(loop.session_id)
    assert record.resolution_params["measurement_mapping"]["column"]=="count"
    final=loop.resume_turn(record.confirmation_id,"raw",expected_version=record.version,idempotency_key="second_mapping")
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert final.content==answer["body"] and all(r["status"]=="answered" for r in answer["requirement_outcomes"])
    assert len(answer["source_snapshot"]["confirmation_refs"])==2
    assert calls==[user] and len([r for r in loop.context.analysis_state.tool_receipts if r["tool_name"]!="record_analysis_plan"])==1


@pytest.mark.parametrize("streaming",[False,True])
def test_host_refresh_precedes_issued_snapshot_and_cannot_invalidate_unchanged_draft(engine,monkeypatch,streaming):
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    loop,_=engine;user="报告当前记录数"
    intent_for_app(monkeypatch,"result",user,{"datasets":["orders"],"quantity":"rows"})
    calls=[]
    def refresh(content):
        calls.append(content)
        # A host refresh changes the structured plan identity; it must happen before issuance.
        loop.context.analysis_state.analysis_plan={"id":"host_refresh_"+str(len(calls))}
        loop.context.analysis_state.save()
    monkeypatch.setattr(loop,"_verify_before_publication",refresh)
    issued=[]
    class FrozenInputClient(AppClient):
        def chat(self,messages,**kw):
            from data_agent.llm.client import Response
            if any(m.get("role")=="tool" for m in messages):
                snapshot=loop._publication_runtime[1]
                assert snapshot.digest in kw["system"]
                issued.append((snapshot.digest,snapshot.as_dict()["plan_id"]))
                return Response(text=draft(snapshot),tool_calls=[],finish_reason="stop")
            return super().chat(messages,**kw)
    loop.client=FrozenInputClient(loop,"describe_dataset",{"name":"orders"})
    if streaming:
        events=list(loop.stream_turn(user));assert not [e for e in events if e["type"]=="error"]
        body="".join(e["text"] for e in events if e["type"]=="text_delta")
    else:body=loop.run_turn_structured(user).content
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert answer["body"]==body and answer["snapshot_digest"]==issued[-1][0]
    assert answer["source_snapshot"]["plan_id"]==issued[-1][1]
    assert not any(i["code"]=="stale_draft" for i in answer["issues"])
    assert len(issued)==1 and calls==[user,user]


@pytest.mark.parametrize("initial",["missing","partial","partial_changed"])
def test_actual_tool_load_reuses_one_intent_and_original_requirement(engine,monkeypatch,tmp_path,initial):
    from data_agent.agent.intent import TurnIntent
    from data_agent.llm.client import Response,ToolCall
    loop,_=engine;user="加载输入后报告记录数" if initial=="missing" else "分别报告已有orders与加载loaded的记录数"
    datasets=["loaded"] if initial=="missing" else ["orders","loaded"]
    prior_identity=loop.context.workspace.get_data_identity("orders")
    source=tmp_path/"load-once.csv";source.write_text("amount\n1\n2\n",encoding="utf-8")
    intent=TurnIntent("data_operation","clear","no_data","execute","load_then_analyze",
        requested_outputs=[{"exact_span":user,"kind":"result",'business_scope':{'datasets': datasets, 'quantity': 'rows'}}])
    calls=[]
    def classify(*a,**kw):calls.append(a[0]);return intent
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent",classify)
    class LoadingClient(AppClient):
        def chat(self,*a,**kw):
            if not getattr(self,"loaded",False):
                self.loaded=True
                if initial=="partial_changed":
                    import pandas as pd
                    loop.context.workspace.add("orders",pd.DataFrame({"amount":[999]}))
                return Response(tool_calls=[ToolCall("load","load_data",{"source":str(source),"name":"loaded"})])
            if not getattr(self,"planned",False):return super().chat(*a,**kw)
            if not getattr(self,"measured",False):
                self.measured=True
                return Response(tool_calls=[ToolCall("describe_"+name,"describe_dataset",{"name":name}) for name in datasets])
            from data_agent.agent.publication.runtime import snapshot_for_turn
            return Response(text=draft(snapshot_for_turn(loop)))
    loop.client=LoadingClient(loop,"describe_dataset",{"name":datasets[0]})
    body=loop.run_turn_structured(user).content
    assert calls==[user] and len(loop.context.analysis_state.answer_requirements)==1
    if initial=="partial_changed":
        assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="evidence_insufficient"
        assert loop.context.analysis_state.answer_requirements[0]["source_data_identities"]=={"orders":prior_identity}
        assert "来源版本已变化：orders" in body
        return
    identities=loop.context.analysis_state.answer_requirements[0]["source_data_identities"]
    assert set(identities)==set([datasets] if isinstance(datasets,str) else datasets)
    if initial=="partial":assert identities["orders"]==prior_identity
    assert loop.context.turn_intent.data_state=="data_loaded" and loop.context.turn_intent.execution_readiness=="ready"
    assert loop.context.analysis_state.answer_requirements[0]["source_data_identities"]["loaded"]==loop.context.workspace._publication_data_identity("loaded")
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered", {"requirements":loop._accepted_answer["source_snapshot"]["requirements"],"tools":[m.get("content") for m in loop.messages if m.get("role")=="tool"],"targets":[c.get("target") for c in loop._accepted_answer["source_snapshot"]["claims"]]}
    assert body==loop._accepted_answer["body"]


def test_ambiguous_selected_objects_preserve_original_demand_without_formula_authority(engine,monkeypatch):
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.publication.runtime import register_request,snapshot_for_turn,publish
    from data_agent.agent.confirmation.models import ConfirmationStatus
    from data_agent.web.blueprints.uploads import configure_upload_confirmation
    loop,_=engine
    text="分别替换两个对象并计算账面净收益"
    request(loop,text)
    loop.context.analysis_state.answer_requirements=[]
    loop.context.analysis_state.requirement_revision=0
    intent=TurnIntent("directed_analysis","clear","data_loaded","execute","run_analysis",execution_readiness="ready",
        requested_outputs=[{"exact_span":"账面净收益","kind":"result",'business_scope':{'datasets': ['candidate'], 'metrics': ['accounting_net'], 'quantity': 'value'}}],
        measurement_mappings=[{"exact_span":"账面净收益","dataset":"candidate","column":"amount","cost_scopes":[["coupon"],["coupon","channel"]]}])
    selected=[{"upload_id":"one","dataset":"orders","relation":"replace","exact_span":"两个对象"},
              {"upload_id":"two","dataset":"second","relation":"replace","exact_span":"两个对象"}]
    record=SimpleNamespace(resolution_action="bind_uploaded_objects",status=ConfirmationStatus.RESOLVED,
        response=json.dumps(selected),resolution_params={"user_input":text,"intent":vars(intent),
            "proposed_bindings":[dict(row,dataset="candidate") for row in selected]})
    prepared=[]
    def complete(content,decision):
        prepared.append(decision)
        register_request(loop,content,decision)
    monkeypatch.setattr(loop,"_complete_analysis_turn",complete)
    configure_upload_confirmation(loop)
    assert loop._after_confirmation_resolution(record)
    requirement=loop.context.analysis_state.answer_requirements[0]
    assert requirement["original_text"]=="账面净收益" and requirement["business_scope"]["datasets"]==["candidate"]
    assert "selector" not in requirement and not prepared[0].measurement_mappings
    snap=snapshot_for_turn(loop)
    body,error=publish(loop,draft(snap))
    assert error is None and loop._accepted_answer["requirement_outcomes"][0]["status"]!="answered"
    assert not snap.as_dict()["claims"]


def test_original_table_formula_and_chart_contract_after_load_keeps_all_deliveries(engine):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace,_write_fixtures
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    loop,cfg=engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True,exist_ok=True)
    _write_fixtures(cfg.workspace_resolved.parent)
    client=ScriptedClient(RunTrace(cfg.workspace_resolved.parent))
    loop.client=client;loop.auxiliary_llm_client=client
    events=list(loop.stream_turn("【CONTENT-B07】展示表格与公式和图表，保留当前原值与范围。"))
    assert not [e for e in events if e["type"] in {"error","suspended"}],events
    answer=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    claims=answer["source_snapshot"]["claims"]
    assert {"amount_sum":120.,"records":12,"average_amount":10.} in [c["value"] for c in claims if c["target"].get("tool")=="run_python"]
    assert all(o["status"]=="answered" for o in answer["requirement_outcomes"])
    assert len(answer["artifact_refs"])==1 and answer["artifact_refs"][0]["type"]=="chart"
    assert "| 订单金额 | 120 |" in answer["body"] and "不能外推总体" in answer["body"]
    assert answer["audit_status"]=="reviewed" and answer["source_snapshot"]["mode"]=="analysis"


@pytest.mark.parametrize("new_target",[False,True])
def test_knowledge_with_registered_data_example_uses_audit_but_cannot_acquire_new_target(engine,new_target):
    from data_agent.agent.publication.runtime import snapshot_for_turn,current_request_uses_data
    from data_agent.agent.publication.requirements import record_execution_targets
    from data_agent.session.history import load_canonical_history
    from data_agent.agent.publication.contracts import ContractError
    loop,_=engine
    request(loop,"解释记录数的方法",kind="knowledge")
    state=loop.context.analysis_state;before=deepcopy(state.answer_requirements)
    if new_target:
        from data_agent.agent.analysis_plan_contracts import validate_analysis_plan_contract
        raw={"contract_version":"stage3c0b.v2","requirement_revision":state.requirement_revision,"goal":"Attempt data execution from knowledge","method_plan":[{"step_id":"invalid","goal":"Compute","expected_output":"Rows","dataset_inputs":["orders"],"evidence_requirements":["receipt"],"required_deliveries":[{"requirement_id":before[0]["id"],"kind":"measurement","label":"rows","scope":{"datasets":["orders"],"quantity":"rows"}}]}]}
        result=validate_analysis_plan_contract(raw,answer_requirements=state.answer_requirements,requirement_revision=state.requirement_revision)
        assert result.error_type=="consultation_delivery_change" and state.answer_requirements==before
        return
    request(loop,"以当前样本记录数举例",{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}})
    state.answer_requirements[-1]["purposes"]=["knowledge"]
    execute(loop,"describe_dataset",{"name":"orders"})
    snap=snapshot_for_turn(loop)
    assert current_request_uses_data(loop) and snap.as_dict()["mode"]=="analysis"
    assert state.answer_requirements[-1]["source_data_identities"]=={"orders":loop.context.workspace.get_data_identity("orders")}


def test_recorded_m02_synthesis_scope_does_not_turn_unreadable_data_into_missing(engine):
    """Recompute captured inputs; old model answer/digest stays immutable."""
    from io import StringIO
    from pathlib import Path
    import pandas as pd
    from data_agent.agent.publication.requirements import update_requirements
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.session.history import load_canonical_history, save_session
    trace=json.loads((Path(__file__).parent/"fixtures/p5-contract-reset-20261009.json").read_text(encoding="utf-8"))
    loop,_=engine
    loop.context.workspace.add("M02-retention",pd.read_csv(StringIO(trace["csv"])))
    loop.messages.append({"role":"user","content":trace["user_input"],"request_id":"recorded_m02"})
    save_session(loop.messages,loop.session_id,merge_protect=False)
    loop._last_jsonl_idx=len(loop.messages)
    changes=[dict(op="add",start=x["source_start"],end=x["source_end"],kind=x["semantic_kind"],business_scope={"datasets":["M02-retention"],"metrics":["retention"]},purposes=x["purposes"]) for x in trace["requirements"]]
    ids=update_requirements(loop.context.analysis_state,load_canonical_history(loop.session_id),"recorded_m02",changes,expected_revision=0)
    loop.context.turn_intent=SimpleNamespace(intent_type="directed_analysis")
    loop.context.turn_requirement_ids=ids
    loop._publication_turn_id="recorded_m02_local"
    from tests.support.plan_inputs import declare_goal_deliveries
    declare_goal_deliveries(loop,[(ids[0],"series",{"datasets":["M02-retention"],"metrics":["retention"]}),(ids[1],"scenario",{"datasets":["M02-retention"],"metrics":["retention"]})])
    execute(loop,"preview_data",{"name":"M02-retention","n":10})
    execute(loop,"curve_fitting",{"name":"M02-retention","x_col":"day","y_col":"retention","scenario_points":[10,14,21,30]})
    from tests.test_scoped_workspace import _stage3c0b_task
    from data_agent.session.task_manager import task_manager
    _stage3c0b_task(task_manager,session_id=loop.session_id,datasets=["M02-retention"],mode="synthesis")
    assert loop.context.refresh_workspace_scope().phase=="synthesis"
    assert loop.context.workspace.list_datasets()=={}
    assert loop.context.workspace.get("M02-retention") is None
    assert not loop.context.workspace.exists("M02-retention")
    snapshot=snapshot_for_turn(loop).as_dict()
    assert snapshot["claims"] and "M02-retention" in snapshot["data_identities"]
    assert snapshot["requirements"][0]["gap"] is None
    assert loop.context.workspace._publication_dataset_exists("M02-retention") is True
    assert loop.context.workspace._publication_dataset_exists("missing") is False
    assert loop.context.workspace.list_datasets()=={}

