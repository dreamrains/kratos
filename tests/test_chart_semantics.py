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


def test_high_cardinality_text_bar_is_rejected_without_artifacts(tmp_path):
    rows = [{"segment": f"segment-{i}", "value": i + 1} for i in range(41)]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "wide_category_bar",
        chart_type="bar",
        data_json=json.dumps(rows),
        x_col="segment",
        y_col="value",
        title="Value by segment",
    )

    assert json.loads(result)["error_code"] == "unreadable_category_axis"
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


def test_mostly_non_numeric_measure_is_rejected(tmp_path):
    rows = [
        {"segment": "A", "value": "bad"},
        {"segment": "B", "value": 2},
        {"segment": "C", "value": "also bad"},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "bad_measure",
        chart_type="bar",
        data_json=json.dumps(rows),
        x_col="segment",
        y_col="value",
        title="Bad measure",
    )

    payload = json.loads(result)
    assert payload["error_code"] == "invalid_measure"
    assert not chart_dir.exists()


def test_duplicate_bar_categories_require_explicit_aggregation(tmp_path):
    rows = [
        {"period": "before", "value": 10},
        {"period": "before", "value": 20},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "duplicate_bar",
        chart_type="bar",
        data_json=json.dumps(rows),
        x_col="period",
        y_col="value",
        title="Period value",
    )

    payload = json.loads(result)
    assert payload["error_code"] == "aggregation_required"
    assert {item["aggregation"] for item in payload["recovery_options"]} == {
        "sum",
        "mean",
        "median",
        "count",
    }
    assert not chart_dir.exists()


def test_duplicate_date_line_requires_explicit_aggregation(tmp_path):
    rows = [
        {"paid_at": "2026-05-01 10:00:00", "revenue": 10},
        {"paid_at": "2026-05-01 11:00:00", "revenue": 20},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "duplicate_line",
        chart_type="line",
        data_json=json.dumps(rows),
        x_col="paid_at",
        y_col="revenue",
        title="Daily revenue",
    )

    assert json.loads(result)["error_code"] == "aggregation_required"
    assert not chart_dir.exists()


def test_divergent_multi_metric_bar_requires_explicit_scale_mode(tmp_path):
    rows = [
        {"segment": "A", "revenue": 100, "exposure": 200_000_000},
        {"segment": "B", "revenue": 200, "exposure": 400_000_000},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "divergent_bar",
        chart_type="bar",
        data_json=json.dumps(rows),
        x_col="segment",
        y_col="revenue,exposure",
        title="Revenue and exposure",
    )

    assert json.loads(result)["error_code"] == "scale_mode_required"
    assert not chart_dir.exists()


def test_stacked_bar_duplicate_groups_require_explicit_aggregation(tmp_path):
    rows = [
        {"segment": "A", "period": "before", "value": 10},
        {"segment": "A", "period": "before", "value": 20},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "duplicate_stacked_bar",
        chart_type="stacked_bar",
        data_json=json.dumps(rows),
        x_col="segment",
        y_col="value",
        color_col="period",
        title="Stacked period value",
    )

    assert json.loads(result)["error_code"] == "aggregation_required"
    assert not chart_dir.exists()


def test_line_rejects_identifier_axis_even_without_trend_words(tmp_path):
    rows = [{"user_id": i, "value": i * 2} for i in range(1, 8)]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "identifier_line",
        chart_type="line",
        data_json=json.dumps(rows),
        x_col="user_id",
        y_col="value",
        title="User values",
    )

    assert json.loads(result)["error_code"] == "invalid_line_axis"
    assert not chart_dir.exists()


def test_line_rejects_high_cardinality_unordered_category_axis(tmp_path):
    rows = [{"label": f"label-{i}", "value": i + 1} for i in range(41)]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "unordered_line",
        chart_type="line",
        data_json=json.dumps(rows),
        x_col="label",
        y_col="value",
        title="Values",
    )

    assert json.loads(result)["error_code"] == "invalid_line_axis"
    assert not chart_dir.exists()


def test_scatter_rejects_numeric_identifier_measure(tmp_path):
    rows = [
        {"user_id": 1001, "revenue": 10},
        {"user_id": 1002, "revenue": 20},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "identifier_scatter",
        chart_type="scatter",
        data_json=json.dumps(rows),
        x_col="user_id",
        y_col="revenue",
        title="User revenue relationship",
    )

    assert json.loads(result)["error_code"] == "invalid_scatter_measure"
    assert not chart_dir.exists()


def test_scatter_rejects_mostly_non_numeric_axis(tmp_path):
    rows = [
        {"input": "bad", "output": 10},
        {"input": 2, "output": 20},
        {"input": "also bad", "output": 30},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "dirty_scatter",
        chart_type="scatter",
        data_json=json.dumps(rows),
        x_col="input",
        y_col="output",
        title="Input output relationship",
    )

    assert json.loads(result)["error_code"] == "invalid_scatter_measure"
    assert not chart_dir.exists()


def test_histogram_rejects_numeric_identifier(tmp_path):
    rows = [{"order_id": 10001}, {"order_id": 10002}]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "identifier_histogram",
        chart_type="histogram",
        data_json=json.dumps(rows),
        x_col="order_id",
        title="Order distribution",
    )

    assert json.loads(result)["error_code"] == "invalid_histogram_measure"
    assert not chart_dir.exists()


def test_histogram_rejects_mostly_non_numeric_values(tmp_path):
    rows = [{"value": "bad"}, {"value": 2}, {"value": "also bad"}]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "dirty_histogram",
        chart_type="histogram",
        data_json=json.dumps(rows),
        x_col="value",
        title="Value distribution",
    )

    assert json.loads(result)["error_code"] == "invalid_histogram_measure"
    assert not chart_dir.exists()


def test_box_uses_x_as_category_and_y_as_measure(tmp_path):
    rows = [
        {"period": "before", "value": 10},
        {"period": "before", "value": 20},
        {"period": "after", "value": 12},
        {"period": "after", "value": 18},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "grouped_box",
        chart_type="box",
        data_json=json.dumps(rows),
        x_col="period",
        y_col="value",
        title="Value distribution",
    )

    assert "Chart saved:" in result
    html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
    assert '"x":["before","before","after","after"]' in html
    assert '"y":[10,20,12,18]' in html


def test_pie_uses_category_labels_and_supplied_measure(tmp_path):
    rows = [
        {"segment": "A", "revenue": 100},
        {"segment": "B", "revenue": 20},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "measure_pie",
        chart_type="pie",
        data_json=json.dumps(rows),
        x_col="segment",
        y_col="revenue",
        title="Revenue share",
    )

    assert "Chart saved:" in result
    html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
    assert '"labels":["A","B"]' in html
    assert '"values":[100,20]' in html


def test_pie_rejects_negative_measure(tmp_path):
    rows = [
        {"segment": "A", "profit": 10},
        {"segment": "B", "profit": -5},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "negative_pie",
        chart_type="pie",
        data_json=json.dumps(rows),
        x_col="segment",
        y_col="profit",
        title="Profit share",
    )

    assert json.loads(result)["error_code"] == "invalid_pie_measure"
    assert not chart_dir.exists()


def test_pie_rejects_high_cardinality_instead_of_silent_top_ten(tmp_path):
    rows = [{"segment": f"S{i}"} for i in range(12)]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "wide_pie",
        chart_type="pie",
        data_json=json.dumps(rows),
        x_col="segment",
        title="Segment share",
    )

    assert json.loads(result)["error_code"] == "unreadable_pie_cardinality"
    assert not chart_dir.exists()


def test_heatmap_uses_only_explicit_numeric_columns(tmp_path):
    rows = [
        {"a": 1, "b": 2, "unrelated": 99},
        {"a": 2, "b": 4, "unrelated": 98},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "selected_heatmap",
        chart_type="heatmap",
        data_json=json.dumps(rows),
        x_col="a",
        y_col="b",
        title="A and B correlation",
    )

    assert "Chart saved:" in result
    html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
    assert "unrelated" not in html


def test_empty_chart_spec_is_rejected_before_save(tmp_path):
    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "empty_bar",
        chart_type="bar",
        data_json='[{"label":"A"}]',
        title="Empty bar",
    )

    payload = json.loads(result)
    assert payload["error_code"] == "non_renderable_figure"
    assert not chart_dir.exists()


def test_constant_heatmap_is_rejected_before_save(tmp_path):
    rows = [
        {"a": 1, "b": 2},
        {"a": 1, "b": 2},
    ]

    result, chart_dir = _create_chart_in_session(
        tmp_path,
        "constant_heatmap",
        chart_type="heatmap",
        data_json=json.dumps(rows),
        x_col="a",
        y_col="b",
        title="Constant correlation",
    )

    assert json.loads(result)["error_code"] == "non_renderable_figure"
    assert not chart_dir.exists()
