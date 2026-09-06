"""Minimal, conclusion-only Workbench projection."""

from __future__ import annotations

from typing import Any


_CONFIDENCE_ORDER = {"high": 0, "medium": 1}
_VERIFIED_LIMIT = 6
_PENDING_LIMIT = 6
_PENDING_STATUSES = {"proposed", "inconclusive", "contested"}


def build_workbench_view(state: Any) -> dict[str, Any]:
    """Expose current verified conclusions plus explicitly pending findings.

    Verified conclusions keep their strict fingerprint gate. Pending findings
    are a separate category: hypothesis explanations that remain undecided
    carry their own status wording, basis, gap, and next verification step,
    and never mix into the verified list (P6/U01–U04).
    """
    conclusions = _verified_conclusions(state)
    return {
        "verified_conclusions": conclusions,
        "verified_total": len(conclusions),
        "pending_findings": _pending_findings(state),
    }


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
    # The full verified set is projected with its real total; the default
    # six-item display and expansion happen in the frontend (U01).
    return sorted(conclusions, key=lambda item: _CONFIDENCE_ORDER[item["confidence"]])


def _pending_findings(state: Any) -> list[dict[str, str]]:
    if state is None:
        return []
    try:
        from data_agent.agent.hypotheses import hydrate_hypothesis_refs

        hypothesis_sets = hydrate_hypothesis_refs(_list_attr(state, "hypothesis_sets"))
    except Exception:
        hypothesis_sets = _list_attr(state, "hypothesis_sets")
    findings: list[dict[str, str]] = []
    for hypothesis_set in hypothesis_sets[:2]:
        for hypothesis in _list_items(hypothesis_set.get("hypotheses")):
            status = _text(hypothesis.get("status"))
            if status not in _PENDING_STATUSES:
                continue
            required = [
                _text(requirement.get("field"))
                for requirement in _list_items(hypothesis.get("evidence_requirements"))
                if _text(requirement.get("field"))
            ][:3]
            basis_ids = _text_list(hypothesis.get("related_evidence_ids"))[:3] or _text_list(
                hypothesis.get("supporting_evidence_ids")
            )[:3]
            findings.append({
                "id": _text(hypothesis.get("id")),
                "claim": _text(hypothesis.get("claim"))[:160],
                "status": status,
                "status_label": _status_label(status),
                "basis": "、".join(basis_ids),
                "gap": "、".join(required),
                "next_step": f"补齐区分性证据：{'、'.join(required) if required else '按假设要求补齐字段或方法'}",
            })
            if len(findings) >= _PENDING_LIMIT:
                return findings
    return findings


def _status_label(status: str) -> str:
    return {
        "proposed": "待验证（候选解释）",
        "inconclusive": "未决（证据不足或不可判定）",
        "contested": "未决（支持与反证冲突）",
    }.get(status, status)


def _list_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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
