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


def test_web_export_pdf_is_not_supported(tmp_path):
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

        assert pdf_resp.status_code == 400
        body = pdf_resp.get_json()
        assert body["error_type"] == "unsupported_export_format"
        assert "pdf" not in body["supported_formats"]
    finally:
        cfg.sessions_dir = old_sessions


def test_web_report_brief_and_formal_are_deprecated(tmp_path):
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

        for report_type in ("brief", "formal"):
            resp = client.get(f"/api/sessions/{session_id}/report?type={report_type}&format=html")

            assert resp.status_code == 410
            body = resp.get_json()
            assert body["error_type"] == "report_artifact_deprecated"
            assert body["report_type"] == report_type
            assert body["supported_actions"] == ["chat_synthesis", "export_conversation"]
    finally:
        cfg.sessions_dir = old_sessions
