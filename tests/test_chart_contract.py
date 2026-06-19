import json
from pathlib import Path

import pandas as pd

from data_agent.config import get_config
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace
from data_agent.tools.visualization import create_chart
from data_agent.tools.registry import registry


def _use_tmp_sessions(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    return cfg, old_sessions


def test_time_trend_rejects_identifier_axis(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("pay", pd.DataFrame({
        "user_id": [101, 102, 103],
        "revenue": [10, 20, 30],
    }))
    ctx = AgentContext(session_id="chart_bad_axis", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = json.loads(create_chart("line", data="pay", x_col="user_id", y_col="revenue", title="月度收入趋势"))

        assert result["error_type"] == "chart_validation"
        assert "identifier" in " ".join(result["validation_warnings"]).lower()
    finally:
        cfg.sessions_dir = old_sessions


def test_valid_chart_writes_metadata_artifact(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("pay", pd.DataFrame({
        "month": ["2026-03", "2026-04", "2026-05"],
        "revenue": [100, 150, 180],
    }))
    ctx = AgentContext(session_id="chart_valid", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart("bar", data="pay", x_col="month", y_col="revenue", title="收入月度对比")

        assert "Chart saved:" in result
        metadata_files = list((tmp_path / "sessions" / "chart_valid" / "charts").glob("*.json"))
        assert metadata_files, "expected chart metadata JSON"
        metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
        assert metadata["validation_status"] == "valid"
        assert metadata["chart_type"] == "bar"
        assert metadata["dataset"] == "pay"
        assert metadata["x_col"] == "month"
        assert metadata["y_cols"] == ["revenue"]
    finally:
        cfg.sessions_dir = old_sessions


def test_multi_metric_chart_warns_on_missing_metric_by_group(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("pay", pd.DataFrame({
        "month": ["2026-03", "2026-04", "2026-05"],
        "revenue": [100, 150, 180],
        "users": [10, None, 18],
    }))
    ctx = AgentContext(session_id="chart_warn", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart("bar", data="pay", x_col="month", y_col="revenue,users", title="收入与用户数")

        assert "Chart saved:" in result
        metadata_files = list((tmp_path / "sessions" / "chart_warn" / "charts").glob("*.json"))
        metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
        assert metadata["validation_status"] == "warning"
        assert any("missing" in w.lower() for w in metadata["validation_warnings"])
    finally:
        cfg.sessions_dir = old_sessions


def test_chart_metadata_records_exploratory_purpose_by_default(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("pay", pd.DataFrame({
        "month": ["2026-03", "2026-04"],
        "revenue": [100, 150],
    }))
    ctx = AgentContext(session_id="chart_purpose", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart("bar", data="pay", x_col="month", y_col="revenue", title="收入对比")

        assert "Chart saved:" in result
        metadata_files = list((tmp_path / "sessions" / "chart_purpose" / "charts").glob("*.json"))
        metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
        assert metadata["purpose"] == "exploratory"
        assert metadata["evidence_ids"] == []
    finally:
        cfg.sessions_dir = old_sessions


def test_chart_metadata_can_bind_evidence_ids(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("pay", pd.DataFrame({
        "month": ["2026-03", "2026-04"],
        "revenue": [100, 150],
    }))
    ctx = AgentContext(session_id="chart_evidence", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "bar",
                data="pay",
                x_col="month",
                y_col="revenue",
                title="收入证据图",
                purpose="evidence",
                evidence_ids="ev_1, ev_2",
            )

        assert "Chart saved:" in result
        metadata_files = list((tmp_path / "sessions" / "chart_evidence" / "charts").glob("*.json"))
        metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
        assert metadata["purpose"] == "evidence"
        assert metadata["evidence_ids"] == ["ev_1", "ev_2"]
    finally:
        cfg.sessions_dir = old_sessions


def test_evidence_or_insight_chart_requires_evidence_ids(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_missing_evidence", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = json.loads(create_chart(
                "bar",
                data_json='[{"segment":"A","value":1}]',
                x_col="segment",
                y_col="value",
                title="Evidence chart",
                purpose="evidence",
            ))

        assert result["error_type"] == "chart_validation"
        assert "evidence_ids" in result["error"]
    finally:
        cfg.sessions_dir = old_sessions


def test_grouped_bar_chart_handles_interval_axis_and_color_grouping(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    amounts = [3, 8, 40, 3, 8, 40]
    ws.add("dist", pd.DataFrame({
        "bucket": pd.cut(amounts, bins=[0, 6, 18, 50]),
        "period": ["before", "before", "before", "after", "after", "after"],
        "orders": [12, 8, 0, 9, 7, 3],
    }))
    ctx = AgentContext(session_id="chart_grouped_bar", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "bar",
                data="dist",
                x_col="bucket",
                y_col="orders",
                color_col="period",
                title="Amount Distribution",
                purpose="insight",
                evidence_ids="ev_amount_distribution",
            )

        assert "Chart saved:" in result
        chart_dir = tmp_path / "sessions" / "chart_grouped_bar" / "charts"
        html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
        assert '"name":"before"' in html
        assert '"name":"after"' in html
        assert "(0, 6]" in html
        metadata = json.loads(next(chart_dir.glob("*.json")).read_text(encoding="utf-8"))
        assert metadata["color_col"] == "period"
        assert metadata["validation_status"] == "valid"
    finally:
        cfg.sessions_dir = old_sessions


def test_line_chart_color_col_creates_grouped_traces(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("daily", pd.DataFrame({
        "date": ["2026-05-01", "2026-05-02", "2026-05-01", "2026-05-02"],
        "company": ["internal", "internal", "external", "external"],
        "revenue": [10, 12, 7, 9],
    }))
    ctx = AgentContext(session_id="chart_grouped_line", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "line",
                data="daily",
                x_col="date",
                y_col="revenue",
                color_col="company",
                title="Daily revenue trend",
            )

        assert "Chart saved:" in result
        html = next((tmp_path / "sessions" / "chart_grouped_line" / "charts").glob("*.html")).read_text(encoding="utf-8")
        assert '"name":"internal"' in html
        assert '"name":"external"' in html
    finally:
        cfg.sessions_dir = old_sessions


def test_line_chart_aggregates_duplicate_dates_to_daily_sum(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("orders", pd.DataFrame({
        "paid_at": [
            "2026-05-01 10:00:00",
            "2026-05-01 11:00:00",
            "2026-05-02 09:00:00",
        ],
        "revenue": [10, 15, 7],
    }))
    ctx = AgentContext(session_id="chart_daily_sum", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "line",
                data="orders",
                x_col="paid_at",
                y_col="revenue",
                aggregation="sum",
                title="Daily revenue trend",
            )

        assert "Chart saved:" in result
        chart_dir = tmp_path / "sessions" / "chart_daily_sum" / "charts"
        html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
        metadata = json.loads(next(chart_dir.glob("*.json")).read_text(encoding="utf-8"))
        assert "2026-05-01" in html
        assert "2026-05-02" in html
        assert "2026-05-01 10:00:00" not in html
        assert metadata["aggregation"] == "sum_by_day"
        assert "aggregation:sum" in metadata["transformations"]
        assert metadata["row_count"] == 2
    finally:
        cfg.sessions_dir = old_sessions


def test_bar_chart_aggregates_duplicate_x_groups_for_multi_metric_comparison(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("active_days", pd.DataFrame({
        "period": ["before", "before", "after", "after"],
        "active_days": [20, 16, 15, 17],
        "orders": [80, 60, 50, 46],
    }))
    ctx = AgentContext(session_id="chart_bar_duplicate_x", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "bar",
                data="active_days",
                x_col="period",
                y_col="active_days,orders",
                aggregation="mean",
                title="Before after active payment days",
            )

        assert "Chart saved:" in result
        chart_dir = tmp_path / "sessions" / "chart_bar_duplicate_x" / "charts"
        html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
        metadata = json.loads(next(chart_dir.glob("*.json")).read_text(encoding="utf-8"))
        assert '"x":["after","before"]' in html or '"x":["before","after"]' in html
        assert metadata["aggregation"] == "mean_by_x"
        assert "aggregation:mean" in metadata["transformations"]
        assert metadata["row_count"] == 2
    finally:
        cfg.sessions_dir = old_sessions


def test_funnel_chart_uses_stage_value_labels(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_funnel_stage", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "funnel",
                title="Conversion funnel",
                data_json='[{"stage":"曝光次数","value":1000},{"stage":"有效点击次数","value":12}]',
            )

        assert "Chart saved:" in result
        html = next((tmp_path / "sessions" / "chart_funnel_stage" / "charts").glob("*.html")).read_text(encoding="utf-8")
        assert "曝光次数" in html
        assert "有效点击次数" in html
        assert '"y":["曝光次数","有效点击次数"]' in html
    finally:
        cfg.sessions_dir = old_sessions


def test_funnel_chart_accepts_chinese_step_value_keys(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_funnel_chinese_keys", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "funnel",
                title="Overall ad funnel",
                data_json='[{"步骤":"① 曝光次数","数值":430785712},{"步骤":"② 有效点击次数","数值":5217534}]',
            )

        assert "Chart saved:" in result
        html = next((tmp_path / "sessions" / "chart_funnel_chinese_keys" / "charts").glob("*.html")).read_text(encoding="utf-8")
        assert "① 曝光次数" in html
        assert "② 有效点击次数" in html
        assert '"x":[430785712.0,5217534.0]' in html
    finally:
        cfg.sessions_dir = old_sessions


def test_funnel_chart_rejects_unreadable_step_or_value_keys(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_funnel_bad_keys", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = json.loads(create_chart(
                "funnel",
                title="Bad funnel",
                data_json='[{"foo":"曝光","bar":100}]',
            ))

        assert result["error_type"] == "chart_validation"
        assert "funnel" in result["error"].lower()
        assert not (tmp_path / "sessions" / "chart_funnel_bad_keys" / "charts").exists()
    finally:
        cfg.sessions_dir = old_sessions


def test_funnel_chart_rejects_mixed_revenue_stage(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_funnel_mixed_units", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = json.loads(create_chart(
                "funnel",
                title="Exposure to revenue",
                data_json='[{"stage":"曝光次数","value":430785712},{"stage":"有效点击","value":5217534},{"stage":"卖量收入","value":451286.73}]',
            ))

        assert result["error_type"] == "chart_validation"
        assert "revenue" in result["error"].lower() or "amount" in result["error"].lower()
        assert not (tmp_path / "sessions" / "chart_funnel_mixed_units" / "charts").exists()
    finally:
        cfg.sessions_dir = old_sessions


def test_multi_metric_bar_with_different_scales_uses_normalized_single_axis(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ws = Workspace()
    ws.add("metrics", pd.DataFrame({
        "company": ["internal", "external"],
        "revenue": [1000, 2000],
        "exposure": [200_000_000, 400_000_000],
        "clicks": [2_000_000, 3_000_000],
    }))
    ctx = AgentContext(session_id="chart_normalized_bar", workspace=ws)

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "bar",
                data="metrics",
                x_col="company",
                y_col="revenue,exposure,clicks",
                scale_mode="normalize",
                title="Metric total comparison",
            )

        assert "Chart saved:" in result
        chart_dir = tmp_path / "sessions" / "chart_normalized_bar" / "charts"
        html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
        metadata = json.loads(next(chart_dir.glob("*.json")).read_text(encoding="utf-8"))
        assert '"yaxis2"' not in html
        assert "Normalized value" in html
        assert "Original value" in html
        assert metadata["validation_status"] == "warning"
        assert any("normalized" in w.lower() for w in metadata["validation_warnings"])
        assert "scale:normalize" in metadata["transformations"]
    finally:
        cfg.sessions_dir = old_sessions


def test_registry_web_result_includes_chart_artifact_for_saved_chart(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_registry_artifact", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = registry.execute("create_chart", {
                "chart_type": "bar",
                "data_json": '[{"segment":"A","value":1}]',
                "x_col": "segment",
                "y_col": "value",
                "title": "Registry Chart",
            })

        web = result.to_web()
        assert web["artifacts"][0]["type"] == "chart"
        assert web["artifacts"][0]["path"].startswith("sessions/chart_registry_artifact/charts/")
        assert web["artifacts"][0]["description"].startswith("Registry_Chart")
    finally:
        cfg.sessions_dir = old_sessions


def test_scatter_rejects_non_numeric_axes(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_bad_scatter", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = json.loads(create_chart(
                "scatter",
                data_json='[{"segment":"A","value":1},{"segment":"B","value":2}]',
                x_col="segment",
                y_col="value",
                title="Segment relationship",
            ))

        assert result["error_type"] == "chart_validation"
        assert "scatter" in result["error"].lower()
        assert "numeric" in result["error"].lower()
    finally:
        cfg.sessions_dir = old_sessions


def test_histogram_rejects_non_numeric_metric(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_bad_histogram", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = json.loads(create_chart(
                "histogram",
                data_json='[{"company":"internal"},{"company":"external"}]',
                x_col="company",
                title="Company distribution",
            ))

        assert result["error_type"] == "chart_validation"
        assert "histogram" in result["error"].lower()
        assert "numeric" in result["error"].lower()
    finally:
        cfg.sessions_dir = old_sessions


def test_rate_title_warns_when_metric_is_count_column(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="chart_rate_title_count_metric", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "bar",
                data_json='[{"day":"2026-05-01","clicks":10},{"day":"2026-05-02","clicks":20}]',
                x_col="day",
                y_col="clicks",
                title="CTR trend",
            )

        assert "Chart saved:" in result
        metadata = json.loads(next((tmp_path / "sessions" / "chart_rate_title_count_metric" / "charts").glob("*.json")).read_text(encoding="utf-8"))
        assert metadata["validation_status"] == "warning"
        assert any("rate" in w.lower() for w in metadata["validation_warnings"])
    finally:
        cfg.sessions_dir = old_sessions


def test_pie_warns_when_category_cardinality_is_high(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    rows = [{"game": f"g{i}"} for i in range(12)]
    ctx = AgentContext(session_id="chart_pie_many_categories", workspace=Workspace())

    try:
        with use_agent_context(ctx):
            result = create_chart(
                "pie",
                data_json=json.dumps(rows),
                x_col="game",
                title="Game share",
            )

        assert "Chart saved:" in result
        metadata = json.loads(next((tmp_path / "sessions" / "chart_pie_many_categories" / "charts").glob("*.json")).read_text(encoding="utf-8"))
        assert metadata["validation_status"] == "warning"
        assert any("pie" in w.lower() and "top 10" in w.lower() for w in metadata["validation_warnings"])
    finally:
        cfg.sessions_dir = old_sessions


def test_create_chart_recovery_hint_does_not_suggest_mermaid_for_data_charts():
    tool = registry.get("create_chart")

    assert tool is not None
    assert "Mermaid" not in tool.recovery_hint
