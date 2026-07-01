"""Measurement compatibility checks for Stage 3C0B evidence comparisons."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


COMPATIBILITY_FIELDS = (
    "metric",
    "definition",
    "unit",
    "grain",
    "time_scope",
    "population_scope",
)


@dataclass
class MeasurementCompatibility:
    compatible: bool
    reason_code: str
    user_message: str = ""
    fields: list[str] = field(default_factory=list)


def _normalize_text(value: Any) -> str:
    if value is None or not isinstance(value, (str, int, float, bool)):
        return ""
    return " ".join(str(value).strip().lower().split())


def compare_measurements(left: Any, right: Any) -> MeasurementCompatibility:
    """Compare canonical measurement identity fields without conversion or alignment."""

    if not isinstance(left, dict) or not isinstance(right, dict):
        return MeasurementCompatibility(
            compatible=False,
            reason_code="missing_measurement_field",
            user_message="测量字段缺失，不能直接比较。",
            fields=list(COMPATIBILITY_FIELDS),
        )

    missing_fields = [
        field_name
        for field_name in COMPATIBILITY_FIELDS
        if not _normalize_text(left.get(field_name)) or not _normalize_text(right.get(field_name))
    ]
    if missing_fields:
        return MeasurementCompatibility(
            compatible=False,
            reason_code="missing_measurement_field",
            user_message="测量字段缺失，不能直接比较。",
            fields=missing_fields,
        )

    for field_name in COMPATIBILITY_FIELDS:
        if _normalize_text(left.get(field_name)) != _normalize_text(right.get(field_name)):
            return MeasurementCompatibility(
                compatible=False,
                reason_code=f"{field_name}_mismatch",
                user_message=_mismatch_message(field_name),
                fields=[field_name],
            )

    return MeasurementCompatibility(compatible=True, reason_code="compatible")


def _mismatch_message(field_name: str) -> str:
    messages = {
        "metric": "指标不同，不能直接比较。",
        "definition": "指标定义不同，不能直接比较。",
        "unit": "计量单位不同，不能直接比较。",
        "grain": "统计粒度不同，不能直接比较。",
        "time_scope": "时间范围不同，不能直接比较。",
        "population_scope": "统计对象不同，不能直接比较。",
    }
    return messages.get(field_name, "测量口径不同，不能直接比较。")
