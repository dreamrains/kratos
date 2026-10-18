from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: files. Shared fixtures have one owner."""
from copy import deepcopy
from data_agent.agent.publication.contracts import encode
from tests.test_trusted_publication_semantics import execute
from types import SimpleNamespace
import hashlib
import json
import pytest
from tests.support.publication_runtime import _NativeProductModel, draft, request

_QUALITY_CASES = ["clean", "constant", "all_missing", "empty", "non_finite", "tiny_bounds"]


def _quality_frame(case):
    import pandas as pd
    values = {"clean": [1.,2.,3.,4.,5.], "constant": [5.,5.,5.], "all_missing": [None,None],
        "empty": [], "non_finite": [1.,2.,float("inf"),float("-inf"),None],
        "tiny_bounds": [.00001,.00002,.00003,.00004,.00009]}[case]
    return pd.DataFrame({"x": pd.Series(values,dtype=float)})


@pytest.mark.parametrize("case", _QUALITY_CASES)
def test_quality_diagnostic_exact_scope_unknown_and_unrounded_iqr(engine, case):
    import pandas as pd
    import numpy as np
    from data_agent.tools.registry import registry
    loop,_=engine;frame=_quality_frame(case);loop.context.workspace.add("quality",frame)
    identity=loop.context.workspace.get_data_identity("quality")
    result=registry.execute("detect_data_quality",{"name":"quality"});data=result.data
    assert not (data or {}).get("error"),result.summary
    assert data["rows"]==len(frame) and data["observation"]["source_rows"]==len(frame)
    diag=data["column_diagnostics"][0];iqr=diag["iqr"]
    expected={"clean":(0,0,5,0),"constant":(0,0,3,None),"all_missing":(2,0,0,None),"empty":(0,0,0,None),"non_finite":(1,2,2,0),"tiny_bounds":(0,0,5,1)}[case]
    assert (diag["missing_count"],diag["non_finite_count"],iqr["effective_n"],iqr["outlier_count"])==expected
    assert diag["constant_status"]==("constant" if case=="constant" else "unknown" if case in {"empty","all_missing"} else "not_constant")
    assert data["total_issues"]==len(data["issues"])
    assert not any(i["type"]=="constant_column" for i in data["issues"]) if case in {"empty","all_missing"} else True
    if case=="non_finite":assert next(i for i in data["issues"] if i["type"]=="non_finite_values")["count"]==2
    if case in {"constant","all_missing","empty"}:
        assert iqr["status"]=="not_assessed" and iqr["bounds"] is None and iqr["outlier_count"] is None
    else:
        assert iqr["status"]=="computed" and iqr["quantile_interpolation"]=="linear"
        values=frame.x[np.isfinite(frame.x)];bounds=iqr["bounds"]
        assert int(((values<bounds["lower"])|(values>bounds["upper"])).sum())==iqr["outlier_count"]
        if case=="tiny_bounds":
            assert bounds["lower"]==pytest.approx(-.00001) and bounds["upper"]==pytest.approx(.00007)
            assert next(i for i in data["issues"] if i["type"]=="outliers")["bounds"]==bounds
    assert any("不表示" in text and "就绪" in text for text in data["limitations"])
    pd.testing.assert_frame_equal(loop.context.workspace.get("quality"),frame)
    assert loop.context.workspace.get_data_identity("quality")==identity


@pytest.mark.parametrize("fault", ["issues","total","missing","non_finite","duplicates","bounds","effective_n","omit_diagnostic"])
def test_quality_closed_adapter_rejects_false_diagnostic_or_scope(engine,monkeypatch,fault):
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("quality",_quality_frame("tiny_bounds"))
    rid,_=execute(loop,"detect_data_quality",{"name":"quality"});original=native.load_receipt_result
    def changed(**kwargs):
        context,receipt,result,binding=original(**kwargs);result=deepcopy(result)
        if fault=="issues":result["issues"]=[]
        elif fault=="total":result["total_issues"]=999
        elif fault=="duplicates":result.setdefault("observation",{})["duplicate_rows_count"]=999
        elif fault=="omit_diagnostic":result["column_diagnostics"]=[]
        else:
            diag=result.setdefault("column_diagnostics",[{"column":"x"}])[0]
            if fault in {"missing","non_finite"}:diag[fault+"_count"]=999
            else:diag.setdefault("iqr",{})["effective_n" if fault=="effective_n" else "bounds"]=999
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("phase", ["planning","synthesis","error"])
def test_quality_no_record_diagnostics_in_forbidden_scope(engine,phase):
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
    from data_agent.tools.registry import registry
    loop,_=engine
    with loop.context.bind_workspace_scope(WorkspaceScopeSnapshot(phase=phase)):
        result=registry.execute("detect_data_quality",{"name":"orders"})
    assert (result.data or {}).get("error"),result.summary
    assert not (result.data or {}).get("issues")


@pytest.mark.parametrize("kind", ["table","measurement"])
def test_quality_declared_product_kind_does_not_guess_from_result_shape(engine,kind):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;scope={"datasets":["orders"],"parameters":{"quality_output":"issues"}}
    if kind=="measurement":scope["quantity"]="count"
    request(loop,"交付质量问题清单",[{"kind":kind,"scope":scope}])
    execute(loop,"detect_data_quality",{"name":"orders"})
    assert bool(snapshot_for_turn(loop).as_dict()["requirements"][0]["claim_ids"])==(kind=="table")


@pytest.mark.parametrize("case", [case for case in _QUALITY_CASES if case != "constant"])
def test_normal_app_quality_actual_upload_plan_diagnosis_sse_save_refresh_export(engine,case):
    import io
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;frame=_quality_frame(case)
    content="检测上传数据的基础质量，将其命名为experiment；交付问题清单、逐列有效观测与IQR范围、原范围和问题总数，只作诊断，不宣称数据已就绪或记录必然错误。"
    specs=[{"kind":"table","scope":{"datasets":["experiment"],"parameters":{"quality_output":key}}} for key in ["issues","column_diagnostics","observation"]]
    specs.append({"kind":"measurement","scope":{"datasets":["experiment"],"quantity":"count","parameters":{"quality_output":"total_issues"}}})
    model=_NativeProductModel(content,"experiment","detect_data_quality",{"name":"experiment"},specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config["agent_manager"]=manager
    sid="s3_quality_"+case;raw=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(raw),"quality.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(raw).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][-1]["status"]=="answered",answer
    values={c["basis_refs"][0]["result_path"][0]:c["value"] for c in answer["source_snapshot"]["claims"] if c["target"]["tool"]=="detect_data_quality"}
    assert values["total_issues"]==len(values["issues"])
    assert values["observation"]["source_rows"]==len(frame)
    assert values["column_diagnostics"][0]["iqr"]["outlier_count"]==({"clean":0,"constant":None,"empty":None,"all_missing":None,"non_finite":0,"tiny_bounds":1}[case])
    assert "诊断" in answer["body"] and "就绪" in answer["body"]
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="detect_data_quality")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==4
    assert model.calls==["describe_dataset","record_analysis_plan","detect_data_quality"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


def _file_write_fault(monkeypatch,destination,phase):
    from pathlib import Path
    from data_agent.session import history
    fired=[];old_read=Path.read_bytes;previous=old_read(destination) if destination.exists() else None
    if phase=="temporary":
        method=Path.write_bytes
        def fail(path,content,*a,**kw):
            if not fired and path.parent==destination.parent and path.name.startswith(".atomic-"):
                fired.append(phase);method(path,b"PARTIAL");raise OSError("partial temporary file")
            return method(path,content,*a,**kw)
        monkeypatch.setattr(Path,"write_bytes",fail)
    elif phase in {"before_replace","after_replace"}:
        method=Path.replace
        def fail(path,target,*a,**kw):
            if not fired and Path(target).resolve()==destination.resolve():
                fired.append(phase)
                if phase=="after_replace":method(path,target,*a,**kw)
                raise OSError("injected file replacement failure")
            return method(path,target,*a,**kw)
        monkeypatch.setattr(Path,"replace",fail)
    elif phase=="hash_read":
        def fail(path,*a,**kw):
            content=old_read(path,*a,**kw)
            if not fired and path.resolve()==destination.resolve() and content!=previous:
                fired.append(phase);raise OSError("injected verification read")
            return content
        monkeypatch.setattr(Path,"read_bytes",fail)
    else:
        method=history.register_artifact
        def fail(*a,**kw):
            result=method(*a,**kw)
            artifact_type=a[2] if len(a)>2 else kw.get("artifact_type")
            artifact_path=a[1] if len(a)>1 else kw.get("path","")
            if not fired and artifact_type=="file" and str(artifact_path).endswith("/output/"+destination.name):
                fired.append(phase);raise OSError("injected file registration failure")
            return result
        monkeypatch.setattr(history,"register_artifact",fail)
    return fired


_FILE_FAILURE_CASES=[("write_file",existing,phase) for existing in [True,False] for phase in ["temporary","before_replace","after_replace","hash_read","manifest"]]+[("edit_file",True,phase) for phase in ["temporary","before_replace","after_replace","hash_read"]]


@pytest.mark.parametrize("tool,existing,phase", _FILE_FAILURE_CASES)
def test_file_write_failure_preserves_old_bytes_manifest_and_no_ghost(engine,monkeypatch,tool,existing,phase):
    from pathlib import Path
    from data_agent.tools.registry import registry
    from data_agent.session.history import register_artifact
    loop,cfg=engine;own=cfg.sessions_resolved/loop.session_id;destination=own/"output/file.txt";destination.parent.mkdir(parents=True,exist_ok=True)
    if existing:
        destination.write_bytes(b"original complete payload");register_artifact(loop.session_id,"sessions/"+loop.session_id+"/output/file.txt","file","original")
    before={p.relative_to(own).as_posix():p.read_bytes() for p in own.rglob("*") if p.is_file()}
    args={"path":"output/file.txt","content":"new complete payload"} if tool=="write_file" else {"path":"output/file.txt","old_text":"original","new_text":"new"}
    with monkeypatch.context() as fault:
        fired=_file_write_fault(fault,destination,phase);result=registry.execute(tool,args)
    assert fired==[phase],result.summary
    assert "error" in result.summary.lower() and not (result.data or {}).get("sha256")
    assert {p.relative_to(own).as_posix():p.read_bytes() for p in own.rglob("*") if p.is_file()}==before
    assert not list(destination.parent.glob(".atomic-*.tmp"))


@pytest.mark.parametrize("tool,phase",[("write_file","temporary"),("write_file","after_replace"),("write_file","manifest"),("edit_file","temporary"),("edit_file","after_replace")])
def test_normal_app_file_failure_after_formal_success_preserves_download_save_refresh_restart(engine,monkeypatch,tool,phase):
    from tests.test_trusted_publication_native_families import _operation_spec
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;initial={"path":"output/document.txt","content":"original complete payload"}
    content="写入指定文件并完成这次文件操作。"
    model=_NativeProductModel(content,None,"write_file",initial,[_operation_spec("write_file",initial,[])])
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config["agent_manager"]=manager
    sid="s3_file_failure_"+tool+"_"+phase;own=cfg.sessions_resolved/sid;destination=own/"output/document.txt"
    def turn(http):
        response=http.post("/api/chat",json={"session_id":sid,"message":model.content})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
        assert answer["body"]==saved["content"]==ends[0]["reply_content"]
        return saved,answer
    with app.test_client() as http:
        first_saved,first=turn(http);assert first["requirement_outcomes"][-1]["status"]=="answered",first
        assert len(first["source_snapshot"]["effects"])==1
        old=destination.read_bytes();url="/api/files/sessions/"+sid+"/output/document.txt";assert http.get(url).data==old
        old_files=[e for e in json.loads((own/"artifacts.json").read_bytes()) if e["type"]=="file"]
        loop=manager.get(sid);before={r["id"] for r in loop.context.analysis_state.tool_receipts if r["tool_name"]==tool}
        args={"path":"output/document.txt","content":"new complete payload"} if tool=="write_file" else {"path":"output/document.txt","old_text":"original","new_text":"new"}
        model.content="按当前新要求"+("重写" if tool=="write_file" else "编辑")+"指定文件并交付本次实际效果。";model.tool=tool;model.args=args;model.specs=[_operation_spec(tool,args,[])];model.step=0;model.calls=[]
        with monkeypatch.context() as fault:
            fired=_file_write_fault(fault,destination,phase);saved,answer=turn(http)
        assert fired==[phase] and answer["requirement_outcomes"][-1]["status"]!="answered",answer
        assert destination.read_bytes()==old and http.get(url).data==old
        assert [e for e in json.loads((own/"artifacts.json").read_bytes()) if e["type"]=="file"]==old_files
        assert read_answer(sid,first_saved["answer_ref"])==first
        assert {r["id"] for r in loop.context.analysis_state.tool_receipts if r["tool_name"]==tool}==before
        assert any(m.get("answer_ref")==saved["answer_ref"] for m in http.get("/api/sessions/"+sid).get_json()["messages"])
        exported=export_assistant_reply(sid,answer["body"],"md");assert answer["body"] in (own/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    app.config["agent_manager"]=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    with app.test_client() as http:
        assert http.get(url).data==old
        assert any(m.get("answer_ref")==saved["answer_ref"] for m in http.get("/api/sessions/"+sid).get_json()["messages"])


@pytest.mark.parametrize("structured", [True,False])
def test_normal_app_upload_load_error_preserves_prior_objects_and_never_marks_loaded(engine,monkeypatch,structured):
    import io
    from data_agent.web.app import create_app
    from data_agent.tools import data_io
    from data_agent.agent.context import use_agent_context
    from data_agent.session.workspace import workspace
    loop,cfg=engine
    before=loop.context.workspace.get_data_identity("orders")
    def fail(source,name):
        workspace.add(name,_quality_frame("clean"))
        return json.dumps({"error":"injected structured load failure","error_type":"data_load_error"}) if structured else "Error: injected structured load failure"
    monkeypatch.setattr(data_io,"load_data",fail)
    app=create_app();app.config.update(TESTING=True,agent_manager=SimpleNamespace(get_or_create=lambda **kw:loop))
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(b"x\n1\n2\n"),"broken.csv")},content_type="multipart/form-data").get_json()
        response=http.post("/api/chat",json={"session_id":loop.session_id,"message":"检测上传数据质量","uploads":[ticket]})
    assert response.status_code==422,response.get_data(as_text=True)
    record=json.loads((cfg.sessions_resolved/loop.session_id/"uploads"/ticket["upload_id"]/"upload.json").read_bytes())
    assert record["status"]=="failed" and "injected structured load failure" in record["error"]
    with use_agent_context(loop.context):
        assert workspace.get_data_identity("orders")==before
        assert not workspace.exists("broken")


@pytest.mark.parametrize("values,expected", [
    ([20260230,20261301],"category_maybe"),([20250229,20260228],"category_maybe"),
    ([20240229,20260301],"date_int_to_datetime"),([20260228,20260301],"date_int_to_datetime"),
])
def test_type_advice_integer_date_requires_valid_calendar(values,expected):
    import pandas as pd
    from data_agent.tools.data_clean import infer_column_type,apply_conversion
    source=pd.Series(values,name="event_date");info=infer_column_type(source)
    assert info["suggested_type"]==expected
    if expected=="date_int_to_datetime":assert apply_conversion(source,expected).notna().all()


_TYPE_ADVICE_CASES=[
    ("datetime",["2026-02-28","2026-03-01"],"datetime"),
    ("percentage",["12.5%","50%"],"percentage_to_float"),
    ("suffix",["2元","3元"],"numeric_with_suffix"),
    ("boolean",["yes","no"],"bool"),
    ("numeric_text",["12.5","25.2"],"numeric"),
    ("valid_integer_date",[20260228,20260301],"date_int_to_datetime"),
    ("invalid_integer_date",[20260230,20261301],"category_maybe"),
    ("category",[0,1],"category_maybe"),
    ("text",["hello","world"],None),
    ("missing",[None,None],None),
    ("non_finite",[float("inf"),float("-inf")],None),
    ("empty",[],None),
]


@pytest.mark.parametrize("case,values,expected", _TYPE_ADVICE_CASES)
def test_type_advice_exact_rules_sample_scope_and_no_mutation(engine,case,values,expected):
    import pandas as pd
    from data_agent.tools.data_clean import suggest_column_types
    from data_agent.tools.registry import registry
    loop,_=engine;frame=pd.DataFrame({"value":values});loop.context.workspace.add("advice",frame)
    identity=loop.context.workspace.get_data_identity("advice")
    direct=suggest_column_types("advice");assert isinstance(direct,str);result=json.loads(direct)
    assert result==registry.execute("suggest_column_types",{"name":"advice"}).data
    assert result["dataset"]=="advice" and result["columns_analyzed"]==1
    assert result["observation"]["source_rows"]==len(frame)
    assert result["observation"]["max_unique_values_per_column"]==20
    assert result["observation"]["max_displayed_values_per_column"]==8
    assert [i["suggested_type"] for i in result["suggestions"]]==([expected] if expected else [])
    assert "建议" in "；".join(result["limitations"]) and "样本" in "；".join(result["limitations"])
    pd.testing.assert_frame_equal(loop.context.workspace.get("advice"),frame)
    assert loop.context.workspace.get_data_identity("advice")==identity


@pytest.mark.parametrize("fault", ["suggestion","confidence","sample","count","rows","sample_scope","limitations","dataset"])
def test_type_advice_closed_adapter_rejects_false_rule_scope_or_source(engine,monkeypatch,fault):
    import pandas as pd
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("advice",pd.DataFrame({"value":[0,1]}))
    rid,_=execute(loop,"suggest_column_types",{"name":"advice"});original=native.load_receipt_result
    def changed(**kwargs):
        context,receipt,result,binding=original(**kwargs);result=deepcopy(result)
        if fault=="suggestion":result["suggestions"][0]["suggested_type"]="datetime"
        elif fault=="confidence":result["suggestions"][0]["confidence"]="high"
        elif fault=="sample":result["suggestions"][0]["sample"]=["forged"]
        elif fault=="count":result["columns_analyzed"]=999
        elif fault=="rows":result.setdefault("observation",{})["source_rows"]=999
        elif fault=="sample_scope":result.setdefault("observation",{})["max_unique_values_per_column"]=999
        elif fault=="dataset":result["dataset"]="orders"
        else:result["limitations"]=[]
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("phase", ["planning","synthesis","error"])
def test_type_advice_no_samples_in_forbidden_scope(engine,phase):
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
    from data_agent.tools.registry import registry
    loop,_=engine
    with loop.context.bind_workspace_scope(WorkspaceScopeSnapshot(phase=phase)):
        result=registry.execute("suggest_column_types",{"name":"orders"})
    assert (result.data or {}).get("error") or "Error" in result.summary
    assert not (result.data or {}).get("suggestions")


@pytest.mark.parametrize("kind", ["table","measurement"])
def test_type_advice_formal_kind_is_table(engine,kind):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;scope={"datasets":["orders"],"parameters":{"type_advice_output":"suggestions"}}
    if kind=="measurement":scope["quantity"]="count"
    request(loop,"交付类型建议",[{"kind":kind,"scope":scope}])
    execute(loop,"suggest_column_types",{"name":"orders"})
    assert bool(snapshot_for_turn(loop).as_dict()["requirements"][0]["claim_ids"])==(kind=="table")


@pytest.mark.parametrize("case,values",[("category",[0,1]),("invalid_date",[20260230,20261301]),("valid_date",[20260228,20260301]),("empty",[]),("keep",[12.5,25.2]),("non_finite",[float("inf"),float("-inf")])])
def test_normal_app_type_advice_upload_plan_sse_save_refresh_export(engine,case,values):
    import io
    import pandas as pd
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;frame=pd.DataFrame({"value":values})
    content="分析上传数据的类型建议，将其命名为experiment；交付建议和建议所用样本范围。"
    specs=[{"kind":"table","scope":{"datasets":["experiment"],"parameters":{"type_advice_output":key}}} for key in ["suggestions","observation"]]
    model=_NativeProductModel(content,"experiment","suggest_column_types",{"name":"experiment"},specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config["agent_manager"]=manager
    sid="s3_type_advice_"+case;raw=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(raw),"advice.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(raw).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][-1]["status"]=="answered",answer
    claims=[c for c in answer["source_snapshot"]["claims"] if c["target"]["tool"]=="suggest_column_types"]
    results={c["basis_refs"][0]["result_path"][0]:c["value"] for c in claims}
    assert results["observation"]["source_rows"]==len(frame)
    expected={"category":"category_maybe","invalid_date":"category_maybe","valid_date":"date_int_to_datetime","empty":None,"keep":None,"non_finite":None}[case]
    assert [s["suggested_type"] for s in results["suggestions"]]==([expected] if expected else [])
    assert all(c["limitations"] for c in claims)
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="suggest_column_types")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==2
    assert model.calls==["describe_dataset","record_analysis_plan","suggest_column_types"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


def test_type_advice_bounded_unique_sample_and_visible_values(engine):
    import pandas as pd
    from data_agent.tools.registry import registry
    loop,_=engine;frame=pd.DataFrame({"value":[str(i+0.5) for i in range(100)]*3+[None]})
    loop.context.workspace.add("advice",frame)
    first=registry.execute("suggest_column_types",{"name":"advice"}).data
    second=registry.execute("suggest_column_types",{"name":"advice"}).data
    assert first==second
    assert first["observation"]["source_rows"]==301
    assert len(first["suggestions"][0]["sample"])==8
    assert set(first["suggestions"][0]["sample"])<=set(frame.value.dropna())
    assert first["suggestions"][0]["suggested_type"]=="numeric"


def test_type_advice_missing_dataset_is_error_without_data_or_suggestions(engine):
    from data_agent.tools.registry import registry
    result=registry.execute("suggest_column_types",{"name":"does_not_exist"})
    assert result.data["error"] and "suggestions" not in result.data


def test_type_advice_receipt_cannot_publish_after_source_replacement(engine):
    import pandas as pd
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("advice",pd.DataFrame({"value":[0,1]}))
    rid,_=execute(loop,"suggest_column_types",{"name":"advice"})
    assert native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    loop.context.workspace.add("advice",pd.DataFrame({"value":[20260228,20260301]}))
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


def test_interpret_dataset_complete_metrics_and_true_count(engine):
    import pandas as pd
    from data_agent.tools.registry import registry
    loop,_=engine;frame=pd.DataFrame({f"metric_{i}":[float(i+1),float(i+2),float(i+3)] for i in range(10)})
    loop.context.workspace.add("interpret",frame)
    result=registry.execute("interpret_dataset",{"name":"interpret"}).data
    assert {m["column"] for m in result["columns_classified"]["key_metrics"]}==set(frame.columns)
    assert result["analysis_signals"]["metric_count"]==10


def test_interpret_dataset_time_range_keeps_hour_and_timezone(engine):
    import pandas as pd
    from data_agent.tools.registry import registry
    loop,_=engine;dates=pd.date_range("2026-10-01 12:00",periods=3,freq="h",tz="Asia/Shanghai")
    loop.context.workspace.add("interpret",pd.DataFrame({"event_time":dates,"value":[1.,2.,3.]}))
    result=registry.execute("interpret_dataset",{"name":"interpret"}).data
    assert result["time_range"]["min"]==dates[0].isoformat()
    assert result["time_range"]["max"]==dates[-1].isoformat()


def test_interpret_dataset_complete_target_relationships(engine):
    import pandas as pd
    from data_agent.tools.registry import registry
    loop,_=engine;loop.context.workspace.add("interpret",pd.DataFrame({"user_id":[1,2,3]}))
    for i in range(6):loop.context.workspace.add("peer_"+str(i),pd.DataFrame({"user_id":[1,2,3],"value":[i,i+1,i+2]}))
    result=registry.execute("interpret_dataset",{"name":"interpret"}).data
    assert {h["other_dataset"] for h in result["cross_dataset_hints"]}=={"peer_"+str(i) for i in range(6)}


@pytest.mark.parametrize("case",["hourly","bad_date","threshold","missing","empty"])
def test_interpret_heuristics_preserve_original_and_audit_date_scope(engine,case):
    import pandas as pd
    from data_agent.tools.registry import registry
    loop,_=engine
    values={"hourly":["2026-10-01 01:00:00","2026-10-01 02:00:00","2026-10-01 03:00:00"],"bad_date":["2026-10-01"]*20+["bad"],"threshold":["2026-10-01"]*4+["bad"],"missing":[None,None],"empty":[]}[case]
    frame=pd.DataFrame({"event_time":pd.Series(values,dtype="object"),"amount":list(range(len(values)))})
    loop.context.workspace.add("interpret",frame);identity=loop.context.workspace.get_data_identity("interpret")
    result=registry.execute("interpret_dataset",{"name":"interpret"}).data
    audit=result["date_observation"]["event_time"]
    assert audit["source_rows"]==len(values) and audit["original_dtype"]=="object"
    assert audit["missing_count"]==(2 if case=="missing" else 0)
    assert audit["parse_failed_count"]==(1 if case in {"bad_date","threshold"} else 0)
    assert audit["sample_size"]==min(20,len([v for v in values if v is not None]))
    assert audit["time_candidate"]==(case in {"hourly","bad_date","threshold"})
    assert result["heuristic_status"]=="candidate_only"
    assert result["grain_basis"] and result["column_role_basis"] and result["theme_basis"]
    assert "不可做" not in result["grain_hint"] and "确认此为" not in result["grain_hint"]
    if case=="hourly":assert "01:00:00" in result["time_range"]["min"]
    if case in {"bad_date","threshold"}:assert result["time_range"]["range_complete"] is False
    assert result["limitations"] and all(a["status"]=="candidate_only" for a in result["suggested_analyses"])
    pd.testing.assert_frame_equal(loop.context.workspace.get("interpret"),frame)
    assert loop.context.workspace.get_data_identity("interpret")==identity


@pytest.mark.parametrize("fault",["theme","grain","basis","date_count","shape","roles","limitations","peer"])
def test_interpret_closed_adapter_rejects_tampered_heuristic_or_range(engine,monkeypatch,fault):
    import pandas as pd
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("interpret",pd.DataFrame({"event_time":["2026-10-01","2026-10-02"],"amount":[1,2]}))
    rid,_=execute(loop,"interpret_dataset",{"name":"interpret"});original=native.load_receipt_result
    assert native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    def changed(**kwargs):
        context,receipt,result,binding=original(**kwargs);result=deepcopy(result)
        if fault=="theme":result["theme"]="forged"
        elif fault=="grain":result["grain"]="individual"
        elif fault=="basis":result["grain_basis"]={"forged":True}
        elif fault=="date_count":result["date_observation"]["event_time"]["parse_failed_count"]=999
        elif fault=="shape":result["data_shape"]["rows"]=999
        elif fault=="roles":result["columns_classified"]["time_columns"]=[]
        elif fault=="peer":result["cross_dataset_hints"]=[{"other_dataset":"hidden"}]
        else:result["limitations"]=[]
        return context,receipt,result,binding
    monkeypatch.setattr(native,"load_receipt_result",changed)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


def test_interpret_all_actual_peer_reads_bound_before_dispatch_and_peer_replacement_rejected(engine):
    import pandas as pd
    from data_agent.agent.publication import native
    loop,_=engine;loop.context.workspace.add("peer",pd.DataFrame({"channel":["A","B"],"extra":[1,2]}))
    binding=loop._capture_tool_execution_binding("interpret_dataset",{"name":"orders"})
    assert "peer" in binding["input_data_identities"]
    rid,_=execute(loop,"interpret_dataset",{"name":"orders"})
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    assert set(receipt["data_identities"])=={"orders","peer"}
    assert native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
    loop.context.workspace.add("peer",pd.DataFrame({"channel":["C"],"extra":[9]}))
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("phase",["planning","synthesis","error"])
def test_interpret_forbidden_scope_leaks_no_candidates(engine,phase):
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
    from data_agent.tools.registry import registry
    loop,_=engine
    with loop.context.bind_workspace_scope(WorkspaceScopeSnapshot(phase=phase)):
        result=registry.execute("interpret_dataset",{"name":"orders"})
    assert (result.data or {}).get("error") or "Error" in result.summary
    assert not (result.data or {}).get("columns_classified")


@pytest.mark.parametrize("case",["hourly","bad_date","empty"])
def test_normal_app_interpret_upload_plan_sse_save_refresh_export(engine,case):
    import io
    import pandas as pd
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    values={"hourly":["2026-10-01 01:00:00","2026-10-01 02:00:00","2026-10-01 03:00:00"],"bad_date":["2026-10-01"]*20+["bad"],"empty":[]}[case]
    frame=pd.DataFrame({"event_time":values,"amount":list(range(len(values)))})
    content="分析上传数据，将其命名为experiment；交付列角色、粒度和主题候选及日期解析范围，具体分析仍需核对方法前提。"
    keys=["columns_classified","grain_basis","theme_basis","date_observation","time_range","cross_dataset_hints"]
    specs=[{"kind":"table","scope":{"datasets":["experiment"],"parameters":{"interpret_output":key}}} for key in keys]
    model=_NativeProductModel(content,"experiment","interpret_dataset",{"name":"experiment"},specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config["agent_manager"]=manager
    sid="s3_interpret_"+case;raw=frame.to_csv(index=False).encode("utf-8")
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(raw),"interpret.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(raw).hexdigest();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][-1]["status"]=="answered",answer
    claims=[c for c in answer["source_snapshot"]["claims"] if c["target"]["tool"]=="interpret_dataset"]
    results={c["basis_refs"][0]["result_path"][0]:c["value"] for c in claims}
    assert set(keys)<=results.keys() and all(c["limitations"] for c in claims)
    if case=="bad_date":assert results["time_range"]["range_complete"] is False
    assert results["cross_dataset_hints"]==[]
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="interpret_dataset")
    assert receipt["plan_id"] and receipt["step_id"]=="native_product" and len(receipt["required_delivery_ids"])==len(keys)
    assert model.calls==["describe_dataset","record_analysis_plan","interpret_dataset"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


@pytest.mark.parametrize("kind",["table","measurement"])
def test_interpret_formal_product_kind_and_exact_output(engine,kind):
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,_=engine;scope={"datasets":["orders"],"parameters":{"interpret_output":"columns_classified"}}
    if kind=="measurement":scope["quantity"]="count"
    request(loop,"交付列角色候选",[{"kind":kind,"scope":scope}]);execute(loop,"interpret_dataset",{"name":"orders"})
    assert bool(snapshot_for_turn(loop).as_dict()["requirements"][0]["claim_ids"])==(kind=="table")


def test_interpret_execution_scope_excludes_hidden_peers(engine):
    import pandas as pd
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot
    from data_agent.tools.registry import registry
    loop,_=engine;loop.context.workspace.add("hidden",pd.DataFrame({"channel":["A","B"],"secret":[1,2]}))
    with loop.context.bind_workspace_scope(WorkspaceScopeSnapshot(phase="execution",allowed_datasets=frozenset({"orders"}))):
        result=registry.execute("interpret_dataset",{"name":"orders"}).data
    assert result["dataset_reads"]==["orders"] and not result["cross_dataset_hints"]
    assert "hidden" not in encode(result)


def test_interpret_unfrozen_peer_added_during_execution_cannot_publish(engine):
    import pandas as pd
    from data_agent.tools.registry import registry
    from data_agent.agent.publication import native
    loop,_=engine;args={"name":"orders"};binding=loop._capture_tool_execution_binding("interpret_dataset",args)
    loop.context.workspace.add("new_peer",pd.DataFrame({"channel":["A","B"]}))
    result=registry.execute("interpret_dataset",args)
    rid=loop._record_turn_tool_result("interpret_dataset",result.summary,args,"new_peer_test",result.data,execution_binding=binding)
    with pytest.raises(ValueError):native.resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("case",["75percent","native_tz","identifier","keywords"])
def test_interpret_adjacent_heuristic_candidates_and_date_observations(engine,case):
    import pandas as pd
    from data_agent.tools.registry import registry
    frames={"75percent":pd.DataFrame({"when":["2026-10-01"]*3+["bad"]}),
        "native_tz":pd.DataFrame({"when":pd.to_datetime(["2026-10-01 12:34:56.123456789+08:00",None])}),
        "identifier":pd.DataFrame({"user_id":[1,2,3,4,4],"amount":[1,2,3,4,5]}),
        "keywords":pd.DataFrame({"total_amount":[1,2,3],"sum_items":[4,5,6]})}
    loop,_=engine;frame=frames[case];loop.context.workspace.add("interpret",frame)
    data=registry.execute("interpret_dataset",{"name":"interpret"}).data
    assert "可做" not in data["grain_hint"] and "确认此为" not in data["grain_hint"]
    if case=="75percent":assert data["date_observation"]["when"]["sample_parseable_count"]==3 and data["time_range"] is None
    if case=="native_tz":assert data["time_range"]["min"]=="2026-10-01T12:34:56.123456789+08:00" and data["date_observation"]["when"]["missing_count"]==1
    if case=="identifier":assert data["grain"]=="individual" and "不保证实体唯一性" in data["grain_basis"]["rule"]
    if case=="keywords":assert data["grain"]=="aggregate" and "不证明实际聚合" in data["grain_basis"]["rule"]
    pd.testing.assert_frame_equal(loop.context.workspace.get("interpret"),frame)


class _InterpretMultiModel(_NativeProductModel):
    def chat(self,messages,system="",tools=None,**kw):
        from data_agent.llm.client import Response
        if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
            return Response(text=encode({"intent_type":"directed_analysis","requested_outputs":[{"kind":"result","exact_span":self.content,"business_scope":{"datasets":["experiment","peer"]}}],"upload_bindings":[{"upload_id":ticket["upload_id"],"dataset":name,"relation":"new","exact_span":"将其命名为"+name} for name,ticket in zip(["experiment","peer"],self.tickets)]}))
        response=super().chat(messages,system,tools,**kw)
        for call in response.tool_calls or []:
            if call.name=="record_analysis_plan":call.arguments["plan_json"]["method_plan"][0]["dataset_inputs"]=["experiment","peer"]
        return response


def test_normal_app_interpret_two_actual_upload_sources_plan_sse_save_refresh_export(engine):
    import io
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;content="解释第一份上传数据，将其命名为experiment；第二份将其命名为peer；交付这两份来源之间的候选共享列与原范围，不直接批准合并。"
    specs=[{"kind":"table","scope":{"datasets":["experiment","peer"],"parameters":{"interpret_output":"cross_dataset_hints"}}}]
    model=_InterpretMultiModel(content,"experiment","interpret_dataset",{"name":"experiment"},specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config["agent_manager"]=manager
    sid="s3_interpret_two_sources";raws=[b"user_id,amount\n1,3\n2,4\n",b"user_id,visits\n1,2\n2,1\n"]
    with app.test_client() as http:
        tickets=[http.post("/api/upload",data={"file":(io.BytesIO(raw),f"source{i}.csv")},content_type="multipart/form-data").get_json() for i,raw in enumerate(raws)]
        assert all(t["sha256"]=="sha256:"+hashlib.sha256(raw).hexdigest() for t,raw in zip(tickets,raws));model.tickets=tickets
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":tickets})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"] and answer["requirement_outcomes"][-1]["status"]=="answered",answer
    claim=next(c for c in answer["source_snapshot"]["claims"] if c["basis_refs"][0].get("result_path")==["cross_dataset_hints"])
    assert claim["value"]==[{"other_dataset":"peer","shared_columns":["user_id"],"rows_other":2,"overlap_pct":1.0}]
    receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="interpret_dataset")
    assert set(receipt["data_identities"])=={"experiment","peer"} and receipt["step_id"]=="native_product"
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


@pytest.mark.parametrize("raw,limit,max_chars,expected",[
    (b"alpha\nbeta\ngamma\n",1,2000,"alpha\n"),
    (b"alpha\nbeta\ngamma\n",2,2000,"alpha\nbeta\n"),
    (b"alpha\nbeta\ngamma\n",None,2000,"alpha\nbeta\ngamma\n"),
    (b"alpha\nbeta",1,3,"alp"),
    (b"alpha\n"+b"x"*3000,1,2000,"alpha\n"),
    (b"",1,2000,""),
    (b"\n\nbeta",1,2000,"\n"),
    ("你😊\r\n二\r第三\n".encode("utf-8"),2,2000,"你😊\n二\n"),
])
def test_read_page_real_content_line_character_limits_and_raw_identity(engine,raw,limit,max_chars,expected):
    from data_agent.tools.file_ops import read_file
    from data_agent.tools.registry import registry
    _,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True);path=root/"read.txt";path.write_bytes(raw)
    args={"path":"read.txt","limit":limit,"max_chars":max_chars}
    direct=read_file(**args);assert isinstance(direct,str);page=json.loads(direct)
    assert page==registry.execute("read_file",args).data
    assert page["schema_version"]=="file_page.v1" and page["content"]==expected
    assert page["sha256"]==hashlib.sha256(raw).hexdigest() and page["offset"]==0
    assert page["end_offset"]==page["returned_chars"]==len(expected)
    assert page["total_chars"]==len(raw.decode("utf-8").replace("\r\n","\n").replace("\r","\n"))
    assert page["limit"]==limit and page["max_chars"]==max_chars
    assert page["returned_lines"]==len(expected.splitlines())
    assert page["next_offset"]==(len(expected) if len(expected)<page["total_chars"] else None)
    assert "more lines" not in page["content"] and path.read_bytes()==raw


@pytest.mark.parametrize("argument,value",[("limit",-1),("limit",0),("limit",True),("limit",1.5),("limit","1"),("offset",-1),("offset",True),("offset",1.5),("max_chars",0),("max_chars",2001),("max_chars",True),("max_chars",1.5)])
def test_read_page_invalid_bounds_rejected_by_direct_and_registry(engine,argument,value):
    from data_agent.tools.file_ops import read_file
    from data_agent.tools.registry import registry
    _,cfg=engine;cfg.project_resolved.mkdir(parents=True,exist_ok=True);(cfg.project_resolved/"read.txt").write_text("secret",encoding="utf-8")
    args={"path":"read.txt",argument:value};result=registry.execute("read_file",args)
    assert "secret" not in result.summary and ((result.data or {}).get("error") or result.summary.startswith("Error:"))
    assert read_file(**args).startswith("Error:")


@pytest.mark.parametrize("offset",[0,2,5])
def test_read_page_actual_offset_and_eof_range(engine,offset):
    from data_agent.tools.file_ops import read_file
    _,cfg=engine;cfg.project_resolved.mkdir(parents=True,exist_ok=True);(cfg.project_resolved/"read.txt").write_text("a\nb\nc",encoding="utf-8")
    page=json.loads(read_file("read.txt",offset=offset,limit=1,max_chars=2))
    expected="a\n" if offset==0 else "b\n" if offset==2 else ""
    assert page["content"]==expected and page["offset"]==offset and page["end_offset"]==offset+len(expected)
    assert page["next_offset"]==(offset+len(expected) if offset+len(expected)<5 else None)


def test_read_page_no_mix_after_source_replacement_and_no_replacement_characters(engine):
    from data_agent.tools.file_ops import read_file
    _,cfg=engine;cfg.project_resolved.mkdir(parents=True,exist_ok=True);path=cfg.project_resolved/"read.txt";path.write_bytes(b"alpha\nbeta\n")
    page=json.loads(read_file("read.txt",limit=1));path.write_bytes(b"alpha\nchanged\n")
    assert "file_changed" in read_file("read.txt",offset=page["next_offset"],expected_sha256=page["sha256"])
    path.write_bytes(b"bad-utf8-\xff");result=read_file("read.txt")
    assert result.startswith("Error:") and "\ufffd" not in result


@pytest.mark.parametrize("path",["../secret.txt","sessions/other/output/secret.txt","sessions/native_contract/messages.jsonl"])
def test_read_page_preserves_workspace_and_session_permission_boundary(engine,path):
    from data_agent.tools.registry import registry
    _,cfg=engine;cfg.project_resolved.mkdir(parents=True,exist_ok=True)
    (cfg.project_resolved.parent/"secret.txt").write_text("hidden-secret",encoding="utf-8")
    other=cfg.sessions_resolved/"other"/"output";other.mkdir(parents=True,exist_ok=True);(other/"secret.txt").write_text("hidden-secret",encoding="utf-8")
    result=registry.execute("read_file",{"path":path})
    error=result.data or (json.loads(result.summary) if result.summary.startswith("{") else {})
    assert "hidden-secret" not in result.summary and (error.get("error") or result.summary.startswith("Error:"))


def test_read_page_full_unicode_reassembly_and_compaction_keeps_exact_page(engine):
    from data_agent.tools.file_ops import read_file
    from data_agent.tools.registry import ToolResult
    loop,cfg=engine;cfg.project_resolved.mkdir(parents=True,exist_ok=True)
    raw=("你😊\r\n"+"x"*2100+"\r尾\n").encode("utf-8");(cfg.project_resolved/"read.txt").write_bytes(raw)
    parts=[];offset=0;sha=hashlib.sha256(raw).hexdigest()
    for index in range(20):
        original=read_file("read.txt",offset=offset,limit=1,max_chars=700,expected_sha256=sha)
        delivered=loop._compact_tool_output(ToolResult.from_str(original),SimpleNamespace(id="read-page-"+str(index),name="read_file"))
        assert original==delivered;page=json.loads(delivered);parts.append(page["content"])
        if page["next_offset"] is None:break
        assert page["next_offset"]>offset;offset=page["next_offset"]
    else:pytest.fail("paging did not reach EOF")
    assert "".join(parts)==raw.decode("utf-8").replace("\r\n","\n").replace("\r","\n")


class _ReadPagingModel(_NativeProductModel):
    """Uses only actual tool messages to request a bounded continuation."""
    def __init__(self,content,args):
        specs=[{"kind":"measurement","scope":{"datasets":["experiment"],"quantity":"rows"}}]
        super().__init__(content,"experiment","describe_dataset",{"name":"experiment"},specs,[("read_file",args)])
        self.reading=False;self.pages=[];self.page_args=args
    def chat(self,messages,system="",tools=None,**kw):
        from data_agent.llm.client import Response,ToolCall
        if self.reading:
            last=next(m for m in reversed(messages) if m.get("role")=="tool")
            page=json.loads(last["content"]);assert page["schema_version"]=="file_page.v1";self.pages.append(page)
            if page["next_offset"] is not None:
                self.calls.append("read_file")
                return Response(tool_calls=[ToolCall("read-next-"+str(len(self.pages)),"read_file",dict(self.page_args,offset=page["next_offset"],expected_sha256=page["sha256"]))])
            self.reading=False
        response=super().chat(messages,system,tools,**kw)
        if any(c.name=="read_file" for c in response.tool_calls or []):self.reading=True
        return response


@pytest.mark.parametrize("case,raw",[("short",b"alpha\nbeta\n"),("long",b"alpha\n"+b"x"*2050+b"\nbeta\n"),("unicode","你😊\r\n二\r第三\n".encode("utf-8")),("empty",b"")])
def test_normal_app_read_page_upload_plan_tool_continuation_sse_save_refresh_export(engine,case,raw):
    import io
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;cfg.project_resolved.mkdir(parents=True,exist_ok=True);source=cfg.project_resolved/"read.txt";source.write_bytes(raw)
    content="分析上传数据，将其命名为experiment；用read_file逐页核对工作目录read.txt的文本范围，正式分析交付为上传表记录数。"
    model=_ReadPagingModel(content,{"path":"read.txt","limit":1,"max_chars":2000})
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config["agent_manager"]=manager
    sid="s3_read_page_"+case;upload=b"amount\n1\n2\n3\n"
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(upload),"data.csv")},content_type="multipart/form-data").get_json();model.ticket=ticket
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(upload).hexdigest()
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    assert "".join(p["content"] for p in model.pages)==raw.decode("utf-8").replace("\r\n","\n").replace("\r","\n")
    assert model.pages and all(p["sha256"]==hashlib.sha256(raw).hexdigest() for p in model.pages)
    assert all(p["returned_lines"]<=1 and p["returned_chars"]<=2000 and p["end_offset"]==p["offset"]+len(p["content"]) for p in model.pages)
    if case=="long":assert model.pages[0]["content"]=="alpha\n" and len(model.pages)==4
    loop=manager.get(sid);receipts=[r for r in loop.context.analysis_state.tool_receipts if r["tool_name"]=="read_file"]
    assert len(receipts)==len(model.pages) and all(r["plan_id"] and r["step_id"]=="native_product" and r["detail_ref"]["sha256"] for r in receipts)
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"] and answer["requirement_outcomes"][-1]["status"]=="answered"
    assert any(c["label"]=="记录数" and c["value"]==3 for c in answer["source_snapshot"]["claims"])
    file_claims=[c for c in answer["source_snapshot"]["claims"] if c["target"].get("tool")=="read_file"]
    assert all(c["scope"]["dataset"] is None and c["basis_refs"][0]["data_identities"]=={} for c in file_claims)
    assert not {c["id"] for c in file_claims}.intersection(answer["source_snapshot"]["requirements"][-1]["claim_ids"])
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")
    assert source.read_bytes()==raw


def test_read_page_public_schema_exposes_exact_supported_bounds():
    from data_agent.tools.registry import registry
    fields=registry.get("read_file").parameters["properties"]
    assert fields["limit"]["minimum"]==1 and set(fields["limit"]["type"])=={"integer","null"}
    assert fields["offset"]["minimum"]==0 and fields["max_chars"]["minimum"]==1 and fields["max_chars"]["maximum"]==2000


def test_read_page_offset_beyond_eof_does_not_report_reversed_range(engine):
    from data_agent.tools.file_ops import read_file
    _,cfg=engine;cfg.project_resolved.mkdir(parents=True,exist_ok=True);(cfg.project_resolved/"read.txt").write_text("abc",encoding="utf-8")
    result=read_file("read.txt",offset=4)
    assert result.startswith("Error:") and "offset" in result


def test_read_page_invalid_limit_rejected_before_file_content_read(engine,monkeypatch):
    from pathlib import Path
    from data_agent.tools.file_ops import read_file
    _,cfg=engine;cfg.project_resolved.mkdir(parents=True,exist_ok=True);path=cfg.project_resolved/"read.txt";path.write_text("secret",encoding="utf-8")
    original=Path.read_bytes;reads=[]
    def tracked(self):
        if self==path:reads.append(self)
        return original(self)
    monkeypatch.setattr(Path,"read_bytes",tracked)
    assert read_file("read.txt",limit=0).startswith("Error:") and reads==[]


def _file_spec(tool="read_file", **args):
    params={"file_scope":"current_readable","file_output":"content" if tool=="read_file" else "entries"}
    if tool=="read_file":params.update(file_path=args.get("path","read.txt"),file_offset=args.get("offset",0),file_max_chars=args.get("max_chars",2000),file_limit=args.get("limit"))
    else:params["file_pattern"]=args.get("pattern","*.txt")
    return {"kind":"table","scope":{"datasets":[],"parameters":params}}


@pytest.mark.parametrize("case",["text","empty","crlf","page","catalog","empty_catalog"])
def test_file_delivery_formal_scope(engine,case):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,read_answer
    from data_agent.session.history import load_session
    loop,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True)
    raw={"text":b"alpha\nbeta\n","empty":b"","crlf":"甲\r\n乙\r丙".encode(),"page":b"alpha\nbeta\n"}.get(case,b"alpha")
    if case!="empty_catalog":(root/"read.txt").write_bytes(raw)
    tool="list_files" if "catalog" in case else "read_file"
    args={"pattern":"*.txt"} if tool=="list_files" else {"path":"read.txt","offset":6 if case=="page" else 0,"limit":1}
    request(loop,"仅交付文件原文或文件目录",_file_spec(tool,**args))
    rid,result=execute(loop,tool,args)
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"
    assert "单位未知" not in body
    assert snap.as_dict()["data_identities"]=={}
    assert commit(loop,{"role":"assistant"},body) is None
    saved=load_session(loop.session_id)["messages"][-1]
    assert read_answer(loop.session_id,saved["answer_ref"])["body"]==body


@pytest.mark.parametrize("case",["read","empty","artifact","catalog","empty_catalog"])
def test_file_delivery_normal_app_plan_save_refresh_export(engine,case):
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True);sid="s3_file_delivery_"+case
    path="sessions/"+sid+"/output/read.txt" if case=="artifact" else "read.txt"
    fp=cfg.sessions_resolved/sid/"output/read.txt" if case=="artifact" else root/path
    if case!="empty_catalog":fp.parent.mkdir(parents=True,exist_ok=True);fp.write_bytes(b"" if case=="empty" else b"alpha\nbeta\n")
    tool="list_files" if "catalog" in case else "read_file";args={"pattern":"*.txt"} if tool=="list_files" else {"path":path,"limit":1}
    content="仅交付文件原文片段或文件目录，不计算文件内数据结论。"
    model=_NativeProductModel(content,None,tool,args,[_file_spec(tool,**args)])
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config["agent_manager"]=manager
    with app.test_client() as http:
        response=http.post("/api/chat",json={"session_id":sid,"message":content})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["requirement_outcomes"][0]["status"]=="answered",answer
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["source_snapshot"]["data_identities"]=={}
    assert model.calls==["record_analysis_plan",tool]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md")
    assert answer["body"] in (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_text(encoding="utf-8")


@pytest.mark.parametrize("fault",["content","result_sha","end_offset","path","arguments","canonical_path","session","permission","source","missing_binding"])
def test_file_delivery_rejects_tampered_receipt_range_permission_and_source(engine,fault):
    from data_agent.agent.publication.native import resolve_native_claims
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True);source=root/"read.txt";source.write_text("alpha\nbeta\n",encoding="utf-8")
    request(loop,"仅交付文件原文",_file_spec(limit=1));rid,result=execute(loop,"read_file",{"path":"read.txt","limit":1})
    receipt=loop.context.analysis_state.tool_receipts[-1]
    if fault in {"content","result_sha","end_offset","path"}:
        result[{"content":"content","result_sha":"sha256","end_offset":"end_offset","path":"path"}[fault]]={"content":"fake","result_sha":"0"*64,"end_offset":99,"path":"other.txt"}[fault]
        _tamper(loop,cfg,rid,result)
    elif fault=="arguments":receipt["arguments"]["offset"]=1
    elif fault=="canonical_path":receipt["file_binding"]["canonical_path"]=str(root/"other.txt")
    elif fault=="session":receipt["file_binding"]["session_id"]="other-session"
    elif fault=="permission":receipt["file_binding"]["permission_scope"]["project_root"]=str(root/"other")
    elif fault=="source":source.write_text("changed",encoding="utf-8")
    else:receipt.pop("file_binding")
    with pytest.raises(ValueError):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("kind",["measurement","chart","forecast","fit","series","scenario"])
def test_file_delivery_cannot_supply_dataset_or_method_identity(kind):
    from data_agent.agent.publication.deliveries import validate_business_scope
    scope=_file_spec()["scope"]
    with pytest.raises(ValueError):validate_business_scope(scope,required=True,measurement=kind=="measurement",metadata=kind=="table")


@pytest.mark.parametrize("fault",["no_path","no_offset","data_identity","mixed_catalog","wrong_output","statistic"])
def test_file_delivery_required_scope_rejects_ambiguous_or_borrowed_identity(fault):
    from data_agent.agent.publication.deliveries import validate_business_scope
    scope=_file_spec()["scope"];p=scope["parameters"]
    if fault=="no_path":p.pop("file_path")
    elif fault=="no_offset":p.pop("file_offset")
    elif fault=="data_identity":scope["datasets"]=["orders"]
    elif fault=="mixed_catalog":p.update(catalog_scope="current_visible",catalog_output="datasets")
    elif fault=="wrong_output":p["file_output"]="entries"
    else:scope["quantity"]="sum"
    with pytest.raises(ValueError):validate_business_scope(scope,required=True,metadata=True)


@pytest.mark.parametrize("fault",["path","offset","limit","sha"])
def test_file_delivery_cannot_close_different_requested_range(engine,fault):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True);(root/"read.txt").write_text("alpha\nbeta",encoding="utf-8");(root/"other.txt").write_text("alpha\nbeta",encoding="utf-8")
    spec=_file_spec(limit=1)
    p=spec["scope"]["parameters"]
    p[{"path":"file_path","offset":"file_offset","limit":"file_limit","sha":"file_sha256"}[fault]]={"path":"other.txt","offset":1,"limit":2,"sha":"0"*64}[fault]
    request(loop,"交付指定文件范围",spec);execute(loop,"read_file",{"path":"read.txt","limit":1})
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]!="answered"


@pytest.mark.parametrize("tool",["read_file","list_files"])
def test_file_delivery_commit_rechecks_actual_source_after_render(engine,tool):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True);source=root/"read.txt";source.write_text("alpha",encoding="utf-8")
    args={"path":"read.txt"} if tool=="read_file" else {"pattern":"*.txt"}
    request(loop,"交付文件范围",_file_spec(tool,**args));execute(loop,tool,args)
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    source.write_text("changed",encoding="utf-8")
    assert commit(loop,{"role":"assistant"},body) and not loop.context.analysis_state.accepted_answers


@pytest.mark.parametrize("fault",["omit_entry","fake_entry","changed_source","cross_session"])
def test_file_delivery_catalogue_exact_snapshot_rejects_tamper(engine,fault):
    from data_agent.agent.publication.native import resolve_native_claims
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True);source=root/"read.txt";source.write_text("alpha",encoding="utf-8")
    request(loop,"列出文件",_file_spec("list_files",pattern="*.txt"));rid,result=execute(loop,"list_files",{"pattern":"*.txt"})
    if fault=="omit_entry":result["entries"]=[];result["returned_entries"]=0;_tamper(loop,cfg,rid,result)
    elif fault=="fake_entry":result["entries"][0]["path"]="fake.txt";_tamper(loop,cfg,rid,result)
    elif fault=="changed_source":source.unlink()
    else:loop.context.analysis_state.tool_receipts[-1]["file_binding"]["session_id"]="other-session"
    with pytest.raises((ValueError,OSError)):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


def test_file_delivery_catalogue_retains_original_enumeration_time_without_ledger_feedback(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True);(root/"read.txt").write_text("alpha",encoding="utf-8")
    # '**/*' includes tool_outputs; persisting this receipt must not mutate its own captured catalogue.
    request(loop,"列出此时全部文件",_file_spec("list_files",pattern="**/*"));rid,result=execute(loop,"list_files",{"pattern":"**/*"})
    (root/"later.txt").write_text("later",encoding="utf-8")
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="answered"
    claim=next(c for c in snap.as_dict()["claims"] if c["basis_refs"][0]["receipt_id"]==rid)
    assert claim["value"]==result["entries"] and not any(e["path"]=="later.txt" for e in claim["value"])
    assert "枚举时点" in body and commit(loop,{"role":"assistant"},body) is None


def test_file_delivery_list_files_discloses_inaccessible_entries_as_partial(engine,monkeypatch):
    from data_agent.tools import file_ops
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;root=cfg.project_resolved;root.mkdir(parents=True,exist_ok=True);(root/"blocked.txt").write_text("alpha",encoding="utf-8")
    original=file_ops._file_entry
    def blocked(ref):
        if ref=="blocked.txt":raise PermissionError("injected unreadable")
        return original(ref)
    monkeypatch.setattr(file_ops,"_file_entry",blocked)
    request(loop,"列出文件目录",_file_spec("list_files",pattern="*.txt"));rid,result=execute(loop,"list_files",{"pattern":"*.txt"})
    assert result["entries"]==[] and result["skipped_entries"]==1 and result["status"]=="partial"
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None
    assert loop._accepted_answer["requirement_outcomes"][0]["status"]=="partial" and "未覆盖范围不称为空" in body


class _TaskScopeModel(_NativeProductModel):
    """Task IDs come only from public results, followed by an ordinary data goal."""
    def __init__(self, case, foreign_id):
        content = "分析上传数据，将其命名为experiment；先维护本会话任务，再报告真实记录数。"
        super().__init__(content,"experiment","describe_dataset",{"name":"experiment"},[{"kind":"measurement","scope":{"datasets":["experiment"],"quantity":"rows"}}])
        self.case,self.foreign_id = case,foreign_id
        self.task_step=0;self.own_id=None;self.task_results=[];self.pending_task=None
    def chat(self,messages,system="",tools=None,**kw):
        if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
            return super().chat(messages,system=system,tools=tools,**kw)
        from data_agent.llm.client import Response,ToolCall
        if self.pending_task is not None:
            message = next(m for m in reversed(messages) if m.get("role")=="tool")
            raw = message.get("content","")
            try: result=json.JSONDecoder().raw_decode(raw.lstrip())[0]
            except (ValueError,TypeError): result=None
            self.task_results.append((self.pending_task,result,raw))
            if self.pending_task=="task_create" and self.own_id is None and result:
                task=result["tasks"][0] if "tasks" in result else result
                self.own_id=task.get("id")
            self.pending_task=None
        self.task_step+=1
        if self.task_step==1:
            name="task_create"
            args={"tasks":json.dumps([{"subject":"LOCAL_TASK"}])} if self.case=="batch" else {"subject":"LOCAL_TASK"}
        elif self.task_step==2:
            name,args="task_get",{"task_id":self.own_id}
        elif self.task_step==3:
            name="task_update"
            change={"task_id":self.own_id,"status":"completed","result_summary":"local todo only"}
            args={"updates":json.dumps([change])} if self.case=="batch" else change
        elif self.case=="foreign" and self.task_step<=8:
            name,args={
                4:("task_get",{"task_id":self.foreign_id}),
                5:("task_update",{"task_id":self.foreign_id,"status":"deleted"}),
                6:("task_update",{"updates":json.dumps([{"task_id":self.own_id,"status":"failed"},{"task_id":self.foreign_id,"status":"completed"}])}),
                7:("task_update",{"task_id":self.own_id,"addBlocks":json.dumps([self.foreign_id])}),
                8:("task_create",{"tasks":json.dumps([{"subject":"INJECTED","session_id":"private_session"}])}),
            }[self.task_step]
        elif self.task_step==(9 if self.case=="foreign" else 4):name,args="task_list",{}
        else:return super().chat(messages,system=system,tools=tools,**kw)
        self.calls.append(name);self.pending_task=name
        return Response(tool_calls=[ToolCall("task_scope_"+str(self.task_step),name,args)])


@pytest.mark.parametrize("case",["single","batch","foreign"])
def test_task_tool_scope_normal_app_upload_task_lifecycle_and_accepted_answer(engine,case):
    import io,hashlib,shutil
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.task_manager import task_manager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    foreign=task_manager.create("PRIVATE_OTHER_SESSION",session_id="private_session")
    original=task_manager._path(foreign["id"]).read_bytes()
    script=_TaskScopeModel(case,foreign["id"])
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager;sid="s3_task_scope_"+case
    data=b"amount\n10\n20\n30\n"
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();script.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":script.content,"uploads":[ticket]})
        assert response.status_code==200
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    assert answer["requirement_outcomes"][0]["status"]=="answered",answer
    req=answer["source_snapshot"]["requirements"][0]
    rows=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    assert len(rows)==1 and rows[0]["value"]==3
    assert script.own_id and script.calls[-3:]==["describe_dataset","record_analysis_plan","describe_dataset"]
    assert "PRIVATE_OTHER_SESSION" not in json.dumps(script.task_results,ensure_ascii=False)
    assert task_manager._path(foreign["id"]).read_bytes()==original
    assert task_manager.get(script.own_id)["status"]=="completed"
    if case=="foreign":
        rejected=[r for name,r,raw in script.task_results[3:8]]
        assert len(rejected)==5 and all(r and r.get("error_type")=="task_scope_not_found" for r in rejected),script.task_results
        assert not any(t["subject"]=="INJECTED" for t in task_manager.list_all_raw())
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md");assert exported["status"]=="exported"
    md=cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]
    assert answer["body"] in md.read_text(encoding="utf-8")
    # Preserve the actual application evidence outside disposable pytest containers.
    evidence=Path("tmp/s3-task-scope-20261012-r1/normal-app-evidence")/cfg.sessions_resolved.parents[1].name/case;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/"answer.json").write_text(json.dumps(answer,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence/"events.json").write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence/"task-results.json").write_text(json.dumps(script.task_results,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence/"refreshed.json").write_text(json.dumps(refreshed,ensure_ascii=False,indent=2),encoding="utf-8")
    shutil.copy2(md,evidence/"reply.md")
    (evidence/"foreign-before.json").write_bytes(original)
    (evidence/"foreign-after.json").write_bytes(task_manager._path(foreign["id"]).read_bytes())


@pytest.mark.parametrize("case",["old","updated","failed"])
def test_rule_persistence_normal_app_context_read_upload_and_accepted_answer(engine,monkeypatch,case):
    import io,hashlib,shutil
    from pathlib import Path
    from data_agent.knowledge.rules import ProjectRules
    from data_agent.tools import knowledge_tools
    from data_agent.tools.registry import registry
    from data_agent.agent.context import use_agent_context
    from tests.test_global_capabilities import _rule_write_fault
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    loop,cfg=engine;sid="s3_rule_context_"+case
    rules=ProjectRules(path=cfg.workspace_resolved/"knowledge/project_rules.md");old="OLD_GLOBAL：只报告可核验结果。";new="NEW_GLOBAL：保留未知，不补造数值。"
    rules.update(old);rules.update_session_rules(sid,"CURRENT_SESSION_ONLY");rules.update_session_rules("other_rules_session","FOREIGN_SESSION_ONLY")
    monkeypatch.setattr(knowledge_tools,"_project_rules",rules)
    if case!="old":
        with monkeypatch.context() as m:
            if case=="failed":fault=_rule_write_fault(m,rules.path,new,"after_replace")
            with use_agent_context(loop.context):result=registry.execute("update_project_rules",{"content":new})
            if case=="failed":assert fault["fired"] and json.loads(result.summary).get("error")
    expected=new if case=="updated" else old
    content="分析上传数据，将其命名为experiment；先读取当前全局及会话规则作为上下文，再报告真实记录数。"
    class RuleContextModel(_NativeProductModel):
        def __init__(self):
            super().__init__(content,"experiment","describe_dataset",{"name":"experiment"},[{"kind":"measurement","scope":{"datasets":["experiment"],"quantity":"rows"}}],[("show_project_rules",{})])
            self.prompts=[];self.rule_result=None
        def chat(self,messages,system="",tools=None,**kw):
            if system!="你是一个JSON输出器，只返回JSON，不要其他内容。":
                self.prompts.append(system)
                for message in messages:
                    if message.get("role")=="tool" and message.get("name")=="show_project_rules":self.rule_result=message.get("content")
            return super().chat(messages,system=system,tools=tools,**kw)
    script=RuleContextModel();manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager;data=b"amount\n10\n20\n30\n"
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();script.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"] and answer["requirement_outcomes"][0]["status"]=="answered"
    req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    assert len(claims)==1 and claims[0]["value"]==3
    assert script.calls==["describe_dataset","record_analysis_plan","show_project_rules","describe_dataset"]
    assert script.prompts and all(expected in p and "CURRENT_SESSION_ONLY" in p and "FOREIGN_SESSION_ONLY" not in p for p in script.prompts)
    rule_result=next(d["web"]["summary"] for e,d in events if e=="tool_result" and d["name"]=="show_project_rules")
    assert expected in rule_result and "CURRENT_SESSION_ONLY" in rule_result and "FOREIGN_SESSION_ONLY" not in rule_result
    assert rules.path.read_bytes()==expected.encode("utf-8") and ProjectRules(path=rules.path).content==expected
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md");assert exported["status"]=="exported"
    md=cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1];assert answer["body"] in md.read_text(encoding="utf-8")
    evidence=Path("tmp/s3-rules-20261012-r2/normal-app-evidence")/cfg.sessions_resolved.parents[1].name/"context"/case;evidence.mkdir(parents=True,exist_ok=True)
    for name,value in [("answer",answer),("events",events),("refreshed",refreshed),("prompts",script.prompts)]:
        (evidence/(name+".json")).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence/"rules.md").write_bytes(rules.path.read_bytes());shutil.copy2(md,evidence/"reply.md")

