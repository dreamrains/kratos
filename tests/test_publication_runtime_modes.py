from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: modes. Shared fixtures have one owner."""
from copy import deepcopy
from data_agent.agent.publication.contracts import encode
from tests.test_trusted_publication_semantics import execute
from types import SimpleNamespace
import hashlib
import json
import pytest
from tests.support.publication_runtime import _NativeProductModel, draft, request

@pytest.mark.parametrize("fault", [None, "duplicate", "too_many", "foreign", "single_legacy_payload"])
def test_recorded_m03_bounded_delivery_collection_closes_each_actual_chart(engine, monkeypatch, fault):
    from copy import deepcopy
    from io import StringIO
    from pathlib import Path
    import pandas as pd
    import plotly.graph_objects as go
    from data_agent.agent.publication.requirements import record_execution_targets
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.session.history import load_canonical_history
    from data_agent.agent.publication.service import PublicationService
    monkeypatch.setattr(go.Figure, "to_image", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline static unavailable")))
    loop, _ = engine
    material = json.loads(Path("tests/fixtures/p5-contract-reset-20261009.json").read_text(encoding="utf-8"))["m03_delivery_collection"]
    for item in material["files"]:
        loop.context.workspace.add(item["dataset"], pd.read_csv(StringIO(item["csv"])))
    periods={"period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"}
    specs=[{"kind":kind,"scope":{"datasets":[x["dataset"]],**({**({"metrics":["amount"]} if q!="rows" else {}),"quantity":q,**({"parameters":periods} if q in {"sum","difference"} else {})} if q else {})}} for x in material["files"] for kind,q in [("chart",None),("measurement","difference"),("measurement","sum"),("measurement","rows")]]
    request(loop,material["prompts"][0],specs)
    state=loop.context.analysis_state;rid=state.answer_requirements[0]["id"]
    if fault:
        from data_agent.agent.analysis_plan_contracts import validate_analysis_plan_contract
        raw=deepcopy(state.analysis_plan);items=raw["method_plan"][0]["required_deliveries"]
        if fault=="duplicate":items.append(deepcopy(items[0]))
        if fault=="too_many":raw["method_plan"][0]["required_deliveries"]=items+[deepcopy(items[0])]*33
        if fault=="foreign":items[0]["scope"]["datasets"]=["foreign_session"];items[0].pop("id")
        before=deepcopy(state.answer_requirements)
        if fault=="single_legacy_payload":
            with pytest.raises(ValueError):record_execution_targets(state,load_canonical_history(loop.session_id),loop.context.workspace,{"requirement_revision":state.requirement_revision,"targets":[{"requirement_id":rid,"selector":{"dataset":"M03-source-1","tool":"create_chart"}}]})
        else:
            assert not validate_analysis_plan_contract(raw,answer_requirements=state.answer_requirements,requirement_revision=state.requirement_revision).ok
        assert state.answer_requirements==before
        return
    for item in material["files"]:
        execute(loop,"compare_periods",{"name":item["dataset"],"date_col":"date","metrics":"amount",**periods})
        execute(loop,"describe_dataset",{"name":item["dataset"]})
    for index, item in enumerate(material["files"]):
        execute(loop, "create_chart", {"data": item["dataset"], "chart_type": "line", "x_col": "date", "y_col": "amount", "purpose": "exploratory"})
        snap = snapshot_for_turn(loop); host = snap.as_dict(); req = next(r for r in host["requirements"] if r["id"] == rid)
        assert len(req["artifact_ids"]) == index + 1
        assert bool(req["gap"]) == (index < 5)
    from tests.test_trusted_publication_pipeline import accept_all
    from data_agent.agent.publication.audit import MAX_AUDIT_BYTES
    calls=[]
    def audit(payload):
        calls.append(payload)
        Path(engine[1].workspace_resolved.parent,"m03-audit-request.json").write_text(encode(payload),encoding="utf-8")
        assert len(encode(payload).encode("utf-8"))<=MAX_AUDIT_BYTES
        return accept_all(payload)
    host=snap.as_dict();req=host["requirements"][0]
    raw=encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":[rid],"parts":[
        {"kind":"text","purpose":"interpretation","text":"逐来源比较当前两日观测，不作跨源合计或因果外推。","claim_refs":req["claim_ids"]}]}]})
    answer=PublicationService(snap,auditor=audit).publish(raw).as_dict()
    assert len(calls)==1 and answer["audit_status"]=="reviewed"
    assert len(calls[0]["claims"])==len(req["claim_ids"])<len(host["claims"])
    assert answer["source_snapshot"]["claims"]==host["claims"]
    for item in material["files"]:
        frame=pd.read_csv(StringIO(item["csv"]))
        bound=[c for c in host["claims"] if c["id"] in req["claim_ids"] and c["scope"]["dataset"]==item["dataset"]]
        assert next(c["value"] for c in bound if c["label"]=="记录数")==len(frame)
        for suffix,date in (("前期","2026-09-01"),("后期","2026-09-02")):
            assert next(c["value"] for c in bound if c["label"]=="amount："+suffix)==frame.loc[frame["date"]==date,"amount"].sum()
    assert len(answer["artifact_refs"]) == 6 and answer["requirement_outcomes"][0]["status"] == "answered"
    assert {a["target"]["dataset"] for a in answer["artifact_refs"]} == {x["dataset"] for x in material["files"]}


@pytest.mark.parametrize("scope", ["current", "other_dataset", "wrong_window"])
def test_current_explanation_permission_cannot_complete_a_missing_goal(engine, scope):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.service import PublicationService
    import pandas as pd
    loop, _ = engine
    bounds={"datasets":["orders"],"metrics":["amount"]}
    if scope=="wrong_window":bounds["parameters"]={"period_a":"2026-09-01~2026-09-06"}
    request(loop,"请评估预测缺口并解释当前观察",{"kind":"forecast","scope":bounds})
    name = "orders"
    if scope == "other_dataset":
        name = "other"; loop.context.workspace.add(name, pd.DataFrame({"amount": [999]}))
    execute(loop, "describe_dataset", {"name": name})
    snap = snapshot_for_turn(loop); host = snap.as_dict(); req = host["requirements"][0]
    row = next(c for c in host["claims"] if c["label"] == "记录数")
    assert not req["claim_ids"] and req["gap"]
    assert (row["id"] in req["context_claim_ids"]) == (scope == "current")
    calls = []
    def audit(payload):
        calls.append(payload)
        return {"schema": "publication_audit.v2", "snapshot_digest": payload["snapshot_digest"], "draft_digest": payload["draft_digest"], "decisions": [
            {"part_id": p["part_id"], "disposition": "accept", "reason": "当前观察可解释缺口，不能授权预测", "evidence_refs": p["claim_refs"]} for p in payload["parts"]]}
    raw = encode({"schema": "answer_bindings.v2", "snapshot_digest": snap.digest, "sections": [{"requirement_ids": [req["id"]], "parts": [
        {"kind": "text", "purpose": "interpretation", "text": "当前观察只描述样本；预测仍未计算。", "claim_refs": [row["id"]]}]}]})
    answer = PublicationService(snap, auditor=audit).publish(raw).as_dict()
    assert all(r["status"] != "answered" for r in answer["requirement_outcomes"])
    assert not any(t["kind"] == "claim" and t["disposition"] == "accepted" for t in answer["render_trace"])
    if scope == "current":
        assert len(calls) == 1 and "当前观察只描述样本" in answer["body"]
        assert answer["requirement_outcomes"][0]["status"] == "partial"
        assert calls[0]["claims"][0]["value"] == 12
    else:
        assert not calls and "当前观察只描述样本" not in answer["body"]


@pytest.mark.parametrize("purpose", ["knowledge", "interpretation", "limitation", "conditional_action"])
def test_pure_consultation_can_deliver_professional_roles_without_data_execution(engine, purpose):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.service import PublicationService
    loop, _ = engine
    request(loop, "请说明如何设计促销分析方案及其限制", kind="knowledge")
    snap = snapshot_for_turn(loop); req = snap.as_dict()["requirements"][0]
    raw = encode({"schema": "answer_bindings.v2", "snapshot_digest": snap.digest, "sections": [{"requirement_ids": [req["id"]], "parts": [
        {"kind": "text", "purpose": purpose, "text": "可先明确分析单位与可用数据；观察关联不证明因果。", "claim_refs": []}]}]})
    answer = PublicationService(snap, auditor=lambda _: pytest.fail("pure consultation has no review call")).publish(raw).as_dict()
    assert answer["requirement_outcomes"][0]["status"] == "answered"
    assert "明确分析单位" in answer["body"] and answer["audit_status"] == "not_applicable"


@pytest.mark.parametrize("fault", [None, "unconfirmed", "changed_root", "overwritten_input", "filtered_parent", "stale_prior_derive"])
def test_recorded_m06_derived_formula_proves_original_columns_in_synthesis(engine, fault):
    from io import StringIO
    from pathlib import Path
    import pandas as pd
    from data_agent.agent.confirmation.runtime import build_action_registry, build_measurement_mapping_candidate
    from data_agent.agent.confirmation.service import ConfirmationService
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.service import PublicationService
    from data_agent.session.history import load_canonical_history
    from tests.test_scoped_workspace import _stage3c0b_task
    from data_agent.session.task_manager import task_manager
    loop, cfg = engine
    material = json.loads(Path("tests/fixtures/p5-contract-reset-20261009.json").read_text(encoding="utf-8"))["m06_derived_formula"]
    if fault == "stale_prior_derive":
        older = pd.read_csv(StringIO(material["csv"]))
        older.loc[0,"incremental_revenue"] = 999
        loop.context.workspace.add("m06_promo",older)
        request(loop,"旧版派生",{'kind':'measurement','scope':{'datasets':['m06_promo'],'metrics':['账面净收益'],'quantity':'value'}})
        execute(loop,"derive_field",{"name":"m06_promo","field_name":"older_net","expression":"incremental_revenue - coupon_cost - channel_cost"})
    loop.context.workspace.add("m06_promo", pd.read_csv(StringIO(material["csv"])))
    request(loop, material["user_input"], {'kind': 'measurement', 'scope': {'datasets': ['m06_promo'], 'metrics': ['账面净收益'], 'quantity': 'value'}})
    history = load_canonical_history(loop.session_id)
    candidate = build_measurement_mapping_candidate(session_id=loop.session_id, turn_id="runtime_turn", workspace=loop.context.workspace, canonical_history=history,
        source_message_ref=history.messages[-1]["request_id"], exact_span="账面净收益", dataset="m06_promo", column="incremental_revenue", cost_scopes=[["coupon_cost"], ["coupon_cost", "channel_cost"]])
    assert candidate is not None
    service = ConfirmationService(cfg.sessions_resolved, action_registry=build_action_registry())
    service.request(candidate); record = service.checkpoint(loop.session_id)
    service.respond(loop.session_id, record.confirmation_id, "unconfirmed" if fault == "unconfirmed" else candidate.options[1].value, record.version, "offline_recorded_formula")
    derive, aggregate = deepcopy(material["steps"])
    if fault == "overwritten_input":
        derive["arguments"].update(field_name="coupon_cost", expression="coupon_cost + 100")
        aggregate["arguments"]["name"] = "m06_promo_coupon_cost"
        aggregate["arguments"]["aggregations"] = aggregate["arguments"]["aggregations"][:3]
    if fault == "filtered_parent":
        loop.context.workspace.derive("m06_promo", "filtered", loop.context.workspace.get("m06_promo").iloc[:1], "filter")
        derive["arguments"]["name"] = "filtered"
        aggregate["arguments"]["name"] = "filtered_net_book_profit"
    execute(loop, derive["tool"], derive["arguments"])
    execute(loop, aggregate["tool"], aggregate["arguments"])
    if fault == "changed_root":
        loop.context.workspace.add("m06_promo", pd.DataFrame({"incremental_revenue": [999], "coupon_cost": [14], "channel_cost": [10]}))
    _stage3c0b_task(task_manager, session_id=loop.session_id, datasets=["m06_promo", aggregate["arguments"]["name"]], mode="synthesis")
    assert loop.context.refresh_workspace_scope().phase == "synthesis"
    assert loop.context.workspace.list_datasets() == {} and loop.context.workspace.get("m06_promo") is None
    snap = snapshot_for_turn(loop); host = snap.as_dict()
    facts = [c for c in host["claims"] if c.get("target", {}).get("statistic") == "accounting_net"]
    answer = PublicationService(snap).publish('{}').as_dict()
    if fault and fault != "stale_prior_derive":
        assert not facts and answer["requirement_outcomes"][0]["status"] != "answered"
    else:
        assert len(facts) == 1 and facts[0]["value"] == "86"
        assert facts[0]["unit"] is None and "因果" in " ".join(facts[0]["limitations"])
        assert {p["tool_name"] for p in facts[0]["basis_refs"]} == {"derive_field", "transform_data"}
        assert any(facts[0]["id"] in r["claim_ids"] for r in host["requirements"])
        assert facts[0]["derivation"]["confirmation_id"] == candidate.confirmation_id
        assert any(r["status"] == "answered" for r in answer["requirement_outcomes"]) and "86" in answer["body"]
    assert loop.context.workspace.list_datasets() == {}


@pytest.mark.parametrize("fault", [None, "implicit_daily_sum", "invalid_formula", "zero_denominator", "missing_operand", "tampered_ratio"])
def test_recorded_m01_window_cost_per_order_is_a_ratio_of_original_sums(engine, fault):
    from pathlib import Path
    from io import StringIO
    import pandas as pd
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.native import resolve_native_claims
    from data_agent.agent.publication.service import PublicationService
    loop, cfg = engine
    material = json.loads(Path("tests/fixtures/p5-contract-reset-20261009.json").read_text(encoding="utf-8"))["m01_window_ratio"]
    data = pd.read_csv(StringIO(material["csv"]))
    first = data.date < "2026-09-14"
    if fault == "zero_denominator": data.loc[first, "orders"] = 0
    if fault == "missing_operand": data.loc[data.index[0], "campaign_cost"] = float("nan")
    loop.context.workspace.add("M01-action", data)
    derive, comparison = deepcopy(material["steps"])
    request(loop, "比较两期窗口成本每单", {'kind': 'measurement', 'scope': {'datasets': ['M01-action'], 'metrics': ['cost_per_order'], 'quantity': 'ratio_of_sums'}})
    execute(loop, derive["tool"], derive["arguments"])
    args = comparison["arguments"]
    if fault != "implicit_daily_sum": args["metric_formulas"] = deepcopy(material["corrected_formula"])
    if fault == "invalid_formula": args["metric_formulas"]["cost_per_order"]["denominator"] = "invented"
    if fault in {"implicit_daily_sum", "invalid_formula"}:
        result = json.loads(registry.execute("compare_periods", args).summary)
        assert result["error_type"] == ("non_additive_metric_requires_formula" if fault == "implicit_daily_sum" else "invalid_metric_formula")
        return
    rid, result = execute(loop, "compare_periods", args)
    measured = result["metrics"]["cost_per_order"]
    assert "daily_avg_a" not in measured
    if fault == "tampered_ratio":
        measured["exact_aggregates"]["period_a"] = 14
        receipt = next(r for r in loop.context.analysis_state.tool_receipts if r["id"] == rid)
        path = cfg.sessions_resolved / loop.session_id / receipt["detail_ref"]["path"]
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        receipt["detail_ref"]["sha256"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        receipt["structured_result_sha256"] = "sha256:" + hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        with pytest.raises(ValueError, match="分子合计"): resolve_native_claims(session_id=loop.session_id, receipt_id=rid)
        return
    snap = snapshot_for_turn(loop); host = snap.as_dict()
    facts = [c for c in host["claims"] if c.get("target", {}).get("statistic") == "ratio_of_sums"]
    values = {c["label"]: c["value"] for c in facts}
    assert values["cost_per_order：后期"] == pytest.approx(25 / 11)
    assert values["cost_per_order：前期"] == (None if fault else 2)
    assert all(c["unit"] is None for c in facts)
    answer = PublicationService(snap).publish('{}').as_dict()
    if fault:
        assert answer["requirement_outcomes"][0]["status"] == "partial"
        assert "未知" in answer["body"] and "分母为零或原列合计缺失" in answer["body"]
    else:
        assert answer["requirement_outcomes"][0]["status"] == "answered"
        assert measured["aggregation"]["operand_sums"]["period_b"] == {"numerator": 175, "denominator": 77}
        assert values["cost_per_order：差值"] == pytest.approx(3 / 11)


@pytest.mark.parametrize("version",["v1","v2"])
def test_original_m04_rules_preserve_each_unmeasured_competitor_and_current_direction(engine,version):
    import io
    import pandas as pd
    from pathlib import Path
    from data_agent.agent.hypotheses import persist_hypothesis_set
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine
    material=next(m for m in json.loads(Path("tests/fixtures/p5-contract-reset-20261009.json").read_text(encoding="utf-8"))["m04_competing_hypotheses"] if m["version"]==version)
    assert hashlib.sha256(material["csv"].encode("utf-8")).hexdigest()==material["csv_sha256"]
    name=material["dataset"]
    loop.context.workspace.add(name,pd.read_csv(io.StringIO(material["csv"])))
    hypothesis_set=deepcopy(material["original_hypotheses"])
    plan_id="offline-"+version
    hypothesis_set["id"]="offline-hypotheses-"+version
    hypothesis_set["plan_id"]=plan_id
    request(loop,"逐项检验当前四个竞争假设",[{"kind":"hypothesis","scope":{"datasets":[name],"hypothesis_ids":[h["id"]]}} for h in hypothesis_set["hypotheses"]])
    loop.context.analysis_state.analysis_plan["id"]=plan_id
    rid,_=execute(loop,"analyze_time_series",{"name":name,"date_col":"date","value_col":"amount"})
    receipt=loop.context.analysis_state.tool_receipts[-1]
    record={"id":"offline-evidence-"+version,"plan_id":plan_id,"dataset":name,"claim":"current trend",
        "tool_receipt_ids":[rid],"result_bindings":[{"receipt_id":rid,"result_sha256":receipt["structured_result_sha256"],"data_identities":receipt["data_identities"]}]}
    loop.context.analysis_state.evidence_records.append(record)
    loop.context.analysis_state.add_hypothesis_set_ref(persist_hypothesis_set(loop.session_id,hypothesis_set))
    snap=snapshot_for_turn(loop)
    host=snap.as_dict();req=host["requirements"][-1]
    matched=[c for c in host["claims"] if c["id"] in req["claim_ids"]]
    assert len(matched)==1 and matched[0]["value"]==("supported" if version=="v1" else "refuted")
    assert req["gap"]["status"]=="evidence_insufficient"
    missing=[h["id"] for h in hypothesis_set["hypotheses"][1:]]
    assert all(hid in req["gap"]["reason"] for hid in missing)
    body,error=publish(loop,encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[]}))
    assert error is None and all(hid in body for hid in missing)
    assert loop._accepted_answer["requirement_outcomes"][-1]["status"]=="partial"
    assert all(hid in loop._accepted_answer["requirement_outcomes"][-1]["reason"] for hid in missing)
    assert len(loop.context.analysis_state.hypothesis_sets)==1


def test_original_six_reuse_operations_pass_actual_request_registration(engine):
    from pathlib import Path
    from data_agent.agent.llm_intent import classify_intent_llm
    from data_agent.agent.publication.runtime import register_request
    from data_agent.agent.publication.requirements import update_requirements
    from data_agent.session.history import save_session,load_canonical_history
    archived=json.loads((Path(__file__).parent/"fixtures/p5-reuse-20261009.json").read_text(encoding="utf-8"))
    client=SimpleNamespace(manages_request_timeout=True,chat=lambda *a,**k:SimpleNamespace(text=archived["visible_json"]))
    parsed=classify_intent_llm(archived["input"],"",client=client)
    loop,_=engine;state=loop.context.analysis_state
    loop.messages=[{"role":"user","content":"abcdef","request_id":"original"}]
    save_session(loop.messages,loop.session_id,merge_protect=False)
    ids=update_requirements(state,load_canonical_history(loop.session_id),"original",[
        {"op":"add","start":i,"end":i+1,"kind":row["kind"]} for i,row in enumerate(parsed["requested_outputs"])],expected_revision=0)
    for req,row in zip(state.answer_requirements,parsed["requested_outputs"]):req["id"]=row["target_id"]
    loop.messages.extend([{"role":"assistant","content":"history","answer_ref":{"answer_id":"prior"}},{"role":"user","content":archived["input"],"request_id":"continue"}])
    loop._last_jsonl_idx=0
    register_request(loop,archived["input"],SimpleNamespace(**parsed))
    assert len(loop.context.turn_requirement_ids)==6
    assert all(len(r["continuation_refs"])==1 for r in state.answer_requirements)
    assert all("source_answer_id" not in r for r in state.answer_requirements)


@pytest.mark.parametrize("fault",["none","missing","conflict","unknown","tampered"])
def test_python_business_parameters_bind_before_execution_without_method_authority(engine,fault):
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.native import resolve_native_claims
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine
    request(loop,"计算当前7日窗口金额",{'kind':'measurement','scope':{'datasets':['orders'],'metrics':['income'],'quantity':'value','parameters':{'window_days':7}}})
    args={'code':"df=get_dataset('orders'); result={'income':float(df.iloc[:7]['amount'].sum())}"}
    if fault!='missing':args['business_parameters']={'window_days':30 if fault=='conflict' else 7}
    if fault=='unknown':args['business_parameters']['result_path']='invented'
    if fault in {'conflict','unknown'}:
        result=registry.execute('run_python',args)
        assert result.data['error_type']=='sandbox_business_parameters'
        assert not loop.context.analysis_state.tool_receipts
        return
    rid,result=execute(loop,'run_python',args)
    assert result['dataset_reads']==['orders'] and result['result_data']['income']==80
    if fault=='tampered':
        result['business_parameters']={'window_days':30};_tamper(loop,cfg,rid,result)
        with pytest.raises(ValueError,match='参数'):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    if fault=='none':
        req=snap.as_dict()['requirements'][0]
        assert len(req['claim_ids'])==1
        claim=next(c for c in snap.as_dict()['claims'] if c['id']==req['claim_ids'][0])
        assert claim['value']==80 and claim['target']['parameters']['window_days']==7
        assert '不证明方法正确或预测有效' in body
        assert loop._accepted_answer['requirement_outcomes'][0]['status']=='answered'
    else:
        assert not snap.as_dict()['requirements'][0]['claim_ids']
        assert loop._accepted_answer['requirement_outcomes'][0]['status'] in {'not_computed','evidence_insufficient'}


@pytest.mark.parametrize("charts", [False, True])
def test_complete_six_source_declared_products_fit_model_view_without_repeated_step_ids(engine, charts):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient, RunTrace, _write_fixtures
    from data_agent.agent.publication.runtime import snapshot_for_turn, model_publication_context
    from data_agent.agent.publication.deliveries import project_deliveries
    from data_agent.agent.publication.contracts import encode
    loop, cfg = engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True, exist_ok=True)
    _write_fixtures(cfg.workspace_resolved.parent)
    client = ScriptedClient(RunTrace(cfg.workspace_resolved.parent))
    loop.client = client; loop.auxiliary_llm_client = client
    marker = "B03-CHART" if charts else "B03"
    text = "分别比较六个来源的两个观测日（2026-09-01~2026-09-01 对比 2026-09-02~2026-09-02）；各自保留原单位及变化，不能擅自合并总指标。"
    if charts: text += "；并展示六个来源各自的图表"
    events = list(loop.stream_turn(f"【{marker}】" + text))
    assert not [e for e in events if e["type"] in {"error", "suspended"}]
    host = snapshot_for_turn(loop); state = loop.context.analysis_state
    from data_agent.llm.request_policy import resolve_request_budget, count_request_tokens
    bound = resolve_request_budget(cfg.model_id,cfg,2048).input_allowance
    before=host.as_dict()
    view = model_publication_context(host, state, budget=bound,soft_budget=1)
    assert not view.get("model_view_issue")
    assert count_request_tokens(cfg.model_id,[{"role":"system","content":encode(view)}],tokenizer_path=cfg.model_tokenizer)["tokens"] <= bound
    assert view["model_view_budget"]["expanded_past_soft_target"] is True
    assert len(host.as_dict()["claims"]) == 72 and len(view["claims"]) == 60
    assert host.as_dict()==before
    assert {row[0] for row in view["claims"]}=={cid for req in before["requirements"] for cid in req["claim_ids"]}
    assert sum(len(item["claim_ids"]) for item in view["deferred_details"])==12
    from data_agent.tools.file_ops import read_file
    import hashlib
    for detail in view["deferred_details"]:
        assert hashlib.sha256((cfg.sessions_resolved/loop.session_id/detail["result_ref"]).read_bytes()).hexdigest()==detail["file_sha256"]
        assert not read_file(detail["result_ref"],expected_sha256=detail["file_sha256"]).startswith("Error:")
    assert sum(c["target"]["business_product"]["kind"]=="measurement" for c in host.as_dict()["claims"])==60
    assert sum(c["target"]["business_product"]["kind"]=="table" for c in host.as_dict()["claims"])==12
    from copy import deepcopy
    original={c["id"]:c for c in host.as_dict()["claims"]}
    for packed in view["claims"]:
        item=dict(zip(view["claim_fields"],packed));target=deepcopy(view["catalog_context"]["targets"][item["target_ref"]])
        target["parameters"]=view["catalog_context"]["parameters"][target.pop("parameters_ref")]
        product=target.get("business_product")
        if isinstance(product,dict) and "parameters_ref" in product:product["parameters"]=view["catalog_context"]["parameters"][product.pop("parameters_ref")]
        assert target==original[item["id"]]["target"]
    assert len(host.as_dict()["artifacts"]) == (6 if charts else 0)
    original_targets={r["id"]:r for r in state.answer_requirements}
    for packed_target in view["execution_targets"]:
        restored=deepcopy(packed_target);restored["business_scope"]=view["catalog_context"]["scopes"][restored.pop("business_scope_ref")]
        for delivery in restored["necessary_deliveries"]:delivery["scope"]=view["catalog_context"]["scopes"][delivery.pop("scope_ref")]
        assert restored=={k:original_targets[restored["id"]][k] for k in restored}
    _, projection = project_deliveries(state.answer_requirements, host.as_dict()["claims"], host.as_dict()["artifacts"])
    for row in view["claims"]:
        item = dict(zip(view["claim_fields"], row))
        assert set(item["declared_delivery_ids"]) == {did for did, value in projection.items() if item["id"] in value["catalogue_ids"]}
    assert all(o["status"] == "answered" for o in loop._accepted_answer["requirement_outcomes"])


@pytest.mark.parametrize("marker,text", [
    ("B03-SYNTH", "对齐 src_1 和 src_2 后分别比较，不求跨源总和。"),
    ("B05-PY-NOROW", "计算当前订单原值和含首尾的日期天数。"),
])
def test_original_alignment_and_separate_day_request_run_declared_plan(engine, marker, text):
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient, RunTrace, _write_fixtures
    loop, cfg = engine
    cfg.workspace_resolved.joinpath("inbox").mkdir(parents=True, exist_ok=True)
    _write_fixtures(cfg.workspace_resolved.parent)
    client = ScriptedClient(RunTrace(cfg.workspace_resolved.parent));loop.client=client;loop.auxiliary_llm_client=client
    events=list(loop.stream_turn(f"【{marker}】"+text))
    assert not [e for e in events if e["type"] in {"error","suspended"}],events
    answer=loop._accepted_answer
    assert all(o["status"]=="answered" for o in answer["requirement_outcomes"])
    if marker=="B03-SYNTH":
        changes=[c for c in answer["source_snapshot"]["claims"] if c["target"].get("tool")=="compare_periods"]
        assert [[c["value"] for c in changes if c["target"].get("metric")==n] for n in ["src_1","src_2"]]==[[21.0,25.0,4.0,19.05],[42.0,50.0,8.0,19.05]]
        assert all(set(p["data_identities"])=={"aligned_pair"} for c in changes for p in c["basis_refs"])
    else:
        req=next(r for r in answer["source_snapshot"]["requirements"] if r["text"]=="含首尾的日期天数")
        assert len(req["claim_ids"])==1
        claim=next(c for c in answer["source_snapshot"]["claims"] if c["id"]==req["claim_ids"][0])
        assert claim["value"]==12 and claim["basis_refs"][0]["result_path"]==["result_data","inclusive_days"]


@pytest.mark.parametrize("tool,args",[
    ("distribution_analysis",{"name":"orders","columns":"amount"}),
    ("run_python",{"code":"result=1","purpose":"formal mean"}),
])
def test_s1_formal_computation_without_predispatch_plan_is_rejected(engine,tool,args):
    loop,_=engine
    request(loop,"计算amount均值")
    error=loop._current_task_scope_guard(tool,args)
    assert error and json.loads(error)["error_type"]=="formal_plan_required"


def test_s1_exploration_receipt_cannot_be_claimed_by_a_later_plan(engine):
    from tests.test_trusted_publication_native_families import _s1_register
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine
    request(loop,"先了解数据结构")
    receipt,_=execute(loop,"describe_dataset",{"name":"orders"})
    before=deepcopy(next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==receipt))
    assert before["required_delivery_ids"]==[]
    _s1_register(loop,"正式交付记录数",[{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}}])
    current=next(r for r in snapshot_for_turn(loop).as_dict()["requirements"] if r["text"]=="正式交付记录数")
    assert current["claim_ids"]==[] and current["gap"]["status"]=="not_computed"
    assert next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==receipt)==before


def test_s1_invalid_scope_is_localized_but_valid_goal_still_answers(engine):
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.publication.runtime import register_request,snapshot_for_turn
    loop,_=engine
    content="计算7日收入，并解释p值"
    loop.messages.append({"role":"user","content":content,"request_id":"scope_local"})
    intent=TurnIntent("directed_analysis","clear","data_loaded","analysis","execute_analysis",requested_outputs=[{"kind":"result","exact_span":"7日收入","business_scope":{"datasets":["orders"],"parameters":{"window":7}}},{"kind":"knowledge","exact_span":"解释p值"}])
    register_request(loop,content,intent);loop.context.turn_intent=intent
    requirements=loop.context.analysis_state.answer_requirements
    assert requirements[0]["scope_issue"]["code"]=="unresolved_business_scope"
    assert requirements[0]["scope_issue"]["proposal"]["parameters"]=={"window":7}
    projected=snapshot_for_turn(loop).as_dict()["requirements"]
    assert projected[0]["gap"]["status"]=="failed" and projected[0]["claim_ids"]==[]
    assert projected[1]["open_purposes"]==["knowledge"] and projected[1]["gap"] is None


def test_s1_failed_predecessor_cannot_unlock_success_dependency(engine):
    from tests.test_trusted_publication_native_families import _s1_register
    from data_agent.session.task_manager import task_manager
    loop,_=engine
    _s1_register(loop,"先记录数再均值",[{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}},{"kind":"measurement","scope":{"datasets":["orders"],"metrics":["amount"],"quantity":"mean"}}],dependencies=True)
    tasks=task_manager.list_active_for_scope(session_id=loop.session_id)
    first=next(t for t in tasks if t["step_id"]=="s1_0")
    second=next(t for t in tasks if t["step_id"]=="s1_1")
    assert task_manager.update(first["id"],status="completed") is None
    task_manager.update(first["id"],status="failed")
    assert first["id"] in task_manager.get(second["id"])["blockedBy"]
    assert task_manager.start_next_ready_stage3c0b_task(session_id=loop.session_id) is None


@pytest.mark.parametrize("reject_action",[False,True])
def test_s1_default_app_upload_plan_receipt_publish_sse_save_and_export(engine,reject_action):
    """E2 normal Flask/AgentLoop integration; no live server or visual claim.

    The scripted model sees only its public system context and emits proposals.
    It never accesses the loop, workspace, receipts, task state or accepted answer.
    """
    import io
    from data_agent.llm.client import Response,ToolCall,StreamTextDelta,StreamComplete
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    from data_agent.session.public_messages import assistant_replies
    _,cfg=engine
    consultation="什么是p值，如何正确解释？"
    facts_span="给出记录数、amount合计、含首尾观测日数"
    action="只有下一同口径七日窗口净贡献不低于基准期，且成本每单不高于本期，才考虑小规模受控试验；否则暂停增加预算并复核。"
    content="分析当前上传的销售订单，将其命名为m01_sales，"+facts_span+"。未来规则："+action
    action_text="未来行动仅为条件规则："+action+"下一窗口尚未观测；当前销售表没有净贡献与成本列，不能声称任一条件已经触发。金额单位未知，描述性观察不能证明因果。"

    class ProposedModel:
        def __init__(self): self.mode="consultation";self.step=0;self.audit_count=0;self.ticket=None;self.tools=[]
        def chat(self,messages,system="",tools=None,**kw):
            if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
                if self.mode=="consultation": payload={"intent_type":"knowledge_qa","requested_outputs":[{"kind":"knowledge","exact_span":consultation}]}
                else: payload={"intent_type":"directed_analysis","requested_outputs":[
                    {"kind":"result","exact_span":facts_span,"business_scope":{"datasets":["m01_sales"]}},
                    {"kind":"conditional_action","exact_span":action,"business_scope":{"datasets":["m01_sales"]}}],
                    "upload_bindings":[{"upload_id":self.ticket["upload_id"],"dataset":"m01_sales","relation":"new","exact_span":"将其命名为m01_sales"}]}
                return Response(text=encode(payload))
            if system.startswith("审核数据相关开放片段"):
                self.audit_count+=1;request=json.loads(messages[0]["content"])
                return Response(text=encode({"schema":"publication_audit.v2","snapshot_digest":request["snapshot_digest"],"draft_digest":request["draft_digest"],"decisions":[{"part_id":p["part_id"],"disposition":"reject" if reject_action else "accept","reason":"scripted local audit transport test","evidence_refs":p["requirement_ids"]} for p in request["parts"]]}))
            # Exactly the JSON view provided to a normal model, no host matcher.
            view=json.JSONDecoder().raw_decode(system.split("</accepted_answer_contract>\n",1)[1].lstrip())[0]
            def call(name,args):
                self.tools.append(name)
                return Response(tool_calls=[ToolCall("s1_proposal_"+str(len(self.tools)),name,args)])
            if self.mode=="analysis" and self.step<3:
                self.step+=1
                if self.step in {1,3}: return call("describe_dataset",{"name":"m01_sales"})
                goals={r["semantic_kind"]:r for r in view["execution_targets"]}
                declarations=[{"requirement_id":goals["result"]["id"],"kind":"measurement","label":label,"scope":scope} for label,scope in [
                    ("Record count",{"datasets":["m01_sales"],"quantity":"rows"}),
                    ("Amount sum",{"datasets":["m01_sales"],"metrics":["amount"],"quantity":"sum"}),
                    ("Inclusive observed dates",{"datasets":["m01_sales"],"quantity":"calendar_days"})]]
                declarations.append({"requirement_id":goals["conditional_action"]["id"],"kind":"conditional_action","label":"Future AND action","scope":{"datasets":["m01_sales"]}})
                plan={"contract_version":"stage3c0b.v2","requirement_revision":view["requirement_revision"],"goal":content,"visualization_strategy":[],"method_plan":[{"step_id":"s1_current","goal":facts_span,"expected_output":"Three original current measurements and future action","evidence_requirements":["actual native receipt"],"dataset_inputs":["m01_sales"],"required_deliveries":declarations}]}
                return call("record_analysis_plan",{"plan_json":plan})
            sections=[]
            for r in view["requirements"]:
                parts=[{"kind":"claim","ref":cid} for cid in r["claim_ids"]]
                if "knowledge" in r["open_purposes"]: parts.append({"kind":"text","purpose":"knowledge","text":"p值是在零假设及检验前提成立时，观察到同样或更极端结果的概率；不是零假设为真的概率。","claim_refs":[]})
                if "conditional_action" in r["open_purposes"]: parts.append({"kind":"text","purpose":"conditional_action","text":action_text,"claim_refs":r.get("context_claim_ids",[])})
                sections.append({"requirement_ids":[r["id"]],"parts":parts})
            return Response(text=encode({"schema":"answer_bindings.v2","snapshot_digest":view["snapshot_digest"],"sections":sections}))
        def stream_chat_structured(self,*a,**kw):
            response=self.chat(*a,**kw)
            if response.text: yield StreamTextDelta(response.text)
            yield StreamComplete(response)

    script=ProposedModel()
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager
    sid="s1_default_app"
    def consume(response):
        assert response.status_code==200,response.get_data(as_text=True)
        events=[(block.split("\n",1)[0][7:],json.loads(block.split("\ndata: ",1)[1])) for block in response.get_data(as_text=True).split("\n\n") if block.startswith("event:")]
        terminals=[d for e,d in events if e=="turn_end"]
        assert len(terminals)==1 and terminals[0]["status"]=="completed",events
        assert manager.runs.snapshot(sid)["turn_id"]==terminals[0]["turn_id"]
        body="".join(d["text"] for e,d in events if e=="text_delta")
        assert body==terminals[0]["reply_content"]
        return body
    with app.test_client() as http:
        knowledge=consume(http.post("/api/chat",json={"session_id":sid,"message":consultation}))
        assert "p值" in knowledge and script.tools==[] and script.audit_count==0
        # Original M01-sales fixture bytes/values, independent of all matchers.
        data=("order_id,date,channel,amount\r\n"+"".join(f"O{i:02d},2026-09-{i:02d},all,10\r\n" for i in range(1,13))).encode()
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"M01-sales.csv")},content_type="multipart/form-data").get_json()
        assert ticket["filename"]=="M01-sales.csv" and ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest(),ticket
        script.mode="analysis";script.ticket=ticket
        body=consume(http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]}))
        refreshed=http.get("/api/sessions/"+sid).get_json()
    loop=manager.get(sid);stored=load_session(sid);terminal=stored["messages"][-1]
    accepted=read_answer(sid,terminal["answer_ref"])
    assert accepted["body"]==terminal["content"]==body
    original=next(r for r in accepted["source_snapshot"]["requirements"] if r["text"]==facts_span)
    facts={c["label"]:c for c in accepted["source_snapshot"]["claims"] if c["id"] in original["claim_ids"]}
    assert {k:v["value"] for k,v in facts.items()}=={"记录数":12,"amount：sum":120,"观测日期含首尾日数":12}
    assert facts["amount：sum"]["unit"] is None
    assert script.tools==["describe_dataset","record_analysis_plan","describe_dataset"] and script.audit_count==1
    receipts=[r for r in loop.context.analysis_state.tool_receipts if r["tool_name"]=="describe_dataset"]
    assert len(receipts)==2 and receipts[0]["required_delivery_ids"]==[]
    assert receipts[1]["step_id"]=="s1_current" and len(receipts[1]["required_delivery_ids"])==4
    assert all(p["receipt_id"]==receipts[1]["id"] for c in facts.values() for p in c["basis_refs"])
    outcomes={r["requirement_id"]:r["status"] for r in accepted["requirement_outcomes"]}
    assert outcomes[original["id"]]=="answered"
    action_req=next(r for r in accepted["source_snapshot"]["requirements"] if r["text"]==action)
    assert outcomes[action_req["id"]]==("failed" if reject_action else "answered")
    if not reject_action: assert action_text in body
    else: assert action_text not in body and all(v["id"] in {t["ref"] for t in accepted["render_trace"] if t["kind"]=="claim"} for v in facts.values())
    assert any(m.get("content")==body for m in refreshed["messages"])
    replies=assistant_replies(stored["messages"],sid)
    exported=export_assistant_reply(sid,body,reply_id=replies[-1]["reply_id"])
    assert exported["status"]=="exported",exported
    path=cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]
    assert body in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("mutation",["unverified_change","failed_load","failed_load_unchanged","same_version"])
def test_s1_explicit_replacement_freezes_only_current_or_verified_loaded_source(engine,mutation):
    import pandas as pd
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.publication.runtime import register_request
    from data_agent.tools.data_io import _record_trust_workflow
    from data_agent.tools.registry import registry
    loop,_=engine;state=loop.context.analysis_state
    request(loop,"统计orders记录数",{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}})
    execute(loop,"describe_dataset",{"name":"orders"})
    old=deepcopy(state.answer_requirements[-1]);receipts=deepcopy(state.tool_receipts)
    content="替换原目标，统计orders新范围记录数"
    loop.messages.append({"role":"user","content":content,"request_id":"s1_replacement_original"})
    intent=TurnIntent("directed_analysis","clear","data_loaded","execute","run_analysis",execution_readiness="ready",requested_outputs=[{"exact_span":content,"kind":"result","op":"replace","target_id":old["id"],"business_scope":{"datasets":["orders"],"quantity":"rows"}}])
    register_request(loop,content,intent)
    new=state.answer_requirements[-1]
    assert new["source_binding"]["status"]=="pending" and not new.get("source_data_identities")
    assert state.answer_requirements[-2]["lifecycle_status"]=="withdrawn"
    assert state.answer_requirements[-2]["source_data_identities"]==old["source_data_identities"]
    assert state.tool_receipts==receipts
    if mutation not in {"same_version","failed_load_unchanged"}:loop.context.workspace.add("orders",pd.DataFrame({"amount":[99]}))
    if mutation in {"failed_load","failed_load_unchanged"}:
        args={"source":"missing-s1-source.csv","name":"orders"}
        binding=loop._capture_tool_execution_binding("reload_data",args)
        assert loop._record_turn_tool_result("reload_data",'{"error":"load failed"}',args,"failed-load",execution_binding=binding)==""
        assert not new["source_binding"].get("verified_load_receipts")
    _record_trust_workflow(session_id=loop.session_id,state=state,dataset="orders",df=loop.context.workspace.get("orders"),applied=[],needs_confirm=[],quality={},interpretation_data={},detail_path="")
    declaration={"requirement_id":new["id"],"kind":"measurement","label":"New rows","scope":{"datasets":["orders"],"quantity":"rows"}}
    plan={"contract_version":"stage3c0b.v2","requirement_revision":state.requirement_revision,"goal":content,"method_plan":[{"goal":"Count current rows","expected_output":"Current rows","evidence_requirements":["receipt"],"dataset_inputs":["orders"],"required_deliveries":[declaration]}]}
    response=registry.execute("record_analysis_plan",{"plan_json":plan});result=response.data or json.loads(response.summary)
    if mutation=="same_version":
        assert "error" not in result,result
        assert state.answer_requirements[-1]["source_binding"]["status"]=="frozen"
    else:
        assert result["error_type"]=="replacement_source_unverified",result
        assert state.answer_requirements[-1]["source_binding"]["status"]=="pending"


@pytest.mark.parametrize("explicit_name",[False,True])
def test_s1_pending_replacement_uses_actual_load_output_even_with_default_name(engine,tmp_path,explicit_name):
    from data_agent.agent.intent import TurnIntent
    from data_agent.agent.publication.runtime import register_request,snapshot_for_turn
    from data_agent.tools.registry import registry
    loop,_=engine;state=loop.context.analysis_state
    request(loop,"原orders记录数",{"kind":"measurement","scope":{"datasets":["orders"],"quantity":"rows"}})
    original=state.answer_requirements[-1]["id"]
    content="替换原目标，加载新版main后计算记录数"
    loop.messages.append({"role":"user","content":content,"request_id":"s1_load_original"})
    intent=TurnIntent("directed_analysis","clear","data_loaded","execute","load_then_analyze",execution_readiness="pending_load",requested_outputs=[{"exact_span":content,"kind":"result","op":"replace","target_id":original,"business_scope":{"datasets":["main"],"quantity":"rows"}}])
    register_request(loop,content,intent)
    source=tmp_path/"new-source.csv";source.write_text("amount\n10\n20\n",encoding="utf-8")
    args={"source":str(source),**({"name":"main"} if explicit_name else {})}
    assert not loop._current_task_scope_guard("load_data",args)
    binding=loop._capture_tool_execution_binding("load_data",args)
    output=registry.execute("load_data",args)
    receipt=loop._record_turn_tool_result("load_data",output.summary,args,"actual-new-load",output.data,execution_binding=binding)
    new=state.answer_requirements[-1]
    assert new["source_binding"]["verified_load_receipts"]["main"]==receipt
    plan={"contract_version":"stage3c0b.v2","requirement_revision":state.requirement_revision,"goal":content,"method_plan":[{"goal":"Count new source","expected_output":"Rows","evidence_requirements":["receipt"],"dataset_inputs":["main"],"required_deliveries":[{"requirement_id":new["id"],"kind":"measurement","label":"New rows","scope":{"datasets":["main"],"quantity":"rows"}}]}]}
    response=registry.execute("record_analysis_plan",{"plan_json":plan});result=response.data or json.loads(response.summary)
    assert "error" not in result,result
    assert state.answer_requirements[-1]["source_binding"]["status"]=="frozen"
    execute(loop,"describe_dataset",{"name":"main"})
    host=snapshot_for_turn(loop).as_dict()
    req=next(r for r in host["requirements"] if r["id"]==new["id"])
    assert req["gap"] is None
    assert [c["value"] for c in host["claims"] if c["id"] in req["claim_ids"]]==[2]


def test_normal_app_unique_goal_continue_retains_plan_and_fact_identity(engine):
    import io,json
    from pathlib import Path
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient,RunTrace
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager

    class ContinuedClient(ScriptedClient):
        def chat(self,messages,**kwargs):
            prompt=self._last_user(messages)
            if "用户输入:" in prompt and prompt.partition("用户输入:")[2].partition("会话上下文:")[0].strip()=="继续":
                reqs=self._s2_context(prompt,"canonical_requirements",[])
                plan=prompt.partition("current_analysis_plan_id: ")[2].splitlines()[0]
                return self._response(json.dumps({"intent_type":"directed_analysis","continuation_of_plan_id":plan,"ambiguities":[],"requested_outputs":[{"op":"reuse","kind":r["semantic_kind"],"target_id":r["id"],"exact_span":"继续"} for r in reqs if r["lifecycle_status"]=="active"]},ensure_ascii=False))
            return super().chat(messages,**kwargs)
        def stream_chat_structured(self,messages,tools=None,system=None):
            if self._last_user(messages)=="继续":
                from data_agent.llm.client import StreamComplete
                yield StreamComplete(self._draft(messages,system,"继续保留同一来源的原事实及其限制。"))
            else:yield from super().stream_chat_structured(messages,tools=tools,system=system)

    _,cfg=engine
    script=ContinuedClient(RunTrace(cfg.workspace_resolved.parent))
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager
    spec=json.loads(Path("scripts/testing/p08_real_matrix_contract.json").read_text(encoding="utf-8"))
    content=spec["scenario_inputs"]["M05"]["prompts"][0]
    data=Path("tmp/p5-real-20261009-r3/fixtures/M01-sales.csv").read_bytes()
    with app.test_client() as client:
        ticket=client.post("/api/upload",data={"file":(io.BytesIO(data),"M01-sales.csv")},content_type="multipart/form-data").get_json()
        first=client.post("/api/chat",json={"session_id":"s2_continue","message":content,"uploads":[ticket]});assert first.status_code==200
        first.get_data()
        loop=manager.get("s2_continue");state=loop.context.analysis_state
        plan=json.loads(json.dumps(state.analysis_plan));spec_before=json.loads(json.dumps(state.analysis_spec));req_ids=[r["id"] for r in state.answer_requirements];receipts=len(state.tool_receipts)
        response=client.post("/api/chat",json={"session_id":"s2_continue","message":"继续"});assert response.status_code==200
        raw=response.get_data(as_text=True)
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in raw.split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"]
        assert len(ends)==1 and ends[0]["status"]=="completed",events
        assert "120" in ends[0]["reply_content"] and "12" in ends[0]["reply_content"]
        assert state.analysis_plan==plan and state.analysis_spec==spec_before
        assert [r["id"] for r in state.answer_requirements]==req_ids and len(state.tool_receipts)==receipts
        assert manager.runs.snapshot("s2_continue")["turn_id"]==ends[0]["turn_id"]


@pytest.mark.parametrize("mode",["wide","long"])
@pytest.mark.parametrize("policy",["exclude","keep"])
def test_curve_zero_policy_filters_observations_before_aggregation_and_preserves_proof(engine,mode,policy):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    loop,_=engine
    observed=[.55,.42,.31,.24,.18,.13,.10,0]
    if mode=="wide":
        frame=pd.DataFrame({"D"+str(i):[v,0] for i,v in enumerate(observed,1)})
        args={"series_columns":",".join(frame.columns)};metrics=list(frame.columns)
    else:
        frame=pd.DataFrame({"day":[i for i in range(1,9) for _ in range(2)],"retention":[v for y in observed for v in (y,0)]})
        args={"x_col":"day","y_col":"retention"};metrics=["retention"]
    loop.context.workspace.add("observations",frame)
    request(loop,"比较含零观测的曲线",{"kind":"series","scope":{"datasets":["observations"],"metrics":metrics,"parameters":{"zero_values":policy}}})
    rid,result=execute(loop,"curve_fitting",{"name":"observations","zero_values":policy,**args})
    expected=observed[:-1] if policy=="exclude" else [v/2 for v in observed]
    assert [p["y"] for p in result["points"]]==pytest.approx(expected)
    assert [p["n_observed"] for p in result["points"]]==[1 if policy=="exclude" else 2]*len(expected)
    assert [p["n_excluded_zeros"] for p in result["points"]]==[1 if policy=="exclude" else 0]*len(expected)
    assert result["zero_value_semantics"]=="unknown" and result["effective_n"]==len(expected)
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot))
    assert error is None and "零值" in body
    assert commit(loop,{"role":"assistant"},body) is None
    accepted=read_answer(loop.session_id,load_session(loop.session_id)["messages"][-1]["answer_ref"])
    assert accepted["body"]==body and accepted["requirement_outcomes"][0]["status"]=="answered"
    series=next(c for c in accepted["source_snapshot"]["claims"] if c["basis_refs"][0]["receipt_id"]==rid and c["basis_refs"][0]["result_path"]==["points"])
    assert [p["y"] for p in series["value"]]==pytest.approx(expected)
    assert any("零值" in x for x in series["limitations"])


@pytest.mark.parametrize("fault",["wrong_policy","receipt_policy"])
def test_curve_zero_policy_mismatch_cannot_complete_declared_series(engine,fault):
    import pandas as pd
    from data_agent.agent.publication.runtime import snapshot_for_turn
    from data_agent.agent.publication.native import MINIMAL_PRODUCT_CONTRACTS
    from data_agent.tools.registry import registry
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine
    loop.context.workspace.add("observations",pd.DataFrame({"day":[i for i in range(1,8) for _ in range(2)],"retention":[v for y in [.55,.42,.31,.24,.18,.13,.10] for v in (y,0)]}))
    request(loop,"按排除零值口径交付留存序列",{"kind":"series","scope":{"datasets":["observations"],"metrics":["retention"],"parameters":{"zero_values":"exclude"}}})
    policy="keep" if fault=="wrong_policy" else "exclude"
    rid,result=execute(loop,"curve_fitting",{"name":"observations","x_col":"day","y_col":"retention","zero_values":policy})
    if fault=="receipt_policy":
        result["parameters"]["zero_values"]="keep";_tamper(loop,cfg,rid,result)
    row=snapshot_for_turn(loop).as_dict()["requirements"][0]
    assert row["gap"]["status"]=="failed" and not row["claim_ids"]
    assert ("product_scope_mismatch" if fault=="wrong_policy" else "result_contract_mismatch") in row["gap"]["reason"]
    assert registry.capability_for("curve_fitting")["output_contract"]==MINIMAL_PRODUCT_CONTRACTS["curve_fitting"]


@pytest.mark.parametrize("method",["pearson","spearman"])
def test_normal_app_correlation_upload_plan_original_matrix_sse_save_refresh_export(engine,method):
    """Normal default app, public-only scripted model, real uploads and tool dispatch."""
    import io,hashlib
    from data_agent.llm.client import Response,ToolCall,StreamTextDelta,StreamComplete
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    from tests.test_trusted_publication_native_families import _correlation_frame,_correlation_oracle
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
    _,cfg=engine
    content=f"分析上传数据，将其命名为relationships，给出x、weak、constant的完整{method}相关矩阵。"
    scope={"datasets":["relationships"],"metrics":["x","weak","constant"],"parameters":{"correlation_method":method}}
    script=_NativeProductModel(content,"relationships","correlation_analysis",{"name":"relationships","columns":"x,weak,constant","method":method},[{"kind":"table","scope":scope}]);manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager
    frame=_correlation_frame()[["x","weak","constant"]];data=frame.to_csv(index=False).encode('utf-8')
    sid="s3_correlation_"+method
    with app.test_client() as http:
        ticket=http.post('/api/upload',data={"file":(io.BytesIO(data),'relationships.csv')},content_type='multipart/form-data').get_json()
        assert ticket['filename']=='relationships.csv' and ticket['sha256']=='sha256:'+hashlib.sha256(data).hexdigest()
        script.ticket=ticket
        response=http.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]})
        assert response.status_code==200
        events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
        ends=[d for e,d in events if e=='turn_end']
        assert len(ends)==1 and ends[0]['status']=='completed',events
        body=''.join(d['text'] for e,d in events if e=='text_delta')
        assert body==ends[0]['reply_content']
        refreshed=http.get('/api/sessions/'+sid).get_json()
    saved=load_session(sid)['messages'][-1];answer=read_answer(sid,saved['answer_ref'])
    assert answer['body']==saved['content']==body
    assert answer['requirement_outcomes'][0]['status']=='answered'
    req=answer['source_snapshot']['requirements'][0]
    matrix=next(c for c in answer['source_snapshot']['claims'] if c['id'] in req['claim_ids'] and c['basis_refs'][0]['result_path']==['correlation_matrix'])
    expected={a:{b:_correlation_oracle(frame[a],frame[b],method) for b in frame} for a in frame}
    assert matrix['value']==expected and matrix['value']['x']['weak']==0
    assert matrix['target']['business_product']['parameters']=={'correlation_method':method}
    loop=manager.get(sid);receipt=next(r for r in loop.context.analysis_state.tool_receipts if r['tool_name']=='correlation_analysis')
    assert receipt['step_id']=='native_product' and receipt['required_delivery_ids']
    assert script.calls==['describe_dataset','record_analysis_plan','correlation_analysis']
    assert len([m for m in refreshed['messages'] if m.get('answer_ref')==saved['answer_ref']])==1
    exported=export_assistant_reply(sid,body,'md')
    assert exported['status']=='exported',exported
    assert body in (cfg.sessions_resolved/sid/'reports'/exported['artifact_path'].split('/')[-1]).read_text(encoding='utf-8')

