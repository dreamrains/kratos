import json

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
    save_session([
        {"role": "user", "content": "分析收入"},
        {"role": "assistant", "content": "## 结论\n收入增长，限制是样本较短。"},
    ], session_id)
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


def test_export_conversation_pdf_degrades_when_dependency_or_render_fails(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    session_id = "export_pdf"
    save_session([
        {"role": "user", "content": "导出"},
        {"role": "assistant", "content": "这是一段可以导出的分析结论，包含限制和下一步。"},
    ], session_id)
    ctx = AgentContext(session_id=session_id, workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = json.loads(export_conversation(format="pdf"))

        assert result["format"] == "pdf"
        assert result["status"] in {"exported", "degraded"}
        if result["status"] == "degraded":
            assert result["fallback_artifact_path"].endswith(".html")
            assert "reason" in result
    finally:
        cfg.sessions_dir = old_sessions


def test_web_export_pdf_and_formal_report_endpoint(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    session_id = "web_export"
    save_session([
        {"role": "user", "content": "分析漏斗"},
        {"role": "assistant", "content": "漏斗分析结论：注册到付费步骤流失最大，需要补充渠道维度。"},
    ], session_id)
    state_dir = tmp_path / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "analysis_state.json").write_text(json.dumps({
        "session_id": session_id,
        "goal": "漏斗分析",
        "stage": "execute",
        "data_state": "data_loaded",
        "evidence_records": [{
            "id": "ev_web",
            "claim": "注册到付费步骤流失最大",
            "dataset": "funnel",
            "method": "funnel analysis",
            "tool_calls": ["funnel_analysis"],
            "result_summary": "该步骤转化率最低",
            "limitations": "未区分渠道",
            "confidence": "high",
        }],
    }, ensure_ascii=False), encoding="utf-8")

    try:
        from data_agent.web.app import create_app
        app = create_app()
        client = app.test_client()

        pdf_resp = client.get(f"/api/sessions/{session_id}/export?format=pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.get_json()["format"] == "pdf"

        report_resp = client.get(f"/api/sessions/{session_id}/report?type=formal&format=html")
        assert report_resp.status_code == 200
        body = report_resp.get_json()
        assert body["type"] == "formal"
        assert body["artifact_path"].endswith(".html")
    finally:
        cfg.sessions_dir = old_sessions
