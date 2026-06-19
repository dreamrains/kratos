"""Semantic contracts shared by analytical chart builders."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

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
) -> ChartContractResult:
    """Validate semantic chart inputs and apply safe, recorded transforms."""

    result = ChartContractResult(dataframe=df.copy())
    referenced = [name for name in [x_col, *y_cols, color_col] if name]
    result.semantic_roles = {
        name: infer_semantic_role(name, result.dataframe[name])
        for name in referenced
        if name in result.dataframe.columns
    }

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


__all__ = [
    "ChartContractResult",
    "infer_semantic_role",
    "validate_chart_request",
]
