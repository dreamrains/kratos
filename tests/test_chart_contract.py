import json
from pathlib import Path

import pandas as pd

from data_agent.config import get_config
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace
from data_agent.tools.visualization import create_chart


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
