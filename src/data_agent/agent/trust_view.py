"""JSON-friendly trust inspector view model helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_agent.agent.multi_file_scope import build_analysis_scope_plan
from data_agent.agent.route_capabilities import build_route_capabilities


def build_trust_view(state: Any, session_id: str | None = None) -> dict[str, Any]:
    """Build a compact Trust Inspector view model from analysis state."""
    if state is None:
        return _empty_view(session_id or "")

    contract_refs = _list_attr(state, "dataset_contracts")
    preview_refs = _list_attr(state, "preview_digests")
    route_refs = _list_attr(state, "route_proposals")
    cleaning_refs = _list_attr(state, "cleaning_logs")
    verification_refs = _list_attr(state, "verification_reports")
    hypothesis_refs = _list_attr(state, "hypothesis_sets")

    contracts = _hydrate_refs(contract_refs)
    previews = _hydrate_refs(preview_refs)
    routes = _hydrate_refs(route_refs)
    cleaning_logs = _hydrate_refs(cleaning_refs)
    verification_reports = _hydrate_refs(verification_refs)
    hypothesis_sets = _hydrate_refs(hypothesis_refs)

    active_scope = _active_scope(getattr(state, "active_scope", {}))
    recommendations = build_route_capabilities(state)
    all_routes = _route_cards(routes, limit=len(routes))
    all_risks = _risk_items(contracts, cleaning_logs)
    verification = _verification_summary(verification_reports)
    all_datasets = _dataset_summaries(contracts, previews)
    all_hypotheses = _hypothesis_summaries(hypothesis_sets, limit=len(hypothesis_sets))
    active_bundle = _active_bundle_summary(state)
    file_relationships = _file_relationship_summaries(
        _list_attr(state, "file_relationships")
    )
    analysis_scope_plan = build_analysis_scope_plan(
        state,
        user_goal=active_scope["active_goal"] or _text(getattr(state, "goal", "")),
    )
    confirmation_gate = recommendations.get("confirmation_gate")
    if not isinstance(confirmation_gate, dict):
        confirmation_gate = {}
    workbench = _workbench_summary(
        state,
        analysis_scope_plan,
        confirmation_gate,
        verification,
    )

    if active_scope["active_mode"] == "consulting":
        datasets = all_datasets
        current_routes: list[dict[str, Any]] = []
        risks: list[dict[str, Any]] = []
        hypotheses: list[dict[str, Any]] = []
    else:
        active_dataset = active_scope["active_dataset"]
        datasets = _filter_by_dataset(all_datasets, active_dataset)
        current_routes = _route_cards(_list_items(recommendations.get("executable")))
        risks = _filter_by_dataset(all_risks, active_dataset)
        hypotheses = _filter_hypotheses(all_hypotheses, active_scope)[:3]

    has_content = bool(all_datasets or all_routes or all_risks or verification or all_hypotheses)
    data_state = _text(getattr(state, "data_state", ""))
    status = "ready" if data_state == "data_loaded" or has_content else "empty"

    return {
        "status": status,
        "session_id": session_id or _text(getattr(state, "session_id", "")),
        "updated_at": _text(getattr(state, "updated_at", "")),
        "datasets": datasets,
        "routes": current_routes,
        "risks": risks,
        "verification": verification,
        "hypotheses": hypotheses,
        "active_scope": active_scope,
        "scope_counts": {
            "datasets": len(all_datasets),
            "routes": len(all_routes),
            "risks": len(all_risks),
            "hypothesis_sets": len(all_hypotheses),
            "artifacts": _artifact_count(
                contract_refs,
                preview_refs,
                route_refs,
                cleaning_refs,
                verification_refs,
                hypothesis_refs,
            ),
        },
        "recommendations": recommendations,
        "analysis_scope_plan": analysis_scope_plan,
        "workbench": workbench,
        "active_bundle": active_bundle,
        "file_relationships": file_relationships,
        "history": {
            "datasets": all_datasets,
            "routes": all_routes,
            "risks": all_risks,
            "hypotheses": all_hypotheses,
        },
    }


def _empty_view(session_id: str) -> dict[str, Any]:
    return {
        "status": "empty",
        "session_id": session_id,
        "updated_at": "",
        "datasets": [],
        "routes": [],
        "risks": [],
        "verification": None,
        "hypotheses": [],
        "active_scope": {
            "active_dataset": "",
            "active_route": "",
            "active_goal": "",
            "active_mode": "consulting",
        },
        "scope_counts": {
            "datasets": 0,
            "routes": 0,
            "risks": 0,
            "hypothesis_sets": 0,
            "artifacts": 0,
        },
        "recommendations": {
            "active_dataset": "",
            "active_route": "",
            "active_mode": "consulting",
            "executable": [],
            "exploratory": [],
            "counts": {"executable": 0, "exploratory": 0},
            "confirmation_gate": {
                "status": "clear",
                "confirmation_type": "",
                "question": "",
                "blocking_reason": "",
                "risk_fields": [],
                "affected_routes": [],
                "blocked_surfaces": [],
            },
        },
        "analysis_scope_plan": None,
        "workbench": {
            "current_context": {
                "goal": "",
                "scope_status": "",
                "included_files": [],
                "excluded_files": [],
                "pending_files": [],
                "assumptions": [],
            },
            "confirmations": {
                "status": "clear",
                "question": "",
                "blocking_reason": "",
            },
            "trust_evidence": {
                "status": "not_run",
                "claim_count": 0,
                "failed_count": 0,
                "downgraded_count": 0,
            },
        },
        "active_bundle": None,
        "file_relationships": [],
        "history": {"datasets": [], "routes": [], "risks": [], "hypotheses": []},
    }


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _hydrate_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_hydrate_ref(item) for item in items]


def _hydrate_ref(item: dict[str, Any]) -> dict[str, Any]:
    artifact_path = _text(item.get("artifact_path"))
    if not artifact_path:
        return item
    artifact = _read_json_artifact(artifact_path)
    if not isinstance(artifact, dict):
        return item
    merged = dict(item)
    merged.update(artifact)
    return merged


def _read_json_artifact(artifact_path: str) -> dict[str, Any] | None:
    try:
        path = Path(artifact_path)
        if path.suffix.lower() != ".json" or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _dataset_summaries(
    contracts: list[dict[str, Any]],
    previews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    previews_by_dataset: dict[str, dict[str, Any]] = {}
    for preview in previews:
        dataset = _text(preview.get("dataset"))
        if dataset:
            previews_by_dataset[dataset] = preview

    summaries: list[dict[str, Any]] = []
    for contract in contracts:
        dataset = _text(contract.get("dataset"))
        if not dataset:
            continue
        quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
        preview = previews_by_dataset.get(dataset, {})
        summaries.append({
            "dataset": dataset,
            "rows": _number_or_zero(contract.get("row_count", contract.get("rows"))),
            "columns": _column_count(contract.get("column_count", contract.get("columns"))),
            "quality_status": _text(quality.get("status") or contract.get("quality_status")),
            "quality_score": _number_or_zero(quality.get("score") or contract.get("quality_score")),
            "key_fields": _key_fields(contract.get("field_roles"))[:6],
            "supported_analyses": _text_list(contract.get("supported_analyses")),
            "preview_notes": _preview_notes(preview)[:3],
        })
    return summaries


def _route_cards(routes: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for route in routes:
        direction = _text(route.get("direction") or route.get("route"))
        if not direction:
            continue
        card = {
            "id": _text(route.get("id")) or f"route_{len(cards) + 1}",
            "dataset": _text(route.get("dataset")),
            "direction": direction,
            "label": _text(route.get("label")) or direction,
            "reason": _text(route.get("reason")),
            "limitations": _text_list(route.get("limitations")),
            "budget_level": _text(route.get("budget_level")),
            "prompt": _route_prompt(route),
            "auto_submit": False,
        }
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _route_prompt(route: dict[str, Any]) -> str:
    direction = _text(route.get("direction") or route.get("route"))
    label = _text(route.get("label"))
    reason = _text(route.get("reason"))
    pieces = [f"Please analyze the current dataset using the {direction} direction."]
    if label:
        pieces.append(f"Focus: {label}.")
    if reason:
        pieces.append(f"Rationale: {reason}.")
    return " ".join(pieces)


def _risk_items(
    contracts: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
    limit: int = 12,
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for contract in contracts:
        dataset = _text(contract.get("dataset"))
        quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
        for issue in _raw_list(quality.get("block_issues")):
            _append_risk(risks, "blocked", "data_quality", dataset, issue)
        for warning in _raw_list(quality.get("warnings")):
            _append_risk(risks, "warning", "data_quality", dataset, warning)
        for unsupported in _raw_list(contract.get("unsupported_analyses")):
            _append_unsupported_risk(risks, dataset, unsupported)
        if len(risks) >= limit:
            return risks[:limit]

    for log in cleaning_logs:
        dataset = _text(log.get("dataset"))
        for decision in _cleaning_decisions(log):
            decision_type = _text(decision.get("decision_type"))
            if decision_type not in {"needs_confirmation", "blocked"}:
                continue
            risks.append({
                "severity": "blocked" if decision_type == "blocked" else "warning",
                "source": "cleaning",
                "dataset": _text(decision.get("dataset")) or dataset,
                "field": _text(decision.get("column")) or _text(decision.get("field")),
                "message": _cleaning_message(decision),
            })
            if len(risks) >= limit:
                return risks[:limit]
    return risks[:limit]


def _verification_summary(reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not reports:
        return None
    report = reports[-1]
    return {
        "id": _text(report.get("id")),
        "status": _text(report.get("overall_status") or report.get("status")),
        "claim_count": _count_value(report.get("claim_count"), report.get("claim_checks")),
        "failed_count": _int_value(report.get("failed_count")),
        "downgraded_count": _int_value(report.get("downgraded_count")),
        "evidence_signature": _text(report.get("evidence_signature")),
        "created_at": _text(report.get("created_at")),
    }


def _workbench_summary(
    state: Any,
    analysis_scope_plan: dict[str, Any] | None,
    confirmation_gate: dict[str, Any],
    verification: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = analysis_scope_plan if isinstance(analysis_scope_plan, dict) else {}
    trust_evidence = verification if _has_meaningful_verification(verification) else {
        "status": "not_run",
        "claim_count": 0,
        "failed_count": 0,
        "downgraded_count": 0,
    }
    return {
        "current_context": {
            "goal": _text(plan.get("goal")) or _text(getattr(state, "goal", "")),
            "scope_status": _text(plan.get("scope_status")),
            "included_files": _list_items(plan.get("included_files")),
            "excluded_files": _list_items(plan.get("excluded_files")),
            "pending_files": _list_items(plan.get("pending_files")),
            "assumptions": _text_list(plan.get("assumptions")),
        },
        "confirmations": {
            "status": _text(confirmation_gate.get("status")) or "clear",
            "question": _text(confirmation_gate.get("question")),
            "blocking_reason": _text(confirmation_gate.get("blocking_reason")),
        },
        "trust_evidence": trust_evidence,
    }


def _has_meaningful_verification(verification: dict[str, Any] | None) -> bool:
    if not isinstance(verification, dict):
        return False
    status = _text(verification.get("status"))
    return bool(
        (status and status != "unknown")
        or _text(verification.get("id"))
        or _int_value(verification.get("claim_count")) > 0
    )


def _hypothesis_summaries(
    hypothesis_sets: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for item in hypothesis_sets:
        item_id = _text(item.get("id"))
        if not item_id:
            continue
        hypotheses = _list_items(item.get("hypotheses"))
        status_summary = item.get("status_summary")
        summaries.append({
            "id": item_id,
            "dataset": _text(item.get("dataset")),
            "route": _text(item.get("route")),
            "count": _count_value(item.get("count"), hypotheses),
            "status_summary": status_summary if isinstance(status_summary, dict) else {},
            "top_claims": [
                {
                    "claim": _text(hypothesis.get("claim")),
                    "status": _text(hypothesis.get("status")),
                }
                for hypothesis in hypotheses[:2]
                if _text(hypothesis.get("claim"))
            ],
        })
        if len(summaries) >= limit:
            break
    return summaries


def _active_bundle_summary(state: Any) -> dict[str, Any] | None:
    bundle = _find_active_bundle(state)
    if not bundle:
        return None

    file_ids = _text_list(bundle.get("file_ids"))
    data_pool_by_file_id = {
        _text(item.get("file_id") or item.get("id")): item
        for item in _list_attr(state, "data_pool")
        if _text(item.get("file_id") or item.get("id"))
    }
    files = [
        _bundle_file_summary(file_id, data_pool_by_file_id.get(file_id, {}))
        for file_id in file_ids[:5]
    ]
    return {
        "bundle_id": _text(bundle.get("bundle_id") or bundle.get("id")),
        "label": _text(bundle.get("label") or bundle.get("name")),
        "file_count": len(file_ids),
        "dataset_names": _text_list(bundle.get("dataset_names"))[:6],
        "relationship_status": _text(bundle.get("relationship_status") or bundle.get("status")),
        "relationship_mode": _text(bundle.get("relationship_mode")),
        "files": files,
        "remaining_file_count": max(len(file_ids) - len(files), 0),
    }


def _find_active_bundle(state: Any) -> dict[str, Any] | None:
    active_bundle_id = _text(getattr(state, "active_bundle_id", ""))
    if not active_bundle_id:
        return None
    for bundle in _list_attr(state, "dataset_bundles"):
        if _text(bundle.get("bundle_id")) == active_bundle_id or _text(bundle.get("id")) == active_bundle_id:
            return bundle
    return None


def _bundle_file_summary(file_id: str, file_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": file_id,
        "filename": _text(file_ref.get("filename") or file_ref.get("name")),
        "dataset": _text(file_ref.get("dataset") or file_ref.get("dataset_name")),
        "rows": _number_or_zero(file_ref.get("row_count", file_ref.get("rows"))),
        "columns": _column_count(file_ref.get("column_count", file_ref.get("columns"))),
        "status": _text(file_ref.get("status")),
    }


def _file_relationship_summaries(
    relationships: list[dict[str, Any]],
    limit: int = 4,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for relationship in reversed(relationships):
        relationship_id = _text(relationship.get("relationship_id") or relationship.get("id"))
        if not relationship_id:
            continue
        file_ids = _text_list(relationship.get("file_ids"))
        summaries.append({
            "relationship_id": relationship_id,
            "status": _text(relationship.get("status")),
            "requires_confirmation": relationship.get("requires_confirmation") is True,
            "relationship_mode": _text(relationship.get("relationship_mode")),
            "confirmation_type": _text(relationship.get("confirmation_type")),
            "file_count": len(file_ids),
            "file_ids": file_ids[:3],
            "evidence": _text_list(relationship.get("evidence"))[:2],
            "uncertainties": _text_list(relationship.get("uncertainties"))[:2],
        })
        if len(summaries) >= limit:
            break
    return summaries


def _active_scope(value: Any) -> dict[str, Any]:
    scope = value if isinstance(value, dict) else {}
    return {
        "active_dataset": _text(scope.get("active_dataset")),
        "active_route": _text(scope.get("active_route")),
        "active_goal": _text(scope.get("active_goal")),
        "active_mode": _text(scope.get("active_mode")) or "consulting",
    }


def _filter_by_dataset(items: list[dict[str, Any]], dataset: str) -> list[dict[str, Any]]:
    if not dataset:
        return items
    return [item for item in items if _text(item.get("dataset")) == dataset]


def _filter_hypotheses(
    items: list[dict[str, Any]],
    active_scope: dict[str, Any],
) -> list[dict[str, Any]]:
    filtered = _filter_by_dataset(items, _text(active_scope.get("active_dataset")))
    active_route = _text(active_scope.get("active_route"))
    if not active_route:
        return filtered
    return [
        item for item in filtered
        if _text(item.get("route")) == active_route
    ]


def _artifact_count(*groups: list[dict[str, Any]]) -> int:
    return sum(1 for group in groups for item in group if _text(item.get("artifact_path")))


def _append_risk(
    risks: list[dict[str, Any]],
    severity: str,
    source: str,
    dataset: str,
    item: Any,
) -> None:
    risks.append({
        "severity": severity,
        "source": source,
        "dataset": dataset,
        "field": _risk_field(item),
        "message": _message_from(item),
    })


def _append_unsupported_risk(
    risks: list[dict[str, Any]],
    dataset: str,
    item: Any,
) -> None:
    field = _text(item.get("type") or item.get("analysis")) if isinstance(item, dict) else ""
    risks.append({
        "severity": "warning",
        "source": "unsupported_analysis",
        "dataset": dataset,
        "field": field,
        "message": _message_from(item),
    })


def _message_from(item: Any) -> str:
    if isinstance(item, dict):
        return _text(
            item.get("message")
            or item.get("reason")
            or item.get("description")
            or _join_texts(item.get("codes"))
            or item.get("type")
            or item.get("analysis")
            or item.get("column")
            or item.get("field")
            or _compact_dict(item)
        )
    return _text(item)


def _risk_field(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return (
        _join_texts(item.get("columns"))
        or _text(item.get("column"))
        or _text(item.get("field"))
        or _join_texts(item.get("codes"))
        or _text(item.get("type"))
    )


def _cleaning_message(decision: dict[str, Any]) -> str:
    return _text(
        decision.get("impact")
        or decision.get("message")
        or decision.get("reason")
        or decision.get("description")
    )


def _preview_notes(preview: dict[str, Any]) -> list[str]:
    notes = []
    notes.extend(_text_list(preview.get("notable_patterns")))
    notes.extend(_text_list(preview.get("risks")))
    notes.extend(_text_list(preview.get("preview_notes")))
    return _dedupe(notes)


def _cleaning_decisions(log: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = _list_items(log.get("decisions"))
    if decisions:
        return decisions
    decision_type = _text(log.get("decision_type"))
    return [log] if decision_type else []


def _key_fields(field_roles: Any) -> list[str]:
    if not isinstance(field_roles, dict):
        return []
    fields: list[str] = []
    for role in ("date", "metrics", "rate_metrics", "dimensions", "ids"):
        fields.extend(_text_list(field_roles.get(role)))
    return _dedupe(fields)


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _join_texts(value: Any) -> str:
    if not isinstance(value, list):
        return _text(value)
    return ", ".join(_text_list(value))


def _compact_dict(value: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in sorted(value):
        text = _join_texts(value[key])
        if text:
            parts.append(f"{key}: {text}")
    return "; ".join(parts)


def _list_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _raw_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _column_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    return _int_value(value)


def _count_value(value: Any, fallback_items: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(fallback_items, list):
        return len([item for item in fallback_items if isinstance(item, dict)])
    return 0


def _number_or_zero(value: Any) -> int | float:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return value
    return 0


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""
