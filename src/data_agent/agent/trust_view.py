"""JSON-friendly trust inspector view model helpers."""

from __future__ import annotations

from typing import Any


def build_trust_view(state: Any, session_id: str | None = None) -> dict[str, Any]:
    """Build a compact Trust Inspector view model from analysis state."""
    if state is None:
        return _empty_view(session_id or "")

    contracts = _list_attr(state, "dataset_contracts")
    previews = _list_attr(state, "preview_digests")
    routes = _route_cards(_list_attr(state, "route_proposals"))
    risks = _risk_items(contracts, _list_attr(state, "cleaning_logs"))
    verification = _verification_summary(_list_attr(state, "verification_reports"))
    datasets = _dataset_summaries(contracts, previews)

    has_content = bool(datasets or routes or risks or verification)
    data_state = _text(getattr(state, "data_state", ""))
    status = "ready" if data_state == "data_loaded" or has_content else "empty"

    return {
        "status": status,
        "session_id": session_id or _text(getattr(state, "session_id", "")),
        "updated_at": _text(getattr(state, "updated_at", "")),
        "datasets": datasets,
        "routes": routes,
        "risks": risks,
        "verification": verification,
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
    }


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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
            "rows": _number_or_zero(contract.get("rows")),
            "columns": _column_count(contract.get("columns")),
            "quality_status": _text(quality.get("status") or contract.get("quality_status")),
            "quality_score": _number_or_zero(quality.get("score") or contract.get("quality_score")),
            "key_fields": _key_fields(contract.get("field_roles"))[:6],
            "supported_analyses": _text_list(contract.get("supported_analyses")),
            "preview_notes": _text_list(preview.get("preview_notes"))[:3],
        })
    return summaries


def _route_cards(routes: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for route in routes:
        direction = _text(route.get("direction"))
        if not direction:
            continue
        card = {
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
    direction = _text(route.get("direction"))
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
            _append_risk(risks, "block", "quality", dataset, issue)
        for warning in _raw_list(quality.get("warnings")):
            _append_risk(risks, "warning", "quality", dataset, warning)
        for unsupported in _raw_list(contract.get("unsupported_analyses")):
            _append_unsupported_risk(risks, dataset, unsupported)
        if len(risks) >= limit:
            return risks[:limit]

    for log in cleaning_logs:
        decision_type = _text(log.get("decision_type"))
        if decision_type not in {"needs_confirmation", "blocked"}:
            continue
        risks.append({
            "severity": decision_type,
            "source": "cleaning",
            "dataset": _text(log.get("dataset")),
            "field": _text(log.get("field")),
            "message": _message_from(log),
        })
        if len(risks) >= limit:
            break
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
        "field": _text(item.get("field")) if isinstance(item, dict) else "",
        "message": _message_from(item),
    })


def _append_unsupported_risk(
    risks: list[dict[str, Any]],
    dataset: str,
    item: Any,
) -> None:
    field = _text(item.get("analysis")) if isinstance(item, dict) else ""
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
            or item.get("analysis")
            or item.get("field")
        )
    return _text(item)


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
