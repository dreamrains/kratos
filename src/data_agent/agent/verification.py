"""Deterministic verification checks for analysis claims."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from data_agent.agent.evidence_compatibility import compare_measurements
from data_agent.agent.evidence_contracts import validate_measurement


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
    if isinstance(claim, dict):
        return str(claim.get("evidence_id") or "")
    return ""


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
) -> dict[str, Any]:
    text = _claim_text(claim)
    evidence: dict[str, Any] | None = None

    comparison_records, comparison_issues = _comparison_issues(
        claim,
        evidence_records,
        current_plan_id,
    )
    if comparison_records:
        evidence = comparison_records[0]

    explicit_evidence_id = _claim_evidence_id(claim)
    if explicit_evidence_id:
        explicit_matches = _find_evidence_by_id(explicit_evidence_id, evidence_records)
        current_matches = [
            record
            for record in explicit_matches
            if _record_matches_current_plan(record, current_plan_id)
        ]
        if current_matches:
            evidence = current_matches[0]
        elif explicit_matches:
            evidence = None
            comparison_issues.append(
                f"Evidence {explicit_evidence_id} is outside the current plan and cannot support this claim"
            )
        else:
            evidence = None
            if current_plan_id:
                comparison_issues.append(
                    f"Explicit evidence {explicit_evidence_id} was not found in the current plan"
                )
            else:
                comparison_issues.append(f"Explicit evidence {explicit_evidence_id} was not found")

    if evidence is None and not comparison_issues:
        evidence = _find_evidence(claim, _current_plan_evidence(evidence_records, current_plan_id))

    check = {
        "claim_id": _claim_id(claim, index),
        "claim": text,
        "evidence_id": evidence.get("id") if evidence else None,
        "status": "passed",
        "strength": "confirmed" if str((evidence or {}).get("confidence") or "").lower() == "high" else "likely",
        "issues": [],
    }

    if comparison_issues:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check["issues"].extend(comparison_issues)
        return check

    if evidence is None:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check["issues"].append("No evidence record supports this claim")
        return check

    revision_issues: list[str] = []
    revision_records = comparison_records or [evidence]
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
        return check

    if current_dataset_versions is not None:
        evidence_versions = {
            str(version_id)
            for ref in _normalize_items(evidence.get("computation_refs"))
            if isinstance(ref, dict)
            for version_id in _normalize_items(ref.get("dataset_versions"))
            if str(version_id or "")
        }
        stale_versions = evidence_versions - current_dataset_versions
        if stale_versions:
            check["status"] = "failed"
            check["strength"] = "unsupported"
            check["issues"].append(
                "Evidence is bound to a stale dataset version: " + ", ".join(sorted(stale_versions))
            )
            return check

    if sessions_root is not None:
        from data_agent.agent.evidence_contracts import hydrate_computation_ref

        for ref in _normalize_items(evidence.get("computation_refs")):
            if not isinstance(ref, dict):
                check["status"] = "failed"
                check["strength"] = "unsupported"
                check["issues"].append("Evidence computation artifact integrity check failed: invalid ref")
                return check
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
                return check

    missing = [field for field in REQUIRED_EVIDENCE_FIELDS if _is_missing(evidence.get(field))]
    if missing:
        check["status"] = "downgraded"
        check["strength"] = "likely"
        check["issues"].append(f"Evidence record is missing required fields: {', '.join(missing)}")

    if _uses_causal_language(text):
        identification = _identification_value(evidence, "identification_status")
        if isinstance(identification, dict) or _is_causal_method(evidence.get("method")):
            identification_issues = _causal_identification_issues(evidence)
            if identification_issues:
                check["status"] = "failed"
                check["strength"] = "unsupported"
                check["issues"].extend(identification_issues)
        else:
            check["status"] = "downgraded"
            check["strength"] = "likely"
            check["issues"].append(
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
            check["status"] = "downgraded"
            check["strength"] = "likely"
            check["issues"].append(
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
        check["status"] = "downgraded"
        check["strength"] = "likely"
        check["issues"].append(
            f"High-confidence inference is not supported by verified provenance: {provenance_level or 'unbound'}"
        )

    cleaning_issues = _risky_cleaning_issues(evidence, cleaning_logs)
    if cleaning_issues:
        check["status"] = "downgraded"
        check["strength"] = "likely"
        check["issues"].extend(cleaning_issues)

    return check


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
) -> dict[str, Any]:
    """Verify claims against recorded evidence, route metadata, and cleaning risk."""

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
        )
        for index, claim in enumerate(safe_claims)
    ]
    route_proposal_ids = [str(route["id"]) for route in safe_routes if route.get("id")]
    payload_for_id = {
        "claims": safe_claims,
        "evidence_records": safe_evidence,
        "route_proposal_ids": route_proposal_ids,
        "cleaning_logs": safe_cleaning_logs,
        "claim_checks": claim_checks,
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
    }
