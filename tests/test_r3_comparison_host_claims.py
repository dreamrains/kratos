"""Comparison rows keep independent receipt values and actual row counts."""
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number, has_record

from copy import deepcopy

import pytest

import json
def _values(snapshot, dataset):
    return {c["label"]:c["value"] for c in snapshot.as_dict()["claims"] if c["scope"]["dataset"]==dataset}


def _tamper(loop,cfg,rid,result):
    import hashlib
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    path=cfg.sessions_resolved/loop.session_id/receipt["detail_ref"]["path"]
    path.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
    receipt["detail_ref"]["sha256"]="sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
    receipt["structured_result_sha256"]="sha256:"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def _action(loop,span="有条件行动建议"):
    _v2_request(loop,span,kind="conditional_action")
    return loop.context.analysis_state.answer_requirements[-1]["id"]


def _dimensional(loop):
    import pandas as pd
    loop.context.workspace.add("paid",pd.DataFrame({"date":pd.to_datetime(["2026-09-01"]*3+["2026-09-02"]*4),
        "channel":["paid"]*7,"revenue":[500,500,750,300,300,300,420]}))
    _v2_request(loop,"比较paid收入",[{'kind': 'measurement', 'scope': {'datasets': ['paid'], 'metrics': ['revenue'], 'quantity': 'sum'}}, {'kind': 'measurement', 'scope': {'datasets': ['paid'], 'metrics': ['revenue'], 'quantity': 'difference'}}, {'kind': 'measurement', 'scope': {'datasets': ['paid'], 'metrics': ['revenue'], 'quantity': 'relative_change'}}, {'kind': 'measurement', 'scope': {'datasets': ['paid'], 'quantity': 'rows'}}, {'kind': 'measurement', 'scope': {'datasets': ['paid'], 'quantity': 'calendar_days'}}])
    return _v2_execute(loop,"compare_periods",{"name":"paid","date_col":"date","metrics":"revenue","dimensions":"channel",
        "period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"})


def test_dimensional_comparison_uses_current_fact_refs_and_rejects_wrong_delta(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.native import resolve_native_claims
    loop,cfg=engine;rid,result=_dimensional(loop)
    host=snapshot_for_turn(loop);values=_values(host,"paid")
    assert values["revenue / paid：前期"]==1750 and values["revenue / paid：后期"]==1320
    assert values["revenue / paid：差值"]==-430 and values["revenue / paid：相对变化"]==-24.57
    assert values["前期记录数"]==3 and values["后期记录数"]==4
    body,error=publish(loop,_v2_draft(host));assert error is None and "-430" in body
    wrong=deepcopy(result);wrong["comparisons"][0]["revenue"]["exact_aggregates"]["diff"]=-420
    _tamper(loop,cfg,rid,wrong)
    with pytest.raises(ValueError,match="相减"):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    _tamper(loop,cfg,rid,result)
    loop.context.workspace.add("paid",loop.context.workspace.get("paid").assign(revenue=0))
    with pytest.raises(ValueError):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)



def test_dimensional_result_does_not_steal_simple_action_gap(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=_actual_comparisons(engine);_dimensional(loop);action=_action(loop)
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    answer=loop._accepted_answer
    assert has_number(body, 'revenue / paid：差值', -430) and has_number(body, 'amount：后期', 11)
    assert sum(t["kind"]=="gap" and t["ref"]==action for t in answer["render_trace"])==1
    assert next(o for o in answer["requirement_outcomes"] if o["requirement_id"]==action)["status"]=="failed"



def test_two_independent_comparisons_keep_values_and_more_than_two_rows(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=_actual_comparisons(engine);host=snapshot_for_turn(loop)
    for i in (1,2):
        values=_values(host,"src_"+str(i))
        assert [values["amount："+k] for k in ("前期","后期","差值","相对变化")]==[10*i,11*i,i,10]
        assert values["前期记录数"]==3 and values["后期记录数"]==4
    body,error=publish(loop,_v2_draft(host));assert error is None
    assert "src_1" in visible_text(body) and "src_2" in visible_text(body) and "单位未知" in body
    assert {c["scope"]["dataset"] for c in host.as_dict()["claims"]}=={"src_1","src_2"}
    assert all(c["scope"]["dataset"]!="合计" for c in host.as_dict()["claims"])



def test_action_request_keeps_independent_comparisons_and_binds_one_gap(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=_actual_comparisons(engine);action=_action(loop)
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    assert has_number(body, 'amount：后期', 11) and has_number(body, 'amount：后期', 22)
    assert sum(t["kind"]=="gap" and t["ref"]==action for t in loop._accepted_answer["render_trace"])==1
    malformed=json.loads(_v2_draft(host));malformed["sections"].append({"requirement_ids":["old-action"],"parts":[{"kind":"text","purpose":"conditional_action","text":"立即执行。","claim_refs":[]}]})
    body,error=publish(loop,json.dumps(malformed));assert error is None and "立即执行。" not in body
    assert any(i["code"]=="unknown_requirement_ref" for i in loop._accepted_answer["issues"])



def test_multiple_user_action_clauses_are_quoted_without_choosing_a_branch(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.service import PublicationService
    from tests.test_r3_comparison_action_inputs import reviewer
    loop,_=_actual_comparisons(engine)
    condition="只有下一同口径窗口达到目标且成本不高于本期时才小试"
    otherwise="否则暂停增加预算并复核"
    current=[_action(loop,condition),_action(loop,otherwise)]
    host=snapshot_for_turn(loop);calls=[]
    proposal=json.loads(_v2_draft(host));proposal["sections"].append({"requirement_ids":current,
        "parts":[{"kind":"text","purpose":"conditional_action","text":condition+"；"+otherwise,"claim_refs":[]}]})
    answer=PublicationService(host,auditor=reviewer("accept",calls)).publish(json.dumps(proposal)).as_dict()
    assert len(calls)==1 and condition in answer["body"] and otherwise in answer["body"]
    assert all(o["status"]=="answered" for o in answer["requirement_outcomes"])
    bad=deepcopy(proposal);bad["sections"][-1]["parts"][0]["text"]="立即增加预算。"
    refused=PublicationService(host,auditor=reviewer("reject",[])).publish(json.dumps(bad)).as_dict()
    assert "立即增加预算。" not in refused["body"] and has_number(refused["body"], 'amount：后期', 22)
    assert all(o["status"]=="failed" for o in refused["requirement_outcomes"] if o["requirement_id"] in current)



def test_terminal_host_comparison_does_not_depend_on_prose_gate(engine,monkeypatch):
    import sys
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=_actual_comparisons(engine)
    monkeypatch.setitem(sys.modules,"data_agent.agent.publication_synthesis",None)
    unsafe="立即加预算。"
    assert publish(loop,unsafe)[1]
    body,error=publish(loop,unsafe);assert error is None
    assert unsafe not in body and has_number(body, 'amount：前期', 10) and has_number(body, 'amount：后期', 11) and has_number(body, 'amount：差值', 1)
    claims=snapshot_for_turn(loop).as_dict()["claims"]
    assert {c["scope"]["dataset"] for c in claims}=={"src_1","src_2"}
    assert any(c["value"]==10 and c["unit"]=="percent" for c in claims)


def test_terminal_composes_current_described_table_with_comparison(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=_actual_comparisons(engine)
    _v2_request(loop,"描述 F-SALES 当前记录",[{'kind':'measurement','scope':{'datasets':['F-SALES'],'quantity':q}} for q in ['rows','sum','calendar_days']])
    _v2_execute(loop,"describe_dataset",{"name":"F-SALES"})
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    values={(c["scope"]["dataset"],c["label"]):c["value"] for c in host.as_dict()["claims"]}
    assert values[("F-SALES","记录数")]==12 and values[("F-SALES","amount：sum")]==120
    assert values[("F-SALES","观测日期含首尾日数")]==12
    assert values[("src_1","amount：前期")]==10 and values[("src_1","amount：后期")]==11
    assert has_number(body, 'amount：sum', 120) and has_number(body, 'amount：后期', 11)


def test_result_links_require_current_requirement_receipt_fields_and_version(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    import pandas as pd
    loop,_=_actual_comparisons(engine)
    _v2_request(loop,"F-SALES 原值合计",{'kind': 'measurement', 'scope': {'datasets': ['F-SALES'], 'metrics': ['amount'], 'quantity': 'sum'}})
    _v2_execute(loop,"describe_dataset",{"name":"F-SALES"})
    first=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(first));assert error is None
    assert all(o["status"]=="answered" for o in loop._accepted_answer["requirement_outcomes"])
    loop.context.workspace.add("F-SALES",pd.DataFrame({"amount":[999]}))
    current=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(current));assert error is None
    assert not has_number(body, 'amount：sum', 120) and has_number(body, 'amount：后期', 11)
    reqs={r["text"]:r["id"] for r in current.as_dict()["requirements"]}
    outcomes={o["requirement_id"]:o["status"] for o in loop._accepted_answer["requirement_outcomes"]}
    assert outcomes[reqs["F-SALES 原值合计"]]=="evidence_insufficient"
    assert outcomes[reqs["比较 src_1"]]=="answered"
    malformed=json.loads(_v2_draft(current));malformed["sections"].append({"requirement_ids":["rq_foreign"],"parts":[{"kind":"claim","ref":"claim_foreign"}]})
    safe,error=publish(loop,json.dumps(malformed));assert error is None and has_number(safe, 'amount：后期', 11)
    assert any(i["code"]=="unknown_requirement_ref" for i in loop._accepted_answer["issues"])


def test_missing_intent_outputs_do_not_publish_unsafe_comparison_prose(engine):
    from data_agent.agent.publication.runtime import publish
    loop,_=_actual_comparisons(engine)
    prose="本期已经满足下一窗口条件，请立即加预算。"
    assert publish(loop,prose)[1]
    body,error=publish(loop,prose);assert error is None
    assert has_number(body, 'amount：前期', 10) and has_number(body, 'amount：后期', 11) and prose not in body
    assert not any(t["kind"]=="text" and t["disposition"]=="accepted" for t in loop._accepted_answer["render_trace"])


def test_evidence_records_do_not_hide_distinct_comparison_windows_or_duplicate_result(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.tools.registry import registry
    loop,_=_actual_comparisons(engine)
    args={"name":"src_1","date_col":"date","metrics":"amount","period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"}
    result=registry.execute("compare_periods",args)
    repeat=loop._record_turn_tool_result("compare_periods",result.summary,args,"distinct-repeat-call",result.data or json.loads(result.summary))
    assert repeat and len([r for r in loop.context.analysis_state.tool_receipts if r["tool_name"]=="compare_periods"])==3
    # Advisory evidence never replaces or repeats a closed measurement.
    loop.context.analysis_state.evidence_records.append({"id":"advisory","claim":"amount is 999","confidence":"high"})
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    assert len([c for c in host.as_dict()["claims"] if c["scope"]["dataset"]=="src_1" and c["target"]["business_product"]["kind"]=="measurement"])==20  # both immutable receipts remain auditable; only declared production renders
    assert sum(row==['amount：前期','10.0（单位未知）'] for table in table_rows(body) for row in table)==1
    assert "amount is 999" not in body
    # A different exact window remains a distinct result even if totals match.
    _v2_request(loop,"比较src_1的扩展窗口",[{'kind': 'measurement', 'scope': {'datasets': ['src_1'], 'quantity': 'sum', 'parameters': {'period_a': '2026-08-31~2026-09-01'}}}, {'kind': 'measurement', 'scope': {'datasets': ['src_1'], 'quantity': 'difference', 'parameters': {'period_a': '2026-08-31~2026-09-01'}}}, {'kind': 'measurement', 'scope': {'datasets': ['src_1'], 'quantity': 'relative_change', 'parameters': {'period_a': '2026-08-31~2026-09-01'}}}, {'kind': 'measurement', 'scope': {'datasets': ['src_1'], 'quantity': 'rows', 'parameters': {'period_a': '2026-08-31~2026-09-01'}}}, {'kind': 'measurement', 'scope': {'datasets': ['src_1'], 'quantity': 'calendar_days', 'parameters': {'period_a': '2026-08-31~2026-09-01'}}}])
    _v2_execute(loop,"compare_periods",{**args,"period_a":"2026-08-31~2026-09-01"})
    changed=snapshot_for_turn(loop)
    assert len([c for c in changed.as_dict()["claims"] if c["scope"]["dataset"]=="src_1" and c["target"]["business_product"]["kind"]=="measurement"])==30
    assert len([c for c in changed.as_dict()["claims"] if c["scope"]["dataset"]=="src_1" and c["target"]["business_product"]["kind"]=="table"])==6
    assert {c["value"] for c in changed.as_dict()["claims"] if c["label"]=="前期含首尾日数"}=={1,2}



def test_python_calculation_does_not_hide_six_native_comparison_receipts(engine):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=_actual_comparisons(engine)
    for i in range(3,7):
        name="src_"+str(i)
        loop.context.workspace.add(name,pd.DataFrame({"date":pd.to_datetime(["2026-09-01"]*3+["2026-09-02"]*4),"amount":[2*i,3*i,5*i,2*i,3*i,5*i,i]}))
        _v2_request(loop,"比较 "+name,[{'kind':'measurement','scope':{'datasets':[name],'quantity':q}} for q in ['sum','difference','relative_change','rows','calendar_days']])
        _v2_execute(loop,"compare_periods",{"name":name,"date_col":"date","metrics":"amount","period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"})
    _v2_request(loop,"保留独立Python结果",{'kind': 'table', 'scope': {'datasets': ['src_1']}})
    python,_=_v2_execute(loop,"run_python",{"code":"df=get_dataset('src_1'); result={'rows':len(df)}","purpose":"original rows"})
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    for i in range(1,7):assert _values(host,"src_"+str(i))["amount：后期"]==11*i
    assert len([c for c in host.as_dict()["claims"] if c["target"]["tool"]=="compare_periods" and c["target"]["business_product"]["kind"]=="measurement"])==60
    assert has_number(body, 'rows', 7) and any(c["basis_refs"][0]["receipt_id"]==python for c in host.as_dict()["claims"])
    assert all(o["status"]=="answered" for o in loop._accepted_answer["requirement_outcomes"])



def test_one_broken_source_only_loses_its_own_rows(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=_actual_comparisons(engine)
    receipt=loop.context.analysis_state.tool_receipts[-1]
    (cfg.sessions_resolved/loop.session_id/receipt["detail_ref"]["path"]).write_text("broken",encoding="utf-8")
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    assert set(c["scope"]["dataset"] for c in host.as_dict()["claims"])=={"src_1"}
    assert has_number(body, 'amount：前期', 10) and "比较 src_2：证据不足" in body
    assert [o["status"] for o in loop._accepted_answer["requirement_outcomes"]]==["answered","evidence_insufficient"]



def test_forged_difference_or_binding_does_not_publish(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.native import resolve_native_claims
    loop,cfg=_actual_comparisons(engine);receipt=loop.context.analysis_state.tool_receipts[0]
    path=cfg.sessions_resolved/loop.session_id/receipt["detail_ref"]["path"]
    result=json.loads(path.read_text(encoding="utf-8"));result["metrics"]["amount"]["diff"]=99
    _tamper(loop,cfg,receipt["id"],result)
    with pytest.raises(ValueError,match="显示值"):resolve_native_claims(session_id=loop.session_id,receipt_id=receipt["id"])
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    assert has_number(body, 'amount：后期', 22) and "比较 src_1：证据不足" in body
    wrong=json.loads(_v2_draft(host));wrong["sections"][0]={"requirement_ids":[host.as_dict()["requirements"][0]["id"]],"parts":[{"kind":"claim","ref":host.as_dict()["requirements"][1]["claim_ids"][0]}]}
    body,error=publish(loop,json.dumps(wrong));assert error is None
    assert any(i["code"]=="unbound_deliverable_ref" for i in loop._accepted_answer["issues"])



def test_zero_denominator_keeps_absolute_result_and_other_source(engine):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=_actual_comparisons(engine,frames={1:pd.DataFrame({"date":pd.to_datetime(["2026-09-01"]*2+["2026-09-02"]*3),"amount":[0,0,1,1,3]})})
    _v2_execute(loop,"compare_periods",{"name":"src_1","date_col":"date","metrics":"amount","period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"})
    host=snapshot_for_turn(loop);values=_values(host,"src_1")
    assert [values["amount："+k] for k in ("前期","后期","差值","相对变化")]==[0,5,5,None]
    assert values["前期记录数"]==2 and values["后期记录数"]==3
    body,error=publish(loop,_v2_draft(host));assert error is None
    assert has_pair(body,'amount：相对变化','未知') or 'amount：相对变化：未知' in visible_text(body)
    assert has_number(body, 'amount：后期', 22)



def test_two_decimal_relative_value_and_negative_base_keep_independent_rows(engine):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.native import resolve_native_claims
    frames={i:pd.DataFrame({"date":pd.to_datetime(["2026-09-01","2026-09-02"]),"amount":[a,b]}) for i,(a,b) in enumerate(((21,25),(-21,-17)),1)}
    loop,cfg=_actual_comparisons(engine,frames=frames)
    host=snapshot_for_turn(loop)
    assert _values(host,"src_1")["amount：相对变化"]==19.05
    assert _values(host,"src_2")["amount：相对变化"]==19.05
    receipt=loop.context.analysis_state.tool_receipts[-1]
    result=json.loads((cfg.sessions_resolved/loop.session_id/receipt["detail_ref"]["path"]).read_text(encoding="utf-8"))
    result["metrics"]["amount"]["change_pct"]=19.04;_tamper(loop,cfg,receipt["id"],result)
    with pytest.raises(ValueError,match="相对变化"):resolve_native_claims(session_id=loop.session_id,receipt_id=receipt["id"])
    changed=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(changed));assert error is None
    assert has_number(body, 'amount：后期', 25) and "比较 src_2：证据不足" in body



def test_current_registered_chart_is_linked_only_to_matching_comparison(engine,monkeypatch):
    import plotly.graph_objects as go
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    monkeypatch.setattr(go.Figure,"to_image",lambda *a,**k:(_ for _ in ()).throw(RuntimeError("no static renderer")))
    loop,_=_actual_comparisons(engine)
    _v2_request(loop,"src_1当前探索图",{'kind': 'chart', 'scope': {'datasets': ['src_1']}})
    _v2_execute(loop,"create_chart",{"data":"src_1","chart_type":"line","x_col":"date","y_col":"amount","purpose":"exploratory","aggregation":"sum"})
    host=snapshot_for_turn(loop);artifact=host.as_dict()["artifacts"][0]
    assert artifact["target"]["dataset"]=="src_1" and artifact["target"]["tool"]=="create_chart"
    body,error=publish(loop,_v2_draft(host));assert error is None and "charts/" in body
    assert sum(t["kind"]=="artifact" and t["disposition"]=="accepted" for t in loop._accepted_answer["render_trace"])==1
    wrong=json.loads(_v2_draft(host));wrong["sections"].append({"requirement_ids":[host.as_dict()["requirements"][1]["id"]],"parts":[{"kind":"artifact","ref":artifact["id"]}]})
    body,error=publish(loop,json.dumps(wrong));assert error is None
    assert any(i["code"]=="unbound_deliverable_ref" for i in loop._accepted_answer["issues"])
    loop.context.workspace.add("src_1",pd.DataFrame({"date":pd.to_datetime(["2026-09-01","2026-09-02"]),"amount":[999,999]}))
    current=snapshot_for_turn(loop)
    assert current.as_dict()["artifacts"]==[] and _values(current,"src_2")["amount：后期"]==22


from tests.test_trusted_publication_semantics import engine,execute as _v2_execute
from tests.test_trusted_publication_runtime import request as _v2_request,draft as _v2_draft


def _actual_comparisons(engine,frames=None):
    import pandas as pd
    loop,cfg=engine
    loop.context.workspace.add("F-SALES",pd.DataFrame({"date":pd.date_range("2026-09-01",periods=12),"amount":[10]*12}))
    for n in (1,2):
        name="src_"+str(n)
        loop.context.workspace.add(name,pd.DataFrame({"date":pd.to_datetime(["2026-09-01"]*3+["2026-09-02"]*4),"amount":[2*n,3*n,5*n,2*n,3*n,5*n,n]}))
        if frames and n in frames: loop.context.workspace.add(name,frames[n])
        _v2_request(loop,"比较 "+name,[{'kind':'measurement','scope':{'datasets':[name],'quantity':q}} for q in ['sum','difference','relative_change','rows','calendar_days']])
        _,result=_v2_execute(loop,"compare_periods",{"name":name,"date_col":"date","metrics":"amount","period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"})
        if not frames or n not in frames: assert result["period_a"]["rows"]==3 and result["period_b"]["rows"]==4
        else: assert result["period_a"]["rows"]+result["period_b"]["rows"]==len(frames[n])
    return loop,cfg
