"""Deterministic verification checks for analysis claims."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from data_agent.agent.evidence_compatibility import compare_measurements
from data_agent.agent.evidence_contracts import (
    MEASUREMENT_PROJECTION_ORIGIN,
    validate_measurement,
)


REQUIRED_EVIDENCE_FIELDS = (
    "dataset",
    "method",
    "sample_size",
    "time_scope",
    "calculation_method",
    "method_detail",
    "limitations",
)

CAUSAL_WORDS = ("causal", "caused", "causes", "cause", "导致", "证明", "使得")
CAUSAL_METHODS = {
    "causal", "ab_test", "experiment", "randomized experiment",
    "did", "difference_in_differences", "matching", "weighting",
    "instrumental_variables", "regression_discontinuity",
}
INFERENTIAL_METHODS = CAUSAL_METHODS | {
    "correlation",
    "regression",
    "ttest",
    "welch_t",
    "mannwhitneyu",
    "chi2",
}
INFERENTIAL_METHOD_PATTERNS = (
    "ab test",
    "chi square",
    "chi2",
    "correlation",
    "difference in differences",
    "experiment",
    "mann whitney",
    "regression",
    "t test",
    "ttest",
    "welch",
)
RISKY_CLEANING_DECISIONS = {"needs_confirmation", "blocked"}
MATCH_STOPWORDS = {"a", "an", "and", "by", "in", "of", "the", "to"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted((_json_safe(item) for item in value), key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _stable_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:10]
    return f"verify_{digest}"


def _claim_text(claim: Any) -> str:
    if isinstance(claim, dict):
        return str(claim.get("claim") or claim.get("text") or claim.get("statement") or "")
    return str(claim or "")


def _claim_external_id(claim: Any) -> str:
    if isinstance(claim, dict):
        return str(claim.get("id") or claim.get("claim_id") or "")
    return ""


def _claim_evidence_id(claim: Any) -> str:
    evidence_ids = _claim_evidence_ids(claim)
    return evidence_ids[0] if evidence_ids else ""


def _claim_evidence_refs(claim: Any) -> list[dict[str, str]]:
    if not isinstance(claim, dict):
        return []
    refs = []
    for item in _normalize_items(claim.get("evidence_refs")):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "").strip()
        measurement_key = str(item.get("measurement_key") or "").strip()
        if evidence_id:
            refs.append({
                "evidence_id": evidence_id,
                "measurement_key": measurement_key,
            })
    return refs


def _claim_evidence_ids(claim: Any) -> list[str]:
    if not isinstance(claim, dict):
        return []
    values = [claim.get("evidence_id")]
    values.extend(_normalize_items(claim.get("evidence_ids")))
    values.extend(
        item["evidence_id"] for item in _claim_evidence_refs(claim)
    )
    return list(dict.fromkeys(
        str(item).strip() for item in values if str(item or "").strip()
    ))


def _claim_compare_evidence_ids(claim: Any) -> list[str]:
    if not isinstance(claim, dict):
        return []
    return [
        str(item)
        for item in _normalize_items(claim.get("compare_evidence_ids"))
        if str(item or "").strip()
    ]


def _claim_id(claim: Any, index: int) -> str:
    if isinstance(claim, dict) and claim.get("id"):
        return str(claim["id"])
    return f"claim_{index + 1}"


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, dict):
        return len(value) == 0
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    if hasattr(value, "empty"):
        try:
            return bool(value.empty)
        except (TypeError, ValueError):
            return False
    if hasattr(value, "size"):
        try:
            return int(value.size) == 0
        except (TypeError, ValueError):
            return False
    return False


def _normalize_text(text: Any) -> str:
    lowered = str(text or "").lower()
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokens(text: Any) -> set[str]:
    return {token for token in _normalize_text(text).split() if token and token not in MATCH_STOPWORDS}


def _text_match_score(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        shorter = min(len(left_norm), len(right_norm))
        longer = max(len(left_norm), len(right_norm))
        return 0.86 if shorter / longer >= 0.45 else 0.0

    left_tokens = _tokens(left_norm)
    right_tokens = _tokens(right_norm)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    precision = overlap / len(left_tokens)
    recall = overlap / len(right_tokens)
    if overlap >= 4 and precision >= 0.65 and recall >= 0.55:
        return (precision + recall) / 2
    if overlap >= 3 and precision >= 0.8 and recall >= 0.8:
        return (precision + recall) / 2
    return 0.0


def _record_ids(record: dict[str, Any]) -> set[str]:
    fields = (
        "id",
        "claim_id",
        "source_claim_id",
        "analysis_claim_id",
        "claim_ref",
        "claim_reference",
    )
    return {str(record[field]) for field in fields if record.get(field)}


def _record_matches_current_plan(record: dict[str, Any], current_plan_id: str) -> bool:
    if not current_plan_id:
        return True
    return str(record.get("plan_id") or "").strip() == str(current_plan_id or "").strip()


def _current_plan_evidence(
    evidence_records: list[dict[str, Any]],
    current_plan_id: str,
) -> list[dict[str, Any]]:
    return [
        record
        for record in evidence_records
        if _record_matches_current_plan(record, current_plan_id)
    ]


def _find_evidence_by_id(
    evidence_id: str,
    evidence_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not evidence_id:
        return []
    return [
        record
        for record in evidence_records
        if str(record.get("id") or "") == evidence_id
    ]


def _find_evidence(claim: Any, evidence_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    claim_text = _claim_text(claim)
    external_id = _claim_external_id(claim)
    if external_id:
        for record in evidence_records:
            if external_id in _record_ids(record):
                return record

    for record in evidence_records:
        if _text_match_score(claim_text, str(record.get("claim") or "")) >= 0.74:
            return record
    return None


def _comparison_measurements(
    record: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    measurements = record.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return [], [f"Comparison evidence {record.get('id')} is missing measurements"]

    valid_measurements: list[dict[str, Any]] = []
    issues: list[str] = []
    for index, measurement in enumerate(measurements):
        validation = validate_measurement(measurement, index=index)
        if not validation.ok:
            issues.append(
                "Measurement compatibility failed: "
                f"comparison evidence {record.get('id')} has invalid measurement at index {index}: "
                f"{validation.error_type}"
            )
            continue
        normalized_measurement = validation.record
        validity = compare_measurements(normalized_measurement, normalized_measurement)
        if not validity.compatible:
            issues.append(
                "Measurement compatibility failed: "
                f"comparison evidence {record.get('id')} has invalid measurement at index {index}: "
                f"{validity.reason_code}"
            )
            continue
        valid_measurements.append(normalized_measurement)
    return valid_measurements, issues


def _comparison_issues(
    claim: Any,
    evidence_records: list[dict[str, Any]],
    current_plan_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    evidence_ids = _claim_compare_evidence_ids(claim)
    if not evidence_ids:
        return [], []

    referenced_records: list[dict[str, Any]] = []
    issues: list[str] = []
    seen_record_ids: set[str] = set()
    for evidence_id in evidence_ids:
        matches = _find_evidence_by_id(evidence_id, evidence_records)
        current_matches = [
            record for record in matches if _record_matches_current_plan(record, current_plan_id)
        ]
        if matches and not current_matches:
            issues.append(
                f"Evidence {evidence_id} is outside the current plan and cannot support this claim"
            )
            continue
        if not current_matches:
            issues.append(f"Comparison evidence {evidence_id} was not found")
            continue
        record = current_matches[0]
        record_id = str(record.get("id") or "")
        if record_id not in seen_record_ids:
            referenced_records.append(record)
            seen_record_ids.add(record_id)

    if len(referenced_records) < 2:
        issues.append("A comparison requires at least two evidence records")

    first_measurements: list[tuple[str, dict[str, Any]]] = []
    for record in referenced_records:
        measurements, measurement_issues = _comparison_measurements(record)
        issues.extend(measurement_issues)
        if not measurements:
            continue
        first_measurements.append((str(record.get("id") or ""), measurements[0]))

    for left_index in range(len(first_measurements)):
        for right_index in range(left_index + 1, len(first_measurements)):
            compatibility = compare_measurements(
                first_measurements[left_index][1],
                first_measurements[right_index][1],
            )
            if not compatibility.compatible:
                issues.append(f"Measurement compatibility failed: {compatibility.user_message}")

    return referenced_records, issues


def _uses_causal_language(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in CAUSAL_WORDS)


def _is_causal_method(method: Any) -> bool:
    normalized = str(method or "").strip().lower()
    return normalized in CAUSAL_METHODS


def _identification_value(evidence: dict[str, Any], name: str) -> Any:
    if name in evidence:
        return evidence.get(name)
    support = evidence.get("statistical_support")
    if isinstance(support, dict) and name in support:
        return support.get(name)
    checks = evidence.get("assumption_checks")
    if isinstance(checks, dict) and name in checks:
        return checks.get(name)
    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("name") or item.get("check") or "").strip().lower()
            if item_name == name:
                return item
    return None


def _normalized_status(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("status")
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _causal_design_type(evidence: dict[str, Any]) -> str:
    identification = _identification_value(evidence, "identification_status")
    if isinstance(identification, dict):
        raw = identification.get("design_type")
    else:
        raw = None
    raw = raw or evidence.get("design_type") or evidence.get("causal_design")
    normalized = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "randomized": "randomized_experiment",
        "rct": "randomized_experiment",
        "did": "difference_in_differences",
        "before_after": "pre_post",
        "instrumental_variable": "instrumental_variables",
        "rd": "regression_discontinuity",
    }
    return aliases.get(normalized, normalized)


def _diagnostic_passed(evidence: dict[str, Any], name: str) -> bool:
    return _normalized_status(_identification_value(evidence, name)) in {
        "passed", "satisfied", "adequate", "supported",
    }


def _causal_identification_issues(evidence: dict[str, Any]) -> list[str]:
    identification = _identification_value(evidence, "identification_status")
    if not isinstance(identification, dict):
        return ["Causal publication requires explicit identification_status evidence."]
    status = _normalized_status(identification)
    allowed_claim_class = str(
        identification.get("allowed_claim_class") or ""
    ).strip().lower()
    design_type = _causal_design_type(evidence)
    if status != "identified" or allowed_claim_class != "causal":
        return [
            f"The {design_type or 'declared'} design does not identify a causal effect; "
            "the allowed claim class is association/descriptive comparison."
        ]

    required_fields = {
        "randomized_experiment": (
            "assignment_unit", "treatment_arms", "exposure_definition",
            "outcome_definition", "per_arm_sample_size", "attrition",
        ),
        "difference_in_differences": ("comparison_group", "treatment_timing"),
        "matching": (),
        "weighting": (),
        "instrumental_variables": ("instrument_definition", "exclusion_restriction"),
        "regression_discontinuity": ("cutoff_assignment",),
    }.get(design_type)
    if required_fields is None:
        return [f"Unsupported or unspecified causal design_type: {design_type or 'missing'}."]
    missing = [
        name for name in required_fields
        if _is_missing(_identification_value(evidence, name))
    ]
    if _is_missing(_identification_value(evidence, "confidence_interval")):
        missing.append("confidence_interval")
    if missing:
        return ["Causal identification evidence is missing: " + ", ".join(missing)]

    diagnostic_fields = {
        "randomized_experiment": ("randomization_integrity", "balance_diagnostics"),
        "difference_in_differences": ("parallel_trends",),
        "matching": ("overlap_diagnostics", "balance_diagnostics"),
        "weighting": ("overlap_diagnostics", "balance_diagnostics"),
        "instrumental_variables": ("instrument_relevance",),
        "regression_discontinuity": ("discontinuity_diagnostics",),
    }[design_type]
    failed = [name for name in diagnostic_fields if not _diagnostic_passed(evidence, name)]
    if failed:
        return [
            "Causal identification diagnostics are missing or not passed: " + ", ".join(failed)
        ]

    outcome_count = evidence.get("outcome_count")
    try:
        multiple_outcomes = int(outcome_count) > 1
    except (TypeError, ValueError):
        multiple_outcomes = False
    if multiple_outcomes and _is_missing(_identification_value(evidence, "multiplicity_handling")):
        return ["Causal effect with multiple outcomes requires multiplicity_handling evidence."]
    return []


def _risky_cleaning_issues(evidence: dict[str, Any], cleaning_logs: list[dict[str, Any]]) -> list[str]:
    evidence_dataset = str(evidence.get("dataset") or "")
    issues: list[str] = []
    for log in cleaning_logs:
        log_dataset = str(log.get("dataset") or "")
        if log_dataset and evidence_dataset and log_dataset != evidence_dataset:
            continue
        decisions = log.get("decisions") if isinstance(log.get("decisions"), list) else []
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            decision_type = str(decision.get("decision_type") or "")
            if decision_type in RISKY_CLEANING_DECISIONS:
                column = str(decision.get("column") or "unknown column")
                issues.append(
                    f"Cleaning decision requires confirmation: {decision_type} on {column}"
                )
    return issues


def _plan_revision_issues(
    evidence: dict[str, Any],
    *,
    current_plan_digest: str,
    current_step_digests: dict[str, str],
) -> list[str]:
    if evidence.get("contract_version") != "evidence_record.v2":
        return []
    refs = [
        ref
        for ref in _normalize_items(evidence.get("computation_refs"))
        if isinstance(ref, dict)
    ]
    if not refs:
        return ["Evidence has no computation refs for the current plan revision"]
    step_id = str(evidence.get("step_id") or "")
    current_step_digest = current_step_digests.get(step_id, "")
    issues: list[str] = []
    for ref in refs:
        if current_plan_digest and str(ref.get("plan_digest") or "") != current_plan_digest:
            issues.append("Evidence belongs to a different semantic revision of the current plan")
            break
        if current_step_digests and not current_step_digest:
            issues.append("Evidence step is absent from the current semantic plan revision")
            break
        if current_step_digest and str(ref.get("step_digest") or "") != current_step_digest:
            issues.append("Evidence belongs to a different semantic revision of the current plan step")
            break
    return issues


def _finalize_check(check: dict[str, Any]) -> dict[str, Any]:
    check.setdefault("measurement_key", None)
    reason_codes = list(check.get("reason_codes") or [])
    for issue in check.get("issues") or []:
        lowered = str(issue).lower()
        if "missing an exact evidencerecord identity" in lowered:
            code = "missing_evidence_identity"
        elif "missing a limitation disclosure" in lowered:
            code = "missing_limitation"
        elif "missing an exploratory label" in lowered:
            code = "missing_exploratory_label"
        elif "outside the current plan" in lowered:
            code = "evidence_outside_current_plan"
        elif "explicit evidence" in lowered and "not found" in lowered:
            code = "evidence_identity_not_found"
        elif "no evidence record" in lowered:
            code = "unsupported_claim"
        elif "semantic revision" in lowered or "plan step" in lowered:
            code = "stale_plan_evidence"
        elif "stale dataset" in lowered:
            code = "stale_dataset_evidence"
        elif "artifact integrity" in lowered:
            code = "computation_integrity_failure"
        elif "causal" in lowered or "identif" in lowered:
            code = "causal_claim_not_identified"
        elif "cleaning decision" in lowered:
            code = "unresolved_cleaning_risk"
        elif "missing required fields" in lowered:
            code = "incomplete_evidence_record"
        else:
            code = "evidence_check_failed" if check.get("status") == "failed" else "claim_revision_required"
        if code not in reason_codes:
            reason_codes.append(code)
    check["reason_codes"] = reason_codes
    if check.get("status") == "failed":
        check["safe_action"] = {
            "action": "remove_or_downgrade_claim",
            "target_claim_id": check.get("claim_id"),
        }
    elif check.get("status") == "downgraded":
        check["safe_action"] = {
            "action": "revise_with_limitations",
            "target_claim_id": check.get("claim_id"),
        }
    else:
        check["safe_action"] = None
    return check


def _mark_downgraded(check: dict[str, Any], issues: str | list[str]) -> None:
    if check.get("status") != "failed":
        check["status"] = "downgraded"
        check["strength"] = "likely"
    if isinstance(issues, list):
        check["issues"].extend(issues)
    else:
        check["issues"].append(issues)


def _claim_requires_evidence(claim: Any) -> bool:
    if not isinstance(claim, dict):
        return True
    if claim.get("requires_evidence") is False:
        return False
    return claim.get("material") is not False


def _measurement_items(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _normalize_items(evidence.get("measurements"))
        if isinstance(item, dict)
    ]


def _identity_measurements(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _normalize_items(record.get("measurements"))
        if isinstance(item, dict)
        and isinstance(item.get("identity"), dict)
    ]


def _numeric_evidence_items(
    evidence: dict[str, Any],
    *,
    selected_measurements: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    items = list(
        selected_measurements
        if selected_measurements is not None
        else _measurement_items(evidence)
    )
    if selected_measurements is not None:
        return items
    support = evidence.get("statistical_support")
    support = support if isinstance(support, dict) else {}
    effect = support.get("effect_estimate")
    if isinstance(effect, dict) and effect.get("value") is not None:
        items.append({"value": effect.get("value"), "unit": effect.get("unit")})

    interval = support.get("confidence_interval")
    if not isinstance(interval, dict):
        interval = evidence.get("confidence_interval")
    if isinstance(interval, dict):
        interval_unit = interval.get("unit")
        if not interval_unit and items:
            interval_unit = items[0].get("unit")
        for field in ("lower", "upper"):
            if interval.get(field) is not None:
                items.append({"value": interval.get(field), "unit": interval_unit})
        if interval.get("level") is not None:
            items.append({"value": interval.get("level"), "unit": "ratio"})

    test = support.get("test")
    if isinstance(test, dict) and test.get("p_value") is not None:
        items.append({"value": test.get("p_value"), "unit": ""})
    elif evidence.get("p_value") is not None:
        items.append({"value": evidence.get("p_value"), "unit": ""})
    return items


def _unit_family(unit: Any) -> str:
    normalized = str(unit or "").strip().lower()
    if normalized in {"value", "unitless", "unspecified", "unknown"}:
        return ""
    if normalized in {"%", "percent", "percentage", "ratio", "proportion"}:
        return "ratio"
    if normalized in {"percentage point", "percentage points", "pp"}:
        return "percentage_points"
    if normalized in {"cny", "rmb", "元", "人民币"}:
        return "cny"
    if normalized in {"usd", "$"}:
        return "usd"
    if normalized in {"count", "row", "rows", "行", "条", "人", "次", "件", "个"}:
        return "count"
    return normalized


def _normalized_numeric(value: Any, unit: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    normalized_unit = str(unit or "").strip().lower()
    if normalized_unit in {"%", "percent", "percentage"}:
        return number / 100.0
    return number


def _scope_matches(claim_scope: Any, evidence_scope: Any) -> bool:
    claim_text = _normalize_text(claim_scope)
    evidence_text = _normalize_text(evidence_scope)
    return bool(
        claim_text
        and evidence_text
        and (claim_text in evidence_text or evidence_text in claim_text)
    )


def _evidence_direction(evidence: dict[str, Any]) -> str:
    text = " ".join(str(evidence.get(key) or "") for key in ("claim", "result_summary"))
    if re.search(r"decrease|decreased|lower|decline|fell|drop|下降|降低|减少|低于", text, re.IGNORECASE):
        return "decrease"
    if re.search(r"increase|increased|higher|grew|growth|rise|rose|上升|增长|提高|提升|高于", text, re.IGNORECASE):
        return "increase"
    if re.search(r"no (?:material |significant )?change|unchanged|持平|无显著变化", text, re.IGNORECASE):
        return "no_change"
    return ""


def _strict_semantic_issues(
    claim: Any,
    evidence: dict[str, Any],
    *,
    selected_measurements: list[dict[str, Any]] | None = None,
) -> list[tuple[str, str]]:
    if not isinstance(claim, dict):
        return []
    issues: list[tuple[str, str]] = []
    measurements = (
        selected_measurements
        if selected_measurements is not None
        else _measurement_items(evidence)
    )
    numeric_evidence = _numeric_evidence_items(
        evidence,
        selected_measurements=selected_measurements,
    )
    quantities = [item for item in _normalize_items(claim.get("quantities")) if isinstance(item, dict)]
    if quantities:
        if not numeric_evidence:
            issues.append(("missing_structured_measurement", "Material numeric claim has no canonical measurement evidence"))
        else:
            for quantity in quantities:
                claim_family = _unit_family(quantity.get("unit"))
                compatible = [
                    measurement
                    for measurement in numeric_evidence
                    if _unit_family(measurement.get("unit")) == claim_family
                ]
                if not compatible:
                    issues.append(("unit_mismatch", f"Claim unit {quantity.get('unit') or 'unitless'} does not match evidence units"))
                    continue
                claim_value = _normalized_numeric(quantity.get("value"), quantity.get("unit"))
                if claim_value is None or not any(
                    (evidence_value := _normalized_numeric(item.get("value"), item.get("unit"))) is not None
                    and abs(evidence_value - claim_value) <= max(1e-9, abs(evidence_value) * 1e-6)
                    for item in compatible
                ):
                    issues.append(("numeric_mismatch", f"Claim quantity {quantity.get('raw')} does not match canonical evidence values"))

    claim_direction = str(claim.get("direction") or "")
    evidence_direction = (
        str(measurements[0].get("direction") or "")
        if selected_measurements is not None and len(measurements) == 1
        else _evidence_direction(evidence)
    )
    if claim_direction and claim_direction != evidence_direction:
        issues.append((
            "direction_mismatch",
            f"Claim direction {claim_direction} conflicts with evidence direction {evidence_direction or 'unavailable'}",
        ))

    for field, code in (("time_scope", "time_scope_mismatch"), ("population_scope", "population_scope_mismatch")):
        claim_scope = claim.get(field)
        if not claim_scope:
            continue
        evidence_scopes = [item.get(field) for item in measurements if item.get(field)]
        if not evidence_scopes and evidence.get(field):
            evidence_scopes = [evidence.get(field)]
        if not evidence_scopes or not any(_scope_matches(claim_scope, scope) for scope in evidence_scopes):
            issues.append((code, f"Claim {field} {claim_scope} does not match evidence scope"))

    if (
        str(claim.get("confidence_assertion") or "") == "high"
        and str(evidence.get("confidence") or "").strip().lower() != "high"
    ):
        issues.append((
            "confidence_mismatch",
            "High-confidence claim is not supported by high-confidence evidence",
        ))

    if claim.get("verification_overclaim") is True and str(evidence.get("verification_level") or "").strip().lower() == "traceable":
        issues.append((
            "verification_level_overclaim",
            "Traceable provenance does not independently verify statistical correctness",
        ))
    return issues


def _claim_mentions_trusted_metric(
    claim_text: Any,
    metric_label: Any,
    metric_aliases: Any,
) -> bool:
    normalized_claim = _normalize_text(claim_text)
    if not normalized_claim:
        return False
    candidates = [
        str(metric_label or ""),
        *[
            str(item)
            for item in _normalize_items(metric_aliases)
            if str(item or "").strip()
        ],
    ]
    generic_single_labels = {"correlation"}
    padded_claim = f" {normalized_claim} "
    for candidate in candidates:
        normalized_candidate = _normalize_text(candidate)
        if (
            not normalized_candidate
            or normalized_candidate in generic_single_labels
        ):
            continue
        if (
            f" {normalized_candidate} " in padded_claim
            or (
                re.search(r"[\u4e00-\u9fff]", normalized_candidate)
                and normalized_candidate in normalized_claim
            )
        ):
            return True
    return False


def _metric_base_identity_issues(
    measurement_metric: Any,
    identity_metric_key: Any,
    metric_label: Any,
    metric_aliases: Any,
) -> list[tuple[str, str]]:
    measurement_base = str(measurement_metric or "").strip()
    metric_key = str(identity_metric_key or "").strip()
    identity_base, delimiter, context = metric_key.partition("::")
    if (
        not measurement_base
        or identity_base != measurement_base
        or (delimiter and not context)
    ):
        return [(
            "measurement_metric_mismatch",
            "Measurement metric identity does not match the selected measurement.",
        )]

    base_tokens = _normalize_text(
        re.sub(r"[._]+", " ", measurement_base)
    ).split()
    structural_tokens = {
        "change",
        "coefficients",
        "correlation",
        "delta",
        "estimate",
        "effect",
        "metric",
        "measurements",
        "pair",
        "pairs",
        "rate",
        "total",
        "value",
        "values",
    }
    authoritative_tokens = [
        token for token in base_tokens if token not in structural_tokens
    ]
    if not authoritative_tokens:
        return []

    trusted_labels = [
        str(metric_label or ""),
        *[
            str(item)
            for item in _normalize_items(metric_aliases)
            if str(item or "").strip()
        ],
    ]
    if not any(
        all(
            token in (label_tokens := set(_normalize_text(label).split()))
            or (
                re.search(r"[\u4e00-\u9fff]", token)
                and token in _normalize_text(label)
            )
            for token in authoritative_tokens
        )
        for label in trusted_labels
    ):
        return [(
            "measurement_metric_mismatch",
            "Trusted metric wording is inconsistent with its authoritative base metric.",
        )]
    return []


def _measurement_identity_issues(
    claim: dict[str, Any],
    evidence: dict[str, Any],
    measurement: dict[str, Any],
    *,
    current_plan_id: str,
    current_plan_digest: str,
    current_step_digests: dict[str, str],
    current_dataset_versions: set[str] | None,
    active_requirement_ids: set[str],
) -> list[tuple[str, str]]:
    from data_agent.agent.evidence_contracts import (
        computation_ref_key,
        validate_measurement_identity,
    )

    identity = measurement.get("identity")
    if not isinstance(identity, dict):
        return [(
            "measurement_identity_missing",
            "Referenced measurement has no server-owned identity.",
        )]
    validation = validate_measurement_identity(identity)
    if not validation.ok:
        return [(
            "measurement_marker_invalid",
            "Referenced measurement identity is invalid.",
        )]
    checks = [
        (
            identity.get("plan_id") == current_plan_id,
            "measurement_marker_invalid",
            "Measurement plan identity does not match the current plan.",
        ),
        (
            not current_plan_digest
            or identity.get("plan_version") == current_plan_digest,
            "measurement_marker_invalid",
            "Measurement plan version does not match the current plan.",
        ),
        (
            not current_plan_digest
            or all(
                str(ref.get("plan_digest") or "")
                == identity.get("plan_version")
                for ref in evidence.get("computation_refs") or []
                if isinstance(ref, dict)
            ),
            "measurement_marker_invalid",
            "Measurement plan version does not match its computation.",
        ),
        (
            identity.get("claim_key") == evidence.get("claim_key"),
            "measurement_claim_key_mismatch",
            "Measurement claim key does not match its EvidenceRecord.",
        ),
        (
            identity.get("step_id") == evidence.get("step_id"),
            "measurement_marker_invalid",
            "Measurement step does not match its EvidenceRecord.",
        ),
        (
            not current_step_digests
            or identity.get("step_id") in current_step_digests,
            "measurement_marker_invalid",
            "Measurement step is absent from the current plan revision.",
        ),
    ]
    issues = [(code, message) for ok, code, message in checks if not ok]
    computation_ref_ids = {
        computation_ref_key(ref)
        for ref in evidence.get("computation_refs") or []
        if isinstance(ref, dict)
    }
    if identity.get("computation_ref_id") not in computation_ref_ids:
        issues.append((
            "measurement_marker_invalid",
            "Measurement computation identity does not match its EvidenceRecord.",
        ))
    identity_requirement_ids = {
        str(item) for item in identity.get("requirement_ids") or []
    }
    evidence_requirement_ids = {
        str(item) for item in evidence.get("requirement_ids") or []
    }
    if (
        identity_requirement_ids != evidence_requirement_ids
        or not identity_requirement_ids
        or not identity_requirement_ids.issubset(active_requirement_ids)
    ):
        issues.append((
            "measurement_claim_key_mismatch",
            "Measurement requirements are not eligible in the current plan.",
        ))
    identity_versions = {
        str(item) for item in identity.get("dataset_versions") or []
    }
    evidence_versions = {
        str(item) for item in evidence.get("dataset_versions") or []
    }
    if (
        current_dataset_versions is None
        or identity_versions != evidence_versions
        or identity_versions != current_dataset_versions
    ):
        issues.append((
            "measurement_dataset_version_mismatch",
            "Measurement dataset versions do not exactly match the current scope.",
        ))
    issues.extend(_metric_base_identity_issues(
        measurement.get("metric"),
        identity.get("metric_key"),
        identity.get("metric_label"),
        identity.get("metric_aliases"),
    ))
    if not _claim_mentions_trusted_metric(
        _claim_text(claim),
        identity.get("metric_label"),
        identity.get("metric_aliases"),
    ):
        issues.append((
            "measurement_metric_mismatch",
            "Claim metric wording does not match the referenced measurement.",
        ))
    for field, code in (
        ("value", "numeric_mismatch"),
        ("unit", "unit_mismatch"),
        ("direction", "direction_mismatch"),
        ("time_scope", "measurement_scope_mismatch"),
        ("population_scope", "measurement_scope_mismatch"),
    ):
        if identity.get(field) != measurement.get(field):
            issues.append((
                code,
                f"Measurement identity {field} does not match the selected measurement.",
            ))
    if identity.get("allowed_claim_class") != evidence.get("allowed_claim_class"):
        issues.append((
            "measurement_claim_key_mismatch",
            "Measurement claim class does not match its EvidenceRecord.",
        ))
    return issues


def _measurement_claim_class_issues(
    claim: dict[str, Any],
    measurement: dict[str, Any],
) -> list[tuple[str, str]]:
    identity = measurement.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    allowed = _normalize_text(identity.get("allowed_claim_class")).replace(" ", "_")
    claim_type = _normalize_text(claim.get("claim_type")).replace(" ", "_")
    if claim_type == "causal" and allowed not in {"causal", "causal_effect"}:
        return [(
            "causal_claim_not_identified",
            "Referenced measurement does not permit a causal claim.",
        )]
    if (
        claim_type
        in {
            "association",
            "inferential",
            "inferential_association",
            "inferential_associations",
        }
        and allowed
        not in {
            "association",
            "exploratory_association",
            "inferential_association",
            "inferential_associations",
            "causal",
            "causal_effect",
        }
    ):
        return [(
            "verification_level_overclaim",
            "Referenced measurement does not permit an inferential association claim.",
        )]
    return []


def _claim_matches_projected_metric_fields(
    claim: dict[str, Any],
    measurement: dict[str, Any],
) -> bool:
    """Require server-projected metric semantics, not only equal numbers."""

    claim_text = _normalize_text(_claim_text(claim)).replace("_", " ")
    if not claim_text:
        return False
    structural_tokens = {
        "change",
        "correlation",
        "estimate",
        "effect",
        "metric",
        "rate",
        "total",
        "value",
        "values",
    }
    metric_tokens = [
        token
        for token in _normalize_text(measurement.get("metric"))
        .replace("_", " ")
        .split()
        if token not in structural_tokens
    ]
    if metric_tokens and all(token in claim_text.split() for token in metric_tokens):
        return True

    definition_tokens = [
        token
        for token in _normalize_text(measurement.get("definition"))
        .replace("_", " ")
        .split()
        if token not in MATCH_STOPWORDS and token not in structural_tokens
    ]
    if not definition_tokens:
        return False
    overlap = sum(token in claim_text.split() for token in definition_tokens)
    return overlap >= min(2, len(definition_tokens))


def _has_current_bound_computation(
    evidence: dict[str, Any],
    *,
    current_plan_digest: str,
    current_step_digests: dict[str, str],
    current_dataset_versions: set[str] | None,
) -> bool:
    """Recognize only a current server-bound v2 computation candidate."""

    if (
        evidence.get("contract_version") != "evidence_record.v2"
        or evidence.get("provenance_status") != "bound"
        or not current_plan_digest
        or current_dataset_versions is None
    ):
        return False
    step_id = str(evidence.get("step_id") or "")
    current_step_digest = current_step_digests.get(step_id, "")
    if not step_id or not current_step_digest:
        return False
    evidence_versions = {
        str(item)
        for item in _normalize_items(evidence.get("dataset_versions"))
        if str(item or "")
    }
    if not evidence_versions or evidence_versions != current_dataset_versions:
        return False
    refs = [
        ref
        for ref in _normalize_items(evidence.get("computation_refs"))
        if isinstance(ref, dict)
    ]
    if not refs:
        return False
    return all(
        ref.get("contract_version") == "computation_ref.v1"
        and ref.get("success") is not False
        and str(ref.get("plan_id") or "") == str(evidence.get("plan_id") or "")
        and str(ref.get("plan_digest") or "") == current_plan_digest
        and str(ref.get("step_id") or "") == step_id
        and str(ref.get("step_digest") or "") == current_step_digest
        and {
            str(item)
            for item in _normalize_items(ref.get("dataset_versions"))
            if str(item or "")
        }
        == current_dataset_versions
        for ref in refs
    )


def _exact_exploratory_measurement_candidates(
    claim: dict[str, Any],
    evidence_records: list[dict[str, Any]],
    *,
    current_plan_id: str,
    current_plan_digest: str,
    current_step_digests: dict[str, str],
    current_dataset_versions: set[str] | None,
    active_requirement_ids: set[str],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    candidates = []
    for evidence in _current_plan_evidence(evidence_records, current_plan_id):
        if not _has_current_bound_computation(
            evidence,
            current_plan_digest=current_plan_digest,
            current_step_digests=current_step_digests,
            current_dataset_versions=current_dataset_versions,
        ):
            continue
        for measurement in _measurement_items(evidence):
            identity = measurement.get("identity")
            if isinstance(identity, dict):
                identity_issues = _measurement_identity_issues(
                    claim,
                    evidence,
                    measurement,
                    current_plan_id=current_plan_id,
                    current_plan_digest=current_plan_digest,
                    current_step_digests=current_step_digests,
                    current_dataset_versions=current_dataset_versions,
                    active_requirement_ids=active_requirement_ids,
                )
            elif (
                measurement.get("identity_status")
                == "metric_identity_missing"
                and measurement.get("projection_origin")
                == MEASUREMENT_PROJECTION_ORIGIN
                and _claim_matches_projected_metric_fields(claim, measurement)
            ):
                identity_issues = []
            else:
                continue
            semantic_issues = _strict_semantic_issues(
                claim,
                evidence,
                selected_measurements=[measurement],
            )
            claim_class_issues = _measurement_claim_class_issues(
                claim,
                measurement,
            )
            if not identity_issues and not semantic_issues and not claim_class_issues:
                candidates.append((evidence, measurement))
    return candidates


def _unmet_block_claim_requirements(
    claim_evidence_records: list[dict[str, Any]],
    analysis_requirements: list[dict[str, Any]],
    *,
    satisfaction_evidence_records: list[dict[str, Any]] | None = None,
    current_plan_id: str = "",
    current_plan_digest: str = "",
    current_step_digests: dict[str, str] | None = None,
    current_dataset_versions: set[str] | None = None,
    active_requirement_ids: set[str] | None = None,
    sessions_root: Any = None,
    current_session_id: str = "",
) -> list[str]:
    if not claim_evidence_records:
        return []
    step_id = str(claim_evidence_records[0].get("step_id") or "")
    matching = [
        requirement
        for requirement in analysis_requirements
        if isinstance(requirement, dict)
        and str(requirement.get("step_id") or "") == step_id
        and str(requirement.get("unmet_action") or "") == "block_claim"
    ]
    if not matching:
        return []
    from data_agent.agent.analysis_requirements import evaluate_requirement_satisfaction
    from data_agent.agent.evidence_contracts import (
        hydrate_computation_ref,
        validate_evidence_record,
    )

    try:
        current_steps = current_step_digests or {}
        active_ids = active_requirement_ids or set()
        qualified_support: list[dict[str, Any]] = []
        candidate_catalog = (
            satisfaction_evidence_records
            if satisfaction_evidence_records is not None
            else claim_evidence_records
        )
        for record in candidate_catalog:
            if (
                not validate_evidence_record(
                    record,
                    current_plan_id=current_plan_id,
                    require_measurement_identity=True,
                ).ok
                or not _has_current_bound_computation(
                    record,
                    current_plan_digest=current_plan_digest,
                    current_step_digests=current_steps,
                    current_dataset_versions=current_dataset_versions,
                )
            ):
                continue
            record_requirement_ids = {
                str(item)
                for item in record.get("requirement_ids") or []
                if str(item)
            }
            if (
                not record_requirement_ids
                or not active_ids
                or not record_requirement_ids.issubset(active_ids)
            ):
                continue
            try:
                for ref in record.get("computation_refs") or []:
                    hydrate_computation_ref(
                        ref,
                        sessions_root=sessions_root,
                        current_session_id=current_session_id or None,
                    )
            except (TypeError, ValueError):
                continue
            qualified_support.append(record)
        evaluated = evaluate_requirement_satisfaction(
            matching,
            qualified_support,
        )
        evaluated_all = evaluate_requirement_satisfaction(
            analysis_requirements,
            qualified_support,
        )
    except ValueError:
        return [str(item.get("id") or item.get("name") or "invalid_requirement") for item in matching]

    def _semantic_key(requirement: dict[str, Any]) -> str:
        semantic_contract = {
            key: value
            for key, value in requirement.items()
            if key not in {"id", "step_id", "status", "evidence_ids"}
        }
        for key in ("name", "category", "necessity", "unmet_action"):
            if key in semantic_contract:
                semantic_contract[key] = _normalize_text(semantic_contract[key])
        for key in ("required_evidence_fields", "assumption_checks"):
            if isinstance(semantic_contract.get(key), list):
                semantic_contract[key] = sorted(
                    _normalize_text(item)
                    for item in semantic_contract[key]
                )
        return json.dumps(
            semantic_contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    requirements_by_id = {
        str(item.get("id") or ""): item
        for item in analysis_requirements
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    satisfied_semantics = {
        _semantic_key(
            requirements_by_id.get(str(item.get("id") or ""), item)
        )
        for item in evaluated_all
        if item.get("status") == "satisfied"
    }
    return [
        str(item.get("id") or item.get("name") or "requirement")
        for item in evaluated
        if (
            item.get("status") == "unmet"
            and _semantic_key(
                requirements_by_id.get(str(item.get("id") or ""), item)
            )
            not in satisfied_semantics
        )
    ]


def _claim_guard_blockers(
    claim: Any,
    evidence_records: list[dict[str, Any]],
    analysis_requirements: list[dict[str, Any]],
) -> list[str]:
    if not re.search(
        r"\bseason(?:al|ality)\b|季节性",
        _claim_text(claim),
        re.IGNORECASE,
    ):
        return []
    step_ids = {
        str(record.get("step_id") or "")
        for record in evidence_records
        if str(record.get("step_id") or "")
    }
    return [
        str(requirement.get("id") or requirement.get("name") or "requirement")
        for requirement in analysis_requirements
        if isinstance(requirement, dict)
        and str(requirement.get("step_id") or "") in step_ids
        and requirement.get("name") == "seasonality_estimability"
        and requirement.get("claim_guard") == "block_claim"
    ]


def _check_claim(
    claim: Any,
    index: int,
    evidence_records: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
    current_plan_id: str = "",
    current_dataset_versions: set[str] | None = None,
    sessions_root: Any = None,
    current_session_id: str = "",
    current_plan_digest: str = "",
    current_step_digests: dict[str, str] | None = None,
    analysis_requirements: list[dict[str, Any]] | None = None,
    require_explicit_evidence_ids: bool = False,
    strict_claim_semantics: bool = False,
    measurement_binding_mode: str = "enforced",
) -> dict[str, Any]:
    text = _claim_text(claim)
    evidence: dict[str, Any] | None = None
    selected_measurement: dict[str, Any] | None = None
    exploratory_measurement_candidate = False
    measurement_v2_exact_match = False
    evidence_refs = _claim_evidence_refs(claim)
    requested_measurement_key = (
        evidence_refs[0]["measurement_key"]
        if len(evidence_refs) == 1
        else ""
    )
    measurement_resolution_issues: list[tuple[str, str]] = []
    active_requirement_ids = {
        str(item.get("id") or "")
        for item in analysis_requirements or []
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    if evidence_refs and isinstance(claim, dict):
        legacy_evidence_ids = {
            str(item).strip()
            for item in [
                claim.get("evidence_id"),
                *_normalize_items(claim.get("evidence_ids")),
            ]
            if str(item or "").strip()
        }
        referenced_evidence_ids = {
            item["evidence_id"] for item in evidence_refs
        }
        if (
            legacy_evidence_ids
            and legacy_evidence_ids != referenced_evidence_ids
        ):
            measurement_resolution_issues.append((
                "measurement_ambiguous",
                "Measurement reference conflicts with legacy evidence identity.",
            ))

    if not _claim_requires_evidence(claim):
        return _finalize_check({
            "claim_id": _claim_id(claim, index),
            "claim": text,
            "evidence_id": None,
            "status": "passed",
            "strength": "diagnostic",
            "issues": [],
            "reason_codes": ["diagnostic_without_positive_claim"],
        })

    comparison_records, comparison_issues = _comparison_issues(
        claim,
        evidence_records,
        current_plan_id,
    )
    if comparison_records:
        evidence = comparison_records[0]

    explicit_evidence_ids = _claim_evidence_ids(claim)
    if (
        require_explicit_evidence_ids
        and not explicit_evidence_ids
        and not _claim_compare_evidence_ids(claim)
    ):
        candidates = (
            _exact_exploratory_measurement_candidates(
                claim,
                evidence_records,
                current_plan_id=current_plan_id,
                current_plan_digest=current_plan_digest,
                current_step_digests=current_step_digests or {},
                current_dataset_versions=current_dataset_versions,
                active_requirement_ids=active_requirement_ids,
            )
            if (
                isinstance(claim, dict)
                and measurement_binding_mode in {"shadow", "soft"}
            )
            else []
        )
        if len(candidates) == 1:
            evidence, selected_measurement = candidates[0]
            exploratory_measurement_candidate = True
        elif len(candidates) > 1:
            return _finalize_check({
                "claim_id": _claim_id(claim, index),
                "claim": text,
                "evidence_id": None,
                "evidence_ids": [],
                "status": "failed",
                "strength": "unsupported",
                "issues": [
                    "Material final-answer claim matches multiple current "
                    "measurement candidates."
                ],
                "reason_codes": ["measurement_ambiguous"],
            })
        else:
            reason_code = (
                "measurement_identity_missing"
                if measurement_binding_mode == "enforced"
                else "missing_evidence_identity"
            )
            return _finalize_check({
                "claim_id": _claim_id(claim, index),
                "claim": text,
                "evidence_id": None,
                "evidence_ids": [],
                "status": "failed",
                "strength": "unsupported",
                "issues": [
                    "Material final-answer claim is missing an exact "
                    "EvidenceRecord measurement identity"
                ],
                "reason_codes": [reason_code],
            })
    explicit_support_records: list[dict[str, Any]] = []
    for explicit_evidence_id in explicit_evidence_ids:
        explicit_matches = _find_evidence_by_id(explicit_evidence_id, evidence_records)
        current_matches = [
            record
            for record in explicit_matches
            if _record_matches_current_plan(record, current_plan_id)
        ]
        if current_matches:
            explicit_support_records.append(current_matches[0])
        elif explicit_matches:
            comparison_issues.append(
                f"Evidence {explicit_evidence_id} is outside the current plan and cannot support this claim"
            )
        else:
            if current_plan_id:
                comparison_issues.append(
                    f"Explicit evidence {explicit_evidence_id} was not found in the current plan"
                )
            else:
                comparison_issues.append(f"Explicit evidence {explicit_evidence_id} was not found")

    if explicit_support_records:
        evidence = explicit_support_records[0]

    if evidence is None and not comparison_issues:
        evidence = _find_evidence(claim, _current_plan_evidence(evidence_records, current_plan_id))

    if evidence_refs:
        if len(evidence_refs) != 1:
            measurement_resolution_issues.append((
                "measurement_ambiguous",
                "Material claim must resolve to exactly one evidence measurement.",
            ))
        else:
            evidence_ref = evidence_refs[0]
            referenced_records = [
                record
                for record in _find_evidence_by_id(
                    evidence_ref["evidence_id"],
                    evidence_records,
                )
                if _record_matches_current_plan(record, current_plan_id)
            ]
            if len(referenced_records) > 1:
                measurement_resolution_issues.append((
                    "measurement_ambiguous",
                    "Evidence identity resolves to multiple current records.",
                ))
            elif len(referenced_records) == 1:
                evidence = referenced_records[0]
                identity_measurements = _identity_measurements(evidence)
                measurement_key = evidence_ref["measurement_key"]
                if measurement_key:
                    matching_measurements = [
                        item
                        for item in identity_measurements
                        if item["identity"].get("measurement_key")
                        == measurement_key
                    ]
                    if len(matching_measurements) == 1:
                        selected_measurement = matching_measurements[0]
                    elif len(matching_measurements) > 1:
                        measurement_resolution_issues.append((
                            "measurement_ambiguous",
                            "Measurement key resolves more than once in its EvidenceRecord.",
                        ))
                    else:
                        measurement_resolution_issues.append((
                            "measurement_not_found",
                            "Referenced measurement key was not found in its EvidenceRecord.",
                        ))
                else:
                    candidates = (
                        _exact_exploratory_measurement_candidates(
                            claim,
                            referenced_records,
                            current_plan_id=current_plan_id,
                            current_plan_digest=current_plan_digest,
                            current_step_digests=current_step_digests or {},
                            current_dataset_versions=current_dataset_versions,
                            active_requirement_ids=active_requirement_ids,
                        )
                        if (
                            isinstance(claim, dict)
                            and measurement_binding_mode in {"shadow", "soft"}
                        )
                        else []
                    )
                    if len(candidates) == 1:
                        evidence, selected_measurement = candidates[0]
                        exploratory_measurement_candidate = True
                    elif len(candidates) > 1:
                        measurement_resolution_issues.append((
                            "measurement_ambiguous",
                            "Legacy evidence marker matches multiple current measurements.",
                        ))
                    else:
                        measurement_resolution_issues.append((
                            (
                                "measurement_identity_missing"
                                if measurement_binding_mode == "enforced"
                                else "missing_evidence_identity"
                            ),
                            "Legacy evidence marker has no exact non-authorizing measurement candidate.",
                        ))

    check = {
        "claim_id": _claim_id(claim, index),
        "claim": text,
        "evidence_id": (
            evidence.get("id")
            if evidence and not exploratory_measurement_candidate
            else None
        ),
        "measurement_key": (
            requested_measurement_key
            if requested_measurement_key and not exploratory_measurement_candidate
            else None
        ),
        "evidence_ids": [
            str(record.get("id") or "")
            for record in (explicit_support_records or comparison_records or ([evidence] if evidence else []))
            if str(record.get("id") or "")
        ] if not exploratory_measurement_candidate else [],
        "status": "passed",
        "strength": "confirmed" if str((evidence or {}).get("confidence") or "").lower() == "high" else "likely",
        "issues": [],
    }

    if comparison_issues:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check["issues"].extend(comparison_issues)
        return _finalize_check(check)

    if measurement_resolution_issues:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        for reason_code, issue in measurement_resolution_issues:
            check.setdefault("reason_codes", []).append(reason_code)
            check["issues"].append(issue)
        return _finalize_check(check)

    if evidence is None:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check["issues"].append("No evidence record supports this claim")
        return _finalize_check(check)

    revision_issues: list[str] = []
    revision_records = (
        [evidence]
        if selected_measurement is not None
        else comparison_records or explicit_support_records or [evidence]
    )
    for revision_record in revision_records:
        revision_issues.extend(_plan_revision_issues(
            revision_record,
            current_plan_digest=current_plan_digest,
            current_step_digests=current_step_digests or {},
        ))
    if revision_issues:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check["issues"].extend(dict.fromkeys(revision_issues))
        return _finalize_check(check)

    evidence_versions = {
        str(version_id)
        for record in revision_records
        for ref in _normalize_items(record.get("computation_refs"))
        if isinstance(ref, dict)
        for version_id in _normalize_items(ref.get("dataset_versions"))
        if str(version_id or "")
    }
    if evidence_versions and current_dataset_versions is None:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check.setdefault("reason_codes", []).append(
            "current_dataset_identity_unavailable"
        )
        check["issues"].append(
            "Current dataset identity is unavailable for version-bound evidence"
        )
        return _finalize_check(check)
    if current_dataset_versions is not None:
        stale_versions = evidence_versions - current_dataset_versions
        if stale_versions:
            check["status"] = "failed"
            check["strength"] = "unsupported"
            check["issues"].append(
                "Evidence is bound to a stale dataset version: " + ", ".join(sorted(stale_versions))
            )
            return _finalize_check(check)

    if sessions_root is not None:
        from data_agent.agent.evidence_contracts import hydrate_computation_ref

        for record in revision_records:
            for ref in _normalize_items(record.get("computation_refs")):
                if not isinstance(ref, dict):
                    check["status"] = "failed"
                    check["strength"] = "unsupported"
                    check["issues"].append("Evidence computation artifact integrity check failed: invalid ref")
                    return _finalize_check(check)
                try:
                    hydrate_computation_ref(
                        ref,
                        sessions_root=sessions_root,
                        current_session_id=current_session_id or None,
                    )
                except ValueError as exc:
                    check["status"] = "failed"
                    check["strength"] = "unsupported"
                    check["issues"].append(
                        f"Evidence computation artifact integrity check failed: {exc}"
                    )
                    return _finalize_check(check)

    identity_issues: list[tuple[str, str]] = []
    if selected_measurement is not None and not exploratory_measurement_candidate:
        identity_issues = _measurement_identity_issues(
            claim,
            evidence,
            selected_measurement,
            current_plan_id=current_plan_id,
            current_plan_digest=current_plan_digest,
            current_step_digests=current_step_digests or {},
            current_dataset_versions=current_dataset_versions,
            active_requirement_ids=active_requirement_ids,
        )
        identity_issues.extend(
            _measurement_claim_class_issues(claim, selected_measurement)
        )
        if identity_issues:
            check["status"] = "failed"
            check["strength"] = "unsupported"
            for reason_code, issue in identity_issues:
                if reason_code not in check.setdefault("reason_codes", []):
                    check["reason_codes"].append(reason_code)
                check["issues"].append(issue)

    semantic_issues: list[tuple[str, str]] = []
    if strict_claim_semantics:
        semantic_issues = _strict_semantic_issues(
            claim,
            evidence,
            selected_measurements=(
                [selected_measurement]
                if selected_measurement is not None
                else None
            ),
        )
        if semantic_issues:
            check["status"] = "failed"
            check["strength"] = "unsupported"
            for reason_code, issue in semantic_issues:
                check.setdefault("reason_codes", []).append(reason_code)
                check["issues"].append(issue)
    if (
        selected_measurement is not None
        and not exploratory_measurement_candidate
        and isinstance(selected_measurement.get("identity"), dict)
        and not identity_issues
        and not semantic_issues
    ):
        measurement_v2_exact_match = True

    unmet_requirements = _unmet_block_claim_requirements(
        revision_records,
        analysis_requirements or [],
        satisfaction_evidence_records=evidence_records,
        current_plan_id=current_plan_id,
        current_plan_digest=current_plan_digest,
        current_step_digests=current_step_digests or {},
        current_dataset_versions=current_dataset_versions,
        active_requirement_ids=active_requirement_ids,
        sessions_root=sessions_root,
        current_session_id=current_session_id,
    )
    if unmet_requirements:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check.setdefault("reason_codes", []).append("unmet_block_claim_requirement")
        check["issues"].append(
            "Unmet block_claim requirements: " + ", ".join(unmet_requirements)
        )

    claim_guard_blockers = _claim_guard_blockers(
        claim,
        revision_records,
        analysis_requirements or [],
    )
    if claim_guard_blockers:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check.setdefault("reason_codes", []).append("claim_guard_blocked")
        check["issues"].append(
            "Claim is blocked by deterministic requirement guard: "
            + ", ".join(claim_guard_blockers)
        )

    if (
        not _is_missing(evidence.get("limitations"))
        and isinstance(claim, dict)
        and claim.get("answer_has_limitation") is False
        and check["status"] != "failed"
    ):
        check["status"] = "downgraded"
        check["strength"] = "likely"
        check.setdefault("reason_codes", []).append("missing_limitation")
        check["issues"].append("Final answer is missing a limitation disclosure required by its evidence")

    if (
        isinstance(claim, dict)
        and str(claim.get("claim_type") or "") in {
            "association", "causal", "prediction", "recommendation",
        }
        and str(evidence.get("confidence") or "").strip().lower() in {
            "low", "weak", "uncertain", "medium_low",
        }
        and claim.get("answer_has_exploratory_label") is False
        and check["status"] != "failed"
    ):
        check["status"] = "downgraded"
        check["strength"] = "likely"
        check.setdefault("reason_codes", []).append("missing_exploratory_label")
        check["issues"].append("Low-confidence material claim is missing an exploratory label")

    missing = [field for field in REQUIRED_EVIDENCE_FIELDS if _is_missing(evidence.get(field))]
    if missing:
        _mark_downgraded(
            check,
            f"Evidence record is missing required fields: {', '.join(missing)}",
        )

    if _uses_causal_language(text):
        identification = _identification_value(evidence, "identification_status")
        if isinstance(identification, dict) or _is_causal_method(evidence.get("method")):
            identification_issues = _causal_identification_issues(evidence)
            if identification_issues:
                check["status"] = "failed"
                check["strength"] = "unsupported"
                check["issues"].extend(identification_issues)
        else:
            _mark_downgraded(
                check,
                "Claim uses causal language, but evidence method is not causal, ab_test, experiment, did, or difference_in_differences"
            )
    else:
        identification = _identification_value(evidence, "identification_status")
        if (
            isinstance(identification, dict)
            and str(identification.get("allowed_claim_class") or "").strip().lower()
            in {"association", "descriptive", "descriptive_comparison"}
            and _is_missing(_identification_value(evidence, "alternative_explanations"))
        ):
            _mark_downgraded(
                check,
                "A non-identifying observational result must disclose alternative_explanations."
            )

    method = str(evidence.get("method") or "").strip().lower()
    normalized_method = re.sub(r"[^a-z0-9]+", " ", method).strip()
    has_inferential_support = any(
        not _is_missing(evidence.get(field_name))
        for field_name in (
            "statistical_support",
            "confidence_interval",
            "p_value",
            "significance",
            "effect_size",
            "effect_estimate",
        )
    )
    is_inferential_method = (
        method in INFERENTIAL_METHODS
        or any(pattern in normalized_method for pattern in INFERENTIAL_METHOD_PATTERNS)
        or has_inferential_support
    )
    provenance_level = str(evidence.get("verification_level") or "").strip().lower()
    asserted_confidence = str(
        evidence.get("original_confidence") or evidence.get("confidence") or ""
    ).strip().lower()
    is_high_confidence_inference = (
        asserted_confidence == "high"
        and (is_inferential_method or _uses_causal_language(text))
    )
    if is_high_confidence_inference and provenance_level not in {
        "structured_checked",
        "independently_recomputed",
    }:
        _mark_downgraded(
            check,
            f"High-confidence inference is not supported by verified provenance: {provenance_level or 'unbound'}"
        )

    cleaning_issues = _risky_cleaning_issues(evidence, cleaning_logs)
    if cleaning_issues:
        _mark_downgraded(check, cleaning_issues)

    if exploratory_measurement_candidate and check["status"] != "failed":
        check["status"] = "downgraded"
        check["strength"] = "exploratory"
        check.setdefault("reason_codes", []).append(
            "measurement_identity_missing"
        )
        check["issues"].append(
            "Exact current computation is informational until the claim "
            "includes a measurement-grain identity."
        )
    if (
        measurement_binding_mode == "shadow"
        and measurement_v2_exact_match
        and check["status"] != "failed"
    ):
        check["status"] = "downgraded"
        check["strength"] = "exploratory"
        check.setdefault("reason_codes", []).append(
            "measurement_identity_missing"
        )
        check["issues"].append(
            "Shadow mode observed an exact measurement identity without "
            "authorizing the claim."
        )
    check["_measurement_v2_exact_match"] = measurement_v2_exact_match
    check["_measurement_v2_authorized"] = bool(
        measurement_v2_exact_match
        and measurement_binding_mode in {"soft", "enforced"}
        and check["status"] != "failed"
    )
    check["_measurement_checked"] = selected_measurement is not None
    return _finalize_check(check)


def _overall_status(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "failed" for check in checks):
        return "fail"
    if any(check["status"] == "downgraded" for check in checks):
        return "pass_with_downgrades"
    return "pass"


def _normalize_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        return [value]
    if hasattr(value, "tolist"):
        try:
            converted = value.tolist()
        except (TypeError, ValueError):
            return [value]
        if isinstance(converted, list):
            return converted
        return [converted]
    return [value]


def verify_analysis_claims(
    claims: list[Any],
    evidence_records: list[dict[str, Any]],
    route_proposals: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
    current_plan_id: str = "",
    current_dataset_versions: list[str] | set[str] | tuple[str, ...] | None = None,
    sessions_root: Any = None,
    current_session_id: str = "",
    current_plan_digest: str = "",
    current_step_digests: dict[str, str] | None = None,
    analysis_requirements: list[dict[str, Any]] | None = None,
    require_explicit_evidence_ids: bool = False,
    strict_claim_semantics: bool = False,
    *,
    measurement_binding_mode: str = "enforced",
) -> dict[str, Any]:
    """Verify claims against recorded evidence, route metadata, and cleaning risk."""

    if measurement_binding_mode not in {"shadow", "soft", "enforced"}:
        raise ValueError("measurement_binding_mode must be shadow, soft, or enforced")
    safe_claims = _normalize_items(claims)
    safe_evidence = [record for record in _normalize_items(evidence_records) if isinstance(record, dict)]
    safe_routes = [route for route in _normalize_items(route_proposals) if isinstance(route, dict)]
    safe_cleaning_logs = [log for log in _normalize_items(cleaning_logs) if isinstance(log, dict)]
    safe_dataset_versions = (
        None
        if current_dataset_versions is None
        else {str(item) for item in _normalize_items(current_dataset_versions) if str(item or "")}
    )

    claim_checks = [
        _check_claim(
            claim,
            index,
            safe_evidence,
            safe_cleaning_logs,
            str(current_plan_id or ""),
            safe_dataset_versions,
            sessions_root,
            str(current_session_id or ""),
            str(current_plan_digest or ""),
            {
                str(key): str(value)
                for key, value in (current_step_digests or {}).items()
                if str(key) and str(value)
            },
            [
                item
                for item in _normalize_items(analysis_requirements)
                if isinstance(item, dict)
            ],
            bool(require_explicit_evidence_ids),
            bool(strict_claim_semantics),
            measurement_binding_mode,
        )
        for index, claim in enumerate(safe_claims)
    ]
    measurement_codes = {
        "measurement_identity_missing",
        "measurement_marker_invalid",
        "measurement_not_found",
        "measurement_metric_mismatch",
        "measurement_claim_key_mismatch",
        "measurement_scope_mismatch",
        "measurement_dataset_version_mismatch",
        "measurement_ambiguous",
    }
    semantic_measurement_contradiction_codes = {
        "numeric_mismatch",
        "unit_mismatch",
        "direction_mismatch",
        "time_scope_mismatch",
        "population_scope_mismatch",
        "confidence_mismatch",
        "verification_level_overclaim",
        "causal_claim_not_identified",
    }
    measurement_checked = [
        bool(check.pop("_measurement_checked", False))
        for check in claim_checks
    ]
    measurement_binding_diagnostics = {
        "mode": measurement_binding_mode,
        "v2_exact_match_count": sum(
            bool(check.pop("_measurement_v2_exact_match", False))
            for check in claim_checks
        ),
        "v2_authorized_count": sum(
            bool(check.pop("_measurement_v2_authorized", False))
            for check in claim_checks
        ),
        "downgrade_count": sum(
            check.get("status") == "downgraded"
            and "measurement_identity_missing" in check.get("reason_codes", [])
            for check in claim_checks
        ),
        "contradiction_count": sum(
            check.get("status") == "failed"
            and bool(
                set(check.get("reason_codes") or [])
                & (measurement_codes - {"measurement_identity_missing"})
                or (
                    measurement_checked[index]
                    and set(check.get("reason_codes") or [])
                    & semantic_measurement_contradiction_codes
                )
            )
            for index, check in enumerate(claim_checks)
        ),
    }
    route_proposal_ids = [str(route["id"]) for route in safe_routes if route.get("id")]
    payload_for_id = {
        "claims": safe_claims,
        "evidence_records": safe_evidence,
        "route_proposal_ids": route_proposal_ids,
        "cleaning_logs": safe_cleaning_logs,
        "claim_checks": claim_checks,
        "analysis_requirement_ids": [
            str(item.get("id") or "")
            for item in _normalize_items(analysis_requirements)
            if isinstance(item, dict) and str(item.get("id") or "")
        ],
        "require_explicit_evidence_ids": bool(require_explicit_evidence_ids),
        "strict_claim_semantics": bool(strict_claim_semantics),
        "measurement_binding_diagnostics": measurement_binding_diagnostics,
    }
    if current_plan_id:
        payload_for_id["current_plan_id"] = str(current_plan_id)
    if current_plan_digest:
        payload_for_id["current_plan_digest"] = str(current_plan_digest)
    if current_step_digests:
        payload_for_id["current_step_digests"] = {
            str(key): str(value)
            for key, value in current_step_digests.items()
            if str(key) and str(value)
        }
    if safe_dataset_versions is not None:
        payload_for_id["current_dataset_versions"] = sorted(safe_dataset_versions)

    return {
        "id": _stable_id(payload_for_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "claim_checks": claim_checks,
        "route_proposal_ids": route_proposal_ids,
        "overall_status": _overall_status(claim_checks),
        "measurement_binding_diagnostics": measurement_binding_diagnostics,
    }
