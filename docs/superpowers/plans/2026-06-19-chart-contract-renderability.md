# Chart Contract and Renderability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent semantically invalid or unreadable analytical charts from being saved, while preserving valid chart behavior and returning actionable recovery guidance.

**Architecture:** Add a focused `chart_contract.py` module for semantic typing, chart-specific validation, safe transformations, and figure renderability checks. Keep Plotly trace construction and artifact persistence in `visualization.py`, but require every request to pass the contract before `_save_chart` is called. Implement one chart family per TDD slice and keep all confirmation, multi-file, Trust View, and side-panel code untouched.

**Tech Stack:** Python 3.12, pandas, Plotly graph objects, pytest, existing `Workspace`, `AgentContext`, and artifact registry helpers.

---

## File Map

- Create `src/data_agent/tools/chart_contract.py`: semantic roles, validation result, recovery options, safe dataframe preparation, and Plotly figure renderability checks.
- Modify `src/data_agent/tools/visualization.py`: call the contract, use prepared axes, require explicit duplicate aggregation, correct chart-family trace semantics, and save only renderable figures.
- Modify `tests/test_chart_contract.py`: preserve existing public behavior tests and update the one test that currently relies on implicit mean aggregation.
- Create `tests/test_chart_semantics.py`: regression matrix for identifiers, cardinality, numeric quality, chart-family semantics, recovery responses, and artifact non-creation.
- Read-only verification consumers: `src/data_agent/tools/registry.py`, `src/data_agent/tools/report.py`, `src/data_agent/session/history.py`, `tests/test_report_strategy.py`, and artifact-related tests.

## Task 1: Semantic Roles and Structured Validation Result

**Files:**
- Create: `src/data_agent/tools/chart_contract.py`
- Create: `tests/test_chart_semantics.py`

- [ ] **Step 1: Write failing semantic-role tests**

```python
import json

import pandas as pd

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.config import get_config
from data_agent.session.workspace import Workspace
from data_agent.tools.visualization import create_chart
from data_agent.tools.chart_contract import infer_semantic_role


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
    assert infer_semantic_role("paid_at", pd.Series(["2026-05-01", "2026-05-02"])) == "time"


def test_low_cardinality_text_is_category():
    assert infer_semantic_role("segment", pd.Series(["A", "B", "A"])) == "category"
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q
```

Expected: collection fails because `data_agent.tools.chart_contract` does not exist.

- [ ] **Step 3: Implement semantic typing and validation result**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


IDENTIFIER_TOKENS = ("id", "uid", "user", "account", "member", "customer", "用户", "账号", "会员")


@dataclass
class ChartContractResult:
    dataframe: pd.DataFrame
    semantic_roles: dict[str, str] = field(default_factory=dict)
    transformations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    recovery_options: list[dict[str, str]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.error


def infer_semantic_role(column: str, series: pd.Series) -> str:
    name = str(column or "").casefold()
    unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
    if any(token in name for token in IDENTIFIER_TOKENS) and unique_ratio >= 0.7:
        return "identifier"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "time"
    if not pd.api.types.is_numeric_dtype(series):
        parsed = pd.to_datetime(series.dropna().astype(str), errors="coerce")
        if len(parsed) and parsed.notna().mean() >= 0.8:
            return "time"
    numeric = pd.to_numeric(series, errors="coerce")
    if len(series) and numeric.notna().mean() >= 0.8:
        return "measure"
    if series.nunique(dropna=True) <= max(20, len(series) // 2):
        return "category"
    return "unknown"
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit the semantic foundation**

```powershell
git add src/data_agent/tools/chart_contract.py tests/test_chart_semantics.py
git commit -m "feat: add chart semantic roles"
```

## Task 2: Identifier Axes, Cardinality, and Reported Regression

**Files:**
- Modify: `src/data_agent/tools/chart_contract.py`
- Modify: `src/data_agent/tools/visualization.py`
- Modify: `tests/test_chart_semantics.py`

- [ ] **Step 1: Write the failing reported-shape tests**

Add a local session-directory fixture equivalent to `_use_tmp_sessions` and these tests:

```python
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
    assert {item["chart_type"] for item in payload["recovery_options"]} >= {"scatter", "box"}
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
    metadata = json.loads(next(chart_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert '"x":["200000000000000001","200000000000000002"]' in html
    assert metadata["semantic_roles"]["user_id"] == "identifier"
    assert "identifier_to_category" in metadata["transformations"]
```

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q -k "identifier_bar"
```

Expected: the 62-user request still returns `Chart saved`, and low-cardinality identifiers remain numeric in serialized Plotly data.

- [ ] **Step 3: Add identifier-axis contract validation**

Implement in `chart_contract.py`:

```python
MAX_BAR_CATEGORIES = 40


def validate_chart_request(
    df: pd.DataFrame,
    chart_type: str,
    x_col: str,
    y_cols: list[str],
    color_col: str = "",
    aggregation: str = "",
) -> ChartContractResult:
    result = ChartContractResult(dataframe=df.copy())
    referenced = [name for name in [x_col, *y_cols, color_col] if name]
    result.semantic_roles = {
        name: infer_semantic_role(name, result.dataframe[name])
        for name in referenced
        if name in result.dataframe.columns
    }
    if chart_type in {"bar", "stacked_bar"} and x_col:
        count = int(result.dataframe[x_col].nunique(dropna=True))
        if result.semantic_roles.get(x_col) == "identifier" and count > MAX_BAR_CATEGORIES:
            result.error = "Identifier axis has too many categories for a readable bar chart."
            result.recovery_options = [
                {"chart_type": "scatter", "description": "Compare before and after measures directly."},
                {"chart_type": "box", "description": "Compare distributions without one bar per identifier."},
                {"chart_type": "bar", "description": "Aggregate or select a documented Top N first."},
            ]
            return result
        if result.semantic_roles.get(x_col) == "identifier":
            result.dataframe[x_col] = result.dataframe[x_col].map(lambda value: "" if pd.isna(value) else str(value))
            result.transformations.append("identifier_to_category")
    return result
```

Extend `_chart_error` in `visualization.py` to accept `error_code` and `recovery_options`, call `validate_chart_request` before `_prepare_chart_dataframe`, and copy `semantic_roles`, `transformations`, and `category_count` into metadata.

- [ ] **Step 4: Run the two tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q -k "identifier_bar"
```

Expected: both tests pass and rejected requests create no chart directory.

- [ ] **Step 5: Run existing chart tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_chart_semantics.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit the identifier-axis fix**

```powershell
git add src/data_agent/tools/chart_contract.py src/data_agent/tools/visualization.py tests/test_chart_semantics.py
git commit -m "fix: reject unreadable identifier charts"
```

## Task 3: Numeric Quality and Explicit Aggregation

**Files:**
- Modify: `src/data_agent/tools/chart_contract.py`
- Modify: `src/data_agent/tools/visualization.py`
- Modify: `tests/test_chart_contract.py`
- Modify: `tests/test_chart_semantics.py`

- [ ] **Step 1: Write failing numeric-quality and duplicate-category tests**

```python
def test_mostly_non_numeric_measure_is_rejected(tmp_path):
    rows = [{"segment": "A", "value": "bad"}, {"segment": "B", "value": 2}, {"segment": "C", "value": "also bad"}]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "bad_measure", chart_type="bar", data_json=json.dumps(rows),
        x_col="segment", y_col="value", title="Bad measure",
    )
    payload = json.loads(result)
    assert payload["error_code"] == "invalid_measure"
    assert not chart_dir.exists()


def test_duplicate_bar_categories_require_explicit_aggregation(tmp_path):
    rows = [{"period": "before", "value": 10}, {"period": "before", "value": 20}]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "duplicate_bar", chart_type="bar", data_json=json.dumps(rows),
        x_col="period", y_col="value", title="Period value",
    )
    payload = json.loads(result)
    assert payload["error_code"] == "aggregation_required"
    assert {item["aggregation"] for item in payload["recovery_options"]} == {"sum", "mean", "median", "count"}
    assert not chart_dir.exists()


def test_duplicate_date_line_requires_explicit_aggregation(tmp_path):
    rows = [
        {"paid_at": "2026-05-01 10:00:00", "revenue": 10},
        {"paid_at": "2026-05-01 11:00:00", "revenue": 20},
    ]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "duplicate_line", chart_type="line", data_json=json.dumps(rows),
        x_col="paid_at", y_col="revenue", title="Daily revenue",
    )
    assert json.loads(result)["error_code"] == "aggregation_required"
    assert not chart_dir.exists()


def test_divergent_multi_metric_bar_requires_explicit_scale_mode(tmp_path):
    rows = [
        {"segment": "A", "revenue": 100, "exposure": 200_000_000},
        {"segment": "B", "revenue": 200, "exposure": 400_000_000},
    ]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "divergent_bar", chart_type="bar", data_json=json.dumps(rows),
        x_col="segment", y_col="revenue,exposure", title="Revenue and exposure",
    )
    assert json.loads(result)["error_code"] == "scale_mode_required"
    assert not chart_dir.exists()
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q -k "mostly_non_numeric or duplicate_bar or duplicate_date or divergent_multi"
```

Expected: mostly non-numeric input is accepted because one value coerces, bar duplicates are silently averaged, date duplicates are silently summed, and divergent metrics are silently normalized.

- [ ] **Step 3: Add `aggregation` to the public tool schema and contract**

Add optional arguments `aggregation` with enum `"", "sum", "mean", "median", "count"` and `scale_mode` with enum `"", "raw", "normalize"`. In `chart_contract.py`, reject duplicate bar or normalized-date line groups when aggregation is empty, reject divergent multi-metric bars when `scale_mode` is empty, and apply only the requested behavior:

```python
AGGREGATIONS = {
    "sum": "sum",
    "mean": "mean",
    "median": "median",
    "count": "count",
}


def aggregate_bar_rows(df, group_cols, y_cols, aggregation):
    if aggregation not in AGGREGATIONS:
        raise ValueError(f"Unsupported aggregation: {aggregation}")
    return df.groupby(group_cols, sort=False, dropna=False)[y_cols].agg(AGGREGATIONS[aggregation]).reset_index()
```

Require at least 80% finite numeric values for measure columns, coerce accepted measure columns to numeric, and record `aggregation:<name>` in transformations.

- [ ] **Step 4: Update the existing intentional-mean test**

Change `test_bar_chart_aggregates_duplicate_x_groups_for_multi_metric_comparison` to call:

```python
create_chart(
    "bar",
    data="active_days",
    x_col="period",
    y_col="active_days,orders",
    aggregation="mean",
    title="Before after active payment days",
)
```

Assert metadata `aggregation == "mean_by_x"` and transformation `aggregation:mean`.

Change `test_line_chart_aggregates_duplicate_dates_to_daily_sum` to pass `aggregation="sum"` and assert transformation `aggregation:sum`.

Rename the existing test to `test_multi_metric_bar_normalizes_when_explicitly_requested` and change its chart call to:

```python
result = create_chart(
    "bar",
    data="metrics",
    x_col="company",
    y_col="revenue,exposure,clicks",
    scale_mode="normalize",
    title="Metric total comparison",
)
```

Keep its existing normalized-axis assertions and add `assert "scale:normalize" in metadata["transformations"]`. The new `test_divergent_multi_metric_bar_requires_explicit_scale_mode` above covers the rejected default.

- [ ] **Step 5: Run chart tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_chart_semantics.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit explicit aggregation**

```powershell
git add src/data_agent/tools/chart_contract.py src/data_agent/tools/visualization.py tests/test_chart_contract.py tests/test_chart_semantics.py
git commit -m "fix: require explicit chart aggregation"
```

## Task 4: Bar, Stacked Bar, and Line Contracts

**Files:**
- Modify: `src/data_agent/tools/chart_contract.py`
- Modify: `src/data_agent/tools/visualization.py`
- Modify: `tests/test_chart_semantics.py`

- [ ] **Step 1: Write failing family tests**

```python
def test_stacked_bar_converts_numeric_identifier_categories(tmp_path):
    rows = [
        {"account_id": 900000000000000001, "period": "before", "value": 10},
        {"account_id": 900000000000000002, "period": "after", "value": 20},
    ]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "stacked_identifier", chart_type="stacked_bar", data_json=json.dumps(rows),
        x_col="account_id", y_col="value", color_col="period", title="Selected accounts",
    )
    assert "Chart saved:" in result
    html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
    assert "900000000000000001" in html
    assert '"type":"category"' in html


def test_line_rejects_identifier_axis_even_without_trend_words(tmp_path):
    rows = [{"user_id": i, "value": i * 2} for i in range(1, 8)]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "identifier_line", chart_type="line", data_json=json.dumps(rows),
        x_col="user_id", y_col="value", title="User values",
    )
    assert json.loads(result)["error_code"] == "invalid_line_axis"
    assert not chart_dir.exists()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q -k "stacked_bar or line_rejects_identifier"
```

Expected: stacked bars keep numeric axes and line validation depends on title keywords.

- [ ] **Step 3: Implement family rules**

Apply identifier conversion to both bar families, set `xaxis.type="category"` for converted axes, and reject identifier line axes regardless of title. Apply daily time aggregation only when the caller supplied an explicit aggregation and record it in transformations.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_chart_semantics.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit family contracts**

```powershell
git add src/data_agent/tools/chart_contract.py src/data_agent/tools/visualization.py tests/test_chart_semantics.py
git commit -m "fix: enforce categorical and line chart contracts"
```

## Task 5: Scatter, Histogram, and Box Contracts

**Files:**
- Modify: `src/data_agent/tools/chart_contract.py`
- Modify: `src/data_agent/tools/visualization.py`
- Modify: `tests/test_chart_semantics.py`

- [ ] **Step 1: Write failing measure-role and box grouping tests**

```python
def test_scatter_rejects_numeric_identifier_measure(tmp_path):
    rows = [{"user_id": 1001, "revenue": 10}, {"user_id": 1002, "revenue": 20}]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "identifier_scatter", chart_type="scatter", data_json=json.dumps(rows),
        x_col="user_id", y_col="revenue", title="User revenue relationship",
    )
    assert json.loads(result)["error_code"] == "invalid_scatter_measure"
    assert not chart_dir.exists()


def test_histogram_rejects_numeric_identifier(tmp_path):
    rows = [{"order_id": 10001}, {"order_id": 10002}]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "identifier_histogram", chart_type="histogram", data_json=json.dumps(rows),
        x_col="order_id", title="Order distribution",
    )
    assert json.loads(result)["error_code"] == "invalid_histogram_measure"
    assert not chart_dir.exists()


def test_box_uses_x_as_category_and_y_as_measure(tmp_path):
    rows = [
        {"period": "before", "value": 10}, {"period": "before", "value": 20},
        {"period": "after", "value": 12}, {"period": "after", "value": 18},
    ]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "grouped_box", chart_type="box", data_json=json.dumps(rows),
        x_col="period", y_col="value", title="Value distribution",
    )
    assert "Chart saved:" in result
    html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
    assert '"x":["before","before","after","after"]' in html
    assert '"y":[10,20,12,18]' in html
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q -k "identifier_scatter or identifier_histogram or box_uses"
```

Expected: identifier measures are accepted and box creates separate `period` and `value` series.

- [ ] **Step 3: Implement the three contracts**

Require scatter and histogram axes to have semantic role `measure`. For box charts with both columns, require `x_col` to be category/identifier and `y_col` to be measure, then build exactly one trace:

```python
fig.add_trace(go.Box(
    x=_plotly_axis_values(df[x_col]),
    y=pd.to_numeric(df[y_col], errors="coerce"),
    name=y_col,
))
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_chart_semantics.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit measure-family contracts**

```powershell
git add src/data_agent/tools/chart_contract.py src/data_agent/tools/visualization.py tests/test_chart_semantics.py
git commit -m "fix: validate distribution and scatter chart measures"
```

## Task 6: Pie and Heatmap Contracts

**Files:**
- Modify: `src/data_agent/tools/chart_contract.py`
- Modify: `src/data_agent/tools/visualization.py`
- Modify: `tests/test_chart_semantics.py`

- [ ] **Step 1: Write failing pie and heatmap tests**

```python
def test_pie_uses_category_labels_and_supplied_measure(tmp_path):
    rows = [{"segment": "A", "revenue": 100}, {"segment": "B", "revenue": 20}]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "measure_pie", chart_type="pie", data_json=json.dumps(rows),
        x_col="segment", y_col="revenue", title="Revenue share",
    )
    assert "Chart saved:" in result
    html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
    assert '"labels":["A","B"]' in html
    assert '"values":[100,20]' in html


def test_pie_rejects_negative_measure(tmp_path):
    rows = [{"segment": "A", "profit": 10}, {"segment": "B", "profit": -5}]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "negative_pie", chart_type="pie", data_json=json.dumps(rows),
        x_col="segment", y_col="profit", title="Profit share",
    )
    assert json.loads(result)["error_code"] == "invalid_pie_measure"
    assert not chart_dir.exists()


def test_pie_rejects_high_cardinality_instead_of_silent_top_ten(tmp_path):
    rows = [{"segment": f"S{i}"} for i in range(12)]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "wide_pie", chart_type="pie", data_json=json.dumps(rows),
        x_col="segment", title="Segment share",
    )
    assert json.loads(result)["error_code"] == "unreadable_pie_cardinality"
    assert not chart_dir.exists()


def test_heatmap_uses_only_explicit_numeric_columns(tmp_path):
    rows = [{"a": 1, "b": 2, "unrelated": 99}, {"a": 2, "b": 4, "unrelated": 98}]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "selected_heatmap", chart_type="heatmap", data_json=json.dumps(rows),
        x_col="a", y_col="b", title="A and B correlation",
    )
    assert "Chart saved:" in result
    html = next(chart_dir.glob("*.html")).read_text(encoding="utf-8")
    assert "unrelated" not in html
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q -k "pie_uses or negative_measure or heatmap_uses"
```

Expected: pie counts revenue values instead of using them as measures, negative values are accepted, high cardinality is silently truncated, and heatmap includes `unrelated`.

- [ ] **Step 3: Implement explicit semantics**

For pie, require category `x_col`, optional measure `y_col`, non-negative finite measures, aggregate duplicate labels only with explicit aggregation, retain count mode when only one category column is supplied, and reject category counts above 10 instead of silently truncating. For heatmap, require at least two explicit comma-separated numeric measure columns through `y_col`, or treat `x_col` plus one `y_col` as the selected pair; reject identifier columns and fewer than two valid measures.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_chart_semantics.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit pie and heatmap fixes**

```powershell
git add src/data_agent/tools/chart_contract.py src/data_agent/tools/visualization.py tests/test_chart_semantics.py
git commit -m "fix: honor pie and heatmap chart fields"
```

## Task 7: Figure Renderability and Artifact Boundary

**Files:**
- Modify: `src/data_agent/tools/chart_contract.py`
- Modify: `src/data_agent/tools/visualization.py`
- Modify: `tests/test_chart_semantics.py`
- Test: `tests/test_chart_contract.py`

- [ ] **Step 1: Write failing no-trace and non-finite tests**

```python
def test_empty_chart_spec_is_rejected_before_save(tmp_path):
    result, chart_dir = _create_chart_in_session(
        tmp_path, "empty_bar", chart_type="bar", data_json='[{"label":"A"}]', title="Empty bar",
    )
    payload = json.loads(result)
    assert payload["error_code"] == "non_renderable_figure"
    assert not chart_dir.exists()


def test_all_infinite_measure_is_rejected_before_save(tmp_path):
    rows = [{"label": "A", "value": float("inf")}, {"label": "B", "value": float("-inf")}]
    result, chart_dir = _create_chart_in_session(
        tmp_path, "infinite_bar", chart_type="bar", data_json=json.dumps(rows),
        x_col="label", y_col="value", title="Infinite bar",
    )
    assert json.loads(result)["error_code"] in {"invalid_measure", "non_renderable_figure"}
    assert not chart_dir.exists()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_semantics.py -q -k "empty_chart or all_infinite"
```

Expected: an empty figure can be saved and infinite values are not rejected consistently.

- [ ] **Step 3: Implement pre-save figure validation**

```python
import math


def _contains_finite_numeric(value) -> bool:
    if value is None:
        return False
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        value = [value]
    for item in value:
        if isinstance(item, (list, tuple)):
            if _contains_finite_numeric(item):
                return True
            continue
        try:
            if math.isfinite(float(item)):
                return True
        except (TypeError, ValueError):
            continue
    return False


def validate_figure_renderability(fig) -> str:
    if not fig.data:
        return "Figure contains no traces."
    for trace in fig.data:
        trace_type = str(getattr(trace, "type", ""))
        measure_fields = {
            "bar": ("y",),
            "box": ("y",),
            "funnel": ("x",),
            "heatmap": ("z",),
            "histogram": ("x",),
            "pie": ("values",),
            "scatter": ("y",),
        }.get(trace_type, ("y", "values", "z"))
        if any(_contains_finite_numeric(getattr(trace, field, None)) for field in measure_fields):
            return ""
    return "Figure contains no finite plottable values."
```

Call this after trace construction and before `fig.update_layout` and `_save_chart`. Return structured `non_renderable_figure` errors with no file writes.

- [ ] **Step 4: Run chart tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_chart_semantics.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the artifact boundary**

```powershell
git add src/data_agent/tools/chart_contract.py src/data_agent/tools/visualization.py tests/test_chart_semantics.py
git commit -m "fix: block non-renderable chart artifacts"
```

## Task 8: Stage 1 Regression Verification

**Files:**
- Verify only; no production changes unless a failing regression is reproduced with a new failing test first.

- [ ] **Step 1: Run the complete chart and registry slice**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_chart_semantics.py tests/test_tool_registry.py tests/test_tool_result_web.py -q
```

Expected: PASS.

- [ ] **Step 2: Run report and artifact consumers**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_strategy.py tests/test_report_chart_matching.py tests/test_web_gui.py -q
```

Expected: PASS.

- [ ] **Step 3: Run unaffected neighboring workflow tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_execution_control.py tests/test_data_bundle.py tests/test_multi_file_scope.py tests/test_trust_view.py -q
```

Expected: PASS with no behavior changes outside visualization.

- [ ] **Step 4: Reproduce the reported session shapes without mutating the session**

Run the two 62-row regression fixtures from `tests/test_chart_semantics.py` with `-vv` and confirm both return structured validation errors with recovery options and zero registered artifacts.

- [ ] **Step 5: Inspect the diff boundary**

```powershell
git diff --check
git status --short
git diff --stat HEAD~7..HEAD
```

Expected: only `chart_contract.py`, `visualization.py`, chart tests, and this plan/spec documentation changed during Stage 1.

- [ ] **Step 6: Record Stage 1 completion**

Update the design document Stage 1 status with exact test counts and any residual limitations, then commit only that documentation update:

```powershell
git add docs/superpowers/specs/2026-06-19-analysis-interaction-redesign.md
git commit -m "docs: record chart contract verification"
```

Do not begin Stage 2 in the same implementation batch.
