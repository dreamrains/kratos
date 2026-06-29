"""Shared confirmation gate rules for analysis recommendations."""

from __future__ import annotations

from typing import Any
import json


BLOCKED_SURFACES = ["direct_recommendation", "analysis_execution", "report_generation"]
OBSOLETE_CONFIRMATION_TYPES = frozenset({
    "file_relationship_confirmation",
    "file_exclusion_confirmation",
    "join_logic_confirmation",
})


def is_actionable_pending_confirmation(item: Any) -> bool:
    """Return whether a legacy state record can still block analysis."""
    if not isinstance(item, dict):
        return False
    return (
        _text(item.get("status") or "pending") == "pending"
        and not is_obsolete_confirmation_record(item)
    )


def is_obsolete_confirmation_record(record: Any) -> bool:
    """Return whether a durable runtime record belongs to the retired workflow."""
    if isinstance(record, dict):
        value = record.get
    else:
        value = lambda key, default=None: getattr(record, key, default)

    params = value("resolution_params", {})
    if not isinstance(params, dict) and not hasattr(params, "get"):
        params = {}
    confirmation_type = _text(
        params.get("confirmation_type") or value("confirmation_type", "")
    )
    operation = _text(value("operation", ""))
    resolution_action = _text(
        value("resolution_action", "") or value("action", "")
    )
    state_updates = params.get("state_updates")
    if state_updates is None:
        state_updates = value("state_updates", {})
    state_updates = _state_updates(state_updates)
    has_legacy_state_update = (
        isinstance(state_updates, dict)
        and isinstance(state_updates.get("file_relationship_confirmation"), dict)
    )
    return (
        confirmation_type in OBSOLETE_CONFIRMATION_TYPES
        or operation in OBSOLETE_CONFIRMATION_TYPES
        or resolution_action == "resolve_file_relationship"
        or has_legacy_state_update
    )


def _state_updates(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def empty_confirmation_gate() -> dict[str, Any]:
    return {
        "status": "clear",
        "confirmation_type": "",
        "question": "",
        "blocking_reason": "",
        "risk_fields": [],
        "affected_routes": [],
        "blocked_surfaces": [],
    }


def pending_confirmation_gate(state: Any) -> dict[str, Any] | None:
    """Return a gate when the session already waits for user confirmation."""
    for item in _list_attr(state, "pending_confirmations"):
        if not is_actionable_pending_confirmation(item):
            continue
        return {
            "status": "needs_confirmation",
            "confirmation_type": _text(item.get("confirmation_type")) or "scope_confirmation",
            "question": _text(item.get("question")) or "请先确认关键信息后再生成最终推荐方向。",
            "blocking_reason": _text(item.get("blocking_reason")),
            "risk_fields": [],
            "affected_routes": [],
            "blocked_surfaces": list(BLOCKED_SURFACES),
        }
    return None


def route_confirmation_gate(
    *,
    risk_fields: list[str],
    affected_routes: list[str],
) -> dict[str, Any] | None:
    """Return a gate when route selection depends on unconfirmed fields."""
    fields = _dedupe([field for field in risk_fields if field])
    routes = _dedupe([route for route in affected_routes if route])
    if not fields and not routes:
        return None
    field_text = "、".join(fields) if fields else "关键字段"
    return {
        "status": "needs_confirmation",
        "confirmation_type": "data_quality_confirmation",
        "question": f"请先确认 {field_text} 的字段含义或清洗方式，再生成最终推荐方向。",
        "blocking_reason": "当前候选分析方向依赖尚未确认的数据字段。",
        "risk_fields": fields,
        "affected_routes": routes,
        "blocked_surfaces": list(BLOCKED_SURFACES),
    }


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
