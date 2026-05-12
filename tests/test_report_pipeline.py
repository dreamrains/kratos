import json

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import get_config
from data_agent.session.history import session_charts_dir
from data_agent.session.task_manager import task_manager
from data_agent.session.workspace import Workspace
from data_agent.tools import report


def _use_tmp_sessions(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    return cfg, old_sessions


def test_formal_report_requires_evidence_and_creates_gap_task(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    ctx = AgentContext(session_id="formal_gap", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="formal_gap", goal="评估省钱卡")

    try:
        with use_agent_context(ctx):
            result = json.loads(report.generate_formal_report(format="html"))

        assert result["error_type"] == "insufficient_evidence"
        assert result["missing"] == ["evidence_records"]
        tasks = task_manager.list_all()
        assert any(t.get("node_type") == "evidence" for t in tasks)
    finally:
        cfg.sessions_dir = old_sessions
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_brief_report_uses_evidence_without_requiring_charts(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="brief_ok", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="brief_ok", goal="收入下降归因")
    ctx.analysis_state.evidence_records.append({
        "id": "ev_1",
        "claim": "收入下降主要来自付费用户数减少",
        "dataset": "pay",
        "method": "driver decomposition",
        "tool_calls": ["groupby"],
        "result_summary": "4月付费用户数下降 20%",
        "limitations": "样本期较短",
        "confidence": "medium",
    })

    try:
        with use_agent_context(ctx):
            result = json.loads(report.generate_analysis_brief(format="markdown"))

        assert result["type"] == "brief"
        assert result["artifact_path"].endswith(".md")
        content = (tmp_path / result["artifact_path"]).read_text(encoding="utf-8")
        assert "收入下降主要来自付费用户数减少" in content
        assert "样本期较短" in content
    finally:
        cfg.sessions_dir = old_sessions


def test_formal_report_references_evidence_ids_and_statistical_details(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="formal_ok", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="formal_ok", goal="漏斗分析")
    ctx.analysis_state.evidence_records.append({
        "id": "ev_funnel",
        "claim": "注册到付费步骤流失最大",
        "dataset": "funnel",
        "method": "funnel analysis",
        "tool_calls": ["funnel_analysis"],
        "result_summary": "该步骤转化率最低",
        "limitations": "未区分渠道",
        "confidence": "high",
        "metrics": [{"name": "付费转化率", "value": "12.4%", "delta": "-3.1pp"}],
        "sample_size": 1200,
        "time_scope": "2026-04",
        "calculation_method": "付费转化率 = 付费用户数 / 注册用户数",
        "method_detail": "按用户漏斗步骤聚合后计算每一步转化率",
        "significance": {"p_value": 0.03, "alpha": 0.05, "significant": True},
        "correlation": {"coefficient": -0.42, "method": "Pearson"},
        "confidence_interval": "[-4.8pp, -1.2pp]",
    })

    try:
        with use_agent_context(ctx):
            result = json.loads(report.generate_formal_report(format="html"))

        assert result["type"] == "formal"
        html = (tmp_path / result["artifact_path"]).read_text(encoding="utf-8")
        assert "ev_funnel" in html
        assert "一页结论摘要" in html
        assert "限制、可靠性与不能下结论的部分" in html
        assert "付费转化率 = 付费用户数 / 注册用户数" in html
        assert "p_value" in html
        assert "-0.42" in html
        assert "1200" in html
    finally:
        cfg.sessions_dir = old_sessions


def test_formal_report_lists_statistical_detail_gaps(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="formal_gaps", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="formal_gaps", goal="收入分析")
    ctx.analysis_state.evidence_records.append({
        "id": "ev_simple",
        "claim": "收入环比上升",
        "dataset": "sales",
        "method": "period compare",
        "tool_calls": ["compare_periods"],
        "result_summary": "收入环比上升 8%",
        "limitations": "未控制季节性",
        "confidence": "medium",
    })

    try:
        with use_agent_context(ctx):
            result = json.loads(report.generate_formal_report(format="markdown"))

        content = (tmp_path / result["artifact_path"]).read_text(encoding="utf-8")
        assert "统计说明缺口" in content
        assert "calculation_method" in content
        assert "sample_size" in content
    finally:
        cfg.sessions_dir = old_sessions


def test_legacy_generate_report_does_not_embed_unvalidated_charts(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    session_id = "legacy_report"
    chart_dir = session_charts_dir(session_id)
    (chart_dir / "bad_chart_abc123.html").write_text(
        '<div id="c" class="plotly-graph-div"></div><script>Plotly.newPlot("c", [], {})</script>',
        encoding="utf-8",
    )
    ctx = AgentContext(session_id=session_id, workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = json.loads(report.generate_report(title="Legacy", insights="[]", summary="只生成文字报告"))

        assert result["type"] == "brief"
        html = (tmp_path / result["artifact_path"]).read_text(encoding="utf-8")
        assert "bad_chart" not in html
    finally:
        cfg.sessions_dir = old_sessions


def test_record_insight_record_persists_to_analysis_state(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="insight_state", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="insight_state")
    payload = {
        "title": "收入下降来自新增用户减少",
        "summary": "新增用户减少解释了主要变化",
        "evidence_ids": ["ev_1"],
        "chart_ids": [],
        "recommendation": "补充渠道拉新数据",
        "limitations": "未区分渠道",
        "confidence": "medium",
        "output_type": "finding",
    }

    try:
        from data_agent.tools.analysis_flow import record_insight_record
        with use_agent_context(ctx):
            result = json.loads(record_insight_record(json.dumps(payload, ensure_ascii=False)))

        assert result["insight_id"]
        assert ctx.analysis_state.insight_records[0]["title"] == "收入下降来自新增用户减少"
    finally:
        cfg.sessions_dir = old_sessions
