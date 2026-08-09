"""Runtime glue for trustworthy analysis workflow integration."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from data_agent.agent.answer_quality import (
    build_final_answer_audit,
    validate_final_answer_audit_structure,
)
from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data
from data_agent.agent.verification import verify_analysis_claims
from data_agent.config import get_config
from data_agent.utils.logging import get_logger


logger = get_logger("trust_workflow_runtime")


def audit_final_answer_draft(
    answer_text: str,
    state: Any,
    *,
    llm_critique: dict[str, Any] | None = None,
    evidence_aliases: tuple[tuple[str, str, str, str], ...] = (),
) -> dict[str, Any]:
    """Persist a deterministic audit of the actual synthesis draft."""

    from data_agent.agent.evidence_contracts import expand_evidence_alias_markers

    answer_text = expand_evidence_alias_markers(answer_text, evidence_aliases)

    current_plan_id = _current_analysis_plan_id(state)
    evidence_records = _current_plan_records(
        _list_attr(state, "evidence_records"),
        current_plan_id,
    )
    current_plan_digest, current_step_digests = _current_plan_semantic_identity(state)
    sessions_root = _sessions_root()
    current_session_id = str(getattr(state, "session_id", "") or "")
    measurement_binding_mode = get_config().measurement_evidence_binding_mode
    audit = build_final_answer_audit(
        answer_text,
        evidence_records=evidence_records,
        route_proposals=_list_attr(state, "route_proposals"),
        cleaning_logs=_list_attr(state, "cleaning_logs"),
        current_plan_id=current_plan_id,
        current_dataset_versions=_active_dataset_versions(),
        sessions_root=sessions_root,
        current_session_id=current_session_id,
        current_plan_digest=current_plan_digest,
        current_step_digests=current_step_digests,
        analysis_requirements=_current_analysis_requirements(state),
        llm_critique=llm_critique,
        measurement_binding_mode=measurement_binding_mode,
    )
    path = _persist_final_answer_audit(
        audit,
        sessions_root=sessions_root,
        session_id=current_session_id,
    )
    checks = [
        item for item in audit.get("claim_checks") or [] if isinstance(item, dict)
    ]
    status = str(audit.get("status") or "blocked")
    ref = {
        "contract_version": "final_answer_audit.v1",
        "id": audit.get("id"),
        "created_at": audit.get("created_at"),
        "status": status,
        "overall_status": {
            "blocked": "fail",
            "revise": "pass_with_downgrades",
            "pass": "pass",
        }.get(status, "fail"),
        "claim_count": len(checks),
        "blocked_count": sum(item.get("status") == "failed" for item in checks),
        "revise_count": sum(item.get("status") == "downgraded" for item in checks),
        "draft_digest": audit.get("draft_digest"),
        "artifact_path": str(path),
        "artifact_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
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


def hydrate_final_answer_audit_ref(ref: dict[str, Any]) -> dict[str, Any] | None:
    path = Path(str(ref.get("artifact_path") or ""))
    if ref.get("contract_version") != "final_answer_audit.v1" or not path.is_file():
        return None
    try:
        artifact_bytes = path.read_bytes()
        if hashlib.sha256(artifact_bytes).hexdigest() != str(ref.get("artifact_digest") or ""):
            return None
        audit = json.loads(artifact_bytes.decode("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(audit, dict)
        or audit.get("id") != ref.get("id")
        or not validate_final_answer_audit_structure(audit)
    ):
        return None
    return audit


def _persist_final_answer_audit(
    audit: dict[str, Any],
    *,
    sessions_root: Any,
    session_id: str,
) -> Path:
    if sessions_root is None:
        raise ValueError("sessions_root is required to persist final_answer_audit.v1")
    safe_session_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id).strip("._") or "session"
    safe_audit_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(audit.get("id") or "audit"))
    path = Path(sessions_root) / safe_session_id / "tool_outputs" / f"{safe_audit_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _current_analysis_requirements(state: Any) -> list[dict[str, Any]]:
    plan = getattr(state, "analysis_plan", None)
    if not isinstance(plan, dict):
        return []
    grouped = plan.get("analysis_requirements")
    if not isinstance(grouped, dict):
        return []
    return [
        item
        for group in grouped.values()
        if isinstance(group, list)
        for item in group
        if isinstance(item, dict)
    ]


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
        current_dataset_versions = _active_dataset_versions()
        sessions_root = _sessions_root()
        current_session_id = str(getattr(state, "session_id", "") or "")
        current_plan_digest, current_step_digests = _current_plan_semantic_identity(state)
        fingerprint = _evidence_fingerprint(
            state,
            evidence_records,
            current_dataset_versions=current_dataset_versions,
            sessions_root=sessions_root,
            current_session_id=current_session_id,
            current_plan_digest=current_plan_digest,
            current_step_digests=current_step_digests,
        )
        if not force and _promote_verification_identity(state, signature, fingerprint):
            return None

        report = verify_analysis_claims(
            claims=claims,
            evidence_records=evidence_records,
            route_proposals=_list_attr(state, "route_proposals"),
            cleaning_logs=_list_attr(state, "cleaning_logs"),
            current_plan_id=current_plan_id,
            current_dataset_versions=current_dataset_versions,
            sessions_root=sessions_root,
            current_session_id=current_session_id,
            current_plan_digest=current_plan_digest,
            current_step_digests=current_step_digests,
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


def _active_dataset_versions() -> list[str] | None:
    from data_agent.agent.context import authoritative_dataset_versions

    return authoritative_dataset_versions()


def _sessions_root():
    try:
        from data_agent.config import get_config

        return get_config().sessions_resolved
    except Exception:
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


def _computation_integrity_identities(
    evidence_records: list[dict[str, Any]],
    *,
    sessions_root: Any,
    current_session_id: str,
) -> list[dict[str, str]]:
    identities: list[dict[str, str]] = []
    try:
        from data_agent.agent.evidence_contracts import hydrate_computation_ref
    except Exception:
        hydrate_computation_ref = None
    for record in evidence_records:
        refs = record.get("computation_refs") if isinstance(record, dict) else None
        for ref in refs if isinstance(refs, list) else []:
            if not isinstance(ref, dict):
                continue
            status = "unavailable"
            if hydrate_computation_ref is not None and sessions_root is not None:
                try:
                    hydrate_computation_ref(
                        ref,
                        sessions_root=sessions_root,
                        current_session_id=current_session_id,
                    )
                    status = "valid"
                except Exception as exc:
                    status = f"invalid:{type(exc).__name__}:{exc}"
            identities.append({
                "evidence_id": str(record.get("id") or ""),
                "turn_id": str(ref.get("turn_id") or ""),
                "tool_call_id": str(ref.get("tool_call_id") or ""),
                "output_digest": str(ref.get("output_digest") or ""),
                "integrity": status,
            })
    return identities


def _evidence_fingerprint(
    state: Any,
    evidence_records: list[dict[str, Any]],
    *,
    current_dataset_versions: list[str] | None = None,
    sessions_root: Any = None,
    current_session_id: str = "",
    current_plan_digest: str = "",
    current_step_digests: dict[str, str] | None = None,
) -> str:
    payload = {
        "evidence_records": evidence_records,
        "route_proposals": _list_attr(state, "route_proposals"),
        "cleaning_logs": _list_attr(state, "cleaning_logs"),
        "current_plan_id": _current_analysis_plan_id(state),
        "current_plan_digest": current_plan_digest,
        "current_step_digests": current_step_digests or {},
        "current_dataset_versions": current_dataset_versions,
        "computation_integrity": _computation_integrity_identities(
            evidence_records,
            sessions_root=sessions_root,
            current_session_id=current_session_id,
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _current_plan_semantic_identity(state: Any) -> tuple[str, dict[str, str]]:
    plan = getattr(state, "analysis_plan", None)
    if not isinstance(plan, dict) or not plan.get("id"):
        return "", {}
    from data_agent.agent.evidence_contracts import (
        analysis_plan_semantic_digest,
        analysis_step_semantic_digest,
    )

    step_digests = {
        str(step.get("step_id")): analysis_step_semantic_digest(step)
        for step in plan.get("method_plan") or []
        if isinstance(step, dict) and str(step.get("step_id") or "")
    }
    return analysis_plan_semantic_digest(plan), step_digests


def _current_analysis_plan_id(state: Any) -> str:
    plan = getattr(state, "analysis_plan", None)
    if isinstance(plan, dict):
        plan_id = str(plan.get("id") or "").strip()
        if plan_id:
            return plan_id
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
