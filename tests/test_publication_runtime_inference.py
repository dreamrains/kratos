from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: inference. Shared fixtures have one owner."""
from data_agent.agent.publication.contracts import encode
import json
import pytest
from tests.support.publication_runtime import _NativeProductModel
from tests.test_trusted_publication_runtime import _s3_distribution_id_save

@pytest.mark.parametrize("case",["complete","singletons","missing_cell"])
def test_normal_app_did_actual_upload_plan_and_persisted_inference_boundary(engine,case):
    import io,hashlib
    from tests.test_trusted_publication_native_families import _did_frame
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    _,cfg=engine
    content="分析上传数据，将其命名为experiment，按treat和period的0/1四组报告outcome的DID点估计及95%区间；平行趋势未验证。"
    scope={"datasets":["experiment"],"metrics":["outcome"],"parameters":{"causal_method":"did"}}
    specs=[{"kind":"measurement","scope":dict(scope,quantity="value",parameters={"causal_method":"did","causal_output":"effect"})},
           {"kind":"table","scope":dict(scope,parameters={"causal_method":"did","causal_output":"confidence_interval"})}]
    script=_NativeProductModel(content,"experiment","causal_analysis",{"name":"experiment","treatment_col":"treat","outcome_col":"outcome","time_col":"period"},specs)
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config['agent_manager']=manager
    data=_did_frame(missing=(1,1) if case=="missing_cell" else None,singleton=case=="singletons").to_csv(index=False).encode('utf-8')
    sid="s3_did_"+case
    with app.test_client() as http:
        ticket=http.post('/api/upload',data={'file':(io.BytesIO(data),'experiment.csv')},content_type='multipart/form-data').get_json()
        assert ticket['sha256']=='sha256:'+hashlib.sha256(data).hexdigest();script.ticket=ticket
        response=http.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]})
        assert response.status_code==200
        events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
        ends=[d for e,d in events if e=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed',events
        refreshed=http.get('/api/sessions/'+sid).get_json()
    saved=load_session(sid)['messages'][-1];answer=read_answer(sid,saved['answer_ref'])
    assert answer['body']==saved['content']==ends[0]['reply_content']
    assert answer['requirement_outcomes'][0]['status']=={'complete':'answered','singletons':'partial','missing_cell':'evidence_insufficient'}[case]
    req=answer['source_snapshot']['requirements'][0]
    facts={c['basis_refs'][0]['result_path'][0]:c for c in answer['source_snapshot']['claims'] if c['id'] in req['claim_ids']}
    assert facts['did_effect']['value']==(None if case=='missing_cell' else 4)
    assert facts['ci_95']['value']==([.08,7.92] if case=='complete' else None)
    assert script.calls==['describe_dataset','record_analysis_plan','causal_analysis']
    assert any(m.get('answer_ref')==saved['answer_ref'] for m in refreshed['messages'])
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r['tool_name']=='causal_analysis')
    assert receipt['step_id']=='native_product' and len(receipt['required_delivery_ids'])==2


@pytest.mark.parametrize("case",["auto","ttest","mannwhitneyu","chi2","paired","one_pair","degenerate"])
def test_normal_app_ab_actual_upload_formal_method_plan_and_persisted_inference(engine,case):
    import io,hashlib
    import pandas as pd
    from tests.test_trusted_publication_native_families import _ab_frame
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    method=case if case in {"auto","ttest","mannwhitneyu","chi2"} else "ttest"
    frame=_ab_frame(case)
    if case in {"auto","ttest","mannwhitneyu"}:frame=_ab_frame()
    if case=="chi2":frame=pd.DataFrame({"group":["A"]*10+["B"]*10,"amount":[0]*8+[1]*2+[0]*2+[1]*8})
    content=f"分析上传数据，将其命名为experiment；用{method}报告amount两组差值及p值，按实际配对设计保留未知。"
    scope={"datasets":["experiment"],"metrics":["amount"]};params={"ab_method":method}
    specs=[{"kind":"measurement","scope":dict(scope,quantity="value",parameters=dict(params,ab_output="p_value"))}]
    specs.append({"kind":"table","scope":dict(scope,parameters=dict(params,ab_output="contingency"))} if case=="chi2" else {"kind":"measurement","scope":dict(scope,quantity="difference",parameters=dict(params,ab_output="difference"))})
    args={"name":"experiment","group_col":"group","metric_col":"amount","method":method}
    if case in {"paired","one_pair"}:args["unit_col"]="unit"
    script=_NativeProductModel(content,"experiment","ab_test",args,specs)
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager
    data=frame.to_csv(index=False).encode("utf-8");sid="s3_ab_"+case
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["filename"]=="experiment.csv" and ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();script.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        assert response.status_code==200
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    status="partial" if case in {"one_pair","degenerate"} else "answered"
    assert answer["requirement_outcomes"][0]["status"]==status
    req=answer["source_snapshot"]["requirements"][0]
    claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    pvalue=next(c for c in claims if c["basis_refs"][0]["result_path"]==["test","p_value"])
    assert pvalue["unit"]=="无量纲"
    if status=="partial":assert pvalue["value"] is None and "未知" in answer["body"]
    elif case=="chi2":assert pvalue["value"]==.025347
    elif case=="mannwhitneyu":assert pvalue["value"]==.1
    elif case=="paired":assert pvalue["value"]==.12169
    else:assert pvalue["value"]==.021312
    if case!="chi2":
        effect=next(c for c in claims if c["basis_refs"][0]["result_path"]==["difference","absolute"])
        assert effect["value"]==(1 if status=="partial" else 3)
    assert script.calls==["describe_dataset","record_analysis_plan","ab_test"]
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="ab_test")
    assert receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==2
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert exported["status"]=="exported"
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


@pytest.mark.parametrize("case",["classification_auto","classification_logistic","classification_rf","regression_auto","regression_linear","regression_rf","regression_gbrt","shap_binary","shap_multiclass","shap_regression","shap_single_output"])
def test_normal_app_ml_actual_upload_formal_plan_model_metrics_and_persisted_explanation(engine,case):
    import io,hashlib,math
    from tests.test_trusted_publication_native_families import _ml_frame
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    is_shap=case.startswith("shap_");classification=case.startswith("classification_") or case in {"shap_binary","shap_multiclass","shap_single_output"}
    trainer="classification" if classification else "regression_analysis"
    method=("auto" if case=="shap_single_output" else "rf") if is_shap else case.split("_",1)[1]
    kind="classification" if classification else "regression"
    frame=_ml_frame(classification,labels=(2,3,4) if case=="shap_multiclass" else (2,3))
    content=f"分析上传数据，将其命名为experiment，用{method}训练target的{kind}模型，报告实际随机留出指标"+("并报告当前模型各类及总体SHAP贡献，不能解释的保持未知。" if is_shap else "，不外推因果或时间表现。")
    scope={"datasets":["experiment"],"metrics":["target"]}
    specs=[{"kind":"fit","scope":dict(scope,parameters={"classification_method" if classification else "regression_method":method,"model_output":"metrics","cv_folds":0})}]
    train_args={"name":"experiment","target_col":"target","features":"x,z","method":method}
    if is_shap:
        specs.extend({"kind":"table","scope":dict(scope,parameters={"model_kind":kind,"shap_output":output})} for output in (["overall","per_class"] if classification else ["overall"]))
        script=_NativeProductModel(content,"experiment","shap_analysis",{"name":"experiment","target_col":"target","model_kind":kind},specs,[(trainer,train_args)])
    else:script=_NativeProductModel(content,"experiment",trainer,train_args,specs)
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager
    data=frame.to_csv(index=False).encode("utf-8");sid="s3_ml_"+case
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["filename"]=="experiment.csv" and ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();script.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        assert response.status_code==200
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("partial" if case=="shap_single_output" else "answered"),answer["source_snapshot"]["requirements"]
    loop=manager.get(sid);receipts=loop.context.analysis_state.tool_receipts
    trained=next(r for r in receipts if r["tool_name"]==trainer)
    from data_agent.agent.publication.facts import load_receipt_result
    from data_agent.agent.context import use_agent_context
    with use_agent_context(loop.context):
        _,_,raw,_=load_receipt_result(session_id=sid,receipt_id=trained["id"])
    truth=raw["evaluation"]["y_true"];pred=raw["evaluation"]["y_pred"]
    if classification:
        assert raw["label_mapping"]==[{"encoded":i,"label":i+2} for i in range(3 if case=="shap_multiclass" else 2)]
        expected_accuracy=round(sum(t==p for t,p in zip(truth,pred))/len(truth),4)
        assert raw["metrics"]["accuracy"]==expected_accuracy
    else:
        n=len(truth);mean=sum(truth)/n;sse=sum((t-p)**2 for t,p in zip(truth,pred));sst=sum((t-mean)**2 for t in truth)
        assert raw["metrics"]=={"r2":round(1-sse/sst,4),"rmse":round(math.sqrt(sse/n),4),"mae":round(sum(abs(t-p) for t,p in zip(truth,pred))/n,4)}
    req=answer["source_snapshot"]["requirements"][0]
    claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    metric=next(c for c in claims if c["basis_refs"][0]["result_path"]==["metrics"])
    assert metric["value"]==raw["metrics"] and metric["target"]["metric"]=="target"
    if is_shap:
        overall=next(c for c in claims if c["basis_refs"][0]["result_path"]==["shap_importance"])
        if case=="shap_single_output":assert overall["value"] is None and "未知" in answer["body"]
        else:
            assert {r["feature"] for r in overall["value"]}=={"x","z"}
            if classification:
                by_class=next(c for c in claims if c["basis_refs"][0]["result_path"]==["per_class_importance"])
                vectors=[{r["feature"]:r["mean_abs_shap"] for r in row["importance"]} for row in by_class["value"]]
                assert [row["label"] for row in by_class["value"]]==([2,3,4] if case=="shap_multiclass" else [2,3])
                assert all(abs(row["mean_abs_shap"]-sum(v[row["feature"]] for v in vectors)/len(vectors))<=1.000001e-6 for row in overall["value"])
    assert script.calls==["describe_dataset","record_analysis_plan",trainer]+(["shap_analysis"] if is_shap else [])
    assert trained["step_id"]=="native_product" and trained["required_delivery_ids"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md");assert exported["status"]=="exported"
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


@pytest.mark.parametrize("case",["features","clean","conversion","derive_field","write","edit","load_skill","unload_skill","enable_skill","disable_skill","delete_skill","optimize_good","optimize_not_found","transform_filter","transform_select","transform_rename","transform_sort","transform_group","transform_resample","transform_melt","transform_pivot"])
def test_normal_app_operation_or_allocation_actual_plan_sse_save_refresh_export(engine,case,tmp_path,monkeypatch):
    import io,hashlib
    import pandas as pd
    from tests.test_trusted_publication_native_families import _operation_spec
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;dataset="" if case in {"write","edit","load_skill","unload_skill","enable_skill","disable_skill","delete_skill"} else "experiment"
    if case.endswith("skill"):
        from data_agent.skills.loader import SkillLoader
        import data_agent.tools.skill_tools as skill_tools
        file=tmp_path/"isolated_skills/fixture/SKILL.md";file.parent.mkdir(parents=True)
        file.write_text("---\nname: fixture\nenabled: true\n---\nfixture instructions",encoding="utf-8")
        loader=SkillLoader(file.parent.parent);loader.discover();monkeypatch.setattr(skill_tools,"_loader",lambda:loader)
        if case in {"unload_skill","disable_skill","delete_skill"}:loader.load("fixture")
        if case=="enable_skill":loader.set_enabled("fixture",False)
    calls={"features":("derive_features",{"name":dataset,"feature_type":"lag_features","columns":"amount","save_as":"features"}),
        "clean":("clean_data",{"name":dataset,"deduplicate":True}),
        "conversion":("apply_type_conversion",{"name":dataset,"column":"amount","target_type":"numeric"}),
        "derive_field":("derive_field",{"name":dataset,"field_name":"double","expression":"amount * 2"}),
        "write":("write_file",{"path":"result.txt","content":"中文操作结果\n"}),
        "edit":("edit_file",{"path":"output/result.txt","old_text":"before","new_text":"after"}),
        "transform_filter":("transform_data",{"name":dataset,"operation":"filter","condition":"amount > 0"}),
        "transform_select":("transform_data",{"name":dataset,"operation":"select","columns":["amount"]}),
        "transform_rename":("transform_data",{"name":dataset,"operation":"rename","rename_mapping":{"amount":"value"}}),
        "transform_sort":("transform_data",{"name":dataset,"operation":"sort","sort_by":["group"],"ascending":False}),
        "transform_group":("transform_data",{"name":dataset,"operation":"group_aggregate","group_by":["group"],"aggregations":[{"column":"amount","functions":["sum"]}]}),
        "transform_resample":("transform_data",{"name":dataset,"operation":"resample","date_col":"day","freq":"W","resample_agg":{"amount":"sum"}}),
        "transform_melt":("transform_data",{"name":dataset,"operation":"pivot","melt_id_vars":["group"],"melt_value_vars":["amount"]}),
        "transform_pivot":("transform_data",{"name":dataset,"operation":"pivot","pivot_index":"group","pivot_columns":"day","pivot_values":"amount"})}
    if case.endswith("skill"):calls[case]=(case,{"name":"fixture"})
    if case.startswith("optimize"):
        tool="what_if_simulation";constraints='{"A":{"max":5}}' if case=="optimize_not_found" else '{}'
        args={"name":dataset,"mode":"optimize","target_metric":"amount","dimension":"group","goal_pct":100 if case=="optimize_not_found" else 10,"constraints":constraints}
        specs=[{"kind":"scenario","scope":{"datasets":[dataset],"metrics":["amount"],"parameters":{"simulation_mode":"optimize","goal_pct":args["goal_pct"],"allocation_constraints":json.loads(constraints)}}}]
    else:
        tool,args=calls[case];specs=[_operation_spec(tool,args,[dataset] if dataset else [])]
    content=("处理上传数据，将其命名为"+dataset+"；" if dataset else "")+"只完成指定操作或约束分配候选，不增加统计解释。"
    model=_NativeProductModel(content,dataset,tool,args,specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_effect_app_"+case
    if case=="edit":
        file=cfg.sessions_resolved/sid/"output/result.txt";file.parent.mkdir(parents=True);file.write_text("before",encoding="utf-8")
    data=pd.DataFrame({"group":["A","B"],"amount":[100.,100.],"day":["2026-10-01","2026-10-02"]}).to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        uploads=[]
        if dataset:
            ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
            assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket;uploads=[ticket]
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":uploads})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("evidence_insufficient" if case=="optimize_not_found" else "answered"),answer
    req=answer["source_snapshot"]["requirements"][0]
    if case.startswith("optimize"):
        c=next(c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"])
        if case=="optimize_not_found":assert c["value"] is None and "数学不可行" in answer["body"]
        else:assert sum(r["required_change"] for r in c["value"])==pytest.approx(20)
    else:
        assert req["effect_ids"] and not req["claim_ids"]
        effect=next(e for e in answer["source_snapshot"]["effects"] if e["id"]==req["effect_ids"][0])
        assert effect["action"]==tool and effect["session_id"]==sid and "操作完成" in answer["body"]
        if case=="write":assert (cfg.sessions_resolved/sid/"output/result.txt").read_text(encoding="utf-8")==args["content"]
        elif case=="edit":assert (cfg.sessions_resolved/sid/"output/result.txt").read_text(encoding="utf-8")=="after"
        elif case.endswith("skill"):
            assert effect["object"]["kind"]=="skill" and not effect["data_identities"]
        else:assert effect["object"]["identity"]["parent_version_ids"]==[effect["before"]["source_data_identities"][dataset]["version_id"]]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]==tool)
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and receipt["required_delivery_ids"]


def test_normal_app_skill_session_loading_global_admin_and_visible_effects(engine,tmp_path,monkeypatch):
    import data_agent.agent.loop as module
    import data_agent.config_resolver as resolver
    from data_agent.skills.loader import SkillLoader
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    from tests.test_trusted_publication_native_families import _operation_spec
    file=tmp_path/"session_skills/fixture/SKILL.md";file.parent.mkdir(parents=True)
    file.write_text("---\nname: fixture\nenabled: true\n---\nPRIVATE_SESSION_INSTRUCTION",encoding="utf-8")
    owner=SkillLoader(file.parent.parent);owner.discover();monkeypatch.setattr(module,"_skill_loader",owner)
    monkeypatch.setattr(resolver,"resolve_skills_dirs",lambda:[file.parent.parent])
    class Observe(_NativeProductModel):
        def __init__(self,*a):super().__init__(*a);self.systems=[]
        def chat(self,*a,**kw):self.systems.append(kw.get("system",""));return super().chat(*a,**kw)
    specs=[("load_skill",{"name":"fixture"}),("write_file",{"path":"separate.txt","content":"session B"})]
    models=[Observe("只完成指定操作", "",tool,args,[_operation_spec(tool,args)]) for tool,args in specs]
    pending=iter(models);current=[]
    def factory(**kw):current[:]=[next(pending)];return current[0]
    manager=AgentManager(client_factory=factory,auxiliary_client_factory=lambda:current[0])
    app=create_app();app.config["agent_manager"]=manager
    with app.test_client() as http:
        for sid in ("skill_app_a","skill_app_b"):
            response=http.post("/api/chat",json={"session_id":sid,"message":"只完成指定操作"})
            events=[json.loads(b.split("\ndata: ",1)[1]) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event: turn_end")]
            assert len(events)==1 and events[0]["status"]=="completed"
            saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
            assert answer["requirement_outcomes"][0]["status"]=="answered" and answer["body"]==events[0]["reply_content"]
            assert any(m.get("answer_ref")==saved["answer_ref"] for m in http.get("/api/sessions/"+sid).get_json()["messages"])
        assert any("PRIVATE_SESSION_INSTRUCTION" in s for s in models[0].systems)
        assert all("PRIVATE_SESSION_INSTRUCTION" not in s for s in models[1].systems)
        assert manager.get("skill_app_a")._skill_loader.list_loaded()
        assert not manager.get("skill_app_b")._skill_loader.list_loaded()
        http.post("/api/skills/fixture/disable")
        assert not manager.get("skill_app_a")._skill_loader.list_loaded()
        assert not manager.get("skill_app_a")._skill_loader.get_prompt_injections()


@pytest.mark.parametrize("case",["eleven","numeric","reverse","zero_reverse"])
def test_normal_app_sensitivity_actual_upload_plan_visible_unknown_and_export(engine,case):
    import io,hashlib,pandas as pd
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    frame=pd.DataFrame({"group":["A","B"],"amount":[100.,200.]})
    args={"name":"experiment","mode":"sensitivity","metric":"amount","dimension":"group"}
    params={"simulation_dimension":"group"}
    reverse=case in {"reverse","zero_reverse"}
    if reverse:
        if case=="zero_reverse":frame["amount"]=[100.,-100.]
        args["target_value"]="100" if case=="zero_reverse" else "600"
        params.update(simulation_mode="sensitivity_reverse",simulation_target=float(args["target_value"]))
    else:
        if case=="eleven":frame=pd.DataFrame({"group":[str(i) for i in range(11)],"amount":[100.]*11})
        if case=="numeric":frame["group"]=[1,2];args["dim_value"]="1";params["simulation_dimension_value"]="1"
        args["change_pct"]=10;params.update(simulation_mode="sensitivity",simulation_change_pct=10)
    outputs=["baseline_total" if reverse else "baseline","breakdown"]
    specs=[{"kind":"scenario","scope":{"datasets":["experiment"],"metrics":["amount"],"parameters":dict(params,simulation_output=output)}} for output in outputs]
    content="处理上传数据，将其命名为experiment；按指定敏感性算术情景保留基线与全部分组，不能反推的结果显示未知。"
    model=_NativeProductModel(content,"experiment","what_if_simulation",args,specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_sensitivity_"+case
    data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        ends=[json.loads(b.split("\ndata: ",1)[1]) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event: turn_end")]
        assert len(ends)==1 and ends[0]["status"]=="completed"
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("partial" if case=="zero_reverse" else "answered"),answer
    req=answer["source_snapshot"]["requirements"][0]
    claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    rows=next(c["value"] for c in claims if c["basis_refs"][0]["result_path"]==["breakdown"])
    assert len(rows)==len(frame)
    if case=="zero_reverse":assert all(r["required_change"] is None for r in rows) and "未知" in answer["body"]
    elif reverse:assert sum(r["required_change"] for r in rows)==pytest.approx(300)
    elif case=="numeric":assert sum(r["change"] for r in rows)==pytest.approx(10)
    else:assert sum(r["change"] for r in rows)==pytest.approx(110)
    assert model.calls==["describe_dataset","record_analysis_plan","what_if_simulation"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


def test_normal_app_model_scenario_reuses_actual_trained_model_and_persists(engine):
    import io,hashlib
    from tests.test_trusted_publication_native_families import _ml_frame
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    content="处理上传数据，将其命名为experiment；先训练当前回归模型，再给x加10%的模型情景均值和差值，不作因果推断。"
    specs=[{"kind":"scenario","scope":{"datasets":["experiment"],"metrics":["target"],"parameters":{"simulation_mode":"predict","simulation_feature_changes":{"x":10},"simulation_output":output}}} for output in ("baseline","projected","impact")]
    train=("regression_analysis",{"name":"experiment","target_col":"target","features":"x,z","method":"rf"})
    model=_NativeProductModel(content,"experiment","what_if_simulation",{"name":"experiment","mode":"predict","target_col":"target","feature_changes":"{\"x\":10}"},specs,preparatory_calls=[train])
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_model_scenario"
    data=_ml_frame(False).to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        ends=[json.loads(b.split("\ndata: ",1)[1]) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event: turn_end")]
        assert len(ends)==1 and ends[0]["status"]=="completed"
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"] and answer["requirement_outcomes"][0]["status"]=="answered",answer
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.publication.facts import load_receipt_result
    with use_agent_context(manager.get(sid).context):
        receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="what_if_simulation")
        _,_,raw,_=load_receipt_result(session_id=sid,receipt_id=receipt["id"])
    n=raw["effective_rows"];pred=raw["scenario_predictions"]
    assert raw["baseline"]==round(sum(pred["baseline"])/n,4) and raw["projected"]==round(sum(pred["projected"])/n,4)
    assert raw["model_identity"]["kind"]=="regression" and raw["model_reused"] is True
    assert model.calls==["describe_dataset","record_analysis_plan","regression_analysis","what_if_simulation"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


@pytest.mark.parametrize("strategy",["keep","drop","fill_mean","fill_mode","fill_constant"])
def test_normal_app_cleaning_actual_new_table_partial_save_refresh_export(engine,strategy):
    import io,hashlib
    import pandas as pd
    from tests.test_trusted_publication_native_families import _operation_spec
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;args={"name":"experiment","missing_strategy":strategy,"fill_value":"0"}
    content="处理上传数据，将其命名为experiment；按指定缺失策略清洗全部列，保留新表和未解决缺失。"
    model=_NativeProductModel(content,"experiment","clean_data",args,[_operation_spec("clean_data",args,["experiment"])])
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_cleaning_"+strategy
    frame=pd.DataFrame({"amount":[1.,None],"text":["a",None]});data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    partial=strategy in {"fill_mean","fill_median"}
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("partial" if partial else "answered"),answer
    req=answer["source_snapshot"]["requirements"][0];assert req["effect_ids"] and not req["claim_ids"]
    effect=next(e for e in answer["source_snapshot"]["effects"] if e["id"]==req["effect_ids"][0])
    handling=effect["details"]["missing_handling"]
    assert handling["filled"]==(0 if strategy in {"keep","drop"} else 1 if partial else 2)
    assert handling["remaining"]==(2 if strategy=="keep" else 1 if partial else 0)
    assert ("操作部分完成" if partial else "操作完成") in answer["body"] and "text" in answer["body"]
    from data_agent.agent.context import use_agent_context
    with use_agent_context(manager.get(sid).context):
        child=manager.get(sid).context.workspace.get(effect["object"]["name"])
        assert int(child.isna().sum().sum())==handling["remaining"]
        if strategy in {"fill_mean","fill_median","fill_mode"}:assert child["amount"].tolist()==[1.,1.]
        elif strategy=="fill_constant":assert child["amount"].tolist()==[1.,0.]
        elif strategy=="drop":assert len(child)==1
        assert int(manager.get(sid).context.workspace.get("experiment").isna().sum().sum())==2
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="clean_data")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and receipt["required_delivery_ids"]


@pytest.mark.parametrize("kind",["numeric","datetime","bool","numeric_with_suffix","category"])
def test_normal_app_type_conversion_actual_new_table_partial_save_refresh_export(engine,kind):
    import io,hashlib
    import pandas as pd
    from tests.test_trusted_publication_native_families import _operation_spec
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;args={"name":"experiment","column":"value","target_type":kind}
    content="处理上传数据，将其命名为experiment；按指定类型转换，保留新表并报告未转换坏值。"
    model=_NativeProductModel(content,"experiment","apply_type_conversion",args,[_operation_spec("apply_type_conversion",args,["experiment"])])
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_conversion_"+kind
    values={"numeric":["1","bad"],"datetime":["2026-10-10","bad"],"bool":["yes","unknown"],"numeric_with_suffix":["1元","bad"],"category":["a","b"]}[kind]
    frame=pd.DataFrame({"value":values});data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    partial=kind!="category"
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("partial" if partial else "answered"),answer
    req=answer["source_snapshot"]["requirements"][0];assert req["effect_ids"] and not req["claim_ids"]
    effect=next(e for e in answer["source_snapshot"]["effects"] if e["id"]==req["effect_ids"][0])
    audit=effect["details"]["conversion_audit"][0]
    assert audit["converted_values"]==(1 if partial else 2) and audit["conversion_failures"]==(1 if partial else 0)
    assert audit["original_missing"]==0 and audit["new_missing"]==(1 if kind in {"numeric","datetime"} else 0)
    assert ("操作部分完成" if partial else "操作完成") in answer["body"] and "value" in answer["body"]
    from data_agent.agent.context import use_agent_context
    with use_agent_context(manager.get(sid).context):
        child=manager.get(sid).context.workspace.get(effect["object"]["name"])["value"]
        assert int(child.isna().sum())==audit["new_missing"]
        if kind=="category":assert str(child.dtype)=="category" and child.tolist()==["a","b"]
        elif kind in {"bool","numeric_with_suffix"}:assert child.iloc[1]==values[1]
        assert manager.get(sid).context.workspace.get("experiment")["value"].tolist()==values
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="apply_type_conversion")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and receipt["required_delivery_ids"]


@pytest.mark.parametrize("wire",["structured","legacy"])
def test_normal_app_transform_merge_two_uploads_actual_parents_sse_save_export(engine,wire):
    import io,hashlib
    from tests.test_trusted_publication_native_families import _operation_spec
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    from data_agent.llm.client import Response
    _,cfg=engine
    args={"name":"experiment","operation":"merge"}
    if wire=="legacy":args["params"]='{"other_name":"second","on":"key","how":"outer"}'
    else:args.update(other_name="second",merge_on="key",merge_how="outer")
    content="加载两份输入，分别将其命名为experiment和将其命名为second；仅按key外连接并保留真实新表。"
    class MergeModel(_NativeProductModel):
        def chat(self,messages,system="",**kw):
            if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
                return Response(text=encode({"intent_type":"directed_analysis","requested_outputs":[{"kind":"result","exact_span":content,"business_scope":{"datasets":["experiment","second"]}}],"upload_bindings":[{"upload_id":ticket["upload_id"],"dataset":name,"relation":"new","exact_span":"将其命名为"+name} for name,ticket in self.tickets.items()]}))
            response=super().chat(messages,system=system,**kw)
            for call in response.tool_calls:
                if call.name=="record_analysis_plan":call.arguments["plan_json"]["method_plan"][0]["dataset_inputs"]=["experiment","second"]
            return response
    model=MergeModel(content,"experiment","transform_data",args,[_operation_spec("transform_data",args,["experiment","second"])]);model.tickets={}
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_transform_merge_"+wire
    with app.test_client() as http:
        for name,data in [("experiment",b"key,amount\n1,10\n2,20\n"),("second",b"key,extra\n2,100\n3,200\n")]:
            ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),name+".csv")},content_type="multipart/form-data").get_json()
            assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.tickets[name]=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":list(model.tickets.values())})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"] and answer["requirement_outcomes"][0]["status"]=="answered",answer
    req=answer["source_snapshot"]["requirements"][0];assert req["effect_ids"] and not req["claim_ids"]
    effect=next(e for e in answer["source_snapshot"]["effects"] if e["id"]==req["effect_ids"][0])
    assert set(effect["before"]["source_data_identities"])=={"experiment","second"}
    assert len(effect["object"]["identity"]["parent_version_ids"])==2
    from data_agent.agent.context import use_agent_context
    with use_agent_context(manager.get(sid).context):
        child=manager.get(sid).context.workspace.get(effect["object"]["name"])
        assert child["key"].tolist()==[1,2,3] and child.loc[child["key"]==2,"extra"].iloc[0]==100
        assert child["amount"].notna().sum()==2 and child["extra"].notna().sum()==2
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


@pytest.mark.parametrize("delivery",["operation","table"])
def test_normal_app_transform_resample_partial_actual_values_sse_save_refresh_export(engine,delivery):
    import io,hashlib
    import pandas as pd
    from tests.test_trusted_publication_native_families import _operation_spec
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;args={"name":"experiment","operation":"resample","date_col":"day","freq":"D","resample_agg":{"amount":"sum"}}
    content="处理上传数据，将其命名为experiment；按日重采样，保留真实零、未知值、新表与未覆盖的原范围。"
    specs=[_operation_spec("transform_data",args,["experiment"])] if delivery=="operation" else [{"kind":"table","scope":{"datasets":["experiment"]}}]
    model=_NativeProductModel(content,"experiment","transform_data",args,specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_resample_"+delivery
    frame=pd.DataFrame({"day":["2026-10-01","2026-10-01","2026-10-03","2026-10-04","bad"],"amount":[1.,None,None,0.,100.]});data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]=="partial",answer
    req=answer["source_snapshot"]["requirements"][0]
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="transform_data")
    effect=next(e for e in answer["source_snapshot"]["effects"] if e["receipt_id"]==receipt["id"])
    assert effect["details"]["resample_audit"]=={"source_rows":5,"effective_rows":4,"excluded_rows":1,"missing_date_rows":0,"invalid_date_rows":1}
    if delivery=="operation":assert req["effect_ids"] and not req["claim_ids"] and "操作部分完成" in answer["body"]
    else:
        claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
        table=next(c for c in claims if c["basis_refs"][0]["result_path"]==["measurement_records"])
        assert [r["amount"] for r in table["value"]]==[1.,None,None,0.] and "未知" in answer["body"]
    from data_agent.agent.context import use_agent_context
    with use_agent_context(manager.get(sid).context):
        child=manager.get(sid).context.workspace.get(effect["object"]["name"])
        assert child["amount"].fillna(-999).tolist()==[1.,-999,-999,0.]
        assert len(manager.get(sid).context.workspace.get("experiment"))==5
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and receipt["required_delivery_ids"]


@pytest.mark.parametrize("case",["regular","constant","two","single","missing","nonfinite"])
def test_normal_app_distribution_actual_values_unknown_inference_sse_save_refresh_export(engine,case):
    import io,hashlib
    import pandas as pd
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;args={"name":"experiment","columns":"amount"}
    content="处理上传数据，将其命名为experiment；交付amount均值和完整分布统计，保留未知推断与排除范围。"
    scope={"datasets":["experiment"],"metrics":["amount"]}
    specs=[{"kind":"measurement","scope":dict(scope,quantity="mean")},{"kind":"table","scope":scope}]
    model=_NativeProductModel(content,"experiment","distribution_analysis",args,specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_distribution_"+case
    values={"regular":[1.,2.,3.,4.],"constant":[5.,5.,5.],"two":[1.,3.],"single":[7.],"missing":[None,None],"nonfinite":[1.,float("inf"),3.]}[case]
    frame=pd.DataFrame({"amount":pd.Series(values,dtype=float)});data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
        html_export=http.get("/api/sessions/"+sid+"/export?format=html").get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("answered" if case=="regular" else "partial"),answer
    req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    table=next(c for c in claims if c["basis_refs"][0]["result_path"]==["amount"])
    mean=next(c for c in claims if c["basis_refs"][0]["result_path"]==["amount","mean"])
    expected={"regular":2.5,"constant":5.,"two":2.,"single":7.,"missing":None,"nonfinite":2.}[case]
    assert table["value"]["mean"]==mean["value"]==expected
    assert table["value"]["quantile_interpolation"]=="linear"
    assert [table["value"]["quantiles"][k] for k in ["min","25%","50%","75%","max"]]=={
        "regular":[1.,1.75,2.5,3.25,4.],"constant":[5.]*5,"two":[1.,1.5,2.,2.5,3.],
        "single":[7.]*5,"missing":[None]*5,"nonfinite":[1.,1.5,2.,2.5,3.]}[case]
    assert table["value"]["observation"]["excluded_nonfinite"]==(1 if case=="nonfinite" else 0)
    if case!="regular":assert table["value"]["normality_test"]["p_value"] is None and "未知" in answer["body"]
    else:assert table["value"]["normality_test"]["conclusion"]=="not_rejected"
    assert "不能证明正态" in answer["body"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="distribution_analysis")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==2

    html_body=(cfg.sessions_resolved.parent/html_export["artifact_path"]).read_text(encoding="utf-8")
    assert "quantile_interpolation" not in answer["body"] and '"normality_test"' not in answer["body"]
    assert "总体标准差" in answer["body"] and "75%分位数" in answer["body"] and "非有限值排除数" in answer["body"]
    assert "<table>" in html_body and "Shapiro–Wilk" in html_body
    assert ("未拒绝正态性" if case=="regular" else "未知") in answer["body"]
    if case=="regular":assert "0.9718770585603881" in answer["body"]
    if case=="nonfinite":assert "原范围" in answer["body"]

    _s3_distribution_id_save("normal_distribution_"+case,dict(case=case,raw_hex=data.hex(),ticket=ticket,events=events,answer=answer,saved=saved,refreshed=refreshed,table=table,html=html_body,session_dir=str(cfg.sessions_resolved/sid),provider_calls=0))


@pytest.mark.parametrize("case",["ordered","sets","aggregate","rates","missing","zero","inferred"])
def test_normal_app_funnel_actual_upload_exact_plan_full_results_sse_save_refresh_export(engine,case):
    import io,hashlib
    import pandas as pd
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    content="分析上传数据，将其命名为experiment；交付指定漏斗的步骤、整体比例和分组，保留未知与方法边界。"
    if case in {"ordered","sets"}:
        frame=pd.DataFrame({"uid":[1]*3,"event":["B","A","B"],"time":["2026-01-01 09:00","2026-01-01 10:00","2026-01-01 11:00"]})
        args={"mode":"steps","user_col":"uid","event_col":"event","steps":"A,B","time_col":"time" if case=="ordered" else ""}
        expected=[1,1];overall=1.
    elif case=="rates":
        frame=pd.DataFrame({"A":[1.]*100,"B":[1.]*10+[0.]*90,"dim":["X"]*10+["Y"]*90})
        args={"mode":"rates","rate_cols":"A,B","dimension":"dim"};expected=[None,None];overall=.1
    else:
        frame=pd.DataFrame({"step":["A","B","A","B"],"count":[10,10,90,0],"dim":["X","X","Y","Y"]})
        args={"mode":"aggregate","step_col":"step","count_col":"count","steps":"A,B","dimension":"dim"};expected=[100,10];overall=.1
        if case=="missing":frame=frame.iloc[[0,2]];expected=[100,None];overall=None
        if case=="zero":frame["count"]=0;expected=[0,0];overall=None
        if case=="inferred":args["steps"]=""
    params={"funnel_mode":args["mode"],"funnel_steps":args.get("steps",""),"funnel_dimension":args.get("dimension","")}
    scope={"datasets":["experiment"],"parameters":params}
    specs=[{"kind":"table","scope":dict(scope,parameters=dict(params,funnel_output="steps"))},
           {"kind":"measurement","scope":dict(scope,quantity="value",parameters=dict(params,funnel_output="overall_conversion"))}]
    if args.get("dimension"):specs.append({"kind":"table","scope":dict(scope,parameters=dict(params,funnel_output="dimension_funnels"))})
    model=_NativeProductModel(content,"experiment","funnel_analysis",dict(name="experiment",**args),specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_funnel_"+case
    data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("partial" if case in {"missing","zero"} else "answered"),answer
    req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    values={c["basis_refs"][0]["result_path"][0]:c["value"] for c in claims}
    assert [s["count"] for s in values["steps"]]==expected and values["overall_conversion"]==overall
    if args.get("dimension"):assert set(values["dimension_funnels"])=={"X","Y"}
    if case=="rates":assert "累积率列均值之比" in answer["body"] and values["steps"][1]["cumulative_rate"]==.1
    if case=="sets":assert "集合包含" in answer["body"]
    if case=="inferred":assert "降序推断" in answer["body"]
    if case in {"missing","zero"}:assert "未知" in answer["body"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="funnel_analysis")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==len(specs)


@pytest.mark.parametrize("case",["regular","excluded","month_end","event_column","duplicate","single_month"])
def test_normal_app_cohort_complete_months_actual_scope_sse_save_refresh_export(engine,case):
    import io,hashlib
    import pandas as pd
    from tests.test_trusted_publication_native_families import _cohort_axis_frame
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;frame=_cohort_axis_frame()
    if case=="excluded":frame=pd.concat([frame,pd.DataFrame({"user":[None,"u4","u5",None],"day":["2026-03-02",None,"bad-date","bad-date"]})],ignore_index=True)
    if case=="month_end":frame.loc[1,"day"]="2026-03-31"
    if case=="duplicate":frame=pd.concat([frame,frame],ignore_index=True)
    if case=="single_month":frame=frame.iloc[[0,2]]
    args={"name":"experiment","user_col":"user","time_col":"day","event_col":"type" if case=="event_column" else ""}
    content="分析上传数据，将其命名为experiment；按user和day报告首次观测月的完整去重用户留存矩阵与真实排除范围。"
    params={"cohort_user_col":"user","cohort_time_col":"day","cohort_event_col":args["event_col"]}
    specs=[{"kind":"table","scope":{"datasets":["experiment"],"parameters":dict(params,cohort_output=output)}} for output in ["cohorts","observation"]]
    model=_NativeProductModel(content,"experiment","cohort_analysis",args,specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_cohort_"+case
    data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("partial" if case=="excluded" else "answered"),answer
    req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    values={c["basis_refs"][0]["result_path"][0]:c["value"] for c in claims}
    rows=values["cohorts"];assert rows[0]["size"]==2 and rows[0]["retention"]["month_0"]==100.
    if case=="single_month":assert len(rows)==1 and rows[0]["retention"]=={"month_0":100.}
    else:
        assert rows[0]["retention"]=={"month_0":100.,"month_1":0.,"month_2":50.}
        assert rows[1]["retention"]=={"month_0":100.,"month_1":0.,"month_2":None}
        assert rows[0]["user_counts"]=={"month_0":2,"month_1":0,"month_2":1} and "未知" in answer["body"]
    audit=values["observation"]
    assert audit["source_rows"]==len(frame) and audit["excluded_rows"]==(4 if case=="excluded" else 0)
    assert audit["effective_rows"]==(2 if case=="single_month" else 8 if case=="duplicate" else 4)
    assert "首次观测" in answer["body"] and "末月可能不完整" in answer["body"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="cohort_analysis")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==2


@pytest.mark.parametrize("case",["regular","constant","singletons","missing","duplicate","single_cluster"])
def test_normal_app_segmentation_actual_clusters_unknown_std_scope_sse_save_refresh_export(engine,case):
    import io,hashlib
    import pandas as pd
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;frame=pd.DataFrame({"x":[0.,0.,10.,10.],"y":[1.,3.,11.,13.]});requested=2;expected=2
    if case=="constant":frame=pd.DataFrame({"x":[1.]*4,"y":[2.]*4});requested=3;expected=1
    elif case=="singletons":frame=pd.DataFrame({"x":[1.,10.,100.],"y":[2.,20.,200.]});requested=expected=3
    elif case=="missing":frame.loc[4]=[None,15.]
    elif case=="duplicate":frame=pd.DataFrame({"x":[0.,0.,0.,10.,10.,10.],"y":[1.,1.,1.,11.,11.,11.]})
    elif case=="single_cluster":frame=pd.DataFrame({"x":[1.,2.,3.],"y":[2.,3.,4.]});requested=expected=1
    content="分析上传数据，将其命名为experiment；按x和y聚类，交付实际非空簇、请求与实际簇数和排除范围，保留未知及方法边界。"
    args={"name":"experiment","features":"x,y","n_clusters":requested}
    params={"segmentation_features":["x","y"],"segmentation_n_clusters":requested}
    specs=[{"kind":"table","scope":{"datasets":["experiment"],"metrics":["x","y"],"parameters":dict(params,segmentation_output=output)}} for output in ["clusters","observation"]]
    specs += [{"kind":"measurement","scope":{"datasets":["experiment"],"metrics":["x","y"],"quantity":"count","parameters":dict(params,segmentation_output=output)}} for output in ["requested_n_clusters","n_clusters"]]
    model=_NativeProductModel(content,"experiment","segmentation_analysis",args,specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_seg_"+case
    data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]==("partial" if case in {"constant","singletons","missing"} else "answered"),answer
    req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    values={c["basis_refs"][0]["result_path"][0]:c["value"] for c in claims}
    assert values["requested_n_clusters"]==requested and values["n_clusters"]==expected==len(values["clusters"])
    assert all(c["size"]>0 for c in values["clusters"])
    assert values["observation"]=={"source_rows":len(frame),"effective_rows":4 if case=="missing" else len(frame),"excluded_rows":1 if case=="missing" else 0,"missing_by_feature":{"x":1 if case=="missing" else 0,"y":0}}
    assert sum(c["size"] for c in values["clusters"])==values["observation"]["effective_rows"]
    if case=="singletons":assert all(c["profile"]["x"]["std"] is None for c in values["clusters"]) and "未知" in answer["body"]
    if case=="constant":assert values["clusters"][0]["profile"]["x"]=={"mean":1.,"std":0.} and "不能制造" in answer["body"]
    if case in {"regular","missing"}:
        ordered=sorted(values["clusters"],key=lambda c:c["profile"]["x"]["mean"])
        assert [c["profile"]["y"] for c in ordered]==[{"mean":2.,"std":1.4142},{"mean":12.,"std":1.4142}]
    assert "不证明因果" in answer["body"] and "输入记录" in answer["body"]
    assert "NaN" not in answer["body"] and "Infinity" not in answer["body"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="segmentation_analysis")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==4


@pytest.mark.parametrize("case",["descending","ascending","columns","oversized","save","operation_only"])
def test_normal_app_topn_original_precision_exact_range_and_real_effect_sse_save_refresh_export(engine,case,monkeypatch):
    import io,hashlib
    import pandas as pd
    from tests.test_trusted_publication_native_families import _operation_spec
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;frame=pd.DataFrame({"id":["A","B","C","D"],"amount":[.123456789012345,.223456789012345,.323456789012345,.423456789012345]})
    ascending=case=="ascending";columns="id" if case=="columns" else "";n=10 if case=="oversized" else 2
    content="分析上传数据，将其命名为experiment；按amount交付指定记录排行，保留原值与真实范围，并按指定参数保存新表。"
    args={"name":"experiment","n":n,"ascending":ascending,"columns":columns}
    selected=["id"] if columns else ["id","amount"]
    params={"topn_sort_by":"amount","topn_ascending":ascending,"topn_n":n,"topn_columns":selected}
    specs=[{"kind":"table","scope":{"datasets":["experiment"],"metrics":selected,"parameters":dict(params,topn_output=output)}} for output in ["records","observation"]]
    specs += [{"kind":"measurement","scope":{"datasets":["experiment"],"metrics":selected,"quantity":"count","parameters":dict(params,topn_output="n")}}]
    if case in {"save","operation_only"}:
        args["save_as"]="ranked"
        if case=="operation_only":specs=[]
        specs.append(_operation_spec("top_n",args,["experiment"]))
    class RankingModel(_NativeProductModel):
        def chat(self,*a,**kw):
            response=super().chat(*a,**kw)
            if case=="save" and response.tool_calls and response.tool_calls[0].name=="top_n":
                from data_agent.llm.client import ToolCall
                response.tool_calls.append(ToolCall("rank_read_after_save","top_n",{k:v for k,v in args.items() if k!="save_as"}))
            return response
    model=RankingModel(content,"experiment","top_n",args,specs)
    from data_agent.agent.loop import AgentLoop
    parallel_batches=[];parallel=AgentLoop._execute_tools_parallel
    def observe_parallel(self,calls):
        parallel_batches.append([c.name for c in calls]);return parallel(self,calls)
    monkeypatch.setattr(AgentLoop,"_execute_tools_parallel",observe_parallel)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_tn_"+case;data=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    assert not any("top_n" in batch for batch in parallel_batches)
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]=="answered",answer
    req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    if case!="operation_only":
        values={c["basis_refs"][0]["result_path"][0]:c["value"] for c in claims}
        assert [r["id"] for r in values["records"]]==(["A","B"] if ascending else ["D","C","B","A"] if n==10 else ["D","C"])
        assert values["n"]==min(n,4) and values["observation"]=={"source_rows":4,"returned_rows":min(n,4)}
        if not columns:assert values["records"][0]["amount"]==(.123456789012345 if ascending else .423456789012345)
        assert "输入记录" in answer["body"] and "不预先舍入" in answer["body"]
    else:assert claims==[]
    if case in {"save","operation_only"}:
        assert len(req["effect_ids"])==1 and "操作完成" in answer["body"]
        effect=next(e for e in answer["source_snapshot"]["effects"] if e["id"]==req["effect_ids"][0])
        assert effect["object"]["name"]=="ranked" and effect["object"]["identity"]["parent_version_ids"]==[effect["before"]["source_data_identities"]["experiment"]["version_id"]]
        from data_agent.agent.context import use_agent_context
        context=manager.get(sid).context
        from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
        with use_agent_context(context):
            actual=context.workspace.get("ranked")
            assert actual["amount"].tolist()==[.423456789012345,.323456789012345]
            with context.bind_workspace_scope(WorkspaceScopeSnapshot(phase="synthesis",session_id=sid,allowed_datasets=frozenset())):
                stored=context.workspace._publication_top_n_result(args)
                assert [r["amount"] for r in stored["records"]]==[.423456789012345,.323456789012345]
                assert context.workspace.get("ranked") is None
    else:assert req["effect_ids"]==[]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="top_n")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==len(specs)

