import json
from tests.test_trusted_publication_semantics import engine

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import get_config
from data_agent.session.history import save_session
from data_agent.session.workspace import Workspace
from data_agent.tools.report import export_conversation


def _use_tmp_sessions(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    return cfg, old_sessions


def test_export_conversation_supports_markdown_and_html(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    session_id = "export_basic"
    save_session(
        [
            {"role": "user", "content": "Analyze revenue"},
            {
                "role": "assistant",
                "content": "## Conclusion\nRevenue increased, with a short sample-window limitation.",
            },
        ],
        session_id,
    )
    ctx = AgentContext(session_id=session_id, workspace=Workspace())

    try:
        with use_agent_context(ctx):
            md_result = json.loads(export_conversation(format="markdown"))
            html_result = json.loads(export_conversation(format="html"))

        assert md_result["artifact_path"].endswith(".md")
        assert html_result["artifact_path"].endswith(".html")
        assert (tmp_path / md_result["artifact_path"]).exists()
        assert (tmp_path / html_result["artifact_path"]).exists()
    finally:
        cfg.sessions_dir = old_sessions


def test_web_export_pdf_uses_existing_converter(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    session_id = "web_export"
    save_session(
        [
            {"role": "user", "content": "Analyze funnel"},
            {
                "role": "assistant",
                "content": "The registration-to-payment step has the largest drop-off.",
            },
        ],
        session_id,
    )

    try:
        from data_agent.web.app import create_app

        app = create_app()
        client = app.test_client()

        pdf_resp = client.get(f"/api/sessions/{session_id}/export?format=pdf")

        assert pdf_resp.status_code == 200
        body = pdf_resp.get_json()
        assert body["format"] == "pdf"
        assert body["status"] in {"exported", "degraded"}
        assert body["outputs"]
        assert "source_binding" in body
    finally:
        cfg.sessions_dir = old_sessions


def test_removed_report_route_has_no_compatibility_endpoint(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    session_id = "web_report_deprecated"
    save_session(
        [
            {"role": "user", "content": "Summarize the analysis"},
            {"role": "assistant", "content": "Use the conversation synthesis instead."},
        ],
        session_id,
    )

    try:
        from data_agent.web.app import create_app

        client = create_app().test_client()

        response = client.get(f"/api/sessions/{session_id}/report")
        assert response.status_code == 404
    finally:
        cfg.sessions_dir = old_sessions


def test_export_includes_publication_receipt_and_pending_findings(engine):
    """Exports carry the same accepted source and explicit evidence gap."""
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from tests.test_trusted_publication_runtime import request,draft
    from tests.test_trusted_publication_semantics import execute
    loop,cfg=engine
    request(loop,"当前 amount 合计",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}})
    request(loop,"订单量因果影响",kind="gap")
    rid,_=execute(loop,"describe_dataset",{"name":"orders"})
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None
    assert commit(loop,{"role":"assistant"},body) is None
    for fmt in ("markdown","html"):
        result=json.loads(export_conversation(format=fmt))
        text=(cfg.sessions_resolved.parent/result["artifact_path"]).read_text(encoding="utf-8")
        assert "接受答案来源" in text and loop._accepted_answer["answer_id"] in text
        assert rid in text and "原需求交付" in text
        assert "evidence_insufficient" in text and "订单量因果影响" in text
        assert "180" in text and "证据不足" in text


def test_chart_exports_keep_values_and_status_without_internal_metadata(tmp_path):
    from data_agent.tools.report import _validated_chart_entries
    from data_agent.session.history import session_charts_dir
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    try:
        charts = session_charts_dir("export_projection")
        metadata = {"title": "Observed values", "validation_status": "valid", "purpose": "exploratory",
                    "figure": {"data": [{"type": "bar", "x": [1, 2], "y": [10, 11]}]},
                    "data_identity": {"dataset": "sales", "version_id": "v_current",
                                      "source_path": "C:/private/internal/source.csv", "fingerprint": "private-fingerprint"},
                    "evidence_ids": [], "static_image": {"status": "failed"}}
        (charts / "observed.json").write_text(json.dumps(metadata), encoding="utf-8")
        (charts / "observed.html").write_text("chart", encoding="utf-8")
        entry = _validated_chart_entries("export_projection")[0]
        for body in (entry["markdown"], entry["html"]):
            assert "sales" in body and "v_current" in body and "探索图" in body
            assert "source_path" not in body and "private/internal" not in body
            assert "evidence_ids" not in body and "private-fingerprint" not in body
        assert '"y":[10,11]' in entry["html"]
        assert json.loads((charts / "observed.json").read_text("utf-8")) == metadata
    finally:
        cfg.sessions_dir = old_sessions


import json
from pathlib import Path
from html.parser import HTMLParser
import pytest
from tests.conftest import forbid_unmocked_provider_requests
class _Tags(HTMLParser):
 def __init__(self):super().__init__();self.tags=[];self.text=[]
 def handle_starttag(self,tag,attrs):self.tags.append((tag,attrs))
 def handle_data(self,value):self.text.append(value)
@pytest.mark.parametrize('text',['D onerror=ops','Docs javascript:reference','plain record','<img src=x onerror=bad>','[click](javascript:alert(1))','[click](vbscript:bad)','[click](data:text/html;base64,PHNjcmlwdD4=)','[click](&#106;avascript:alert(1))','[click](java&#x73;cript:bad)','[click](JaVaScRiPt:bad)','<script>alert(1)</script>','[ok](https://example.test/path)'])
def test_s3_html_existing_renderer_preserves_literal_values_and_blocks_active_payloads(text):
 from data_agent.tools.report import _markdown_to_html
 html=_markdown_to_html(text);p=_Tags();p.feed(html)
 if text in ['D onerror=ops','Docs javascript:reference','plain record']:assert ''.join(p.text).strip()==text
 assert not any(t in ['script','img','iframe'] or any(k.lower().startswith('on') or k in ['href','src'] and str(v).lower().startswith(('javascript:','vbscript:','data:text/html')) for k,v in attrs) for t,attrs in p.tags)
 if text.startswith('[ok]'):assert ('a',[('href','https://example.test/path')]) in p.tags


def test_s3_html_business_cell_keeps_literal_newline_and_safe_special_characters():
 from data_agent.tools.report import _markdown_to_html
 from data_agent.agent.publication.renderer import _table
 class Cells(HTMLParser):
  def __init__(self):super().__init__();self.cells=[];self.current=None;self.tags=[]
  def handle_starttag(self,tag,attrs):
   self.tags.append((tag,attrs))
   if tag=='td':self.current=[]
  def handle_data(self,text):
   if self.current is not None:self.current.append(text)
  def handle_endtag(self,tag):
   if tag=='td':self.cells.append(''.join(self.current));self.current=None
 text='A|<img src=x onerror=bad>\nDocs javascript:reference [link]'
 p=Cells();p.feed(_markdown_to_html(_table(['group'],[[text]])))
 assert p.cells==[text] and not any(t=='img' or any(k.startswith('on') for k,v in attrs) for t,attrs in p.tags)


@pytest.mark.parametrize('original',['  保留开头与结尾  \n','原文后有空格   '])
def test_exact_accepted_answer_export_preserves_whitespace_and_source_binding(engine,original):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.agent.publication.contracts import encode
    from data_agent.session.history import load_session
    from data_agent.tools.report import export_assistant_reply
    from data_agent.web.app import create_app
    loop,cfg=engine;request(loop,'请解释一般分析方法',kind='knowledge');snap=snapshot_for_turn(loop);rid=snap.as_dict()['requirements'][0]['id'];body,error=publish(loop,encode({'schema':'answer_bindings.v2','snapshot_digest':snap.digest,'sections':[{'requirement_ids':[rid],'parts':[{'kind':'text','purpose':'knowledge','text':original,'claim_refs':[]}]}]}));assert error is None and body==original;assert commit(loop,{'role':'assistant'},body) is None;message=load_session(loop.session_id)['messages'][-1]
    direct=export_assistant_reply(loop.session_id,body,'md');assert 'artifact_path' in direct;path=cfg.sessions_resolved.parent/direct['artifact_path'];assert body in path.read_text(encoding='utf-8')
    app=create_app()
    with app.test_client() as http:
        response=http.post('/api/sessions/'+loop.session_id+'/export-reply',json={'reply_id':message['reply_id'],'format':'markdown'});assert response.status_code==200;result=response.get_json();assert body in (cfg.sessions_resolved.parent/result['artifact_path']).read_text(encoding='utf-8')


import pytest

@pytest.mark.parametrize("route",["assign","projection"])
@pytest.mark.parametrize("accepted",[False,True])
def test_s3_r07_execution_notice_keeps_accepted_reply_identity_separate(route,accepted):
    from data_agent.session.public_messages import assign_reply_ids,assistant_replies
    answer={"role":"assistant","content":"原接受答案：3行。","reply_id":"original_reply"}
    if accepted:answer.update(answer_id="original_answer",answer_ref={"answer_id":"original_answer"},answer_sha256="original_digest")
    notice={"role":"assistant","content":"执行失败：冲突回答。"}
    if route=="projection":notice["reply_id"]="failure_reply"
    messages=[{"role":"user","content":"计算全表记录数。"},answer,notice]
    if route=="assign":
        assign_reply_ids(messages)
        assert (messages[1]["reply_id"]!=messages[2]["reply_id"]) is accepted
        assert messages[1]["reply_id"]=="original_reply"
    else:
        replies=assistant_replies(messages,"s3_identity")
        assert len(replies)==(2 if accepted else 1)
        assert replies[0]["reply_id"]=="original_reply"
        if accepted:
            assert replies[0]["content"]==answer["content"] and replies[0]["answer_ref"]==answer["answer_ref"]
            assert replies[1]["reply_id"]=="failure_reply" and not replies[1].get("answer_ref")


@pytest.mark.parametrize("route", ["public", "grouped", "writer"])
def test_s3_r07_historical_reply_collision_is_read_only(route):
    from copy import deepcopy
    from data_agent.session.public_messages import assign_reply_ids, public_messages, assistant_replies
    answer = {"role": "assistant", "content": "原接受答案：3行。", "reply_id": "original_reply",
              "answer_id": "original_answer", "answer_ref": {"answer_id": "original_answer"},
              "answer_sha256": "original_digest"}
    notice = {"role": "assistant", "content": "执行失败：冲突回答。", "reply_id": "original_reply"}
    messages = [{"role": "user", "content": "计算全表记录数。"}, answer, notice]
    original = deepcopy(messages)
    if route == "writer":
        assign_reply_ids(messages)
        assert messages == original, "Saving legacy history must not migrate persisted reply identities."
        return
    project = public_messages if route == "public" else assistant_replies
    replies = [m for m in project(messages, "historical_collision") if m.get("role", "assistant") == "assistant"]
    assert messages == original
    assert replies == [m for m in project(messages, "historical_collision") if m.get("role", "assistant") == "assistant"]
    assert len(replies) == 2
    assert replies[0]["reply_id"] == answer["reply_id"] and replies[0]["content"] == answer["content"]
    assert replies[0]["answer_ref"] == answer["answer_ref"]
    assert replies[1]["reply_id"].startswith("legacy_") and replies[1]["reply_id"] != answer["reply_id"]
    assert replies[1]["content"] == notice["content"] and not replies[1].get("answer_ref")
