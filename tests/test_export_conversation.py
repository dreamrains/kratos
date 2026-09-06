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


def test_export_includes_publication_receipt_and_pending_findings(tmp_path):
    """P7-L3/B03：导出保留发布来源、收据引用、省略说明与待验证标签。"""
    import json as _json

    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.publication_synthesis import build_publication_packet

    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    session_id = "export_packet"
    state = AnalysisSessionState(session_id=session_id, data_state="data_loaded")
    state.add_tool_receipt({
        "id": "tr_export_1",
        "tool_name": "run_python",
        "result_sha256": "sha256:e1",
        "result_preview": "amount_sum=120 over 12 orders",
        "publication_facts": [{"path": "amount_sum", "value": "120"}],
        "publication_contract": {
            "schema_version": "publication_scope.v1", "tool": "run_python",
            "source_dataset": "orders", "inference_performed": False,
        },
    })
    packet = build_publication_packet(
        state, user_input="分析订单合计", substantive_tools={"run_python"},
    )
    state.add_publication_packet(packet)
    state.hypothesis_sets = [{
        "id": "hyps_orders_trend",
        "dataset": "orders",
        "route": "trend",
        "count": 1,
        "hypotheses": [{
            "id": "hyps_orders_trend_h2",
            "claim": "收入变化由订单量驱动",
            "status": "inconclusive",
            "claim_type": "causal",
            "related_evidence_ids": [],
            "supporting_evidence_ids": [],
            "conflicting_evidence_ids": [],
            "evidence_requirements": [{"kind": "metric", "field": "orders", "required": True}],
        }],
    }]
    state.save()
    save_session(
        [
            {"role": "user", "content": "分析订单合计"},
            {"role": "assistant", "content": "## 结论\n当前 12 条订单合计 120，仅覆盖当前记录，不能外推总体。"},
        ],
        session_id,
    )
    ctx = AgentContext(session_id=session_id, workspace=Workspace())

    try:
        with use_agent_context(ctx):
            md_result = _json.loads(export_conversation(format="markdown"))
            html_result = _json.loads(export_conversation(format="html"))

        md_text = (tmp_path / md_result["artifact_path"]).read_text(encoding="utf-8")
        html_text = (tmp_path / html_result["artifact_path"]).read_text(encoding="utf-8")
        for text in (md_text, html_text):
            assert "计算来源与省略说明" in text
            assert "tr_export_1" in text
            assert "待验证发现" in text
            assert "未决" in text
            assert "orders" in text
    finally:
        cfg.sessions_dir = old_sessions
