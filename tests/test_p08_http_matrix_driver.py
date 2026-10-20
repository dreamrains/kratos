"""Critical transport and confirmation integrity for the existing P08 HTTP route."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from tests.test_trusted_publication_semantics import engine


def _driver():
    path = Path(__file__).parents[1] / "scripts" / "testing" / "run_p08_http_matrix.py"
    spec = importlib.util.spec_from_file_location("p08_http_driver", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _SSE:
    headers = {"X-Data-Agent-Session-Id": "session_one"}

    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def raise_for_status(self):
        return None

    def iter_lines(self, *, decode_unicode):
        assert decode_unicode
        return iter(self.events)


def test_sse_requires_one_terminal_matching_persisted_state(monkeypatch):
    driver = _driver()
    events = ["event: turn_start", 'data: {"session_id":"session_one","turn_id":"t_one"}', "", "event: turn_end",
              'data: {"session_id":"session_one","turn_id":"t_one","status":"completed"}', ""]
    monkeypatch.setattr(driver.requests, "post", lambda *_args, **_kwargs: _SSE(events))
    monkeypatch.setattr(driver, "_json", lambda *_args, **_kwargs: {"status": "completed", "turn_id":"t_one"})
    assert driver._chat("http://127.0.0.1:1", "/api/chat", {"message": "x"})["terminal"] == "completed"

    duplicate = events + ["event: turn_end", 'data: {"session_id":"session_one","turn_id":"t_one","status":"completed"}', ""]
    monkeypatch.setattr(driver.requests, "post", lambda *_args, **_kwargs: _SSE(duplicate))
    with pytest.raises(RuntimeError, match="terminal integrity"):
        driver._chat("http://127.0.0.1:1", "/api/chat", {"message": "x"})

    monkeypatch.setattr(driver.requests, "post", lambda *_args, **_kwargs: _SSE(events))
    monkeypatch.setattr(driver, "_json", lambda *_args, **_kwargs: {"status": "failed", "turn_id":"t_one"})
    with pytest.raises(RuntimeError, match="durable status"):
        driver._chat("http://127.0.0.1:1", "/api/chat", {"message": "x"})


def test_frozen_option_choice_uses_stable_value_not_mutable_prose():
    driver = _driver()
    good = {"options": [
        {"label": "A. 仅代金券成本", "value": "coupon"},
        {"label": "B. 同时扣代金券 + 渠道成本", "value": "both"},
    ]}
    frozen = "select_value both"
    assert driver._choice(good, frozen) == "both"
    renamed = {"options": [
        {"label": "仅券", "value": "coupon"},
        {"label": "券与渠道", "value": "both"},
    ]}
    assert driver._choice(renamed, frozen) == "both"
    assert driver._choice({"options": good["options"] * 2}, frozen) is None
    assert driver._choice({"options": good["options"][:1]}, frozen) is None
    assert driver._choice(good, "select_value other") is None


def test_provider_ledger_must_close_each_physical_call(monkeypatch):
    driver = _driver()

    class Reply:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    events = ('{"event":"started","call_number":1}\n'
              '{"event":"dispatched","call_number":1}\n'
              '{"event":"stream_exhausted","call_number":1}\n')
    monkeypatch.setattr(driver.requests, "get", lambda *_args, **_kwargs: Reply(events))
    assert driver._ledger_state("http://127.0.0.1:1", 1) == {
        "started": 1, "dispatched": 1, "completed": 1, "failed": 0, "denied": 0,
    }

    unfinished = ('{"event":"started","call_number":1}\n'
                  '{"event":"dispatched","call_number":1}\n')
    monkeypatch.setattr(driver.requests, "get", lambda *_args, **_kwargs: Reply(unfinished))
    with pytest.raises(RuntimeError, match="Provider ledger"):
        driver._ledger_state("http://127.0.0.1:1", 1)

    orphan = '{"event":"started","call_number":1}\n'
    monkeypatch.setattr(driver.requests, "get", lambda *_args, **_kwargs: Reply(orphan))
    with pytest.raises(RuntimeError, match="Provider ledger"):
        driver._ledger_state("http://127.0.0.1:1", 1)


def test_typed_confirmation_requires_exact_native_formula_and_scope():
    import json
    driver = _driver()
    frozen = {"kind":"metric_scope_formula","datasets":["m06_promo"],
        "effect_column":"incremental_revenue","cost_columns":["coupon_cost","channel_cost"]}
    formula = {"schema_version":"metric_scope_formula.v1","dataset":"m06_promo",
        "effect_column":"incremental_revenue","cost_columns":["coupon_cost","channel_cost"]}
    value=json.dumps(formula)
    good={"confirmation_type":"metric_definition","options":[{"label":"arbitrary prose","value":value}]}
    assert driver._choice(good,frozen)==value
    reversed_value=json.dumps({**formula,"cost_columns":list(reversed(formula["cost_columns"]))})
    assert driver._choice({**good,"options":[{"value":reversed_value}]},frozen)==reversed_value
    for key, bad in (("dataset","other"),("effect_column","order_amount"),("cost_columns",["coupon_cost"]),("schema_version","v2"),("extra",True)):
        changed={**formula,key:bad}
        assert driver._choice({**good,"options":[{"value":json.dumps(changed)}]},frozen) is None
    assert driver._choice({**good,"options":good["options"]*2},frozen) is None
    assert driver._choice({**good,"confirmation_type":"method_choice"},frozen) is None


def test_frozen_business_response_uses_only_existing_free_text_permission():
    driver=_driver()
    frozen={"kind":"free_text","types":["metric_definition"],"response":"同时扣除代金券成本和渠道成本"}
    suspension={"allow_free_text":True,"confirmation_type":"metric_definition"}
    assert driver._choice(suspension,frozen)==frozen["response"]
    assert driver._choice({**suspension,"allow_free_text":False},frozen) is None
    assert driver._choice({**suspension,"confirmation_type":"method_choice"},frozen) is None


def test_publication_snapshot_reads_normal_persisted_binding_and_rejects_tamper(tmp_path, monkeypatch):
    import hashlib, json
    driver=_driver()
    sid="session_one"
    directory=tmp_path/"sessions"/sid
    (directory/"analyses").mkdir(parents=True)
    body="current original body"
    sha="sha256:"+hashlib.sha256(body.encode()).hexdigest()
    answer={"schema":"answer_bindings.v2","session_id":sid,"answer_id":"a1","body":body,
            "content_sha256":sha,"snapshot_digest":"snap","artifact_refs":[]}
    path=directory/"analyses/answer.json"
    path.write_text(json.dumps(answer))
    ref={"path":"analyses/answer.json","answer_id":"a1","sha256":driver._sha(path),"content_sha256":sha,"snapshot_digest":"snap"}
    session={"messages":[{"answer_id":"a1","content":body,"answer_sha256":sha}]}
    analysis={"state":{"accepted_answers":[ref]}}
    monkeypatch.setattr(driver,"_json",lambda m,u:analysis if u.endswith("/analysis") else session)
    assert driver._snapshot("http://local",tmp_path,sid)["accepted_answers"]=={"a1":answer}
    session["messages"].append(dict(session["messages"][0]))
    with pytest.raises(driver.ScenarioFailure,match="public projection"):
        driver._snapshot("http://local",tmp_path,sid)
    records=[json.loads(line) for line in (tmp_path/"http-matrix.jsonl").read_text().splitlines()]
    assert records[-1]["action"]=="raw_publication_response" and len(records[-1]["session"]["messages"])==2
    path.write_text("tampered")
    with pytest.raises(RuntimeError,match="file identity") as failure:
        driver._snapshot("http://local",tmp_path,sid)
    assert not isinstance(failure.value,driver.ScenarioFailure)


def test_multiple_frozen_confirmations_keep_distinct_resume_identities(tmp_path, monkeypatch):
    import sys, json
    driver=_driver()
    action={"kind":"free_text","types":["metric_definition"],"response":"frozen business"}
    freeze={"matrix":["M06"],"call_cap":3,"fixtures":{},"scenario_inputs":{"M06":{
        "prompts":["one","two","three"],"fixtures":[],"actions":[],
        "confirmations":{str(i):action for i in (1,2,3)}}}}
    monkeypatch.setattr(driver,"_preflight",lambda *args:freeze)
    bodies=[]
    def chat(base,route,body):
        bodies.append((route,body))
        return {"session_id":"s1","terminal":"completed" if route.endswith("resume") else "suspended",
                "suspended":{"allow_free_text":True,"confirmation_type":"metric_definition","confirmation_id":"c"+str(len(bodies)),"version":1}}
    monkeypatch.setattr(driver,"_chat",chat)
    monkeypatch.setattr(driver,"_snapshot",lambda *args:{})
    monkeypatch.setattr(driver,"_check_turn_publication",lambda *args:None)
    monkeypatch.setattr(driver,"_json",lambda *args,**kw:{"messages":[],"run_state":{"status":"completed"}})
    monkeypatch.setattr(driver,"_ledger_state",lambda *args:{"started":0})
    monkeypatch.setattr(sys,"argv",["driver","--base-url","http://127.0.0.1:1","--run-dir",str(tmp_path)])
    driver.main()
    keys=[body["idempotency_key"] for route,body in bodies if route.endswith("resume")]
    assert len(keys)==len(set(keys))==3
    assert keys==[f"p08-M06-s1-{i}" for i in (1,2,3)]
    records=[json.loads(s) for s in (tmp_path/"http-matrix.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(not item["errors"] for item in records if item.get("action")=="persisted_reload")


def test_accounting_stop_marks_remaining_cases_without_sending_them(tmp_path, monkeypatch):
    import sys, json
    driver=_driver()
    freeze={"matrix":["M01","M02"],"call_cap":3,"fixtures":{},"scenario_inputs":{
        name:{"prompts":[name],"fixtures":[],"actions":[]} for name in ("M01","M02")}}
    monkeypatch.setattr(driver,"_preflight",lambda *args:freeze)
    calls=[]
    def chat(base,route,body):
        calls.append(body)
        return {"session_id":"s1","terminal":"completed"}
    monkeypatch.setattr(driver,"_chat",chat)
    monkeypatch.setattr(driver,"_snapshot",lambda *args:{})
    monkeypatch.setattr(driver,"_check_turn_publication",lambda *args:None)
    monkeypatch.setattr(driver,"_json",lambda *args:{"messages":[]})
    def failed(*args): raise RuntimeError("Provider ledger failed")
    monkeypatch.setattr(driver,"_ledger_state",failed)
    monkeypatch.setattr(sys,"argv",["driver","--base-url","http://127.0.0.1:1","--run-dir",str(tmp_path)])
    with pytest.raises(RuntimeError,match="Provider ledger failed"): driver.main()
    assert calls==[{"message":"M01"}]
    records=[json.loads(s) for s in (tmp_path/"http-matrix.jsonl").read_text().splitlines()]
    assert records[-1]["scenario"]=="M02" and records[-1]["classification"]=="blocked_not_started"


def test_export_checks_http_download_against_owned_bytes_and_original_body(tmp_path, monkeypatch):
    driver=_driver()
    path=tmp_path/"sessions/s1/reports/out.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"exported original body")
    monkeypatch.setattr(driver,"_json",lambda *args:{"status":"exported","artifact_path":"sessions/s1/reports/out.md"})
    class Response:
        content=b"exported original body"
        def raise_for_status(self):pass
    monkeypatch.setattr(driver.requests,"get",lambda *args,**kw:Response())
    snapshot={"accepted_answers":{"a1":{"body":"original body"}}}
    assert driver._export_evidence("http://local",tmp_path,"s1",snapshot)["content_verified"]
    assert not driver._export_evidence("http://local",tmp_path,"s1",{"accepted_answers":{}})["content_verified"]
    Response.content=b"different download"
    with pytest.raises(RuntimeError,match="owned export bytes"):
        driver._export_evidence("http://local",tmp_path,"s1",snapshot)


@pytest.mark.parametrize("failure", ["projection", "tool", "host_failure", "confirmation", "sha", "sse", "cross_session", "unknown"])
def test_owned_scenario_failure_continues_but_uncertain_batch_stops(tmp_path, monkeypatch, failure):
    import sys, json
    driver=_driver()
    freeze={"matrix":["M01","M02"],"call_cap":5,"fixtures":{},"scenario_inputs":{
        name:{"prompts":[name+" first",name+" dependent"],"fixtures":[],"actions":[]} for name in ("M01","M02")}}
    monkeypatch.setattr(driver,"_preflight",lambda *args:freeze)
    calls=[]
    def chat(base,route,body):
        calls.append(body)
        sid="s1" if body["message"].startswith("M01") else "s2"
        return {"session_id":sid,"terminal":"failed" if failure=="tool" and sid=="s1" else "suspended" if failure=="confirmation" and sid=="s1" else "completed","terminal_payload":{"reply_id":sid+"reply","reply_content":sid+"body"}}
    monkeypatch.setattr(driver,"_chat",chat)
    def snap(base,run,sid):
        if sid=="s1" and failure=="projection":raise driver.ScenarioFailure("scenario_integrity_failure","owned projection")
        if sid=="s1" and failure in {"sha","sse","cross_session"}:raise RuntimeError(failure)
        if sid=="s1" and failure=="unknown":raise KeyError("unexpected")
        return {"session":{"messages":[{"reply_id":sid+"reply","answer_id":"a"}]},"accepted_answers":{"a":{"body":sid+"body","source_snapshot":{"requirements":[{"id":"r","withdrawn":False,"gap":{"status":"failed"} if failure=="host_failure" and sid=="s1" else None}]}}}}
    monkeypatch.setattr(driver,"_snapshot",snap)
    monkeypatch.setattr(driver,"_json",lambda *args,**kw:{"messages":[]})
    monkeypatch.setattr(driver,"_ledger_state",lambda *args:{"started":0,"completed":0})
    monkeypatch.setattr(sys,"argv",["driver","--base-url","http://local","--run-dir",str(tmp_path)])
    local=failure in {"projection","tool","host_failure","confirmation"}
    if local:driver.main()
    else:
        with pytest.raises((RuntimeError,KeyError)):driver.main()
    assert [row["message"] for row in calls]==(["M01 first","M02 first","M02 dependent"] if local else ["M01 first"])
    rows=[json.loads(line) for line in (tmp_path/"http-matrix.jsonl").read_text().splitlines()]
    assert any(row.get("classification")==("scenario_failure" if local else "global_stop") for row in rows)
    assert any(row.get("classification")=="blocked_not_started" for row in rows)==(not local)


def test_visual_checkpoint_binds_readonly_receipt_and_keeps_same_closed_ledger(tmp_path, monkeypatch):
    import json
    driver=_driver()
    receipt=tmp_path/"visual.json"
    receipt.write_text(json.dumps({'scenario':'M01','session_id':'s1','checkpoint':'scenario_end','status':'unassessed','reason':'readonly browser bridge unavailable'}))
    freeze={"call_cap":5,"operator_protocol":{"control_route":"combined_http_api_browser","visual_checkpoint":"closed_ledger_stdin_v2"}}
    monkeypatch.setattr(driver,"_ledger_state",lambda *args:{"started":2,"completed":2})
    monkeypatch.setattr("builtins.input",lambda:json.dumps({"scenario":"M01","session_id":"s1","checkpoint":"scenario_end","visual_status":"unassessed",
        "evidence_path":"visual.json","evidence_sha256":driver._sha(receipt)}))
    driver._visual_checkpoint("http://local",freeze,tmp_path/"http-matrix.jsonl","M01","s1")
    records=[json.loads(line) for line in (tmp_path/"http-matrix.jsonl").read_text().splitlines()]
    assert [row["action"] for row in records]==["visual_checkpoint_ready","visual_checkpoint_result"]
    assert records[0]["provider_calls"]=={"started":2,"completed":2}


def test_owned_projection_failure_still_executes_next_actual_app_scenario(engine, monkeypatch):
    """Same driver batch: an owned UI defect cannot erase independent engine evidence."""
    import copy, io, json, sys
    from urllib.parse import urlsplit
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient, RunTrace
    driver=_driver();_,cfg=engine
    run=cfg.sessions_resolved.parent
    (run/"fixtures").mkdir()
    data=("date,amount\n"+"".join(f"2026-09-{i:02},10\n" for i in range(1,13))).encode()
    (run/"fixtures/M01-sales.csv").write_bytes(data)
    contract=json.loads(Path("scripts/testing/p08_real_matrix_contract.json").read_text("utf-8"))
    freeze={"matrix":["M01","M05"],"call_cap":1,"fixtures":{"M01-sales.csv":driver._sha(run/"fixtures/M01-sales.csv")},
        "scenario_inputs":{name:{**copy.deepcopy(contract["scenario_inputs"][name]),"prompts":[contract["scenario_inputs"][name]["prompts"][0]],"actions":[]}
                           for name in ("M01","M05")}}
    freeze["scenario_inputs"]["M01"].update(fixtures=[],upload_stages=[])
    trace=RunTrace(run)
    manager=AgentManager(client_factory=lambda **kw:ScriptedClient(trace),auxiliary_client_factory=lambda:ScriptedClient(trace))
    app=create_app();app.config["agent_manager"]=manager
    http=app.test_client()
    class Reply:
        def __init__(self,response):
            self.response=response;self.status_code=response.status_code;self.headers=response.headers
        def raise_for_status(self):
            assert self.status_code<400,self.response.get_data(as_text=True)
        def json(self):return self.response.get_json()
        def iter_lines(self,decode_unicode=False):
            value=self.response.get_data(as_text=True).splitlines()
            return iter(value if decode_unicode else [line.encode() for line in value])
        def __enter__(self):return self
        def __exit__(self,*args):self.response.close()
    def dispatch(method,url,**kwargs):
        route=urlsplit(url).path
        body={}
        if "json" in kwargs:body["json"]=kwargs["json"]
        if kwargs.get("files"):
            name,stream,_=kwargs["files"]["file"]
            body.update(data={"file":(io.BytesIO(stream.read()),name)},content_type="multipart/form-data")
        return Reply(http.open(route,method=method,buffered=False,**body))
    monkeypatch.setattr(driver.requests,"request",dispatch)
    monkeypatch.setattr(driver.requests,"post",lambda url,**kw:dispatch("POST",url,**kw))
    monkeypatch.setattr(driver,"_preflight",lambda *args:freeze)
    original_json=driver._json
    first_sid=[]
    def projection(method,url,**kwargs):
        value=original_json(method,url,**kwargs)
        if method=="GET" and urlsplit(url).path.startswith("/api/sessions/") and "/analysis" not in url and "/run-state" not in url:
            sid=urlsplit(url).path.rsplit("/",1)[-1]
            if not first_sid:first_sid.append(sid)
            if sid==first_sid[0]:
                value=copy.deepcopy(value)
                value["messages"].append(copy.deepcopy(next(m for m in value["messages"] if m.get("answer_id"))))
        return value
    monkeypatch.setattr(driver,"_json",projection)
    monkeypatch.setattr(driver,"_ledger_state",lambda *args:{"started":0,"completed":0})
    monkeypatch.setattr(sys,"argv",["driver","--base-url","http://local","--run-dir",str(run)])
    driver.main()
    rows=[json.loads(line) for line in (run/"http-matrix.jsonl").read_text("utf-8").splitlines()]
    assert any(r.get("scenario")=="M01" and r.get("code")=="scenario_integrity_failure" for r in rows)
    second=next(r for r in rows if r.get("scenario")=="M05" and r.get("terminal")=="completed")
    assert second["session_id"]!=first_sid[0]
    state=http.get('/api/sessions/'+second['session_id']+'/analysis').get_json()['state']
    assert any(r['tool_name']=='describe_dataset' for r in state['tool_receipts'])
    assert not any(r.get('classification')=='global_stop' for r in rows)


@pytest.mark.parametrize("terminal", [
    {"session_id":"other","turn_id":"t_one","status":"completed"},
    {"session_id":"session_one","turn_id":"stale","status":"completed"},
    {"session_id":"session_one","status":"completed"},
])
def test_sse_rejects_cross_session_stale_or_missing_turn_identity(monkeypatch, terminal):
    import json
    driver=_driver()
    events=["event: turn_start",'data: {"session_id":"session_one","turn_id":"t_one"}',"",
            "event: turn_end","data: "+json.dumps(terminal),""]
    monkeypatch.setattr(driver.requests,"post",lambda *args,**kw:_SSE(events))
    with pytest.raises(RuntimeError,match="identity mismatch"):
        driver._chat("http://local","/api/chat",{"message":"frozen"})


@pytest.mark.parametrize("changed",[False,True])
def test_export_normalizes_only_line_endings_and_still_rejects_missing_content(tmp_path,monkeypatch,changed):
    driver=_driver();path=tmp_path/"sessions/s1/reports/out.md";path.parent.mkdir(parents=True)
    content="来源\r\n金额：120\r\n限制：仅当前文件".encode("utf-8")
    if changed:content=content.replace(b"120",b"999")
    path.write_bytes(content)
    monkeypatch.setattr(driver,"_json",lambda *a:{"status":"exported","artifact_path":"sessions/s1/reports/out.md"})
    class Response:
        def raise_for_status(self):pass
    response=Response();response.content=content
    monkeypatch.setattr(driver.requests,"get",lambda *a,**k:response)
    result=driver._export_evidence("http://local",tmp_path,"s1",{"accepted_answers":{"a1":{"body":"来源\n金额：120\n限制：仅当前文件"}}})
    assert result["content_verified"] is (not changed)
    assert result["download_bytes"]==len(content)


@pytest.mark.parametrize("host_gap", [None,{"status":"failed"},{"status":"evidence_insufficient"}])
def test_completed_turn_uses_reply_identity_and_only_host_failure_stops_dependents(host_gap):
    driver=_driver()
    result={"terminal":"completed","turn_id":"sse-turn","terminal_payload":{"reply_id":"reply1","reply_content":"original"}}
    answer={"body":"original","turn_id":"publication-turn","source_snapshot":{"requirements":[{"id":"r","withdrawn":False,"gap":host_gap}]},"requirement_outcomes":[{"status":"failed"}]}
    snapshot={"session":{"messages":[{"reply_id":"reply1","role":"assistant","tool_calls":[{"id":"tool1"}]},{"reply_id":"reply1","answer_id":"a1"}]},"accepted_answers":{"a1":answer}}
    if host_gap and host_gap["status"]=="failed":
        with pytest.raises(driver.ScenarioFailure,match="host execution failure"):driver._check_turn_publication(result,snapshot)
    else:driver._check_turn_publication(result,snapshot)
