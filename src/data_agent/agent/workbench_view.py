"""Minimal, conclusion-only Workbench projection."""

from __future__ import annotations

from typing import Any


_CONFIDENCE_ORDER = {"high": 0, "medium": 1}


def build_workbench_view(state: Any) -> dict[str, Any]:
    """Expose only current, verified conclusions to the Workbench."""
    return {"verified_conclusions": _verified_conclusions(state)}


def _verified_conclusions(state: Any) -> list[dict[str, str]]:
    if state is None:
        return []
    evidence = _list_attr(state, "evidence_records")
    reports = _list_attr(state, "verification_reports")
    latest = reports[-1] if reports else {}
    verified_ids = _current_verified_evidence_ids(state, evidence, latest)
    conclusions = []
    for item in evidence:
        evidence_id = _text(item.get("id"))
        confidence = _text(item.get("confidence")) or "medium"
        claim = _text(item.get("claim"))
        if claim and confidence in _CONFIDENCE_ORDER and evidence_id in verified_ids:
            conclusions.append({
                "id": evidence_id,
                "claim": claim,
                "summary": _text(item.get("result_summary")),
                "confidence": confidence,
                "dataset": _text(item.get("dataset")),
            })
    return sorted(conclusions, key=lambda item: _CONFIDENCE_ORDER[item["confidence"]])[:6]


def _current_verified_evidence_ids(state: Any, evidence: list[dict[str, Any]], report: dict[str, Any]) -> set[str]:
    expected = _text(report.get("evidence_fingerprint"))
    if not expected:
        return set()
    try:
        from data_agent.agent.trust_workflow_runtime import (
            _current_analysis_plan_id, _current_plan_records, _evidence_fingerprint,
        )

        # Verification signs the current plan's evidence, not every historical
        # plan in this session. Consumer and producer must use the same scope.
        current = _current_plan_records(evidence, _current_analysis_plan_id(state))
        if _evidence_fingerprint(state, current) != expected:
            return set()
    except Exception:
        return set()
    current_ids = {str(item.get("id")) for item in current}
    return {str(item) for item in _text_list(report.get("passed_evidence_ids")) if str(item) in current_ids}


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text_list(value: Any) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""
