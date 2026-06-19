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


__all__ = ["ChartContractResult", "infer_semantic_role"]
