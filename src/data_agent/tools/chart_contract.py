"""Semantic contracts shared by analytical chart builders."""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
import binascii
import math
import re

import numpy as np
import pandas as pd
from data_agent.utils.column_semantics import is_identifier_name, is_measure_name


IDENTIFIER_TOKENS = {
    "id",
    "uid",
    "user",
    "account",
    "member",
    "customer",
}
IDENTIFIER_TEXT_MARKERS = (
    "用户",
    "账号",
    "会员",
)


@dataclass
class ChartContractResult:
    dataframe: pd.DataFrame
    semantic_roles: dict[str, str] = field(default_factory=dict)
    transformations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_row_count: int = 0
    dropped_row_count: int = 0
    dropped_missing_fields: list[str] = field(default_factory=list)
    error: str = ""
    error_code: str = ""
    recovery_options: list[dict[str, str]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.error


def infer_semantic_role(column: str, series: pd.Series) -> str:
    """Infer the analytical role of a column without treating IDs as measures."""

    name = str(column or "").casefold()
    unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
    name_tokens = {token for token in re.split(r"[^a-z0-9]+", name) if token}
    identifier_name = bool(name_tokens & IDENTIFIER_TOKENS) or any(
        marker in name for marker in IDENTIFIER_TEXT_MARKERS
    )
    if is_identifier_name(column) or (identifier_name and not is_measure_name(column) and unique_ratio >= 0.7):
        return "identifier"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "time"
    if not pd.api.types.is_numeric_dtype(series):
        parsed = pd.to_datetime(
            series.dropna().astype(str),
            errors="coerce",
            format="mixed",
        )
        if len(parsed) and parsed.notna().mean() >= 0.8:
            return "time"
    numeric = pd.to_numeric(series, errors="coerce")
    if len(series) and numeric.notna().mean() >= 0.8:
        return "measure"
    if series.nunique(dropna=True) <= max(20, len(series) // 2):
        return "category"
    return "unknown"


MAX_BAR_CATEGORIES = 40
MAX_NUMERIC_CATEGORY_CODES = 12


def is_chart_count_aggregation(df, chart_type, x_col, aggregation):
    """Use the original count-capable plot modes without coercing counted values."""
    return aggregation == "count" and (
        chart_type in {"bar", "stacked_bar", "pie"}
        or chart_type == "line" and x_col in df.columns
    )


def chart_parameter_error(chart_type, x_col, y_cols, color_col="", aggregation=""):
    """Validate explicit mode/selector identity before any dataframe projection."""
    if chart_type in {"box", "histogram", "pie", "funnel"} and color_col:
        return "This chart type does not support color_col; use its original category/overall plot or select a supported chart type.", "unsupported_chart_color"
    if chart_type in {"scatter", "box", "histogram", "funnel"} and aggregation:
        return "This chart type does not support aggregation; transform the data explicitly before using its original plot.", "unsupported_chart_aggregation"
    if chart_type == "scatter" and bool(x_col) != bool(y_cols):
        return "Scatter requires both explicit x_col and y_col, or neither for the original numeric defaults.", "incomplete_scatter_axes"
    if chart_type in {"line", "bar"} and x_col and not y_cols:
        return "Line and bar require y_col when x_col is explicit; use y-only for original row-index plots or omit both for original defaults.", "missing_explicit_chart_measure"
    if chart_type in {"line", "bar"} and not x_col and (aggregation or color_col):
        return "Line and bar require an explicit x_col or label_columns for aggregation or color grouping; omit grouping parameters for the original row-index/default plot.", "missing_chart_group_axis"
    if chart_type == "box" and x_col and not y_cols:
        return "Box requires a single y_col when x_col is explicit; use y-only for an ungrouped box or omit both for original defaults.", "missing_explicit_chart_measure"
    if chart_type == "pie" and aggregation in {"sum", "mean", "median"} and not y_cols:
        return "Pie sum/mean/median requires one explicit y_col measure; omit aggregation or use count for the original category frequency plot.", "missing_explicit_chart_measure"
    if chart_type in {"histogram", "box", "pie", "stacked_bar", "funnel"} and len(y_cols) > 1:
        return "This chart type supports one explicit y measure; select one column.", "single_chart_measure_required"
    if chart_type == "histogram" and x_col and y_cols and x_col != y_cols[0]:
        return "Histogram is single-variable; explicit x_col and y_col must select the same column, or provide only one selector.", "conflicting_histogram_selectors"
    if chart_type == "heatmap":
        selected = [name for name in [x_col, *y_cols] if name]
        if len(selected) < 2 or len(set(selected)) != len(selected):
            return "Heatmaps require at least two distinct explicit numeric measures, without duplicates.", "invalid_heatmap_measures"
        if color_col or aggregation:
            return "Heatmap supports an overall Pearson matrix; color grouping and aggregation are not supported.", "unsupported_heatmap_parameters"
    return None


def validate_chart_request(
    df: pd.DataFrame,
    chart_type: str,
    x_col: str,
    y_cols: list[str],
    color_col: str = "",
    aggregation: str = "",
    scale_mode: str = "",
) -> ChartContractResult:
    """Validate semantic chart inputs and apply safe, recorded transforms."""

    result = ChartContractResult(
        dataframe=df.copy(),
        source_row_count=int(len(df)),
    )
    if scale_mode not in {"", "raw", "normalize", "index100"} or (
        scale_mode == "index100" and chart_type != "line"
    ) or (scale_mode == "normalize" and chart_type not in {"line", "bar"}):
        result.error = "Unsupported chart/scale combination; normalize=max(abs)=100, index100=first observation=100 (line only)."
        result.error_code = "unsupported_scale_mode"
        return result
    parameter_error = chart_parameter_error(chart_type, x_col, y_cols, color_col, aggregation)
    if parameter_error:
        result.error, result.error_code = parameter_error
        return result
    if chart_type == "line" and x_col in result.dataframe.columns and pd.api.types.is_numeric_dtype(result.dataframe[x_col]):
        axis = result.dataframe[x_col]
        if (axis.notna() & ~np.isfinite(axis)).any():
            result.error = f"Numeric line x_col '{x_col}' contains nonfinite coordinates; provide finite coordinates or explicitly transform the data."
            result.error_code = "invalid_numeric_line_axis"
            return result
    referenced = [name for name in [x_col, *y_cols, color_col] if name]
    result.semantic_roles = {
        name: infer_semantic_role(name, result.dataframe[name])
        for name in referenced
        if name in result.dataframe.columns
    }

    for column in y_cols:
        count_supported = is_chart_count_aggregation(df, chart_type, x_col, aggregation)
        if chart_type in {"bar", "stacked_bar", "line", "box", "pie"} and result.semantic_roles.get(column) == "identifier" and not count_supported:
            result.error = f"Identifier '{column}' is not a numeric measure; select a measure or explicitly count identifiers."
            result.error_code = "invalid_identifier_measure"
            return result
        if count_supported:
            continue
        numeric = pd.to_numeric(result.dataframe[column], errors="coerce")
        finite = numeric.notna() & np.isfinite(numeric)
        if not len(numeric) or float(finite.mean()) < 0.5:
            result.error = f"Measure column '{column}' is not sufficiently numeric."
            result.error_code = "invalid_measure"
            return result
        result.dataframe[column] = numeric.where(finite)

    if (
        chart_type == "line"
        and x_col
        and (
            result.semantic_roles.get(x_col) == "identifier"
            or (
                result.semantic_roles.get(x_col) not in {"time", "measure"}
                and result.dataframe[x_col].nunique(dropna=True) > MAX_BAR_CATEGORIES
            )
        )
    ):
        result.error = "Line charts require an ordered dimension, not an identifier axis."
        result.error_code = "invalid_line_axis"
        result.recovery_options = [
            {
                "chart_type": "scatter",
                "description": "Compare numeric measures without ordering identifiers.",
            },
            {
                "chart_type": "bar",
                "description": "Use a documented small selection or aggregate first.",
            },
        ]
        return result

    if chart_type == "scatter" and any(
        result.semantic_roles.get(column) != "measure"
        for column in [x_col, *y_cols]
        if column
    ):
        result.error = "Scatter axes must be numeric measures."
        result.error_code = "invalid_scatter_measure"
        return result

    if chart_type == "scatter" and x_col:
        numeric_x = pd.to_numeric(result.dataframe[x_col], errors="coerce")
        finite_x = numeric_x.notna() & np.isfinite(numeric_x)
        if not len(numeric_x) or float(finite_x.mean()) < 0.5:
            result.error = "Scatter x axis must contain sufficiently finite numeric values."
            result.error_code = "invalid_scatter_measure"
            return result
        result.dataframe[x_col] = numeric_x.where(finite_x)
        _drop_missing_required_fields(result, [x_col, *y_cols])
        if result.dataframe.empty:
            result.error = "Scatter chart has no complete x/y pairs."
            result.error_code = "no_complete_scatter_pairs"
            return result

    if (
        chart_type in {"bar", "stacked_bar"}
        and x_col
        and result.semantic_roles.get(x_col) == "measure"
    ):
        category_count = int(result.dataframe[x_col].nunique(dropna=True))
        # Encoded experiment arms and before/after windows are commonly
        # stored as integers (for example 1 / 2).  When the caller explicitly
        # selects a small-cardinality x axis, preserving those labels as
        # categories is safe; it does not invent their business meaning.
        if category_count <= MAX_NUMERIC_CATEGORY_CODES:
            result.dataframe[x_col] = result.dataframe[x_col].map(
                lambda value: "" if pd.isna(value) else str(value)
            )
            result.semantic_roles[x_col] = "category"
            result.transformations.append("low_cardinality_numeric_to_category")
        else:
            result.error = (
                "Bar charts require a categorical or time-bucket x axis; "
                f"'{x_col}' is a continuous numeric measure."
            )
            result.error_code = "invalid_bar_axis"
            result.recovery_options = [
                {
                    "chart_type": "scatter",
                    "description": "Use a scatter chart to show the relationship between two numeric measures.",
                },
                {
                    "chart_type": "histogram",
                    "description": "Use a histogram to show the distribution of one numeric measure.",
                },
                {
                    "chart_type": "bar",
                    "description": "Aggregate or transform the x measure into documented categories before using bars.",
                },
            ]
            return result

    histogram_col = y_cols[0] if y_cols else x_col
    if (
        chart_type == "histogram"
        and histogram_col
        and result.semantic_roles.get(histogram_col) != "measure"
    ):
        result.error = "Histogram values must be a numeric measure."
        result.error_code = "invalid_histogram_measure"
        return result

    if chart_type in {"bar", "stacked_bar"} and x_col:
        category_count = int(result.dataframe[x_col].nunique(dropna=True))
        if category_count > MAX_BAR_CATEGORIES:
            is_identifier = result.semantic_roles.get(x_col) == "identifier"
            result.error = "Category axis has too many values for a readable bar chart."
            result.error_code = (
                "unreadable_identifier_axis"
                if is_identifier
                else "unreadable_category_axis"
            )
            result.recovery_options = [
                {
                    "chart_type": "scatter",
                    "description": "Compare numeric measures without one bar per category.",
                },
                {
                    "chart_type": "box",
                    "description": "Compare distributions across meaningful groups.",
                },
                {
                    "chart_type": "bar",
                    "description": "Aggregate or select a documented Top N first.",
                },
            ]
            return result

    if chart_type == "pie" and x_col:
        category_count = int(result.dataframe[x_col].nunique(dropna=True))
        if category_count > 10:
            result.error = "Pie charts support at most 10 readable categories."
            result.error_code = "unreadable_pie_cardinality"
            result.recovery_options = [
                {
                    "chart_type": "bar",
                    "description": "Use a sorted bar chart or an explicit Top N.",
                }
            ]
            return result
        if y_cols:
            values = pd.to_numeric(result.dataframe[y_cols[0]], errors="coerce")
            if aggregation != "count" and (values < 0).any():
                result.error = "Pie chart measures must be non-negative."
                result.error_code = "invalid_pie_measure"
                return result
            if result.dataframe.duplicated(subset=[x_col]).any() and not aggregation:
                _set_aggregation_required(result)
                return result

    if chart_type == "heatmap":
        selected = [name for name in [x_col, *y_cols] if name]
        if len(selected) < 2 or any(
            result.semantic_roles.get(name) != "measure" for name in selected
        ):
            result.error = "Heatmaps require at least two explicit numeric measure columns."
            result.error_code = "invalid_heatmap_measures"
            return result

    if chart_type == "line" and x_col and infer_semantic_role(
        x_col, result.dataframe[x_col]
    ) == "time":
        parsed = pd.to_datetime(result.dataframe[x_col], errors="coerce")
        groups = pd.DataFrame({x_col: parsed})
        if color_col:
            groups[color_col] = result.dataframe[color_col]
        if groups.duplicated().any() and not aggregation:
            _set_aggregation_required(result)
            return result

    if chart_type in {"bar", "stacked_bar"} and x_col:
        group_cols = [x_col] + ([color_col] if color_col else [])
        if result.dataframe.duplicated(subset=group_cols).any() and not aggregation:
            _set_aggregation_required(result)
            return result
        if chart_type == "bar" and len(y_cols) > 1 and _has_divergent_scales(result.dataframe, y_cols):
            if not scale_mode:
                result.error = "Metrics use divergent scales; choose raw values or explicit normalization."
                result.error_code = "scale_mode_required"
                result.recovery_options = [
                    {
                        "scale_mode": "raw",
                        "description": "Keep original values on one shared axis.",
                    },
                    {
                        "scale_mode": "normalize",
                        "description": "Normalize each metric to its own maximum of 100.",
                    },
                ]
                return result
            if scale_mode == "normalize":
                result.transformations.append("scale:normalize")

    if chart_type not in {"bar", "stacked_bar"} or not x_col:
        return result

    if result.semantic_roles.get(x_col) == "identifier":
        result.dataframe[x_col] = result.dataframe[x_col].map(
            lambda value: "" if pd.isna(value) else str(value)
        )
        result.transformations.append("identifier_to_category")
    return result


def _set_aggregation_required(result: ChartContractResult) -> None:
    result.error = "Duplicate chart groups require an explicit aggregation."
    result.error_code = "aggregation_required"
    result.recovery_options = [
        {
            "aggregation": aggregation,
            "description": f"Aggregate duplicate groups using {aggregation}.",
        }
        for aggregation in ("sum", "mean", "median", "count")
    ]


def _drop_missing_required_fields(
    result: ChartContractResult,
    required_fields: list[str],
) -> None:
    fields = list(dict.fromkeys(
        field for field in required_fields if field in result.dataframe.columns
    ))
    if not fields:
        return

    missing_fields = [
        field for field in fields if result.dataframe[field].isna().any()
    ]
    if not missing_fields:
        return

    before = len(result.dataframe)
    result.dataframe = result.dataframe.dropna(subset=fields).copy()
    result.dropped_row_count = before - len(result.dataframe)
    result.dropped_missing_fields = missing_fields
    if result.dropped_row_count:
        result.transformations.append("drop_missing_required_fields")


def _has_divergent_scales(df: pd.DataFrame, y_cols: list[str]) -> bool:
    maxima = []
    for column in y_cols:
        values = pd.to_numeric(df[column], errors="coerce").abs().dropna()
        maximum = float(values.max()) if len(values) else 0.0
        if maximum > 0:
            maxima.append(maximum)
    return bool(maxima) and max(maxima) / min(maxima) >= 50


def _contains_finite_numeric(value) -> bool:
    if value is None:
        return False
    # Plotly serializes numpy arrays as typed binary payloads. Inspect the
    # original values after reload, rather than treating that payload as a
    # nonnumeric dict and dropping a previously valid chart from exports.
    if isinstance(value, dict) and "bdata" in value:
        try:
            dtype = str(value.get("dtype", ""))
            if dtype not in {"i1", "u1", "i2", "u2", "i4", "u4", "f4", "f8"}:
                return False
            array = np.frombuffer(base64.b64decode(value["bdata"], validate=True), dtype=dtype)
            shape = value.get("shape")
            if shape is not None:
                dimensions = tuple(int(part.strip()) for part in str(shape).split(","))
                if not dimensions or any(part < 0 for part in dimensions) or math.prod(dimensions) != array.size:
                    return False
            return bool(np.isfinite(array).any())
        except (ValueError, TypeError, binascii.Error):
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
    """Return an error when a Plotly figure has no finite measure values."""

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
        if any(
            _contains_finite_numeric(getattr(trace, field, None))
            for field in measure_fields
        ):
            return ""
    return "Figure contains no finite plottable values."


__all__ = [
    "ChartContractResult",
    "infer_semantic_role",
    "validate_chart_request",
    "validate_figure_renderability",
]
