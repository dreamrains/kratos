from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: storage. Shared fixtures have one owner."""
from data_agent.agent.publication.contracts import encode
from data_agent.knowledge.memory import MemoryStore
from data_agent.tools import knowledge_tools
from data_agent.tools.registry import registry
from pathlib import Path
from tests.test_memory_candidate_extractor import _extraction_capture
from tests.test_memory_candidate_extractor import _extraction_rows
from tests.test_memory_candidate_extractor import _extraction_setup
from tests.test_trusted_publication_semantics import execute
import hashlib
import json
import pytest
import sqlite3
from tests.support.publication_runtime import _NativeProductModel, request

def _rule_operation_fixture(cfg,monkeypatch):
    from data_agent.knowledge.rules import ProjectRules
    from data_agent.tools import knowledge_tools
    rules=ProjectRules(path=cfg.knowledge_dir/"project_rules.md");rules.update("OLD_GLOBAL_RULE")
    monkeypatch.setattr(knowledge_tools,"_project_rules",rules)
    return rules


def _rule_operation_spec(content="NEW_GLOBAL_RULE"):
    return {"kind":"operation","scope":{"operation":{"action":"update_project_rules","arguments":{"content":content}}}}


def test_rule_operation_exact_global_file_cache_and_effect_without_data_claim(engine,monkeypatch):
    from data_agent.agent.publication.native import resolve_operation_effect
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,cfg=engine;rules=_rule_operation_fixture(cfg,monkeypatch);old=rules.path.read_bytes()
    request(loop,"将全局规则替换为NEW_GLOBAL_RULE",_rule_operation_spec())
    rid,result=execute(loop,"update_project_rules",{"content":"NEW_GLOBAL_RULE"})
    effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
    assert effect["action"]=="update_project_rules" and effect["permission_scope"]=="configured_global_rules"
    assert effect["before"]["object_before"]["sha256"]=="sha256:"+hashlib.sha256(old).hexdigest()
    assert effect["object"]["identity"]["sha256"]=="sha256:"+hashlib.sha256(b"NEW_GLOBAL_RULE").hexdigest()
    assert rules.content=="NEW_GLOBAL_RULE" and not effect["data_identities"]
    snap=snapshot_for_turn(loop).as_dict();assert not snap["claims"] and len(snap["effects"])==1


@pytest.mark.parametrize("case",["undeclared","wrong_content","wrong_permission"])
def test_rule_operation_guard_rejects_before_mutation(engine,monkeypatch,case):
    loop,cfg=engine;rules=_rule_operation_fixture(cfg,monkeypatch);old=rules.path.read_bytes()
    request(loop,"只更新指定全局规则",None if case=="undeclared" else _rule_operation_spec())
    args={"content":"OTHER_RULE" if case=="wrong_content" else "NEW_GLOBAL_RULE"}
    if case=="wrong_permission":
        from data_agent.agent.publication.native import capture_operation_binding
        rules.path=cfg.workspace_resolved/"other.md"
        with pytest.raises(ValueError):capture_operation_binding(loop.context,"update_project_rules",args)
    else:
        error=loop._current_task_scope_guard("update_project_rules",args)
        assert error and json.loads(error)["error_type"]=="operation_plan_required"
    assert (cfg.knowledge_dir/"project_rules.md").read_bytes()==old


@pytest.mark.parametrize("fault",["result_path","result_sha","result_before","binding_path","binding_sha","permission","session","cache","disk","configured_path"])
def test_rule_operation_rejects_receipt_or_live_rule_tamper(engine,monkeypatch,fault):
    from data_agent.agent.publication.native import resolve_operation_effect
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;rules=_rule_operation_fixture(cfg,monkeypatch)
    request(loop,"只更新指定全局规则",_rule_operation_spec());rid,result=execute(loop,"update_project_rules",{"content":"NEW_GLOBAL_RULE"})
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid)
    if fault=="result_path":result["path"]="other.md";_tamper(loop,cfg,rid,result)
    elif fault=="result_sha":result["state"]["sha256"]="sha256:"+"0"*64;_tamper(loop,cfg,rid,result)
    elif fault=="result_before":result["before"]["sha256"]="sha256:"+"0"*64;_tamper(loop,cfg,rid,result)
    elif fault=="binding_path":receipt["operation_binding"]["object_before"]["path"]="other.md"
    elif fault=="binding_sha":receipt["operation_binding"]["expected_sha256"]="sha256:"+"0"*64
    elif fault=="permission":receipt["operation_binding"]["permission_scope"]="current_session_rules"
    elif fault=="session":receipt["operation_binding"]["session_id"]="other_session"
    elif fault=="cache":rules._content="SILENT_CACHE_CHANGE"
    elif fault=="disk":rules.path.write_bytes(b"SILENT_DISK_CHANGE")
    else:rules.path=cfg.workspace_resolved/"other.md"
    with pytest.raises(ValueError):resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("change",["disk","cache"])
def test_rule_operation_commit_rechecks_global_file_and_prompt(engine,monkeypatch,change):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine;rules=_rule_operation_fixture(cfg,monkeypatch)
    request(loop,"只更新指定全局规则",_rule_operation_spec());execute(loop,"update_project_rules",{"content":"NEW_GLOBAL_RULE"})
    snap=snapshot_for_turn(loop);host=snap.as_dict();req=host["requirements"][0]
    raw=encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":[req["id"]],"parts":[{"kind":"effect","ref":req["effect_ids"][0]}]}]})
    body,error=publish(loop,raw);assert error is None and "操作完成" in body
    if change=="disk":rules.path.write_bytes(b"CHANGED_AFTER_RENDER")
    else:rules._content="CHANGED_AFTER_RENDER"
    assert commit(loop,{"role":"assistant"},body) and not loop.context.analysis_state.accepted_answers


@pytest.mark.parametrize("case",["regular","empty","mixed_newlines","failed","undeclared","wrong_content"])
def test_rule_operation_normal_app_standalone_exact_effect_or_refusal_sse_save_refresh_export(engine,monkeypatch,case):
    import shutil
    from pathlib import Path
    from tests.test_global_capabilities import _rule_write_fault
    from data_agent.knowledge.rules import ProjectRules
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;rules=_rule_operation_fixture(cfg,monkeypatch);old=rules.path.read_bytes();sid="s3_rule_operation_"+case
    new={"empty":"","mixed_newlines":"RULE_ONE\r\n中文规则\rfinal"}.get(case,"NEW_GLOBAL_RULE")
    content="将全局规则完整替换为以下内容，并交付实际操作效果："+repr(new)
    class RuleOperationModel(_NativeProductModel):
        def __init__(self):
            super().__init__(content,None,"update_project_rules",{"content":"OTHER_RULE" if case=="wrong_content" else new},[_rule_operation_spec(new)])
            if case=="undeclared":self.step=1
            self.systems=[]
        def chat(self,messages,system="",tools=None,**kw):
            if system!="你是一个JSON输出器，只返回JSON，不要其他内容。":self.systems.append(system)
            return super().chat(messages,system=system,tools=tools,**kw)
    script=RuleOperationModel();manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager
    with monkeypatch.context() as m:
        if case=="failed":fault=_rule_write_fault(m,rules.path,new,"after_replace")
        with app.test_client() as http:
            response=http.post("/api/chat",json={"session_id":sid,"message":content})
            events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
            ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]==("failed" if case in {"undeclared","wrong_content"} else "completed"),events
            refreshed=http.get("/api/sessions/"+sid).get_json()
    if case in {"undeclared","wrong_content"}:
        state=load_session(sid);loop=manager.get(sid)
        durable=json.loads((cfg.sessions_resolved/sid/"run_state.json").read_text(encoding="utf-8"))
        assert durable["status"]=="failed" and durable["turn_id"]==ends[0]["turn_id"]
        assert "operation_plan_required" in ends[0]["execution_notice"]
        assert rules.path.read_bytes()==old and rules.content=="OLD_GLOBAL_RULE"
        refs=loop.context.analysis_state.accepted_answers;assert len(refs)==1
        answer=read_answer(sid,refs[0])
        assert answer["requirement_outcomes"][0]["status"]!="answered" and not answer["source_snapshot"]["effects"] and not answer["source_snapshot"]["claims"]
        assert any(m.get("answer_ref")==refs[0] and m["content"]==answer["body"] for m in state["messages"])
        assert state["messages"][-1]["content"]==ends[0]["execution_notice"]
        assert not any(r["tool_name"]=="update_project_rules" for r in loop.context.analysis_state.tool_receipts)
        assert "操作完成" not in ends[0]["reply_content"] and "OLD_GLOBAL_RULE" in script.systems[-1]
        assert any("operation_plan_required" in m.get("content","") for m in refreshed["messages"])
        evidence=Path("tmp/s3-rules-20261012-r2/normal-app-evidence")/cfg.sessions_resolved.parents[1].name/"operation"/case;evidence.mkdir(parents=True,exist_ok=True)
        for name,value in [("answer",answer),("session",state),("events",events),("refreshed",refreshed),("prompts",script.systems),("durable",durable)]:
            (evidence/(name+".json")).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
        (evidence/"rules.md").write_bytes(rules.path.read_bytes());(evidence/"before.md").write_bytes(old)
        return
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"]);success=case in {"regular","empty","mixed_newlines"}
    assert answer["body"]==saved["content"]==ends[0]["reply_content"]
    expected=new.encode("utf-8") if success else old
    assert rules.path.read_bytes()==expected and ProjectRules(path=rules.path).content==expected.decode("utf-8")
    assert not answer["source_snapshot"]["claims"] and not answer["source_snapshot"]["data_identities"]
    req=answer["source_snapshot"]["requirements"][0]
    if success:
        assert answer["requirement_outcomes"][0]["status"]=="answered" and req["effect_ids"] and "操作完成" in answer["body"]
        effect=answer["source_snapshot"]["effects"][0]
        assert effect["object"]["identity"]["sha256"]=="sha256:"+hashlib.sha256(expected).hexdigest()
        assert effect["before"]["object_before"]["sha256"]=="sha256:"+hashlib.sha256(old).hexdigest()
        assert effect["arguments"]=={"content":new} and effect["permission_scope"]=="configured_global_rules"
        assert (new in script.systems[-1]) if new else "(无项目规则)" in script.systems[-1]
        receipt=next(r for r in manager.get(sid).context.analysis_state.tool_receipts if r["tool_name"]=="update_project_rules")
        assert receipt["plan_id"] and receipt["required_delivery_ids"] and receipt["operation_binding"]["session_id"]==sid
    else:
        assert answer["requirement_outcomes"][0]["status"]!="answered" and not req["effect_ids"] and "操作完成" not in answer["body"]
        assert "OLD_GLOBAL_RULE" in script.systems[-1]
        result=next((d["web"] for e,d in events if e=="tool_result" and d["name"]=="update_project_rules"),None)
        if result is not None:assert result.get("data",{}).get("error") or json.loads(result["summary"]).get("error")
        else:assert "operation_plan_required" in ends[0]["execution_notice"]
        if case=="failed":assert fault["fired"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md");assert exported["status"]=="exported"
    md=cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1];assert answer["body"] in md.read_text(encoding="utf-8")
    evidence=Path("tmp/s3-rules-20261012-r2/normal-app-evidence")/cfg.sessions_resolved.parents[1].name/"operation"/case;evidence.mkdir(parents=True,exist_ok=True)
    for name,value in [("answer",answer),("events",events),("refreshed",refreshed),("prompts",script.systems)]:
        (evidence/(name+".json")).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence/"rules.md").write_bytes(rules.path.read_bytes());(evidence/"before.md").write_bytes(old);shutil.copy2(md,evidence/"reply.md")


@pytest.mark.parametrize("case",["created","updated","failed_update","deprecated","restored"])
def test_knowledge_storage_normal_app_context_upload_and_accepted_answer(engine,monkeypatch,case):
    import io,ast,shutil
    from pathlib import Path
    from data_agent.tools import knowledge_tools
    from data_agent.knowledge.library import KnowledgeLibrary
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    from tests.test_global_capabilities import _rule_write_fault
    loop,cfg=engine;sid="s3_knowledge_context_"+case
    library=KnowledgeLibrary(cfg.knowledge_dir)
    monkeypatch.setattr(knowledge_tools,"_knowledge_library",library)
    content="分析上传数据，将其命名为experiment；搜索METRIC_CTX知识作为上下文，再报告真实记录数。知识正文不作为数据事实。"
    script=_NativeProductModel(content,"experiment","describe_dataset",{"name":"experiment"},[{"kind":"measurement","scope":{"datasets":["experiment"],"quantity":"rows"}}],[("search_knowledge",{"query":"METRIC_CTX"})])
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager;app.config["PROPAGATE_EXCEPTIONS"]=False
    old="METRIC_CTX OLD\r\nreference\nend\r";new="METRIC_CTX NEW\r\nreference\nend\r";expected=new if case=="updated" else old
    with app.test_client() as http:
        created=http.post("/api/management/knowledge",json={"title":"METRIC_CTX","domain":"general","content":old}).get_json()
        assert created["content"]==old
        item_id=created["id"];path=library.root/library.get(item_id).path
        if case in {"updated","failed_update"}:
            with monkeypatch.context() as m:
                if case=="failed_update":fired=_rule_write_fault(m,path,new,"after_replace")
                response=http.patch("/api/management/knowledge/"+item_id,json={"content":new})
                assert response.status_code==(500 if case=="failed_update" else 200)
                if case=="failed_update":assert fired["fired"]
        if case in {"deprecated","restored"}:
            assert http.post("/api/management/knowledge/"+item_id+"/deprecate").get_json()["status"]=="deprecated"
            if case=="restored":assert http.post("/api/management/knowledge/"+item_id+"/restore").get_json()["status"]=="active"
        data=b"amount\n10\n20\n30\n"
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();script.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
        api_items=http.get("/api/management/knowledge/search?q=METRIC_CTX").get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"] and answer["requirement_outcomes"][0]["status"]=="answered"
    req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    assert len(claims)==1 and claims[0]["value"]==3 and not answer["source_snapshot"].get("effects")
    assert script.calls==["describe_dataset","record_analysis_plan","search_knowledge","describe_dataset"]
    output=next(d["web"]["summary"] for e,d in events if e=="tool_result" and d["name"]=="search_knowledge")
    found=ast.literal_eval(output)
    assert len(found)==(0 if case=="deprecated" else 1)
    if found:assert found[0]["id"]==item_id and found[0]["content"]==expected
    assert len(api_items)==len(found)
    if api_items:assert api_items[0]["content"]==expected
    loaded=KnowledgeLibrary(library.root).get(item_id)
    assert loaded.content==expected and loaded.version==(2 if case=="updated" else 1)
    assert path.read_bytes()==expected.encode("utf-8")
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md");assert exported["status"]=="exported"
    md=cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1];assert answer["body"] in md.read_text(encoding="utf-8")
    evidence=Path("tmp/s3-knowledge-20261012-r1/normal-app-evidence")/cfg.sessions_resolved.parents[1].name/case;evidence.mkdir(parents=True,exist_ok=True)
    for name,value in [("answer",answer),("events",events),("refreshed",refreshed),("knowledge-result",found),("api-search",api_items),("item",dict(id=loaded.id,version=loaded.version,content=loaded.content,status=loaded.status.value))]:
        (evidence/(name+".json")).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence/"knowledge.md").write_bytes(path.read_bytes());shutil.copy2(md,evidence/"reply.md")


def _knowledge_operation_fixture(cfg,monkeypatch):
    from data_agent.knowledge.library import KnowledgeLibrary
    from data_agent.tools import knowledge_tools
    library=KnowledgeLibrary(cfg.knowledge_dir)
    monkeypatch.setattr(knowledge_tools,"_knowledge_library",library)
    old=library.create("Old knowledge","general","OLD_KNOWLEDGE")
    return library,old


def _knowledge_operation_args(case="regular"):
    args={"title":"Metric policy","domain":"general","content":"GMV includes paid orders only.","summary":"Metric scope","tags":["metric"]}
    if case=="empty":args["content"]=""
    elif case=="mixed_newlines":args["content"]="METRIC\r\n中文\nend\r"
    elif case=="sanitized":args.update(title="指标/政策",domain="../../商务")
    return args


def _knowledge_operation_spec(args=None):
    return {"kind":"operation","scope":{"operation":{"action":"create_knowledge_item","arguments":args or _knowledge_operation_args()}}}


@pytest.mark.parametrize("case",["regular","empty","mixed_newlines","sanitized"])
def test_knowledge_operation_exact_new_row_file_and_existing_effect(engine,monkeypatch,case):
    from data_agent.agent.publication.native import resolve_operation_effect
    from data_agent.agent.publication.runtime import snapshot_for_turn
    loop,cfg=engine;library,old=_knowledge_operation_fixture(cfg,monkeypatch);args=_knowledge_operation_args(case)
    request(loop,"创建指定正式知识",_knowledge_operation_spec(args));rid,result=execute(loop,"create_knowledge_item",args)
    effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
    item=library.get(result["id"])
    assert item.id!=old.id and item.version==1 and item.status.value=="active" and item.source.value=="user"
    assert item.content==args["content"] and (library.root/item.path).read_bytes()==args["content"].encode("utf-8")
    assert effect["object"]["kind"]=="file" and effect["object"]["identity"]["sha256"]=="sha256:"+hashlib.sha256(args["content"].encode()).hexdigest()
    assert effect["details"]["knowledge"]["id"]==item.id and effect["details"]["knowledge"]["version"]==1
    assert effect["before"]["object_before"]["existing_ids"]==[old.id]
    assert effect["permission_scope"]=="configured_global_knowledge" and not effect["data_identities"]
    assert library.get(old.id).content=="OLD_KNOWLEDGE"
    snap=snapshot_for_turn(loop).as_dict();assert len(snap["effects"])==1 and not snap["claims"]


@pytest.mark.parametrize("case",["undeclared","wrong_content","wrong_root","wrong_db"])
def test_knowledge_operation_guard_and_capture_reject_before_creation(engine,monkeypatch,case):
    from data_agent.agent.publication.native import capture_operation_binding
    loop,cfg=engine;library,old=_knowledge_operation_fixture(cfg,monkeypatch);args=_knowledge_operation_args()
    request(loop,"创建指定正式知识",None if case=="undeclared" else _knowledge_operation_spec(args))
    if case in {"undeclared","wrong_content"}:
        actual=dict(args,content="OTHER") if case=="wrong_content" else args
        error=loop._current_task_scope_guard("create_knowledge_item",actual)
        assert error and json.loads(error)["error_type"]=="operation_plan_required"
    else:
        if case=="wrong_root":library.root=cfg.workspace_resolved/"other"
        else:library.db.path=cfg.workspace_resolved/"other.sqlite3"
        with pytest.raises(ValueError):capture_operation_binding(loop.context,"create_knowledge_item",args)
    assert not (cfg.workspace_resolved/"other.sqlite3").exists()
    from data_agent.knowledge.library import KnowledgeLibrary
    assert [(i.id,i.content) for i in KnowledgeLibrary(cfg.knowledge_dir).list()]==[(old.id,"OLD_KNOWLEDGE")]


@pytest.mark.parametrize("fault",["result_id","result_content","result_metadata","result_path","result_version","result_status","result_source","binding_root","binding_db","binding_sha","permission","session","existing_id","disk","row_summary","row_version","row_status","configured_root"])
def test_knowledge_operation_rejects_result_binding_or_live_item_tamper(engine,monkeypatch,fault):
    from data_agent.agent.publication.native import resolve_operation_effect
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;library,old=_knowledge_operation_fixture(cfg,monkeypatch);args=_knowledge_operation_args()
    request(loop,"创建指定正式知识",_knowledge_operation_spec(args));rid,result=execute(loop,"create_knowledge_item",args)
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["id"]==rid);item=library.get(result["id"])
    if fault.startswith("result_"):
        key={"id":"id","content":"content","metadata":"summary","path":"path","version":"version","status":"status","source":"source"}[fault[7:]]
        result[key]=99 if key=="version" else "TAMPERED";_tamper(loop,cfg,rid,result)
    elif fault=="binding_root":receipt["operation_binding"]["object_before"]["root"]="other"
    elif fault=="binding_db":receipt["operation_binding"]["object_before"]["database_path"]="other.sqlite3"
    elif fault=="binding_sha":receipt["operation_binding"]["expected_sha256"]="sha256:"+"0"*64
    elif fault=="permission":receipt["operation_binding"]["permission_scope"]="other"
    elif fault=="session":receipt["operation_binding"]["session_id"]="other"
    elif fault=="existing_id":receipt["operation_binding"]["object_before"]["existing_ids"].append(item.id)
    elif fault=="disk":(library.root/item.path).write_bytes(b"TAMPERED")
    elif fault.startswith("row_"):
        field=fault[4:];value=2 if field=="version" else "deprecated" if field=="status" else "TAMPERED"
        with library.db.connect() as conn:conn.execute("UPDATE knowledge_items SET "+field+"=? WHERE id=?",(value,item.id))
    else:library.root=cfg.workspace_resolved/"other"
    with pytest.raises(ValueError):resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("change",["disk","metadata","version"])
def test_knowledge_operation_commit_rechecks_actual_file_and_database(engine,monkeypatch,change):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine;library,old=_knowledge_operation_fixture(cfg,monkeypatch);args=_knowledge_operation_args()
    request(loop,"创建指定正式知识",_knowledge_operation_spec(args));rid,result=execute(loop,"create_knowledge_item",args)
    snap=snapshot_for_turn(loop);req=snap.as_dict()["requirements"][0]
    raw=encode({"schema":"answer_bindings.v2","snapshot_digest":snap.digest,"sections":[{"requirement_ids":[req["id"]],"parts":[{"kind":"effect","ref":req["effect_ids"][0]}]}]})
    body,error=publish(loop,raw);assert error is None and "操作完成" in body
    item=library.get(result["id"])
    if change=="disk":(library.root/item.path).write_bytes(b"CHANGED_AFTER_RENDER")
    else:
        field="summary" if change=="metadata" else "version";value="CHANGED" if change=="metadata" else 2
        with library.db.connect() as conn:conn.execute("UPDATE knowledge_items SET "+field+"=? WHERE id=?",(value,item.id))
    assert commit(loop,{"role":"assistant"},body) and not loop.context.analysis_state.accepted_answers


def test_knowledge_operation_registry_keeps_direct_mapping_and_structured_result(engine,monkeypatch):
    from data_agent.tools import knowledge_tools
    from data_agent.tools.registry import registry
    _,cfg=engine;library,old=_knowledge_operation_fixture(cfg,monkeypatch);args=_knowledge_operation_args()
    direct=knowledge_tools.create_knowledge_item(**args);assert isinstance(direct,dict) and direct["title"]==args["title"]
    result=registry.execute("create_knowledge_item",args)
    assert isinstance(result.data,dict) and result.data["id"]!=direct["id"] and result.data["content"]==args["content"]
    assert result.summary==str(result.data) and result.to_web()["data"]==result.data


@pytest.mark.parametrize("case",["regular","empty","mixed_newlines","sanitized","failed_write","failed_sql","undeclared","wrong_content"])
def test_knowledge_operation_normal_app_standalone_effect_or_predispatch_refusal(engine,monkeypatch,case):
    import shutil
    from pathlib import Path
    from data_agent.knowledge import library as library_module
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;library,old=_knowledge_operation_fixture(cfg,monkeypatch);args=_knowledge_operation_args(case);sid="s3_knowledge_operation_"+case
    old_bytes=(library.root/old.path).read_bytes();content="只创建正式知识并交付实际操作效果，完整参数："+json.dumps(args,ensure_ascii=False)
    class KnowledgeOperationModel(_NativeProductModel):
        def __init__(self):
            super().__init__(content,None,"create_knowledge_item",dict(args,content="OTHER") if case=="wrong_content" else args,[_knowledge_operation_spec(args)])
            if case=="undeclared":self.step=1
    script=KnowledgeOperationModel();manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager
    blocked=case in {"undeclared","wrong_content"};success=case in {"regular","empty","mixed_newlines","sanitized"};fired=[]
    with monkeypatch.context() as m:
        if case=="failed_write":
            original=library_module.write_bytes_atomic
            def reject(path,value):
                original(path,value);fired.append(True);raise OSError("knowledge write failed after replacement")
            m.setattr(library_module,"write_bytes_atomic",reject)
        if case=="failed_sql":
            with library.db.connect() as conn:conn.execute("CREATE TRIGGER fail_create BEFORE INSERT ON knowledge_items BEGIN SELECT RAISE(ABORT, 's3_create_refused'); END")
        with app.test_client() as http:
            response=http.post("/api/chat",json={"session_id":sid,"message":content})
            events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
            ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]==("failed" if blocked else "completed"),events
            refreshed=http.get("/api/sessions/"+sid).get_json()
            listed=http.get("/api/management/knowledge").get_json()
    loop=manager.get(sid);state=load_session(sid);refs=loop.context.analysis_state.accepted_answers;assert len(refs)==1
    answer=read_answer(sid,refs[0]);snap=answer["source_snapshot"];effects=snap["effects"]
    assert not snap["claims"] and not snap["data_identities"]
    assert (answer["requirement_outcomes"][0]["status"]=="answered")==success
    assert (library.root/old.path).read_bytes()==old_bytes and library.get(old.id).content=="OLD_KNOWLEDGE"
    assert len(listed)==(2 if success else 1)
    if success:
        assert len(effects)==1 and "操作完成" in answer["body"]
        effect=effects[0];item_id=effect["details"]["knowledge"]["id"];item=library.get(item_id)
        assert item.version==1 and item.content==args["content"] and item.status.value=="active" and item.source.value=="user"
        assert effect["arguments"]==args and effect["permission_scope"]=="configured_global_knowledge"
        assert effect["object"]["identity"]["sha256"]=="sha256:"+hashlib.sha256(args["content"].encode()).hexdigest()
        assert effect["before"]["object_before"]["existing_ids"]==[old.id]
        assert item_id in answer["body"] and '"version":1' in answer["body"].replace(" ","")
        receipt=next(r for r in loop.context.analysis_state.tool_receipts if r["tool_name"]=="create_knowledge_item")
        assert receipt["plan_id"] and receipt["required_delivery_ids"] and receipt["operation_binding"]["session_id"]==sid
        assert (library.root/item.path).read_bytes()==args["content"].encode("utf-8")
    else:
        assert not effects and "操作完成" not in answer["body"] and not list(library.root.rglob(".atomic-*.tmp"))
        if case=="failed_write":assert fired
    durable=json.loads((cfg.sessions_resolved/sid/"run_state.json").read_text(encoding="utf-8"))
    assert durable["turn_id"]==ends[0]["turn_id"] and durable["status"]==ends[0]["status"]
    if blocked:
        assert "operation_plan_required" in ends[0]["execution_notice"] and state["messages"][-1]["content"]==ends[0]["execution_notice"]
        assert not any(r["tool_name"]=="create_knowledge_item" for r in loop.context.analysis_state.tool_receipts)
    else:
        assert answer["body"]==state["messages"][-1]["content"]==ends[0]["reply_content"]
    assert any(m.get("answer_ref")==refs[0] and m["content"]==answer["body"] for m in refreshed["messages"])
    evidence=Path("tmp/s3-knowledge-20261012-r2/normal-app-evidence")/cfg.sessions_resolved.parents[1].name/case;evidence.mkdir(parents=True,exist_ok=True)
    for name,value in [("answer",answer),("events",events),("refreshed",refreshed),("session",state),("durable",durable),("items",listed)]:
        (evidence/(name+".json")).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence/"old.md").write_bytes(old_bytes)
    if success:(evidence/"created.md").write_bytes(args["content"].encode("utf-8"))
    if not blocked:
        exported=export_assistant_reply(sid,answer["body"],"md");assert exported["status"]=="exported"
        md=cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1];assert answer["body"] in md.read_text(encoding="utf-8");shutil.copy2(md,evidence/"reply.md")


def test_knowledge_operation_rejects_reusing_identical_preexisting_item(engine,monkeypatch):
    from data_agent.agent.publication.native import resolve_operation_effect
    from tests.test_r3_comparison_host_claims import _tamper
    from dataclasses import asdict
    loop,cfg=engine;library,_=_knowledge_operation_fixture(cfg,monkeypatch);args=_knowledge_operation_args()
    old=library.create(**args)
    request(loop,"创建一条新的指定正式知识",_knowledge_operation_spec(args));rid,result=execute(loop,"create_knowledge_item",args)
    record=asdict(old);record["status"]=old.status.value;record["source"]=old.source.value
    _tamper(loop,cfg,rid,record)
    with pytest.raises(ValueError):resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize("case",["candidate","confirmed","updated","failed_update","failed_confirm","deprecated"])
def test_memory_storage_normal_app_context_upload_and_accepted_answer(engine,monkeypatch,case):
    import io,ast,shutil
    from pathlib import Path
    from data_agent.tools import knowledge_tools
    from data_agent.knowledge.memory import MemoryStore
    from data_agent.knowledge.retrieval import KnowledgeRetrievalService
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    from tests.test_memory_store import _memory_storage_rows
    _,cfg=engine;sid="s3_memory_context_"+case;store=MemoryStore(cfg.knowledge_dir)
    monkeypatch.setattr(knowledge_tools,"_memory_store",store)
    monkeypatch.setattr(knowledge_tools,"_retrieval_service",KnowledgeRetrievalService(cfg.knowledge_dir))
    content="分析上传数据，将其命名为experiment；列出待审记忆并检索MEMCTX作低优先级上下文，再报告真实记录数。记忆不作为当前数据事实。"
    script=_NativeProductModel(content,"experiment","describe_dataset",{"name":"experiment"},[{"kind":"measurement","scope":{"datasets":["experiment"],"quantity":"rows"}}],[("list_memory_candidates",{}),("retrieve_knowledge_context",{"query":"MEMCTX"})])
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script)
    app=create_app();app.config["agent_manager"]=manager;app.config["PROPAGATE_EXCEPTIONS"]=False
    old="MEMCTX OLD\r\nreference\nend\r";new="MEMCTX NEW\r\nreference\nend\r";expected=new if case=="updated" else old
    with app.test_client() as http:
        created=http.post("/api/management/memory",json={"text":old,"summary":"MEMCTX OLD","source_session_id":sid}).get_json()
        # The existing management API strips surrounding text whitespace.
        old=old.strip();new=new.strip();expected=new if case=="updated" else old
        assert created["text"]==old;item_id=created["id"]
        if case not in {"candidate","failed_confirm"}:assert http.post("/api/management/memory/"+item_id+"/confirm").get_json()["status"]=="confirmed"
        before=_memory_storage_rows(store.root)
        if case in {"updated","failed_update","failed_confirm"}:
            original=MemoryStore._item_from_row;fired=[]
            def reject(self,row):
                changed=row["text"]==new if case=="failed_update" else row["status"]=="confirmed"
                if changed:fired.append(True);raise OSError("normal app memory readback failed")
                return original(self,row)
            with monkeypatch.context() as m:
                if case!="updated":m.setattr(MemoryStore,"_item_from_row",reject)
                if case=="failed_confirm":response=http.post("/api/management/memory/"+item_id+"/confirm")
                else:response=http.patch("/api/management/memory/"+item_id,json={"text":new,"summary":"MEMCTX NEW"})
                assert response.status_code==(200 if case=="updated" else 500)
                if case!="updated":assert fired
            if case!="updated":assert _memory_storage_rows(store.root)==before
        if case=="deprecated":assert http.post("/api/management/memory/"+item_id+"/deprecate").get_json()["status"]=="deprecated"
        data=b"amount\n10\n20\n30\n"
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();script.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json()
        api_items=http.get("/api/management/memory").get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"])
    assert answer["body"]==saved["content"]==ends[0]["reply_content"] and answer["requirement_outcomes"][0]["status"]=="answered"
    req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    assert len(claims)==1 and claims[0]["value"]==3 and not answer["source_snapshot"].get("effects")
    assert script.calls==["describe_dataset","record_analysis_plan","list_memory_candidates","retrieve_knowledge_context","describe_dataset"]
    outputs={d["name"]:d["web"]["summary"] for e,d in events if e=="tool_result"}
    candidates=ast.literal_eval(outputs["list_memory_candidates"]);context=outputs["retrieve_knowledge_context"]
    assert (item_id in {c["id"] for c in candidates})==(case in {"candidate","failed_confirm"})
    assert all(c["status"]=="candidate" for c in candidates)
    visible=case in {"confirmed","updated","failed_update"}
    assert ("MEMCTX OLD" in context or "MEMCTX NEW" in context)==visible
    if visible:assert ("MEMCTX NEW" if case=="updated" else "MEMCTX OLD") in context and '<memory_hints priority="low">' in context
    assert store.get(item_id).text==expected and next(i for i in api_items if i["id"]==item_id)["text"]==expected
    status="candidate" if case in {"candidate","failed_confirm"} else "deprecated" if case=="deprecated" else "confirmed"
    assert store.get(item_id).status.value==status
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md");assert exported["status"]=="exported"
    md=cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1];assert answer["body"] in md.read_text(encoding="utf-8")
    evidence=Path("tmp/s3-memory-20261012-r1/normal-app-evidence")/cfg.sessions_resolved.parents[1].name/case;evidence.mkdir(parents=True,exist_ok=True)
    for name,value in [("answer",answer),("events",events),("refreshed",refreshed),("api-memory",api_items),("raw-rows",_memory_storage_rows(store.root)),("candidates",candidates),("storage-root",str(store.root))]:
        (evidence/(name+".json")).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    (evidence/"context.txt").write_text(context,encoding="utf-8");shutil.copy2(md,evidence/"reply.md")


@pytest.mark.parametrize("case",["promoted","overrides","failed_sql","failed_commit","failed_write"])
def test_memory_promotion_normal_app_context_upload_and_accepted_answer(engine,monkeypatch,case):
    import io,ast,shutil
    from data_agent.knowledge.memory import MemoryStore
    from data_agent.knowledge.library import KnowledgeLibrary
    from data_agent.knowledge.retrieval import KnowledgeRetrievalService
    from data_agent.knowledge import library as library_module
    from data_agent.tools import knowledge_tools
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    from tests.test_memory_store import _memory_storage_rows
    _,cfg=engine;sid="s3_memory_promotion_"+case;store=MemoryStore(cfg.knowledge_dir);library=KnowledgeLibrary(cfg.knowledge_dir)
    monkeypatch.setattr(knowledge_tools,"_memory_store",store);monkeypatch.setattr(knowledge_tools,"_knowledge_library",library);monkeypatch.setattr(knowledge_tools,"_retrieval_service",KnowledgeRetrievalService(cfg.knowledge_dir))
    original_item=library.create("Original policy","general","ORIGINAL_REFERENCE")
    content="分析上传数据，将其命名为experiment；搜索PROMOCTX知识和低优先级记忆上下文，报告真实记录数。引用材料不作为当前数据事实。"
    script=_NativeProductModel(content,"experiment","describe_dataset",{"name":"experiment"},[{"kind":"measurement","scope":{"datasets":["experiment"],"quantity":"rows"}}],[("search_knowledge",{"query":"PROMOCTX"}),("retrieve_knowledge_context",{"query":"PROMOCTX"})])
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script);app=create_app();app.config["agent_manager"]=manager;app.config["PROPAGATE_EXCEPTIONS"]=False
    text="PROMOCTX BODY\r\n中文\nend\r".strip();success=case in {"promoted","overrides"}
    with app.test_client() as http:
        item=http.post("/api/management/memory",json={"text":text,"summary":"PROMOCTX summary","source_session_id":sid,"tags":["metric"]}).get_json();item_id=item["id"]
        assert http.post("/api/management/memory/"+item_id+"/confirm").get_json()["status"]=="confirmed"
        before=_memory_storage_rows(store.root)
        with monkeypatch.context() as m:
            if case in {"failed_sql","failed_commit"}:
                with store.db.connect() as conn:
                    if case=="failed_sql":conn.execute("CREATE TRIGGER deny_promotion BEFORE UPDATE ON memory_items WHEN NEW.status='promoted' BEGIN SELECT RAISE(ABORT, 'promotion denied'); END")
                    else:
                        conn.execute("CREATE TABLE allowed_guard (id INTEGER PRIMARY KEY)")
                        conn.execute("CREATE TABLE deferred_guard (id INTEGER REFERENCES allowed_guard(id) DEFERRABLE INITIALLY DEFERRED)")
                        conn.execute("CREATE TRIGGER fail_commit AFTER UPDATE ON memory_items WHEN NEW.status='promoted' BEGIN INSERT INTO deferred_guard VALUES(1); END")
            elif case=="failed_write":
                original=library_module.write_bytes_atomic;fired=[]
                def reject(path,data):
                    original(path,data);fired.append(True);raise OSError("promotion write failed after replace")
                m.setattr(library_module,"write_bytes_atomic",reject)
            args={"title":"Explicit policy","summary":"PROMOCTX promoted summary"} if case=="overrides" else {}
            response=http.post("/api/management/memory/"+item_id+"/promote",json=args)
            assert response.status_code==(201 if success else 500)
            if case=="failed_write":assert fired
        if not success:assert _memory_storage_rows(store.root)==before and [i.id for i in library.list()]==[original_item.id]
        data=b"amount\n10\n20\n30\n";ticket=http.post("/api/upload",data={"file":(io.BytesIO(data),"experiment.csv")},content_type="multipart/form-data").get_json()
        assert ticket["sha256"]=="sha256:"+hashlib.sha256(data).hexdigest();script.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed",events
        refreshed=http.get("/api/sessions/"+sid).get_json();api_memory=http.get("/api/management/memory").get_json();api_knowledge=http.get("/api/management/knowledge").get_json()
    saved=load_session(sid)["messages"][-1];answer=read_answer(sid,saved["answer_ref"]);req=answer["source_snapshot"]["requirements"][0];claims=[c for c in answer["source_snapshot"]["claims"] if c["id"] in req["claim_ids"]]
    assert answer["body"]==saved["content"]==ends[0]["reply_content"] and answer["requirement_outcomes"][0]["status"]=="answered"
    assert len(claims)==1 and claims[0]["value"]==3 and not answer["source_snapshot"].get("effects")
    outputs={d["name"]:d["web"]["summary"] for e,d in events if e=="tool_result"};found=ast.literal_eval(outputs["search_knowledge"]);context=outputs["retrieve_knowledge_context"]
    assert len(found)==(1 if success else 0)
    current=store.get(item_id);assert current.status.value==("promoted" if success else "confirmed")
    if success:
        knowledge=library.get(current.promotion_target);assert knowledge.content==text and found[0]["id"]==knowledge.id
        assert '<retrieved_knowledge priority="reference">' in context and '<memory_hints priority="low">' not in context
        assert knowledge.title==("Explicit policy" if case=="overrides" else "PROMOCTX summary")
    else:assert '<memory_hints priority="low">' in context and '<retrieved_knowledge' not in context
    assert script.calls==["describe_dataset","record_analysis_plan","search_knowledge","retrieve_knowledge_context","describe_dataset"]
    assert any(m.get("answer_ref")==saved["answer_ref"] for m in refreshed["messages"])
    exported=export_assistant_reply(sid,answer["body"],"md");assert exported["status"]=="exported";md=cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1];assert answer["body"] in md.read_text(encoding="utf-8")
    evidence=Path("tmp/s3-memory-20261012-r2/normal-app-evidence")/cfg.sessions_resolved.parents[1].name/("promotion_"+case);evidence.mkdir(parents=True,exist_ok=True)
    with store.db.connect() as conn:knowledge_rows=[dict(r) for r in conn.execute("SELECT * FROM knowledge_items ORDER BY id")]
    for name,value in [("answer",answer),("events",events),("refreshed",refreshed),("api-memory",api_memory),("api-knowledge",api_knowledge),("raw-rows",_memory_storage_rows(store.root)),("knowledge-rows",knowledge_rows),("search-result",found),("memory-id",item_id),("storage-root",str(store.root))]:
        (evidence/(name+".json")).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    files=evidence/"knowledge-files";files.mkdir()
    for row in knowledge_rows:shutil.copy2(library.root/row["path"],files/(row["id"]+".md"))
    (evidence/"context.txt").write_text(context,encoding="utf-8");shutil.copy2(md,evidence/"reply.md")


@pytest.mark.parametrize('mode',['success','create','refresh'])
def test_extraction_normal_agentloop_failure_or_success_does_not_create_partial_memory(engine,monkeypatch,mode):
    import io,shutil
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;source,store,before=_extraction_setup(cfg,monkeypatch,mode);sid='s3_extract_'+mode
    content='分析上传数据，将其命名为experiment；提取指定旧会话的待审候选作上下文准备，然后报告当前表真实记录数。'
    script=_NativeProductModel(content,'experiment','describe_dataset',{'name':'experiment'},[{'kind':'measurement','scope':{'datasets':['experiment'],'quantity':'rows'}}],[('extract_memory_candidates',{'session_id':source}),('list_memory_candidates',{})])
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script);app=create_app();app.config['agent_manager']=manager
    data=b'amount\n10\n20\n30\n'
    with app.test_client() as http:
        ticket=http.post('/api/upload',data={'file':(io.BytesIO(data),'experiment.csv')},content_type='multipart/form-data').get_json();script.ticket=ticket
        response=http.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]})
        events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
        refreshed=http.get('/api/sessions/'+sid).get_json()
    saved=load_session(sid)['messages'][-1];answer=read_answer(sid,saved['answer_ref']);after=_extraction_rows(store.root)
    ends=[d for e,d in events if e=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed'
    assert answer['body']==saved['content']==ends[0]['reply_content']
    assert answer['requirement_outcomes'][0]['status']=='answered'
    assert any(c.get('value')==3 for c in answer['source_snapshot']['claims'])
    assert any(m.get('answer_ref')==saved['answer_ref'] for m in refreshed['messages'])
    export=export_assistant_reply(sid,answer['body'],'md');assert export['status']=='exported'
    md=cfg.sessions_resolved/sid/'reports'/export['artifact_path'].split('/')[-1];assert answer['body'] in md.read_text(encoding='utf-8')
    captured=_extraction_capture('normal_'+mode+'.json',{'before':before,'after':after,'answer':answer,'events':events,'refreshed':refreshed,'storage_root':str(store.root),'source_session':source,'csv_text':data.decode(),'provider_calls':0})
    shutil.copy2(md,captured.with_suffix('.md'))
    relevant=[r for r in after if r['source_session_id']==source]
    assert (len(relevant)==2) if mode=='success' else relevant==before


_MEMORY_EFFECT_OUT=Path('tmp/s3-memory-effects-20261013-r1')


def _memory_effect_rows(root):
    with sqlite3.connect(root/'knowledge.sqlite3') as conn:
        conn.row_factory=sqlite3.Row
        return [dict(r) for r in conn.execute('SELECT * FROM memory_items ORDER BY id')]


def _memory_effect_fixture(cfg,monkeypatch,action):
    from data_agent.tools import knowledge_tools
    store=MemoryStore(cfg.knowledge_dir);monkeypatch.setattr(knowledge_tools,'_memory_store',store)
    old=store.create_candidate('MEMEFFECT OLD',summary='Old reference',source_session_id='seed_session')
    args={'text':'MEMEFFECT NEW\r\n中文\nend\r','summary':'New reference','memory_type':'preference','confidence':.7,'domain':'general','tags':['reference']} if action=='create_memory_candidate' else {'memory_id':old.id}
    return store,old,args


def _memory_effect_spec(action,args):return {'kind':'operation','scope':{'operation':{'action':action,'arguments':args}}}


def _memory_effect_capture(name,value):
    p=_MEMORY_EFFECT_OUT/'red-evidence'/Path(value['storage_root']).parents[2].name/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    return p


@pytest.mark.parametrize('action',['create_memory_candidate','confirm_memory'])
def test_memory_native_registry_write_has_an_operation_contract(engine,monkeypatch,action):
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.native import operation_requested
    _,cfg=engine;store,old,args=_memory_effect_fixture(cfg,monkeypatch,action);before=_memory_effect_rows(store.root)
    result=registry.execute(action,args);after=_memory_effect_rows(store.root)
    _memory_effect_capture('registry_'+action+'.json',{'before':before,'after':after,'result':result.to_web(),'arguments':args,'storage_root':str(store.root)})
    assert after!=before and result.data
    assert operation_requested(action,args)


@pytest.mark.parametrize('action',['create_memory_candidate','confirm_memory'])
def test_memory_native_formal_plan_accepts_actual_memory_effect(engine,monkeypatch,action):
    loop,cfg=engine;store,old,args=_memory_effect_fixture(cfg,monkeypatch,action);error=None
    try:request(loop,'执行指定记忆操作',_memory_effect_spec(action,args))
    except ValueError as exc:error=str(exc)
    _memory_effect_capture('plan_'+action+'.json',{'error':error,'arguments':args,'rows':_memory_effect_rows(store.root),'storage_root':str(store.root)})
    assert error is None


@pytest.mark.parametrize('action',['create_memory_candidate','confirm_memory'])
def test_memory_native_undeclared_guard_rejects_before_dispatch(engine,monkeypatch,action):
    loop,cfg=engine;store,old,args=_memory_effect_fixture(cfg,monkeypatch,action);request(loop,'执行指定记忆操作')
    error=loop._current_task_scope_guard(action,args)
    _memory_effect_capture('guard_'+action+'.json',{'error':error,'arguments':args,'rows':_memory_effect_rows(store.root),'storage_root':str(store.root)})
    assert error and json.loads(error)['error_type']=='operation_plan_required'


@pytest.mark.parametrize('action',['create_memory_candidate','confirm_memory'])
@pytest.mark.parametrize('case',['valid','undeclared','wrong_args'])
def test_memory_native_normal_app_standalone_effect_or_refusal(engine,monkeypatch,action,case):
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    _,cfg=engine;store,old,args=_memory_effect_fixture(cfg,monkeypatch,action);before=_memory_effect_rows(store.root);sid='s3_memory_effect_'+action+'_'+case
    actual=dict(args)
    if case=='wrong_args':
        if action=='create_memory_candidate':actual['text']='WRONG MEMORY'
        else:actual['memory_id']=store.create_candidate('OTHER CANDIDATE').id;before=_memory_effect_rows(store.root)
    content='仅执行指定记忆操作并交付实际效果，参数：'+json.dumps(args,ensure_ascii=False)
    script=_NativeProductModel(content,None,action,actual,[_memory_effect_spec(action,args)])
    if case=='undeclared':script.step=1
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script);app=create_app();app.config['agent_manager']=manager
    with app.test_client() as http:
        response=http.post('/api/chat',json={'session_id':sid,'message':content})
        events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
        refreshed=http.get('/api/sessions/'+sid).get_json()
        listed=http.get('/api/management/memory').get_json()
    loop=manager.get(sid);state=load_session(sid);refs=loop.context.analysis_state.accepted_answers
    answer=read_answer(sid,refs[0]) if refs else None;after=_memory_effect_rows(store.root)
    captured=_memory_effect_capture('normal_'+action+'_'+case+'.json',{'before':before,'after':after,'arguments':args,'actual_arguments':actual,'answer':answer,'events':events,'session':state,'refreshed':refreshed,'items':listed,'storage_root':str(store.root),'provider_calls':0})
    ends=[d for e,d in events if e=='turn_end'];assert len(ends)==1
    durable=json.loads((cfg.sessions_resolved/sid/'run_state.json').read_text(encoding='utf-8'))
    assert durable['turn_id']==ends[0]['turn_id'] and durable['status']==ends[0]['status']
    assert answer and any(m.get('answer_ref')==refs[0] and m['content']==answer['body'] for m in refreshed['messages'])
    if case=='valid':
        assert answer and answer['requirement_outcomes'][0]['status']=='answered'
        assert len(answer['source_snapshot']['effects'])==1 and not answer['source_snapshot']['claims']
        assert answer['body']==state['messages'][-1]['content']==ends[0]['reply_content']
        from data_agent.tools.report import export_assistant_reply
        import shutil
        exported=export_assistant_reply(sid,answer['body'],'md');assert exported['status']=='exported'
        md=cfg.sessions_resolved/sid/'reports'/exported['artifact_path'].split('/')[-1]
        assert answer['body'] in md.read_text(encoding='utf-8');shutil.copy2(md,captured.with_suffix('.md'))
    else:
        assert after==before
        assert ends[0]['status']=='failed' and 'operation_plan_required' in ends[0]['execution_notice']


@pytest.mark.parametrize('status',['rejected','observed','promoted','deprecated'])
@pytest.mark.parametrize('route',['direct','registry'])
def test_memory_native_refuses_nonconfirmable_states_before_mutation(engine,monkeypatch,status,route):
    _,cfg=engine;store,item,args=_memory_effect_fixture(cfg,monkeypatch,'confirm_memory')
    with store.db.connect() as conn:conn.execute('UPDATE memory_items SET status=? WHERE id=?',(status,item.id))
    before=_memory_effect_rows(store.root);error=None
    try:
        if route=='direct':result=knowledge_tools.confirm_memory(item.id);error=result.get('error')
        else:
            result=registry.execute('confirm_memory',args);result=result.data or json.loads(result.summary);error=result.get('error')
    except ValueError as exc:error=str(exc);result={'error':error}
    after=_memory_effect_rows(store.root);_memory_effect_capture('state_'+status+'_'+route+'.json',{'before':before,'after':after,'result':result,'error':error,'storage_root':str(store.root)})
    assert error and before==after


@pytest.mark.parametrize('status',['candidate','confirmed'])
def test_memory_native_confirmation_reports_actual_transition(engine,monkeypatch,status):
    _,cfg=engine;store,item,args=_memory_effect_fixture(cfg,monkeypatch,'confirm_memory')
    if status=='confirmed':store.confirm(item.id)
    before=_memory_effect_rows(store.root);result=registry.execute('confirm_memory',args).data;after=_memory_effect_rows(store.root)
    _memory_effect_capture('transition_'+status+'.json',{'before':before,'after':after,'result':result,'storage_root':str(store.root)})
    expected={k:(json.loads(v) if k in {'tags','source_message_ids','source_tool_call_ids','source_evidence_ids'} else bool(v) if k=='needs_review' else v) for k,v in before[0].items()}
    assert result['before']==expected and result['state']['status']=='confirmed'
    if status=='confirmed':assert before==after


@pytest.mark.parametrize('action',['create_memory_candidate','confirm_memory'])
@pytest.mark.parametrize('fault',['result_id','result_text','result_state','result_before','root','database','permission','session','row_text','row_status','row_delete','old_identity'])
def test_memory_effect_rejects_result_binding_and_actual_row_tamper(engine,monkeypatch,action,fault):
    from data_agent.agent.publication.native import resolve_operation_effect
    from tests.test_r3_comparison_host_claims import _tamper
    loop,cfg=engine;store,old,args=_memory_effect_fixture(cfg,monkeypatch,action)
    request(loop,'执行指定记忆操作',_memory_effect_spec(action,args));rid,result=execute(loop,action,args)
    receipt=next(r for r in loop.context.analysis_state.tool_receipts if r['id']==rid)
    binding=receipt['operation_binding'];item_id=result['id']
    if fault.startswith('result_'):
        key=fault[7:]
        if key=='state':result['state']['source_message_ids']=['UNBOUND']
        elif key=='before':result['before']={'id':'OTHER'}
        else:result[key]='TAMPERED'
        _tamper(loop,cfg,rid,result)
    elif fault=='root':binding['object_before']['root']='OTHER'
    elif fault=='database':binding['object_before']['database_path']='OTHER.sqlite3'
    elif fault=='permission':binding['permission_scope']='OTHER'
    elif fault=='session':binding['session_id']='OTHER'
    elif fault=='old_identity':
        if action=='create_memory_candidate':binding['object_before']['existing_ids'].append(item_id)
        else:binding['object_before']['sha256']='sha256:'+'0'*64
    else:
        with store.db.connect() as conn:
            if fault=='row_delete':conn.execute('DELETE FROM memory_items WHERE id=?',(item_id,))
            else:conn.execute('UPDATE memory_items SET '+fault[4:]+'=? WHERE id=?',('rejected' if fault=='row_status' else 'CHANGED',item_id))
    with pytest.raises(ValueError):resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize('action',['create_memory_candidate','confirm_memory'])
@pytest.mark.parametrize('change',['text','confidence','delete'])
def test_memory_effect_commit_rechecks_actual_record(engine,monkeypatch,action,change):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine;store,old,args=_memory_effect_fixture(cfg,monkeypatch,action)
    request(loop,'执行指定记忆操作',_memory_effect_spec(action,args));rid,result=execute(loop,action,args)
    snap=snapshot_for_turn(loop);req=snap.as_dict()['requirements'][0]
    raw=encode({'schema':'answer_bindings.v2','snapshot_digest':snap.digest,'sections':[{'requirement_ids':[req['id']],'parts':[{'kind':'effect','ref':req['effect_ids'][0]}]}]})
    body,error=publish(loop,raw);assert error is None and '操作完成' in body
    with store.db.connect() as conn:
        if change=='delete':conn.execute('DELETE FROM memory_items WHERE id=?',(result['id'],))
        else:conn.execute('UPDATE memory_items SET '+change+'=? WHERE id=?',(.13 if change=='confidence' else 'CHANGED_AFTER_RENDER',result['id']))
    assert commit(loop,{'role':'assistant'},body) and not loop.context.analysis_state.accepted_answers


@pytest.mark.parametrize('action',['create_memory_candidate','confirm_memory'])
@pytest.mark.parametrize('target',['root','database'])
def test_memory_effect_capture_rejects_wrong_configured_target_before_write(engine,monkeypatch,action,target):
    from data_agent.agent.publication.native import capture_operation_binding
    loop,cfg=engine;store,old,args=_memory_effect_fixture(cfg,monkeypatch,action);before=_memory_effect_rows(store.root)
    original=store.root
    if target=='root':store.root=cfg.workspace_resolved/'wrong-memory'
    else:store.db.path=cfg.workspace_resolved/'wrong-memory.sqlite3'
    with pytest.raises(ValueError):capture_operation_binding(loop.context,action,args)
    assert _memory_effect_rows(original)==before and not (cfg.workspace_resolved/'wrong-memory.sqlite3').exists()


def _memory_effect_inject_failure(store,monkeypatch,mode,action):
    statement='INSERT' if action=='create_memory_candidate' else 'UPDATE'
    if mode=='failed_sql':
        with store.db.connect() as conn:conn.execute('CREATE TRIGGER deny_effect BEFORE '+statement+" ON memory_items BEGIN SELECT RAISE(ABORT,'effect denied'); END")
    elif mode=='failed_commit':
        with store.db.connect() as conn:
            conn.execute('CREATE TABLE allowed_effect(id INTEGER PRIMARY KEY)')
            conn.execute('CREATE TABLE deferred_effect(id INTEGER REFERENCES allowed_effect(id) DEFERRABLE INITIALLY DEFERRED)')
            conn.execute('CREATE TRIGGER deny_effect AFTER '+statement+' ON memory_items BEGIN INSERT INTO deferred_effect VALUES(1); END')
    elif mode=='failed_readback':
        def fail(*args,**kwargs):raise OSError('effect readback failed inside transaction')
        monkeypatch.setattr(store,'_require_with_connection',fail)


@pytest.mark.parametrize('action',['create_memory_candidate','confirm_memory'])
@pytest.mark.parametrize('case',['empty','defaults','confirmed','failed_sql','failed_commit','failed_readback','missing','rejected'])
def test_memory_effect_normal_app_actual_scope_transition_failure_and_export(engine,monkeypatch,action,case):
    import shutil
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine;store,old,args=_memory_effect_fixture(cfg,monkeypatch,action);sid='s3_memory_effect_'+action+'_'+case
    if action=='create_memory_candidate':
        if case=='empty':args['text']=''
        elif case=='defaults':args={'text':'DEFAULT EXACT'}
        elif case=='confirmed':args.update(domain='  商务  ',tags=['same','same'])
        elif case=='missing':args['confidence']=-1
        elif case=='rejected':args['memory_type']='unsupported'
    else:
        if case=='confirmed':store.confirm(old.id)
        elif case=='missing':args['memory_id']='mem_missing'
        elif case=='rejected':
            with store.db.connect() as conn:conn.execute("UPDATE memory_items SET status='rejected' WHERE id=?",(old.id,))
    before=_memory_effect_rows(store.root);success=case in {'empty','defaults','confirmed'}
    content='仅执行指定记忆操作并交付实际效果，参数：'+json.dumps(args,ensure_ascii=False)
    script=_NativeProductModel(content,None,action,args,[_memory_effect_spec(action,args)])
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script);app=create_app();app.config['agent_manager']=manager
    with monkeypatch.context() as m:
        _memory_effect_inject_failure(store,m,case,action)
        with app.test_client() as http:
            response=http.post('/api/chat',json={'session_id':sid,'message':content})
            events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
            refreshed=http.get('/api/sessions/'+sid).get_json();listed=http.get('/api/management/memory').get_json()
    loop=manager.get(sid);state=load_session(sid);refs=loop.context.analysis_state.accepted_answers
    if action=='confirm_memory' and case in {'missing','rejected'}:
        after=_memory_effect_rows(store.root);ends=[d for e,d in events if e=='turn_end']
        durable=json.loads((cfg.sessions_resolved/sid/'run_state.json').read_text(encoding='utf-8'))
        _memory_effect_capture('normal_extra_'+action+'_'+case+'.json',{'before':before,'after':after,'arguments':args,'answer':None,'events':events,'refreshed':refreshed,'session':state,'durable':durable,'items':listed,'storage_root':str(store.root),'provider_calls':0})
        assert before==after and not refs and len(ends)==1 and ends[0]['status']=='failed'
        assert durable['turn_id']==ends[0]['turn_id'] and durable['status']=='failed'
        assert '目标不存在或状态不支持' in ends[0]['execution_notice']
        assert not any(r['tool_name']==action for r in loop.context.analysis_state.tool_receipts)
        assert state['messages'][-1]['content']==ends[0]['execution_notice']
        assert refreshed['messages'][-1]['content']==ends[0]['execution_notice']
        return
    assert len(refs)==1
    answer=read_answer(sid,refs[0]);after=_memory_effect_rows(store.root);effects=answer['source_snapshot']['effects']
    ends=[d for e,d in events if e=='turn_end'];assert len(ends)==1
    durable=json.loads((cfg.sessions_resolved/sid/'run_state.json').read_text(encoding='utf-8'))
    assert durable['turn_id']==ends[0]['turn_id'] and durable['status']==ends[0]['status']
    assert not answer['source_snapshot']['claims'] and not answer['source_snapshot']['data_identities']
    assert (answer['requirement_outcomes'][0]['status']=='answered')==success
    if success:
        assert len(effects)==1 and '操作完成' in answer['body']
        effect=effects[0];item_id=effect['object']['name'];current=next(r for r in after if r['id']==item_id)
        assert effect['object']['kind']=='memory' and effect['permission_scope']=='configured_global_memory'
        canonical={k:(json.loads(v) if k in {'tags','source_message_ids','source_tool_call_ids','source_evidence_ids'} else bool(v) if k=='needs_review' else v) for k,v in current.items()}
        assert effect['details']['memory']==canonical
        expected_digest='sha256:'+hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        assert effect['object']['identity']['sha256']==expected_digest
        if action=='create_memory_candidate':
            assert item_id!=old.id and current['source_session_id']==sid and current['text']==args['text'] and current['status']=='candidate'
            assert next(r for r in after if r['id']==old.id)==before[0]
        else:
            assert item_id==old.id and current['status']=='confirmed'
            if case=='confirmed':assert before==after and effect['details']['changed'] is False and '幂等' in answer['body']
        assert answer['body']==state['messages'][-1]['content']==ends[0]['reply_content']
    else:assert before==after and not effects and '操作完成' not in answer['body']
    assert any(m.get('answer_ref')==refs[0] and m['content']==answer['body'] for m in refreshed['messages'])
    captured=_memory_effect_capture('normal_extra_'+action+'_'+case+'.json',{'before':before,'after':after,'arguments':args,'answer':answer,'events':events,'refreshed':refreshed,'session':state,'durable':durable,'items':listed,'storage_root':str(store.root),'provider_calls':0})
    if ends[0]['status']=='completed':
        exported=export_assistant_reply(sid,answer['body'],'md');assert exported['status']=='exported'
        md=cfg.sessions_resolved/sid/'reports'/exported['artifact_path'].split('/')[-1];assert answer['body'] in md.read_text(encoding='utf-8');shutil.copy2(md,captured.with_suffix('.md'))

