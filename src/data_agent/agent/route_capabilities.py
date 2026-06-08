"""Deterministic route capability model for chat and side panel surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_ACTIVE_MODES = {"consulting", "data_loaded", "analysis", "artifact_review"}


def build_route_capabilities(state: Any, limit: int = 4) -> dict[str, Any]:
    """Build executable and exploratory route recommendations from session state."""
    limit = _normalize_limit(limit)
    scope = getattr(state, "active_scope", {}) if state is not None else {}
    if not isinstance(scope, dict):
        scope = {}

    active_dataset = _text(scope.get("active_dataset"))
    active_route = _text(scope.get("active_route"))
    active_mode = _active_mode(state, scope, active_dataset)

    contracts = _hydrate_refs(_list_attr(state, "dataset_contracts"))
    routes = _hydrate_refs(_list_attr(state, "route_proposals"))
    cleaning_logs = _hydrate_refs(_list_attr(state, "cleaning_logs"))

    if limit <= 0:
        executable: list[dict[str, Any]] = []
        exploratory: list[dict[str, Any]] = []
    elif active_mode == "consulting":
        executable: list[dict[str, Any]] = []
        exploratory = _consulting_exploratory(_list_attr(state, "last_recommended_paths"), limit)
    else:
        executable = _executable_routes(routes, cleaning_logs, active_dataset, limit)
        exploratory = _unsupported_exploratory(contracts, active_dataset, limit)

    return {
        "active_dataset": active_dataset,
        "active_route": active_route,
        "active_mode": active_mode,
        "executable": executable,
        "exploratory": exploratory,
        "counts": {"executable": len(executable), "exploratory": len(exploratory)},
    }


def _executable_routes(
    routes: list[dict[str, Any]],
    cleaning_logs: list[dict[str, Any]],
    active_dataset: str,
    limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for route in routes:
        dataset = _text(route.get("dataset"))
        if active_dataset and dataset != active_dataset:
            continue
        direction = _text(route.get("direction") or route.get("route"))
        if not direction:
            continue
        risk_fields = _required_field_risks(route, cleaning_logs)
        category = "needs_confirmation" if risk_fields else "ready"
        items.append({
            "id": _text(route.get("id")) or f"route_{len(items) + 1}",
            "dataset": dataset,
            "route": direction,
            "direction": direction,
            "label": _text(route.get("label")) or direction,
            "category": category,
            "reason": _text(route.get("reason")),
            "limitations": _text_list(route.get("limitations")),
            "evidence_requirements": _text_list(route.get("evidence_requirements")),
            "risk_fields": risk_fields,
            "budget_level": _text(route.get("budget_level")),
            "prompt": _route_prompt(route, risk_fields),
            "auto_submit": False,
        })
        if len(items) >= limit:
            break
    return items


def _active_mode(state: Any, scope: dict[str, Any], active_dataset: str) -> str:
    raw_mode = _text(scope.get("active_mode"))
    if raw_mode in _ACTIVE_MODES:
        return raw_mode
    data_state = _text(getattr(state, "data_state", ""))
    if active_dataset and data_state == "data_loaded":
        return "data_loaded"
    return "consulting"


def _unsupported_exploratory(
    contracts: list[dict[str, Any]],
    active_dataset: str,
    limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for contract in contracts:
        dataset = _text(contract.get("dataset"))
        if active_dataset and dataset != active_dataset:
            continue
        for unsupported in _raw_list(contract.get("unsupported_analyses")):
            item = _unsupported_item(dataset, unsupported)
            if not item:
                continue
            items.append(item)
            if len(items) >= limit:
                return items
    return items


def _unsupported_item(dataset: str, unsupported: Any) -> dict[str, Any] | None:
    if isinstance(unsupported, dict):
        analysis = _text(unsupported.get("type") or unsupported.get("analysis"))
        reason = _text(unsupported.get("reason"))
        data_requirements = _text_list(unsupported.get("data_requirements"))
        value_if_available = _text(unsupported.get("value_if_available"))
    else:
        analysis = _text(unsupported)
        reason = ""
        data_requirements = []
        value_if_available = ""
    if not analysis:
        return None
    return {
        "id": f"explore_{_slug(dataset)}_{_slug(analysis)}",
        "dataset": dataset,
        "analysis": analysis,
        "label": analysis,
        "category": "needs_more_data",
        "reason": reason,
        "data_requirements": data_requirements,
        "value_if_available": value_if_available,
        "prompt": (
            f'I want to explore "{analysis}". Please tell me what data is missing, '
            "why the current data cannot verify it, and what dataset would be needed."
        ),
    }


def _consulting_exploratory(paths: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in paths:
        analysis = _text(path.get("id")) or _slug(_text(path.get("title"))) or f"method_{len(items) + 1}"
        label = _text(path.get("title")) or analysis
        items.append({
            "id": _text(path.get("id")) or f"method_{len(items) + 1}",
            "dataset": _text(path.get("dataset")),
            "analysis": analysis,
            "label": label,
            "category": "method_discussion",
            "reason": _text(path.get("reason")),
            "data_requirements": _text_list(path.get("data_requirements")),
            "value_if_available": _text(path.get("value_if_available")),
            "prompt": f'I want to discuss "{label}" as an analysis approach before running data.',
        })
        if len(items) >= limit:
            break
    return items


def _required_field_risks(route: dict[str, Any], cleaning_logs: list[dict[str, Any]]) -> list[str]:
    required = set(_required_fields(route))
    if not required:
        return []
    route_dataset = _text(route.get("dataset"))
    risks: list[str] = []
    for log in cleaning_logs:
        log_dataset = _text(log.get("dataset"))
        if route_dataset and log_dataset and route_dataset != log_dataset:
            continue
        for decision in _cleaning_decisions(log):
            if _text(decision.get("decision_type")) != "needs_confirmation":
                continue
            field = _text(decision.get("column") or decision.get("field"))
            if field in required:
                risks.append(field)
    return _dedupe(risks)


def _required_fields(route: dict[str, Any]) -> list[str]:
    required = _text_list(route.get("evidence_requirements"))
    roles = route.get("field_roles") if isinstance(route.get("field_roles"), dict) else {}
    direction = _text(route.get("direction") or route.get("route"))
    if direction in {"trend", "period_compare"}:
        required.extend(_text_list(roles.get("date")))
    elif direction == "dimension_decomposition":
        required.extend(_text_list(roles.get("dimensions")))
        required.extend(_text_list(roles.get("metrics")))
        required.extend(_text_list(roles.get("rate_metrics")))
    elif direction == "cohort":
        required.extend(_text_list(roles.get("ids")))
        required.extend(_text_list(roles.get("date")))
    elif direction == "funnel":
        required.extend(_text_list(roles.get("dimensions")))
        required.extend(_text_list(roles.get("metrics")))
        required.extend(_text_list(roles.get("rate_metrics")))
    return _dedupe(required)


def _route_prompt(route: dict[str, Any], risk_fields: list[str]) -> str:
    direction = _text(route.get("direction") or route.get("route"))
    if risk_fields:
        fields = ", ".join(risk_fields)
        return f"Before running {direction}, please confirm the cleaning decisions for: {fields}."
    label = _text(route.get("label"))
    reason = _text(route.get("reason"))
    pieces = [f"Please analyze the active dataset using the {direction} route."]
    if label:
        pieces.append(f"Focus: {label}.")
    if reason:
        pieces.append(f"Rationale: {reason}.")
    return " ".join(pieces)


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


def _cleaning_decisions(log: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = log.get("decisions")
    if isinstance(decisions, list):
        return [item for item in decisions if isinstance(item, dict)]
    return [log] if _text(log.get("decision_type")) else []


def _raw_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_limit(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 4


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _slug(value: str) -> str:
    return "_".join(_text(value).lower().split())


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
