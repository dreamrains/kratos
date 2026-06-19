import json

import pandas as pd

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import get_config
from data_agent.session.workspace import Workspace
from data_agent.tools.chart_contract import ChartContractResult, infer_semantic_role
from data_agent.tools.visualization import create_chart


def _create_chart_in_session(tmp_path, session_id, **kwargs):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    chart_dir = cfg.sessions_dir / session_id / "charts"
    try:
        ctx = AgentContext(session_id=session_id, workspace=Workspace())
        with use_agent_context(ctx):
            result = create_chart(**kwargs)
        return result, chart_dir
    finally:
        cfg.sessions_dir = old_sessions


def test_numeric_user_identifier_is_not_a_measure():
    series = pd.Series([200000000000000001, 200000000000000002])

    assert infer_semantic_role("user_id", series) == "identifier"


def test_numeric_amount_is_a_measure():
    assert infer_semantic_role("revenue", pd.Series([10.5, 12.0])) == "measure"


def test_parseable_dates_are_time():
    assert infer_semantic_role(
        "paid_at",
        pd.Series(["2026-05-01", "2026-05-02"]),
    ) == "time"


def test_low_cardinality_text_is_category():
    assert infer_semantic_role("segment", pd.Series(["A", "B", "A"])) == "category"


def test_contract_result_is_valid_only_without_error():
    valid = ChartContractResult(dataframe=pd.DataFrame({"value": [1]}))
    invalid = ChartContractResult(
        dataframe=pd.DataFrame({"value": [1]}),
        error="invalid measure",
    )

    assert valid.valid is True
    assert invalid.valid is False


def test_high_cardinality_numeric_identifier_bar_is_rejected_without_artifacts(tmp_path):
    rows = [
        {"user_id": 200000000000000000 + i, "before": i + 1, "after": i + 2}
        for i in range(62)
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "identifier_bar",
        chart_type="bar",
        data_json=json.dumps(rows),
        x_col="user_id",
        y_col="before,after",
        title="Before and after by user",
    )

    payload = json.loads(result)
    assert payload["error_type"] == "chart_validation"
    assert payload["error_code"] == "unreadable_identifier_axis"
    assert {item["chart_type"] for item in payload["recovery_options"]} >= {
        "scatter",
        "box",
    }
    assert not chart_dir.exists()


def test_low_cardinality_numeric_identifier_bar_uses_category_axis(tmp_path):
    rows = [
        {"user_id": 200000000000000001, "revenue": 10},
        {"user_id": 200000000000000002, "revenue": 20},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "small_identifier_bar",
        chart_type="bar",
        data_json=json.dumps(rows),
        x_col="user_id",
        y_col="revenue",
        title="Revenue by selected user",
    )

    assert "Chart saved:" in result
    html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
    metadata = json.loads(
        next(chart_dir.glob("*.json")).read_text(encoding="utf-8")
    )
    assert '"x":["200000000000000001","200000000000000002"]' in html
    assert '"type":"category"' in html
    assert metadata["semantic_roles"]["user_id"] == "identifier"
    assert "identifier_to_category" in metadata["transformations"]
