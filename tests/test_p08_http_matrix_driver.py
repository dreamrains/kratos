"""Critical transport and confirmation integrity for the existing P08 HTTP route."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


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
    path.write_text("tampered")
    with pytest.raises(RuntimeError,match="file identity"):
        driver._snapshot("http://local",tmp_path,sid)


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
