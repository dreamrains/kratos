from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
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

DERIVED_OPERATIONS = {
    "sum", "difference", "product", "ratio", "percent_change",
    "percentage_point_change",
}

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

NORMALIZED_EVIDENCE_TEXT_FIELDS = (
    "plan_id",
    "step_id",
    "claim_key",
    "dataset",
    "dataset_contract_id",
    "method",
    "confidence",
    "evidence_requirement",
)

NORMALIZED_MEASUREMENT_TEXT_FIELDS = (
    "metric",
    "definition",
    "unit",
    "grain",
    "population_scope",
    "time_scope",
    "method",
    "denominator",
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


def validate_stage3c0b_measurement(
    measurement: Any,
    *,
    index: int = 0,
) -> EvidenceValidationResult:
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

    normalized = dict(measurement)
    for field_name in NORMALIZED_MEASUREMENT_TEXT_FIELDS:
        if field_name in normalized:
            normalized[field_name] = _text(normalized[field_name])
    return EvidenceValidationResult(True, record=normalized)


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

    normalized_measurements = []
    for index, measurement in enumerate(measurements):
        measurement_validation = validate_stage3c0b_measurement(measurement, index=index)
        if not measurement_validation.ok:
            return measurement_validation
        normalized_measurements.append(measurement_validation.record)

    normalized = dict(record)
    for field_name in NORMALIZED_EVIDENCE_TEXT_FIELDS:
        if field_name in normalized:
            normalized[field_name] = _text(normalized[field_name])
    normalized["measurements"] = normalized_measurements
    derived = record.get("derived_measurements")
    if derived is not None:
        validation = validate_derived_measurements(derived, normalized_measurements)
        if not validation.ok:
            return validation
        normalized["derived_measurements"] = validation.record.get("derived_measurements", [])
    normalized["id"] = evidence_id_for(
        normalized.get("plan_id"),
        normalized.get("step_id"),
        normalized.get("claim_key"),
    )
    return EvidenceValidationResult(True, record=normalized)


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _measurement_ref(measurement: dict[str, Any], index: int) -> str:
    return str(measurement.get("id") or measurement.get("metric") or f"measurement_{index}")


def validate_derived_measurements(
    derived: Any,
    measurements: list[dict[str, Any]],
) -> EvidenceValidationResult:
    """Recompute a closed set of operations; arbitrary expressions are never executed."""
    if not isinstance(derived, list):
        return _error("invalid_derived_measurements", "derived_measurements must be an array.")
    keys = [_measurement_ref(item, index) for index, item in enumerate(measurements) if isinstance(item, dict)]
    if len(keys) != len(set(keys)):
        return _error("ambiguous_derived_operand", "Canonical operand identities must be unique within this EvidenceRecord.")
    operands = {
        _measurement_ref(item, index): item
        for index, item in enumerate(measurements)
        if isinstance(item, dict)
    }
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(derived):
        if not isinstance(item, dict):
            return _error("invalid_derived_measurement", "Each derived measurement must be an object.", index=index)
        operation = str(item.get("operation") or "")
        refs = item.get("operand_refs")
        if operation not in DERIVED_OPERATIONS or not isinstance(refs, list) or not refs:
            return _error("invalid_derived_operation", "Derived operation or operand_refs is invalid.", index=index)
        if any(str(ref) not in operands for ref in refs):
            return _error("unbound_derived_operand", "Derived operand does not belong to this EvidenceRecord.", index=index)
        if operation in {"difference", "ratio", "percent_change", "percentage_point_change"} and len(refs) != 2:
            return _error("invalid_derived_arity", "This derived operation requires exactly two operands.", index=index)
        source = [operands[str(ref)] for ref in refs]
        values = [_decimal(entry.get("value")) for entry in source]
        if any(value is None for value in values):
            return _error("invalid_derived_operand", "Derived operands must be finite numeric values.", index=index)
        scopes = {
            (str(entry.get("population_scope") or ""), str(entry.get("time_scope") or ""), str(entry.get("unit") or ""))
            for entry in source
        }
        if len({scope[:2] for scope in scopes}) != 1:
            return _error("derived_scope_mismatch", "Derived operands have different population or time scopes.", index=index)
        identities = {
            str(entry.get("data_identity") or entry.get("source_version") or "")
            for entry in source
            if entry.get("data_identity") or entry.get("source_version")
        }
        if len(identities) > 1:
            return _error("derived_source_mismatch", "Derived operands belong to different data versions.", index=index)
        units = {str(entry.get("unit") or "") for entry in source}
        if operation in {"sum", "difference", "percent_change", "percentage_point_change"} and len(units) != 1:
            return _error("derived_unit_mismatch", "Derived operands have incompatible units.", index=index)
        nums = [value for value in values if value is not None]
        try:
            if operation == "sum":
                expected = sum(nums, Decimal(0))
            elif operation == "difference":
                expected = nums[0] - nums[1]
            elif operation == "product":
                expected = nums[0]
                for number in nums[1:]:
                    expected *= number
            elif operation == "ratio":
                if len(nums) != 2 or nums[1] == 0:
                    raise ZeroDivisionError
                expected = nums[0] / nums[1]
            elif operation == "percent_change":
                if len(nums) != 2 or nums[0] <= 0:
                    raise ZeroDivisionError
                expected = (nums[1] - nums[0]) / nums[0] * Decimal(100)
            else:
                if len(nums) != 2:
                    return _error("invalid_derived_arity", "percentage_point_change requires two operands.", index=index)
                expected = (nums[1] - nums[0]) * Decimal(100)
        except (ZeroDivisionError, IndexError):
            return _error("undefined_derived_measurement", "Derived operation is undefined for these operands.", index=index)
        reported = _decimal(item.get("result"))
        if reported is None:
            return _error("invalid_derived_result", "Derived result must be finite.", index=index)
        tolerance = max(Decimal("0.000000001"), abs(expected) * Decimal("0.000001"))
        if abs(reported - expected) > tolerance:
            return _error(
                "derived_result_mismatch",
                "Derived result does not match the host recomputation.",
                index=index,
                expected=format(expected, "f"),
            )
        normalized_item = dict(item)
        normalized_item["operation"] = operation
        normalized_item["operand_refs"] = [str(ref) for ref in refs]
        normalized_item["result"] = format(expected, "f")
        normalized.append(normalized_item)
    return EvidenceValidationResult(True, record={"derived_measurements": normalized})
