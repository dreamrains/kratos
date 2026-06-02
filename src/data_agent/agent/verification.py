"""Deterministic verification checks for analysis claims."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


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
CAUSAL_METHODS = {"causal", "ab_test", "experiment", "did", "difference_in_differences"}
RISKY_CLEANING_DECISIONS = {"needs_confirmation", "blocked"}


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


def _claim_id(claim: Any, index: int) -> str:
    if isinstance(claim, dict) and claim.get("id"):
        return str(claim["id"])
    return f"claim_{index + 1}"


def _is_missing(value: Any) -> bool:
    return value in (None, "", [], {})


def _find_evidence(claim_text: str, evidence_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = claim_text.strip().lower()
    for record in evidence_records:
        if str(record.get("claim") or "").strip().lower() == normalized:
            return record
    return None


def _uses_causal_language(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in CAUSAL_WORDS)


def _is_causal_method(method: Any) -> bool:
    normalized = str(method or "").strip().lower()
    return normalized in CAUSAL_METHODS


def _risky_cleaning_issues(evidence: dict[str, Any], cleaning_logs: list[dict[str, Any]]) -> list[str]:
    evidence_dataset = str(evidence.get("dataset") or "")
    issues: list[str] = []
    for log in cleaning_logs:
        log_dataset = str(log.get("dataset") or "")
        if log_dataset and evidence_dataset and log_dataset != evidence_dataset:
            continue
        for decision in log.get("decisions") or []:
            decision_type = str(decision.get("decision_type") or "")
            if decision_type in RISKY_CLEANING_DECISIONS:
                column = str(decision.get("column") or "unknown column")
                issues.append(
                    f"Cleaning decision requires confirmation: {decision_type} on {column}"
                )
    return issues


def _check_claim(
    claim: Any,
    index: int,
    evidence_records: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    text = _claim_text(claim)
    evidence = _find_evidence(text, evidence_records)
    check = {
        "claim_id": _claim_id(claim, index),
        "claim": text,
        "evidence_id": evidence.get("id") if evidence else None,
        "status": "passed",
        "strength": "supported",
        "issues": [],
    }

    if evidence is None:
        check["status"] = "failed"
        check["strength"] = "unsupported"
        check["issues"].append("No evidence record supports this claim")
        return check

    missing = [field for field in REQUIRED_EVIDENCE_FIELDS if _is_missing(evidence.get(field))]
    if missing:
        check["status"] = "downgraded"
        check["strength"] = "likely"
        check["issues"].append(f"Evidence record is missing required fields: {', '.join(missing)}")

    if _uses_causal_language(text) and not _is_causal_method(evidence.get("method")):
        check["status"] = "downgraded"
        check["strength"] = "likely"
        check["issues"].append(
            "Claim uses causal language, but evidence method is not causal, ab_test, experiment, did, or difference_in_differences"
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


def verify_analysis_claims(
    claims: list[Any],
    evidence_records: list[dict[str, Any]],
    route_proposals: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify claims against recorded evidence, route metadata, and cleaning risk."""

    safe_claims = list(claims or [])
    safe_evidence = [record for record in evidence_records or [] if isinstance(record, dict)]
    safe_routes = [route for route in route_proposals or [] if isinstance(route, dict)]
    safe_cleaning_logs = [log for log in cleaning_logs or [] if isinstance(log, dict)]

    claim_checks = [
        _check_claim(claim, index, safe_evidence, safe_cleaning_logs)
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

    return {
        "id": _stable_id(payload_for_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "claim_checks": claim_checks,
        "route_proposal_ids": route_proposal_ids,
        "overall_status": _overall_status(claim_checks),
    }
