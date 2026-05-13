"""Automatic data quality scanning and feature extraction for loaded datasets."""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.utils.logging import get_logger

logger = get_logger("data_features")

_METADATA_KEY = "data_features_card"


def scan_data_quality(df: pd.DataFrame) -> dict:
    """Scan a DataFrame and return per-column quality metrics plus summary flags.

    Returns a dict with keys: columns, duplicate_row_ratio, quality_score,
    block_issues, warnings, info.
    """
    if df.empty:
        return {
            "columns": {},
            "duplicate_row_ratio": 0.0,
            "quality_score": 100,
            "block_issues": [],
            "warnings": [],
            "info": ["Empty DataFrame"],
        }

    n_rows = len(df)
    duplicate_row_ratio = df.duplicated().sum() / n_rows if n_rows > 0 else 0.0

    columns_info: dict[str, dict] = {}
    block_issues: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    for col in df.columns:
        series = df[col]
        missing_rate = series.isna().sum() / n_rows

        is_constant = series.nunique(dropna=False) <= 1
        all_same = series.nunique(dropna=True) <= 1 and missing_rate == 0

        col_type = _classify_column_type(series)
        outlier_ratio: float | None = None
        if col_type == "numeric":
            outlier_ratio = _compute_outlier_ratio(series)

        columns_info[col] = {
            "missing_rate": missing_rate,
            "is_constant": is_constant,
            "outlier_ratio": outlier_ratio,
            "type": col_type,
        }

        if missing_rate > 0.5:
            block_issues.append(f"Column '{col}' has {missing_rate:.0%} missing values")
        elif missing_rate >= 0.3:
            warnings.append(f"Column '{col}' has {missing_rate:.0%} missing values")

        if is_constant and not all_same:
            info.append(f"Column '{col}' is constant (single value including NaN)")
        elif all_same:
            info.append(f"Column '{col}' has all identical values")

    if duplicate_row_ratio > 0.1:
        warnings.append(f"Duplicate row ratio is {duplicate_row_ratio:.0%}")

    quality_score = _compute_quality_score(columns_info, duplicate_row_ratio)

    return {
        "columns": columns_info,
        "duplicate_row_ratio": duplicate_row_ratio,
        "quality_score": quality_score,
        "block_issues": block_issues,
        "warnings": warnings,
        "info": info,
    }


def detect_cross_dataset_relationships(
    datasets: dict[str, pd.DataFrame],
) -> list[dict]:
    """Detect potential join keys between pairs of datasets.

    Returns a list of relationship descriptors sorted by overlap percentage
    descending.
    """
    names = list(datasets.keys())
    if len(names) < 2:
        return []

    relationships: list[dict] = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            left_name = names[i]
            right_name = names[j]
            left_df = datasets[left_name]
            right_df = datasets[right_name]

            common_cols = set(left_df.columns) & set(right_df.columns)
            for col in common_cols:
                left_series = left_df[col].dropna()
                right_series = right_df[col].dropna()

                left_cardinality = left_series.nunique()
                right_cardinality = right_series.nunique()

                is_id_like = _is_id_like(left_series) and _is_id_like(right_series)

                if is_id_like or (left_cardinality > 1 and right_cardinality > 1):
                    left_vals = set(left_series.values)
                    right_vals = set(right_series.values)

                    if left_vals and right_vals:
                        overlap = len(left_vals & right_vals)
                        overlap_pct = overlap / min(len(left_vals), len(right_vals))
                    else:
                        overlap_pct = 0.0

                    relationships.append({
                        "left": left_name,
                        "right": right_name,
                        "column": col,
                        "left_cardinality": left_cardinality,
                        "right_cardinality": right_cardinality,
                        "overlap_pct": round(overlap_pct, 4),
                        "is_id_like": is_id_like,
                    })

    relationships.sort(key=lambda r: r["overlap_pct"], reverse=True)
    return relationships


def build_data_characteristics_card(
    name: str,
    df: pd.DataFrame,
    quality: dict | None = None,
) -> str:
    """Build a compact text summary card for a dataset."""
    if quality is None:
        quality = scan_data_quality(df)

    n_rows, n_cols = df.shape
    score = quality.get("quality_score", 0)
    n_warnings = len(quality.get("warnings", []))
    n_blocks = len(quality.get("block_issues", []))

    type_counts = {"numeric": 0, "categorical": 0, "date": 0, "id": 0}
    for col_info in quality.get("columns", {}).values():
        t = col_info.get("type", "categorical")
        if t in type_counts:
            type_counts[t] += 1
        else:
            type_counts["categorical"] += 1

    lines: list[str] = []
    lines.append("[data_features]")
    lines.append(
        f"Dataset: {name} | {n_rows} rows x {n_cols} cols"
    )
    lines.append(
        f"Quality: {score}/100 | {n_warnings} warnings, {n_blocks} blocks"
    )
    lines.append(
        f"Columns: {type_counts['numeric']} numeric, "
        f"{type_counts['categorical']} categorical, "
        f"{type_counts['date']} date, "
        f"{type_counts['id']} ID"
    )

    time_info = _extract_time_info(df, quality)
    if time_info:
        lines.append(f"Time: {time_info}")

    issues = quality.get("block_issues", []) + quality.get("warnings", []) + quality.get("info", [])
    if issues:
        issue_descriptions = "; ".join(issues[:5])
        severity = _severity_marker(n_blocks, n_warnings)
        lines.append(f"Issues: {severity} {issue_descriptions}")

    return "\n".join(lines)


def get_cached_features(name: str) -> str | None:
    """Retrieve cached feature card from workspace metadata."""
    return workspace.get_metadata(name, _METADATA_KEY)


def set_cached_features(name: str, card: str) -> None:
    """Store feature card to workspace metadata."""
    workspace.set_metadata(name, _METADATA_KEY, card)


def _classify_column_type(series: pd.Series) -> str:
    """Classify a column as numeric, date, id, or categorical."""
    dtype = series.dtype

    if pd.api.types.is_numeric_dtype(dtype):
        if _is_id_like(series):
            return "id"
        return "numeric"

    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "date"

    sample = series.dropna().head(100)
    if len(sample) > 0 and _looks_like_dates(sample):
        return "date"

    if _is_id_like(series):
        return "id"

    return "categorical"


def _is_id_like(series: pd.Series) -> bool:
    """Heuristic: high cardinality, mostly unique values."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return False
    n_unique = non_null.nunique()
    n_total = len(non_null)
    uniqueness = n_unique / n_total
    return n_total >= 5 and uniqueness > 0.9 and n_unique >= 5


def _looks_like_dates(sample: pd.Series) -> bool:
    """Check if string values parse as dates with reasonable success."""
    success = 0
    for val in sample:
        try:
            parsed = pd.to_datetime(val, errors="raise")
            if pd.notna(parsed):
                success += 1
        except (ValueError, TypeError):
            pass
    return success / len(sample) > 0.8 if len(sample) > 0 else False


def _compute_outlier_ratio(series: pd.Series) -> float:
    """IQR-based outlier ratio for numeric columns."""
    clean = series.dropna()
    if len(clean) < 4:
        return 0.0
    q1 = clean.quantile(0.25)
    q3 = clean.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return 0.0
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = ((clean < lower) | (clean > upper)).sum()
    return float(outliers / len(clean))


def _compute_quality_score(columns_info: dict, duplicate_row_ratio: float) -> int:
    """Heuristic quality score from 0 to 100."""
    if not columns_info:
        return 100

    penalty = 0.0

    for col_info in columns_info.values():
        missing = col_info.get("missing_rate", 0)
        if missing > 0.5:
            penalty += 25
        elif missing >= 0.3:
            penalty += 10
        elif missing > 0:
            penalty += missing * 5

        if col_info.get("is_constant"):
            penalty += 2

        outlier = col_info.get("outlier_ratio")
        if outlier is not None and outlier > 0.1:
            penalty += 5

    penalty += duplicate_row_ratio * 20

    score = max(0, int(100 - penalty))
    return min(100, score)


def _severity_marker(n_blocks: int, n_warnings: int) -> str:
    """Return a severity indicator string."""
    if n_blocks > 0:
        return "[BLOCK]"
    if n_warnings > 0:
        return "[WARN]"
    return "[INFO]"


def _extract_time_info(df: pd.DataFrame, quality: dict) -> str | None:
    """Extract time grain and range from date columns, if any."""
    date_cols = [
        col for col, info in quality.get("columns", {}).items()
        if info.get("type") == "date"
    ]
    if not date_cols:
        return None

    best_col = date_cols[0]
    date_series = df[best_col].dropna()

    if pd.api.types.is_string_dtype(date_series.dtype):
        try:
            date_series = pd.to_datetime(date_series, errors="coerce").dropna()
        except Exception:
            return None

    if date_series.empty:
        return None

    min_date = date_series.min()
    max_date = date_series.max()

    if hasattr(min_date, "strftime"):
        min_str = min_date.strftime("%Y-%m-%d")
        max_str = max_date.strftime("%Y-%m-%d")
    else:
        min_str = str(min_date)
        max_str = str(max_date)

    try:
        days = (max_date - min_date).days
    except Exception:
        days = 0

    grain = _infer_time_grain(date_series)

    return f"{grain} ({min_str} ~ {max_str}, {days} days)"


def _infer_time_grain(date_series: pd.Series) -> str:
    """Infer the grain of a date series from unique date spacing."""
    try:
        unique_sorted = date_series.sort_values().unique()
        if len(unique_sorted) < 2:
            return "point"
        diffs = np.diff(unique_sorted.astype("int64"))
        median_diff = np.median(diffs.astype(float))
        median_days = median_diff / 86400000000000

        if median_days < 1.5:
            return "daily"
        if median_days < 10:
            return "weekly"
        if median_days < 40:
            return "monthly"
        return "yearly"
    except Exception:
        return "unknown"
