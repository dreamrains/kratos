"""Runtime glue for trustworthy analysis workflow integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data
from data_agent.agent.verification import verify_analysis_claims
from data_agent.utils.logging import get_logger


logger = get_logger("trust_workflow_runtime")


def refine_turn_intent_with_state(user_input: str, intent: TurnIntent, state: Any) -> TurnIntent:
    """Refine a turn intent using trustworthy state refs without breaking the loop."""

    try:
        return refine_intent_with_data(
            user_input=user_input,
            intent=intent,
            dataset_contracts=_list_attr(state, "dataset_contracts"),
            route_proposals=_list_attr(state, "route_proposals"),
        )
    except Exception as exc:
        logger.warning(
            "Trust workflow intent refinement skipped",
            extra={"extra_data": {"error": str(exc)}},
        )
        return intent


def maybe_verify_turn_claims(user_input: str, state: Any, *, force: bool = False) -> dict[str, Any] | None:
    """Create one compact verification report for recorded evidence claims."""

    try:
        current_plan_id = _current_analysis_plan_id(state)
        evidence_records = _current_plan_records(
            _list_attr(state, "evidence_records"),
            current_plan_id,
        )
        claims = _extract_claims(evidence_records)
        if not claims:
            return None

        signature = _evidence_signature(state, evidence_records)
        fingerprint = _evidence_fingerprint(state, evidence_records)
        if not force and _promote_verification_identity(state, signature, fingerprint):
            return None

        report = verify_analysis_claims(
            claims=claims,
            evidence_records=evidence_records,
            route_proposals=_list_attr(state, "route_proposals"),
            cleaning_logs=_list_attr(state, "cleaning_logs"),
            current_plan_id=current_plan_id,
        )
        ref = _compact_verification_ref(report, signature, fingerprint)
        add_ref = getattr(state, "add_verification_report_ref", None)
        if callable(add_ref):
            stored = add_ref(ref)
        else:
            reports = getattr(state, "verification_reports", None)
            if isinstance(reports, list):
                reports.append(ref)
            stored = ref
        save = getattr(state, "save", None)
        if callable(save):
            save()
        return stored
    except Exception as exc:
        logger.warning(
            "Trust workflow verification skipped",
            extra={"extra_data": {"error": str(exc), "user_input": (user_input or "")[:200]}},
        )
        return None


def maybe_create_hypothesis_set(user_input: str, intent: TurnIntent, state: Any) -> dict[str, Any] | None:
    """Create one compact hypothesis set for a runnable analysis route."""

    try:
        from data_agent.agent.analysis_entry import decide_analysis_entry
        from data_agent.agent.hypotheses import (
            build_hypothesis_set,
            hydrate_hypothesis_refs,
            persist_hypothesis_set,
            update_hypotheses_from_evidence,
        )

        decision = decide_analysis_entry(user_input, intent, state)
        if decision.get("decision") not in {"direct_analysis", "exploratory_only", "request_data"}:
            return None

        evidence_records = _list_attr(state, "evidence_records")
        hypothesis_set = build_hypothesis_set(user_input, decision, state)
        dataset = str(hypothesis_set.get("dataset") or "")
        route = str(hypothesis_set.get("route") or "")
        existing_ref = _find_hypothesis_set_ref(state, dataset, route)
        if existing_ref and not evidence_records:
            return None
        if existing_ref:
            hydrated = hydrate_hypothesis_refs([existing_ref])
            if not hydrated:
                return None
            hypothesis_set = update_hypotheses_from_evidence(hydrated[0], evidence_records)
        elif evidence_records:
            hypothesis_set = update_hypotheses_from_evidence(hypothesis_set, evidence_records)

        ref = persist_hypothesis_set(str(getattr(state, "session_id", "")), hypothesis_set)
        if existing_ref and existing_ref.get("created_at"):
            ref["created_at"] = existing_ref["created_at"]
        add_ref = getattr(state, "add_hypothesis_set_ref", None)
        if callable(add_ref):
            stored = add_ref(ref)
        else:
            refs = getattr(state, "hypothesis_sets", None)
            if isinstance(refs, list):
                refs.append(ref)
            stored = ref

        save = getattr(state, "save", None)
        if callable(save):
            save()
        return stored
    except Exception as exc:
        logger.warning(
            "Hypothesis set creation skipped",
            extra={"extra_data": {"error": str(exc), "user_input": (user_input or "")[:200]}},
        )
        return None


def _find_hypothesis_set_ref(state: Any, dataset: str, route: str) -> dict[str, Any] | None:
    for ref in _list_attr(state, "hypothesis_sets"):
        if str(ref.get("dataset") or "") == dataset and str(ref.get("route") or "") == route:
            return ref
    return None


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _extract_claims(evidence_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for record in evidence_records:
        claim = record.get("claim")
        if isinstance(claim, str) and claim.strip():
            structured_claim = dict(record)
            structured_claim["claim"] = claim.strip()
            claims.append(structured_claim)
    return claims


def _current_plan_records(
    evidence_records: list[dict[str, Any]],
    current_plan_id: str,
) -> list[dict[str, Any]]:
    if not current_plan_id:
        return evidence_records
    return [
        record
        for record in evidence_records
        if str(record.get("plan_id") or "").strip() == current_plan_id
    ]


def _evidence_signature(state: Any, evidence_records: list[dict[str, Any]]) -> str:
    evidence_ids = [str(record.get("id") or index) for index, record in enumerate(evidence_records)]
    route_ids = [str(route.get("id")) for route in _list_attr(state, "route_proposals") if route.get("id")]
    cleaning_ids = [str(log.get("id")) for log in _list_attr(state, "cleaning_logs") if log.get("id")]
    signature = "|".join(evidence_ids) + "|routes:" + ",".join(route_ids) + "|cleaning:" + ",".join(cleaning_ids)
    current_plan_id = _current_analysis_plan_id(state)
    if current_plan_id:
        signature += "|plan:" + current_plan_id
    return signature


def _evidence_fingerprint(state: Any, evidence_records: list[dict[str, Any]]) -> str:
    payload = {
        "evidence_records": evidence_records,
        "route_proposals": _list_attr(state, "route_proposals"),
        "cleaning_logs": _list_attr(state, "cleaning_logs"),
        "current_plan_id": _current_analysis_plan_id(state),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _current_analysis_plan_id(state: Any) -> str:
    for attr_name in ("analysis_plan", "analysis_spec"):
        plan = getattr(state, attr_name, None)
        if isinstance(plan, dict) and plan.get("id"):
            return str(plan.get("id") or "").strip()
    return ""


def _promote_verification_identity(state: Any, signature: str, fingerprint: str) -> bool:
    reports = getattr(state, "verification_reports", None)
    if not isinstance(reports, list):
        return False

    for index, report in enumerate(reports):
        if not isinstance(report, dict):
            continue
        if (
            report.get("evidence_signature") == signature
            and report.get("evidence_fingerprint") == fingerprint
        ):
            if index != len(reports) - 1:
                reports.append(reports.pop(index))
                save = getattr(state, "save", None)
                if callable(save):
                    save()
            return True
    return False


def _compact_verification_ref(report: dict[str, Any], signature: str, fingerprint: str) -> dict[str, Any]:
    checks = report.get("claim_checks") if isinstance(report, dict) else []
    if not isinstance(checks, list):
        checks = []
    failed_count = sum(1 for check in checks if isinstance(check, dict) and check.get("status") == "failed")
    downgraded_count = sum(1 for check in checks if isinstance(check, dict) and check.get("status") == "downgraded")
    return {
        "id": "verify_" + str(report.get("id") or "")[:16],
        "source_report_id": report.get("id"),
        "overall_status": report.get("overall_status", "unknown"),
        "claim_count": len(checks),
        "failed_count": failed_count,
        "downgraded_count": downgraded_count,
        "evidence_signature": signature,
        "evidence_fingerprint": fingerprint,
        "route_proposal_ids": list(report.get("route_proposal_ids") or []),
    }
