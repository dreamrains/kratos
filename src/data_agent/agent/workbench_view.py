"""User-value Workbench projections for multifile analysis."""

from __future__ import annotations

from typing import Any

from data_agent.agent.data_understanding import build_user_data_brief
from data_agent.agent.multi_file_scope import build_analysis_scope_plan
from data_agent.agent.route_capabilities import build_route_capabilities


def build_workbench_view(state: Any) -> dict[str, Any]:
    """Build the complete Workbench contract: four primary areas and details."""
    if state is None:
        return {
            "multifile_analysis": build_multifile_workbench_view(None, capabilities={}),
            "details": _details_section(None, {}, {}),
        }

    capabilities = build_route_capabilities(state)
    goal = _text(getattr(state, "goal", ""))
    scope_plan = build_analysis_scope_plan(state, user_goal=goal)
    confirmation = capabilities.get("confirmation_gate")
    if not isinstance(confirmation, dict):
        confirmation = {}
    return {
        "multifile_analysis": build_multifile_workbench_view(
            state,
            capabilities=capabilities,
        ),
        "details": _details_section(state, scope_plan, confirmation),
    }


def build_multifile_workbench_view(
    state: Any,
    *,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only four-section Workbench model from existing state."""

    return {
        "data_understanding": _data_understanding_section(state),
        "relationships": _relationship_section(state),
        "analysis_directions": _analysis_direction_section(state, capabilities),
        "answer_coverage": _answer_coverage_section(state),
    }


def _data_understanding_section(state: Any) -> dict[str, Any]:
    for bundle in reversed(_list_attr(state, "data_understanding_bundles")):
        try:
            brief = build_user_data_brief(bundle)
        except Exception:
            continue
        if brief.get("bundle_id"):
            return brief
    return {
        "bundle_id": "",
        "fingerprint": "",
        "datasets": [],
        "relationships": [],
        "quality_findings": [],
        "answerable_questions": [],
        "unanswerable_questions": [],
        "recommended_paths": [],
        "needed_confirmations": [],
        "analysis_constraints": [],
    }


def _relationship_section(state: Any) -> list[dict[str, Any]]:
    relationships = []
    for item in _list_attr(state, "file_relationships"):
        relationship_id = _text(item.get("relationship_id") or item.get("id"))
        relationships.append({
            "id": relationship_id,
            "status": _text(item.get("status") or item.get("relationship_status")),
            "file_ids": _text_list(item.get("file_ids")),
            "requires_confirmation": bool(item.get("requires_confirmation")),
            "confirmation_type": _text(item.get("confirmation_type")),
            "value": _text(item.get("value") or item.get("reason")),
            "risk": _text(item.get("risk") or item.get("risk_level")),
            "evidence": _text_list(item.get("evidence"))[:4],
            "uncertainties": _text_list(item.get("uncertainties"))[:4],
            "diagnostic_only": True,
        })
    return relationships


def _analysis_direction_section(
    state: Any,
    capabilities: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if capabilities is None:
        capabilities = build_route_capabilities(state)
    directions = []
    for item in _list_items(capabilities.get("executable")) + _list_items(capabilities.get("exploratory")):
        direction = _text(item.get("direction") or item.get("route"))
        if not direction:
            continue
        directions.append({
            "source": "route_capabilities",
            "id": _text(item.get("id")),
            "dataset": _text(item.get("dataset")),
            "direction": direction,
            "label": _text(item.get("label")) or direction,
            "reason": _text(item.get("reason")) or "; ".join(_text_list(item.get("support_reasons"))),
            "support_status": _text(item.get("support_status")),
            "evidence_requirements": _text_list(item.get("evidence_requirements")),
            "risk_fields": _text_list(item.get("risk_fields")),
            "auto_submit": False,
        })
    return directions


def _answer_coverage_section(state: Any) -> dict[str, Any]:
    evidence = _list_attr(state, "evidence_records")
    verification_reports = _list_attr(state, "verification_reports")
    latest_verification = verification_reports[-1] if verification_reports else {}
    return {
        "evidence_count": len(evidence),
        "verified_claim_count": _int_value(
            latest_verification.get("claim_count"),
            fallback=len(evidence),
        ),
        "failed_claim_count": _int_value(latest_verification.get("failed_count")),
        "status": _text(
            latest_verification.get("overall_status")
            or latest_verification.get("status")
            or ("has_evidence" if evidence else "not_started")
        ),
        "covered_claims": [
            {
                "claim": _text(item.get("claim")),
                "confidence": _text(item.get("confidence")),
                "summary": _text(item.get("result_summary")),
            }
            for item in evidence[:6]
            if _text(item.get("claim"))
        ],
        "limitations": _flatten_limitations(evidence),
    }


def _details_section(
    state: Any,
    scope_plan: dict[str, Any],
    confirmation: dict[str, Any],
) -> dict[str, Any]:
    file_decisions = _list_items(scope_plan.get("file_decisions"))
    verification_reports = _list_attr(state, "verification_reports")
    latest_verification = verification_reports[-1] if verification_reports else {}
    return {
        "scope": {
            "goal": _text(scope_plan.get("goal")) or _text(getattr(state, "goal", "")),
            "status": _text(scope_plan.get("scope_status")) or "ready",
            "files": [
                {
                    "file_id": _text(item.get("file_id")),
                    "dataset": _text(item.get("dataset")),
                    "filename": _text(item.get("filename")),
                    "assignment": _text(item.get("assignment")),
                    "eligibility": _text(item.get("eligibility")),
                    "reason": _text(item.get("reason")),
                    "task_count": len(item.get("task_refs") or [])
                    if isinstance(item.get("task_refs"), list)
                    else 0,
                }
                for item in file_decisions
            ],
            "notes": _text_list(scope_plan.get("notes")),
        },
        "confirmation": {
            "status": _text(confirmation.get("status")) or "clear",
            "question": _text(confirmation.get("question")),
            "blocking_reason": _text(confirmation.get("blocking_reason")),
        },
        "verification": {
            "status": _text(
                latest_verification.get("overall_status")
                or latest_verification.get("status")
            ) or "not_run",
            "claim_count": _int_value(latest_verification.get("claim_count")),
            "failed_count": _int_value(latest_verification.get("failed_count")),
            "downgraded_count": _int_value(latest_verification.get("downgraded_count")),
            "created_at": _text(latest_verification.get("created_at")),
        },
    }


def _flatten_limitations(evidence: list[dict[str, Any]], limit: int = 6) -> list[str]:
    limitations: list[str] = []
    for item in evidence:
        for text in _text_list(item.get("limitations")):
            if text and text not in limitations:
                limitations.append(text)
            if len(limitations) >= limit:
                return limitations
    return limitations


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item)
        if text:
            result.append(text)
    return result


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _int_value(value: Any, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
