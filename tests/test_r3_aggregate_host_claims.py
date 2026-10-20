from tests.support.publication_runtime import audit_reasons
"""Current grouped frames keep source grain, methods and version identity."""
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number, has_record

import json

import pandas as pd
import pytest



def _source():
    return pd.DataFrame({"channel":["A","A","A","B"],"order_id":["X","X","Y","Z"],"amount":[10.0,None,10.0,0.0]})


def test_terminal_publication_keeps_aggregate_and_comparison_with_auxiliary_tool(engine):
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    from tests.test_r3_comparison_host_claims import _actual_comparisons
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=_actual_comparisons(engine)
    loop.context.workspace.add("sales",_source())
    request(loop,"保留分组各计数和金额",{'kind':'table','scope':{'datasets':['sales'],'metrics':['amount_sum','amount_count','amount_size','order_id_nunique']}})
    rid,result=execute(loop,"transform_data",{"name":"sales","operation":"group_aggregate","group_by":["channel"],"aggregations":[{"column":"amount","functions":["sum","count","size"]},{"column":"order_id","functions":["nunique"]}]})
    request(loop,"辅助 Python 描述",{'kind': 'table', 'scope': {'datasets': ['sales']}})
    execute(loop,"run_python",{"code":"df=get_dataset('sales'); result={'rows':len(df)}","purpose":"preserve auxiliary result"})
    first=result["measurement_records"][0]
    assert first=={"channel":"A","amount_sum":20.0,"amount_count":2,"amount_size":3,"order_id_nunique":2}
    host=snapshot_for_turn(loop);body,error=publish(loop,draft(host));assert error is None
    assert "amount_sum" in visible_text(body) and has_number(body, 'amount：后期', 11) and "result_data" in visible_text(body)
    from data_agent.agent.publication.facts import _safe_path
    _safe_path(loop.context.analysis_state.tool_receipts[-2]["detail_ref"]["path"]).write_text("corrupt",encoding="utf-8")
    changed=snapshot_for_turn(loop);body,error=publish(loop,draft(changed));assert error is None
    assert not any(c["basis_refs"][0]["receipt_id"]==rid for c in changed.as_dict()["claims"])
    assert has_number(body, 'amount：后期', 11) and "保留分组各计数和金额：证据不足" in body


def test_grouped_values_keep_count_size_nunique_and_source_rows(engine):
    loop, cfg, rid, result = _grouped(engine)
    assert result["rows"] == 2
    assert result["source_observation"]["rows"] == 4
    assert result["measurement_records"] == [
        {"channel":"A","amount_sum":20.0,"amount_count":2,"amount_size":3,"order_id_nunique":2},
        {"channel":"B","amount_sum":0.0,"amount_count":1,"amount_size":1,"order_id_nunique":1},
    ]
    snap=snapshot_for_turn(loop); host=snap.as_dict()
    source=next(c for c in host["claims"] if c["basis_refs"][0]["result_path"]==["source_observation"])
    assert source["value"]["rows"]==4 and source["scope"]["dataset"]=="sales"
    assert set(source["basis_refs"][0]["data_identities"])=={"sales","by_channel"}
    body,error=publish(loop,draft(snap)); assert error is None
    assert has_record(body, {'channel':'A','amount_sum':20.0,'amount_count':2,'amount_size':3,'order_id_nunique':2}) and has_record(body, {'channel':'B','amount_sum':0.0,'amount_count':1,'amount_size':1,'order_id_nunique':1})
    assert "非空值个数" in body and "组内行数" in body and "非空唯一值个数" in body
    assert "单位未知" in body
    assert (has_pair(body, '派生表 by_channel 记录数', '2 条') or '派生表 by_channel 记录数：2 条' in visible_text(body)) and has_number(body, 'rows', 4)
    forged=json.loads(draft(snap)); forged["sections"][0]["parts"][0]["value"]=99
    body,error=publish(loop,json.dumps(forged,ensure_ascii=False)); assert error is None
    assert not getattr(loop,"_turn_finalization_recovery_used",False)
    assert any(i["code"]=="invalid_fields" for i in loop._accepted_answer["issues"])
    assert has_number(body, 'amount_sum', 20.0)


def test_aggregate_source_date_span_is_bound_to_current_source_version(engine):
    loop, cfg, rid, result = _grouped(engine, dated=True)
    window=result["source_observation"]["observation_window"]["columns"]["date"]
    assert window=={"min":"2026-09-01 00:00:00","max":"2026-09-04 00:00:00","non_null_rows":4,"distinct_values":4}
    snap=snapshot_for_turn(loop); claims=snap.as_dict()["claims"]
    days=next(c for c in claims if c.get("derivation",{}).get("operator")=="inclusive_calendar_days")
    assert days["value"]==4 and days["unit"]=="天"
    assert days["derivation"]["operand_paths"]==[
        ["source_observation","observation_window","columns","date","min"],
        ["source_observation","observation_window","columns","date","max"],
    ]
    body,error=publish(loop,draft(snap)); assert error is None
    assert "2026-09-01 00:00:00" in body and "2026-09-04 00:00:00" in body
    assert (has_pair(body, '源观测日期含首尾日数', '4 天') or '源观测日期含首尾日数：4 天' in visible_text(body))
    frame=loop.context.workspace.get("sales"); frame.loc[0,"date"]=pd.Timestamp("2026-08-31")
    loop.context.workspace.add("sales",frame)
    changed=snapshot_for_turn(loop)
    assert not any(c["basis_refs"][0]["receipt_id"]==rid for c in changed.as_dict()["claims"])
    body,error=publish(loop,draft(changed)); assert error is None
    assert "2026-09-01 00:00:00" not in body and "证据不足" in body


def test_current_presentation_request_changes_only_the_verified_aggregate_claim(engine):
    loop,cfg,rid,result=_grouped(engine)
    from data_agent.agent.publication.runtime import commit
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    assert commit(loop,{'role':'assistant'},body) is None
    request(loop,"请改成业务负责人表达，保留同一事实。",kind='presentation',purposes=['interpretation'],source_answer_id=loop._accepted_answer['answer_id'])
    snap=snapshot_for_turn(loop);req=next(r for r in snap.as_dict()["requirements"] if r["text"].startswith("请改成"))
    text="按当前分组说明观测差异；金额与三种计数的口径不同，未来行动阈值仍需另行确定。"
    body,error=_open(loop,snap,req,text);assert error is None
    assert text in body and has_number(body, 'amount_sum', 20.0) and "投放" not in body
    assert next(r for r in loop._accepted_answer["requirement_outcomes"] if r["requirement_id"]==req["id"])["status"]=="answered"
    assert len(loop.client.calls)==1
    forged=json.loads(_open_raw(snap,req,text));forged["sections"][0]["requirement_ids"]=["rq_other"]
    body,error=publish(loop,json.dumps(forged,ensure_ascii=False));assert error is None
    assert text not in body and has_number(body, 'amount_sum', 20.0)
    assert next(r for r in loop._accepted_answer["requirement_outcomes"] if r["requirement_id"]==req["id"])["status"]=="partial"


def test_current_action_subgoal_has_a_bound_gap_without_losing_aggregate_values(engine):
    loop,cfg,rid,result=_grouped(engine)
    request(loop,"请给出有条件行动建议。",kind="conditional_action")
    snap=snapshot_for_turn(loop);req=next(r for r in snap.as_dict()["requirements"] if r["text"]=="请给出有条件行动建议。")
    body,error=publish(loop,draft(snap)); assert error is None
    assert has_number(body, 'amount_sum', 20.0) and "条件性建议未核" in body
    assert "未交付所需开放内容：conditional_action" in audit_reasons(loop._accepted_answer)
    action=next(r for r in loop._accepted_answer["requirement_outcomes"] if r["requirement_id"]==req["id"])
    assert action["status"]!="answered"
    # A locator can bind existing facts; it cannot invent missing conditions.
    raw=_open_raw(snap,req,"仅当未来可比窗口的成本和效果两项条件均满足时再作决策；当前未测这些条件。")
    from tests.test_publication_audit_view import AuditClient
    loop.client=AuditClient(["reject"])
    body,error=publish(loop,raw);assert error is None
    assert has_number(body, 'amount_sum', 20.0) and "两项条件均满足" not in body
    assert len(loop.client.calls)==1 and not any(o["status"]=="answered" for o in loop._accepted_answer["requirement_outcomes"] if o["requirement_id"]==req["id"])


def test_confirmed_partial_result_keeps_observation_and_itemizes_missing_result(engine):
    loop,cfg,candidate,service,rid,result=_formula(engine,choice="both",columns=["order_amount"])
    request(loop,"判断促销增量是否成立",kind="gap")
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    assert result["measurement_records"]==[{"channel":"all","order_amount_sum":120}]
    assert has_number(body, 'order_amount_sum', 120) and "账面净收益：未计算" in body and "判断促销增量是否成立：证据不足" in body
    assert not any(c.get("target",{}).get("statistic")=="accounting_net" for c in snap.as_dict()["claims"])
    outcomes=loop._accepted_answer["requirement_outcomes"]
    net=next(r for r in snap.as_dict()["requirements"] if r["text"]=="计算账面净收益")
    assert next(r for r in outcomes if r["requirement_id"]==net["id"])["status"]=="not_computed"
    assert candidate.options[1].value==service.get(loop.session_id,candidate.confirmation_id).response


@pytest.mark.parametrize("fault",["none","pending","skipped","foreign_session","forged_response","changed_scope","missing_response_id","changed_source"])
def test_partial_scope_requires_resolved_same_session_business_confirmation(engine,fault):
    from dataclasses import replace
    from data_agent.agent.confirmation.models import ConfirmationRequest
    from data_agent.agent.publication.requirements import resolve_confirmation
    loop,cfg,candidate,service,rid,result=_formula(engine,choice=None if fault=="pending" else "skipped" if fault=="skipped" else "both")
    current=ConfirmationRequest.from_candidate(candidate)
    if fault=="foreign_session": current=replace(current,session_id="foreign_session")
    if fault=="forged_response": _change_record(loop,cfg,service,candidate,response="forged_choice")
    if fault=="changed_scope": _change_record(loop,cfg,service,candidate,spec_version="changed_spec")
    if fault=="missing_response_id": _change_record(loop,cfg,service,candidate,response_id="")
    if fault=="changed_source":
        frame=loop.context.workspace.get("promo");frame.loc[0,"increment"]+=1;loop.context.workspace.add("promo",frame)
        from data_agent.agent.confirmation.runtime import build_measurement_mapping_candidate
        from data_agent.session.history import load_canonical_history
        candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id=candidate.turn_id,workspace=loop.context.workspace,canonical_history=load_canonical_history(loop.session_id),**candidate.resolution_params["measurement_mapping"])
        current=ConfirmationRequest.from_candidate(candidate)
    if fault=="none":
        selected=resolve_confirmation(current)
        assert selected["response_id"]=="aggregate_choice" and json.loads(selected["response"])["cost_columns"]==["coupon","channel_cost"]
    else:
        with pytest.raises(ValueError): resolve_confirmation(current)
        owned=[c for c in snapshot_for_turn(loop).as_dict()["claims"] if c.get("target",{}).get("statistic")=="accounting_net"]
        if fault=="foreign_session":
            assert len(owned)==1 and owned[0]["derivation"]["confirmation_id"]==candidate.confirmation_id
            assert all(p["session_id"]==loop.session_id for p in owned[0]["basis_refs"])
        else: assert not owned


@pytest.mark.parametrize("fault",["none","hidden_formula","missing_response_id"])
def test_selected_formula_is_visible_in_the_real_business_choice(engine,fault):
    from dataclasses import replace
    from data_agent.agent.confirmation.models import ConfirmationRequest
    from data_agent.agent.publication.requirements import resolve_confirmation
    loop,cfg,candidate,service,rid,result=_formula(engine,choice="both")
    option=candidate.options[1]
    assert 'SUM("increment") - SUM("coupon") - SUM("channel_cost")' in option.description
    assert '"promo"' in option.description
    assert json.loads(option.value)=={"schema_version":"metric_scope_formula.v1","dataset":"promo","effect_column":"increment","cost_columns":["coupon","channel_cost"]}
    if fault=="hidden_formula":
        _change_record(loop,cfg,service,candidate,options=tuple(replace(o,description=o.label) for o in candidate.options))
    if fault=="missing_response_id": _change_record(loop,cfg,service,candidate,response_id="")
    if fault=="none": assert resolve_confirmation(ConfirmationRequest.from_candidate(candidate))["response"]==option.value
    else:
        with pytest.raises(ValueError): resolve_confirmation(ConfirmationRequest.from_candidate(candidate))
        assert not any(c.get("target",{}).get("statistic")=="accounting_net" for c in snapshot_for_turn(loop).as_dict()["claims"])


@pytest.mark.parametrize("choice,expected",[("both",86),("coupon",96),("skipped",None),("unconfirmed",None),("missing_cost",None),("old_version",None)])
def test_current_aggregate_and_confirmed_formula_publish_only_accounting_value(engine,choice,expected):
    loop,cfg,candidate,service,rid,result=_formula(engine,choice="both" if choice in {"missing_cost","old_version"} else choice,missing=choice=="missing_cost")
    if choice=="old_version":
        frame=loop.context.workspace.get("promo");frame.loc[0,"order_amount"]+=1;loop.context.workspace.add("promo",frame)
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    owned=[c for c in snap.as_dict()["claims"] if c.get("target",{}).get("statistic")=="accounting_net"]
    if expected is None:
        assert not owned and ("账面净收益：证据不足" if choice=="old_version" else "账面净收益：未计算") in body
        if choice!="old_version": assert any(isinstance(c["value"],list) and c["value"]==result["measurement_records"] for c in snap.as_dict()["claims"])
    else:
        assert len(owned)==1 and float(owned[0]["value"])==expected and owned[0]["unit"] is None
        assert result["measurement_records"][0]["increment_sum"]==110
        assert result["measurement_records"][0]["coupon_sum"]==14
        assert result["measurement_records"][0]["channel_cost_sum"]==10
        assert owned[0]["derivation"]["formula"]["cost_columns"]==(["coupon","channel_cost"] if choice=="both" else ["coupon"])
        assert len(owned[0]["basis_refs"])==(3 if choice=="both" else 2)
        assert "账面净收益："+str(expected) in body and "不授予增量、促销因果" in body and not has_number(body, 'order_amount_sum', 120)
        assert any(c["value"]==result["measurement_records"] for c in snap.as_dict()["claims"])
        forged=json.loads(draft(snap));forged["sections"][0]["parts"].append({"kind":"claim","ref":"c_forged_net"})
        body,error=publish(loop,json.dumps(forged));assert error is None
        assert "c_forged_net" not in [t["ref"] for t in loop._accepted_answer["render_trace"] if t["disposition"]=="accepted"]
        assert "账面净收益："+str(expected) in body


@pytest.mark.parametrize("fault",["none","changed_source","missing_answer","plan_changed_during_commit"])
def test_presentation_continuation_requires_published_same_plan_and_source(engine,fault):
    from data_agent.agent.publication.runtime import commit,register_request
    from data_agent.agent.intent import TurnIntent
    from data_agent.session.history import load_canonical_history
    loop,cfg,rid,result=_grouped(engine)
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    original=loop._accepted_answer;ref=loop.messages[-1]["answer_ref"]
    text="请改成分析师表达，保留同一限制。"
    loop.messages.append({"role":"user","content":text,"request_id":"msg_group_reword"})
    intent=TurnIntent("result_followup","clear","data_loaded","follow_up","answer_directly",requested_outputs=[{"kind":"presentation","exact_span":text}])
    register_request(loop,text,intent);loop.context.turn_intent=intent
    assert loop.context.analysis_state.answer_requirements[-1]["source_answer_id"]==original["answer_id"]
    if fault=="changed_source":
        frame=loop.context.workspace.get("sales");frame.loc[0,"amount"]=99;loop.context.workspace.add("sales",frame)
    if fault=="missing_answer": (cfg.sessions_resolved/loop.session_id/ref["path"]).unlink()
    snap=snapshot_for_turn(loop);req=next(r for r in snap.as_dict()["requirements"] if r["text"]==text)
    if fault in {"changed_source","missing_answer"}:
        assert not req["claim_ids"] and req["gap"]["status"]=="evidence_insufficient"
    else:
        assert set(req["claim_ids"])=={t["ref"] for t in original["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
        body,error=_open(loop,snap,req,"金额和记录计数属于不同口径；当前观测仍不能确定未来行动阈值。")
        assert error is None and has_number(body, 'amount_sum', 20.0)
        if fault=="plan_changed_during_commit":
            loop.context.analysis_state.analysis_plan={"id":"changed_plan"}
            before=load_canonical_history(loop.session_id)
            assert commit(loop,{"role":"assistant"},body)
            assert load_canonical_history(loop.session_id)==before


@pytest.mark.parametrize("fault",["changed_derived","changed_source","wrong_result_dataset"])
def test_stale_source_or_wrong_derived_row_cannot_bind(engine,fault):
    loop,cfg,rid,result=_grouped(engine)
    if fault in {"changed_derived","changed_source"}:
        name="by_channel" if fault=="changed_derived" else "sales"
        frame=loop.context.workspace.get(name);frame.loc[0,"amount_sum" if fault=="changed_derived" else "amount"]=99
        loop.context.workspace.add(name,frame)
    else:
        from tests.test_r3_comparison_host_claims import _tamper
        result["dataset"]="foreign_derived";_tamper(loop,cfg,rid,result)
    snap=snapshot_for_turn(loop)
    assert not any(c["basis_refs"][0]["receipt_id"]==rid for c in snap.as_dict()["claims"])
    body,error=publish(loop,draft(snap));assert error is None
    assert not has_number(body, 'amount_sum', 20.0) and "证据不足" in body


def test_auto_named_grouped_result_requires_one_recorded_derived_identity(engine):
    loop,cfg=engine;loop.context.workspace.add("sales",_source())
    request(loop,"计算自动命名分组结果",{'kind': 'table', 'scope': {'datasets': ['sales']}})
    rid,result=execute(loop,"transform_data",{"name":"sales","operation":"group_aggregate","group_by":["channel"],"aggregations":[{"column":"amount","functions":["sum","count","size"]},{"column":"order_id","functions":["nunique"]}]})
    target=result["dataset"]
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    assert target!="sales" and target in receipt["data_identities"]
    snap=snapshot_for_turn(loop)
    assert any(c["value"]==result["measurement_records"] for c in snap.as_dict()["claims"])
    # An unrelated derived frame is not a second authority; the original result names the exact one.
    loop.context.workspace.derive("sales","other_derived",loop.context.workspace.get(target),expression="independent derived copy")
    assert snapshot_for_turn(loop).as_dict()["claims"]==snap.as_dict()["claims"]
    from tests.test_r3_comparison_host_claims import _tamper
    result["dataset"]="other_derived";_tamper(loop,cfg,rid,result)
    assert not snapshot_for_turn(loop).as_dict()["claims"]


def test_proven_old_source_is_local_gap_beside_current_grouped_result(engine):
    loop,cfg,old_rid,result=_grouped(engine)
    loop.context.workspace.add("current_sales",_source())
    request(loop,"保留独立当前分组结果",{'kind': 'table', 'scope': {'datasets': ['current_sales']}})
    rid,result=execute(loop,"transform_data",{"name":"current_sales","operation":"group_aggregate","group_by":["channel"],"aggregations":[{"column":"amount","functions":["sum","count","size"]},{"column":"order_id","functions":["nunique"]}]})
    frame=loop.context.workspace.get("sales");frame.loc[0,"amount"]=99;loop.context.workspace.add("sales",frame)
    snap=snapshot_for_turn(loop);claims=snap.as_dict()["claims"]
    assert claims and all(c["basis_refs"][0]["receipt_id"]==rid for c in claims)
    assert not any(c["basis_refs"][0]["receipt_id"]==old_rid for c in claims)
    body,error=publish(loop,draft(snap));assert error is None
    assert has_number(body, 'amount_sum', 20.0) and "保留分组各计数、原始行数和观测日期：证据不足" in body
    assert "current_sales" in visible_text(body)


def test_tool_schema_executes_nunique_without_collapsing_other_counts():
    from data_agent.session.workspace import workspace
    from data_agent.tools.registry import registry

    registry._ensure_discovered()
    source_name = "r3_nunique_source"
    target_name = "r3_nunique_groups"
    workspace.add(source_name, pd.DataFrame({
        "channel": ["A", "A", "A", "B"],
        "order_id": ["X", "X", "Y", None],
        "amount": [10.0, None, 10.0, None],
    }))
    try:
        result = registry.execute("transform_data", {
            "name": source_name, "operation": "group_aggregate", "group_by": ["channel"],
            "aggregations": [
                {"column": "amount", "functions": ["sum", "count", "size"]},
                {"column": "order_id", "functions": ["nunique"]},
            ],
            "save_as": target_name,
        })
        assert json.loads(result.to_cli())["rows"] == 2
        frame = workspace.get(target_name).set_index("channel")
        assert frame.loc["A", ["amount_sum", "amount_count", "amount_size", "order_id_nunique"]].tolist() == [20, 2, 3, 2]
        assert pd.isna(frame.loc["B", "amount_sum"])
        assert frame.loc["B", ["amount_count", "amount_size", "order_id_nunique"]].tolist() == [0, 1, 0]
    finally:
        workspace._datasets.pop(source_name, None)
        workspace._datasets.pop(target_name, None)
        workspace._metadata.pop(source_name, None)
        workspace._metadata.pop(target_name, None)

from tests.test_trusted_publication_semantics import engine


from tests.test_trusted_publication_runtime import request, draft
from tests.test_trusted_publication_semantics import execute
from data_agent.agent.publication.runtime import snapshot_for_turn, publish


def _grouped(engine, *, dated=False):
    loop, cfg=engine
    frame=_source()
    if dated: frame["date"]=pd.date_range("2026-09-01",periods=4)
    loop.context.workspace.add("sales",frame)
    request(loop,"保留分组各计数、原始行数和观测日期",[{'kind':'table','scope':{'datasets':['sales']}},{'kind':'measurement','scope':{'datasets':['sales'],'quantity':'rows'}}]+([{'kind':'measurement','scope':{'datasets':['sales'],'quantity':'calendar_days'}}] if dated else []))
    rid,result=execute(loop,"transform_data",{
        "name":"sales","save_as":"by_channel","operation":"group_aggregate","group_by":["channel"],
        "aggregations":[{"column":"amount","functions":["sum","count","size"]},{"column":"order_id","functions":["nunique"]}],
    })
    return loop,cfg,rid,result


def _open_raw(snapshot,req,text):
    from data_agent.agent.publication.contracts import encode
    return encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,"sections":[{"requirement_ids":[req["id"]],"parts":[{"kind":"claim","ref":cid} for cid in req["claim_ids"]]+[{"kind":"text","purpose":req["open_purposes"][0],"text":text,"claim_refs":req["claim_ids"]}]}]})


def _open(loop,snapshot,req,text):
    from tests.test_publication_audit_view import AuditClient
    loop.client=AuditClient(["accept"])
    return publish(loop,_open_raw(snapshot,req,text))


def _formula(engine,*,choice="both",columns=None,missing=False):
    from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.session.history import load_canonical_history
    loop,cfg=engine
    frame=pd.DataFrame({"channel":["all"]*4,"order_amount":[20,25,35,40],"increment":[20,30,25,35],"coupon":[3,4,2,5],"channel_cost":[2,3,4,1]})
    if missing: frame["channel_cost"]=float("nan")
    loop.context.workspace.add("promo",frame)
    request(loop,"计算账面净收益",{'kind': 'measurement', 'scope': {'datasets': ['promo'], 'metrics': ['账面净收益'], 'quantity': 'value'}})
    history=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="aggregate_turn",workspace=loop.context.workspace,canonical_history=history,source_message_ref=history.messages[-1]["request_id"],exact_span="账面净收益",dataset="promo",column="increment",cost_scopes=[["coupon"],["coupon","channel_cost"]])
    assert candidate is not None
    service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry());service.request(candidate)
    record=service.checkpoint(loop.session_id)
    if choice is not None:
        response=candidate.options[0 if choice=="coupon" else 1].value if choice in {"both","coupon"} else choice
        service.respond(loop.session_id,candidate.confirmation_id,response,record.version,"aggregate_choice")
    if columns is not None: request(loop,"报告已观测的订单金额原列合计",{'kind':'table','scope':{'datasets':['promo']}})
    rid,result=execute(loop,"transform_data",{"name":"promo","save_as":"promo_group","operation":"group_aggregate","group_by":["channel"],"aggregations":[{"column":col,"functions":["sum"]} for col in (columns if columns is not None else ["order_amount","increment","coupon","channel_cost"])]})
    return loop,cfg,candidate,service,rid,result


def _change_record(loop,cfg,service,candidate,**updates):
    from dataclasses import replace
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.agent.confirmation.models import ConfirmationEvent
    record=service.get(loop.session_id,candidate.confirmation_id)
    changed=replace(record,version=record.version+1,**updates)
    ConfirmationStore(cfg.sessions_resolved,loop.session_id).append(ConfirmationEvent(event_id="changed_aggregate_scope",confirmation_id=record.confirmation_id,session_id=loop.session_id,event_type="changed",version=changed.version,occurred_at=record.updated_at,record=changed))
