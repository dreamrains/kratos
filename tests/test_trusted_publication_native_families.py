"""Actual registered method families and exact demand selectors."""
import json
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number, has_matrix_cell
import pandas as pd
import pytest
from data_agent.agent.publication.contracts import encode
from tests.test_trusted_publication_semantics import engine, execute, history, source_ref, change

@pytest.mark.parametrize("tool,args,key",[
    ("curve_fitting",{"name":"orders","x_col":"x","y_col":"amount"},"points"),
    ("transform_data",{"name":"orders","operation":"group_aggregate","group_by":["group"],"aggregations":[{"column":"amount","functions":["sum"]}]},"measurement_records"),
    ("run_python",{"code":"df=get_dataset('orders'); result={'sum':float(df['amount'].sum())}","purpose":"current total"},"result_data"),
    ("analyze_time_series",{"name":"orders","date_col":"day","value_col":"amount"},"statistics"),
    ("top_n",{"name":"orders","sort_by":"amount","n":12},"records"),
    ("distribution_analysis",{"name":"orders","columns":"amount"},"amount"),
    ("forecast",{"name":"orders","target_col":"amount","date_col":"day","periods":3},"forecast"),
])
def test_actual_family_keeps_original_complete_measurements(engine,tool,args,key):
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-09-01",periods=30),"x":range(1,31),"amount":range(1,31),"group":["A","B","C"]*10}))
    rid,result=execute(loop,tool,args)
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    selected=next(c for c in claims if c["basis_refs"][0]["result_path"]==[key])
    assert selected["value"]==result[key] and selected["unit"] is None
    assert selected["target"]["dataset"]=="orders"
    if tool=="top_n": assert len(selected["value"])==12
    if tool=="transform_data": assert sum(row["amount_sum"] for row in selected["value"])==465
    if tool=="run_python": assert selected["value"]=={"sum":465}
    if tool=="curve_fitting": assert len(selected["value"])==30 and len(result["fits"])==3
    if tool=="forecast": assert result["parameters"]["backtest_scheme"]=="ordered_holdout" and len(selected["value"])==3

@pytest.mark.parametrize("fault",[None,"wrong_dataset","wrong_metric","wrong_window","wrong_method"])
def test_typed_requirement_binding_never_guesses_from_repeated_numbers(engine,fault):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine
    loop.context.workspace.add("other",pd.DataFrame({"amount":[60,120]}))
    scope={"datasets":["orders"],"metrics":["amount"],"parameters":{"period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"}}
    if fault=="wrong_dataset":scope["datasets"]=["other"]
    if fault=="wrong_metric":scope["metrics"]=["cost"]
    if fault=="wrong_window":scope["parameters"]["period_a"]="2026-08-01~2026-08-06"
    specs=[{"kind":"forecast","scope":scope}] if fault=="wrong_method" else [{"kind":"measurement","scope":dict(scope,quantity=q)} for q in ["sum","difference","relative_change"]]
    request(loop,"比较当前 amount 两期变化",specs)
    execute(loop,"compare_periods",{"name":"orders","date_col":"day","metrics":"amount","period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"})
    row=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert row["id"]==loop.context.analysis_state.answer_requirements[0]["id"]
    if fault:
        assert row["claim_ids"]==[]
        assert row["gap"]["status"]==("failed" if fault in {"wrong_dataset","wrong_window"} else "not_computed")
        if fault in {"wrong_dataset","wrong_window"}:assert "product_scope_mismatch" in row["gap"]["reason"]
    else:assert len(row["claim_ids"])==4 and row["gap"] is None


@pytest.mark.parametrize("rate,expected",[(.051,1142.4),(.01417,317.408)])
def test_registered_python_product_uses_original_operands_and_model_cannot_replace_value(engine,rate,expected):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from tests.test_trusted_publication_runtime import request,draft
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"users":[22400],"rate":[rate]}))
    request(loop,"Compute product of current operands",{'kind': 'table', 'scope': {'datasets': ['orders']}})
    code="df=get_dataset('orders'); result={'users':int(df['users'].iloc[0]),'rate':float(df['rate'].iloc[0]),'product':float(df['users'].iloc[0]*df['rate'].iloc[0])}"
    rid,result=execute(loop,"run_python",{"code":code,"purpose":"original product"})
    snapshot=snapshot_for_turn(loop)
    claim=next(c for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["receipt_id"]==rid)
    assert claim["value"]["users"]==22400 and claim["value"]["rate"]==rate
    assert claim["value"]["product"]==pytest.approx(expected,abs=1e-10)
    assert claim["unit"] is None
    proposal=json.loads(draft(snapshot));proposal["sections"][0]["parts"][0]["value"]=11400 if rate==.051 else 3200
    # A local value override is rejected once; original host operands survive.
    body,error=publish(loop,json.dumps(proposal));assert error is None
    assert loop._accepted_answer["issues"][0]["code"]=="invalid_fields"
    assert loop._accepted_answer["source_snapshot"]["claims"][0]["value"]["product"]==pytest.approx(expected,abs=1e-10)
    assert all(has_number(body, key, value) for key, value in claim["value"].items()) and not getattr(loop,"_turn_finalization_recovery_used",False)



def test_grouped_integer_sum_does_not_overflow_original_result(engine):
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"group":["all","all"],"amount":[9_000_000_000_000_000_000]*2}))
    rid,result=execute(loop,"transform_data",{"name":"orders","operation":"group_aggregate","group_by":["group"],"aggregations":[{"column":"amount","functions":["sum"]}]})
    assert result["measurement_records"][0]["amount_sum"]==18_000_000_000_000_000_000
    claim=next(c for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid) if c["basis_refs"][0]["result_path"]==["measurement_records"])
    assert claim["value"]==result["measurement_records"]


@pytest.mark.parametrize("tool,args,keys",[
    ("preview_data",{"name":"orders","n":7},["data","shape"]),
    ("quick_profile",{"name":"orders"},["shape","columns"]),
    ("detect_data_quality",{"name":"orders"},["issues","total_issues"]),
    ("correlation_analysis",{"name":"orders","columns":"x,amount"},["columns_analyzed","high_correlations"]),
    ("segmentation_analysis",{"name":"orders","features":"x,amount","n_clusters":3},["clusters","total_samples"]),
    ("cohort_analysis",{"name":"orders","user_col":"user","time_col":"day"},["cohorts","right_censoring"]),
    ("contribute_decomposition",{"name":"orders","metric":"amount","dimension":"group","date_col":"day","period_a":"2026-09-01~2026-09-20","period_b":"2026-09-21~2026-10-10"},["decomposition","total_change"]),
    ("funnel_analysis",{"name":"orders","mode":"aggregate","step_col":"step","count_col":"count","steps":"view,buy"},["steps"]),
    ("ab_test",{"name":"orders","group_col":"group","metric_col":"amount","method":"ttest"},["groups","test"]),
    ("classification",{"name":"orders","target_col":"class","features":"x","method":"rf","cv_folds":3},["metrics","feature_importance","train_size","test_size","cv"]),
    ("regression_analysis",{"name":"orders","target_col":"amount","features":"x","method":"gbrt","cv_folds":3},["metrics","feature_importance","train_size","test_size","cv"]),
    ("causal_analysis",{"name":"orders","treatment_col":"treat","outcome_col":"amount","time_col":"period","method":"did"},["did_effect","ci_95","group_means"]),
    ("shap_analysis",{"name":"orders","target_col":"amount"},["shap_importance","model_identity"]),
    ("attribution_analysis",{"name":"orders","target_col":"amount","features":"x"},["estimates"]),
    ("what_if_simulation",{"name":"orders","mode":"sensitivity","metric":"amount","dimension":"group","change_pct":10},["baseline","projected","impact","breakdown"]),
    ("synthesize_time_series",{"datasets":"orders,other","date_col":"day","metrics":"orders:amount,other:amount"},["aligned_rows","coverage","source_identities"]),
])
def test_remaining_actual_families_publish_original_results_and_current_sources(engine,tool,args,keys):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.agent.publication.service import PublicationService
    from tests.test_trusted_publication_runtime import request,draft
    from data_agent.session.history import load_session
    loop,_=engine
    frame=pd.DataFrame({"day":list(pd.date_range("2026-09-01",periods=40))*2,"x":list(range(1,41))*2,
        "amount":[2*x+1+(i//40)*5 for i,x in enumerate(list(range(1,41))*2)],"group":["A"]*40+["B"]*40,
        "user":["u"+str(i%10) for i in range(80)],"class":[i%2 for i in range(80)],
        "treat":[0]*40+[1]*40,"period":([0]*20+[1]*20)*2,"step":(["view"]*20+["buy"]*20)*2,"count":[2]*20+[1]*20+[3]*20+[1]*20})
    loop.context.workspace.add("orders",frame)
    loop.context.workspace.add("other",frame.iloc[2:-2].copy())
    kind={"preview_data":"table","correlation_analysis":"table","cohort_analysis":"table","segmentation_analysis":"table","contribute_decomposition":"table","funnel_analysis":"table","ab_test":"table","attribution_analysis":"table","classification":"fit","regression_analysis":"fit","what_if_simulation":"scenario","synthesize_time_series":"series"}.get(tool,"measurement")
    scope={"datasets":["orders","other"] if tool=="synthesize_time_series" else ["orders"]}
    if tool=="shap_analysis":
        kind="table";scope.update(metrics=["amount"],parameters={"model_kind":"regression","shap_output":"overall"})
    if kind=="measurement":scope["quantity"]="value"
    if tool=="detect_data_quality":scope.update(quantity="count",parameters={"quality_output":"total_issues"})
    declarations=([{"kind":"table","scope":{"datasets":["orders"],"parameters":{"profile_compact":False,"diagnostic_output":key}}} for key in keys]
                  if tool=="quick_profile" else {"kind":kind,"scope":scope})
    request(loop,"交付当前方法的实际结果",declarations)
    if tool=="shap_analysis":
        # Train through the existing registry on this exact current source.
        execute(loop,"regression_analysis",{"name":"orders","target_col":"amount","features":"x","method":"gbrt"})
    rid,result=execute(loop,tool,args)
    assert "error" not in result,result
    snapshot=snapshot_for_turn(loop)
    claims=[c for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["receipt_id"]==rid]
    paths={tuple(c["basis_refs"][0]["result_path"]):c for c in claims}
    for key in keys:
        assert key in result,(tool,key,result)
        assert (key,) in paths,(tool,key,paths)
        assert paths[(key,)]["value"]==result[key]
    if tool in {"classification","regression_analysis"}:
        assert result["train_size"]+result["test_size"]==80 and result["cv"]["folds"]==3
    if tool=="what_if_simulation":
        assert result["baseline"]["total"]==frame.amount.sum()
        assert result["projected"]["total"]==pytest.approx(frame.amount.sum()*1.1,abs=1e-8)
    if tool=="segmentation_analysis": assert sum(row["size"] for row in result["clusters"])==80
    if tool=="synthesize_time_series":
        assert result["aligned_rows"]==40
        assert set(claims[0]["basis_refs"][0]["data_identities"])=={"orders","other"}
    payload=json.loads(draft(snapshot))
    bound=set(snapshot.as_dict()["requirements"][0]["claim_ids"])
    payload["sections"][0]["parts"]=[part for part in payload["sections"][0]["parts"] if part["ref"] in bound]
    body,error=publish(loop,json.dumps(payload,ensure_ascii=False))
    assert error is None
    answer=loop._accepted_answer
    assert answer["issues"]==[]
    assert answer["requirement_outcomes"][0]["status"]=="answered",answer["requirement_outcomes"]
    accepted={t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    assert accepted==bound  # Professional body closes the requested deliveries.
    assert {c["id"] for c in claims}.issubset({c["id"] for c in answer["source_snapshot"]["claims"]})  # Full method/provenance remains inspectable.
    # Persist through the same existing runtime CAS/manifest transaction.
    assert commit(loop,{"role":"assistant"},answer["body"]) is None
    message=load_session(loop.session_id)["messages"][-1]
    stored=read_answer(loop.session_id,message["answer_ref"])
    assert stored["body"]==message["content"]==answer["body"]
    assert stored["source_snapshot"]["claims"]==snapshot.as_dict()["claims"]


@pytest.mark.parametrize("fault",["missing_model","stale_model"])
def test_actual_shap_keeps_model_prerequisite_and_current_identity(engine,monkeypatch,fault):
    from data_agent.tools import ml
    from data_agent.tools.registry import registry
    monkeypatch.setattr(ml,"_trained_models",{})
    monkeypatch.setattr(ml,"_trained_model_metadata",{})
    loop,_=engine
    frame=pd.DataFrame({"x":range(40),"amount":[x*x+1 for x in range(40)]})
    loop.context.workspace.add("orders",frame)
    if fault=="stale_model":
        execute(loop,"regression_analysis",{"name":"orders","target_col":"amount","features":"x","method":"gbrt"})
        loop.context.workspace.add("orders",frame.assign(amount=frame.amount+1))
    result=registry.execute("shap_analysis",{"name":"orders","target_col":"amount"})
    payload=json.loads(result.summary)
    assert "error" in payload and not payload.get("shap_importance")
    if fault=="stale_model": assert payload["error_type"]=="stale_model_data_identity"
    # A refused model explanation cannot register a successful source receipt.
    assert not loop._record_turn_tool_result("shap_analysis",result.summary,{"name":"orders","target_col":"amount"},"shap-refused",result.data)


def test_actual_preview_preserves_original_integer_float_and_null(engine):
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine
    value=1.1234567890123457
    loop.context.workspace.add("orders",pd.DataFrame({"integer":[9_000_000_000_000_000_001],"value":[value],"missing":[None]}))
    rid,result=execute(loop,"preview_data",{"name":"orders","n":1})
    assert result["data"]==[{"integer":9_000_000_000_000_000_001,"value":value,"missing":None}]
    claim=next(c for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid) if c["basis_refs"][0]["result_path"]==["data"])
    assert claim["value"]==result["data"] and claim["unit"] is None


def test_original_year_window_keeps_all_current_curve_observations(engine):
    # VP-C05 / CP-AC11: a valid long window cannot fail because a host
    # requirement accidentally inherits the model's 128-reference limit.
    from tests.test_publication_synthesis import _curve_actual
    from data_agent.agent.publication.runtime import snapshot_for_turn,publication_prompt
    from data_agent.agent.publication.service import PublicationService
    from tests.test_trusted_publication_runtime import draft
    loop,_,rid,result=_curve_actual(engine,days=365,scenarios=False)
    host=snapshot_for_turn(loop)
    points=[c for c in host.as_dict()['claims'] if len(c['basis_refs'][0]['result_path'])==3 and c['basis_refs'][0]['result_path'][0]=='points']
    assert len(points)==365 and [c['value'] for c in points]==[p['y'] for p in result['points']]
    assert points[-1]['value']==round(.5*365**(-.4),4)
    answer=PublicationService(host).publish(draft(host)).as_dict()
    assert answer['source_snapshot']['claims']==host.as_dict()['claims']
    assert {t['ref'] for t in answer['render_trace'] if t['kind']=='claim'}==set(host.as_dict()['requirements'][0]['claim_ids'])
    assert answer['source_snapshot']['claims']==host.as_dict()['claims']
    prompt=publication_prompt(loop)
    from data_agent.llm.request_policy import resolve_request_budget
    from data_agent.config import get_config
    cfg=get_config();policy=resolve_request_budget(cfg.model_id,cfg,cfg.max_tokens)
    assert policy.admit([{"role":"system","content":prompt}]+loop.messages)["tokens"]<=policy.input_allowance and host.digest in prompt


def test_original_oversized_required_group_remains_complete_in_model_context(engine):
    # VP-E05 / CP-AC12 / decision50: required groups retain full values in
    # the model, source and answer, bounded by actual request tokens.
    from data_agent.agent.publication.runtime import snapshot_for_turn,publication_prompt
    from data_agent.agent.publication.service import PublicationService
    from tests.test_trusted_publication_runtime import request,draft
    loop,_=engine
    request(loop,'保留超大分组及最后必答组',{'kind': 'table', 'scope': {'datasets': ['orders']}})
    rid,result=execute(loop,'run_python',{'code':"df=get_dataset('orders'); result={'first':int(df['amount'].sum()),'oversized_group':['detail-'+str(i)+'x'*210 for i in range(280)],'last_required_group':{'name':'final','amount':999}}",'purpose':'original bounded group output'})
    host=snapshot_for_turn(loop);claim=host.as_dict()['claims'][0]
    assert claim['value']['first']==180 and len(claim['value']['oversized_group'])==280
    assert claim['value']['last_required_group']=={'name':'final','amount':999}
    prompt=publication_prompt(loop)
    from data_agent.llm.request_policy import resolve_request_budget
    from data_agent.config import get_config
    cfg=get_config();policy=resolve_request_budget(cfg.model_id,cfg,cfg.max_tokens)
    assert policy.admit([{"role":"system","content":prompt}]+loop.messages)["tokens"]<=policy.input_allowance
    context=json.loads(prompt.split('</accepted_answer_contract>\n',1)[1])
    assert context['snapshot_digest']==host.digest
    projected=dict(zip(context['claim_fields'],context['claims'][0]))
    assert projected['id']==claim['id'] and projected['value']==claim['value']
    assert context['catalog_context']['scopes'][projected['scope_ref']]==claim['scope']
    assert context['catalog_context']['limitations'][projected['limitations_ref']]==claim['limitations']
    assert 'value_refs' not in context and 'value_ref' not in context['claim_fields']
    answer=PublicationService(host).publish(draft(host)).as_dict()
    assert answer['source_snapshot']['claims'][0]['value']==result['result_data']
    assert 'last_required_group' in visible_text(answer['body']) and any(['amount','999'] in table and ['name','final'] in table for table in table_rows(answer['body']))
    assert answer['requirement_outcomes'][0]['status']=='answered'


def test_model_metadata_overflow_preserves_host_facts_and_marks_open_work_unassessed(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,model_publication_context
    from data_agent.agent.publication.service import PublicationService
    from tests.test_trusted_publication_runtime import request,draft
    loop,_=engine
    request(loop,'当前合计并解释',{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}})
    loop.context.analysis_state.answer_requirements[-1]['purposes']=['interpretation']
    execute(loop,'describe_dataset',{'name':'orders'})
    host=snapshot_for_turn(loop)
    view=model_publication_context(host,loop.context.analysis_state,budget=1)
    assert [r['id'] for r in view['requirements']]==[r['id'] for r in host.as_dict()['requirements']]
    audits=[]
    answer=PublicationService(host,auditor=lambda request:audits.append(request),model_view_issue=view['model_view_issue']).publish(draft(host)).as_dict()
    assert not audits and answer['issues'][0]['code']=='publication_context_size'
    assert answer['source_snapshot']==host.as_dict()
    assert answer['requirement_outcomes'][0]['status']=='partial'
    assert '预算' in answer['requirement_outcomes'][0]['reason']
    assert {t['ref'] for t in answer['render_trace'] if t['kind']=='claim'}==set(host.as_dict()['requirements'][0]['claim_ids'])


def test_model_written_copy_is_exploratory_and_cannot_impersonate_uploaded_source(engine,tmp_path):
    from data_agent.tools.data_io import load_data
    from data_agent.tools.file_ops import write_file
    from data_agent.agent.publication.native import resolve_native_claims
    from data_agent.agent.publication.requirements import record_execution_targets
    from data_agent.session.history import load_canonical_history
    from tests.test_trusted_publication_runtime import request
    loop,cfg=engine
    source=tmp_path/'original.csv'
    source.write_text('amount\n10\n20\n',encoding='utf-8')
    assert 'Error:' not in load_data(str(source),name='uploaded')
    original=loop.context.workspace.get_data_identity('uploaded')
    write_file('copy.csv',source.read_text(encoding='utf-8'))
    loaded=load_data('copy.csv',name='copy')
    copied=loop.context.workspace.get_data_identity('copy')
    assert original['fingerprint']==copied['fingerprint']
    assert original['version_id']!=copied['version_id']
    assert copied['source_origins'][0]['kind']=='session_generated'
    assert original['version_id'] not in copied['ancestor_version_ids']
    assert '探索' in loaded
    request(loop,'合计原上传金额',{'kind': 'measurement', 'scope': {'datasets': ['uploaded'], 'metrics': ['amount'], 'quantity': 'sum'}})
    state=loop.context.analysis_state
    before=encode(state.answer_requirements);revision=state.requirement_revision
    with pytest.raises(ValueError):
        record_execution_targets(state,load_canonical_history(loop.session_id),loop.context.workspace,
            {'requirement_revision':revision,'targets':[{'requirement_id':state.answer_requirements[-1]['id'],
                'deliverables':[{'dataset':'copy','tool':'describe_dataset','metric':'amount','statistic':'sum'}]}]})
    assert encode(state.answer_requirements)==before and state.requirement_revision==revision
    rid,_=execute(loop,'describe_dataset',{'name':'copy'})
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    total=next(c for c in claims if c.get('target',{}).get('statistic')=='sum')
    assert total['value']==30 and any('会话生成文件' in limit for limit in total['limitations'])
    assert total['basis_refs'][0]['data_identities']['copy']['source_origins']==copied['source_origins']
    loop.context.workspace.save_meta(loop.session_id)
    metadata=json.loads((cfg.sessions_resolved/loop.session_id/'workspace_meta.json').read_text(encoding='utf-8'))
    assert metadata['copy']['data_identity']==copied


def _s1_register(loop, content, specs, *, dependencies=False):
    # Unit integration setup: original history and actual public plan tool.
    from data_agent.session.history import save_session,load_canonical_history
    from data_agent.agent.publication.requirements import update_requirements
    from data_agent.tools.data_io import _record_trust_workflow
    from data_agent.tools.registry import registry
    state=loop.context.analysis_state
    loop.messages.append({"role":"user","content":content,"request_id":"s1_original"})
    save_session(loop.messages,loop.session_id,extra_meta={"publication_schema":"answer_bindings.v2"},merge_protect=False)
    loop._last_jsonl_idx=len(loop.messages)
    datasets=sorted({n for s in specs for n in s.get("scope",{}).get("datasets",[])})
    ids=update_requirements(state,load_canonical_history(loop.session_id),"s1_original",[{"op":"add","start":0,"end":len(content),"kind":"result","business_scope":({"datasets":datasets} if datasets else {})}],expected_revision=state.requirement_revision)
    for dataset in datasets:
        _record_trust_workflow(session_id=loop.session_id,state=state,dataset=dataset,df=loop.context.workspace.get(dataset),applied=[],needs_confirm=[],quality={},interpretation_data={},detail_path="")
    declarations=[dict(s,requirement_id=ids[0],label="Required product "+str(i)) for i,s in enumerate(specs)]
    groups=[declarations[:-1],declarations[-1:]] if dependencies else [declarations]
    steps=[{"step_id":"s1_"+str(i),"goal":"Produce declared result","expected_output":"Declared business product","evidence_requirements":["native_receipt"],"dataset_inputs":sorted({n for d in group for n in d.get("scope",{}).get("datasets",[])}),"required_deliveries":group,**({"required_evidence_step_ids":["s1_0"]} if i else {})} for i,group in enumerate(groups)]
    result=registry.execute("record_analysis_plan",{"plan_json":{"contract_version":"stage3c0b.v2","requirement_revision":state.requirement_revision,"goal":content,"method_plan":steps,"visualization_strategy":[]}}).data
    assert "error" not in result,result
    loop.context.turn_requirement_ids=ids
    return result


@pytest.mark.parametrize("product",["mean","forecast"])
def test_s1_actual_prebound_business_product_reaches_visible_answer(engine,product):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from tests.test_trusted_publication_runtime import draft
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-09-01",periods=30),"amount":range(1,31)}))
    scope={"datasets":["orders"],"metrics":["amount"]}
    scope.update({"quantity":"mean"} if product=="mean" else {"parameters":{"forecast_periods":3}})
    plan=_s1_register(loop,"交付amount均值" if product=="mean" else "交付amount未来三期预测",[{"kind":"measurement" if product=="mean" else "forecast","scope":scope}])
    rid,result=execute(loop,"distribution_analysis" if product=="mean" else "forecast",{"name":"orders","columns":"amount"} if product=="mean" else {"name":"orders","target_col":"amount","date_col":"day","periods":3})
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    assert receipt["plan_sha256"]==plan["plan_sha256"] and receipt["step_id"]=="s1_0"
    snapshot=snapshot_for_turn(loop); req=snapshot.as_dict()["requirements"][0]
    assert req["gap"] is None,req
    claims=[c for c in snapshot.as_dict()["claims"] if c["id"] in req["claim_ids"]]
    if product=="mean": assert [c["value"] for c in claims]==[15.5]
    else:
        assert len(claims)==1
        assert [float(row["yhat"]) for row in claims[0]["value"]]==pytest.approx([31,32,33],abs=1e-8)
    body,error=publish(loop,draft(snapshot))
    assert error is None and loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"
    assert all(str(v) in body for v in ([15.5] if product=="mean" else [31,32,33]))


def test_s1_factual_step_with_open_obligation_unlocks_real_dependent_calculation(engine):
    from data_agent.session.task_manager import task_manager
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from tests.test_trusted_publication_runtime import draft
    loop,_=engine
    _s1_register(loop,"记录数、解释与amount均值",[
        {"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}},
        {"kind":"interpretation","scope":{"datasets":["orders"]}},
        {"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}},
    ],dependencies=True)
    execute(loop,"describe_dataset",{"name":"orders"})
    tasks=task_manager.list_active_for_scope(session_id=loop.session_id)
    assert next(t for t in tasks if t["step_id"]=="s1_0")["status"]=="completed",tasks
    assert next(t for t in tasks if t["step_id"]=="s1_1")["status"]=="in_progress",tasks
    execute(loop,"distribution_analysis",{"name":"orders","columns":"amount"})
    snapshot=snapshot_for_turn(loop)
    assert snapshot.as_dict()["requirements"][0]["open_purposes"]==["interpretation"]
    body,error=publish(loop,draft(snapshot))
    assert error is None and loop._accepted_answer["requirement_outcomes"][0]["status"]=="partial"


@pytest.mark.parametrize("method",["simple","prophet"])
def test_s1_forecast_rejects_retired_algorithm_aliases(engine,method):
    from data_agent.tools.registry import registry
    result=registry.execute("forecast",{"name":"orders","target_col":"amount","date_col":"day","periods":3,"method":method})
    assert result.data and "error" in result.data,result



@pytest.mark.parametrize("save_failure",[False,True])
def test_s1_real_append_keeps_prior_receipt_and_cannot_backfill_new_product(engine,monkeypatch,save_failure):
    from copy import deepcopy
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.deliveries import project_deliveries
    from data_agent.agent.publication.runtime import collect_products
    from data_agent.session.task_manager import task_manager
    loop,_=engine
    _s1_register(loop,"amount均值及必要原表",[{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}}])
    rid,_=execute(loop,"distribution_analysis",{"name":"orders","columns":"amount"})
    state=loop.context.analysis_state;before=deepcopy(state.tool_receipts)
    original=deepcopy(state.answer_requirements[0]["necessary_deliveries"])
    plan=deepcopy(state.analysis_plan);plan["requirement_revision"]=state.requirement_revision
    plan["method_plan"][0]["required_deliveries"]=[{"id":d["id"]} for d in original]+[{"requirement_id":state.answer_requirements[0]["id"],"kind":"table","label":"Amount distribution table","scope":{"datasets":["orders"],"metrics":["amount"]}}]
    if save_failure:
        saved=deepcopy((state.answer_requirements,state.requirement_revision,state.analysis_plan))
        task_bytes={p.name:p.read_bytes() for p in task_manager.dir.glob("*.json")}
        monkeypatch.setattr(state,"save",lambda: (_ for _ in ()).throw(OSError("append save failed")))
        response=registry.execute("record_analysis_plan",{"plan_json":plan})
        assert "append save failed" in response.summary
        assert (state.answer_requirements,state.requirement_revision,state.analysis_plan)==saved
        assert state.tool_receipts==before
        assert {p.name:p.read_bytes() for p in task_manager.dir.glob("*.json")}==task_bytes
        return
    response=registry.execute("record_analysis_plan",{"plan_json":plan}).data
    assert "error" not in response,response
    assert state.tool_receipts==before
    additions=state.answer_requirements[0]["delivery_additions"]
    assert additions[-1]["retained_ids"]==[original[0]["id"]] and len(additions[-1]["added_ids"])==1
    new_id=additions[-1]["added_ids"][0]
    claims,artifacts,gaps,_,effects=collect_products(state,loop.session_id)
    projection=project_deliveries(state.answer_requirements,claims,artifacts,product_gaps=gaps)[1]
    assert projection[original[0]["id"]]["gap"] is None
    assert projection[new_id]["gap"]["status"]=="not_computed"
    task=next(t for t in task_manager.list_active_for_scope(session_id=loop.session_id) if t["step_id"]=="s1_0")
    assert task["status"]=="in_progress"
    execute(loop,"distribution_analysis",{"name":"orders","columns":"amount"})
    assert snapshot_for_turn(loop).as_dict()["requirements"][0]["gap"] is None
    assert state.tool_receipts[0]==before[0]


@pytest.mark.parametrize("fault",["parameter","internal_contract","post_dispatch"])
def test_s1_gap_distinguishes_wrong_product_contract_and_absent_prebinding(engine,monkeypatch,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.contracts import ContractError
    from data_agent.tools.registry import registry
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"day":pd.date_range("2026-09-01",periods=30),"amount":range(1,31)}))
    spec={"kind":"forecast","scope":{"datasets":["orders"],"metrics":["amount"],"parameters":{"forecast_periods":3}}}
    _s1_register(loop,"交付未来三期amount",[spec])
    if fault=="post_dispatch":
        args={"name":"orders","date_col":"day","target_col":"amount","periods":3}
        output=registry.execute("forecast",args)
        loop._record_turn_tool_result("forecast",output.summary,args,"without-prebinding",output.data)
        assert loop.context.analysis_state.tool_receipts[-1]["required_delivery_ids"]==[]
    else:
        execute(loop,"forecast",{"name":"orders","date_col":"day","target_col":"amount","periods":2 if fault=="parameter" else 3})
    if fault=="internal_contract":
        def broken(**kwargs): raise ContractError("result_contract_mismatch","测试原生合同故障")
        monkeypatch.setattr("data_agent.agent.publication.runtime.resolve_native_claims",broken)
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    if fault=="post_dispatch":
        assert req["gap"]["status"]=="not_computed" and not req["claim_ids"]
    else:
        assert req["gap"]["status"]=="failed",req
        assert ("product_scope_mismatch" if fault=="parameter" else "result_contract_mismatch") in req["gap"]["reason"]
        assert "没有实际预测序列" not in req["gap"]["reason"]


# Independent arithmetic oracles; do not call pandas.corr/scipy correlation.
def _correlation_oracle(xs,ys,method):
    import math
    pairs=[(float(x),float(y)) for x,y in zip(xs,ys) if pd.notna(x) and pd.notna(y)]
    if len(pairs)<2:return None
    xs,ys=map(list,zip(*pairs))
    def ranks(values):
        return [(1+sum(v<x for v in values)+sum(v<=x for v in values))/2 for x in values]
    if method=="kendall":
        concordance=ties_x=ties_y=0
        total=len(xs)*(len(xs)-1)//2
        for i in range(len(xs)):
            for j in range(i):
                dx,dy=xs[i]-xs[j],ys[i]-ys[j]
                ties_x+=dx==0;ties_y+=dy==0
                concordance+=(dx*dy>0)-(dx*dy<0)
        denominator=math.sqrt((total-ties_x)*(total-ties_y))
        return round(concordance/denominator,4) if denominator else None
    if method=="spearman":xs,ys=ranks(xs),ranks(ys)
    ax,ay=sum(xs)/len(xs),sum(ys)/len(ys)
    covariance=sum((x-ax)*(y-ay) for x,y in zip(xs,ys))
    denominator=math.sqrt(sum((x-ax)**2 for x in xs)*sum((y-ay)**2 for y in ys))
    return round(covariance/denominator,4) if denominator else None


def _correlation_frame():
    return pd.DataFrame({"x":[1,2,3,4,5,6],"y":[1,4,2,5,3,6],
        "weak":[1,-1,-1,-1,-1,1],"constant":[7]*6,
        "sparse":[1,None,3,None,5,None],"category":["a","b"]*3})


@pytest.mark.parametrize("method",["pearson","spearman","kendall"])
@pytest.mark.parametrize("columns",["","x,y,weak,constant,sparse,category,missing"])
def test_correlation_all_public_methods_preserve_full_matrix_and_undefined_cells(engine,method,columns):
    from data_agent.tools.registry import registry
    loop,_=engine;frame=_correlation_frame();loop.context.workspace.add("orders",frame)
    output=registry.execute("correlation_analysis",{"name":"orders","columns":columns,"method":method})
    result=json.loads(output.summary)
    names=["x","y","weak","constant","sparse"]
    assert result["columns_analyzed"]==names
    matrix=result["correlation_matrix"]
    assert set(matrix)==set(names)
    for a in names:
        assert set(matrix[a])==set(names)
        for b in names:
            assert matrix[a][b]==_correlation_oracle(frame[a],frame[b],method),(a,b,method)
            assert result["pairwise_counts"][a][b]==sum(pd.notna(x) and pd.notna(y) for x,y in zip(frame[a],frame[b]))
    assert matrix["x"]["weak"]==0 and matrix["constant"]["x"] is None
    assert result["method"]==method
    assert result["excluded_columns"]==(["category","missing"] if columns else ["category"])
    assert "NaN" not in output.summary and "Infinity" not in output.summary
    assert all(abs(r["correlation"])>0.3 for r in result["high_correlations"])
    assert any("因果" in text for text in result["limitations"])


@pytest.mark.parametrize("method",["pearson","spearman","kendall"])
def test_correlation_formal_plan_receipt_matrix_answer_and_reload_keep_metrics_and_method(engine,method):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    from tests.test_trusted_publication_runtime import draft
    from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS
    from data_agent.tools.registry import registry
    loop,_=engine;frame=_correlation_frame();loop.context.workspace.add("orders",frame)
    scope={"datasets":["orders"],"metrics":["x","weak","constant"],"parameters":{"correlation_method":method}}
    plan=_s1_register(loop,"交付x、weak和constant完整相关矩阵",[{"kind":"table","scope":scope}])
    rid,result=execute(loop,"correlation_analysis",{"name":"orders","columns":"x,weak,constant","method":method})
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    assert receipt["plan_sha256"]==plan["plan_sha256"] and receipt["step_id"]=="s1_0"
    snap=snapshot_for_turn(loop);host=snap.as_dict();req=host["requirements"][0]
    assert req["gap"] is None,req
    claims=[c for c in host["claims"] if c["id"] in req["claim_ids"]]
    matrix=next(c for c in claims if c["basis_refs"][0]["result_path"]==["correlation_matrix"])
    assert matrix["value"]["x"]["weak"]==0 and matrix["value"]["x"]["constant"] is None
    assert matrix["unit"]=="无量纲"
    assert set(matrix["target"]["business_product"]["metrics"])=={"x","weak","constant"}
    body,error=publish(loop,draft(snap));assert error is None
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"
    assert commit(loop,{"role":"assistant"},body) is None
    saved=load_session(loop.session_id)["messages"][-1]
    stored=read_answer(loop.session_id,saved["answer_ref"])
    assert stored["body"]==body==saved["content"] and all(has_matrix_cell(body, row, column, "未知" if value is None else str(value)) for row, entries in result["correlation_matrix"].items() for column, value in entries.items())
    assert registry.capability_for("correlation_analysis")["output_contract"]==MINIMAL_PRODUCT_CONTRACTS["correlation_analysis"]


@pytest.mark.parametrize("fault",["method","metric","receipt_method","matrix_shape","coefficient_range"])
def test_correlation_wrong_method_metric_or_original_contract_cannot_complete_goal(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;loop.context.workspace.add("orders",_correlation_frame())
    scope={"datasets":["orders"],"metrics":["x","y"],"parameters":{"correlation_method":"spearman"}}
    _s1_register(loop,"交付原方法与原指标矩阵",[{"kind":"table","scope":scope}])
    args={"name":"orders","columns":"x,weak" if fault=="metric" else "x,y","method":"pearson" if fault=="method" else "spearman"}
    rid,result=execute(loop,"correlation_analysis",args)
    if fault=="receipt_method":result["method"]="pearson"
    if fault=="matrix_shape":result["correlation_matrix"]["x"].pop("y")
    if fault=="coefficient_range":result["correlation_matrix"]["x"]["y"]=2
    if fault not in {"method","metric"}:_tamper(loop,cfg,rid,result)
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert req["gap"]["status"]==("not_computed" if fault=="metric" else "failed") and not req["claim_ids"],req
    if fault!="metric":assert ("product_scope_mismatch" if fault=="method" else "result_contract_mismatch") in req["gap"]["reason"]


def test_correlation_unknown_method_never_silently_becomes_pearson(engine):
    from data_agent.tools.eda import correlation_analysis
    loop,_=engine
    result=json.loads(correlation_analysis("orders",method="unknown"))
    assert result["error_type"]=="unsupported_correlation_method" and "correlation_matrix" not in result


@pytest.mark.parametrize("method",["pearson","spearman","kendall"])
@pytest.mark.parametrize("values",[[1.0],[1.0,float("inf"),float("-inf"),float("nan")],[7.0,7.0]])
def test_correlation_undefined_single_column_is_unknown_not_one(engine,method,values):
    from data_agent.tools.registry import registry
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"x":values}))
    result=json.loads(registry.execute("correlation_analysis",{"name":"orders","columns":"x,x","method":method}).summary)
    assert result["columns_analyzed"]==["x"]
    assert result["correlation_matrix"]=={"x":{"x":None}}
    assert result["pairwise_counts"]["x"]["x"]==sum(pd.notna(x) and abs(x)!=float("inf") for x in values)
    assert result["high_correlations"]==[]



def _did_frame(*,missing=None,singleton=False):
    cells={(0,0):10,(0,1):11,(1,0):20,(1,1):25}
    return pd.DataFrame([{"treat":t,"period":p,"outcome":v+d} for (t,p),v in cells.items() if (t,p)!=missing for d in ([0] if singleton else [-1,1])])


@pytest.mark.parametrize("missing",[(0,0),(0,1),(1,0),(1,1)])
def test_did_missing_cell_has_unknown_effect_and_no_inference_or_zero_imputation(engine,missing):
    from data_agent.tools.registry import registry
    loop,_=engine;loop.context.workspace.add("orders",_did_frame(missing=missing))
    result=json.loads(registry.execute("causal_analysis",{"name":"orders","treatment_col":"treat","outcome_col":"outcome","time_col":"period"}).summary)
    assert result["status"]=="limited" and result["reason_code"]=="missing_did_cell"
    assert result["did_effect"] is None and result["ci_95"] is None and result["p_value"] is None
    assert result["cell_counts"][f"treatment={missing[0]}_period={missing[1]}"]==0
    assert result["group_means"][f"treatment={missing[0]}_period={missing[1]}"] is None
    assert result["assumptions"]["parallel_trends"]=="unverified"


@pytest.mark.parametrize("singleton",[False,True])
def test_did_four_cell_point_estimate_and_independent_variance_oracle(engine,singleton):
    import math
    from data_agent.tools.registry import registry
    loop,_=engine;loop.context.workspace.add("orders",_did_frame(singleton=singleton))
    result=json.loads(registry.execute("causal_analysis",{"name":"orders","treatment_col":"treat","target_col":"outcome","time_col":"period"}).summary)
    assert result["did_effect"]==4 and result["treatment_diff"]==5 and result["control_diff"]==1
    assert result["assumptions"]=={"parallel_trends":"unverified","independent_groups":"unverified"}
    assert "warning" not in result  # Baseline levels do not identify a pre-trend.
    assert any("独立" in v for v in result["limitations"])
    if singleton:
        assert result["status"]=="limited" and result["reason_code"]=="insufficient_did_cell_variance"
        assert result["standard_error"] is None and result["ci_95"] is None and result["p_value"] is None and result["significant_at_005"] is None
    else:
        # Each [-1,+1] pair has sample variance 2; sum of 4 variance/n terms=4.
        assert result["standard_error"]==2 and result["ci_95"]==[.08,7.92]
        assert result["p_value"]==round(math.erfc(2/math.sqrt(2)),6)


@pytest.mark.parametrize("fault",["nonbinary_treatment","nonbinary_time","infinite_outcome","conflicting_alias"])
def test_did_rejects_inputs_that_do_not_represent_declared_binary_cells(engine,fault):
    from data_agent.tools.registry import registry
    loop,_=engine;frame=_did_frame();args={"name":"orders","treatment_col":"treat","outcome_col":"outcome","time_col":"period"}
    if fault=="nonbinary_treatment":frame.loc[0,"treat"]=2
    if fault=="nonbinary_time":
        frame["period"]=frame["period"].astype(float);frame.loc[0,"period"]=.5
    if fault=="infinite_outcome":
        frame["outcome"]=frame["outcome"].astype(float);frame.loc[0,"outcome"]=float("inf")
    if fault=="conflicting_alias":args["target_col"]="treat"
    loop.context.workspace.add("orders",frame)
    result=json.loads(registry.execute("causal_analysis",args).summary)
    assert "error" in result and "did_effect" not in result


@pytest.mark.parametrize("case",["complete","singletons","missing_cell"])
def test_did_prebound_effect_and_interval_keep_separate_answer_gaps(engine,case):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    from tests.test_trusted_publication_runtime import draft
    loop,_=engine;loop.context.workspace.add("orders",_did_frame(missing=(1,1) if case=="missing_cell" else None,singleton=case=="singletons"))
    scope={"datasets":["orders"],"metrics":["outcome"],"parameters":{"causal_method":"did"}}
    specs=[{"kind":"measurement","scope":dict(scope,quantity="value",parameters={**scope["parameters"],"causal_output":"effect"})},
           {"kind":"table","scope":dict(scope,parameters={**scope["parameters"],"causal_output":"confidence_interval"})}]
    plan=_s1_register(loop,"报告原DID点估计及95%区间，不把未知当零",specs)
    rid,result=execute(loop,"causal_analysis",{"name":"orders","treatment_col":"treat","outcome_col":"outcome","time_col":"period","method":"did"})
    snap=snapshot_for_turn(loop);req=snap.as_dict()["requirements"][0]
    claims={c["basis_refs"][0]["result_path"][0]:c for c in snap.as_dict()["claims"] if c["id"] in req["claim_ids"]}
    assert claims["did_effect"]["value"]==(None if case=="missing_cell" else 4)
    assert claims["ci_95"]["value"]==([.08,7.92] if case=="complete" else None)
    if case=="complete":assert req["gap"] is None
    else:assert req["gap"]["status"]=="evidence_insufficient"
    body,error=publish(loop,draft(snap));assert error is None
    status=loop._accepted_answer["requirement_outcomes"][0]["status"]
    assert status==({"complete":"answered","singletons":"partial","missing_cell":"evidence_insufficient"}[case])
    if case!="complete":assert "未知" in body and "显著" not in body
    assert commit(loop,{"role":"assistant"},body) is None
    accepted=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert accepted["body"]==body and accepted["requirement_outcomes"][0]["status"]==status


@pytest.mark.parametrize("fault",["effect","p_value","variance","assumptions","metric","missing_effect","singleton_interval"])
def test_did_tampered_original_contract_never_authorizes_an_effect_or_inference(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;loop.context.workspace.add("orders",_did_frame(missing=(1,1) if fault=="missing_effect" else None,singleton=fault=="singleton_interval"))
    scope={"datasets":["orders"],"metrics":["outcome"],"quantity":"value","parameters":{"causal_method":"did","causal_output":"effect"}}
    _s1_register(loop,"交付原DID点估计",[{"kind":"measurement","scope":scope}])
    rid,result=execute(loop,"causal_analysis",{"name":"orders","treatment_col":"treat","outcome_col":"outcome","time_col":"period"})
    if fault=="effect":result["did_effect"]=999
    if fault=="p_value":result["p_value"]=0
    if fault=="variance":result["cell_variances"]["treatment=0_period=0"]=-1
    if fault=="assumptions":result["assumptions"]["parallel_trends"]="verified"
    if fault=="metric":result["outcome_col"]="other"
    if fault=="missing_effect":result["did_effect"]=-21
    if fault=="singleton_interval":result["ci_95"]=[4,4]
    _tamper(loop,cfg,rid,result)
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert not req["claim_ids"] and req["gap"]["status"]=="failed",req
    assert "result_contract_mismatch" in req["gap"]["reason"]


@pytest.mark.parametrize("tool",["correlation_analysis","causal_analysis","compare_periods"])
def test_method_capability_evidence_fields_exist_in_actual_result_and_contract(engine,tool):
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS
    loop,_=engine
    if tool=="correlation_analysis":
        loop.context.workspace.add("orders",_correlation_frame());args={"name":"orders"}
    elif tool=="compare_periods":
        loop.context.workspace.add("orders",_periods_frame());args=_periods_args()
    else:
        loop.context.workspace.add("orders",_did_frame());args={"name":"orders","treatment_col":"treat","outcome_col":"outcome","time_col":"period"}
    result=json.loads(registry.execute(tool,args).summary);cap=registry.capability_for(tool)
    assert set(cap['evidence_fields'])<=set(result)
    assert cap['output_contract']==MINIMAL_PRODUCT_CONTRACTS[tool]



def _ab_frame(case="independent"):
    if case in {"paired","one_pair","unpaired_units"}:
        units=[1,2,3,1,2,3] if case=="paired" else [1,2,3,1,4,5] if case=="one_pair" else [1,1,2,3,3,4]
        return pd.DataFrame({"group":["A"]*3+["B"]*3,"amount":[10,20,30,11,23,35],"unit":units})
    values=[1,2,3,4,5,6] if case=="independent" else [1]*3+[2]*3
    return pd.DataFrame({"group":["A"]*3+["B"]*3,"amount":values})


@pytest.mark.parametrize("fault",["three_groups","unknown_method","nonfinite","bad_metric","paired_u","paired_chi2"])
def test_ab_never_ignores_groups_changes_explicit_method_or_accepts_invalid_measurements(engine,fault):
    from data_agent.tools.statistics import ab_test
    from data_agent.tools.registry import registry
    loop,_=engine;frame=_ab_frame("paired" if fault.startswith("paired_") else "independent")
    args={"name":"orders","group_col":"group","metric_col":"amount","method":"ttest"}
    if fault=="three_groups":frame=pd.concat([frame,pd.DataFrame({"group":["C","C"],"amount":[100,200]})],ignore_index=True)
    if fault=="unknown_method":args["method"]="typo"
    if fault in {"nonfinite","bad_metric"}:
        frame["amount"]=frame["amount"].astype(object);frame.loc[0,"amount"]=float("inf") if fault=="nonfinite" else "bad"
    if fault.startswith("paired_"):args.update(unit_col="unit",method="mannwhitneyu" if fault=="paired_u" else "chi2")
    loop.context.workspace.add("orders",frame)
    raw=ab_test(**args) if fault=="unknown_method" else registry.execute("ab_test",args).summary
    result=json.loads(raw)
    assert "error" in result and "test" not in result and "difference" not in result


@pytest.mark.parametrize("aggregation",["sum","mean"])
def test_ab_unit_aggregation_precedes_independent_or_paired_design(engine,aggregation):
    from data_agent.tools.statistics import ab_test
    loop,_=engine;loop.context.workspace.add("orders",_ab_frame("unpaired_units"))
    result=json.loads(ab_test("orders","group","amount",method="ttest",unit_col="unit",unit_aggregation=aggregation))
    assert result["design"]=="independent" and result["analysis_unit"]=="unit"
    assert result["groups"]["A"]["n"]==result["groups"]["B"]["n"]==2
    expected=4.5 if aggregation=="sum" else 3.5
    assert result["difference"]["absolute"]==expected
    assert result["source_rows"]==6 and result["complete_case_rows"]==6


@pytest.mark.parametrize("case",["paired","one_pair","degenerate"])
def test_ab_paired_or_degenerate_sample_does_not_fabricate_inference(engine,case):
    from data_agent.tools.statistics import ab_test
    loop,_=engine;loop.context.workspace.add("orders",_ab_frame(case))
    result=json.loads(ab_test("orders","group","amount",method="ttest",unit_col="unit" if case!="degenerate" else ""))
    assert result["difference"]["absolute"]==({"paired":3,"one_pair":1,"degenerate":1}[case])
    json.dumps(result,allow_nan=False)
    if case=="paired":
        # Differences 1,3,5: mean=3, sample variance=4, df=2.
        import math
        t=3/math.sqrt(4/3);p=1-t/math.sqrt(t*t+2)
        assert result["test"]["statistic"]==round(t,4) and result["test"]["p_value"]==round(p,6)
        assert result["difference"]["confidence_interval_95"]==[-1.9683,7.9683]
        assert result["paired_sample_size"]==3 and result["excluded_unpaired_units"]==0
        assert result["wilcoxon_signed_rank"]["p_value"]==.25  # 2/2^3 sign assignments.
    else:
        assert result["status"]=="limited" and result["test"]["p_value"] is None
        assert result["test"]["statistic"] is None and result["test"]["significant"] is None
        assert result["difference"].get("confidence_interval_95") is None
        if case=="one_pair":assert result["design"]=="paired" and result["paired_sample_size"]==1


@pytest.mark.parametrize("method",["auto","ttest","mannwhitneyu","chi2"])
def test_ab_each_public_method_has_independent_numeric_oracle_and_actual_method(engine,method):
    import math,itertools
    from data_agent.tools.statistics import ab_test
    loop,_=engine;frame=_ab_frame()
    if method=="chi2":frame=pd.DataFrame({"group":["A"]*10+["B"]*10,"amount":[0]*8+[1]*2+[0]*2+[1]*8})
    loop.context.workspace.add("orders",frame)
    result=json.loads(ab_test("orders","group","amount",method=method))
    assert result["requested_method"]==method and result["design"]=="independent"
    assert result["metric_col"]=="amount" and result["test"]["p_value"] is not None
    if method in {"auto","ttest"}:
        assert result["method"]=="ttest" and result["difference"]["absolute"]==3
        assert result["test"]["statistic"]==round(3/math.sqrt(2/3),4)
        # Student t df=4 survival by numerical quadrature, no scipy test oracle.
        t=3/math.sqrt(2/3);steps=20000;h=t/steps
        density=lambda x: math.gamma(2.5)/(math.sqrt(4*math.pi)*math.gamma(2))*(1+x*x/4)**-2.5
        mass=h/3*(density(0)+density(t)+sum((4 if i%2 else 2)*density(i*h) for i in range(1,steps)))
        assert result["test"]["p_value"]==round(1-2*mass,6)
        assert result["test"]["difference_direction"]=="second_minus_first"
    elif method=="mannwhitneyu":
        # Complete separation: only the two extreme allocations among C(6,3).
        assert result["test"]["statistic"]==0 and result["test"]["p_value"]==round(2/math.comb(6,3),6)
    else:
        # Existing Yates correction: four cells (abs(O-E)-.5)^2/E => 5.
        assert result["test"]["statistic"]==5 and result["test"]["dof"]==1
        assert result["test"]["p_value"]==round(math.erfc(math.sqrt(5/2)),6)
        assert result["contingency_table"]=={"A":{"0":8,"1":2},"B":{"0":2,"1":8}}
    assert result["assumptions"]["random_assignment"]=="unverified"
    assert any("因果" in item for item in result["limitations"])


@pytest.mark.parametrize("case",["independent","paired","one_pair","degenerate"])
def test_ab_prebound_effect_and_inference_have_separate_business_deliveries(engine,case):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    from tests.test_trusted_publication_runtime import draft
    loop,_=engine;loop.context.workspace.add("orders",_ab_frame(case))
    params={"ab_method":"ttest"};scope={"datasets":["orders"],"metrics":["amount"]}
    specs=[{"kind":"measurement","scope":dict(scope,quantity="difference",parameters=dict(params,ab_output="difference"))},
           {"kind":"measurement","scope":dict(scope,quantity="value",parameters=dict(params,ab_output="p_value"))}]
    _s1_register(loop,"交付A/B差值和p值，保留配对与未知推断边界",specs)
    args={"name":"orders","group_col":"group","metric_col":"amount","method":"ttest"}
    if case in {"paired","one_pair"}:args["unit_col"]="unit"
    rid,result=execute(loop,"ab_test",args);snap=snapshot_for_turn(loop);req=snap.as_dict()["requirements"][0]
    claims=[c for c in snap.as_dict()["claims"] if c["id"] in req["claim_ids"]]
    assert {c["target"]["business_product"]["parameters"]["ab_output"] for c in claims}=={"difference","p_value"}
    assert all(c["target"]["business_product"]["metrics"]==["amount"] for c in claims)
    body,error=publish(loop,draft(snap));assert error is None
    status="partial" if case in {"one_pair","degenerate"} else "answered"
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]==status
    if status=="partial":assert "未知" in body
    assert commit(loop,{"role":"assistant"},body) is None
    saved=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert saved["body"]==body and saved["requirement_outcomes"][0]["status"]==status


@pytest.mark.parametrize("fault",["metric","method","difference","p_value","degenerate_p","wrong_goal_method","wrong_goal_metric"])
def test_ab_wrong_business_binding_or_original_contract_cannot_close_delivery(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;loop.context.workspace.add("orders",_ab_frame("degenerate" if fault=="degenerate_p" else "independent"))
    scope={"datasets":["orders"],"metrics":["cost" if fault=="wrong_goal_metric" else "amount"],"quantity":"difference","parameters":{"ab_method":"mannwhitneyu" if fault=="wrong_goal_method" else "ttest","ab_output":"difference"}}
    _s1_register(loop,"交付指定指标和方法的A/B差值",[{"kind":"measurement","scope":scope}])
    rid,result=execute(loop,"ab_test",{"name":"orders","group_col":"group","metric_col":"amount","method":"ttest"})
    if fault=="metric":result["metric_col"]="cost"
    if fault=="method":result["requested_method"]="mannwhitneyu"
    if fault=="difference":result["difference"]["absolute"]=999
    if fault=="p_value":result["test"]["p_value"]=1.5
    if fault=="degenerate_p":result["test"]["p_value"]=0
    if not fault.startswith("wrong_goal"):_tamper(loop,cfg,rid,result)
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert not req["claim_ids"] and req["gap"]["status"]==("not_computed" if fault=="wrong_goal_metric" else "failed"),req


@pytest.mark.parametrize("values",[[1,2,4,5],[1,1,2,2],[1,1,1,1]])
def test_ab_auto_unassessed_normality_uses_existing_rank_test_without_inventing_assumptions(engine,values):
    from data_agent.tools.statistics import ab_test
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"group":["A","A","B","B"],"amount":values}))
    result=json.loads(ab_test("orders","group","amount"))
    assert result["method"]=="mannwhitneyu" and result["requested_method"]=="auto"
    assert all(row["status"]=="unassessed" and row["p_value"] is None for row in result["normality"].values())
    assert "不足" in result["selection_reason"] and result["test"]["p_value"] is not None
    json.dumps(result,allow_nan=False)



def _ml_frame(classification=False,labels=(2,3)):
    return pd.DataFrame({"x":[i%7 for i in range(40)],"z":[i%5 for i in range(40)],
                         "target":[labels[i%len(labels)] if classification else 2*(i%7)+(i%5)+.25*(i%3) for i in range(40)]})


@pytest.mark.parametrize("method",["auto","logistic","rf"])
@pytest.mark.parametrize("folds",[0,3])
def test_ml_classification_all_methods_preserve_original_label_mapping_and_confusion_oracle(engine,method,folds):
    from data_agent.tools.ml import classification
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(True))
    result=json.loads(classification("orders","target","x,z",method,folds))
    assert result["method"]=={"auto":"GradientBoostingClassifier","logistic":"LogisticRegression","rf":"RandomForestClassifier"}[method]
    assert result["requested_method"]==method and result["target_col"]=="target" and result["feature_cols"]==["x","z"]
    assert result["label_mapping"]==[{"encoded":0,"label":2},{"encoded":1,"label":3}] and result["positive_class"]==3
    truth=result["evaluation"]["y_true"];pred=result["evaluation"]["y_pred"]
    counts=[[sum(t==i and p==j for t,p in zip(truth,pred)) for j in range(2)] for i in range(2)]
    assert result["confusion_matrix"]==counts
    assert result["metrics"]["accuracy"]==round(sum(t==p for t,p in zip(truth,pred))/len(truth),4)
    fs=[]
    for i,row in enumerate(result["class_metrics"]):
        tp=counts[i][i];fp=sum(counts[j][i] for j in range(2) if j!=i);fn=sum(counts[i][j] for j in range(2) if j!=i)
        precision=tp/(tp+fp) if tp+fp else 0;recall=tp/(tp+fn) if tp+fn else 0;f=2*precision*recall/(precision+recall) if precision+recall else 0
        assert row["label"]==i+2 and row["support"]==sum(counts[i]) and row["precision"]==round(precision,4) and row["recall"]==round(recall,4) and row["f1"]==round(f,4)
        fs.append(f)
    assert result["metrics"]["f1_macro"]==round(sum(fs)/2,4)
    assert result["train_size"]==32 and result["test_size"]==8
    assert result["validation"]["scheme"]=="random_holdout" and result["validation"]["stratified"] is False
    if folds:assert result["cv"]["folds"]==folds and len(result["cv"]["scores"])==folds
    else:assert "cv" not in result


@pytest.mark.parametrize("method",["auto","linear","rf","gbrt"])
@pytest.mark.parametrize("folds",[0,3])
def test_ml_regression_all_methods_match_independent_holdout_metric_oracle(engine,method,folds):
    import math
    from data_agent.tools.ml import regression_analysis
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame())
    result=json.loads(regression_analysis("orders","target","x,z",method,folds))
    assert result["method"]=={"auto":"GradientBoostingRegressor","gbrt":"GradientBoostingRegressor","rf":"RandomForestRegressor","linear":"ElasticNet"}[method]
    truth=result["evaluation"]["y_true"];pred=result["evaluation"]["y_pred"];n=len(truth)
    mean=sum(truth)/n;sse=sum((a-b)**2 for a,b in zip(truth,pred));sst=sum((a-mean)**2 for a in truth)
    assert result["metrics"]=={"r2":round(1-sse/sst,4),"rmse":round(math.sqrt(sse/n),4),"mae":round(sum(abs(a-b) for a,b in zip(truth,pred))/n,4)}
    assert result["requested_method"]==method and result["target_col"]=="target"
    if folds:assert result["cv"]["folds"]==folds and len(result["cv"]["scores"])==folds
    else:assert "cv" not in result


@pytest.mark.parametrize("tool",["classification","regression_analysis"])
@pytest.mark.parametrize("fault",["unknown_method","target_leakage","bad_feature","missing_feature","fold_one","fold_negative","fold_too_large"])
def test_ml_invalid_declared_inputs_fail_before_recording_a_model(engine,tool,fault):
    from data_agent.tools import ml
    loop,_=engine;frame=_ml_frame(tool=="classification");args={"name":"orders","target_col":"target","features":"x,z","method":"auto","cv_folds":0}
    if fault=="unknown_method":args["method"]="typo"
    if fault=="target_leakage":args["features"]="x,target"
    if fault=="missing_feature":args["features"]="absent"
    if fault=="bad_feature":frame["x"]=frame["x"].astype(object);frame.loc[0,"x"]="bad"
    if fault.startswith("fold_"):args["cv_folds"]={"fold_one":1,"fold_negative":-1,"fold_too_large":100}[fault]
    loop.context.workspace.add("orders",frame)
    result=json.loads(getattr(ml,tool)(**args))
    assert "error" in result and "metrics" not in result


@pytest.mark.parametrize("shape",["array","list"])
def test_shap_preserves_every_class_and_uses_explicit_equal_weight_aggregation(engine,monkeypatch,shape):
    import numpy as np,shap
    from data_agent.tools.ml import classification
    from data_agent.tools.statistics import shap_analysis
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(True));classification("orders","target","x,z","rf")
    values=np.tile(np.array([[[1,-3],[-2,4]]],dtype=float),(40,1,1))
    class Explainer:
        def __init__(self,model):pass
        def shap_values(self,frame):return values if shape=="array" else [values[:,:,i] for i in range(2)]
    monkeypatch.setattr(shap,"TreeExplainer",Explainer)
    result=json.loads(shap_analysis("orders","target"))
    assert result["aggregation"]=="equal_weight_mean_across_classes"
    assert result["per_class_importance"]==[{"label":2,"importance":[{"feature":"z","mean_abs_shap":2.0},{"feature":"x","mean_abs_shap":1.0}]},{"label":3,"importance":[{"feature":"z","mean_abs_shap":4.0},{"feature":"x","mean_abs_shap":3.0}]}]
    assert result["shap_importance"]==[{"feature":"z","mean_abs_shap":3.0},{"feature":"x","mean_abs_shap":2.0}]
    assert result["model_identity"]["feature_cols"]==["x","z"] and result["n_observations"]==40


@pytest.mark.parametrize("kind",["regression","binary","multiclass"])
def test_actual_tree_shap_keeps_supported_model_kind_labels_and_current_data(engine,kind):
    from data_agent.tools.ml import classification,regression_analysis
    from data_agent.tools.statistics import shap_analysis
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(kind!="regression",labels=(2,3,4) if kind=="multiclass" else (2,3)))
    trainer=regression_analysis if kind=="regression" else classification
    trained=json.loads(trainer("orders","target","x,z","rf"));assert "error" not in trained,trained
    result=json.loads(shap_analysis("orders","target"));assert "error" not in result,result
    assert result["status"]=="supported" and {row["feature"] for row in result["shap_importance"]}=={"x","z"}
    assert all(row["mean_abs_shap"]>=0 for row in result["shap_importance"])
    if kind!="regression":assert [row["label"] for row in result["per_class_importance"]]==([2,3,4] if kind=="multiclass" else [2,3])
    else:assert result["aggregation"]=="mean_abs_across_observations" and result["per_class_importance"]==[]


def test_trained_models_are_owned_by_session_even_for_identical_dataset_names_and_bytes(engine):
    from data_agent.agent.context import AgentContext,use_agent_context
    from data_agent.session.workspace import Workspace
    from data_agent.tools.ml import regression_analysis
    from data_agent.tools.statistics import shap_analysis
    from data_agent.tools.simulation import what_if_simulation
    loop,_=engine;frame=_ml_frame();loop.context.workspace.add("orders",frame)
    trained=json.loads(regression_analysis("orders","target","x,z","rf"));assert "error" not in trained
    with use_agent_context(AgentContext(session_id="other_model_owner",workspace=Workspace())) as other:
        other.workspace.add("orders",frame)
        result=json.loads(shap_analysis("orders","target"))
        assert "error" in result and "shap_importance" not in result
        result=what_if_simulation("orders",mode="predict",target_col="target",feature_changes='{"x":10}')
        assert isinstance(result,str) and "Error" in result
    result=json.loads(shap_analysis("orders","target"));assert "error" not in result



def test_shap_auto_requires_unique_current_model_and_explicit_kind_chooses_exact_estimator(engine):
    from data_agent.tools.ml import classification,regression_analysis
    from data_agent.tools.statistics import shap_analysis
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(True))
    classification("orders","target","x,z","rf");regression_analysis("orders","target","x,z","rf")
    auto=json.loads(shap_analysis("orders","target"));assert auto["error_type"]=="ambiguous_current_model"
    for kind in ("classification","regression"):
        result=json.loads(shap_analysis("orders","target",kind));assert "error" not in result,result
        assert result["model_identity"]["kind"]==kind and result["model_type"]==("RandomForestClassifier" if kind=="classification" else "RandomForestRegressor")


@pytest.mark.parametrize("tool,method",[("classification","rf"),("regression_analysis","linear"),("shap_analysis","rf")])
def test_ml_formal_plan_actual_method_product_and_persisted_answer(engine,tool,method):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    from tests.test_trusted_publication_runtime import draft
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(tool!="regression_analysis"))
    params={"shap_output":"overall","model_kind":"classification"} if tool=="shap_analysis" else {"classification_method" if tool=="classification" else "regression_method":method,"model_output":"metrics","cv_folds":0}
    specs=[{"kind":"table" if tool=="shap_analysis" else "fit","scope":{"datasets":["orders"],"metrics":["target"],"parameters":params}}]
    if tool=="shap_analysis":
        prerequisite={"kind":"fit","scope":{"datasets":["orders"],"metrics":["target"],"parameters":{"classification_method":"rf","model_output":"metrics"}}}
        _s1_register(loop,"训练当前分类模型并解释各类贡献",[prerequisite,*specs])
        execute(loop,"classification",{"name":"orders","target_col":"target","features":"x,z","method":"rf"})
    else:_s1_register(loop,"交付指定模型实际留出评估",specs)
    args={"name":"orders","target_col":"target"}
    if tool!="shap_analysis":args.update(features="x,z",method=method)
    else:args["model_kind"]="classification"
    rid,result=execute(loop,tool,args);snapshot=snapshot_for_turn(loop)
    assert any(r["claim_ids"] and r["gap"] is None for r in snapshot.as_dict()["requirements"])
    body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    saved=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert saved["body"]==body


@pytest.mark.parametrize("fault",["method","metric","metrics","predictions","cv","positive_class"])
def test_ml_tampered_native_method_or_original_holdout_cannot_close_fit(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;loop.context.workspace.add("orders",_ml_frame(True))
    scope={"datasets":["orders"],"metrics":["target"],"parameters":{"classification_method":"rf","model_output":"metrics","cv_folds":3}}
    _s1_register(loop,"交付原分类模型评估",[{"kind":"fit","scope":scope}])
    rid,result=execute(loop,"classification",{"name":"orders","target_col":"target","features":"x,z","method":"rf","cv_folds":3})
    if fault=="method":result["method"]="LogisticRegression"
    if fault=="metric":result["target_col"]="cost"
    if fault=="metrics":result["metrics"]["accuracy"]=999
    if fault=="predictions":result["evaluation"]["y_pred"][0]=5
    if fault=="cv":result["cv"]["folds"]=2
    if fault=="positive_class":result["positive_class"]=2
    _tamper(loop,cfg,rid,result)
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert not req["claim_ids"] and req["gap"]["status"]=="failed",req

@pytest.mark.parametrize("fault",["identity","model_key","kind","labels","aggregation","overall","observations"])
def test_shap_tampered_model_version_or_class_average_cannot_close_explanation(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;loop.context.workspace.add("orders",_ml_frame(True))
    specs=[{"kind":"fit","scope":{"datasets":["orders"],"metrics":["target"],"parameters":{"classification_method":"rf","model_output":"metrics"}}},
           {"kind":"table","scope":{"datasets":["orders"],"metrics":["target"],"parameters":{"model_kind":"classification","shap_output":"overall"}}}]
    _s1_register(loop,"训练分类模型并交付全类别平均解释",specs)
    execute(loop,"classification",{"name":"orders","target_col":"target","features":"x,z","method":"rf"})
    rid,result=execute(loop,"shap_analysis",{"name":"orders","target_col":"target","model_kind":"classification"})
    if fault=="identity":result["data_identity"]["version_id"]="old"
    if fault=="model_key":result["model_identity"]["model_key"]="foreign"
    if fault=="kind":result["model_identity"]["kind"]="regression"
    if fault=="labels":result["per_class_importance"].pop()
    if fault=="aggregation":result["aggregation"]="first_class"
    if fault=="overall":result["shap_importance"][0]["mean_abs_shap"]+=5
    if fault=="observations":result["n_observations"]=-1
    _tamper(loop,cfg,rid,result)
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert req["gap"]["status"]==("evidence_insufficient" if fault=="identity" else "failed"),req
    assert all(c["basis_refs"][0]["tool_name"]!="shap_analysis" for c in snapshot_for_turn(loop).as_dict()["claims"] if c["id"] in req["claim_ids"])
    assert any(c["basis_refs"][0]["tool_name"]=="classification" for c in snapshot_for_turn(loop).as_dict()["claims"] if c["id"] in req["claim_ids"])


def test_ml_current_subset_features_are_reused_by_predict_and_stale_model_is_not_selected(engine):
    from data_agent.tools.ml import regression_analysis,classification
    from data_agent.tools.statistics import shap_analysis
    from data_agent.tools.simulation import what_if_simulation
    loop,_=engine;frame=_ml_frame();loop.context.workspace.add("orders",frame)
    regression_analysis("orders","target","x","linear")
    predicted=what_if_simulation("orders",mode="predict",target_col="target",feature_changes='{"x":0}')
    assert predicted.data["model_identity"]["feature_cols"]==["x"] and predicted.data["impact"]["absolute"]==0
    loop.context.workspace.add("orders",_ml_frame(True))
    stale=json.loads(shap_analysis("orders","target","regression"));assert stale["error_type"]=="stale_model_data_identity"
    classification("orders","target","x,z","rf")
    current=json.loads(shap_analysis("orders","target"));assert current["model_identity"]["kind"]=="classification"


@pytest.mark.parametrize("method",["auto","logistic","rf"])
def test_ml_multiclass_string_labels_keep_all_class_metrics_and_coefficients(engine,method):
    from data_agent.tools.ml import classification
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(True,labels=("beta","alpha","gamma")))
    result=json.loads(classification("orders","target","x,z",method,3))
    assert [r["label"] for r in result["label_mapping"]]==["alpha","beta","gamma"] and result["positive_class"] is None
    assert [r["label"] for r in result["class_metrics"]]==["alpha","beta","gamma"]
    if method=="logistic":assert [r["label"] for r in result["coefficients_by_class"]]==["alpha","beta","gamma"]

@pytest.mark.parametrize("fault",["bad_json","nonobject","missing_column","unknown_agg","nonpositive_window","negative_lag","unknown_type","collision"])
def test_feature_invalid_declared_input_is_atomic_and_cannot_report_a_fake_column(engine,fault):
    from data_agent.tools.derive_features import derive_features
    loop,_=engine;frame=pd.DataFrame({"x":[1.,2.,3.],"group":["A","B","A"]})
    kind="rolling_features";columns="x";params='{"window":2}'
    if fault=="bad_json":params="{"
    if fault=="nonobject":params="[]"
    if fault=="missing_column":columns="absent"
    if fault=="unknown_agg":params='{"agg":"typo"}'
    if fault=="nonpositive_window":params='{"window":0}'
    if fault=="negative_lag":kind="lag_features";params='{"lag_periods":[-1]}'
    if fault=="unknown_type":kind="typo"
    if fault=="collision":frame["x_rolling2_mean"]=[99.,99.,99.]
    loop.context.workspace.add("orders",frame);before=loop.context.workspace.get_data_identity("orders");names=set(loop.context.workspace.list_datasets())
    result=json.loads(derive_features("orders",kind,columns,params,"features"))
    assert "error" in result and "new_columns" not in result,result
    assert set(loop.context.workspace.list_datasets())==names and loop.context.workspace.get_data_identity("orders")==before
    pd.testing.assert_frame_equal(loop.context.workspace.get("orders"),frame)


@pytest.mark.parametrize("kind,columns,params,expected",[
    ("lag_features","x",'{"lag_periods":[1,2]}',{"x_lag1":[None,1.,2.],"x_lag2":[None,None,1.]}),
    ("rolling_features","x",'{"window":2,"agg":"mean"}',{"x_rolling2_mean":[1.,1.5,2.5]}),
    ("rolling_features","x",'{"window":2,"agg":"std"}',{"x_rolling2_std":[None,2**-.5,2**-.5]}),
    ("rolling_features","x",'{"window":2,"agg":"min"}',{"x_rolling2_min":[1.,1.,2.]}),
    ("rolling_features","x",'{"window":2,"agg":"max"}',{"x_rolling2_max":[1.,2.,3.]}),
    ("ratio_features","",'{"numerator":"x","denominator":"den"}',{"x_div_den":[.5,None,1.5]}),
    ("bin_features","x",'{"bins":[0,2,4],"labels":["low","high"]}',{"x_binned":["low","low","high"]}),
    ("onehot_encoding","group",'{"drop_first":true}',{"group_B":[False,True,False]}),
    ("onehot_encoding","group",'{"drop_first":false}',{"group_A":[True,False,True],"group_B":[False,True,False]}),
    ("onehot_encoding","group",'{"drop_first":"true"}',{"group_B":[False,True,False]}),
    ("time_features","day","",{"day_year":[2026,2026,2026],"day_month":[10,10,10],"day_day":[10,9,11],"day_dayofweek":[5,4,6],"day_quarter":[4,4,4],"day_is_weekend":[1,0,1]}),
])
def test_feature_all_existing_modes_produce_exact_columns_and_preserve_parent_source(engine,kind,columns,params,expected):
    from data_agent.tools.derive_features import derive_features
    loop,_=engine;frame=pd.DataFrame({"x":[1.,2.,3.],"den":[2.,0.,2.],"group":["A","B","A"],"day":["2026-10-10","2026-10-09","2026-10-11"]})
    loop.context.workspace.add("orders",frame);identity=loop.context.workspace.get_data_identity("orders")
    result=json.loads(derive_features("orders",kind,columns,params,"features"));assert "error" not in result,result
    output=loop.context.workspace.get("features")
    assert set(result["new_columns"])==set(expected) and all(col in output for col in result["new_columns"])
    for col,values in expected.items():
        actual=[None if pd.isna(v) else v for v in output[col].tolist()]
        for a,b in zip(actual,values):
            if isinstance(b,float):assert a==pytest.approx(b)
            else:assert a==b
    pd.testing.assert_frame_equal(output[frame.columns],frame)
    pd.testing.assert_frame_equal(loop.context.workspace.get("orders"),frame)
    assert loop.context.workspace.get_data_identity("orders")==identity
    child=loop.context.workspace.get_data_identity("features")
    assert child["parent_version_ids"]==[identity["version_id"]] and child["source_origins"]==identity["source_origins"]
    assert result["source_data_identity"]==identity and result["data_identity"]==child
    assert result["parameters"]==json.loads(params or '{}')
    if kind in {"lag_features","rolling_features"}:assert result["row_order"]=="existing_dataset_order" and "排序" in " ".join(result["limitations"])

@pytest.mark.parametrize("tool",["classification","regression_analysis"])
@pytest.mark.parametrize("folds,valid",[(0,True),(2,True),(3,True),(1,False),(-1,False),(True,False),(2.5,False)])
def test_ml_public_cv_schema_and_business_scope_share_the_actual_input_boundary(engine,tool,folds,valid):
    from jsonschema import Draft7Validator
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.deliveries import business_scope_schema
    args={"name":"orders","target_col":"target","cv_folds":folds}
    assert Draft7Validator(registry.get(tool).parameters).is_valid(args) is valid
    scope={"datasets":["orders"],"parameters":{"cv_folds":folds}}
    assert Draft7Validator(business_scope_schema()).is_valid(scope) is valid


@pytest.mark.parametrize("values,constraints",[([100.,100.],'{"A":{"max":5}}'),([100.,100.],'{"B":{"max":5}}')])
def test_optimize_does_not_deliver_redistributed_out_of_bounds_candidate(engine,values,constraints):
    from data_agent.tools.simulation import what_if_simulation
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"group":["A","B"],"amount":values}))
    raw=what_if_simulation("orders",mode="optimize",target_metric="amount",dimension="group",goal_pct=100,constraints=constraints)
    result=raw.data if hasattr(raw,"data") else json.loads(raw)
    assert result["status"]=="candidate_not_found"
    assert result["breakdown"]==[] and result.get("feasible") is not True
    assert "不可行" not in getattr(raw,"summary","")

@pytest.mark.parametrize("values,constraints,goal",[([0.,100.],"",10),([-1.,100.],"",10),([100.,100.],"[]",10),([100.,100.],'{"A":{"max":-101}}',10),([100.,100.],'{"missing":{"max":5}}',10),([100.,100.],'{"A":{"max":true}}',10),([100.,100.],"",float("inf"))])
def test_optimize_rejects_invalid_basis_or_constraint(engine,values,constraints,goal):
    from data_agent.tools.simulation import what_if_simulation
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"group":["A","B"],"amount":values}))
    raw=what_if_simulation("orders",mode="optimize",target_metric="amount",dimension="group",goal_pct=goal,constraints=constraints)
    result=raw.data if hasattr(raw,"data") else json.loads(raw)
    assert "error" in result and "breakdown" not in result

@pytest.mark.parametrize("goal",[10.,-20.])
def test_optimize_legal_candidate_retains_exact_arithmetic_and_actual_method(engine,goal):
    from data_agent.tools.simulation import what_if_simulation
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"group":["A","B"],"amount":[100.,200.]}))
    result=what_if_simulation("orders",mode="optimize",target_metric="amount",dimension="group",goal_pct=goal).data
    assert result["status"]=="candidate_verified" and result["method"]=="share_allocation_sequential_clipping"
    assert result["projected"]==pytest.approx(300*(1+goal/100))
    assert sum(r["required_change"] for r in result["breakdown"])==pytest.approx(3*goal)
    for row in result["breakdown"]:
        assert row["min_pct"]<=row["required_pct"]<=row["max_pct"]
        assert row["required_change"]==pytest.approx(row["current"]*row["required_pct"]/100)


def _operation_spec(tool,args,datasets=()):
    return {"kind":"operation","scope":{"datasets":list(datasets),"operation":{"action":tool,"arguments":args}}} if datasets else {"kind":"operation","scope":{"operation":{"action":tool,"arguments":args}}}

@pytest.mark.parametrize("tool,args",[
    ("derive_features",{"name":"orders","feature_type":"lag_features","columns":"amount","params":'{"lag_periods":[1]}',"save_as":"features"}),
    ("clean_data",{"name":"orders","deduplicate":True}),
    ("apply_type_conversion",{"name":"orders","column":"amount","target_type":"numeric"}),
    ("derive_field",{"name":"orders","field_name":"double","expression":"amount * 2"}),
    ("write_file",{"path":"note.txt","content":"中文效果"}),
])
def test_operation_effect_closes_original_target_without_data_fact_claim(engine,tool,args):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    datasets=["orders"] if "name" in args else []
    _s1_register(loop,"只执行指定操作，不做统计分析",[_operation_spec(tool,args,datasets)])
    rid,result=execute(loop,tool,args)
    host=snapshot_for_turn(loop).as_dict();req=host["requirements"][0]
    assert req["gap"] is None and len(req["effect_ids"])==1 and req["claim_ids"]==[]
    effect=next(e for e in host["effects"] if e["receipt_id"]==rid)
    assert effect["id"] in req["effect_ids"] and effect["action"]==tool and effect["session_id"]==loop.session_id
    raw=encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot_for_turn(loop).digest,"sections":[{"requirement_ids":[req["id"]],"parts":[{"kind":"effect","ref":effect["id"]}]}]})
    body,error=publish(loop,raw);assert error is None
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"
    assert any(t["kind"]=="effect" and t["disposition"]=="accepted" for t in loop._accepted_answer["render_trace"])
    assert "操作完成" in body and "单位未知" not in body

@pytest.mark.parametrize("fault",["parameters","parent","changed_object","missing_predispatch","foreign_session"])
def test_operation_effect_rejects_mismatched_parameters_parent_object_and_authority(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.native import resolve_operation_effect
    loop,_=engine;args={"name":"orders","feature_type":"lag_features","columns":"amount","save_as":"features"}
    declared=dict(args,feature_type="rolling_features") if fault=="parameters" else args
    _s1_register(loop,"只创建指定派生对象",[_operation_spec("derive_features",declared,["orders"])])
    if fault=="parameters":
        assert json.loads(loop._current_task_scope_guard("derive_features",args))["error_type"]=="operation_plan_required"
        assert not loop.context.workspace._publication_dataset_exists("features");return
    rid,result=execute(loop,"derive_features",args)
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    if fault=="parent":receipt["operation_binding"]["source_data_identities"]["orders"]["version_id"]="foreign_parent"
    if fault=="missing_predispatch":receipt.pop("operation_binding",None)
    if fault=="changed_object":
        loop.prepare_for_bound_upload()
        loop.context.workspace.add("features",pd.DataFrame({"amount":[1]}))
    with pytest.raises(ValueError):resolve_operation_effect(session_id="other" if fault=="foreign_session" else loop.session_id,receipt_id=rid)


def test_operation_plan_allows_no_dataset_only_for_exact_nondata_operation(engine):
    from data_agent.agent.analysis_plan_contracts import analysis_plan_schema
    from jsonschema import Draft7Validator
    loop,_=engine
    _s1_register(loop,"写入指定内容",[_operation_spec("write_file",{"path":"note.txt","content":"hello"})])
    step=loop.context.analysis_state.analysis_plan["method_plan"][0]
    assert step["dataset_inputs"]==[]
    bad=dict(loop.context.analysis_state.analysis_plan)
    bad["method_plan"]=[dict(step,required_deliveries=[dict(step["required_deliveries"][0],kind="table",scope={"datasets":["orders"]})])]
    assert not Draft7Validator(analysis_plan_schema()).is_valid(bad)


@pytest.mark.parametrize("action",["load_skill","unload_skill","enable_skill","disable_skill","delete_skill"])
def test_operation_skill_effect_uses_actual_configured_state_without_dataset(engine,tmp_path,monkeypatch,action):
    from data_agent.skills.loader import SkillLoader
    from data_agent.agent.publication.runtime import snapshot_for_turn
    import data_agent.tools.skill_tools as skill_tools
    loop,_=engine;directory=tmp_path/"isolated_skills";file=directory/"fixture"/"SKILL.md";file.parent.mkdir(parents=True)
    file.write_text("---\nname: fixture\nenabled: true\n---\nfixture instructions",encoding="utf-8")
    loader=SkillLoader(directory);loader.discover();monkeypatch.setattr(skill_tools,"_loader",lambda:loader)
    if action in {"unload_skill","disable_skill","delete_skill"}:loader.load("fixture")
    if action=="enable_skill":loader.set_enabled("fixture",False)
    args={"name":"fixture"};_s1_register(loop,"执行指定扩展管理操作",[_operation_spec(action,args)])
    rid,result=execute(loop,action,args);host=snapshot_for_turn(loop).as_dict();req=host["requirements"][0]
    assert not req["gap"] and not req["claim_ids"] and req["effect_ids"]
    effect=next(e for e in host["effects"] if e["receipt_id"]==rid)
    assert effect["object"]["identity"]==result["state"] and effect["permission_scope"]==("current_session_skills" if action in {"load_skill","unload_skill"} else "configured_global_skills")
    assert not effect["data_identities"]
    if action=="delete_skill":assert not file.exists() and not result["state"]["exists"]

@pytest.mark.parametrize("fault",[None,"changed_file","wrong_session_path","no_plan","forged_ref"])
def test_operation_file_effect_requires_actual_bytes_scope_and_dispatch(engine,fault):
    from data_agent.tools.file_ops import write_file
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.native import resolve_operation_effect
    loop,cfg=engine
    if fault=="no_plan":
        assert json.loads(loop._current_task_scope_guard("write_file",{"path":"x.txt","content":"hello"}))["error_type"]=="operation_plan_required";return
    path="output/x.txt" if fault!="wrong_session_path" else "sessions/other/output/x.txt"
    if fault!="wrong_session_path":write_file("x.txt","before\n")
    args={"path":path,"old_text":"before","new_text":"after"}
    _s1_register(loop,"编辑指定文件",[_operation_spec("edit_file",args)])
    if fault=="wrong_session_path":
        with pytest.raises(ValueError):execute(loop,"edit_file",args)
        return
    rid,result=execute(loop,"edit_file",args);file=cfg.sessions_resolved/loop.session_id/"output/x.txt"
    assert file.read_text(encoding="utf-8")=="after\n"
    if fault=="changed_file":
        file.write_text("tampered",encoding="utf-8")
        with pytest.raises(ValueError):resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
        assert snapshot_for_turn(loop).as_dict()["requirements"][0]["gap"]
        return
    snap=snapshot_for_turn(loop);req=snap.as_dict()["requirements"][0]
    ref="forged_effect" if fault=="forged_ref" else req["effect_ids"][0]
    body,error=publish(loop,encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":[req["id"]],"parts":[{"kind":"effect","ref":ref}]}]}))
    assert error is None and loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"
    if fault=="forged_ref":assert any(i["code"]=="unknown_effect_ref" for i in loop._accepted_answer["issues"])


def test_operation_file_changed_after_publication_cannot_commit_success(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine;args={"path":"x.txt","content":"before"}
    _s1_register(loop,"写入指定内容",[_operation_spec("write_file",args)])
    execute(loop,"write_file",args);snap=snapshot_for_turn(loop)
    body,error=publish(loop,encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[]}));assert error is None
    (cfg.sessions_resolved/loop.session_id/"output/x.txt").write_text("changed",encoding="utf-8")
    assert commit(loop,{"role":"assistant"},body) and not loop.context.analysis_state.accepted_answers


@pytest.mark.parametrize("fault",["out_of_bounds","target_not_met","wrong_goal","wrong_constraint"])
def test_optimize_receipt_adapter_rechecks_candidate_instead_of_trusting_feasible(engine,monkeypatch,fault):
    from data_agent.tools.registry import registry,ToolResult
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"group":["A","B"],"amount":[100.,100.]}))
    tool=registry.get("what_if_simulation");original=tool.func
    def corrupted(**kw):
        raw=original(**kw);result=raw.data
        if fault=="out_of_bounds":result["breakdown"][0]["required_pct"]=101
        elif fault=="target_not_met":result["projected"]+=1
        elif fault=="wrong_goal":result["goal_pct"]=11
        else:result["constraints"]={"A":{"max":5}}
        return ToolResult(summary="candidate",data=result)
    monkeypatch.setattr(tool,"func",corrupted)
    rid,result=execute(loop,"what_if_simulation",{"name":"orders","mode":"optimize","target_metric":"amount","dimension":"group","goal_pct":10})
    with pytest.raises(ValueError,match="分配|候选"):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


def test_operation_invalid_or_nonexistent_skill_cannot_produce_success_receipt(engine,tmp_path,monkeypatch):
    from data_agent.skills.loader import SkillLoader
    from data_agent.tools.registry import registry
    import data_agent.tools.skill_tools as skill_tools
    loop,_=engine;loader=SkillLoader(tmp_path/"empty_skills");monkeypatch.setattr(skill_tools,"_loader",lambda:loader)
    for action in ("load_skill","unload_skill","enable_skill","disable_skill","delete_skill"):
        result=registry.execute(action,{"name":"missing"})
        assert result.data.get("error") and not result.data.get("state")


def test_operation_effect_producers_are_serialized_write_capabilities():
    from data_agent.tools.registry import registry,get_read_only_tools
    from data_agent.agent.publication.native import OPERATION_TOOLS
    assert not OPERATION_TOOLS & get_read_only_tools(registry)


def test_auto_type_conversion_effect_default_schema_roundtrip(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;args={"name":"orders","auto":True}
    _s1_register(loop,"自动类型转换",[_operation_spec("apply_type_conversion",args,["orders"])])
    execute(loop,"apply_type_conversion",args)
    assert snapshot_for_turn(loop).as_dict()["requirements"][0]["effect_ids"]


@pytest.mark.parametrize("changed",[False,True])
def test_operation_prior_answer_keeps_effect_identity_and_invalidates_changed_file(engine,changed):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from tests.test_trusted_publication_runtime import request
    loop,cfg=engine;args={"path":"note.txt","content":"original"}
    _s1_register(loop,"创建指定文件",[_operation_spec("write_file",args)]);execute(loop,"write_file",args)
    first=snapshot_for_turn(loop);body,error=publish(loop,encode({"schema":"answer_bindings.v2","snapshot_digest":first.digest,"sections":[]}));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    answer_id=loop._accepted_answer["answer_id"];effect_id=first.as_dict()["effects"][0]["id"]
    if changed:(cfg.sessions_resolved/loop.session_id/"output/note.txt").write_text("changed",encoding="utf-8")
    request(loop,"展示并解释刚才创建的文件",kind="presentation",source_answer_id=answer_id)
    host=snapshot_for_turn(loop).as_dict();req=next(r for r in host["requirements"] if r["id"]==loop.context.turn_requirement_ids[0])
    assert not req["claim_ids"]
    if changed:assert not req["effect_ids"] and req["gap"]["status"]=="evidence_insufficient"
    else:assert req["effect_ids"]==[effect_id] and any(e["id"]==effect_id for e in host["effects"])


def test_withdrawn_operation_effect_cannot_be_reassigned_by_draft(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.contracts import HostSnapshot
    from data_agent.agent.publication.service import PublicationService
    loop,_=engine;args={"path":"note.txt","content":"original"}
    _s1_register(loop,"创建指定文件",[_operation_spec("write_file",args)]);execute(loop,"write_file",args)
    host=snapshot_for_turn(loop).as_dict();req=host["requirements"][0];req["withdrawn"]=True
    host["requirements"].append(dict(req,id="other",text="创建另一文件",effect_ids=[],withdrawn=False,gap={"status":"not_computed","reason":"无对应效果"}))
    snap=HostSnapshot.freeze(**host)
    answer=PublicationService(snap).publish(encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":["other"],"parts":[{"kind":"effect","ref":req["effect_ids"][0]}]}]})).as_dict()
    assert any(i["code"]=="unbound_deliverable_ref" for i in answer["issues"])
    assert not any(t["kind"]=="effect" and t["disposition"]=="accepted" for t in answer["render_trace"])


def test_operation_plan_id_reuse_empty_dataset_input_keeps_existing_delivery(engine):
    from copy import deepcopy
    from data_agent.tools.registry import registry
    loop,_=engine
    _s1_register(loop,"只写指定文件",[_operation_spec("write_file",{"path":"note.txt","content":"original"})])
    plan=deepcopy(loop.context.analysis_state.analysis_plan)
    plan["requirement_revision"]=loop.context.analysis_state.requirement_revision
    plan["method_plan"][0]["required_deliveries"]=[{"id":d["id"]} for d in plan["method_plan"][0]["required_deliveries"]]
    response=registry.execute("record_analysis_plan",{"plan_json":plan})
    result=json.loads(response.summary)
    assert not result.get("error"),result
    assert loop.context.analysis_state.analysis_plan["method_plan"][0]["dataset_inputs"]==[]


def test_nonoperation_delivery_id_still_requires_actual_dataset_inputs(engine):
    from copy import deepcopy
    from data_agent.tools.registry import registry
    loop,_=engine
    _s1_register(loop,"计算当前记录数",[{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}}])
    plan=deepcopy(loop.context.analysis_state.analysis_plan)
    plan["requirement_revision"]=loop.context.analysis_state.requirement_revision
    step=plan["method_plan"][0];step["dataset_inputs"]=[]
    step["required_deliveries"]=[{"id":d["id"]} for d in step["required_deliveries"]]
    response=registry.execute("record_analysis_plan",{"plan_json":plan})
    result=json.loads(response.summary)
    assert result.get("error_type")=="invalid_independent_binding",result


@pytest.mark.parametrize("case",["forward","eleven","numeric","reverse","zero_reverse","zero_target","unknown_dimension","ambiguous_dimension","missing_dimension","missing_metric","infinite","bad_target"])
def test_sensitivity_arithmetic_original_records_complete_groups_and_unknown(engine,case):
    from data_agent.tools.simulation import _sensitivity
    frame=pd.DataFrame({"group":["A","B"],"amount":[100.,200.]})
    change,target,selected=10,"",""
    if case=="eleven":frame=pd.DataFrame({"group":[str(i) for i in range(11)],"amount":[100.]*11})
    if case=="numeric":frame["group"]=[1,2];selected="1"
    if case in {"reverse","zero_reverse","zero_target"}:target="600";change=0
    if case in {"zero_reverse","zero_target"}:frame["amount"]=[100.,-100.];target="100" if case=="zero_reverse" else "0"
    if case=="unknown_dimension":selected="absent"
    if case=="ambiguous_dimension":frame["group"]=[1,"1"];selected="1"
    if case=="missing_dimension":frame.loc[0,"group"]=None
    if case=="missing_metric":frame.loc[0,"amount"]=float("nan")
    if case=="infinite":change=float("inf")
    if case=="bad_target":target="nan"
    raw=_sensitivity(frame,"orders","amount","group",change,target,selected)
    if case in {"unknown_dimension","ambiguous_dimension","missing_dimension","missing_metric","infinite","bad_target"}:
        assert "error" in json.loads(str(raw)).keys();return
    data=raw.data
    assert data["claim_ceiling"]=="arithmetic_scenario" and data["dimension"]=="group"
    assert len(data["breakdown"])==len(frame)
    assert set(data["basis_by_dimension"])=={str(v) for v in frame["group"]}
    if target:
        baseline=float(frame["amount"].sum());gap=float(target)-baseline
        assert data["baseline_total"]==baseline and data["gap"]==gap and data["target"]==float(target)
        if case=="zero_reverse":
            assert data["required_total_pct"] is None and data["status"]=="limited"
            assert all(r["required_change"] is None and r["required_pct"] is None for r in data["breakdown"])
        else:assert sum(r["required_change"] for r in data["breakdown"])==pytest.approx(gap)
    else:
        expected=[v*(1+change/100) if not selected or str(k)==selected else v for k,v in zip(frame["group"],frame["amount"])]
        assert data["baseline"]["total"]==float(frame["amount"].sum())
        assert data["projected"]["total"]==pytest.approx(sum(expected))
        assert data["impact"]["absolute"]==pytest.approx(sum(expected)-frame["amount"].sum())
        assert sum(r["change"] for r in data["breakdown"])==pytest.approx(data["impact"]["absolute"])


@pytest.mark.parametrize("fault",["missing_group","wrong_parameter","wrong_total","false_known"])
def test_sensitivity_native_rejects_tampered_scenario_contract(engine,fault,monkeypatch):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"group":["A","B"],"amount":[100.,-100.]}))
    args={"name":"orders","mode":"sensitivity","metric":"amount","dimension":"group","target_value":"100"}
    rid,_=execute(loop,"what_if_simulation",args)
    original=native.load_receipt_result
    def changed(**kw):
        context,receipt,result,binding=original(**kw);result=deepcopy(result)
        if fault=="missing_group":result["breakdown"].pop()
        elif fault=="wrong_parameter":result["scenario_parameters"]["simulation_target"]=200
        elif fault=="wrong_total":result["baseline_total"]=100
        else:result["breakdown"][0]["required_change"]=0
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("case",["same_dimension_metric","integer_overflow"])
def test_sensitivity_preserves_original_dimension_identity_and_numeric_sum(engine,case):
    from data_agent.tools.simulation import _sensitivity
    if case=="same_dimension_metric":
        raw=_sensitivity(pd.DataFrame({"amount":[1,2]}),"orders","amount","amount",10,"","1")
        assert raw.data["projected"]["total"]==pytest.approx(3.1)
        assert list(raw.data["basis_by_dimension"])==["1","2"]
    else:
        raw=_sensitivity(pd.DataFrame({"group":["A","A"],"amount":[9_000_000_000_000_000_000]*2}),"orders","amount","group",10,"","")
        assert raw.data["baseline"]["total"]==1.8e19
        assert raw.data["projected"]["total"]==pytest.approx(1.98e19)


@pytest.mark.parametrize("changes",['[]','{}','{"x":true}','{"x":"10"}','{"x":NaN}','{"unknown":10}'])
def test_model_scenario_rejects_invalid_change_object_without_inventing_method(engine,changes):
    from data_agent.tools.simulation import what_if_simulation
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(False))
    execute(loop,"regression_analysis",{"name":"orders","target_col":"target","features":"x,z","method":"rf"})
    raw=what_if_simulation("orders",mode="predict",target_col="target",feature_changes=changes)
    assert "error" in str(raw).lower(),raw


def test_model_scenario_native_binds_actual_current_model_and_mean_predictions(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(False))
    specs=[{"kind":"scenario","scope":{"datasets":["orders"],"metrics":["target"],"parameters":{"simulation_mode":"predict","simulation_feature_changes":{"x":10},"simulation_output":output}}} for output in ("baseline","projected","impact")]
    _s1_register(loop,"当前模型的x加10%算术情景",specs)
    execute(loop,"regression_analysis",{"name":"orders","target_col":"target","features":"x,z","method":"rf"})
    rid,result=execute(loop,"what_if_simulation",{"name":"orders","mode":"predict","target_col":"target","feature_changes":"{\"x\":10}"})
    pred=result["scenario_predictions"];n=result["effective_rows"]
    assert n==len(pred["baseline"])==len(pred["projected"])
    assert result["baseline"]==round(sum(pred["baseline"])/n,4)
    assert result["projected"]==round(sum(pred["projected"])/n,4)
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert req["gap"] is None and len(req["claim_ids"])==3


@pytest.mark.parametrize("fault",["identity","parameters","mean","missing_prediction"])
def test_model_scenario_tampered_identity_parameters_or_predictions_rejected(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",_ml_frame(False))
    execute(loop,"regression_analysis",{"name":"orders","target_col":"target","features":"x,z","method":"rf"})
    rid,_=execute(loop,"what_if_simulation",{"name":"orders","mode":"predict","target_col":"target","feature_changes":"{\"x\":10}"})
    original=native.load_receipt_result
    def changed(**kw):
        context,receipt,result,binding=original(**kw);result=deepcopy(result)
        if fault=="identity":result["model_identity"]["model_key"]="another_session"
        elif fault=="parameters":result["feature_changes"]["x"]=20
        elif fault=="mean":result["projected"]+=1
        else:result["scenario_predictions"]["projected"].pop()
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("strategy",["keep","drop","fill_mean","fill_median","fill_mode","fill_constant"])
def test_cleaning_actual_filled_and_remaining_counts_match_created_object(engine,strategy):
    from data_agent.tools.data_clean import clean_data
    loop,_=engine;frame=pd.DataFrame({"amount":[1.,None],"text":["a",None]})
    loop.context.workspace.add("orders",frame)
    result=json.loads(clean_data("orders",missing_strategy=strategy,fill_value="0"))
    actual=loop.context.workspace.get(result["dataset"])
    report=result["missing_handling"]
    assert report["strategy"]==strategy and [r["column"] for r in report["columns"]]==list(frame.columns)
    assert report["remaining"]==int(actual.isna().sum().sum())
    expected=0 if strategy in {"keep","drop"} else 1 if strategy in {"fill_mean","fill_median"} else 2
    assert report["filled"]==expected
    assert sum(r["filled"] for r in report["columns"])==expected
    assert result["status"]==("partial" if strategy in {"fill_mean","fill_median"} else "complete")
    assert loop.context.workspace.get("orders").equals(frame)


@pytest.mark.parametrize("strategy",["fill_mean","fill_median","fill_mode"])
def test_cleaning_all_missing_column_remains_unknown_without_false_filled(engine,strategy):
    from data_agent.tools.data_clean import clean_data
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[float("nan")]*2}))
    result=json.loads(clean_data("orders",missing_strategy=strategy))
    assert result["missing_handling"]["filled"]==0 and result["missing_handling"]["remaining"]==2
    assert result["status"]=="partial" and result["missing_handling"]["columns"][0]["reason"]


def test_cleaning_partial_new_object_effect_is_retained_with_original_goal_gap(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,None],"text":["a",None]}))
    args={"name":"orders","missing_strategy":"fill_mean"}
    _s1_register(loop,"对所选全部列按均值清洗并保留新表",[_operation_spec("clean_data",args,["orders"])])
    rid,result=execute(loop,"clean_data",args)
    snap=snapshot_for_turn(loop);host=snap.as_dict();req=host["requirements"][0]
    assert req["effect_ids"] and not req["claim_ids"] and req["gap"]["status"]=="evidence_insufficient"
    effect=next(e for e in host["effects"] if e["receipt_id"]==rid)
    assert effect["object"]["name"]==result["dataset"] and effect["details"]["missing_handling"]["filled"]==1
    raw=encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":[req["id"]],"parts":[{"kind":"effect","ref":effect["id"]}]}]})
    body,error=publish(loop,raw);assert error is None
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="partial"
    assert "操作部分完成" in body and result["dataset"] in body and "text" in body


@pytest.mark.parametrize("fault",["filled","remaining","status","scope","before","child"])
def test_cleaning_actual_effect_rejects_mismatched_report_or_object(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,None],"text":["a",None]}))
    args={"name":"orders","missing_strategy":"fill_mean"}
    _s1_register(loop,"均值清洗并保留新表",[_operation_spec("clean_data",args,["orders"])])
    rid,result=execute(loop,"clean_data",args)
    if fault=="child":
        loop.prepare_for_bound_upload()
        child=loop.context.workspace.get(result["dataset"]);child["text"]=child["text"].fillna("changed")
        outcome=loop.context.workspace.add(result["dataset"],child)
        assert not str(outcome).startswith("Error:")
        assert loop.context.workspace.get(result["dataset"])["text"].notna().all()
    original=native.load_receipt_result
    def changed(**kw):
        context,receipt,result,binding=original(**kw);result=deepcopy(result)
        if fault=="filled":result["missing_handling"]["filled"]=2
        elif fault=="remaining":result["missing_handling"]["remaining"]=0
        elif fault=="status":result["status"]="complete"
        elif fault=="scope":result["missing_handling"]["columns"].pop()
        elif fault=="before":result["missing_handling"]["columns"][0]["missing_before"]+=1
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)


def test_cleaning_partial_prior_answer_reuse_keeps_missing_gap(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from tests.test_trusted_publication_runtime import request
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,None],"text":["a",None]}))
    args={"name":"orders","missing_strategy":"fill_mean"}
    _s1_register(loop,"均值清洗并保留新表",[_operation_spec("clean_data",args,["orders"])])
    execute(loop,"clean_data",args);snap=snapshot_for_turn(loop)
    body,error=publish(loop,encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[]}));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    prior=loop._accepted_answer["answer_id"];eid=snap.as_dict()["effects"][0]["id"]
    request(loop,"展示并解释刚才清洗的新表",kind="presentation",source_answer_id=prior)
    host=snapshot_for_turn(loop).as_dict();req=next(r for r in host["requirements"] if r["id"]==loop.context.turn_requirement_ids[0])
    assert req["effect_ids"]==[eid] and req["gap"]["status"]=="evidence_insufficient" and "text" in req["gap"]["reason"]


def test_cleaning_nullable_integer_fraction_does_not_round_or_change_strategy(engine):
    from data_agent.tools.data_clean import clean_data
    loop,_=engine;frame=pd.DataFrame({"amount":pd.Series([1,2,None],dtype="Int64")})
    loop.context.workspace.add("orders",frame)
    result=json.loads(clean_data("orders",missing_strategy="fill_mean"))
    assert result["status"]=="partial" and result["missing_handling"]["filled"]==0
    assert "原列类型" in result["missing_handling"]["columns"][0]["reason"]
    assert loop.context.workspace.get(result["dataset"]).equals(frame)


def test_cleaning_dedup_then_fill_counts_and_outlier_drop_are_distinct(engine):
    from data_agent.agent.publication.native import resolve_operation_effect
    loop,_=engine;frame=pd.DataFrame({"amount":[1.,1.,1.,2.,3.,4.,1000.,None,None],"text":["a"]*6+[None,"b","b"]})
    loop.context.workspace.add("orders",frame)
    args={"name":"orders","deduplicate":True,"missing_strategy":"fill_mean","outlier_strategy":"drop"}
    _s1_register(loop,"按所选顺序清洗并保留新表",[_operation_spec("clean_data",args,["orders"])])
    rid,result=execute(loop,"clean_data",args);effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
    loop.prepare_for_bound_upload()
    actual=loop.context.workspace.get(result["dataset"])
    assert result["missing_handling"]["filled"]==1
    assert result["missing_handling"]["remaining"]==int(actual.isna().sum().sum())
    assert result["rows_removed"]==len(frame)-len(actual)
    assert effect["object"]["name"]==result["dataset"]


@pytest.mark.parametrize("strategy",["mark","cap","drop"])
def test_cleaning_iqr_modes_preserve_original_algorithm_and_truthful_rows(engine,strategy):
    from data_agent.tools.data_clean import clean_data
    loop,_=engine;frame=pd.DataFrame({"amount":[1.,2.,3.,4.,100.]})
    loop.context.workspace.add("orders",frame)
    result=json.loads(clean_data("orders",outlier_strategy=strategy))
    actual=loop.context.workspace.get(result["dataset"])["amount"].tolist()
    assert actual==([1.,2.,3.,4.,7.] if strategy=="cap" else [1.,2.,3.,4.] if strategy=="drop" else frame["amount"].tolist())
    assert result["rows_removed"]==(1 if strategy=="drop" else 0) and result["status"]=="complete"
    assert result["missing_handling"]["filled"]==0


def test_cleaning_selected_scope_excludes_unrequested_missing_column(engine):
    from data_agent.tools.data_clean import clean_data
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,None],"text":["a",None]}))
    result=json.loads(clean_data("orders",columns="amount",missing_strategy="fill_mean"))
    assert result["status"]=="complete" and result["missing_handling"]["remaining"]==0
    assert result["missing_handling"]["filled"]==1 and loop.context.workspace.get(result["dataset"])["text"].isna().sum()==1


@pytest.mark.parametrize("kind,values,expected,failures,new_missing",[
    ("numeric",["1","bad",None],[1.,None,None],1,1),
    ("datetime",["2026-10-10","bad",None],["2026-10-10",None,None],1,1),
    ("bool",["yes","unknown",None],[True,"unknown",None],1,0),
    ("numeric_with_suffix",["1元","bad",None],[1.,"bad",None],1,0),
    ("category",["a","b",None],["a","b",None],0,0),
    ("percentage_to_float",["10%","20%",None],[.1,.2,None],0,0),
    ("date_int_to_datetime",[20261010,99999999,None],["2026-10-10",None,None],1,1),
])
def test_type_conversion_actual_values_and_audit_preserve_original_bad_value_policy(engine,kind,values,expected,failures,new_missing):
    from data_agent.tools.data_clean import apply_type_conversion
    loop,_=engine
    # nullable integer keeps the valid calendar code intact for this native format.
    frame=pd.DataFrame({"value":pd.Series(values,dtype="Int64") if kind=="date_int_to_datetime" else values})
    loop.context.workspace.add("orders",frame)
    result=json.loads(apply_type_conversion("orders",column="value",target_type=kind))
    actual=loop.context.workspace.get(result["dataset"])["value"]
    if "datetime" in kind:
        actual=[v.strftime("%Y-%m-%d") if pd.notna(v) else None for v in actual]
    else:actual=[None if pd.isna(v) else v for v in actual]
    assert actual==expected
    row=result["conversion_audit"][0]
    assert row["original_missing"]==1 and row["conversion_failures"]==failures and row["new_missing"]==new_missing
    assert row["converted_values"]==2-failures
    assert result["status"]==("partial" if failures else "complete")
    if kind=="category":assert str(loop.context.workspace.get(result["dataset"])["value"].dtype)=="category"
    assert loop.context.workspace.get("orders").equals(frame)


@pytest.mark.parametrize("error",[False,True])
def test_type_conversion_auto_audits_applied_and_retains_skipped_original_policy(engine,monkeypatch,error):
    import data_agent.tools.data_clean as tool
    loop,_=engine;frame=pd.DataFrame({"number":["1","2",None],"percent":["10%","20%",None],"suffix":["1元","2元",None],"flag":["yes","no",None],"label":["a","b",None]})
    loop.context.workspace.add("orders",frame)
    original=tool.apply_conversion
    def convert(series,kind):
        if error and kind=="numeric":raise ValueError("fixture original parser rejected")
        return original(series,kind)
    monkeypatch.setattr(tool,"apply_conversion",convert)
    args={"name":"orders","auto":True}
    _s1_register(loop,"应用已有自动转换策略",[_operation_spec("apply_type_conversion",args,["orders"])])
    rid,result=execute(loop,"apply_type_conversion",args)
    from data_agent.agent.publication.native import resolve_operation_effect
    effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
    audits={r["column"]:r for r in result["conversion_audit"]}
    assert set(audits)=={"number","percent","suffix","flag"}
    assert audits["number"]["conversion_failures"]==(2 if error else 0)
    assert audits["number"]["new_missing"]==0
    assert result["status"]==("partial" if error else "complete")
    assert result["skipped"]==[{"column":"label","suggested_type":"keep","reason":"文本类型，无需转换"}]
    assert bool(effect.get("completion_gap"))==error


@pytest.mark.parametrize("fault",["counts","kind","status","missing"])
def test_type_conversion_effect_rejects_audit_not_matching_actual_object(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":["1","bad",None]}))
    args={"name":"orders","column":"amount","target_type":"numeric"}
    _s1_register(loop,"转换数值并保留真实新表",[_operation_spec("apply_type_conversion",args,["orders"])])
    rid,_=execute(loop,"apply_type_conversion",args);original=native.load_receipt_result
    def changed(**kw):
        context,receipt,result,binding=original(**kw);result=deepcopy(result)
        if fault=="counts":result["conversion_audit"][0]["converted_values"]=2
        elif fault=="kind":result["conversion_audit"][0]["to"]="category"
        elif fault=="status":result["status"]="complete"
        else:result["conversion_audit"][0]["new_missing"]=0
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("case",["filter","sort","aggregate","merge"])
def test_transform_structured_arguments_follow_public_priority_including_explicit_defaults(engine,case):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"key":[1,2],"amount":[10.,20.]}))
    if case=="filter":
        result=json.loads(transform_data("orders","filter",params='{"condition":"amount > 0"}',condition="amount > 10"))
        assert loop.context.workspace.get(result["dataset"])["amount"].tolist()==[20.]
    elif case=="sort":
        result=json.loads(transform_data("orders","sort",params='{"by":["amount"],"ascending":false}',ascending=True))
        assert loop.context.workspace.get(result["dataset"])["amount"].tolist()==[10.,20.]
    elif case=="aggregate":
        result=json.loads(transform_data("orders","group_aggregate",params='{"group_by":["key"],"agg":{"amount":"sum"}}',group_by=["key"],aggregations=[{"column":"amount","functions":["mean"]}]))
        assert "amount_mean" in result["columns"] and "amount_sum" not in result["columns"]
    else:
        loop.context.workspace.add("second",pd.DataFrame({"key":[2,3],"extra":[100,200]}))
        result=json.loads(transform_data("orders","merge",params='{"other_name":"second","on":"key","how":"outer"}',merge_how="inner"))
        assert result["rows"]==1


@pytest.mark.parametrize("how,rows",[("inner",1),("left",2),("right",2),("outer",3)])
def test_transform_merge_all_methods_keep_both_actual_parent_versions(engine,how,rows):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"key":[1,2],"amount":[10.,20.]}))
    loop.context.workspace.add("second",pd.DataFrame({"key":[2,3],"extra":[100,200]}))
    expected=[loop.context.workspace.get_data_identity(n)["version_id"] for n in ["orders","second"]]
    result=json.loads(transform_data("orders","merge",other_name="second",merge_on="key",merge_how=how))
    assert result["rows"]==rows
    assert loop.context.workspace.get_data_identity(result["dataset"])["parent_version_ids"]==expected


def test_transform_operation_goal_closes_without_fabricated_data_claim(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;args={"name":"orders","operation":"filter","condition":"amount > 10"}
    _s1_register(loop,"只筛选并保留新表",[_operation_spec("transform_data",args,["orders"])])
    rid,result=execute(loop,"transform_data",args);host=snapshot_for_turn(loop).as_dict();req=host["requirements"][0]
    assert req["effect_ids"] and not req["claim_ids"] and req["gap"] is None
    effect=next(e for e in host["effects"] if e["receipt_id"]==rid)
    assert effect["object"]["name"]==result["dataset"]


@pytest.mark.parametrize("wire",["structured","legacy"])
def test_transform_merge_effect_validates_both_sources_and_exact_parameters(engine,wire):
    from data_agent.agent.publication.native import resolve_operation_effect
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("second",pd.DataFrame({"amount":[10,20],"extra":[100,200]}))
    args={"name":"orders","operation":"merge"}
    if wire=="legacy":args["params"]='{"other_name":"second","on":"amount","how":"left"}'
    else:args.update(other_name="second",merge_on="amount",merge_how="left")
    _s1_register(loop,"只合并并保留双来源新表",[_operation_spec("transform_data",args,["orders","second"])])
    rid,result=execute(loop,"transform_data",args);effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
    assert set(effect["before"]["source_data_identities"])=={"orders","second"}
    assert all(n in effect["data_identities"] for n in ["orders","second",result["dataset"]])
    assert len(effect["object"]["identity"]["parent_version_ids"])==2
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert req["effect_ids"]==[effect["id"]] and req["gap"] is None


@pytest.mark.parametrize("operation,args,expected",[
    ("select",{"columns":["amount"]},["amount"]),
    ("rename",{"rename_mapping":{"amount":"value"}},["day","value"]),
    ("sort",{"sort_by":["amount"],"ascending":False},None),
    ("pivot",{"melt_id_vars":["day"],"melt_value_vars":["amount"]},["day","variable","value"]),
    ("pivot",{"pivot_index":"amount","pivot_columns":"day","pivot_values":"other"},None),
    ("resample",{"date_col":"day","freq":"W","resample_agg":{"amount":"sum"}},["day","amount"]),
])
def test_transform_remaining_modes_have_actual_operation_effect_and_original_values(engine,operation,args,expected):
    from data_agent.agent.publication.native import resolve_operation_effect,resolve_native_claims
    loop,_=engine
    if "pivot_values" in args:loop.context.workspace.add("orders",pd.DataFrame({"amount":[1,2],"day":["D1","D2"],"other":[10,20]}))
    args=dict(args,name="orders",operation=operation)
    _s1_register(loop,"只变换并保留真实新表",[_operation_spec("transform_data",args,["orders"])])
    rid,result=execute(loop,"transform_data",args);effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
    if expected:assert result["columns"]==expected
    assert effect["object"]["name"]==result["dataset"]
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    if operation=="resample":assert sum(r["amount"] for r in result["measurement_records"])==180
    if operation=="pivot":assert any(c["basis_refs"][0]["result_path"]==["measurement_records"] for c in claims)


@pytest.mark.parametrize("raw",["[]","null","true","bad"])
def test_transform_invalid_legacy_json_is_structured_failure_without_new_object(engine,raw):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;before=loop.context.workspace.list_datasets()
    result=json.loads(transform_data("orders","filter",params=raw))
    assert result["error_type"]=="invalid_parameter" and loop.context.workspace.list_datasets()==before


def test_transform_self_merge_records_one_actual_source_identity(engine):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;result=json.loads(transform_data("orders","merge",other_name="orders",merge_on="day"))
    assert loop.context.workspace.get_data_identity(result["dataset"])["parent_version_ids"]==[loop.context.workspace.get_data_identity("orders")["version_id"]]


@pytest.mark.parametrize("fault",["parameters","source","operation","parent"])
def test_transform_facts_and_effect_use_same_closed_source_and_parameter_validation(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;args={"name":"orders","operation":"group_aggregate","group_by":["amount"],"aggregations":[{"column":"amount","functions":["sum"]}]}
    _s1_register(loop,"聚合并保留新表及原事实",[_operation_spec("transform_data",args,["orders"])])
    rid,result=execute(loop,"transform_data",args);original=native.load_receipt_result
    def changed(**kw):
        context,receipt,result,binding=original(**kw);result=deepcopy(result);binding=deepcopy(binding)
        if fault=="parameters":result["parameters"]["agg"]={"amount":["mean"]}
        elif fault=="source":result["source_datasets"]=["second"]
        elif fault=="operation":result["operation"]="filter"
        else:binding["data_identities"][result["dataset"]]["parent_version_ids"]=["wrong"]
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    for resolver in [native.resolve_native_claims,native.resolve_operation_effect]:
        with pytest.raises(ValueError):resolver(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("method,expected",[("count",[1,0,1]),("size",[2,2,1])])
def test_transform_legacy_count_and_size_match_structured_nonmissing_or_rows(engine,method,expected):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"group":["A","A","B","B","C"],"amount":[1.,None,None,None,100.]}))
    old=json.loads(transform_data("orders","group_aggregate",params=json.dumps({"group_by":["group"],"agg_func":method,"agg_col":"amount"})))
    new=json.loads(transform_data("orders","group_aggregate",group_by=["group"],aggregations=[{"column":"amount","functions":[method]}]))
    old_values=[r["count"] for r in old["measurement_records"]]
    assert old_values==expected==[r["amount_"+method] for r in new["measurement_records"]]


def test_transform_legacy_count_without_column_refuses_implicit_rows(engine):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;before=loop.context.workspace.list_datasets()
    result=json.loads(transform_data("orders","group_aggregate",params='{"group_by":["amount"],"agg_func":"count"}'))
    assert "error" in result and "size" in result["error"] and "列" in result["error"]
    assert loop.context.workspace.list_datasets()==before


@pytest.mark.parametrize("wire",["structured","legacy","default","multiple"])
def test_transform_resample_empty_missing_zero_and_bad_dates_are_distinct(engine,wire):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"day":["2026-10-01","2026-10-01","2026-10-03","2026-10-04","bad",None],"amount":[1.,None,None,0.,100.,200.]}))
    args={"name":"orders","operation":"resample"}
    if wire=="legacy":args["params"]='{"date_col":"day","freq":"D","agg":{"amount":"sum"}}'
    else:args.update(date_col="day",freq="D")
    if wire=="structured":args["resample_agg"]={"amount":"sum"}
    if wire=="multiple":args["params"]='{"agg":{"amount":["sum","count","size"]}}'
    result=json.loads(transform_data(**args));metric="amount_sum" if wire=="multiple" else "amount"
    assert [r[metric] for r in result["measurement_records"]]==[1.,None,None,0.]
    assert result["resample_audit"]=={"source_rows":6,"effective_rows":4,"excluded_rows":2,"missing_date_rows":1,"invalid_date_rows":1}
    assert result["status"]=="partial" and result["rows"]==4
    if wire=="multiple":
        assert [r["amount_count"] for r in result["measurement_records"]]==[1,0,0,1]
        assert [r["amount_size"] for r in result["measurement_records"]]==[2,0,1,1]


@pytest.mark.parametrize("delivery",["operation","table"])
def test_transform_resample_partial_effect_and_fact_keep_original_known_results(engine,delivery):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.native import resolve_operation_effect,resolve_native_claims
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"day":["2026-10-01","2026-10-03","bad"],"amount":[1.,None,100.]}))
    args={"name":"orders","operation":"resample","date_col":"day","freq":"D","resample_agg":{"amount":"sum"}}
    specs=[_operation_spec("transform_data",args,["orders"])] if delivery=="operation" else [{"kind":"table","scope":{"datasets":["orders"]}}]
    _s1_register(loop,"按日重采样并交付原范围结果",specs)
    rid,result=execute(loop,"transform_data",args)
    effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
    assert effect["details"]["resample_audit"]["excluded_rows"]==1 and effect["completion_gap"]["status"]=="evidence_insufficient"
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    table=next(c for c in claims if c["basis_refs"][0]["result_path"]==["measurement_records"])
    assert [r["amount"] for r in table["value"]]==[1.,None,None] and table["target"]["completion_gap"]==effect["completion_gap"]
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert req["gap"]["status"]=="evidence_insufficient"
    assert req["effect_ids"] if delivery=="operation" else req["claim_ids"]


@pytest.mark.parametrize("fault",["count","status"])
def test_transform_resample_tampered_scope_is_rejected_for_facts_and_effects(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;args={"name":"orders","operation":"resample","date_col":"day","freq":"W"}
    _s1_register(loop,"重采样保留实际范围",[_operation_spec("transform_data",args,["orders"])])
    rid,result=execute(loop,"transform_data",args);original=native.load_receipt_result
    def changed(**kw):
        context,receipt,result,binding=original(**kw);result=deepcopy(result)
        if fault=="count":result["resample_audit"]["excluded_rows"]+=1
        else:result["status"]="partial"
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    for resolver in [native.resolve_native_claims,native.resolve_operation_effect]:
        with pytest.raises(ValueError):resolver(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("method,expected",[("sum",4.),("mean",2.),("count",2),("size",3),("nunique",2),("min",1.),("max",3.),("median",2.),("std",2**.5)])
def test_transform_all_public_aggregations_have_independent_actual_values(engine,method,expected):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"group":["A"]*3,"amount":[1.,3.,None]}))
    result=json.loads(transform_data("orders","group_aggregate",group_by=["group"],aggregations=[{"column":"amount","functions":[method]}]))
    assert result["measurement_records"][0]["amount_"+method]==pytest.approx(expected)


@pytest.mark.parametrize("freq,days,values",[("D",["2026-10-01","2026-10-02"],[1.,3.]),("W",["2026-10-04"],[4.]),("ME",["2026-10-31"],[4.]),("QE",["2026-12-31"],[4.]),("YE",["2026-12-31"],[4.])])
def test_transform_all_public_resample_frequencies_preserve_sum_and_bucket_identity(engine,freq,days,values):
    from data_agent.tools.data_transform import transform_data
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"day":["2026-10-01","2026-10-02"],"amount":[1.,3.]}))
    result=json.loads(transform_data("orders","resample",date_col="day",freq=freq,resample_agg={"amount":"sum"}))
    assert [r["day"][:10] for r in result["measurement_records"]]==days
    assert [r["amount"] for r in result["measurement_records"]]==values
    assert result["resample_audit"]["excluded_rows"]==0 and result["status"]=="complete"


@pytest.mark.parametrize("values,mean,std,skew,kurt,reason",[
    ([5.,5.,5.],5.,0.,None,None,"constant_sample"),
    ([1.,3.],2.,1.,0.,-2.,"insufficient_sample"),
    ([7.],7.,0.,None,None,"insufficient_sample"),
    ([None,None],None,None,None,None,"insufficient_sample"),
    ([1.,float("inf"),3.],2.,1.,0.,-2.,"insufficient_sample"),
    ([1.,2.,3.,4.],2.5,1.118,0.,-1.36,""),
])
def test_distribution_degenerate_and_finite_ranges_keep_each_actual_column(engine,values,mean,std,skew,kurt,reason):
    from data_agent.tools.eda import distribution_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":pd.Series(values,dtype=float)}))
    raw=distribution_analysis("orders","amount");result=json.loads(raw)
    json.loads(raw,parse_constant=lambda value:pytest.fail("nonfinite JSON "+value))
    row=result["amount"]
    assert (row["mean"],row["std"],row["skewness"],row["kurtosis"])==(mean,std,skew,kurt)
    count=sum(v is not None and v!=float("inf") for v in values)
    audit=row["observation"]
    assert audit=={"source_rows":len(values),"missing_count":values.count(None),"excluded_nonfinite":values.count(float("inf")),"count":count}
    normality=row["normality_test"]
    assert "is_normal" not in normality and normality["reason"]==reason
    if reason:assert normality["p_value"] is None and normality["reject_normality"] is None and normality["conclusion"]=="unknown"
    else:assert normality["p_value"]==pytest.approx(.971877,abs=1e-6) and normality["reject_normality"] is False and normality["conclusion"]=="not_rejected"
    assert row["status"]==("partial" if float("inf") in values else "complete")


@pytest.mark.parametrize("columns",["missing","amount,amount","text","amount,text"])
def test_distribution_explicit_invalid_column_selection_is_rejected_as_a_whole(engine,columns):
    from data_agent.tools.eda import distribution_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,2.],"text":["a","b"]}))
    result=json.loads(distribution_analysis("orders",columns))
    assert result["error_type"]=="invalid_parameter" and "amount" not in result


def test_distribution_shapiro_upper_bound_remains_unassessed_with_descriptive_values(engine):
    from data_agent.tools.eda import distribution_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":range(5000)}))
    row=json.loads(distribution_analysis("orders","amount"))["amount"]
    assert row["count"]==5000 and row["mean"]==2499.5 and row["normality_test"]["reason"]=="sample_limit"
    assert row["normality_test"]["p_value"] is None


@pytest.mark.parametrize("case,expected,partial",[("single",7.,False),("missing",None,True),("nonfinite",2.,True)])
def test_distribution_actual_mean_keeps_unknown_or_excluded_scope_in_original_goal(engine,case,expected,partial):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;values={"single":[7.],"missing":[None,None],"nonfinite":[1.,float("inf"),3.]}[case]
    loop.context.workspace.add("orders",pd.DataFrame({"amount":pd.Series(values,dtype=float)}))
    _s1_register(loop,"交付amount均值",[{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}}])
    rid,result=execute(loop,"distribution_analysis",{"name":"orders","columns":"amount"})
    host=snapshot_for_turn(loop).as_dict();req=host["requirements"][0]
    claims=[c for c in host["claims"] if c["id"] in req["claim_ids"]]
    assert len(claims)==1 and claims[0]["value"]==expected
    assert bool(req["gap"])==partial
    if partial:assert req["gap"]["status"]=="evidence_insufficient"


@pytest.mark.parametrize("fault",["count","missing","status","normality","quantile"])
def test_distribution_closed_adapter_rejects_scope_or_inference_tampering(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,2.,3.,4.]}))
    rid,result=execute(loop,"distribution_analysis",{"name":"orders","columns":"amount"});original=native.load_receipt_result
    def changed(**kw):
        context,receipt,result,binding=original(**kw);result=deepcopy(result);row=result["amount"]
        if fault=="count":row["count"]+=1
        elif fault=="missing":row["observation"]["missing_count"]+=1
        elif fault=="status":row["status"]="partial"
        elif fault=="quantile":row["quantiles"]["25%"]+=1
        else:row["normality_test"]["conclusion"]="normality_proven"
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("values,expected",[([1.,2.,3.,4.],[1.,1.75,2.5,3.25,4.]),([7.],[7.]*5),([None,None],[None]*5)])
def test_distribution_promised_five_number_summary_has_linear_quantiles_and_original_claims(engine,values,expected):
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":pd.Series(values,dtype=float)}))
    rid,result=execute(loop,"distribution_analysis",{"name":"orders","columns":"amount"});row=result["amount"]
    assert row["quantile_interpolation"]=="linear"
    keys=["min","25%","50%","75%","max"]
    assert [row["quantiles"][k] for k in keys]==expected
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    for key,value in zip(keys,expected):
        claim=next(c for c in claims if c["basis_refs"][0]["result_path"]==["amount","quantiles",key])
        assert claim["value"]==value and claim["target"]["statistic"]==key and claim["target"]["deliverable"]
        assert bool(claim["target"].get("completion_gap"))==(value is None)


@pytest.mark.parametrize("window,expected",[(0,1),(2,1),(1,0)])
def test_funnel_earliest_valid_path_preserves_adjacent_window(engine,window,expected):
    loop,_=engine
    loop.context.workspace.add("orders",pd.DataFrame({"uid":[1]*3,"event":["B","A","B"],"time":["2026-01-01 09:00","2026-01-01 10:00","2026-01-01 12:00"]}))
    _,r=execute(loop,"funnel_analysis",{"name":"orders","mode":"steps","user_col":"uid","event_col":"event","time_col":"time","steps":"A,B","window_hours":window})
    assert [s["count"] for s in r["steps"]]==[1,expected]
    assert r["temporal_order_verified"] is True

@pytest.mark.parametrize("mode",["steps","aggregate","rates"])
def test_funnel_overall_uses_full_source_and_keeps_every_group(engine,mode):
    loop,_=engine
    if mode=="steps":
        rows=[{"uid":i,"event":"A","dim":"all" if i<10 else "Y"} for i in range(100)]+[{"uid":i,"event":"B","dim":"all"} for i in range(10)]
        frame=pd.DataFrame(rows);args={"user_col":"uid","event_col":"event","steps":"A,B"}
    elif mode=="aggregate":
        frame=pd.DataFrame({"step":["A","B","A","B"],"count":[10,10,90,0],"dim":["all","all","Y","Y"]});args={"step_col":"step","count_col":"count","steps":"A,B"}
    else:
        frame=pd.DataFrame({"A":[1.]*100,"B":[1.]*10+[0.]*90,"dim":["all"]*10+["Y"]*90});args={"rate_cols":"A,B"}
    loop.context.workspace.add("orders",frame)
    rid,r=execute(loop,"funnel_analysis",dict(name="orders",mode=mode,dimension="dim",**args))
    assert r["overall_conversion"]==.1 and set(r["dimension_funnels"])=={"all","Y"}
    assert r["dimension_funnels"]["all"]["overall_conversion"]==1.
    from data_agent.agent.publication.native import resolve_native_claims
    claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    for key in ["steps","overall_conversion","dimension_funnels"]:
        assert next(c for c in claims if c["basis_refs"][0]["result_path"]==[key])["value"]==r[key]


def test_funnel_aggregate_sums_duplicate_steps_before_inferred_order(engine):
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"step":["A","A","B"],"count":[10,20,5]}))
    _,r=execute(loop,"funnel_analysis",{"name":"orders","mode":"aggregate","step_col":"step","count_col":"count"})
    assert [(s["step"],s["count"]) for s in r["steps"]]==[("A",30),("B",5)]
    assert r["step_order"]=="inferred_from_aggregate_counts"

@pytest.mark.parametrize("counts",[[-1,2],[1.5,2],[float("inf"),2]])
def test_funnel_aggregate_invalid_counts_are_rejected(engine,counts):
    from data_agent.tools.eda import funnel_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"step":["A","B"],"count":counts}))
    r=funnel_analysis("orders",mode="aggregate",step_col="step",count_col="count")
    assert isinstance(r,str) and r.startswith("Error:"),r

@pytest.mark.parametrize("counts,steps,expected",[([0,0],"A,B",[0,0]),([10],"A,B",[10,None])])
def test_funnel_missing_step_and_zero_denominator_stay_unknown(engine,counts,steps,expected):
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"step":["A","B"][:len(counts)],"count":counts}))
    _s1_register(loop,"交付漏斗步骤及整体比例",[{"kind":"table","scope":{"datasets":["orders"]}}])
    _,r=execute(loop,"funnel_analysis",{"name":"orders","mode":"aggregate","step_col":"step","count_col":"count","steps":steps})
    assert [s["count"] for s in r["steps"]]==expected and r["overall_conversion"] is None
    from data_agent.agent.publication.runtime import snapshot_for_turn
    assert snapshot_for_turn(loop).as_dict()["requirements"][0]["gap"]["status"]=="evidence_insufficient"

@pytest.mark.parametrize("values",[[80.,40.],[.4,.8],[float("inf"),.2],[-.1,0.]])
def test_funnel_rates_invalid_cumulative_proportions_refuse_without_clipping(engine,values):
    from data_agent.tools.eda import funnel_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"A":[values[0]],"B":[values[1]]}))
    r=funnel_analysis("orders",mode="rates",rate_cols="A,B")
    assert isinstance(r,str) and r.startswith("Error:"),r


def test_funnel_rates_retains_column_means_effective_counts_and_unknown_people(engine):
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"A":[.8,.6,None],"B":[.4,.2,None]}))
    _,r=execute(loop,"funnel_analysis",{"name":"orders","mode":"rates","rate_cols":"A,B"})
    assert [s["cumulative_rate"] for s in r["steps"]]==[.7,.3]
    assert [s["count"] for s in r["steps"]]==[None,None]
    assert [s["effective_n"] for s in r["steps"]]==[2,2]
    assert r["steps"][1]["step_conversion"]==pytest.approx(.3/.7,abs=1e-4)
    assert r["overall_conversion"]==pytest.approx(.3/.7,abs=1e-4)
    assert "累积率列均值之比" in " ".join(r["limitations"])


def test_funnel_without_time_only_delivers_set_containment(engine):
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"uid":[1,1],"event":["B","A"]}))
    _,r=execute(loop,"funnel_analysis",{"name":"orders","mode":"steps","user_col":"uid","event_col":"event","steps":"A,B"})
    assert [s["count"] for s in r["steps"]]==[1,1] and r["temporal_order_verified"] is False
    assert "集合包含" in " ".join(r["limitations"])

@pytest.mark.parametrize("fault",["steps","overall","dimension","parameters","temporal"])
def test_funnel_closed_adapter_rejects_original_receipt_tampering(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"step":["A","B"],"count":[100,10],"dim":["X","X"]}))
    rid,_=execute(loop,"funnel_analysis",{"name":"orders","mode":"aggregate","step_col":"step","count_col":"count","steps":"A,B","dimension":"dim"});original=native.load_receipt_result
    def changed(**kw):
        context,receipt,r,binding=original(**kw);r=deepcopy(r)
        if fault=="steps":r["steps"][0]["count"]=101
        elif fault=="overall":r["overall_conversion"]=1.
        elif fault=="dimension":r["dimension_funnels"]={}
        elif fault=="parameters":r["parameters"]={}
        else:r["temporal_order_verified"]=True
        return context,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)



def test_funnel_rates_ratio_uses_original_means_before_display_rounding(engine):
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"A":[.5],"B":[.33335]}))
    _,r=execute(loop,"funnel_analysis",{"name":"orders","mode":"rates","rate_cols":"A,B"})
    assert r["steps"][1]["step_conversion"]==r["overall_conversion"]==.6667

@pytest.mark.parametrize("fault",[None,"mode","steps","column","dimension","window"])
def test_funnel_typed_delivery_requires_exact_original_business_parameters(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"step":["A","B"],"count":[100,10],"dim":["X","X"]}))
    params={"funnel_mode":"aggregate","funnel_steps":"A,B","funnel_step_col":"step","funnel_count_col":"count","funnel_dimension":"dim","funnel_window_hours":0,"funnel_output":"steps"}
    if fault:params[{"mode":"funnel_mode","steps":"funnel_steps","column":"funnel_count_col","dimension":"funnel_dimension","window":"funnel_window_hours"}[fault]]={"mode":"rates","steps":"B,A","column":"wrong","dimension":"wrong","window":1}[fault]
    _s1_register(loop,"交付指定漏斗步骤",[{"kind":"table","scope":{"datasets":["orders"],"parameters":params}}])
    execute(loop,"funnel_analysis",{"name":"orders","mode":"aggregate","step_col":"step","count_col":"count","steps":"A,B","dimension":"dim"})
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert bool(req["claim_ids"])==(fault is None)


def test_funnel_all_eleven_groups_and_missing_dimension_are_retained(engine):
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"step":["A","B"]*12,"count":[10,1]*12,"dim":sum(([str(i)]*2 for i in range(11)),[])+[None,None]}))
    _,r=execute(loop,"funnel_analysis",{"name":"orders","mode":"aggregate","step_col":"step","count_col":"count","steps":"A,B","dimension":"dim"})
    assert len(r["dimension_funnels"])==12 and r["steps"][0]["count"]==120 and r["overall_conversion"]==.1



def _cohort_axis_frame():
    return pd.DataFrame({"user":["u1","u1","u2","u3"],"day":["2026-01-01","2026-03-01","2026-01-15","2026-02-01"],"type":["open","pay","open","open"]})


def test_cohort_complete_age_axis_distinguishes_observed_zero_and_future_unknown(engine):
    loop,_=engine;loop.context.workspace.add("orders",_cohort_axis_frame())
    _,r=execute(loop,"cohort_analysis",{"name":"orders","user_col":"user","time_col":"day"})
    assert r["age_axis"]==[0,1,2]
    assert r["cohorts"]==[
        {"cohort":"2026-01","size":2,"retention":{"month_0":100.,"month_1":0.,"month_2":50.},"user_counts":{"month_0":2,"month_1":0,"month_2":1}},
        {"cohort":"2026-02","size":1,"retention":{"month_0":100.,"month_1":0.,"month_2":None},"user_counts":{"month_0":1,"month_1":0,"month_2":None}}]
    assert r["final_month_incomplete"] is True and r["status"]=="complete"


def test_cohort_exclusion_audit_counts_union_without_losing_valid_months(engine):
    loop,_=engine;frame=_cohort_axis_frame()
    bad=pd.DataFrame({"user":[None,"u4","u5",None],"day":["2026-03-02",None,"bad-date","bad-date"]})
    loop.context.workspace.add("orders",pd.concat([frame,bad],ignore_index=True))
    _s1_register(loop,"交付留存矩阵",[{"kind":"table","scope":{"datasets":["orders"]}}])
    _,r=execute(loop,"cohort_analysis",{"name":"orders","user_col":"user","time_col":"day"})
    assert r["observation"]=={"source_rows":8,"effective_rows":4,"excluded_rows":4,"missing_user_rows":2,"missing_time_rows":1,"invalid_time_rows":2}
    assert r["status"]=="partial" and r["cohorts"][0]["retention"]["month_2"]==50.
    from data_agent.agent.publication.runtime import snapshot_for_turn
    host=snapshot_for_turn(loop).as_dict();req=host["requirements"][0]
    assert req["claim_ids"] and req["gap"]["status"]=="evidence_insufficient"
    assert any(c["value"]==r["cohorts"] for c in host["claims"] if c["id"] in req["claim_ids"])


def test_cohort_explicit_absent_event_column_refuses_without_silent_omission(engine):
    from data_agent.tools.eda import cohort_analysis
    loop,_=engine;loop.context.workspace.add("orders",_cohort_axis_frame())
    r=cohort_analysis("orders","user","day",event_col="missing")
    assert r.startswith("Error:") and "missing" in r


def test_cohort_user_dedup_and_real_last_calendar_day_remain_original_method(engine):
    from data_agent.tools.eda import cohort_analysis
    loop,_=engine;frame=_cohort_axis_frame();frame.loc[1,"day"]="2026-03-31"
    loop.context.workspace.add("orders",pd.concat([frame,frame],ignore_index=True))
    r=json.loads(cohort_analysis("orders","user","day",event_col="type"))
    assert [row["size"] for row in r["cohorts"]]==[2,1] and r["cohorts"][0]["retention"]["month_2"]==50.
    assert r["observation"]["effective_rows"]==8 and r["final_month_incomplete"] is False
    assert r["parameters"]=={"user_col":"user","time_col":"day","event_col":"type"}

@pytest.mark.parametrize("fault",["age","count","rate","window","audit","status","parameters"])
def test_cohort_closed_adapter_rejects_matrix_scope_or_receipt_tampering(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",_cohort_axis_frame())
    rid,_=execute(loop,"cohort_analysis",{"name":"orders","user_col":"user","time_col":"day"});original=native.load_receipt_result
    def changed(**kw):
        context,receipt,r,binding=original(**kw);r=deepcopy(r)
        if fault=="age":r["age_axis"]=[0,2]
        elif fault=="count":r["cohorts"][0]["size"]=3
        elif fault=="rate":r["cohorts"][0]["retention"]["month_2"]=100.
        elif fault=="window":r["observation_window"]=["2026-01-01","2026-04-01"]
        elif fault=="audit":r["observation"]={}
        elif fault=="status":r["status"]="partial"
        else:r["parameters"]={"user_col":"wrong"}
        return context,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"user","time","event"])
def test_cohort_formal_delivery_binds_exact_user_time_and_event_columns(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",_cohort_axis_frame())
    params={"cohort_user_col":"user","cohort_time_col":"day","cohort_event_col":"type","cohort_output":"cohorts"}
    if fault:params["cohort_"+fault+"_col"]="wrong"
    _s1_register(loop,"交付指定留存矩阵",[{"kind":"table","scope":{"datasets":["orders"],"parameters":params}}])
    execute(loop,"cohort_analysis",{"name":"orders","user_col":"user","time_col":"day","event_col":"type"})
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert bool(req["claim_ids"])==(fault is None)


def test_cohort_all_unusable_observations_return_audited_error_without_invented_cohorts(engine):
    from data_agent.tools.eda import cohort_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"user":[None,"u1"],"day":["bad",None]}))
    r=json.loads(cohort_analysis("orders","user","day"))
    assert r["error"]=="没有可用用户与事件时间" and r["status"]=="not_computed"
    assert r["observation"]=={"source_rows":2,"effective_rows":0,"excluded_rows":2,"missing_user_rows":1,"missing_time_rows":1,"invalid_time_rows":1}
    assert "cohorts" not in r


def test_cohort_original_user_column_named_period_does_not_overwrite_entity_identity(engine):
    loop,_=engine;frame=_cohort_axis_frame().rename(columns={"user":"period"});loop.context.workspace.add("orders",frame)
    _,r=execute(loop,"cohort_analysis",{"name":"orders","user_col":"period","time_col":"day"})
    assert [row["size"] for row in r["cohorts"]]==[2,1]


@pytest.mark.parametrize("values,requested,actual",[([1.,1.,1.,1.],3,1),([1.,10.,100.],3,3),([1.,10.,None],2,2)])
def test_segmentation_actual_nonempty_clusters_unknown_std_and_scope(engine,values,requested,actual):
    from data_agent.tools.eda import segmentation_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"x":values}))
    r=json.loads(segmentation_analysis("orders","x",requested))
    assert r["requested_n_clusters"]==requested and r["n_clusters"]==actual==len(r["clusters"])
    assert all(c["size"]>0 for c in r["clusters"])
    assert sum(c["size"] for c in r["clusters"])==r["total_samples"]==sum(v is not None for v in values)
    assert all(c["profile"]["x"]["std"] is None for c in r["clusters"] if c["size"]==1)
    assert r["observation"]=={"source_rows":len(values),"effective_rows":sum(v is not None for v in values),"excluded_rows":sum(v is None for v in values),"missing_by_feature":{"x":sum(v is None for v in values)}}
    assert r["status"]=="partial" and r["analysis_unit"]=="input_record"
    assert r["parameters"]=={"features":["x"],"n_clusters":requested,"scaler":"StandardScaler","algorithm":"KMeans","random_state":42,"n_init":10}
    assert "NaN" not in json.dumps(r) and "Infinity" not in json.dumps(r)


def test_segmentation_existing_scaler_kmeans_and_original_profile_oracle(engine,monkeypatch):
    from data_agent.tools.eda import segmentation_analysis
    from sklearn.cluster import KMeans
    import numpy as np
    calls=[]
    def model(**kwargs):
        calls.append(kwargs);return KMeans(**kwargs)
    monkeypatch.setattr("sklearn.cluster.KMeans",model)
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"x":[0.,0.,10.,10.],"y":[1.,3.,11.,13.]}))
    r=json.loads(segmentation_analysis("orders"," x, y ",2))
    assert calls==[{"n_clusters":2,"random_state":42,"n_init":10}]
    assert r["status"]=="complete" and r["requested_n_clusters"]==r["n_clusters"]==2
    profiles=sorted(r["clusters"],key=lambda c:c["profile"]["x"]["mean"])
    assert [(c["size"],c["percentage"],c["profile"]["x"]["mean"],c["profile"]["y"]["mean"]) for c in profiles]==[(2,50.,0.,2.),(2,50.,10.,12.)]
    assert all(c["profile"]["x"]["std"]==0. and c["profile"]["y"]["std"]==round(np.sqrt(2),4) for c in profiles)


@pytest.mark.parametrize("features,values,n",[("x,x",[1.,2.],1),("missing",[1.,2.],1),("x",["a","b"],1),("x",[float("inf"),2.],1),("x",[float("-inf"),2.],1),("",[1.,2.],1),("x",[None,None],1),("x",[1.,2.],0),("x",[1.,2.],-1),("x",[1.,2.],3)])
def test_segmentation_invalid_features_nonfinite_or_cluster_count_refuse(engine,features,values,n):
    from data_agent.tools.eda import segmentation_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"x":values}))
    r=segmentation_analysis("orders",features,n)
    assert r.startswith("Error:"),r


def test_segmentation_missing_scope_is_union_and_nonfinite_cannot_hide_in_dropped_row(engine):
    from data_agent.tools.eda import segmentation_analysis
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"x":[0.,10.,None,None],"y":[1.,11.,None,3.]}))
    r=json.loads(segmentation_analysis("orders","x,y",2))
    assert r["observation"]=={"source_rows":4,"effective_rows":2,"excluded_rows":2,"missing_by_feature":{"x":2,"y":1}}
    loop.context.workspace.add("orders",pd.DataFrame({"x":[0.,10.,float("inf")],"y":[1.,11.,None]}))
    assert segmentation_analysis("orders","x,y",2).startswith("Error:")


@pytest.mark.parametrize("fault",["size","std","actual_count","parameters","audit","status","limits"])
def test_segmentation_closed_adapter_rejects_original_profiles_scope_and_receipt_tampering(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"x":[0.,0.,10.,10.],"y":[1.,3.,11.,13.]}))
    rid,_=execute(loop,"segmentation_analysis",{"name":"orders","features":"x,y","n_clusters":2});original=native.load_receipt_result
    def changed(**kw):
        context,receipt,r,binding=original(**kw);r=deepcopy(r)
        if fault=="size":r["clusters"][0]["size"]+=1
        elif fault=="std":r["clusters"][0]["profile"]["y"]["std"]=0.
        elif fault=="actual_count":r["n_clusters"]=3
        elif fault=="parameters":r["parameters"]["n_init"]=1
        elif fault=="audit":r["observation"]["excluded_rows"]=1
        elif fault=="status":r["status"]="partial"
        else:r["limitations"]=[]
        return context,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"features","count","metric","type"])
def test_segmentation_formal_delivery_requires_exact_features_requested_clusters_and_kind(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"x":[0.,0.,10.,10.],"y":[1.,3.,11.,13.]}))
    params={"segmentation_features":["x","y"],"segmentation_n_clusters":2,"segmentation_output":"clusters"}
    scope={"datasets":["orders"],"metrics":["x","y"],"parameters":params};kind="table"
    if fault=="features":params["segmentation_features"]=["y","x"]
    elif fault=="count":params["segmentation_n_clusters"]=3
    elif fault=="metric":scope["metrics"]=["wrong"]
    elif fault=="type":kind="measurement";scope["quantity"]="value"
    _s1_register(loop,"交付指定特征和请求簇数的分群",[{"kind":kind,"scope":scope}])
    execute(loop,"segmentation_analysis",{"name":"orders","features":"x,y","n_clusters":2})
    req=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert bool(req["claim_ids"])==(fault is None)


def test_segmentation_storage_validation_in_synthesis_does_not_expose_frame(engine):
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"x":[1.,2.,10.,11.]}))
    rid,r=execute(loop,"segmentation_analysis",{"name":"orders","features":"x","n_clusters":2})
    boundary=WorkspaceScopeSnapshot(phase="synthesis",session_id=loop.session_id,allowed_datasets=frozenset())
    with loop.context.bind_workspace_scope(boundary):
        assert loop.context.workspace.get("orders") is None
        claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
        assert next(c["value"] for c in claims if c["basis_refs"][0]["result_path"]==["clusters"])==r["clusters"]
        assert loop.context.workspace.get("orders") is None


@pytest.mark.parametrize("args",[{"n":-1},{"n":0},{"n":True},{"n":1.5},{"columns":"missing"},{"columns":"id,missing"},{"columns":"id,id"},{"sort_by":"missing"}])
def test_topn_invalid_requested_range_or_columns_refuse_without_derived_object(engine,args):
    from data_agent.tools.eda import top_n
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"id":["A","B","C","D"],"amount":[1.,2.,3.,4.]}))
    result=top_n("orders",save_as="ranked",**args)
    assert result.startswith("Error:"),result
    assert loop.context.workspace.get("ranked") is None


@pytest.mark.parametrize("ascending,columns,n,ids",[(False,"",2,["D","C"]),(True,"id,amount",2,["A","B"]),(False,"id",10,["D","C","B","A"])])
def test_topn_original_values_actual_sort_scope_and_real_derived_table(engine,ascending,columns,n,ids):
    from data_agent.tools.eda import top_n
    loop,_=engine;amount=[.123456789012345,.223456789012345,.323456789012345,.423456789012345]
    loop.context.workspace.add("orders",pd.DataFrame({"id":["A","B","C","D"],"amount":amount}))
    r=json.loads(top_n("orders",n=n,ascending=ascending,columns=columns,save_as="ranked"))
    assert [row["id"] for row in r["records"]]==ids
    assert r["sort_by"]=="amount" and r["ascending"] is ascending and r["n"]==len(ids)
    assert r["parameters"]=={"sort_by":"amount","ascending":ascending,"n":n,"columns":columns.split(",") if columns else ["id","amount"]}
    assert r["observation"]=={"source_rows":4,"returned_rows":len(ids)}
    if columns!="id":assert r["records"][0]["amount"]==amount[0 if ascending else 3]
    derived=loop.context.workspace.get("ranked");assert derived.to_dict("records")==r["records"]
    assert loop.context.workspace.get_data_identity("ranked")["parent_version_ids"]==[loop.context.workspace.get_data_identity("orders")["version_id"]]


@pytest.mark.parametrize("fault",["records","n","sort","direction","parameters"])
def test_topn_closed_adapter_rejects_ranking_receipt_tampering(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[.123456789012345,.423456789012345]}))
    rid,_=execute(loop,"top_n",{"name":"orders","sort_by":"amount","n":1});original=native.load_receipt_result
    def changed(**kw):
        context,receipt,r,binding=original(**kw);r=deepcopy(r)
        if fault=="records":r["records"][0]["amount"]=0
        elif fault=="n":r["n"]=99
        elif fault=="sort":r["sort_by"]="other"
        elif fault=="direction":r["ascending"]=True
        else:r.setdefault("parameters",{})["n"]=99
        return context,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"sort","direction","n","columns","metric","kind"])
def test_topn_exact_delivery_parameters_do_not_match_other_rankings(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"id":["A","B"],"amount":[1.,2.]}))
    params={"topn_sort_by":"amount","topn_ascending":False,"topn_n":1,"topn_columns":["id","amount"],"topn_output":"records"}
    scope={"datasets":["orders"],"metrics":["id","amount"],"parameters":params};kind="table"
    if fault=="sort":params["topn_sort_by"]="id"
    elif fault=="direction":params["topn_ascending"]=True
    elif fault=="n":params["topn_n"]=2
    elif fault=="columns":params["topn_columns"]=["amount","id"]
    elif fault=="metric":scope["metrics"]=["other"]
    elif fault=="kind":kind="measurement";scope["quantity"]="value"
    _s1_register(loop,"交付当前原值排行",[{"kind":kind,"scope":scope}])
    execute(loop,"top_n",{"name":"orders","n":1})
    host=snapshot_for_turn(loop).as_dict();req=host["requirements"][0]
    assert bool(req["claim_ids"])==(fault is None)
    assert not host["effects"]


@pytest.mark.parametrize("fault",[None,"parent","missing_predispatch","changed_object","foreign_session"])
def test_topn_real_operation_effect_validates_new_object_parent_parameters_and_permissions(engine,fault):
    from data_agent.agent.publication.native import resolve_operation_effect
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;args={"name":"orders","sort_by":"amount","n":2,"save_as":"ranked"}
    _s1_register(loop,"只保存指定排行新表",[_operation_spec("top_n",args,["orders"])])
    rid,result=execute(loop,"top_n",args);receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    if fault=="parent":receipt["operation_binding"]["source_data_identities"]["orders"]["version_id"]="foreign"
    elif fault=="missing_predispatch":receipt.pop("operation_binding",None)
    elif fault=="changed_object":
        loop.prepare_for_bound_upload();loop.context.workspace.add("ranked",pd.DataFrame({"amount":[-1.]}))
    if fault:
        with pytest.raises(ValueError):resolve_operation_effect(session_id="foreign" if fault=="foreign_session" else loop.session_id,receipt_id=rid)
    else:
        effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
        assert effect["object"]["identity"]==loop.context.workspace._publication_data_identity("ranked")
        req=snapshot_for_turn(loop).as_dict()["requirements"][0]
        assert req["gap"] is None and req["effect_ids"]==[effect["id"]] and req["claim_ids"]==[]


def test_topn_operation_without_new_target_refuses_and_collision_keeps_original(engine):
    from data_agent.agent.publication.native import operation_spec
    from data_agent.tools.eda import top_n
    loop,_=engine
    with pytest.raises(ValueError):operation_spec("top_n",{"name":"orders","n":1})
    before=loop.context.workspace.get_data_identity("orders")
    r=json.loads(top_n("orders",sort_by="amount",n=1,save_as="orders"));assert "error" in r
    assert loop.context.workspace.get_data_identity("orders")==before


def test_topn_missing_values_and_dates_preserve_original_sort_and_unknown_serialization(engine):
    from data_agent.tools.eda import top_n
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[None,0.,.423456789012345],"day":pd.to_datetime([None,"2026-10-01","2026-10-02"])}))
    r=json.loads(top_n("orders",n=10))
    assert [row["amount"] for row in r["records"]]==[.423456789012345,0.,None]
    assert r["records"][0]["day"]=="2026-10-02T00:00:00" and r["records"][-1]["day"] is None
    assert r["observation"]=={"source_rows":3,"returned_rows":3}


def _contribution_frame(case="regular"):
    frame=pd.DataFrame({"day":["2026-09-01","2026-09-01","2026-10-01","2026-10-01"],"group":["A","B","A","B"],"amount":[10.,30.,20.,50.]})
    if case=="new":frame=pd.DataFrame({"day":["2026-09-01","2026-10-01","2026-10-01"],"group":["A","A","B"],"amount":[10.,20.,100.]})
    elif case=="gone":frame=pd.DataFrame({"day":["2026-09-01","2026-09-01","2026-10-01"],"group":["A","B","A"],"amount":[20.,100.,10.]})
    elif case=="missing":frame.loc[4]=["bad","B",100.];frame.loc[5]=[None,"B",100.];frame.loc[6]=["2026-09-01",None,None]
    return frame


def _contribution_args(aggregation="mean",name="orders"):
    return {"name":name,"metric":"amount","dimension":"group","date_col":"day","period_a":"2026-09-01~2026-09-01","period_b":"2026-10-01~2026-10-01","agg_func":aggregation}


@pytest.mark.parametrize("case,expected,parts",[("regular",15.,{"A":5.,"B":10.}),("new",50.,{"A":5.,"B":45.}),("gone",-50.,{"A":-30.,"B":-20.})])
def test_contribution_mean_observed_weighted_terms_never_fabricate_absent_group_mean(engine,case,expected,parts):
    from data_agent.tools.eda import contribute_decomposition
    loop,_=engine;loop.context.workspace.add("orders",_contribution_frame(case))
    r=contribute_decomposition(**_contribution_args()).data;rows={row["value"]:row for row in r["decomposition"]}
    assert r["total_change"]==expected and {k:v["contribution"] for k,v in rows.items()}==parts
    assert sum(v["contribution"] for v in rows.values())==expected
    assert r["period_a"]["rows"]==(1 if case=="new" else 2) and r["period_b"]["rows"]==(1 if case=="gone" else 2)
    if case=="new":assert rows["B"]["period_a_mean"] is None and rows["B"]["weight_a"]==0 and rows["B"]["count_a"]==0
    if case=="gone":assert rows["B"]["period_b_mean"] is None and rows["B"]["weight_b"]==0 and rows["B"]["count_b"]==0
    assert r["percentage_denominators"]=={"contribution_pct":"abs(total_change)","total_change_pct":"abs(period_a.value)"}


@pytest.mark.parametrize("aggregation",["sum","mean"])
def test_contribution_real_exclusion_union_and_period_counts_are_visible(engine,aggregation):
    from data_agent.tools.eda import contribute_decomposition
    loop,_=engine;loop.context.workspace.add("orders",_contribution_frame("missing"))
    r=contribute_decomposition(**_contribution_args(aggregation)).data
    assert r["observation"]=={"source_rows":7,"effective_rows":4,"excluded_rows":3,"missing_time":1,"invalid_time":1,"missing_metric":1,"missing_dimension":1,"outside_period_rows":0,"overlap_rows":0}
    assert r["status"]=="partial" and r["period_a"]["rows"]==r["period_b"]["rows"]==2
    assert sum(row["count_a"] for row in r["decomposition"])==2
    assert sum(row["count_b"] for row in r["decomposition"])==2
    assert r["total_change"]==(30. if aggregation=="sum" else 15.)
    assert any("因果" in v for v in r["limitations"])


@pytest.mark.parametrize("fault",["mean","contribution","counts","scope","parameters","denominator"])
def test_contribution_closed_adapter_rejects_original_measurement_range_or_method_tampering(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",_contribution_frame("new"))
    rid,_=execute(loop,"contribute_decomposition",_contribution_args());original=native.load_receipt_result
    def changed(**kw):
        context,receipt,r,binding=original(**kw);r=deepcopy(r)
        if fault=="mean":next(row for row in r["decomposition"] if row["value"]=="B")["period_a_mean"]=0.
        elif fault=="contribution":r["decomposition"][0]["contribution"]=999.
        elif fault=="counts":r["decomposition"][0]["count_a"]=99
        elif fault=="scope":r.setdefault("observation",{})["effective_rows"]=999
        elif fault=="parameters":r.setdefault("parameters",{})["agg_func"]="sum"
        else:r["percentage_denominators"]={}
        return context,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"dimension","aggregation","date","window","metric","kind"])
def test_contribution_exact_business_window_dimension_and_aggregation_binding(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",_contribution_frame())
    params={"decomposition_dimension":"group","decomposition_aggregation":"mean","decomposition_date_col":"day","period_a":"2026-09-01~2026-09-01","period_b":"2026-10-01~2026-10-01","decomposition_output":"decomposition"}
    scope={"datasets":["orders"],"metrics":["amount"],"parameters":params};kind="table"
    if fault=="dimension":params["decomposition_dimension"]="other"
    elif fault=="aggregation":params["decomposition_aggregation"]="sum"
    elif fault=="date":params["decomposition_date_col"]="other_day"
    elif fault=="window":params["period_a"]="2026-09-01~2026-09-02"
    elif fault=="metric":scope["metrics"]=["other"]
    elif fault=="kind":kind="measurement";scope["quantity"]="value"
    _s1_register(loop,"交付指定原窗口的均值贡献分解",[{"kind":kind,"scope":scope}])
    execute(loop,"contribute_decomposition",_contribution_args())
    req=snapshot_for_turn(loop).as_dict()["requirements"][0];assert bool(req["claim_ids"])==(fault is None)


def test_contribution_sum_zero_denominators_and_complete_eleven_groups(engine):
    from data_agent.tools.eda import contribute_decomposition
    loop,_=engine;frame=pd.DataFrame({"day":["2026-09-01"]*11+["2026-10-01"]*11,"group":[str(i) for i in range(11)]*2,"amount":list(range(-5,6))+[2*i for i in range(-5,6)]})
    loop.context.workspace.add("orders",frame);r=contribute_decomposition(**_contribution_args("sum")).data
    assert len(r["decomposition"])==11 and {row["value"] for row in r["decomposition"]}=={str(i) for i in range(11)}
    assert r["period_a"]["value"]==r["period_b"]["value"]==r["total_change"]==0
    assert r["total_change_pct"] is None and all(row["contribution_pct"] is None for row in r["decomposition"])
    assert sum(row["contribution"] for row in r["decomposition"])==0


def test_contribution_original_calendar_normalization_and_outside_scope_are_disclosed(engine):
    from data_agent.tools.eda import contribute_decomposition
    loop,_=engine;frame=_contribution_frame();frame.loc[4]=["2026-11-01","A",999.]
    loop.context.workspace.add("orders",frame);args=_contribution_args("sum");args.update(period_a="2026-09-01~2026-09-02",period_b="2026-10-01~2026-10-04")
    r=contribute_decomposition(**args).data
    assert r["daily_normalized"]=={"daily_avg_a":20.,"daily_avg_b":17.5,"daily_change":-2.5,"daily_change_pct":-12.5,"note":"Daily averages account for different period lengths"}
    assert r["observation"]["outside_period_rows"]==1 and r["observation"]["excluded_rows"]==0 and r["status"]=="complete"
    assert r["total_change"]==30.


@pytest.mark.parametrize("args",[{"agg_func":"median"},{"metric":"missing"},{"dimension":"missing"},{"date_col":"missing"},{"period_a":"invalid"}])
def test_contribution_explicit_invalid_inputs_refuse_instead_of_changing_method(engine,args):
    from data_agent.tools.eda import contribute_decomposition
    loop,_=engine;loop.context.workspace.add("orders",_contribution_frame());params=dict(_contribution_args(),**args)
    result=contribute_decomposition(**params);assert isinstance(result,str) and result.startswith("Error:"),result


# Approved factor boundaries: the actual producer and the closed publication path.
def _factor_frame(case="regular"):
    import itertools
    rows=list(itertools.product([-1.,1.],repeat=3))*2
    frame=pd.DataFrame(rows,columns=["x","z","noise"])
    frame["amount"]=2*frame.x+3*frame.z+frame.noise
    frame["unit"]=["U"+str(i//2) for i in range(len(frame))]
    frame["time"]=["2026-09-01","2026-09-02"]*(len(frame)//2)
    if case=="constant":frame["amount"]=1.
    if case=="collinear":frame["z"]=2*frame.x
    if case=="excluded":frame["constant"]=1.;frame["text"]="unknown"
    if case=="missing":
        frame["z"]=frame.z.astype(object)
        frame.loc[0,"x"]=None;frame.loc[1,"amount"]=float("inf");frame.loc[2,"z"]="bad"
    if case=="short":frame=frame.iloc[:3].copy()
    if case=="scope":
        frame.loc[0,"unit"]=None;frame.loc[1,"time"]="bad";frame.loc[2,"time"]=None
    return frame


def _factor_args(name="orders",**extra):
    return dict(name=name,target_col="amount",features="x,z",**extra)


@pytest.mark.parametrize("args",[{"features":"amount,x"},{"features":"x,x"},{"features":"missing"},{"unit_col":"absent"},{"time_col":"absent"}])
def test_factor_explicit_leakage_duplicate_missing_columns_refuse(engine,args):
    from data_agent.tools.ml import attribution_analysis
    loop,_=engine;loop.context.workspace.add("orders",_factor_frame())
    kw=_factor_args();kw.update(args);raw=attribution_analysis(**kw)
    assert "error" in json.loads(raw),raw


@pytest.mark.parametrize("case",["constant","short","collinear"])
def test_factor_undefined_inference_is_strict_unknown_with_specific_gap(engine,case):
    from data_agent.tools.ml import attribution_analysis
    loop,_=engine;loop.context.workspace.add("orders",_factor_frame(case))
    raw=attribution_analysis(**_factor_args());r=json.loads(raw,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
    assert r["status"]=="limited" and r["completion_gaps"] and r["claim_ceiling"]=="associational"
    if case=="constant":
        assert r["reason_code"]=="constant_target"
        assert all(row["coefficient"] is None and row["confidence_interval_95"]==[None,None] and row["p_value"] is None and row["p_value_holm"] is None and row["reliable"] is None for row in r["estimates"])
        assert all(row["pearson_r"] is None and row["p_value"] is None for row in r["bivariate_associations"])


def test_factor_original_ols_hc3_holm_vif_has_independent_balanced_oracle(engine):
    import math
    from scipy.stats import norm
    from data_agent.tools.ml import attribution_analysis
    loop,_=engine;loop.context.workspace.add("orders",_factor_frame())
    r=json.loads(attribution_analysis(**_factor_args()));rows={v["feature"]:v for v in r["estimates"]}
    # Orthogonal balanced design: standardized beta=[2,3]/sqrt(14), HC3 variance=(16/13)^2/(16*14).
    se=1/(math.sqrt(16*14)*(1-3/16));critical=norm.ppf(.975)
    for col,beta in {"x":2/math.sqrt(14),"z":3/math.sqrt(14)}.items():
        assert rows[col]["coefficient"]==round(beta,8) and rows[col]["vif"]==1.
        assert rows[col]["confidence_interval_95"]==[round(beta-critical*se,8),round(beta+critical*se,8)]
        assert rows[col]["p_value"]==round(2*norm.sf(abs(beta/se)),8)
    assert rows["z"]["p_value_holm"]==round(min(1.,4*norm.sf(abs((3/math.sqrt(14))/se))),8)
    assert r["observation"]["source_rows"]==r["effective_n"]==16 and r["observation"]["excluded_rows"]==0


def test_factor_real_complete_cases_excluded_features_and_scope_metadata(engine):
    from data_agent.tools.ml import attribution_analysis
    loop,_=engine;frame=_factor_frame("scope");frame["constant"]=1.;frame["text"]="unknown";loop.context.workspace.add("orders",frame)
    r=json.loads(attribution_analysis(**dict(_factor_args(unit_col="unit",time_col="time"),features="x,z,constant,text")))
    assert r["excluded_features"]=={"constant":"constant_or_non_numeric","text":"constant_or_non_numeric"}
    assert r["observation"]["effective_rows"]==16
    assert r["unit_observation"]["missing_rows"]==1 and r["unit_observation"]["distinct_units"]==8 and r["unit_observation"]["repeated_units"]==7
    assert r["time_observation"]["missing_rows"]==1 and r["time_observation"]["invalid_rows"]==1 and r["time_observation"]["valid_rows"]==14 and r["time_observation"]["distinct_times"]==2
    assert r["time_observation"]["range"]==["2026-09-01T00:00:00","2026-09-02T00:00:00"]
    assert any("未按单位聚类" in v and "时间" in v for v in r["limitations"])


def test_factor_joint_exclusions_are_disclosed_without_changing_numeric_coercion(engine):
    from data_agent.tools.ml import attribution_analysis
    loop,_=engine;frame=_factor_frame();frame["z"]=frame.z.astype(object);frame.loc[0,"x"]=None;frame.loc[1,"amount"]=float("inf");frame.loc[2,"z"]="bad";loop.context.workspace.add("orders",frame)
    r=json.loads(attribution_analysis(**_factor_args()))
    assert r["observation"]["source_rows"]==16 and r["observation"]["effective_rows"]==13 and r["observation"]["excluded_rows"]==3
    assert r["observation"]["columns"]["x"]["missing_rows"]==1 and r["observation"]["columns"]["amount"]["nonfinite_rows"]==1 and r["observation"]["columns"]["z"]["non_numeric_rows"]==1
    assert r["completion_gaps"]


@pytest.mark.parametrize("fault",["coefficient","scope","parameters","ceiling","unit","pvalue"])
def test_factor_closed_adapter_rejects_forged_inference_scope_or_method(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",_factor_frame())
    rid,_=execute(loop,"attribution_analysis",_factor_args(unit_col="unit",time_col="time"));original=native.load_receipt_result
    def changed(**kw):
        context,receipt,r,binding=original(**kw);r=deepcopy(r)
        if fault=="coefficient":r["estimates"][0]["coefficient"]=999.
        elif fault=="scope":r.setdefault("observation",{})["effective_rows"]=999
        elif fault=="parameters":r["parameters"]["features"]=["amount"]
        elif fault=="ceiling":r["claim_ceiling"]="causal"
        elif fault=="unit":r.setdefault("unit_observation",{})["distinct_units"]=999
        else:r["estimates"][0]["p_value_holm"]=1.
        return context,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"features","unit","time","metric","kind"])
def test_factor_exact_public_plan_and_business_parameters(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",_factor_frame())
    params={"factor_features":["x","z"],"factor_unit_col":"unit","factor_time_col":"time","factor_output":"estimates"}
    if fault=="features":params["factor_features"]=["x"]
    if fault=="unit":params["factor_unit_col"]=""
    if fault=="time":params["factor_time_col"]=""
    spec={"kind":"fit" if fault=="kind" else "table","scope":{"datasets":["orders"],"metrics":["x" if fault=="metric" else "amount"],"parameters":params}}
    _s1_register(loop,"交付调整关联和方法边界",[spec])
    execute(loop,"attribution_analysis",_factor_args(unit_col="unit",time_col="time"))
    row=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert bool(row["gap"])==bool(fault),row



def test_factor_auto_features_and_original_ratio_identity_exclusion_remain_explicit(engine):
    from data_agent.tools.ml import attribution_analysis
    loop,_=engine;frame=_factor_frame();loop.context.workspace.add("orders",frame)
    r=json.loads(attribution_analysis("orders","amount",unit_col="unit",time_col="time"))
    assert r["parameters"]["features"]==["x","z","noise"] and r["parameters"]["target"]=="amount"
    assert len(r["bivariate_associations"])==3
    frame=pd.DataFrame({"events":[float(i*i+1) for i in range(1,17)],"users":[float(i) for i in range(1,17)]});frame["ratio"]=frame.events/frame.users
    loop.context.workspace.add("orders",frame)
    r=json.loads(attribution_analysis("orders","ratio",features="events,users"))
    assert r["excluded_features"]["events"]=="mathematical_identity_with_target" and r["completion_gaps"]
    assert r["observation"]["effective_rows"]==16 and r["observation"]["columns"]["events"]["used_for_filter"] is False


def test_factor_features_constant_after_joint_filter_do_not_create_nan_design(engine):
    from data_agent.tools.ml import attribution_analysis
    loop,_=engine;frame=_factor_frame();frame.loc[frame.x<0,"z"]=None;loop.context.workspace.add("orders",frame)
    r=json.loads(attribution_analysis(**_factor_args()),parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
    assert r["excluded_features"]["x"]=="constant_after_complete_case_filter"
    assert r["observation"]["effective_rows"]==8 and r["observation"]["excluded_rows"]==8
    assert all(row["feature"]!="x" for row in r["estimates"])



def _time_series_frame(case="linear"):
    frame=pd.DataFrame({"day":pd.date_range("2026-09-01",periods=30),"amount":[float(i) for i in range(1,31)]})
    if case=="zero":frame["amount"]=[0.]*15+[10.]*15
    if case=="constant":frame["amount"]=1.
    if case=="many":frame=pd.DataFrame({"day":pd.date_range("2026-09-01",periods=40),"amount":[float(i*i) for i in range(1,41)]})
    if case=="missing":
        frame["day"]=frame.day.astype(object);frame.loc[0,"day"]="bad";frame.loc[1,"amount"]=float("inf");frame.loc[2,"amount"]=None;frame.loc[3,"day"]=None
    if case=="irregular":frame=pd.DataFrame({"day":pd.to_datetime(["2026-09-01","2026-09-01","2026-09-10","2026-09-20"]),"amount":[1.,2.,3.,4.]})
    if case=="short":frame=frame.iloc[:2].copy()
    return frame


def _time_series_args(name="orders",**extra):return dict(name=name,date_col="day",value_col="amount",**extra)


@pytest.mark.parametrize("args",[{"date_col":"missing"},{"value_col":"missing"},{"value_col":"amount","target_col":"other"}])
def test_time_series_explicit_column_identity_and_alias_conflict_refuse(engine,args):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;frame=_time_series_frame();frame["other"]=2.;loop.context.workspace.add("orders",frame)
    kw=_time_series_args();kw.update(args);r=analyze_time_series(**kw)
    assert isinstance(r,str) and r.startswith("Error:"),r


def test_time_series_bad_numeric_is_explicit_error_without_silent_filter(engine):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;frame=_time_series_frame();frame["amount"]=frame.amount.astype(object);frame.loc[0,"amount"]="bad";loop.context.workspace.add("orders",frame)
    r=analyze_time_series(**_time_series_args());assert r.startswith("Error:"),r


def test_time_series_original_linear_index_slope_and_acf_are_not_seasonal_validation(engine):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;loop.context.workspace.add("orders",_time_series_frame())
    r=json.loads(analyze_time_series(**_time_series_args()))
    assert r["statistics"]=={"mean":15.5,"std":8.6554,"min":1.,"max":30.}
    assert r["trend"]["slope"]==1. and r["trend"]["axis"]=="sorted_observation_index"
    assert r["seasonality"]["threshold_exceeded"] is True and r["seasonality"]["seasonality_validated"] is False
    assert len(r["autocorrelation"])==15 and all(v["autocorrelation"]==1. for v in r["autocorrelation"])
    assert any("不证明季节性" in v for v in r["limitations"])


@pytest.mark.parametrize("case",["zero","many"])
def test_time_series_complete_windows_zero_percentage_unknown_and_original_absolute_change(engine,case):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;frame=_time_series_frame(case);loop.context.workspace.add("orders",frame)
    r=json.loads(analyze_time_series(**_time_series_args()));window=max(3,len(frame)//5)
    assert len(r["window_comparisons"])==len(frame)-2*window
    for row in r["window_comparisons"]:
        i=row["index"];before=sum(frame.amount.iloc[i-window:i])/window;after=sum(frame.amount.iloc[i:i+window])/window
        assert row["before_mean"]==pytest.approx(before) and row["after_mean"]==pytest.approx(after) and row["absolute_change"]==pytest.approx(after-before)
        if before:assert row["change_pct"]==round((after-before)/abs(before)*100,2)
    if case=="zero":
        mid=next(v for v in r["window_comparisons"] if v["index"]==15)
        assert mid["absolute_change"]==10. and mid["change_pct"] is None and mid["threshold_exceeded"] is None
    else:assert len(r["change_points"])==24 and {v["index"] for v in r["change_points"]}==set(range(8,32))


@pytest.mark.parametrize("case",["constant","short"])
def test_time_series_undefined_inference_and_acf_are_json_unknown(engine,case):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;loop.context.workspace.add("orders",_time_series_frame(case))
    r=json.loads(analyze_time_series(**_time_series_args()),parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
    assert r["trend"]["p_value"] is None and r["trend"]["significant"] is None
    assert r["seasonality"]["autocorrelation"] is None and r["seasonality"]["threshold_exceeded"] is None
    if case=="short":assert r["trend"]["slope"] is None


def test_time_series_joint_scope_excludes_only_invalid_dates_missing_or_nonfinite(engine):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;loop.context.workspace.add("orders",_time_series_frame("missing"))
    r=json.loads(analyze_time_series(**_time_series_args()))
    a=r["observation"];assert a["source_rows"]==30 and a["effective_rows"]==26 and a["excluded_rows"]==4
    assert [a[k] for k in ["missing_date","invalid_date","missing_value","nonfinite_value"]]==[1,1,1,1]
    assert r["status"]=="partial" and r["statistics"]["mean"]==17.5


def test_time_series_duplicate_dates_irregular_spacing_keep_per_record_axis(engine):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;loop.context.workspace.add("orders",_time_series_frame("irregular"))
    r=json.loads(analyze_time_series(**_time_series_args()))
    assert r["data_points"]==4 and r["trend"]["slope"]==1. and r["trend"]["axis"]=="sorted_observation_index"
    assert r["observation"]["duplicate_date_rows"]==1 and r["observation"]["unique_dates"]==3 and r["observation"]["equal_intervals"] is False


def test_time_series_auto_and_target_alias_disclose_actual_columns(engine):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;frame=_time_series_frame();frame["day"]=frame.day.astype(str);loop.context.workspace.add("orders",frame)
    r=json.loads(analyze_time_series("orders"));alias=json.loads(analyze_time_series("orders",date_col="day",target_col="amount"))
    assert r["parameters"]==alias["parameters"]=={"date_col":"day","value_col":"amount"}
    assert r["inferred_columns"]=={"date_col":"day","value_col":"amount"}


@pytest.mark.parametrize("fault",["statistics","slope","window","acf","observation","parameters"])
def test_time_series_closed_adapter_rejects_real_source_or_method_tampering(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",_time_series_frame())
    rid,_=execute(loop,"analyze_time_series",_time_series_args());original=native.load_receipt_result
    def changed(**kw):
        context,receipt,r,binding=original(**kw);r=deepcopy(r)
        if fault=="statistics":r["statistics"]["mean"]=999.
        elif fault=="slope":r["trend"]["slope"]=999.
        elif fault=="window":r["window_comparisons"][0]["absolute_change"]=999.
        elif fault=="acf":r["seasonality"]["seasonality_validated"]=True
        elif fault=="observation":r["observation"]["effective_rows"]=999
        else:r["parameters"]["value_col"]="other"
        return context,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"date","value","metric","kind"])
def test_time_series_exact_formal_business_parameters_and_product_kind(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",_time_series_frame())
    params={"time_series_date_col":"day","time_series_value_col":"amount","time_series_output":"statistics"}
    if fault=="date":params["time_series_date_col"]="missing"
    if fault=="value":params["time_series_value_col"]="other"
    spec={"kind":"fit" if fault=="kind" else "table","scope":{"datasets":["orders"],"metrics":["other" if fault=="metric" else "amount"],"parameters":params}}
    _s1_register(loop,"交付原时间序列统计和边界",[spec]);execute(loop,"analyze_time_series",_time_series_args())
    row=snapshot_for_turn(loop).as_dict()["requirements"][0];assert bool(row["gap"])==bool(fault),row


@pytest.mark.parametrize("value",[None,float("inf")])
def test_time_series_no_finite_observations_keeps_scope_and_unknown_descriptions(engine,value):
    from data_agent.tools.eda import analyze_time_series
    loop,_=engine;frame=pd.DataFrame({"day":pd.date_range("2026-09-01",periods=5),"amount":[value]*5});loop.context.workspace.add("orders",frame)
    r=json.loads(analyze_time_series(**_time_series_args()),parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
    assert r["observation"]["source_rows"]==r["observation"]["excluded_rows"]==5 and r["data_points"]==0
    assert all(v is None for v in r["statistics"].values()) and r["date_range"]=={"start":None,"end":None}
    assert r["trend"]["slope"] is None and r["status"]=="partial"


# Forecast 46/47: independent time/range/band oracles against the real producer.
def _forecast_frame(case="hourly"):
    import numpy as np
    f=pd.DataFrame({"day":pd.date_range("2026-09-01",periods=30,freq="h" if case=="hourly" else "D"),"amount":np.arange(1.,31.)})
    if case=="single":f["amount"]=np.arange(1.,31.)+5*np.sin(np.arange(30))
    if case=="missing":
        bad=pd.DataFrame({"day":[None,"bad",f.day.iloc[0],f.day.iloc[0],f.day.iloc[0]],"amount":[1.,2.,None,"bad",float("inf")]})
        f=pd.concat([f,bad],ignore_index=True)
    if case=="duplicates":f=pd.concat([f,f],ignore_index=True)
    if case=="short":f=f.iloc[:19].copy()
    if case=="irregular":f=f.drop(index=8).reset_index(drop=True)
    if case=="all_bad":f["amount"]=float("inf")
    return f


def _forecast_args(name="orders",case="hourly",**kwargs):return dict(name=name,date_col="day",target_col="amount",periods=1 if case=="single" else 3,**kwargs)


@pytest.mark.parametrize("method",["auto","backtest"])
def test_forecast_full_hourly_timestamps_and_original_candidate_predictions(engine,method):
    from data_agent.tools.ml import forecast
    loop,_=engine;loop.context.workspace.add("orders",_forecast_frame())
    r=json.loads(forecast(**_forecast_args(method=method)),parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
    assert [pd.Timestamp(x["date"]) for x in r["forecast"]]==list(pd.date_range("2026-09-02 06:00:00",periods=3,freq="h"))
    assert [x["yhat"] for x in r["forecast"]]==[31.,32.,33.]
    assert r["parameters"]["backtest_scheme"]=="ordered_holdout" and r["parameters"]["validation_points"]==3
    assert r["backtest"]["candidates_mae"]=={"naive_last_value":2.,"linear_trend":0.}
    assert r["interval"]["coverage_probability"] is None and r["interval"]["future_uncertainty_validated"] is False
    assert "未校准" in " ".join(r["limitations"])


def test_forecast_single_residual_keeps_point_but_never_zero_fills_band(engine):
    import numpy as np
    from data_agent.tools.ml import forecast
    loop,_=engine;f=_forecast_frame("single");loop.context.workspace.add("orders",f)
    r=json.loads(forecast(**_forecast_args(case="single")))
    assert r["forecast"][0]["yhat"]==round(float(f.amount.iloc[-1]),8)
    assert r["backtest"]["mae"]==round(abs(float(f.amount.iloc[-1]-f.amount.iloc[-2])),8)
    assert r["forecast"][0]["yhat_lower"] is r["forecast"][0]["yhat_upper"] is None
    assert r["interval"]["residual_count"]==1 and r["interval"]["residual_std"] is None
    assert r["completion_gaps"]


def test_forecast_original_residual_sample_sd_formula_without_coverage_grant(engine):
    import math,numpy as np
    from data_agent.tools.ml import forecast
    loop,_=engine;f=_forecast_frame("single");loop.context.workspace.add("orders",f)
    r=json.loads(forecast(**_forecast_args()));y=f.amount.to_numpy();train=y[:-3];actual=y[-3:]
    # Independent least squares arithmetic, no call to producer/polyfit.
    x=np.arange(len(train));slope=sum((x-x.mean())*(train-train.mean()))/sum((x-x.mean())**2);intercept=train.mean()-slope*x.mean()
    pred={"naive_last_value":np.repeat(train[-1],3),"linear_trend":intercept+slope*np.arange(27,30)}
    scores={k:sum(abs(actual-v))/3 for k,v in pred.items()};selected=min(scores,key=scores.get);res=actual-pred[selected];scale=math.sqrt(sum((res-res.mean())**2)/2)
    assert r["method"]==selected and r["interval"]["residual_std"]==pytest.approx(scale)
    for row in r["forecast"]:assert row["yhat_upper"]-row["yhat_lower"]==pytest.approx(2*1.96*scale,abs=2e-8)
    assert r["interval"]["method"]=="uncalibrated_residual_heuristic"


@pytest.mark.parametrize("case",["missing","duplicates","all_bad"])
def test_forecast_finite_scope_and_duplicate_sum_are_audited(engine,case):
    from data_agent.tools.ml import forecast
    loop,_=engine;loop.context.workspace.add("orders",_forecast_frame(case))
    r=json.loads(forecast(**_forecast_args()),parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)));o=r["observation"]
    assert o["source_rows"]=={"missing":35,"duplicates":60,"all_bad":30}[case]
    assert o["effective_rows"]=={"missing":30,"duplicates":60,"all_bad":0}[case]
    assert o["excluded_rows"]=={"missing":5,"duplicates":0,"all_bad":30}[case]
    assert o["time_points"]==(0 if case=="all_bad" else 30)
    if case=="missing":
        assert [o[k] for k in ["missing_date","invalid_date","missing_value","non_numeric_value","nonfinite_value"]]==[1,1,1,1,1]
        assert [x["yhat"] for x in r["forecast"]]==[31.,32.,33.] and r["completion_gaps"]
    if case=="duplicates":
        assert o["collapsed_duplicate_rows"]==o["duplicate_timestamp_groups"]==30
        assert all(x["input_rows"]==2 for x in o["timestamp_aggregation"])
        assert [x["yhat"] for x in r["forecast"]]==[62.,64.,66.]
    if case=="all_bad":assert r["status"]=="limited" and not r.get("forecast")


@pytest.mark.parametrize("case,reason",[("short","insufficient_time_points"),("irregular","missing_time_intervals")])
def test_forecast_rechecks_original_point_and_interval_preconditions_after_filter(engine,case,reason):
    from data_agent.tools.ml import forecast
    loop,_=engine;loop.context.workspace.add("orders",_forecast_frame(case));r=json.loads(forecast(**_forecast_args()))
    assert r["reason_code"]==reason and not r.get("forecast") and r["observation"]["time_points"]==len(_forecast_frame(case))


@pytest.mark.parametrize("fault",["date","value","score","band","scope","parameters"])
def test_forecast_closed_adapter_rejects_actual_source_and_method_tampering(engine,monkeypatch,fault):
    import copy
    from data_agent.agent.publication import native
    from data_agent.agent.publication.contracts import ContractError
    loop,_=engine;loop.context.workspace.add("orders",_forecast_frame());rid,_=execute(loop,"forecast",_forecast_args());original=native.load_receipt_result
    def altered(*a,**kw):
        context,receipt,r,binding=original(*a,**kw);r=copy.deepcopy(r)
        if fault=="date":r["forecast"][0]["date"]="2026-09-02"
        if fault=="value":r["forecast"][0]["yhat"]=999
        if fault=="score":r["backtest"]["mae"]=999
        if fault=="band":r["forecast"][0]["yhat_upper"]=999
        if fault=="scope":r["observation"]["source_rows"]=999
        if fault=="parameters":r["parameters"]["date_col"]="other"
        return context,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",altered)
    with pytest.raises(ContractError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"date","method","metric","kind"])
def test_forecast_exact_formal_parameters_and_selected_product(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",_forecast_frame());params={"forecast_periods":3,"forecast_date_col":"day","forecast_method":"auto","forecast_output":"forecast"}
    if fault=="date":params["forecast_date_col"]="other"
    if fault=="method":params["forecast_method"]="backtest"
    spec={"kind":"table" if fault=="kind" else "forecast","scope":{"datasets":["orders"],"metrics":["other" if fault=="metric" else "amount"],"parameters":params}}
    _s1_register(loop,"交付未来三小时点预测及未校准启发带",[spec]);execute(loop,"forecast",_forecast_args());snap=snapshot_for_turn(loop).as_dict();row=snap["requirements"][0]
    assert bool(row["gap"])==bool(fault),snap


@pytest.mark.parametrize("column",["date_col","target_col"])
def test_forecast_explicit_missing_columns_do_not_infer_replacement(engine,column):
    from data_agent.tools.ml import forecast
    loop,_=engine;loop.context.workspace.add("orders",_forecast_frame());args=_forecast_args();args[column]="missing"
    r=json.loads(forecast(**args));assert r["error_type"]=="forecast_failed" and not r.get("forecast")


def test_forecast_inferred_date_identity_and_zero_width_calculable_band(engine):
    from data_agent.tools.ml import forecast
    loop,_=engine;f=_forecast_frame();f["amount"]=4.;loop.context.workspace.add("orders",f)
    r=json.loads(forecast("orders","amount",periods=3))
    assert r["date_col"]==r["parameters"]["date_col"]=="day" and r["method"]=="naive_last_value"
    assert r["interval"]["residual_std"]==0. and r["interval"]["future_uncertainty_validated"] is False
    assert all(row["yhat"]==row["yhat_lower"]==row["yhat_upper"]==4. for row in r["forecast"])


@pytest.mark.parametrize("n,expected",[(20,"insufficient_time_points"),(30,"missing_time_intervals")])
def test_forecast_exclusion_rechecks_points_and_spacing_without_fill(engine,n,expected):
    from data_agent.tools.ml import forecast
    loop,_=engine;f=_forecast_frame().iloc[:n].copy();f.loc[8,"amount"]=float("inf");loop.context.workspace.add("orders",f)
    r=json.loads(forecast(**_forecast_args()));assert r["reason_code"]==expected and not r.get("forecast")
    assert r["observation"]["excluded_rows"]==1 and r["observation"]["time_points"]==n-1


# Period comparison 48: sums retain their real numerical inputs and scope.
def _periods_frame(case="regular"):
    f=pd.DataFrame({"day":pd.date_range("2026-09-01",periods=4),"amount":[10.,20.,30.,40.],"group":["A","B","A","B"]})
    if case=="missing":f.loc[0,"amount"]=None
    if case=="unknown":f.loc[:1,"amount"]=None
    if case=="nonfinite":f.loc[0,"amount"]=float("inf")
    if case=="zero":f.loc[:1,"amount"]=0.
    if case=="text":f["amount"]=["10","20","30","40"]
    if case=="invalid_date":f=pd.concat([f,pd.DataFrame({"day":["bad",None],"amount":[1000.,2000.],"group":["A","B"]})],ignore_index=True)
    if case=="new_group":f.loc[1,"group"]="A"
    return f


def _periods_args(name="orders",**kw):return dict(name=name,date_col="day",metrics="amount",period_a="2026-09-01~2026-09-02",period_b="2026-09-03~2026-09-04",**kw)


@pytest.mark.parametrize("fault",["text","missing_metric","duplicate_metric","missing_dimension","duplicate_dimension","missing_date"])
def test_periods_explicit_input_identity_refuses_silent_replacement_or_string_sum(engine,fault):
    from data_agent.tools.eda import compare_periods
    loop,_=engine;loop.context.workspace.add("orders",_periods_frame("text" if fault=="text" else "regular"));args=_periods_args()
    if fault=="missing_metric":args["metrics"]="amount,missing"
    if fault=="duplicate_metric":args["metrics"]="amount,amount"
    if fault=="missing_dimension":args["dimensions"]="missing"
    if fault=="duplicate_dimension":args["dimensions"]="group,group"
    if fault=="missing_date":args["date_col"]="missing"
    r=compare_periods(**args);assert r.startswith("Error:") or json.loads(r).get("error"),r


@pytest.mark.parametrize("case,a,b,d",[("regular",30.,70.,40.),("missing",20.,70.,50.),("nonfinite",20.,70.,50.),("unknown",None,70.,None),("zero",0.,70.,70.)])
def test_periods_original_sum_unknown_zero_and_per_period_finite_scope(engine,case,a,b,d):
    from data_agent.tools.eda import compare_periods
    loop,_=engine;loop.context.workspace.add("orders",_periods_frame(case));r=json.loads(compare_periods(**_periods_args()),parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
    item=r["metrics"]["amount"];assert item["exact_aggregates"]=={"period_a":a,"period_b":b,"diff":d}
    assert item["daily_avg_a"]==(None if a is None else a/2) and item["daily_avg_b"]==35.
    o=item["observation"];assert o["period_a"]["source_rows"]==2 and o["period_b"]["effective_rows"]==2
    assert o["period_a"]["effective_rows"]=={"regular":2,"missing":1,"nonfinite":1,"unknown":0,"zero":2}[case]
    if case in {"unknown","zero"}:assert item["change_pct"] is None
    if case in {"missing","nonfinite","unknown"}:assert item["completion_gaps"]


def test_periods_invalid_date_range_audit_is_not_silently_complete(engine):
    from data_agent.tools.eda import compare_periods
    loop,_=engine;loop.context.workspace.add("orders",_periods_frame("invalid_date"));r=json.loads(compare_periods(**_periods_args()))
    assert r["observation"]["source_rows"]==6 and r["observation"]["invalid_date"]==r["observation"]["missing_date"]==1
    assert r["observation"]["date_excluded_rows"]==2 and r["completion_gaps"]
    assert r["metrics"]["amount"]["exact_aggregates"]["diff"]==40.


def test_periods_new_group_has_unknown_absent_sum_and_real_counts(engine):
    from data_agent.tools.eda import compare_periods
    loop,_=engine;loop.context.workspace.add("orders",_periods_frame("new_group"));r=json.loads(compare_periods(**_periods_args(dimensions="group")))
    b=next(row for row in r["comparisons"] if row["dimension"]=="B")["amount"]
    assert b["exact_aggregates"]=={"a":None,"b":40.,"diff":None} and b["observation"]["a"]["effective_rows"]==0
    assert b["daily_avg_a"] is None and b["daily_avg_b"]==20.


@pytest.mark.parametrize("fault",["coherent_values","daily","scope","parameters"])
def test_periods_closed_adapter_rejects_coherent_but_false_actual_values(engine,monkeypatch,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("orders",_periods_frame());rid,_=execute(loop,"compare_periods",_periods_args());original=native.load_receipt_result
    def changed(**kw):
        ctx,receipt,r,binding=original(**kw);r=deepcopy(r)
        if fault=="coherent_values":
            item=r["metrics"]["amount"];item["exact_aggregates"].update(period_a=40.,diff=30.);item.update(period_a=40.,diff=30.,change_pct=75.,daily_avg_a=20.,daily_avg_diff=15.,daily_avg_change_pct=75.)
        if fault=="daily":r["metrics"]["amount"]["daily_avg_a"]=999
        if fault=="scope":r["period_a"]["rows"]=99
        if fault=="parameters":r.setdefault("parameters",{})["date_col"]="other"
        return ctx,receipt,r,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("fault",[None,"date","dimensions","formula","metric","kind"])
def test_periods_closed_plan_preserves_exact_scope_and_real_audit_product(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;loop.context.workspace.add("orders",_periods_frame());params={"comparison_date_col":"day","comparison_dimensions":[],"comparison_output":"comparison", "period_a":"2026-09-01~2026-09-02","period_b":"2026-09-03~2026-09-04"}
    if fault=="date":params["comparison_date_col"]="other"
    if fault=="dimensions":params["comparison_dimensions"]=["group"]
    if fault=="formula":params["comparison_formulas"]={"amount":{"operator":"ratio_of_sums","numerator":"amount","denominator":"other"}}
    spec={"kind":"fit" if fault=="kind" else "table","scope":{"datasets":["orders"],"metrics":["other" if fault=="metric" else "amount"],"parameters":params}}
    _s1_register(loop,"交付原两期比较和有效范围",[spec]);execute(loop,"compare_periods",_periods_args());row=snapshot_for_turn(loop).as_dict()["requirements"][0];assert bool(row["gap"])==bool(fault),row


@pytest.mark.parametrize("case",["unknown","nonfinite","missing"])
def test_periods_unknown_first_period_does_not_erase_or_downgrade_independent_known_second_period(engine,case):
    from data_agent.agent.publication.native import resolve_native_claims
    loop,_=engine;loop.context.workspace.add("orders",_periods_frame(case));rid,_=execute(loop,"compare_periods",_periods_args());claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    a=next(c for c in claims if c["basis_refs"][0]["result_path"]==["metrics","amount","exact_aggregates","period_a"])
    b=next(c for c in claims if c["basis_refs"][0]["result_path"]==["metrics","amount","exact_aggregates","period_b"])
    assert b["value"]==70. and not b["target"].get("completion_gap")
    assert a["target"].get("completion_gap")


import json
import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine

@pytest.mark.parametrize("tool",["quick_profile","assess_readiness"])
@pytest.mark.parametrize("case",["empty","infinite","unused_missing"])
def test_diagnostic_does_not_assert_method_readiness_or_block_independent_columns(engine,tool,case):
    from data_agent.tools.registry import registry
    loop,_=engine
    frame=pd.DataFrame({"amount":pd.Series(dtype="float64")}) if case=="empty" else pd.DataFrame({"amount":[1.,float("inf"),3.]}) if case=="infinite" else pd.DataFrame({"amount":[10.,20.,30.],"unused":[None]*3})
    loop.context.workspace.add("orders",frame)
    result=json.loads(registry.execute(tool,{"name":"orders"}).summary)
    assert result["readiness" if tool=="quick_profile" else "overall"]==("blocked" if case=="empty" else "ready_with_warnings"),result
    assert result["method_preconditions_verified"] is False
    if case=="infinite":assert result["column_diagnostics"]["amount"]["nonfinite_count"]==1
    if case=="unused_missing":assert result["column_diagnostics"]["unused"]["missing_count"]==3


def test_quick_profile_same_shape_new_version_does_not_reuse_old_missingness(engine):
    from data_agent.tools.registry import registry
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,2.,3.]}))
    first=json.loads(registry.execute("quick_profile",{"name":"orders"}).summary)
    loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,None,None]}))
    second=json.loads(registry.execute("quick_profile",{"name":"orders"}).summary)
    assert second["columns"][0]["missing_pct"]==pytest.approx(66.67)
    assert second!=first


@pytest.mark.parametrize("compact",[False,True])
def test_quick_profile_quality_counts_all_missing_columns_not_only_threshold_failures(engine,compact):
    from data_agent.tools.registry import registry
    loop,_=engine;loop.context.workspace.add("orders",pd.DataFrame({"amount":[1.,2.,3.,None]}))
    result=json.loads(registry.execute("quick_profile",{"name":"orders","compact":compact}).summary)
    assert result["quality"]["missing"]==1,result


@pytest.mark.parametrize("tool,compact",[("quick_profile",False),("quick_profile",True),("assess_readiness",False)])
@pytest.mark.parametrize("fault",[None,"parameter","output"])
def test_diagnostic_closed_plan_preserves_actual_parameters_and_output(engine,tool,compact,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine
    params={"profile_compact":compact} if tool=="quick_profile" else {"readiness_intent":"classification"}
    args={"name":"orders",**({"compact":compact} if tool=="quick_profile" else {"intent":"classification"})}
    if fault=="parameter":params.update(profile_compact=not compact) if tool=="quick_profile" else params.update(readiness_intent="forecast")
    params["diagnostic_output"]="overall" if tool=="quick_profile" and fault=="output" else "readiness" if tool=="assess_readiness" and fault=="output" else "column_diagnostics"
    _s1_register(loop,"报告实际列级诊断，不验证方法前提",[{"kind":"table","scope":{"datasets":["orders"],"parameters":params}}])
    execute(loop,tool,args);row=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert bool(row["gap"])==bool(fault),row


@pytest.mark.parametrize("tool",["quick_profile","assess_readiness"])
@pytest.mark.parametrize("fault",["counts","readiness","method"])
def test_diagnostic_closed_source_guard_rejects_forged_counts_or_method_validation(engine,monkeypatch,tool,fault):
    from copy import deepcopy
    from data_agent.agent.publication import native
    loop,_=engine;rid,_=execute(loop,tool,{"name":"orders"});original=native.load_receipt_result
    def changed(**kw):
        ctx,receipt,result,binding=original(**kw);result=deepcopy(result)
        if fault=="counts":result["column_diagnostics"]["amount"]["missing_count"]=99
        if fault=="readiness":result["readiness" if tool=="quick_profile" else "overall"]="blocked"
        if fault=="method":result["method_preconditions_verified"]=True
        return ctx,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError,match="实际数据"):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("output",["comparison","observation"])
def test_explicitly_requested_period_audit_table_is_not_deferred_by_model_projection(engine,output):
    from data_agent.agent.publication.runtime import snapshot_for_turn,model_publication_context
    loop,_=engine;loop.context.workspace.add("orders",_periods_frame("invalid_date"))
    params={"comparison_date_col":"day","comparison_dimensions":[],"comparison_output":output,"period_a":"2026-09-01~2026-09-02","period_b":"2026-09-03~2026-09-04"}
    _s1_register(loop,"交付完整审计表和真实范围",[{"kind":"table","scope":{"datasets":["orders"],"metrics":["amount"],"parameters":params}}])
    execute(loop,"compare_periods",_periods_args());snapshot=snapshot_for_turn(loop);host=snapshot.as_dict()
    view=model_publication_context(snapshot,loop.context.analysis_state,budget=1000000,soft_budget=1)
    required={cid for req in host["requirements"] for cid in req["claim_ids"]}
    assert required and required.issubset({row[0] for row in view["claims"]})
    original={c["id"]:c for c in host["claims"]}
    for row in view["claims"]:
        item=dict(zip(view["claim_fields"],row));assert item["value"]==original[item["id"]]["value"]
        assert view["catalog_context"]["limitations"][item["limitations_ref"]]==original[item["id"]]["limitations"]
    assert not required.intersection(cid for d in view["deferred_details"] for cid in d["claim_ids"])
    assert snapshot.as_dict()==host


def test_large_requested_table_expands_past_64k_tokens_and_hard_limit_never_truncates_rows(engine,monkeypatch):
    from data_agent.agent.publication.runtime import snapshot_for_turn,model_publication_context
    from data_agent.llm.request_policy import count_request_tokens
    from data_agent.agent.publication.contracts import encode
    loop,cfg=engine
    frame=pd.DataFrame({"amount":range(3000),"label":["字段"*30+str(i) for i in range(3000)]})
    loop.context.workspace.add("orders",frame)
    params={"topn_sort_by":"amount","topn_ascending":False,"topn_n":3000,"topn_columns":["amount","label"],"topn_output":"records"}
    _s1_register(loop,"完整交付3000条原值，不截断",[{"kind":"table","scope":{"datasets":["orders"],"metrics":["amount","label"],"parameters":params}}])
    execute(loop,"top_n",{"name":"orders","n":3000});snapshot=snapshot_for_turn(loop);before=snapshot.as_dict()
    view=model_publication_context(snapshot,loop.context.analysis_state,budget=164000,soft_budget=65536)
    assert not view.get("model_view_issue") and view["model_view_budget"]["expanded_past_soft_target"]
    assert count_request_tokens(cfg.model_id,[{"role":"system","content":encode(view)}],tokenizer_path=cfg.model_tokenizer)["tokens"]>65536
    values=[dict(zip(view["claim_fields"],r))["value"] for r in view["claims"]]
    records=next(v for v in values if isinstance(v,list))
    assert records==[{"amount":i,"label":"字段"*30+str(i)} for i in reversed(range(3000))]
    tiny=model_publication_context(snapshot,loop.context.analysis_state,budget=100,soft_budget=65536)
    assert tiny["model_view_issue"]["code"]=="publication_context_size" and snapshot.as_dict()==before


def test_explanation_context_keeps_nonowned_source_claims_and_all_limits(engine):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.runtime import snapshot_for_turn,model_publication_context
    loop,_=engine
    request(loop,"报告当前合计并解释",{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"sum"}},purposes=["interpretation"])
    execute(loop,"describe_dataset",{"name":"orders"});snapshot=snapshot_for_turn(loop);host=snapshot.as_dict()
    view=model_publication_context(snapshot,loop.context.analysis_state,budget=1000000)
    needed=set(host["requirements"][0]["context_claim_ids"])
    assert needed-set(host["requirements"][0]["claim_ids"])
    assert needed.issubset({row[0] for row in view["claims"]})
    by_id={c["id"]:c for c in host["claims"]}
    for row in view["claims"]:
        packed=dict(zip(view["claim_fields"],row))
        assert packed["value"]==by_id[packed["id"]]["value"]
        assert view["catalog_context"]["limitations"][packed["limitations_ref"]]==by_id[packed["id"]]["limitations"]


@pytest.mark.parametrize('resolved',['steps','aggregate','rates'])
def test_funnel_auto_dispatch_keeps_each_original_numeric_method_and_current_receipt(engine,resolved):
    loop,_=engine
    if resolved=='steps':
        frame=pd.DataFrame(dict(uid=['u1','u2','u1'],event=['A','A','B']));args=dict(user_col='uid',event_col='event',steps='A,B');expected=.5
    elif resolved=='aggregate':
        frame=pd.DataFrame(dict(step=['A','B'],count=[20,5]));args=dict(step_col='step',count_col='count',steps='A,B');expected=.25
    else:
        frame=pd.DataFrame(dict(a_rate=[1.,1.],b_rate=[.2,.3]));args=dict(rate_cols='a_rate,b_rate');expected=.25
    loop.context.workspace.add('orders',frame);rid,result=execute(loop,'funnel_analysis',dict(name='orders',mode='auto',**args))
    assert result['mode']==resolved and result['parameters']['mode']==resolved and result['overall_conversion']==expected
    from data_agent.agent.publication.native import resolve_native_claims
    original=next(c for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid) if c['basis_refs'][0]['result_path']==['overall_conversion'])
    assert original['value']==expected and original['basis_refs'][0]['data_identities']['orders']==loop.context.workspace.get_data_identity('orders')
