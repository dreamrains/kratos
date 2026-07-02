"""Deterministic validation for explicitly proposed tabular relationships.

Coverage denominators are intentionally visible: row coverage uses every input
row (including rows with null key components), while distinct-key coverage uses
the non-null distinct keys on that side.  The join multiplier baseline is the
larger input row count.  Expected inner-join rows are derived from key
multiplicities and never require materializing a merge.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
from pandas.api import types as pd_types


RELATIONSHIP_VALIDATION_VERSION = "relationship_validation.v1"
DEFAULT_MIN_ROW_COVERAGE = 0.5
DEFAULT_MAX_NULL_RATE = 0.2
DEFAULT_MAX_JOIN_MULTIPLIER = 1.0


@dataclass(frozen=True)
class RelationshipValidation:
    """Immutable relationship-validation outcome with a stable record form."""

    relationship_id: str
    status: str
    cardinality: str | None = None
    normalized_left_key: tuple[str, ...] = field(default_factory=tuple)
    normalized_right_key: tuple[str, ...] = field(default_factory=tuple)
    left_row_count: int | None = None
    right_row_count: int | None = None
    left_non_null_key_rows: int | None = None
    right_non_null_key_rows: int | None = None
    left_distinct_keys: int | None = None
    right_distinct_keys: int | None = None
    left_row_coverage: float | None = None
    right_row_coverage: float | None = None
    left_distinct_key_coverage: float | None = None
    right_distinct_key_coverage: float | None = None
    left_null_rate: float | None = None
    right_null_rate: float | None = None
    left_key_unique: bool | None = None
    right_key_unique: bool | None = None
    expected_inner_join_rows: int | None = None
    join_row_baseline: int | None = None
    row_multiplier: float | None = None
    risks: tuple[str, ...] = field(default_factory=tuple)
    contract_version: str = RELATIONSHIP_VALIDATION_VERSION

    def to_record(self) -> dict[str, Any]:
        """Return a fresh JSON-serializable canonical relationship record."""
        record = asdict(self)
        record["id"] = self.relationship_id
        record["left_key"] = list(self.normalized_left_key)
        record["right_key"] = list(self.normalized_right_key)
        record["normalized_left_key"] = list(self.normalized_left_key)
        record["normalized_right_key"] = list(self.normalized_right_key)
        record["risks"] = list(self.risks)
        return record


def _normalize_key(value: Any) -> tuple[tuple[str, ...], str | None]:
    if isinstance(value, str):
        items = (value,)
    elif isinstance(value, (list, tuple)):
        items = tuple(value)
    else:
        return (), "invalid_key_type"
    if not items:
        return (), "empty_key"
    if not all(isinstance(item, str) for item in items):
        return (), "invalid_key_type"
    normalized = tuple(item.strip() for item in items)
    if any(not item for item in normalized):
        return (), "empty_key"
    return normalized, None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _with_identity(values: dict[str, Any]) -> RelationshipValidation:
    identity_values = {
        "contract_version": RELATIONSHIP_VALIDATION_VERSION,
        **values,
    }
    serializable = {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in identity_values.items()
    }
    digest = hashlib.sha256(_canonical_json(serializable).encode("utf-8")).hexdigest()
    return RelationshipValidation(relationship_id=f"rel_{digest[:20]}", **values)


def _rejected(
    risk: str,
    *,
    left_key: tuple[str, ...] = (),
    right_key: tuple[str, ...] = (),
    left_rows: int | None = None,
    right_rows: int | None = None,
) -> RelationshipValidation:
    return _with_identity(
        {
            "status": "rejected",
            "normalized_left_key": left_key,
            "normalized_right_key": right_key,
            "left_row_count": left_rows,
            "right_row_count": right_rows,
            "risks": (risk,),
        }
    )


def _is_null(value: Any) -> bool:
    null = pd.isna(value)
    return bool(null) if isinstance(null, (bool, type(pd.NA))) else False


def _key_counts(frame: pd.DataFrame, key: tuple[str, ...]) -> tuple[Counter[tuple[Any, ...]], int]:
    counts: Counter[tuple[Any, ...]] = Counter()
    null_rows = 0
    for values in frame.loc[:, list(key)].itertuples(index=False, name=None):
        if any(_is_null(value) for value in values):
            null_rows += 1
            continue
        try:
            counts[tuple(values)] += 1
        except TypeError as exc:
            raise ValueError("unhashable_key_value") from exc
    return counts, null_rows


def _series_family(series: pd.Series) -> str:
    dtype = series.dtype
    if pd_types.is_bool_dtype(dtype):
        return "boolean"
    if pd_types.is_numeric_dtype(dtype):
        return "numeric"
    if pd_types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pd_types.is_timedelta64_dtype(dtype):
        return "timedelta"
    if pd_types.is_string_dtype(dtype) and not pd_types.is_object_dtype(dtype):
        return "string"

    families: set[str] = set()
    for value in series.dropna():
        if isinstance(value, bool):
            families.add("boolean")
        elif isinstance(value, (int, float, complex)) and not isinstance(value, bool):
            families.add("numeric")
        elif isinstance(value, (pd.Timestamp,)):
            families.add("datetime")
        elif isinstance(value, str):
            families.add("string")
        else:
            families.add(type(value).__name__)
    if not families:
        return "unknown"
    return next(iter(families)) if len(families) == 1 else "mixed"


def _valid_thresholds(min_row_coverage: Any, max_null_rate: Any, max_join_multiplier: Any) -> bool:
    values = (min_row_coverage, max_null_rate, max_join_multiplier)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        return False
    if not all(math.isfinite(float(value)) for value in values):
        return False
    return 0 <= min_row_coverage <= 1 and 0 <= max_null_rate <= 1 and max_join_multiplier >= 0


def validate_relationship(
    left: Any,
    right: Any,
    *,
    left_key: str | list[str] | tuple[str, ...],
    right_key: str | list[str] | tuple[str, ...],
    min_row_coverage: float = DEFAULT_MIN_ROW_COVERAGE,
    max_null_rate: float = DEFAULT_MAX_NULL_RATE,
    max_join_multiplier: float = DEFAULT_MAX_JOIN_MULTIPLIER,
) -> RelationshipValidation:
    """Validate only the exact supplied key mapping; no key inference is used."""
    if not isinstance(left, pd.DataFrame):
        return _rejected("invalid_left_type")
    if not isinstance(right, pd.DataFrame):
        return _rejected("invalid_right_type", left_rows=len(left))

    normalized_left, left_key_error = _normalize_key(left_key)
    normalized_right, right_key_error = _normalize_key(right_key)
    key_error = left_key_error or right_key_error
    if key_error:
        return _rejected(
            key_error,
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=len(right),
        )
    if len(normalized_left) != len(normalized_right):
        return _rejected(
            "key_arity_mismatch",
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=len(right),
        )
    if not _valid_thresholds(min_row_coverage, max_null_rate, max_join_multiplier):
        return _rejected(
            "invalid_thresholds",
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=len(right),
        )
    missing_left = [key for key in normalized_left if key not in left.columns]
    if missing_left:
        return _rejected(
            "missing_left_key",
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=len(right),
        )
    missing_right = [key for key in normalized_right if key not in right.columns]
    if missing_right:
        return _rejected(
            "missing_right_key",
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=len(right),
        )
    if left.empty:
        return _rejected(
            "empty_left_data",
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=0,
            right_rows=len(right),
        )
    if right.empty:
        return _rejected(
            "empty_right_data",
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=0,
        )

    try:
        left_counts, left_null_rows = _key_counts(left, normalized_left)
        right_counts, right_null_rows = _key_counts(right, normalized_right)
    except ValueError as exc:
        return _rejected(
            str(exc),
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=len(right),
        )
    if not left_counts:
        return _rejected(
            "all_null_left_key",
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=len(right),
        )
    if not right_counts:
        return _rejected(
            "all_null_right_key",
            left_key=normalized_left,
            right_key=normalized_right,
            left_rows=len(left),
            right_rows=len(right),
        )

    left_unique = max(left_counts.values()) == 1
    right_unique = max(right_counts.values()) == 1
    if left_unique and right_unique:
        cardinality = "one_to_one"
    elif left_unique:
        cardinality = "one_to_many"
    elif right_unique:
        cardinality = "many_to_one"
    else:
        cardinality = "many_to_many"

    matching_keys = left_counts.keys() & right_counts.keys()
    matching_left_rows = sum(left_counts[key] for key in matching_keys)
    matching_right_rows = sum(right_counts[key] for key in matching_keys)
    expected_rows = sum(left_counts[key] * right_counts[key] for key in matching_keys)
    baseline = max(len(left), len(right))
    left_row_coverage = matching_left_rows / len(left)
    right_row_coverage = matching_right_rows / len(right)
    left_distinct_coverage = len(matching_keys) / len(left_counts)
    right_distinct_coverage = len(matching_keys) / len(right_counts)
    left_null_rate = left_null_rows / len(left)
    right_null_rate = right_null_rows / len(right)
    multiplier = expected_rows / baseline

    risks: list[str] = []
    if cardinality == "many_to_many":
        risks.append("many_to_many_join_explosion")
    if left_row_coverage < min_row_coverage:
        risks.append("low_left_row_coverage")
    if right_row_coverage < min_row_coverage:
        risks.append("low_right_row_coverage")
    if left_null_rate > max_null_rate:
        risks.append("high_left_null_rate")
    if right_null_rate > max_null_rate:
        risks.append("high_right_null_rate")
    if multiplier > max_join_multiplier:
        risks.append("excessive_row_multiplier")
    if any(
        _series_family(left[left_name]) != _series_family(right[right_name])
        for left_name, right_name in zip(normalized_left, normalized_right)
    ):
        risks.append("key_type_family_mismatch")

    status = "rejected" if cardinality == "many_to_many" else (
        "needs_confirmation" if risks else "validated"
    )
    return _with_identity(
        {
            "status": status,
            "cardinality": cardinality,
            "normalized_left_key": normalized_left,
            "normalized_right_key": normalized_right,
            "left_row_count": len(left),
            "right_row_count": len(right),
            "left_non_null_key_rows": len(left) - left_null_rows,
            "right_non_null_key_rows": len(right) - right_null_rows,
            "left_distinct_keys": len(left_counts),
            "right_distinct_keys": len(right_counts),
            "left_row_coverage": left_row_coverage,
            "right_row_coverage": right_row_coverage,
            "left_distinct_key_coverage": left_distinct_coverage,
            "right_distinct_key_coverage": right_distinct_coverage,
            "left_null_rate": left_null_rate,
            "right_null_rate": right_null_rate,
            "left_key_unique": left_unique,
            "right_key_unique": right_unique,
            "expected_inner_join_rows": expected_rows,
            "join_row_baseline": baseline,
            "row_multiplier": multiplier,
            "risks": tuple(risks),
        }
    )
