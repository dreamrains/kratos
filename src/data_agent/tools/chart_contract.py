"""Semantic contracts shared by analytical chart builders."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

import numpy as np
import pandas as pd


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
    if identifier_name and unique_ratio >= 0.7:
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

    result = ChartContractResult(dataframe=df.copy())
    referenced = [name for name in [x_col, *y_cols, color_col] if name]
    result.semantic_roles = {
        name: infer_semantic_role(name, result.dataframe[name])
        for name in referenced
        if name in result.dataframe.columns
    }

    for column in y_cols:
        numeric = pd.to_numeric(result.dataframe[column], errors="coerce")
        finite = numeric.notna() & np.isfinite(numeric)
        if not len(numeric) or float(finite.mean()) < 0.5:
            result.error = f"Measure column '{column}' is not sufficiently numeric."
            result.error_code = "invalid_measure"
            return result
        result.dataframe[column] = numeric.where(finite)

    if chart_type == "line" and x_col and result.semantic_roles.get(x_col) == "identifier":
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

    if chart_type == "scatter" and (
        result.semantic_roles.get(x_col) == "identifier"
        or any(result.semantic_roles.get(column) == "identifier" for column in y_cols)
    ):
        result.error = "Scatter axes must be numeric measures, not identifiers."
        result.error_code = "invalid_scatter_measure"
        return result

    histogram_col = y_cols[0] if y_cols else x_col
    if (
        chart_type == "histogram"
        and histogram_col
        and result.semantic_roles.get(histogram_col) == "identifier"
    ):
        result.error = "Histogram values must be a measure, not an identifier."
        result.error_code = "invalid_histogram_measure"
        return result

    if chart_type == "line" and x_col and infer_semantic_role(
        x_col, result.dataframe[x_col]
    ) == "time":
        parsed = pd.to_datetime(result.dataframe[x_col], errors="coerce")
        days = parsed.dt.normalize()
        group_cols = [days] + (
            [result.dataframe[color_col]] if color_col else []
        )
        duplicated_days = pd.DataFrame(group_cols).T.duplicated().any()
        if duplicated_days and not aggregation:
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

    category_count = int(result.dataframe[x_col].nunique(dropna=True))
    if (
        result.semantic_roles.get(x_col) == "identifier"
        and category_count > MAX_BAR_CATEGORIES
    ):
        result.error = "Identifier axis has too many categories for a readable bar chart."
        result.error_code = "unreadable_identifier_axis"
        result.recovery_options = [
            {
                "chart_type": "scatter",
                "description": "Compare before and after measures directly.",
            },
            {
                "chart_type": "box",
                "description": "Compare distributions without one bar per identifier.",
            },
            {
                "chart_type": "bar",
                "description": "Aggregate or select a documented Top N first.",
            },
        ]
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


def _has_divergent_scales(df: pd.DataFrame, y_cols: list[str]) -> bool:
    maxima = []
    for column in y_cols:
        values = pd.to_numeric(df[column], errors="coerce").abs().dropna()
        maximum = float(values.max()) if len(values) else 0.0
        if maximum > 0:
            maxima.append(maximum)
    return bool(maxima) and max(maxima) / min(maxima) >= 50


__all__ = [
    "ChartContractResult",
    "infer_semantic_role",
    "validate_chart_request",
]
