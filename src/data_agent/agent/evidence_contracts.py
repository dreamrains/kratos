from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


CANONICAL_EVIDENCE_FIELDS = (
    "plan_id",
    "step_id",
    "claim_key",
    "claim",
    "dataset",
    "dataset_contract_id",
    "method",
    "tool_calls",
    "result_summary",
    "sample_size",
    "limitations",
    "confidence",
    "evidence_requirement",
    "measurements",
)

MEASUREMENT_FIELDS = (
    "metric",
    "definition",
    "value",
    "unit",
    "grain",
    "population_scope",
    "time_scope",
    "method",
    "denominator",
    "limitations",
)


@dataclass
class EvidenceValidationResult:
    ok: bool
    record: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _slug(value: Any) -> str:
    text = _text(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def evidence_id_for(plan_id: Any, step_id: Any, claim_key: Any) -> str:
    return f"ev_{_slug(plan_id)}_{_slug(step_id)}_{_slug(claim_key)}"


def _error(error_type: str, message: str, **details: Any) -> EvidenceValidationResult:
    return EvidenceValidationResult(False, error_type=error_type, message=message, details=details)


def validate_stage3c0b_evidence(
    record: Any,
    *,
    current_plan_id: str | None = None,
) -> EvidenceValidationResult:
    if not isinstance(record, dict):
        return _error("invalid_evidence", "EvidenceRecord must be a JSON object.")

    plan_id = _text(record.get("plan_id"))
    current_plan = _text(current_plan_id)
    if not current_plan or plan_id != current_plan:
        return _error(
            "evidence_outside_current_plan",
            "EvidenceRecord plan_id does not match the current analysis plan.",
            current_plan_id=current_plan,
            record_plan_id=plan_id,
        )

    if "measurements" not in record or _missing(record.get("measurements")):
        return _error(
            "missing_measurements",
            "Stage 3C0B EvidenceRecord requires non-empty canonical measurements.",
            has_legacy_metrics=bool(record.get("metrics")),
        )

    missing = [
        field_name
        for field_name in CANONICAL_EVIDENCE_FIELDS
        if field_name not in record or _missing(record.get(field_name))
    ]
    if missing:
        return _error(
            "missing_canonical_fields",
            "Stage 3C0B EvidenceRecord is missing canonical fields.",
            missing=missing,
        )

    measurements = record.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return _error(
            "missing_measurements",
            "Stage 3C0B EvidenceRecord requires a non-empty measurements list.",
        )

    for index, measurement in enumerate(measurements):
        if not isinstance(measurement, dict):
            return _error(
                "invalid_measurement",
                "Each Stage 3C0B measurement must be an object.",
                index=index,
            )
        missing_measurement_fields = [
            field_name
            for field_name in MEASUREMENT_FIELDS
            if field_name not in measurement or _missing(measurement.get(field_name))
        ]
        if missing_measurement_fields:
            return _error(
                "missing_measurement_fields",
                "Stage 3C0B measurement is missing required fields.",
                index=index,
                missing=missing_measurement_fields,
            )

    normalized = dict(record)
    normalized["id"] = evidence_id_for(
        normalized.get("plan_id"),
        normalized.get("step_id"),
        normalized.get("claim_key"),
    )
    return EvidenceValidationResult(True, record=normalized)
