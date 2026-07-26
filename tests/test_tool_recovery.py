import json

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.task_manager import task_manager
from data_agent.session.workspace import Workspace
from data_agent.tools.ml import forecast
from data_agent.tools.registry import registry
from data_agent.tools.sandbox import run_python
from data_agent.tools.task_tools import task_create


def test_forecast_accepts_string_periods_and_marks_simple_fallback():
    ws = Workspace()
    ws.add("sales", pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=20),
        "revenue": list(range(20, 40)),
    }))
    ctx = AgentContext(session_id="forecast_string", workspace=ws)

    with use_agent_context(ctx):
        result = json.loads(forecast("sales", target_col="revenue", date_col="date", periods="3", method="simple"))

    assert len(result["forecast"]) == 3
    assert result["periods"] == 3
    assert result["fallback_used"] is False


def test_forecast_rejects_invalid_periods_with_structured_error():
    ws = Workspace()
    ws.add("sales", pd.DataFrame({"date": pd.date_range("2026-01-01", periods=20), "revenue": range(20)}))
    ctx = AgentContext(session_id="forecast_bad_period", workspace=ws)

    with use_agent_context(ctx):
        result = json.loads(forecast("sales", target_col="revenue", date_col="date", periods="abc", method="simple"))

    assert "error" in result
    assert result["error_type"] == "invalid_parameter"
    assert "periods" in result["field"]


def test_forecast_infers_date_column_when_missing():
    ws = Workspace()
    ws.add("sales", pd.DataFrame({
        "biz_date": pd.date_range("2026-01-01", periods=20),
        "revenue": list(range(20, 40)),
    }))
    ctx = AgentContext(session_id="forecast_infer_date", workspace=ws)

    with use_agent_context(ctx):
        result = json.loads(forecast("sales", target_col="revenue", periods=2, method="simple"))

    assert result["date_col"] == "biz_date"
    assert len(result["forecast"]) == 2


def test_run_python_sandbox_error_contains_recovery_hint():
    result = json.loads(run_python("open('x.txt').read()"))

    assert "error" in result
    assert result["error_type"] == "sandbox_violation"
    assert "alternatives" in result
    assert "describe_dataset" in " ".join(result["alternatives"])


def test_run_python_result_marks_fallback_policy_and_purpose():
    result = json.loads(run_python("1 + 1", purpose="quick unsupported calculation check"))

    assert result["result"] == "2"
    assert result["fallback_policy"]["role"] == "supplemental"
    assert result["fallback_policy"]["purpose"] == "quick unsupported calculation check"


def test_task_create_inherits_current_analysis_plan(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0
    ctx = AgentContext(session_id="task_inherit", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(
        session_id="task_inherit",
        analysis_plan={
            "id": "plan_123",
            "workflow_id": "wf_123",
            "confirmation_policy": {"requires_confirmation": True},
        },
    )

    try:
        with use_agent_context(ctx):
            task = json.loads(task_create(subject="check revenue", node_type="analysis", required_capability="data.describe"))

        assert task["analysis_plan_id"] == "plan_123"
        assert task["analysis_spec_id"] == "plan_123"
        assert task["workflow_id"] == "wf_123"
        assert task["stage"] == "execute"
        assert task["confirmation_policy"]["requires_confirmation"] is True
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id


def test_task_create_title_alias_is_compatible_but_conflicts_fail(tmp_path):
    old_task_dir = task_manager._dir
    old_next_id = task_manager._next_id_val
    task_manager._dir = tmp_path / "tasks"
    task_manager._next_id_val = 0

    try:
        aliased = registry.execute("task_create", {"title": "检查缺失值"})
        assert aliased.data is None
        assert json.loads(aliased.summary)["subject"] == "检查缺失值"

        conflict = registry.execute(
            "task_create",
            {"subject": "A", "title": "B"},
        )
        payload = json.loads(conflict.summary)
        assert payload["error_type"] == "invalid_tool_arguments"
        assert payload == conflict.data
    finally:
        task_manager._dir = old_task_dir
        task_manager._next_id_val = old_next_id
