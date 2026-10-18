from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number, has_record
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.loop import AgentLoop
from datetime import date, timedelta
import copy
import json

import pytest








def test_packet_carries_curve_values_that_the_final_model_must_not_reconstruct_from_history(engine):
    import numpy as np
    import pandas as pd
    from scipy.optimize import brentq
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine
    x=np.arange(1,63,dtype=float); design=np.column_stack([np.ones(62),x])
    wave=np.sin(x); noise=wave-design@np.linalg.lstsq(design,wave,rcond=None)[0]
    fitted=.18800129*np.exp(-.01*x)
    def score(scale):
        observed=fitted*np.exp(scale*noise)
        return 1-np.sum((observed-fitted)**2)/np.sum((observed-observed.mean())**2)
    scale=brentq(lambda scale:score(scale)-.98240474,0,.1)
    loop.context.workspace.add("curve",pd.DataFrame({"x":x,"y":fitted*np.exp(scale*noise)}))
    _v2_request(loop,"拟合留存曲线并说明边界",[{'kind':k,'scope':{'datasets':['curve'],**({'quantity':'count'} if k=='measurement' else {})}} for k in ['series','fit','measurement']])
    rid,result=_v2_execute(loop,"curve_fitting",{"name":"curve","x_col":"x","y_col":"y"})
    fit=next(f for f in result["fits"] if f["family"]=="exponential")
    assert fit["parameters"]["a"]==.18800129 and fit["r_squared"]==.98240474 and result["effective_n"]==62
    snapshot=snapshot_for_turn(loop)
    exact=next(c for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["result_path"]==["fits"])
    assert exact["value"]==result["fits"] and exact["basis_refs"][0]["receipt_id"]==rid
    body,error=publish(loop,_v2_draft(snapshot));assert error is None
    assert "0.18800129" in body and "0.98240474" in body and has_number(body, 'effective_n', 62)


def test_packet_renders_period_comparison_anchors_from_receipts_not_model_text(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg,rid,result=_v2_full_period(engine)
    assert result["combined"]=={"row_count":71,"day_count":30}
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(snapshot));assert error is None
    assert has_number(body, 'revenue：前期', 1818) and has_number(body, 'revenue：后期', 684) and has_number(body, 'revenue：差值', -1134)
    assert (has_pair(body, '合并范围记录数', '71 条') or '合并范围记录数：71 条' in visible_text(body)) and (has_pair(body, '合并范围日历日数', '30 天') or '合并范围日历日数：30 天' in visible_text(body))
    claims=[c for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["result_path"][0]=="combined"]
    assert [c["value"] for c in claims]==[71,30] and all(c["basis_refs"][0]["receipt_id"]==rid for c in claims)


def test_metric_period_totals_outscore_calendar_detail_in_the_fact_budget(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg,rid,result=_v2_full_period(engine)
    snapshot=snapshot_for_turn(loop);claims=snapshot.as_dict()["claims"]
    values=[c["value"] for c in claims if c["basis_refs"][0]["result_path"][:2]==["metrics","revenue"]]
    assert values==[1818,684,-1134,-62.38]
    body,error=publish(loop,_v2_draft(snapshot));assert error is None
    assert all(str(v) in body for v in [1818,684,-1134])
    assert all(c["basis_refs"][0]["result_path"][0]!="replay" for c in claims)


@pytest.mark.parametrize("overlap",[False,True])
@pytest.mark.parametrize("fault",[None,"wrong_calendar_union","impossible_row_count"])
def test_combined_period_scope_is_retained_in_the_bounded_fact_budget(engine,overlap,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg,rid,result=_v2_full_period(engine,overlap=overlap)
    if fault:
        from tests.test_r3_comparison_host_claims import _tamper
        result["combined"]["day_count" if fault=="wrong_calendar_union" else "row_count"]=36 if fault=="wrong_calendar_union" else result["period_a"]["rows"]+result["period_b"]["rows"]+1
        _tamper(loop,cfg,rid,result)
        snapshot=snapshot_for_turn(loop)
        assert snapshot.as_dict()["claims"]==[]
        body,error=publish(loop,_v2_draft(snapshot));assert error is None and "证据不足" in body
        return
    snapshot=snapshot_for_turn(loop)
    combined={c["basis_refs"][0]["result_path"][-1]:c["value"] for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["result_path"][0]=="combined"}
    assert combined=={"row_count":71,"day_count":30}
    if overlap:
        assert result["period_a"]["rows"]+result["period_b"]["rows"]>71
        assert result["period_a"]["day_count"]+result["period_b"]["day_count"]==36
    body,error=publish(loop,_v2_draft(snapshot));assert error is None
    assert (has_pair(body, '合并范围记录数', '71 条') or '合并范围记录数：71 条' in visible_text(body)) and (has_pair(body, '合并范围日历日数', '30 天') or '合并范围日历日数：30 天' in visible_text(body))


def test_structured_result_preview_does_not_duplicate_raw_json_into_publication(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg,rid,result=_v2_full_period(engine)
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    receipt["result_preview"]='{"period_a":{"rows":46,"dates":["2026-04-07"]}}'
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(snapshot));assert error is None
    assert not has_record(body, {'rows':46}) and '2026-04-07' not in ' '.join(cell for table in table_rows(body) for row in table for cell in row)
    assert has_number(body, 'revenue：前期', 1818) and has_number(body, 'revenue：后期', 684)


def test_loop_persists_packet_without_exposing_receipts_after_finalization(engine,monkeypatch):
    from tests.test_trusted_publication_runtime import AppClient,intent_for_app
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop,_=engine;content="计算当前记录数"
    intent_for_app(monkeypatch,"result",content,{'datasets': ['orders'], 'quantity': 'rows'})
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"})
    body=loop.run_turn_structured(content).content
    message=load_session(loop.session_id)["messages"][-1]
    answer=read_answer(loop.session_id,message["answer_ref"])
    assert body==answer["body"]==message["content"] and "12" in body
    assert "本轮计算收据" not in body and "snapshot_digest" not in body
    assert len(loop.context.analysis_state.accepted_answers)==1


def test_terminal_publication_prepares_the_packet_and_rejects_unbound_comparison(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=_v2_comparison(engine)
    proposal=json.loads(_v2_draft(snapshot_for_turn(loop)))
    proposal["sections"][0]["parts"].append({"kind":"claim","ref":"foreign_comparison"})
    body,error=publish(loop,json.dumps(proposal))
    assert error is None and has_number(body, 'amount：前期', 60) and has_number(body, 'amount：后期', 120) and has_number(body, 'amount：差值', 60)
    assert any(i["code"]=="unknown_claim_ref" for i in loop._accepted_answer["issues"])
    assert not loop.context.analysis_state.accepted_answers


def test_three_point_limited_curve_does_not_require_m02_fit_binding(engine):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    loop.context.workspace.add("three",pd.DataFrame({"x":[1,2,3],"value":[10,20,20]}))
    _v2_request(loop,"观察当前三点",{'kind': 'series', 'scope': {'datasets': ['three']}})
    _,result=_v2_execute(loop,"curve_fitting",{"name":"three","x_col":"x","y_col":"value"})
    assert result["fits"]==[] and result["reason_code"]=="insufficient_points" and result["effective_n"]==3
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    assert all(str(v) in body for v in (10,20)) and "不支持外推或因果" in body
    assert not any(c["value"] for c in host.as_dict()["claims"] if c["basis_refs"][0]["result_path"]==["fits"])


def test_confirmed_result_cannot_finish_without_a_current_computation_receipt(engine):
    _v2_confirmed_without_result(engine,"促销净收益")


def test_confirmed_analysis_goal_is_guarded_when_semantic_output_is_unavailable(engine):
    _v2_confirmed_without_result(engine,"evaluate the requested result")


def test_terminal_publication_rebuilds_a_ready_preview_after_late_evidence(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    _v2_request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    early,_=_v2_execute(loop,"describe_dataset",{"name":"orders"})
    preview=snapshot_for_turn(loop)
    _v2_request(loop,"比较两期金额",[{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'sum'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'difference'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'relative_change'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'calendar_days'}}])
    late,_=_v2_execute(loop,"compare_periods",_v2_compare_args())
    loop.context.analysis_state.evidence_records.append({"id":"ev_annotation","claim":"自报高置信度","confidence":"high"})
    final=snapshot_for_turn(loop)
    assert final.digest!=preview.digest
    body,error=publish(loop,_v2_draft(final));assert error is None
    assert "12" in body and has_number(body, 'amount：前期', 60) and has_number(body, 'amount：后期', 120)
    assert {p["receipt_id"] for c in final.as_dict()["claims"] for p in c["basis_refs"]}=={early,late}
    assert "自报高置信度" not in body


def test_packet_digest_changes_when_validation_or_result_content_changes(engine):
    loop,_=_python_result(engine,{'metric':'收入','value':10},content='分析收入')
    first=snapshot_for_turn(loop)
    loop.context.analysis_state.verification_reports=[{'overall_status':'fail'}]
    assert snapshot_for_turn(loop).digest==first.digest  # old parallel prose verdict is no longer authority
    receipt=loop.context.analysis_state.tool_receipts[-1]
    receipt['detail_ref']['sha256']='sha256:changed'
    changed=snapshot_for_turn(loop)
    assert changed.digest!=first.digest and not changed.as_dict()['claims']
    assert _host_answer(changed)['requirement_outcomes'][0]['status']=='evidence_insufficient'


def test_python_business_output_outranks_replay_metadata_and_keeps_tail_lines(engine):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine
    loop.context.workspace.add("weighted",pd.DataFrame({"rate":[.17080,.16803]}))
    _v2_request(loop,"比较原普通与加权D1均值",{'kind': 'table', 'scope': {'datasets': ['weighted']}})
    rid,result=_v2_execute(loop,"run_python",{"code":"df=get_dataset('weighted'); result={'ordinary':float(df['rate'].iloc[0]),'weighted':float(df['rate'].iloc[1]),'weighted_delta':float(df['rate'].iloc[0]-df['rate'].iloc[1])}; print('概览完成\\nD1普通均值=17.080%\\nD1加权均值=16.803%\\nweighted_delta=0.00277')","purpose":"actual weighted means"})
    snapshot=snapshot_for_turn(loop);claims=snapshot.as_dict()["claims"]
    assert len(claims)==1 and claims[0]["value"]["weighted_delta"]==pytest.approx(.00277)
    assert claims[0]["basis_refs"][0]["result_path"]==["result_data"]
    assert claims[0]["value"]==result["result_data"]
    body,error=publish(loop,_v2_draft(snapshot));assert error is None
    assert "weighted_delta" in visible_text(body) and "replay" not in visible_text(body) and "code_sha256" not in visible_text(body) and "risk_level" not in visible_text(body)


def test_all_group_request_uses_natural_order_and_retains_twelve_complete_groups(engine):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine
    loop.context.workspace.add("groups",pd.DataFrame({"name":[f"segment_{i}" for i in range(12)],"revenue":[i*100 for i in range(12)],"count":[i*10 for i in range(12)]}))
    _v2_request(loop,"逐一列出全部分组",{'kind': 'table', 'scope': {'datasets': ['groups']}})
    rid,result=_v2_execute(loop,"run_python",{"code":"df=get_dataset('groups'); result={'groups':df.to_dict('records')}","purpose":"all twelve original groups"})
    snapshot=snapshot_for_turn(loop);claim=snapshot.as_dict()["claims"][0]
    assert [r["name"] for r in claim["value"]["groups"]]==[f"segment_{i}" for i in range(12)]
    assert claim["value"]==result["result_data"]
    assert [(r["revenue"],r["count"]) for r in claim["value"]["groups"]]==[(i*100,i*10) for i in range(12)]
    body,error=publish(loop,_v2_draft(snapshot));assert error is None
    assert visible_text(body).index("segment_2")<visible_text(body).index("segment_10") and "segment_11" in visible_text(body)


def test_explicit_arithmetic_mismatch_is_rejected_but_correct_rounding_passes(engine):
    loop,_=_python_result(engine,{'users':22400,'rate':.051},code="df=get_dataset('original'); result={'users':int(df['users'].iloc[0]),'rate':float(df['rate'].iloc[0]),'product':float(df['users'].iloc[0]*df['rate'].iloc[0])}")
    host=snapshot_for_turn(loop)
    assert host.as_dict()['claims'][0]['value']['product']==pytest.approx(1142.4)
    bad=_claim_override(host,value=11400)
    assert bad['issues'][0]['code']=='invalid_fields' and bad['source_snapshot']==host.as_dict()
    for text,disposition in [('日新增22400人，D7留存5.1%，约为1.14万人。','reject'),('日新增22400人，D7留存5.1%，约为1142人。','accept')]:
        answer,calls=_open_answer(host,text,disposition)
        assert calls[0]['claims'][0]['value']['product']==pytest.approx(1142.4)
        assert (text in answer['body'])==(disposition=='accept')


def test_nonzero_mean_cannot_be_described_as_zero_cv_denominator(engine):
    for mean in (10.,0.):
        loop,_=_python_result(engine,{'amount':mean},code="df=get_dataset('original'); mean=float(df['amount'].mean()); std=float(df['amount'].std(ddof=0)); result={'mean':mean,'std':std,'cv':None if mean==0 else std/mean}")
        host=snapshot_for_turn(loop);value=next(c['value'] for c in host.as_dict()['claims'] if c['basis_refs'][0]['result_path']==['result_data'])
        assert value=={'mean':mean,'std':0.,'cv':None if mean==0 else 0.}
        wrong='amount 描述统计：mean=10.0、std=0.0、min=10，变差系数 CV 无定义（分母为 0）。'
        correct='amount 描述统计：mean=0.0、std=0.0，变差系数 CV 无定义（分母为 0）。' if mean==0 else 'amount 描述统计：mean=10.0、std=0.0，变差系数 CV=0。'
        answer,calls=_open_answer(host,correct,'accept');assert correct in answer['body']
        if mean:
            answer,calls=_open_answer(host,wrong,'reject');assert wrong not in answer['body']
        assert next(c['value'] for c in calls[0]['claims'] if isinstance(c['value'],dict))==value


def test_constant_sample_does_not_license_data_origin_or_population_claims(engine):
    loop,_=_python_result(engine,{'amount':10,'rows':12})
    host=snapshot_for_turn(loop)
    for text,disposition in [('amount 全等于 10，极可能是脱敏/占位/示意数据，真实业务波动为零。', 'reject'), ('amount 全等于 10；需确认该文件是否为占位或样例数据。', 'accept')]:
        answer,calls=_open_answer(host,text,disposition)
        assert len(calls)==1 and calls[0]['parts'][0]['text']==text
        assert (text in answer['body'])==(disposition=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert calls[0]['claims']==[{k:c[k] for k in ('id','label','value','unit','scope','limitations')} for c in host.as_dict()['claims']]


def test_plain_language_non_ledger_inference_is_rejected(engine):
    loop,_=_python_result(engine,{'amount':10,'rows':12})
    host=snapshot_for_turn(loop)
    for text,disposition in [('每笔 amount 都是 10。这大概率是份占位/样例数据，不是真账本。', 'reject')]:
        answer,calls=_open_answer(host,text,disposition)
        assert len(calls)==1 and calls[0]['parts'][0]['text']==text
        assert (text in answer['body'])==(disposition=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert calls[0]['claims']==[{k:c[k] for k in ('id','label','value','unit','scope','limitations')} for c in host.as_dict()['claims']]


def test_unqualified_human_rule_and_constructed_sample_claims_are_rejected(engine):
    loop,_=_python_result(engine,{'amount':10,'rows':12})
    host=snapshot_for_turn(loop)
    for text,disposition in [('样本极小（12 行）且为人为规则数据。', 'reject'), ('各来源均上涨 10%，呈现出构造样例特征，更可能是数据本身为样例。', 'reject'), ('各来源均上涨 10%；需确认该文件是否为构造样例。', 'accept')]:
        answer,calls=_open_answer(host,text,disposition)
        assert len(calls)==1 and calls[0]['parts'][0]['text']==text
        assert (text in answer['body'])==(disposition=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert calls[0]['claims']==[{k:c[k] for k in ('id','label','value','unit','scope','limitations')} for c in host.as_dict()['claims']]


@pytest.mark.parametrize("text", [
    "该数据是测试数据。",
    "该样本由机器生成。",
    "这是合成数据。",
    "这个文件是人工构造的。",
    "这些记录并非真实账本。",
])
def test_unqualified_provenance_assertions_require_evidence(text,engine):
    loop,_=_python_result(engine,{'amount':10,'rows':7})
    host=snapshot_for_turn(loop);answer,calls=_open_answer(host,text,'reject')
    assert len(calls)==1 and calls[0]['parts'][0]['text']==text
    assert (text in answer['body'])==('reject'=='accept')
    assert answer['source_snapshot']['claims']==host.as_dict()['claims']


@pytest.mark.parametrize("text", [
    "需确认该数据是否为测试数据。",
    "尚不清楚该样本是否由机器生成。",
    "无法判断这些记录是否来自真实账本。",
    "分析文件: M01-sales.csv",
])
def test_bounded_provenance_language_and_source_labels_publish(text,engine):
    loop,_=_python_result(engine,{'amount':10,'rows':7})
    host=snapshot_for_turn(loop);answer,calls=_open_answer(host,text,'accept')
    assert len(calls)==1 and calls[0]['parts'][0]['text']==text
    assert (text in answer['body'])==('accept'=='accept')
    assert answer['source_snapshot']['claims']==host.as_dict()['claims']


def test_structured_provenance_fact_licenses_the_matching_assertion_only(engine):
    loop,_=_python_result(engine,{'metadata':{'provenance':'synthetic'}})
    host=snapshot_for_turn(loop)
    assert host.as_dict()['claims'][0]['value']['metadata']['provenance']=='synthetic'
    for text,disposition in [('这是合成数据。','accept'),('该样本由机器生成。','reject')]:
        answer,calls=_open_answer(host,text,disposition)
        assert (text in answer['body'])==(disposition=='accept')
        assert calls[0]['claims'][0]['value']=={'metadata':{'provenance':'synthetic'}}


def test_missing_cost_cannot_be_rewritten_as_zero_by_pronoun(engine):
    loop,_=_python_result(engine,{'channel_cost':0,'coupon_cost':None})
    host=snapshot_for_turn(loop)
    for text,disposition in [('渠道成本字段未提供，因此净收益无法计算。口径决定怎么减，数据决定减多少，后者当前为零。', 'reject'), ('渠道成本由账本计算为零；代金券成本字段未提供，因此净收益无法计算。', 'accept')]:
        answer,calls=_open_answer(host,text,disposition)
        assert len(calls)==1 and calls[0]['parts'][0]['text']==text
        assert (text in answer['body'])==(disposition=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert calls[0]['claims']==[{k:c[k] for k in ('id','label','value','unit','scope','limitations')} for c in host.as_dict()['claims']]


def test_explicit_subquestion_requires_visible_result_or_specific_gap(engine):
    loop,_=_python_result(engine,{'收入':100},content='收入')
    _v2_request(loop,'复购率',{'kind': 'table', 'scope': {'datasets': ['original'], 'metrics': ['复购率']}})
    host=snapshot_for_turn(loop);answer=_host_answer(host)
    outcomes=answer['requirement_outcomes']
    assert [r['status'] for r in outcomes]==['answered','not_computed']
    assert '100' in answer['body'] and '复购率：未计算' in answer['body']
    assert host.as_dict()['requirements'][1]['claim_ids']==[]
    assert '复购率为20%' not in answer['body']


def test_requirement_keyword_without_result_or_gap_stays_unassessed(engine):
    loop,_=_python_result(engine,{'收入':100},content='收入')
    _v2_request(loop,'复购率',{'kind': 'table', 'scope': {'datasets': ['original'], 'metrics': ['复购率']}})
    host=snapshot_for_turn(loop);answer=_host_answer(host)
    outcomes=answer['requirement_outcomes']
    assert [r['status'] for r in outcomes]==['answered','not_computed']
    assert '100' in answer['body'] and '复购率：未计算' in answer['body']
    assert host.as_dict()['requirements'][1]['claim_ids']==[]
    assert '复购率为20%' not in answer['body']


def test_adjacent_requirement_number_does_not_cover_the_next_requirement(engine):
    loop,_=_python_result(engine,{'收入':100},content='收入')
    _v2_request(loop,'复购率',{'kind': 'table', 'scope': {'datasets': ['original'], 'metrics': ['复购率']}})
    host=snapshot_for_turn(loop);answer=_host_answer(host)
    outcomes=answer['requirement_outcomes']
    assert [r['status'] for r in outcomes]==['answered','not_computed']
    assert '100' in answer['body'] and '复购率：未计算' in answer['body']
    assert host.as_dict()['requirements'][1]['claim_ids']==[]
    assert '复购率为20%' not in answer['body']


def test_arithmetic_ignores_date_prefix_and_an_explicitly_corrected_quote(engine):
    loop,_=_python_result(engine,{'users':22400,'rate':.051},code="df=get_dataset('original'); result={'users':22400,'rate':.051,'product':float(df['users'].iloc[0]*df['rate'].iloc[0])}")
    host=snapshot_for_turn(loop)
    for text in ['2026年新增22400人，D7留存5.1%，约为1142人。','“22400人乘5.1%约为1.14万人”这个说法错误，正确约为1142人。']:
        answer,calls=_open_answer(host,text,'accept')
        assert text in answer['body'] and calls[0]['claims'][0]['value']['product']==pytest.approx(1142.4)


def test_packet_is_incomplete_without_a_successful_substantive_receipt(engine):
    loop,_=engine;_v2_request(loop,'分析数据',[{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'sum'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'difference'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'relative_change'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'calendar_days'}}])
    host=snapshot_for_turn(loop)
    assert host.as_dict()['claims']==[]
    assert _host_answer(host)['requirement_outcomes'][0]['status']=='not_computed'


def test_packet_uses_only_current_turn_receipts_and_state_roundtrip_preserves_it(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,_=engine
    old_args=dict(_v2_compare_args(),period_a="2026-09-01~2026-09-01",period_b="2026-09-02~2026-09-02")
    old,_=_v2_execute(loop,"compare_periods",old_args)
    loop.context.turn_receipt_ids=[]
    selector={"dataset":"orders","tool":"compare_periods","parameters":{"period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"}}
    _v2_request(loop,"比较当前两期",[{"kind":"measurement","scope":{"datasets":["orders"],"quantity":q,"parameters":selector["parameters"]}} for q in ["sum","difference","relative_change","rows","calendar_days"]])
    current,_=_v2_execute(loop,"compare_periods",_v2_compare_args())
    host=snapshot_for_turn(loop)
    assert {p["receipt_id"] for c in host.as_dict()["claims"] for p in c["basis_refs"]}=={current}
    body,error=publish(loop,_v2_draft(host));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    restored=AnalysisSessionState.from_dict(loop.context.analysis_state.to_dict(),loop.session_id)
    assert restored.accepted_answers==loop.context.analysis_state.accepted_answers


def test_streaming_finalization_persists_without_exposing_the_verified_appendix(engine,monkeypatch):
    from tests.test_trusted_publication_runtime import AppClient,intent_for_app
    from data_agent.session.history import load_session
    loop,_=engine;content="计算当前记录数"
    intent_for_app(monkeypatch,"result",content,{'datasets': ['orders'], 'quantity': 'rows'})
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"})
    events=list(loop.stream_turn(content));body="".join(e["text"] for e in events if e["type"]=="text_delta")
    assert not [e for e in events if e["type"]=="error"]
    assert body==load_session(loop.session_id)["messages"][-1]["content"] and "12" in body
    assert "本轮计算收据" not in body and "answer_bindings" not in body


def test_streaming_publication_rewrites_once_and_never_projects_rejected_narrative(engine,monkeypatch):
    from tests.test_trusted_publication_runtime import AppClient,intent_for_app
    from data_agent.session.public_messages import assistant_replies
    from data_agent.llm.client import Response
    loop,_=engine;content="计算当前记录数"
    intent_for_app(monkeypatch,"result",content,{'datasets': ['orders'], 'quantity': 'rows'})
    class RepairClient(AppClient):
        def chat(self,*a,**k):
            if self.called==1:
                self.called+=1
                return Response(text="这6个零值均为未观测值而非真实零，可用于LTV预测。")
            return super().chat(*a,**k)
    loop.client=RepairClient(loop,"describe_dataset",{"name":"orders"})
    events=list(loop.stream_turn(content));body="".join(e["text"] for e in events if e["type"]=="text_delta")
    assert loop.client.called==3 and "12" in body and "这6个零值" not in body
    assert "这6个零值" not in "\n".join(r["content"] for r in assistant_replies(loop.messages,loop.session_id))
    assert not [e for e in events if e["type"]=="error"]


# ── P3 (D02): claim-scoped publication checks (N01–N09, N11) ──














def test_m02_host_claims_preserve_raw_observation_and_unknown_d30(engine):
    loop,_,rid,result=_curve_actual(engine)
    host=snapshot_for_turn(loop);answer=_host_answer(host)
    point=next(c for c in host.as_dict()['claims'] if c['basis_refs'][0]['result_path']==['points',6,'y'])
    assert point['value']==result['points'][6]['y']==.2296 and point['unit'] is None
    assert '0.2296%' not in answer['body'] and '未来真实值未知' in answer['body']
    assert all(r['status']=='unvalidated' and r['validation']=='none' for r in result['scenarios'])
    assert {f['family'] for f in result['fits']}=={'power','exponential','logarithmic'}


def test_m02_registered_result_bound_chart_survives_host_rendering(engine):
    loop,cfg,rid,result=_curve_actual(engine)
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r['id']==rid)
    from data_agent.tools.analysis_flow import record_evidence_record
    from tests.test_evidence_receipts import _payload
    evidence=_payload(tool_calls=['curve_fitting'])
    evidence.update(id='ev_current_curve',dataset='渠道 A',claim='当前七个观测点的描述性拟合',result_summary='D7原值.2296，未来真实值未知',sample_size=7,time_scope='D1-D7')
    recorded=json.loads(record_evidence_record(evidence))
    assert recorded.get('evidence_id')=='ev_current_curve',recorded
    _v2_request(loop,'打开 D1-D7 curve',{'kind': 'chart', 'scope': {'datasets': ['渠道 A']}})
    _,chart=_v2_execute(loop,'create_chart',{'chart_type':'line','data':'渠道 A','x_col':'x','y_col':'actual','purpose':'evidence','evidence_ids':'ev_current_curve','result_ref':receipt['detail_ref']['path'],'title':'D1-D7 curve'})
    host=snapshot_for_turn(loop);answer=_host_answer(host)
    assert host.as_dict()['artifacts'] and answer['artifact_refs']
    artifact=answer['artifact_refs'][0]
    assert artifact['path'] in answer['body'] and 'D1-D7 curve' in answer['body']
    (cfg.sessions_resolved/loop.session_id/artifact['path']).write_text('changed',encoding='utf-8')
    assert snapshot_for_turn(loop).as_dict()['artifacts']==[]
    assert any(c['value']==.2296 for c in snapshot_for_turn(loop).as_dict()['claims'])


def test_host_keeps_current_curve_facts_when_other_receipts_fill_prompt_budget(engine):
    loop,_,rid,result=_curve_actual(engine)
    for index in range(7):
        _v2_execute(loop,'run_python',{'code':"df=get_dataset('渠道 A'); result={'context':"+repr([f'source {index} detail {item}' for item in range(20)])+"}",'purpose':f'background {index}'})
    host=snapshot_for_turn(loop);answer=_host_answer(host)
    assert any(c['basis_refs'][0]['receipt_id']==rid and c['value']==.2296 for c in host.as_dict()['claims'])
    assert answer['source_snapshot']['claims']==host.as_dict()['claims']
    prompt=publication_prompt(loop)
    assert host.digest in prompt
    from data_agent.llm.request_policy import resolve_request_budget
    from data_agent.config import get_config
    policy=resolve_request_budget(get_config().model_id,get_config(),get_config().max_tokens)
    assert policy.estimate([{'role':'system','content':prompt}])['tokens']<=policy.input_allowance
    assert len({p['receipt_id'] for c in host.as_dict()['claims'] for p in c['basis_refs']})==8


def test_m02_host_claims_require_real_unit_confirmation_and_current_binding(engine):
    loop,_,rid,result=_curve_actual(engine)
    host=snapshot_for_turn(loop)
    for fields in ({'unit':'proportion'},{'unit_status':'confirmed'},{'value':22.96}):
        answer=_claim_override(host,**fields)
        assert answer['issues'][0]['code']=='invalid_fields' and answer['source_snapshot']==host.as_dict()
    raw=json.loads(_v2_draft(host));raw['snapshot_digest']='sha256:stale'
    assert _host_answer(host,raw)['issues'][0]['code']=='stale_draft'
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r['id']==rid)
    receipt['arguments']['analysis_unit']='ratio'  # a self-reported argument is no durable confirmation
    assert all(c['unit'] is None for c in snapshot_for_turn(loop).as_dict()['claims'])


def test_m02_host_claims_keep_independent_curve_when_other_source_is_incomplete(engine):
    loop,cfg,a,ra=_curve_actual(engine,name='curve_a')
    _,_,b,rb=_curve_actual(engine,name='curve_b')
    host=snapshot_for_turn(loop)
    assert {c['scope']['dataset'] for c in host.as_dict()['claims']}=={'curve_a','curve_b'}
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r['id']==b)
    (cfg.sessions_resolved/loop.session_id/receipt['detail_ref']['path']).write_text('corrupt',encoding='utf-8')
    changed=snapshot_for_turn(loop);answer=_host_answer(changed)
    assert {c['scope']['dataset'] for c in changed.as_dict()['claims']}=={'curve_a'}
    assert answer['requirement_outcomes'][-1]['status']=='evidence_insufficient'
    assert changed.as_dict()['requirements'][-1]['claim_ids']==[]
    assert '0.2296' in answer['body']






LEGAL_D30_BOUNDARIES = [
    "目前暂不具备 D30 预测条件。",
    "D30 预测尚缺外推基础。",
    "D30 无从推算。",
    "现有证据无法支持 D30 的点估计。",
    "对 D30 暂不作方向判断。",
    "是否可以预测 D30？",
    "为什么当前阻断 D30 预测？",
    "建议继续观测至第 30 天再判断。",
    "如果 D30 达到预先阈值，则继续试点。",
    "D7 留存为 10%，当前不能预测 D30。",
    "D30 目前不可预测，只有 D1 至 D7 的观测。",
    "当前数据不足以支持对 D30 的预测，因此不报告 D30 数值。",
    "观测区间内的拟合不构成 D30 预测依据。",
    "能否预测 D30——当前证据分级。",
    "请把任何 D30 数字视为假设而非预测。",
    "D30 尚未观测。",
    "D30 缺少验证窗口。",
    "暂时没有 D30 的证据基础。",
    "D30 方向未知。",
    "现阶段无法形成 D30 结论。",
    "不应从 D7 直接外推 D30。",
    "当前不发布 D30 趋势判断。",
    "D30 外推条件尚未满足。",
    "已有数据不能用于估计 D30。",
    "D30 的变化方向仍不清楚。",
    "D30 不在当前观测窗口内。",
    "需要补充 D8 至 D30 数据后再验证。",
    "关于 D30 的结论仍待验证。",
    "D30 应保持为未知项。",
    "当前没有经过验证的 D30 结果。",
    "本轮没有计算 D30。",
    "D30 标记为未计算。",
]


ILLEGAL_D30_CLAIMS = [
    "预计 D30 将达到 5%。",
    "D30 留存大约是 5%。",
    "预测 D30 会继续下降。",
    "D30 将保持稳定。",
    "D30 预计处于低位。",
    "不能预测 D30，但 D30 大约是 5%。",
    "D30 留存为 0.05。",
    "D30 约 0.05。",
    "D30 会继续上升。",
    "D30 将出现反弹。",
    "D30 预计改善。",
    "D30 会回落。",
    "D30 将保持高位。",
    "D30 留存将翻倍。",
    "D30 将提高 8 个百分点。",
    "D30 留存将在 4% 至 6% 之间。",
    "D30 不低于 5%。",
    "渠道 A 的 D30 留存为 5%。",
]


AUDITABLE_D30_SCENARIO = (
    "以下仅为拟合外推情景，不是经过验证的预测；假设 D1-D7 的幂律关系延续至 D30。"
    "幂律模型 R²=0.97，未做留出、回测或 D30 验证；不同模型结果应作为敏感性分析。"
    "幂律情景下 D30 留存约为 12.83%。"
)


class TestNSeriesPublication:

    @pytest.mark.parametrize("text", LEGAL_D30_BOUNDARIES)
    def test_n01_legal_d30_paraphrases_publish(self,text,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate=text
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    @pytest.mark.parametrize("text", ILLEGAL_D30_CLAIMS)
    def test_n03_affirmative_d30_claims_are_rejected(self,text,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate=text
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n03_receipt_bound_scenario_extrapolation_with_full_disclosure_publishes(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=True)
        host=snapshot_for_turn(loop)

        candidate=AUDITABLE_D30_SCENARIO
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        scenario=next(c for c in host.as_dict()['claims'] if c['basis_refs'][0]['result_path']==['scenarios'])
        assert scenario['value']==result['scenarios'] and all(s['validation']=='none' for s in scenario['value'])
        assert _claim_override(host,value=5.)['issues'][0]['code']=='invalid_fields'

    def test_n03_scenario_caveats_do_not_rescue_wrong_extrapolation_arithmetic(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=True)
        host=snapshot_for_turn(loop)

        candidate=AUDITABLE_D30_SCENARIO.replace('12.83%', '5%')
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        scenario=next(c for c in host.as_dict()['claims'] if c['basis_refs'][0]['result_path']==['scenarios'])
        assert scenario['value']==result['scenarios'] and all(s['validation']=='none' for s in scenario['value'])
        assert _claim_override(host,value=5.)['issues'][0]['code']=='invalid_fields'

    def test_n03_prose_disclosures_no_longer_required(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=True)
        host=snapshot_for_turn(loop)
        text = '假设 D1-D7 的幂律关系延续，幂律模型 R²=0.97。幂律情景下 D30 留存约为 12.83%。'
        candidate=text
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        scenario=next(c for c in host.as_dict()['claims'] if c['basis_refs'][0]['result_path']==['scenarios'])
        assert scenario['value']==result['scenarios'] and all(s['validation']=='none' for s in scenario['value'])
        assert _claim_override(host,value=5.)['issues'][0]['code']=='invalid_fields'

    def test_n03_inline_multi_family_sensitivity_recomputes_each_value(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=True)
        host=snapshot_for_turn(loop)
        disclosure = '以下仅为拟合外推情景，不是经过验证的预测；幂律 R²=0.97，指数 R²=0.91，未做留出、回测或 D30 验证；不同模型结果仅作敏感性分析。'
        correct = disclosure + '延伸至 D30：指数约 2.49%，幂律约 12.83%。'
        wrong_second = disclosure + '延伸至 D30：指数约 2.49%，幂律约 3.27%。'
        candidate=correct
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        candidate=wrong_second
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        scenario=next(c for c in host.as_dict()['claims'] if c['basis_refs'][0]['result_path']==['scenarios'])
        assert scenario['value']==result['scenarios'] and all(s['validation']=='none' for s in scenario['value'])
        assert _claim_override(host,value=5.)['issues'][0]['code']=='invalid_fields'

    def test_n03_markdown_d30_column_audits_each_row_value(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=True)
        host=snapshot_for_turn(loop)
        prefix = '以下仅为拟合外推情景，不是经过验证的预测；幂律模型 R²=0.97，未做留出、回测或 D30 验证；不同模型结果仅作敏感性分析。\n'
        correct = prefix + '| 模型 | D30 |\n| --- | --- |\n| 幂律 | 12.83% |'
        wrong = prefix + '| 模型 | D30 |\n| --- | --- |\n| 幂律 | 5.00% |'
        candidate=correct
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        candidate=wrong
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        scenario=next(c for c in host.as_dict()['claims'] if c['basis_refs'][0]['result_path']==['scenarios'])
        assert scenario['value']==result['scenarios'] and all(s['validation']=='none' for s in scenario['value'])
        assert _claim_override(host,value=5.)['issues'][0]['code']=='invalid_fields'

    def test_n03_markdown_d30_column_does_not_bind_another_percentage_column(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=True)
        host=snapshot_for_turn(loop)
        text = '以下仅为拟合外推情景，不是经过验证的预测；幂律模型 R²=0.97，未做留出、回测或 D30 验证；不同模型结果仅作敏感性分析。\n| 模型 | R² | D30 |\n| --- | --- | --- |\n| 幂律 | 97% | 12.83% |'
        candidate=text
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        scenario=next(c for c in host.as_dict()['claims'] if c['basis_refs'][0]['result_path']==['scenarios'])
        assert scenario['value']==result['scenarios'] and all(s['validation']=='none' for s in scenario['value'])
        assert _claim_override(host,value=5.)['issues'][0]['code']=='invalid_fields'

    def test_n01_boundary_statement_with_d30_publishes(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='D7 留存为 10%。当前不能预测 D30，需补充数据。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n01_full_missing_observation_boundary_is_not_misread_as_prediction(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='D30 目前不可预测：本数据只有 D1–D7，没有 D8–D30 的任何观测，也没有验证窗口。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n01_withheld_d30_number_is_not_misread_as_prediction(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='当前数据不足以支持对 D30 的预测，因此我不报告任何 D30 数值。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n01_not_a_prediction_basis_is_not_misread_as_prediction(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='曲线拟合为观测区间内的描述，不构成 D30 或任何未来天数的预测依据。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n01_prediction_question_heading_is_not_misread_as_prediction(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='## 三、“能否预测 D30”——证据分级\nD30 当前不能预测：只有 D1–D7 观测。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n01_prediction_barrier_table_heading_is_not_misread_as_prediction(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='| 判断维度 | 现状（均来自已加载数据） | 为什么阻断 D30 预测 |'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n01_non_predictive_hypothesis_reference_publishes_without_a_value(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='在此之前，请把任何 D30 数字视为假设，而非预测。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n01_hypothesis_label_does_not_license_an_unobserved_value(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='D30 的 5% 只是一个假设，而非预测。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n02_collection_plan_with_day30_publishes(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='D7 留存为 10%。建议继续收集至第30天再验证。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n02_yoy_label_backed_by_crossyear_receipt_publishes(self,engine):
        loop,_=_calendar_comparison(engine,('2025-09-01', '2025-09-07', '2026-09-01', '2026-09-07'))
        host=snapshot_for_turn(loop)

        candidate='金额同比增长 10%。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n02_yoy_label_with_sameyear_receipt_is_revision_only(self,engine):
        loop,_=_calendar_comparison(engine,('2026-09-01', '2026-09-02', '2026-09-08', '2026-09-09'))
        host=snapshot_for_turn(loop)

        candidate='2026-09-01 与 2026-09-02 的金额均同比增长 10%。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n02_yoy_label_without_receipt_is_revision_only_not_verdict_from_prose(self,engine):
        loop,_=engine;_v2_request(loop,'解释同比',[{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'sum'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'difference'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'relative_change'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'calendar_days'}}],kind="result",purposes=["interpretation"])
        host=snapshot_for_turn(loop)

        candidate='2025-09-01 与 2026-09-01 相比，金额同比增长 10%。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n02_same_proportional_growth_is_not_a_yoy_label(self,engine):
        loop,_=_calendar_comparison(engine,('2026-09-01', '2026-09-02', '2026-09-08', '2026-09-09'))
        host=snapshot_for_turn(loop)

        candidate='2026-09-01 至 2026-09-02，各来源均同比例上升 10%。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n03_unsupported_d30_prediction_rejected(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='D30 留存预计为 5%。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n03_missing_observation_does_not_qualify_positive_directional_prediction(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='没有 D8–D30 观测，预测 D30 会继续下降。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n04_negation_does_not_cover_assertion_in_same_sentence(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='不能预测 D30，但 D30 大约是 5%。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n05_conditional_action_publishes(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='如果 D30 达到预先阈值，则继续试点。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n06_other_source_with_valid_d30_not_blocked(self,engine):
        loop,_,a,ra=_curve_actual(engine)
        _,_,b,rb=_curve_actual(engine,name='渠道 B',days=30)
        host=snapshot_for_turn(loop)
        assert any(c['scope']['dataset']=='渠道 B' and c['basis_refs'][0]['result_path']==['points',29,'y'] for c in host.as_dict()['claims'])

        candidate='渠道 B 的 D30 留存为 8%。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n06_a_extrapolation_still_blocked_when_b_present(self,engine):
        loop,_,a,ra=_curve_actual(engine)
        _,_,b,rb=_curve_actual(engine,name='渠道 B',days=30)
        host=snapshot_for_turn(loop)
        assert any(c['scope']['dataset']=='渠道 B' and c['basis_refs'][0]['result_path']==['points',29,'y'] for c in host.as_dict()['claims'])

        candidate='渠道 A 的 D30 留存预计为 5%。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n06_a_scope_still_blocks_when_b_absent(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='渠道 B 的 D30 留存为 8%。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n07_significance_claim_without_any_test_rejected(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)

        candidate='两组转化率差异不显著。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n08_unrelated_significance_claim_not_backed_globally(self,engine):
        loop,_=_actual_inference(engine,causal=False)
        host=snapshot_for_turn(loop)

        candidate='新用户的留存差异不显著。'
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n08_bound_significance_claim_publishes(self,engine):
        loop,_=_actual_inference(engine,causal=False)
        host=snapshot_for_turn(loop)

        candidate='treatment 组的 revenue 差异不显著时不应加价。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n09_causal_tool_metadata_counts_as_executed_inference(self,engine):
        loop,_=_actual_inference(engine,causal=True)
        host=snapshot_for_turn(loop)

        candidate='campaign 对 revenue 的差异不显著。'
        answer,calls=_open_answer(host,candidate,'accept')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('accept'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']

    def test_n11_issues_carry_position_and_stable_code(self,engine):
        loop,_,rid,result=_curve_actual(engine,scenarios=False)
        host=snapshot_for_turn(loop)
        text = 'D7 为 10%。D30 大约是 5%。'
        candidate=text
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert answer['render_trace'][0]['part_id']=='s0p0' and answer['render_trace'][0]['disposition']=='reject'
        assert calls[0]['parts'][0]['text']=='D7 为 10%。D30 大约是 5%。'
        candidate=text
        answer,calls=_open_answer(host,candidate,'reject')
        assert len(calls)==1 and calls[0]['parts'][0]['text']==candidate
        assert (candidate in answer['body'])==('reject'=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert answer['render_trace'][0]['part_id']=='s0p0' and answer['render_trace'][0]['disposition']=='reject'
        assert calls[0]['parts'][0]['text']=='D7 为 10%。D30 大约是 5%。'


def test_unconfirmed_amount_unit_rejects_currency_rewrite_but_allows_explicit_unknown(engine):
    loop,_=_python_result(engine,{'amount':120,'orders':12})
    host=snapshot_for_turn(loop)
    assert all(c['unit'] is None for c in host.as_dict()['claims'])
    for text,decision in [('每单都是10块钱，12单合计120块。','reject'),('amount 合计为120，金额单位未知，不能写成120元。','accept'),('金额单位未知，但每单10元。','reject'),('合计120元（金额单位未知）。','reject')]:
        answer,calls=_open_answer(host,text,decision)
        assert (text in answer['body'])==(decision=='accept')
    assert _claim_override(host,unit='CNY')['issues'][0]['code']=='invalid_fields'


def test_mixed_observed_future_window_cannot_be_labeled_wholly_future(engine):
    import pandas as pd
    loop,_=engine;today=date.today()
    frame=pd.DataFrame({'date':pd.date_range(today-timedelta(days=2),periods=5),'amount':[10]*5})
    loop.context.workspace.add('mixed',frame)
    _v2_request(loop,'解释窗口',{'kind': 'measurement', 'scope': {'datasets': ['mixed'], 'quantity': 'rows'}},kind="result",purposes=["interpretation"])
    _,result=_v2_execute(loop,'describe_dataset',{'name':'mixed'})
    host=snapshot_for_turn(loop)
    assert result['observation_window']['columns']['date']['min'].startswith((today-timedelta(days=2)).isoformat())
    assert result['observation_window']['columns']['date']['max'].startswith((today+timedelta(days=2)).isoformat())
    for text,decision in [('观测窗口属于未来日期，数据时效未验证。','reject'),('观测窗口包含部分未来日期，采集截止未知。','accept')]:
        answer,calls=_open_answer(host,text,decision)
        assert (text in answer['body'])==(decision=='accept')


def test_presentation_followup_reuses_only_current_bound_publication_snapshot(engine,monkeypatch):
    _v2_presentation_with_unit_rejection(engine,monkeypatch,"请用大白话重述，但不要改变事实",check_stale=True)


def test_presentation_followup_outside_followup_phrases_still_validates(engine,monkeypatch):
    _v2_presentation_with_unit_rejection(engine,monkeypatch,"请把刚才的结论整理成一份正式的书面汇报")


# ── P4 (D03): evidence coverage and recoverable packet selection (E01–E05, E09–E10) ──


def test_provenance_question_is_not_misread_as_an_asserted_origin(engine):
    loop,_=_python_result(engine,{'amount':10,'rows':12})
    host=snapshot_for_turn(loop)
    for text,disposition in [('请确认该文件是完整、抽样还是测试数据？', 'accept')]:
        answer,calls=_open_answer(host,text,disposition)
        assert len(calls)==1 and calls[0]['parts'][0]['text']==text
        assert (text in answer['body'])==(disposition=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert calls[0]['claims']==[{k:c[k] for k in ('id','label','value','unit','scope','limitations')} for c in host.as_dict()['claims']]


def test_ordinary_sample_size_language_is_not_a_provenance_classification(engine):
    loop,_=_python_result(engine,{'amount':10,'rows':12})
    host=snapshot_for_turn(loop)
    for text,disposition in [('The observed sample size is 7, so uncertainty remains high.', 'accept')]:
        answer,calls=_open_answer(host,text,disposition)
        assert len(calls)==1 and calls[0]['parts'][0]['text']==text
        assert (text in answer['body'])==(disposition=='accept')
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert calls[0]['claims']==[{k:c[k] for k in ('id','label','value','unit','scope','limitations')} for c in host.as_dict()['claims']]


@pytest.mark.parametrize("text", [
    "下面用一个样例说明计算过程。",
    "附上演示数据的加载代码。",
    "这不是占位数据，是真实流水。",
    "请问这是不是测试数据？",
])
def test_non_assertive_or_negated_provenance_mentions_publish(text,engine):
    loop,_=_python_result(engine,{'amount':10,'rows':7})
    host=snapshot_for_turn(loop);answer,calls=_open_answer(host,text,'accept')
    assert len(calls)==1 and calls[0]['parts'][0]['text']==text
    assert (text in answer['body'])==('accept'=='accept')
    assert answer['source_snapshot']['claims']==host.as_dict()['claims']


@pytest.mark.parametrize("text", [
    "该文件是单一取值的样例数据。",
    "数据来源分类：占位数据。",
    "当前交付的这份文件属于测试数据。",
])
def test_provenance_taxonomy_rejects_unsupported_assertions_without_phrase_enumeration(text,engine):
    loop,_=_python_result(engine,{'amount':10,'rows':7})
    host=snapshot_for_turn(loop);answer,calls=_open_answer(host,text,'reject')
    assert len(calls)==1 and calls[0]['parts'][0]['text']==text
    assert (text in answer['body'])==('reject'=='accept')
    assert answer['source_snapshot']['claims']==host.as_dict()['claims']






class TestESeriesPacket:

    def test_b03_explicit_all_sources_request_retains_every_source_with_facts(self,engine):
        loop,receipts,values=_six_actual(engine)
        host=snapshot_for_turn(loop);answer=_host_answer(host)
        assert {p['receipt_id'] for c in host.as_dict()['claims'] for p in c['basis_refs']}==set(receipts)
        assert [c['value'] for c in host.as_dict()['claims']]==values
        assert len(answer['requirement_outcomes'])==6 and all(o['status']=='answered' for o in answer['requirement_outcomes'])
        assert all(name in visible_text(answer['body']) for name in ['revenue_a','a_vs_b','long_tail','checkout','power','weak'])

    def test_e01_all_primary_subquestion_sources_kept(self,engine):
        loop,receipts,values=_six_actual(engine)
        host=snapshot_for_turn(loop);answer=_host_answer(host)
        assert {p['receipt_id'] for c in host.as_dict()['claims'] for p in c['basis_refs']}==set(receipts)
        assert [c['value'] for c in host.as_dict()['claims']]==values
        assert len(answer['requirement_outcomes'])==6 and all(o['status']=='answered' for o in answer['requirement_outcomes'])
        assert all(name in visible_text(answer['body']) for name in ['revenue_a','a_vs_b','long_tail','checkout','power','weak'])

    def test_e02_current_evidence_not_sliced_before_filter(self,engine):
        loop,receipts,values=_six_actual(engine)
        state=loop.context.analysis_state
        state.evidence_records=[{'id':'ev_current','claim':'A 渠道趋势上升','tool_receipt_ids':[receipts[0]],'limitations':[]}]+[{'id':f'ev_other_{i}','claim':'其它来源','tool_receipt_ids':[f'tr_q{i+8}'],'limitations':[]} for i in range(1,5)]
        host=snapshot_for_turn(loop);answer=_host_answer(host)
        assert answer['source_snapshot']['claims']==host.as_dict()['claims']
        assert host.as_dict()['claims'][0]['basis_refs'][0]['receipt_id']==receipts[0]
        assert state.evidence_records[0]['id']=='ev_current'  # EvidenceStore retained; metadata grants no new fact
        assert len(host.as_dict()['claims'])==6

    def test_e03_fourth_group_value_enters_facts_with_its_name(self,engine):
        data={'metric':'amount','groups':[{'channel':'A','amount':1},{'channel':'B','amount':2},{'channel':'C','amount':3},{'channel':'D','amount':999}]}
        loop,_=_python_result(engine,data,content='各渠道金额最高的是谁')
        host=snapshot_for_turn(loop);answer=_host_answer(host)
        assert host.as_dict()['claims'][0]['value']==data
        assert host.as_dict()['claims'][0]['value']['groups'][3]=={'channel':'D','amount':999}
        assert has_record(answer['body'], {'channel':'D','amount':999})

    def test_e04_comparison_fields_kept_as_a_group(self,engine):
        loop,_,rid,result=_v2_full_period(engine)
        host=snapshot_for_turn(loop);answer=_host_answer(host)
        facts=host.as_dict()['claims']
        for value,period in [(1818,'period_a'),(684,'period_b')]:
            assert any(c['value']==value and c['basis_refs'][0]['result_path']==['metrics','revenue','exact_aggregates',period] for c in facts)
            assert any(c['value']==15 and c['basis_refs'][0]['result_path']==[period,'day_count'] for c in facts)
        assert answer['source_snapshot']['claims']==facts  # context budget never splits or deletes host facts

    def test_e05_budget_omissions_are_recorded_with_references(self,engine):
        loop,receipts,values=_six_actual(engine)
        for i in range(10):
            rid,result=_v2_execute(loop,'run_python',{'code':"df=get_dataset('source_1'); result={'value':"+str(i)+"}",'purpose':f'background calc {i}'})
            receipts.append(rid)
        host=snapshot_for_turn(loop);answer=_host_answer(host)
        assert {p['receipt_id'] for c in host.as_dict()['claims'] for p in c['basis_refs']}==set(receipts)
        assert len(host.as_dict()['claims'])==16 and answer['source_snapshot']['claims']==host.as_dict()['claims']
        from data_agent.llm.request_policy import resolve_request_budget
        from data_agent.config import get_config
        policy=resolve_request_budget(get_config().model_id,get_config(),get_config().max_tokens)
        assert policy.estimate([{'role':'system','content':publication_prompt(loop)}])['tokens']<=policy.input_allowance

    def test_e09_packet_identity_changes_when_evidence_content_changes(self,engine):
        loop,receipts,values=_six_actual(engine)
        state=loop.context.analysis_state
        state.evidence_records=[{'id':'ev_1','claim':'A 渠道趋势上升 12%','tool_receipt_ids':[receipts[0]],'limitations':[]}]
        first=snapshot_for_turn(loop)
        state.evidence_records[0]['claim']='A 渠道趋势上升 15%'
        second=snapshot_for_turn(loop)
        assert first.digest==second.digest and '15%' not in _host_answer(second)['body']
        # Retired model prose annotations cannot mutate closed raw measurements.
        receipt=next(r for r in state.tool_receipts if r['id']==receipts[0]);receipt['detail_ref']['sha256']='sha256:changed'
        changed=snapshot_for_turn(loop)
        assert changed.digest!=first.digest and len(changed.as_dict()['claims'])==5

    def test_e10_search_terms_do_not_become_answer_gaps(self,engine):
        loop,_=_python_result(engine,{'trend':'rising','metric':'revenue_a'},content='分析A渠道趋势')
        host=snapshot_for_turn(loop);answer=_host_answer(host)
        assert len(answer['requirement_outcomes'])==1 and answer['requirement_outcomes'][0]['status']=='answered'
        assert '搜索' not in answer['body'] and '异常检测' not in answer['body']
        _v2_request(loop,'漏斗',{'kind': 'table', 'scope': {'datasets': ['original']}})
        _v2_request(loop,'留存曲线',{'kind': 'series', 'scope': {'datasets': ['original']}})
        answer=_host_answer(snapshot_for_turn(loop))
        assert [o['status'] for o in answer['requirement_outcomes']]==['answered','not_computed','not_computed']


# ── P7-L3/B03: publication receipt renderer (sources/omissions/pending) ──


def test_b03_render_publication_receipt_markdown_covers_sources_omissions_pending(engine):
    loop,receipts,values=_six_actual(engine)
    _v2_request(loop,'收入变化由订单量驱动；补齐区分性证据：orders',{'kind': 'table', 'scope': {'datasets': ['source_1'], 'metrics': ['orders']}})
    host=snapshot_for_turn(loop);answer=_host_answer(host)
    assert [c['value'] for c in host.as_dict()['claims']]==values
    assert '补齐区分性证据：orders' in answer['body'] and answer['requirement_outcomes'][-1]['status']=='not_computed'
    assert 'artifact_path' not in answer['body'] and 'publication_rejected' not in answer['body'] and 'tool_receipt_ids' not in answer['body']
    assert {p['receipt_id'] for c in answer['source_snapshot']['claims'] for p in c['basis_refs']}==set(receipts)


def test_b03_render_includes_omitted_refs_and_requirement_delivery_state(engine):
    loop,receipts,values=_six_actual(engine)
    _v2_request(loop,'异常检测',{'kind': 'measurement', 'scope': {'datasets': ['source_1'], 'quantity': 'value'}})
    host=snapshot_for_turn(loop);answer=_host_answer(host)
    assert '异常检测：未计算' in answer['body'] and answer['requirement_outcomes'][-1]['status']=='not_computed'
    assert answer['source_snapshot']['requirements'][-1]['gap']['status']=='not_computed'
    assert len(answer['source_snapshot']['claims'])==6
    raw=json.loads(_v2_draft(host));raw['sections'][0]['parts'].append({'kind':'claim','ref':'tr_extra_99'})
    changed=_host_answer(host,raw)
    assert any(i['code']=='unknown_claim_ref' for i in changed['issues']) and 'tr_extra_99' not in changed['body']


def test_b03_publication_packet_registers_receipt_artifact(engine):
    from data_agent.agent.publication.runtime import publish,snapshot_for_turn,commit,read_answer
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    from data_agent.session.history import list_artifacts,load_session
    from pathlib import Path
    loop,cfg=engine
    request(loop,"计算当前记录数",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}})
    execute(loop,"describe_dataset",{"name":"orders"})
    body,error=publish(loop,draft(snapshot_for_turn(loop)));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    artifacts=[a for a in list_artifacts(loop.session_id) if a["type"]=="accepted_answer"]
    assert len(artifacts)==1
    message=load_session(loop.session_id)["messages"][-1]
    reference=message["answer_ref"]
    assert artifacts[0]["path"]=="sessions/"+loop.session_id+"/"+reference["path"] and artifacts[0]["sha256"]==reference["sha256"]
    assert read_answer(loop.session_id,reference)["body"]==body
    assert commit(loop,{"role":"assistant"},body) is None
    assert len([a for a in list_artifacts(loop.session_id) if a["type"]=="accepted_answer"])==1


def test_r1_publication_validator_exception_never_releases_candidate(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.llm.client import Response
    loop,_=engine
    _v2_request(loop,"解释当前记录",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}},kind="result",purposes=["interpretation"])
    _v2_execute(loop,"describe_dataset",{"name":"orders"})
    host=snapshot_for_turn(loop);raw=json.loads(_v2_draft(host));raw["sections"][0]["parts"].append({"kind":"text","purpose":"interpretation","text":"收入为999。","claim_refs":host.as_dict()["requirements"][0]["claim_ids"]})
    class BrokenAudit:
        def chat(self,*a,**k): raise ZeroDivisionError("unavailable audit")
    loop.client=BrokenAudit()
    body,error=publish(loop,json.dumps(raw));assert error is None
    assert "999" not in body and "12" in body and loop._accepted_answer["audit_status"]=="unavailable"


def test_r1_missing_current_packet_never_releases_candidate(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    _v2_request(loop,"计算收入",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}})
    host=snapshot_for_turn(loop);raw=json.loads(_v2_draft(host));raw["sections"][0]["parts"]=[{"kind":"claim","ref":"fabricated_income_999"}]
    body,error=publish(loop,json.dumps(raw));assert error is None
    assert "999" not in body and "未计算" in body and host.as_dict()["claims"]==[]


def test_r1_exhausted_revision_retains_only_selected_current_receipt_values(engine):
    loop,_=_python_result(engine,{'revenue':{'value':100}},content='收入')
    _v2_request(loop,'复购率',{'kind': 'table', 'scope': {'datasets': ['original'], 'metrics': ['复购率']}})
    host=snapshot_for_turn(loop);raw=json.loads(_v2_draft(host))
    raw['sections'][0]['parts'].append({'kind':'claim','ref':'invented-repeat-20-percent'})
    answer=_host_answer(host,raw)
    assert '100' in answer['body'] and '复购率为20%' not in answer['body'] and '复购率：未计算' in answer['body']
    assert [o['status'] for o in answer['requirement_outcomes']]==['answered','not_computed']
    assert any(i['code']=='unknown_claim_ref' for i in answer['issues'])


def test_r1_exhausted_revision_publishes_selected_receipt_without_bad_prose(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    _v2_request(loop,"计算金额合计",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}})
    _v2_execute(loop,"describe_dataset",{"name":"orders"})
    _v2_request(loop,"计算复购率",{'kind': 'table', 'scope': {'datasets': ['orders'], 'metrics': ['repurchase']}})
    raw="收入为100。复购率为20%。"
    assert publish(loop,raw)[1]
    body,error=publish(loop,raw);assert error is None
    assert has_number(body, 'amount：sum', 180) and "复购率为20%" not in body and "计算复购率：未计算" in body

from tests.test_trusted_publication_semantics import engine

from tests.test_trusted_publication_runtime import request as _v2_request, draft as _v2_draft
from tests.test_trusted_publication_semantics import execute as _v2_execute


def _v2_compare_args():
    return {"name":"orders","date_col":"day","metrics":"amount","period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"}


def _v2_comparison(engine):
    loop,cfg=engine
    _v2_request(loop,"比较两期金额",[{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'sum'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'difference'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'relative_change'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'rows'}}, {'kind': 'measurement', 'scope': {'datasets': ['orders'], 'quantity': 'calendar_days'}}])
    _v2_execute(loop,"compare_periods",_v2_compare_args())
    return loop,cfg


def _v2_confirmed_without_result(engine,content):
    from data_agent.agent.confirmation.runtime import build_measurement_mapping_candidate
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.session.history import load_canonical_history
    loop,cfg=engine
    _v2_request(loop,content,{'kind': 'series', 'scope': {'datasets': ['orders']}})
    history=load_canonical_history(loop.session_id)
    candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="confirmed_without_result",workspace=loop.context.workspace,canonical_history=history,source_message_ref=history.messages[-1]["request_id"],exact_span=content,dataset="orders",column="amount")
    service=loop._confirmation_runtime();service.request(candidate)
    record=service.checkpoint(loop.session_id)
    service.respond(loop.session_id,record.confirmation_id,record.options[0].value,expected_version=record.version,idempotency_key="confirmed_no_result")
    host=snapshot_for_turn(loop);body,error=publish(loop,_v2_draft(host));assert error is None
    assert host.as_dict()["confirmation_refs"] and host.as_dict()["claims"]==[]
    assert "未计算" in body and loop._accepted_answer["requirement_outcomes"][0]["status"]=="not_computed"


def _v2_presentation_with_unit_rejection(engine,monkeypatch,text,check_stale=False):
    from tests.test_trusted_publication_runtime import AppClient,intent_for_app
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.llm.client import Response
    import pandas as pd
    loop,_=engine
    intent_for_app(monkeypatch,"result","计算当前金额",{'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'})
    loop.client=AppClient(loop,"describe_dataset",{"name":"orders"})
    original_body=loop.run_turn_structured("计算当前金额").content
    original=loop.context.analysis_state.accepted_answers[-1]
    follow=TurnIntent("result_followup","clear","data_loaded","follow_up","answer_directly",requested_outputs=[{"kind":"presentation","exact_span":text}])
    monkeypatch.setattr("data_agent.agent.intent.plan_turn_intent",lambda *a,**k:follow)
    class FollowClient(AppClient):
        def chat(self,messages,system="",**kwargs):
            if system.startswith("审核数据相关开放片段"):
                data=json.loads(messages[0]["content"])
                return Response(text=json.dumps({"schema":"publication_audit.v2","snapshot_digest":data["snapshot_digest"],"draft_digest":data["draft_digest"],"decisions":[{"part_id":p["part_id"],"disposition":"reject","reason":"币种未由原测量或业务决定确认","evidence_refs":p["requirement_ids"]} for p in data["parts"]]}))
            host=snapshot_for_turn(loop);proposal=json.loads(_v2_draft(host));proposal["sections"][0]["parts"].append({"kind":"text","purpose":"interpretation","text":"订单合计180块钱。","claim_refs":host.as_dict()["requirements"][0]["claim_ids"]})
            return Response(text=json.dumps(proposal,ensure_ascii=False))
    loop.client=FollowClient(loop)
    body=loop.run_turn_structured(text).content
    assert "180块钱" not in body and has_number(body, 'amount：sum', 180)
    assert loop.context.analysis_state.answer_requirements[-1]["source_answer_id"]==original["answer_id"]
    if check_stale:
        loop.prepare_for_bound_upload()
        loop.context.workspace.add("orders",pd.DataFrame({"amount":[20,20]}))
        second=loop.run_turn_structured(text).content
        assert "180块钱" not in second and not snapshot_for_turn(loop).as_dict()["claims"]


def _v2_full_period(engine,*,overlap=False):
    import pandas as pd
    loop,cfg=engine
    rows=[{"day":date(2026,4,7)+timedelta(days=i%15),"revenue":38 if i<46 else 70} for i in range(47)]
    rows += [{"day":date(2026,4,22)+timedelta(days=i%15),"revenue":28 if i<23 else 40} for i in range(24)]
    frame=pd.DataFrame(rows);frame["day"]=pd.to_datetime(frame["day"])
    loop.context.workspace.add("periods",frame)
    _v2_request(loop,"比较前后两个周期，保留合并范围",[{'kind': 'measurement', 'scope': {'datasets': ['periods'], 'quantity': 'sum'}}, {'kind': 'measurement', 'scope': {'datasets': ['periods'], 'quantity': 'difference'}}, {'kind': 'measurement', 'scope': {'datasets': ['periods'], 'quantity': 'relative_change'}}, {'kind': 'measurement', 'scope': {'datasets': ['periods'], 'quantity': 'rows'}}, {'kind': 'measurement', 'scope': {'datasets': ['periods'], 'quantity': 'calendar_days'}}])
    args={"name":"periods","date_col":"day","metrics":"revenue","period_a":"2026-04-07~2026-04-21","period_b":"2026-04-22~2026-05-06"}
    if overlap: args.update(period_a="2026-04-07~2026-04-24",period_b="2026-04-19~2026-05-06")
    rid,result=_v2_execute(loop,"compare_periods",args)
    return loop,cfg,rid,result


# Actual source-backed fixtures shared only by the historical behavior tests.
from data_agent.agent.publication.runtime import snapshot_for_turn,publication_prompt
from data_agent.agent.publication.service import PublicationService
from data_agent.agent.publication.contracts import encode

def _host_answer(host,payload=None):
    return PublicationService(host).publish(encode(payload) if payload is not None else _v2_draft(host)).as_dict()

def _claim_override(host,**fields):
    raw=json.loads(_v2_draft(host));raw['sections'][0]['parts'][0].update(fields)
    return _host_answer(host,raw)

def _python_result(engine,data,*,content='解释原计算范围',code=None):
    import pandas as pd
    loop,cfg=engine
    nested=any(isinstance(value,(dict,list)) for value in data.values())
    cells={}
    def source_expression(value):
        if isinstance(value,dict):return '{'+','.join(repr(k)+':'+source_expression(v) for k,v in value.items())+'}'
        if isinstance(value,list):return '['+','.join(source_expression(v) for v in value)+']'
        key='cell_'+str(len(cells));cells[key]=[value]
        return 'df['+repr(key)+'].iloc[0]'
    expression=source_expression(data) if nested else None
    frame=pd.DataFrame(cells) if nested else pd.DataFrame({key:[value] for key,value in data.items()})
    loop.context.workspace.add('original',frame)
    purpose='original business output'
    _v2_request(loop,content,{'kind': 'table', 'scope': {'datasets': ['original']}})
    _v2_execute(loop,'run_python',{'code':code or ("df=get_dataset('original'); result="+expression if nested else "df=get_dataset('original'); result=df.to_dict('records')[0]"),'purpose':purpose})
    return loop,cfg

def _open_answer(host,text,disposition,*,claim_refs=None):
    # A fixed located response tests one-call dispatch and partial publication;
    # it makes no assertion that a natural auditor chooses this disposition.
    calls=[]
    request=host.as_dict()['requirements'][0]
    requirements=host.as_dict()['requirements']
    for item in requirements:item['open_purposes']=['interpretation']
    from data_agent.agent.publication.contracts import HostSnapshot
    source=host.as_dict();source['requirements']=requirements
    source.pop('schema',None)
    scoped=HostSnapshot.freeze(**source)
    refs=claim_refs if claim_refs is not None else request['claim_ids']
    raw={'schema':'answer_bindings.v2','snapshot_digest':scoped.digest,'sections':[{'requirement_ids':[request['id']],'parts':[{'kind':'text','purpose':'interpretation','text':text,'claim_refs':refs}]}]}
    def audit(payload):
        calls.append(payload)
        return {'schema':'publication_audit.v2','snapshot_digest':payload['snapshot_digest'],'draft_digest':payload['draft_digest'],'decisions':[{'part_id':p['part_id'],'disposition':disposition,'reason':'原独立语义案例的冻结局部裁决','evidence_refs':p['requirement_ids']} for p in payload['parts']]}
    answer=PublicationService(scoped,auditor=audit).publish(encode(raw)).as_dict()
    assert answer['source_snapshot']['claims']==host.as_dict()['claims']
    assert len(calls)==1 and calls[0]['parts'][0]['claim_refs']==refs
    assert calls[0]['claims']==[{k:c[k] for k in ('id','label','value','unit','scope','limitations')} for c in host.as_dict()['claims'] if c['id'] in set(refs) | {cid for req in requirements if not req['withdrawn'] for cid in req['claim_ids']}]
    assert answer['audit_status']=='reviewed'
    return answer,calls

def _curve_actual(engine,*,name='渠道 A',days=7,scenarios=True):
    import pandas as pd
    loop,cfg=engine
    values=[round(.5*day**(-.4),4) for day in range(1,days+1)]
    loop.context.workspace.add(name,pd.DataFrame({'day':range(1,days+1),'retention':values}))
    _v2_request(loop,'解释 '+name+' D1 至 D'+str(days)+' 的原观测及 D30 边界',[{'kind':k,'scope':{'datasets':[name],**({'quantity':'value'} if k=='measurement' else {})}} for k in ['series','fit','measurement']+(['scenario'] if scenarios else [])],purposes=['interpretation'])
    args={'name':name,'x_col':'day','y_col':'retention'}
    if scenarios:args['scenario_points']=[30]
    rid,result=_v2_execute(loop,'curve_fitting',args)
    assert rid,result
    return loop,cfg,rid,result

def _calendar_comparison(engine,dates):
    import pandas as pd
    loop,cfg=engine;a0,a1,b0,b1=dates
    loop.context.workspace.add('calendar',pd.DataFrame({'day':pd.to_datetime([a0,b0]),'revenue':[10,11]}))
    _v2_request(loop,'解释两期范围及10%变化',[{'kind': 'measurement', 'scope': {'datasets': ['calendar'], 'quantity': 'sum'}}, {'kind': 'measurement', 'scope': {'datasets': ['calendar'], 'quantity': 'difference'}}, {'kind': 'measurement', 'scope': {'datasets': ['calendar'], 'quantity': 'relative_change'}}, {'kind': 'measurement', 'scope': {'datasets': ['calendar'], 'quantity': 'rows'}}, {'kind': 'measurement', 'scope': {'datasets': ['calendar'], 'quantity': 'calendar_days'}}],kind="result",purposes=["interpretation"])
    _v2_execute(loop,'compare_periods',{'name':'calendar','date_col':'day','metrics':'revenue','period_a':a0+'~'+a1,'period_b':b0+'~'+b1})
    return loop,cfg

def _actual_inference(engine,*,causal=False):
    import pandas as pd
    loop,cfg=engine
    frame=pd.DataFrame({'revenue':[10+i%7+(i//40)*2 for i in range(80)],'group':['control']*40+['treatment']*40,'campaign':[0]*40+[1]*40,'period':([0]*20+[1]*20)*2})
    loop.context.workspace.add('experiment',frame)
    tool='causal_analysis' if causal else 'ab_test'
    _v2_request(loop,'解释 campaign 对 revenue 的关系' if causal else '解释 treatment 与 control 的 revenue 检验',{'kind': 'measurement', 'scope': {'datasets': ['experiment'], 'quantity': 'value'}},kind="result",purposes=["interpretation"])
    args={'name':'experiment','treatment_col':'campaign','outcome_col':'revenue','time_col':'period','method':'did'} if causal else {'name':'experiment','group_col':'group','metric_col':'revenue','method':'ttest'}
    _,result=_v2_execute(loop,tool,args)
    assert 'error' not in result,result
    return loop,cfg

def _six_actual(engine):
    import pandas as pd
    loop,cfg=engine
    values=[{'trend':'rising','metric':'revenue_a'},{'compare':'a_vs_b','delta':12},{'distribution':'long_tail','bins':9},{'funnel':'checkout','drop_off':.4},{'retention':'power','d7':.1},{'correlation':'weak','pairs':3}]
    topics=['A渠道趋势','B渠道对比','用户分布','漏斗','留存曲线','相关性'];receipts=[]
    for i,(topic,value) in enumerate(zip(topics,values),1):
        name=f'source_{i}';loop.context.workspace.add(name,pd.DataFrame({k:[v] for k,v in value.items()}))
        _v2_request(loop,topic,{'kind': 'table', 'scope': {'datasets': [name]}})
        rid,result=_v2_execute(loop,'run_python',{'code':f"df=get_dataset('{name}'); result=df.to_dict('records')[0]",'purpose':topic})
        assert result['result_data']==value
        receipts.append(rid)
    return loop,receipts,values
