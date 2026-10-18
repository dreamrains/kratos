"""Offline contracts for quality scope, chart rendering, and bounded export."""
import json
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest
from tests.test_trusted_publication_semantics import engine

from tests.test_artifact_publication_contracts import context


def test_quality_results_carry_observed_dates_not_collection_cutoff(context, monkeypatch):
    from data_agent.tools.data_understand import describe_dataset, detect_data_quality
    from data_agent.tools.evidence_statistics import bind_computed_statistics
    from data_agent.tools.analysis_flow import _mark_statistical_detail_status
    context.workspace.add('retention', pd.DataFrame({'date':pd.to_datetime(['2020-07-01','2020-08-31']), 'D30':[.02,0.]}))
    results = {'r1':json.loads(describe_dataset('retention')), 'r2':json.loads(detect_data_quality('retention'))}
    scope = results['r1']['observation_window']
    assert scope['columns']['date']['min'].startswith('2020-07-01')
    assert scope['columns']['date']['max'].startswith('2020-08-31')
    assert scope['collection_cutoff'] == 'unknown'
    assert results['r1']['field_statistics'][0]['datetime_range']['span_days'] == 61
    monkeypatch.setattr('data_agent.tools.result_reference.load_result_reference',
                        lambda ref: (results[ref.split('/')[-1].split('_')[0]], {'receipt_id':ref.split('/')[-1].split('_')[0]}))
    payload = {'time_scope':'invented collection date'}
    bind_computed_statistics(payload, [{'id':r, 'tool_call_id':r, 'tool_name':t, 'arguments':{'name':'retention'}, 'structured_result_sha256':'validated'}
                                     for r,t in [('r1','describe_dataset'),('r2','detect_data_quality')]])
    _mark_statistical_detail_status(payload)
    assert payload['time_scope'] == scope
    assert payload['statistical_detail_status'] == 'complete'
    assert payload['metrics']['detect_data_quality']['total_issues'] == 0
    assert payload['sample_size'] == 2


def test_date_like_strings_do_not_invent_a_time_window(context):
    from data_agent.tools.data_understand import describe_dataset
    context.workspace.add('text', pd.DataFrame({'label':['2020-01','unknown']}))
    assert not json.loads(describe_dataset('text')).get('observation_window')


def test_static_failure_is_receipted_once_and_exported_as_partial(context, monkeypatch):
    from data_agent.tools.visualization import _save_chart
    from data_agent.config import get_config
    from data_agent.tools.report import _validated_chart_entries
    attempts = []
    def fail(self, **kwargs):
        attempts.append(kwargs)
        raise RuntimeError('renderer unavailable at first attempt')
    monkeypatch.setattr(go.Figure, 'to_image', fail)
    result = _save_chart(go.Figure(go.Scatter(x=[1,2], y=[2,3])), 'diagnostic',
                         {'purpose':'exploratory','validation_status':'valid','title':'diagnostic'})
    root = get_config().sessions_resolved / context.session_id / 'charts'
    meta = json.loads(next(root.glob('*.json')).read_text('utf8'))
    assert meta['static_image']['status'] == 'failed'
    assert meta['static_image']['exception_type'] == 'RuntimeError'
    assert 'first attempt' in meta['static_image']['message']
    assert len(attempts) == 1 and '静态图不可用' in result
    assert not list(root.glob('*.png'))
    exported = _validated_chart_entries(context.session_id)
    assert len(exported) == 1 and '静态图不可用' in exported[0]['markdown']
    assert 'RuntimeError' in exported[0]['markdown']
    assert len(attempts) == 1  # Export is not a hidden rendering retry.


def test_fit_scope_preserves_unknown_zero_meaning_and_descriptive_ceiling(engine):
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_runtime import request,draft
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.service import PublicationService
    from data_agent.agent.publication.contracts import encode
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"D1":[.5,0],"D2":[.4,0],"D3":[.3,0],"D4":[.2,0],"D5":[.15,0],"D6":[.12,0],"D7":[.1,0]}))
    request(loop,"拟合观测并解释限制",{'kind': 'series', 'scope': {'datasets': ['orders']}},kind="result",purposes=["interpretation"])
    _,result=execute(loop,"curve_fitting",{"name":"orders","series_columns":"D1,D2,D3,D4,D5,D6,D7","zero_values":"exclude"})
    assert result["zero_value_semantics"]=="unknown" and result["claim_ceiling"]=="descriptive"
    assert all(p["n_excluded_zeros"]==1 for p in result["points"])
    snapshot=snapshot_for_turn(loop)
    payload=json.loads(draft(snapshot))
    payload["sections"][0]["parts"] += [
        {"kind":"text","purpose":"interpretation","text":"零值证明未到期，ROI最高。","claim_refs":[snapshot.as_dict()["claims"][0]["id"]]},
        {"kind":"text","purpose":"interpretation","text":"零值含义未知；排除零值不证明其为未观测。","claim_refs":[snapshot.as_dict()["claims"][0]["id"]]}]
    calls=[]
    def scoped_audit(candidate):
        calls.append(candidate)
        # Frozen independent fixture decisions, not a product prose validator.
        return {"schema":"publication_audit.v2","snapshot_digest":candidate["snapshot_digest"],"draft_digest":candidate["draft_digest"],
            "decisions":[{"part_id":p["part_id"],"disposition":disposition,"reason":reason,"evidence_refs":p["requirement_ids"]+p["claim_refs"]}
                for p,disposition,reason in zip(candidate["parts"],["reject","accept"],["no maturity or ROI evidence","descriptive boundary"])]}
    answer=PublicationService(snapshot,auditor=scoped_audit).publish(encode(payload)).as_dict()
    assert len(calls)==1 and "ROI最高" not in answer["body"]
    assert "零值含义未知" in answer["body"]
    assert {t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}=={cid for r in snapshot.as_dict()["requirements"] if not r["withdrawn"] for cid in r["claim_ids"]}
    assert answer["source_snapshot"]["claims"]==snapshot.as_dict()["claims"]


def test_timestamp_chart_first_static_attempt_uses_canonical_figure(context):
    from data_agent.tools.visualization import _save_chart
    from data_agent.config import get_config
    from PIL import Image
    fig = go.Figure(go.Scatter(x=list(pd.date_range('2020-07-01', periods=3)), y=[1,2,3]))
    original = fig.to_json()
    _save_chart(fig, 'timestamp', {'purpose':'exploratory','validation_status':'valid','title':'timestamp'})
    root = get_config().sessions_resolved / context.session_id / 'charts'
    meta = json.loads(next(root.glob('*.json')).read_text('utf8'))
    assert meta['static_image']['status'] == 'completed', meta['static_image']
    assert meta['static_image']['attempts'] == 1
    assert meta['figure']['data'] == json.loads(original)['data']
    with Image.open(next(root.glob('*.png'))) as png:
        png.verify()
    # Only the publication annotation is added; the interactive figure must
    # not inherit the static renderer's fixed dimensions.
    assert fig.layout.width is None and fig.layout.height is None


def test_combined_bar_labels_keep_full_identity_and_use_bounded_ticks(context):
    from data_agent.config import get_config
    from data_agent.tools.visualization import create_chart

    frame = pd.DataFrame({
        'region': [f'超长区域名称-{index:02d}' for index in range(15)],
        'channel': [f'渠道名称-{index % 3}-特别长' for index in range(15)],
        'campaign': [f'活动批次-{index:02d}-长标签' for index in range(15)],
        'revenue': list(range(15)),
    })
    context.workspace.add('combinations', frame)
    original = context.workspace.get('combinations').copy(deep=True)
    result = create_chart('bar', data='combinations', label_columns='region,channel,campaign',
                          y_col='revenue', title='组合收入')
    assert 'Chart saved:' in result
    root = get_config().sessions_resolved / context.session_id / 'charts'
    meta = json.loads(next(root.glob('*.json')).read_text('utf8'))
    xaxis = meta['figure']['layout']['xaxis']
    assert xaxis['tickmode'] == 'array'
    assert len(xaxis['tickvals']) == len(xaxis['ticktext']) == 15
    assert all(len(text) <= 18 for text in xaxis['ticktext'])
    assert any('…' in text for text in xaxis['ticktext'])
    assert meta['axis_label_presentation']['identity_preserved_in_tickvals'] is True
    assert meta['axis_label_presentation']['max_tick_characters'] == 18
    assert xaxis['tickangle'] == -90
    assert meta['axis_label_presentation']['truncated_count'] > 0
    assert meta['figure']['data'][0]['x'] == xaxis['tickvals']
    pd.testing.assert_frame_equal(context.workspace.get('combinations'), original)


def test_html_export_bounds_wide_content_and_workbench_collapses_details():
    from data_agent.tools.report import _html_from_markdown
    from data_agent.web.app import create_app

    exported = _html_from_markdown('Report', '| very-long-column | other |\n|---|---|\n| ' + 'x' * 300 + ' | y |')
    assert 'table{border-collapse:collapse;width:100%;max-width:100%' in exported
    assert '.chart-container{overflow-x:auto}' in exported
    assert 'overflow-wrap:anywhere;word-break:break-word' in exported
    assert exported.count('<h1>Report</h1>') == 1
    page = create_app().test_client().get('/').get_data(as_text=True)
    assert '<details x-show="conclusion.summary" class="workbench-conclusion-details mt-1">' in page
    assert '<summary>查看计算详情</summary>' in page


def test_original_d1_d7_weighted_definitions_and_maximum_difference_are_delivered(engine):
    from tests.test_trusted_publication_semantics import execute
    from tests.test_trusted_publication_runtime import request,draft
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.service import PublicationService
    import pytest
    loop,_ = engine
    loop.context.workspace.add("original_cohorts",pd.DataFrame({"cohort_size":[1,3],"D1":[.17634,.16526],"D7":[.05244,.04956]}))
    for field in ("D1","D7","maximum_difference"):
        request(loop,"交代"+field+"普通与加权口径差异",{'kind': 'measurement' if field=='maximum_difference' else 'table', 'scope': {'datasets': ['original_cohorts'], 'metrics': [field], 'quantity': 'value'}})
    rid,result=execute(loop,"run_python",{"code":
        "df=get_dataset('original_cohorts')\n"
        "result={}\n"
        "for day in ['D1','D7']:\n"
        "    ordinary=float(df[day].mean()); weighted=float((df[day]*df['cohort_size']).sum()/df['cohort_size'].sum())\n"
        "    result[day]={'ordinary':ordinary,'weighted':weighted,'absolute_difference':abs(ordinary-weighted),'unit':'fraction','ordinary_definition':'equal cohort weights','weighted_definition':'cohort_size weights'}\n"
        "result['maximum_difference']=max(result[d]['absolute_difference'] for d in ['D1','D7'])\nresult",
        "purpose":"original D1 and D7 complete methodology comparison"})
    expected={"D1":(.17080,.16803,.00277),"D7":(.05100,.05028,.00072)}
    for day,(ordinary,weighted,delta) in expected.items():
        assert result['result_data'][day]['ordinary']==pytest.approx(ordinary,abs=1e-14)
        assert result['result_data'][day]['weighted']==pytest.approx(weighted,abs=1e-14)
        assert result['result_data'][day]['absolute_difference']==pytest.approx(delta,abs=1e-14)
    assert result['result_data']['maximum_difference']==pytest.approx(.00277,abs=1e-14)
    host=snapshot_for_turn(loop);answer=PublicationService(host).publish(draft(host)).as_dict()
    assert [o['status'] for o in answer['requirement_outcomes']]==['answered']*3
    claims=host.as_dict()['claims'];bound=[c for c in claims if c['basis_refs'][0]['result_path'] in [['result_data',f] for f in ('D1','D7','maximum_difference')]]
    assert len(bound)==3 and all(c['basis_refs'][0]['receipt_id']==rid for c in bound)
    assert all(c['value']==result['result_data'][c['basis_refs'][0]['result_path'][-1]] for c in bound)
    assert {t['ref'] for t in answer['render_trace'] if t['kind']=='claim'} >= {c['id'] for c in bound}
    assert 'equal cohort weights' in visible_text(answer['body']) and 'cohort_size weights' in visible_text(answer['body'])


# Typed display contracts use canonical values; application-path binding is
# separately exercised by test_s3_business_tables_normal_agentloop.
def _business_render_claim(tool, output, value):
    params = ({"topn_output":output,"topn_columns":["group","amount"],"topn_sort_by":"amount","topn_ascending":False,"topn_n":4}
              if tool == "top_n" else {"comparison_output":output,"comparison_dimensions":["group"],"comparison_formulas":{}})
    return {"label":"original label","value":value,"unit":None,"scope":{"dataset":"experiment","population":"当前范围","grain":"原计算粒度","time_scope":json.dumps({"period_a":["2026-09-01","2026-09-02"],"period_b":["2026-09-03","2026-09-06"]})},"limitations":["关联不证明因果"],"target":{"tool":tool,"business_product":{"kind":"table","metrics":["amount"],"parameters":params}},"basis_refs":[{"session_id":"s","receipt_id":"r","tool_name":tool,"result_sha256":"sha256:original","data_identities":{"experiment":{"version_id":"v1"}},"result_path":["records" if tool=="top_n" else "comparisons"]}]}


def test_business_topn_table_keeps_original_precision_unknown_zero_order_and_safe_text():
    from data_agent.agent.publication.renderer import claim_text
    c=_business_render_claim("top_n","records",[{"group":"D","amount":999},{"group":"A|<img src=x onerror=bad>\n[*link*](javascript:bad)","amount":.423456789012345},{"group":"zero","amount":0},{"group":"null text","amount":None}])
    body=claim_text(c)
    assert "| D | 999 |" in body and "0.423456789012345" in body
    assert "| zero | 0 |" in body and "| null text | 未知 |" in body
    assert body.index("| D |")<body.index("0.423456789012345")<body.index("| zero |")
    assert "A\\|&lt;img" in body and "<img" not in body and "["+"*link*"+"]" not in body
    assert "amount 降序" in body and "请求前 4 条" in body and "关联不证明因果" in body
    assert c["value"][1]["amount"]==.423456789012345 and c["value"][1]["group"].startswith("A|")


def test_business_topn_empty_table_retains_columns_and_real_zero_counts():
    from data_agent.agent.publication.renderer import claim_text
    c=_business_render_claim("top_n","records",[])
    assert "| group | amount |" in claim_text(c) and "无返回记录" in claim_text(c)
    c["target"]["business_product"]["parameters"]["topn_output"]="observation";c["value"]={"source_rows":0,"returned_rows":0}
    assert "| 0 | 0 |" in claim_text(c)


def _render_comparison_item(a=999,b=1998):
    audit={"source_rows":1,"effective_rows":1,"excluded_rows":0,"missing_value":0,"nonfinite_value":0}
    return {"aggregation":{"operator":"sum"},"exact_aggregates":{"a":a,"b":b,"diff":999 if a is not None else None},"change_pct":100 if a else None,"daily_avg_a":499.5 if a else None,"daily_avg_b":499.5,"daily_avg_diff":0 if a else None,"daily_avg_change_pct":0 if a else None,"observation":{"a":dict(audit),"b":dict(audit)},"completion_gaps":[],"percentage_limitation":""}


@pytest.mark.parametrize("fault",["none","session_id","receipt_id","result_sha256","data_identities"])
def test_business_period_day_counts_bind_only_same_receipt_and_version(fault):
    from copy import deepcopy
    from data_agent.agent.publication.renderer import claim_text
    c=_business_render_claim("compare_periods","comparison",[{"dimension_values":{"group":"D"},"amount":_render_comparison_item()}]);context=[]
    for period,n in [("period_a",2),("period_b",4)]:
        for key,v in [("day_count",n),("rows",4)]:
            other=deepcopy(c);other["value"]=v;other["basis_refs"][0]["result_path"]=[period,key]
            if fault!="none":other["basis_refs"][0][fault]="other"
            context.append(other)
    body=claim_text(c,context=context)
    assert "2026-09-01—2026-09-02" in body and "2026-09-03—2026-09-06" in body
    assert ("（2天；4条）" in body)==(fault=="none")
    if fault!="none":assert body.count("（未知天；未知条）")==2
    assert "| D | 999 | 1998 | 999 | 100% | 1 | 1 | 499.5 | 499.5 | 0 | 0% |" in body
    assert "前期值的绝对值" in body and "exact_aggregates" not in body


def test_business_comparison_keeps_all_groups_multiple_metrics_and_unknown_range_audit():
    from data_agent.agent.publication.renderer import claim_text
    rows=[]
    for i in range(11):
        item=_render_comparison_item(None if i==10 else i,2*i);item["observation"]["a"].update(effective_rows=0,excluded_rows=1,missing_value=1)
        item["completion_gaps"]=["缺失被排除，原范围不完整"]
        rows.append({"dimension_values":{"group":"g"+str(i),"region":"R"},"amount":item,"cost":item})
    c=_business_render_claim("compare_periods","comparison",rows);c["target"]["business_product"]["metrics"]=["amount","cost"];c["target"]["business_product"]["parameters"]["comparison_dimensions"]=["group","region"]
    body=claim_text(c)
    assert body.count("| g10 | R | 未知")==2 and "cost（求和）" in body and "amount（求和）" in body
    assert "| g10 | R | 前期 | 指标 | 1 | 0 | 1 | 1 | 0 |" in body
    assert "缺失被排除，原范围不完整" in body and "Infinity" not in body
    assert len(c["value"])==11 and c["value"][-1]["amount"]["exact_aggregates"]["a"] is None


def test_business_ungrouped_ratio_table_uses_exact_values_and_original_operand_sums():
    from data_agent.agent.publication.renderer import claim_text
    item=_render_comparison_item();item.pop("daily_avg_a");item.pop("daily_avg_b");item.pop("daily_avg_diff");item.pop("daily_avg_change_pct")
    item["exact_aggregates"]={"period_a":.423456789012345,"period_b":None,"diff":None};item["change_pct"]=None;item["observation"]={"period_a":item["observation"]["a"],"period_b":item["observation"]["b"]};item["aggregation"]={"operator":"ratio_of_sums","numerator":"cost","denominator":"orders","operand_sums":{"period_a":{"numerator":1.270370367037035,"denominator":3},"period_b":{"numerator":7,"denominator":0}}};item["percentage_limitation"]="零分母，比率未知"
    c=_business_render_claim("compare_periods","comparison",{"amount":item});c["target"]["business_product"]["parameters"].update(comparison_dimensions=[],comparison_formulas={"amount":{"operator":"ratio_of_sums","numerator":"cost","denominator":"orders"}})
    body=claim_text(c)
    assert "| 0.423456789012345 | 未知 | 未知 | 未知 |" in body and "前期值" in body
    assert "| 前期 | 1.270370367037035 | 3 |" in body and "| 后期 | 7 | 0 |" in body
    assert "cost 合计 ÷ orders 合计" in body and "零分母，比率未知" in body and "日均" not in body


def test_business_rendering_keeps_json_strings_literal_and_structured_data_complete():
    from data_agent.agent.publication.renderer import claim_text
    c=_business_render_claim("top_n","records",'{"group":"D","amount":999}')
    body=claim_text(c);assert "| ---" not in body and c["value"] in body
    c=_business_render_claim("preview_data","records",[{"group":"D","amount":999,"family":"business family","nested":None},{"group":"A|<img src=x>","amount":0,"family":"other","nested":{"raw":.423456789012345}}])
    body=claim_text(c)
    assert "| group | amount | family |" in body and "模型族" not in body
    assert "| D | 999 | business family |" in body and "0.423456789012345" in body and "未知" in body
    assert "<img" not in body and "\\|&lt;img" in body and '[{"' not in body
    matrix=_business_render_claim("run_python","records",{"rowA":{"a":0,"b":None},"rowB":{"a":1,"b":2}})
    matrix_body=claim_text(matrix)
    assert "| 条目 | a | b |" in matrix_body and "| rowA | 0 | 未知 |" in matrix_body and "| rowB | 1 | 2 |" in matrix_body


@pytest.mark.parametrize("interface", ["renderer", "accepted_answer", "session_api"])
def test_s3_new_period_windows_are_readable_without_rewriting_scope_or_answer(engine, interface):
    import os
    from copy import deepcopy
    from data_agent.agent.publication.renderer import claim_text
    from data_agent.agent.publication.runtime import snapshot_for_turn, publish, commit, read_answer
    from data_agent.session.history import load_session
    from data_agent.web.app import create_app
    from data_agent.tools.report import export_assistant_reply
    from tests.test_trusted_publication_runtime import request, draft
    from tests.test_trusted_publication_semantics import execute
    loop, cfg = engine
    request(loop, "比较前后六天amount的差值", {"kind":"measurement", "scope":{
        "datasets":["orders"], "metrics":["amount"], "quantity":"difference"}})
    execute(loop, "compare_periods", {"name":"orders", "date_col":"day", "metrics":"amount",
        "period_a":"2026-09-01~2026-09-06", "period_b":"2026-09-07~2026-09-12"})
    snapshot = snapshot_for_turn(loop)
    claim = next(c for c in snapshot.as_dict()["claims"] if c["label"] == "amount：差值")
    original_claim = deepcopy(claim)
    rendered = claim_text(claim, context=snapshot.as_dict()["claims"])
    body, error = publish(loop, draft(snapshot))
    assert error is None and commit(loop, {"role":"assistant"}, body) is None
    saved = load_session(loop.session_id); owner = saved["messages"][-1]
    answer = read_answer(loop.session_id, owner["answer_ref"])
    with create_app().test_client() as http:
        refreshed = http.get("/api/sessions/"+loop.session_id).get_json()
        view = http.get("/api/sessions/"+loop.session_id+"/trust").get_json()
    exported = export_assistant_reply(loop.session_id, body, "md", reply_id=owner["reply_id"])
    md = (cfg.sessions_resolved/loop.session_id/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    visible = rendered if interface == "renderer" else body if interface == "accepted_answer" else view["workbench"]["verified_conclusions"][0]["summary"]
    out = Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/("new_period_window_"+interface+".json")).write_text(json.dumps({"interface":interface,
        "claim":claim,"rendered":rendered,"answer":answer,"saved":saved,"refreshed":refreshed,"view":view,"export_md":md,"provider_calls":0},
        ensure_ascii=False,indent=2), encoding="utf-8")
    assert claim == original_claim and claim["value"] == 60
    assert json.loads(claim["scope"]["time_scope"]) == {"period_a":["2026-09-01","2026-09-06"], "period_b":["2026-09-07","2026-09-12"]}
    assert body == answer["body"] == owner["content"] and body in md
    assert next(m for m in refreshed["messages"] if m.get("answer_ref")==owner["answer_ref"])["content"] == body
    assert view["workbench"]["verified_conclusions"][0]["summary"] == rendered
    assert '"period_a"' not in visible and '"period_b"' not in visible
    assert "前期：2026-09-01—2026-09-06" in visible and "后期：2026-09-07—2026-09-12" in visible


@pytest.mark.parametrize("window", ["原回执范围", "{bad-json", {"period_a":["a","b"]},
    {"period_a":["a","b"],"period_b":["c","d"],"extra":"must remain visible"},
    {"sha256":"original-hash","offset":0,"end_offset":40},
    {"period_a":[{"unverified":"label"},"b"],"period_b":["c","d"]}])
def test_s3_window_display_never_reinterprets_prose_or_drops_other_scope_fields(window):
    from data_agent.agent.publication.renderer import claim_text
    claim = _business_render_claim("compare_periods", "other", 0)
    claim["target"].pop("business_product")
    original = window if isinstance(window, str) else json.dumps(window, ensure_ascii=False)
    claim["scope"]["time_scope"] = original
    assert original in claim_text(claim)
    assert claim["scope"]["time_scope"] == original



def test_standalone_html_renders_math_and_exact_owned_chart_at_body_position():
    from data_agent.tools.report import _html_from_markdown
    path = 'sessions/own/charts/owned_abc123.html'
    entry = {'path': path, 'html': '<div class="chart-container" data-owned="yes">REAL CHART</div>'}
    markdown = ('Before\n\n[chart](/api/files/' + path + ')\n\nAfter\n\n'
                r'Calculation: $$\frac{120}{12}=10$$' + '\n\n' +
                r'`$$not_math$$`' + '\n\n' +
                '[foreign](/api/files/sessions/other/charts/owned_abc123.html)\n\n'
                '[bad hash](/api/files/sessions/own/charts/owned_ffffff.html)')
    html = _html_from_markdown('Report', markdown, chart_entries=[entry])
    body = html.split('<body>', 1)[1]
    assert body.index('Before') < body.index('REAL CHART') < body.index('After')
    assert html.count('data-owned="yes"') == 1 and 'Supplemental chart' not in html
    assert html.count('class="export-math"') == 1
    assert 'data-tex="' in html and 'katex.render(' in html and 'trust: false' in html
    assert 'data:font/woff2;base64,' in html and 'url(fonts/' not in html
    assert '<code>$$not_math$$</code>' in html
    assert 'href="/api/files/sessions/other/' in html
    assert 'href="/api/files/sessions/own/charts/owned_ffffff.html"' in html



def test_s4_complete_curve_tables_keep_every_original_field_and_no_json_dump(engine):
    from copy import deepcopy
    from html.parser import HTMLParser
    import mistune
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.service import PublicationService
    from data_agent.agent.publication.renderer import claim_text
    from tests.test_trusted_publication_runtime import request, draft
    from tests.test_trusted_publication_semantics import execute
    loop, _ = engine
    loop.context.workspace.add('curve_readable', pd.DataFrame({'day':range(1,8),'retention':[.55,.42,.31,.24,.18,.13,.1]}))
    params={'zero_values':'keep','scenario_points':[30]}
    request(loop,'保留全部观测、拟合参数和误差、未验证D30情景',[
        {'kind':kind,'scope':{'datasets':['curve_readable'],'metrics':['retention'],'parameters':params}}
        for kind in ('series','fit','scenario')])
    execute(loop,'curve_fitting',{'name':'curve_readable','x_col':'day','y_col':'retention',**params})
    snapshot=snapshot_for_turn(loop);original=snapshot.as_dict()
    answer=PublicationService(snapshot).publish(draft(snapshot)).as_dict()
    assert all(o['status']=='answered' for o in answer['requirement_outcomes'])
    assert answer['source_snapshot']==original
    class Cells(HTMLParser):
        def __init__(self):super().__init__();self.cells=[];self.current=None
        def handle_starttag(self,tag,attrs):
            if tag in ('td','th'):self.current=''
        def handle_data(self,text):
            if self.current is not None:self.current+=text
        def handle_endtag(self,tag):
            if tag in ('td','th') and self.current is not None:self.cells.append(self.current);self.current=None
    def leaves(value):
        if isinstance(value,dict):
            for nested in value.values():yield from leaves(nested)
        elif isinstance(value,list):
            for nested in value:yield from leaves(nested)
        else:yield '未知' if value is None else str(value)
    compound=[c for c in original['claims'] if c['basis_refs'][0]['result_path'] in (['points'],['fits'],['scenarios'])]
    assert len(compound)==3
    for claim in compound:
        before=deepcopy(claim);body=claim_text(claim,context=original['claims'])
        cells=Cells();cells.feed(mistune.create_markdown(plugins=['table'])(body))
        assert all(value in cells.cells for value in leaves(claim['value']))
        assert '[{"' not in body and '"family"' not in body
        assert claim==before and '单位未知' in body
    assert '拟合值' in answer['body'] and '残差' in answer['body'] and '未验证' in answer['body']
    dangerous=deepcopy(next(c for c in compound if c['basis_refs'][0]['result_path']==['fits']))
    dangerous['value'][0]['family']='A|<img src=x onerror=bad>'
    assert '<img' not in claim_text(dangerous,context=original['claims'])
    literal=deepcopy(dangerous);literal['value']='[{"family":"literal JSON string"}]'
    assert literal['value'] in claim_text(literal) and '| 模型族 |' not in claim_text(literal)
    assert snapshot.as_dict()==original


def test_s4_scalar_grouping_preserves_identity_owners_limits_and_body_positions(engine):
    from copy import deepcopy
    from data_agent.agent.publication.renderer import Renderer
    from data_agent.agent.publication.native import resolve_native_claims
    from tests.test_trusted_publication_semantics import execute
    loop,_=engine
    rid,_=execute(loop,'compare_periods',{'name':'orders','date_col':'day','metrics':'amount','period_a':'2026-09-01~2026-09-06','period_b':'2026-09-07~2026-09-12'})
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    source=next(c for c in claims if c['basis_refs'][0]['result_path']==['metrics','amount','exact_aggregates','period_a'])
    original=deepcopy(source)
    for difference in ('same','receipt','session','version','window','limits','owner','unit_proof','intervening','interleaved'):
        a,b=deepcopy(source),deepcopy(source);b['id']='display_second';b['label']='second scalar';b['value']=None
        if difference=='receipt':b['basis_refs'][0]['receipt_id']='other_receipt'
        if difference=='session':b['basis_refs'][0]['session_id']='other_session'
        if difference=='version':next(iter(b['basis_refs'][0]['data_identities'].values()))['version_id']='other_version'
        if difference=='window':b['scope']['time_scope']='other window'
        if difference=='limits':b['limitations'].append('second claim only')
        if difference=='unit_proof':b['target']['source_unit_proof']={'render_as_source_label':True,'units':['explicit unit']}
        view=Renderer();view.add_claim(a,context=claims,part_id='first',ref=a['id'],requirement_ids=['owner'])
        if difference=='intervening':view.add('chart must stay here',part_id='middle',kind='artifact',ref='chart')
        if difference=='interleaved':
            c=deepcopy(source);c['id']='other_display';c['scope']['dataset']='other_source'
            view.add_claim(c,context=claims,part_id='other',ref=c['id'],requirement_ids=['owner'])
        view.add_claim(b,context=claims,part_id='second',ref=b['id'],requirement_ids=['different_owner'] if difference=='owner' else ['owner'])
        body=view.body;by_id={row['part_id']:row for row in view.trace}
        assert all(body[row['start']:row['end']]==row['rendered_text'] for row in view.trace)
        assert (by_id['first']['start']==by_id['second']['start'])==(difference in ('same','interleaved'))
        assert '未知' in body
        if difference=='limits':assert 'second claim only' in by_id['second']['rendered_text'] and 'second claim only' not in by_id['first']['rendered_text']
        if difference=='owner':assert by_id['first']['requirement_ids']==['owner'] and by_id['second']['requirement_ids']==['different_owner']
        if difference=='intervening':assert by_id['first']['end']<body.index('chart must stay here')<by_id['second']['start']
    assert source==original
