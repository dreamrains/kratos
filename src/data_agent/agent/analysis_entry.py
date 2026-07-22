"""Deterministic analysis entry decisions from user intent and trust state."""

from __future__ import annotations

from typing import Any

from data_agent.agent.artifact_refs import hydrate_refs
from data_agent.agent.confirmation_policy import pending_confirmation_gate
from data_agent.agent.question_need_detector import (
    computable_route_evidence,
    detect_question_need,
    to_confirmation_gate,
)
from data_agent.agent.trust_contracts import route_evidence_requirements


_RETENTION_KEYWORDS = ("retention", "cohort", "\u7559\u5b58")
_ROUTE_KEYWORDS = {
    "trend": ("trend", "time series", "\u8d8b\u52bf", "\u8d70\u52bf"),
    "period_compare": ("period", "compare", "comparison", "\u540c\u6bd4", "\u73af\u6bd4", "\u5bf9\u6bd4"),
    "dimension_decomposition": ("segment", "dimension", "breakdown", "\u5206\u7ef4", "\u5f52\u56e0"),
    "cohort": ("cohort", "retention", "\u7559\u5b58"),
    "user_level_retention": ("retention", "user retention", "\u7559\u5b58"),
}


def decide_analysis_entry(user_input: str, intent: Any, state: Any) -> dict[str, Any]:
    """Choose whether a requested analysis can proceed from current trust state."""
    gate = pending_confirmation_gate(state)
    if gate:
        return _decision(
            "clarify_intent",
            reason="A pending confirmation must be resolved before analysis recommendations or execution.",
            required_user_action="ask_user_question",
            confirmation_gate=gate,
        )

    contracts = hydrate_refs(_list_attr(state, "dataset_contracts"))
    raw_routes = hydrate_refs(_list_attr(state, "route_proposals"))
    active_dataset = _active_dataset(state)
    scoped_contracts = _filter_by_dataset(contracts, active_dataset)
    capability_model = _route_capabilities(state)
    if capability_model is None:
        routes = raw_routes
        exploratory_routes: list[dict[str, Any]] = []
    else:
        capability_routes = capability_model["executable"]
        exploratory_routes = capability_model["exploratory"]
        if (
            not capability_routes
            and not exploratory_routes
            and capability_model["active_mode"] == "consulting"
            and not _explicit_active_mode(state)
        ):
            routes = raw_routes
        else:
            routes = capability_routes
    cleaning_logs = hydrate_refs(_list_attr(state, "cleaning_logs"))

    blocked = _blocked_contract(scoped_contracts)
    if blocked:
        return _decision(
            "blocked",
            dataset=_text(blocked.get("dataset")),
            reason="Data quality blocks formal analysis.",
            required_user_action="resolve_data_quality",
            limitations=_quality_blocks(blocked),
        )

    unsupported_retention = _unsupported_retention(scoped_contracts)
    if _mentions_retention(user_input) and unsupported_retention:
        return _decision(
            "request_data",
            dataset=active_dataset,
            reason="The loaded data cannot support user-level retention analysis.",
            required_user_action="provide_user_level_retention_data",
            limitations=_unsupported_reasons(unsupported_retention),
        )

    question_need = detect_question_need(user_input, intent, state)
    if question_need.get("status") == "hard_question":
        if question_need.get("question_type") == "route_selection":
            return _decision(
                "clarify_intent",
                reason=question_need.get("reason", ""),
                required_user_action="choose_analysis_route",
                route_options=_route_options(routes),
                risk_fields=question_need.get("risk_fields", []),
                confirmation_gate=to_confirmation_gate(question_need),
            )
        return _decision(
            "clarify_intent",
            reason=question_need.get("reason", ""),
            required_user_action="ask_user_question",
            route_options=[],
            risk_fields=question_need.get("risk_fields", []),
            confirmation_gate=to_confirmation_gate(question_need),
        )

    missing_route = _infer_requested_exploratory_route(user_input, exploratory_routes)
    if missing_route:
        missing_requirements = _text_list(missing_route.get("missing_requirements"))
        return _decision(
            "request_data",
            dataset=_text(missing_route.get("dataset")),
            route=_route_direction(missing_route),
            reason="The requested analysis route needs data that is not available in the current scope.",
            required_user_action="provide_required_data",
            limitations=missing_requirements,
            evidence_requirements=route_evidence_requirements(missing_route),
        )

    route = _infer_requested_route(user_input, routes)
    if not route and _text(getattr(intent, "clarity", "")) == "vague" and len(routes) > 1:
        return _decision(
            "clarify_intent",
            reason="Multiple data-supported analysis routes are available.",
            required_user_action="choose_analysis_route",
            route_options=_route_options(routes),
        )
    if not route and routes:
        route = routes[0]

    if route:
        risk_fields = _text_list(route.get("risk_fields")) or _required_field_risks(route, cleaning_logs)
        if risk_fields or _text(route.get("category")) == "needs_confirmation":
            return _decision(
                "clarify_intent",
                dataset=_text(route.get("dataset")),
                route=_route_direction(route),
                reason="A required field has a cleaning decision that needs confirmation.",
                required_user_action="confirm_cleaning_decision",
                risk_fields=risk_fields,
                limitations=_text_list(route.get("limitations")),
                evidence_requirements=route_evidence_requirements(route),
            )
        return _decision(
            "direct_analysis",
            dataset=_text(route.get("dataset")),
            route=_route_direction(route),
            reason="The request matches a supported data route.",
            confidence="medium",
            limitations=_text_list(route.get("limitations")),
            evidence_requirements=route_evidence_requirements(route),
            analysis_evidence_to_compute=computable_route_evidence(route),
        )

    return _decision(
        "clarify_intent",
        reason="No supported analysis route can be selected deterministically.",
        required_user_action="clarify_analysis_goal",
    )


def _route_capabilities(state: Any) -> dict[str, Any] | None:
    try:
        from data_agent.agent.route_capabilities import build_route_capabilities
    except ImportError:
        return None

    model = build_route_capabilities(state)
    if not isinstance(model, dict):
        return None
    executable = model.get("executable")
    exploratory = model.get("exploratory")
    if not isinstance(executable, list) or not isinstance(exploratory, list):
        return None
    return {
        "executable": [item for item in executable if isinstance(item, dict)],
        "exploratory": [item for item in exploratory if isinstance(item, dict)],
        "active_mode": _text(model.get("active_mode")),
    }


def _decision(decision: str, **overrides: Any) -> dict[str, Any]:
    payload = {
        "decision": decision,
        "reason": "",
        "dataset": "",
        "route": "",
        "confidence": "low",
        "required_user_action": "",
        "limitations": [],
        "evidence_requirements": [],
        "route_options": [],
        "risk_fields": [],
        "analysis_evidence_to_compute": [],
    }
    payload.update(overrides)
    return payload


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _active_dataset(state: Any) -> str:
    scope = getattr(state, "active_scope", None)
    if not isinstance(scope, dict):
        return ""
    return _text(scope.get("active_dataset"))


def _explicit_active_mode(state: Any) -> str:
    scope = getattr(state, "active_scope", None)
    if not isinstance(scope, dict):
        return ""
    mode = _text(scope.get("active_mode"))
    if mode == "consulting" and not any(
        _text(scope.get(key))
        for key in ("active_dataset", "active_route", "active_goal", "updated_at")
    ):
        return ""
    return mode


def _filter_by_dataset(items: list[dict[str, Any]], dataset: str) -> list[dict[str, Any]]:
    if not dataset:
        return items
    return [item for item in items if _text(item.get("dataset")) == dataset]


def _blocked_contract(contracts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for contract in contracts:
        quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
        if quality.get("status") == "blocked":
            return contract
    return None


def _quality_blocks(contract: dict[str, Any]) -> list[str]:
    quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
    return _text_list(quality.get("block_issues"))


def _unsupported_retention(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    for contract in contracts:
        unsupported_items = contract.get("unsupported_analyses")
        if not isinstance(unsupported_items, list):
            continue
        for unsupported in unsupported_items:
            if isinstance(unsupported, dict) and unsupported.get("type") == "user_level_retention":
                matches.append(unsupported)
    return matches


def _unsupported_reasons(items: list[dict[str, Any]]) -> list[str]:
    return [_text(item.get("reason")) for item in items if _text(item.get("reason"))]


def _mentions_retention(user_input: str) -> bool:
    text = (user_input or "").lower()
    return any(keyword in text for keyword in _RETENTION_KEYWORDS)


def _infer_requested_route(user_input: str, routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = (user_input or "").lower()
    for route in routes:
        direction = _route_direction(route)
        keywords = _ROUTE_KEYWORDS.get(direction, (direction,))
        if any(keyword and keyword in text for keyword in keywords):
            return route
    return None


def _infer_requested_exploratory_route(
    user_input: str,
    routes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = [
        route
        for route in routes
        if _text(route.get("category")) == "needs_more_data"
        and _text(route.get("support_status")) == "needs_more_data"
    ]
    route = _infer_requested_route(user_input, candidates)
    if route:
        return route
    text = (user_input or "").lower()
    for route in candidates:
        labels = [
            _text(route.get("analysis")),
            _text(route.get("label")),
            _route_direction(route),
        ]
        if any(label and label.lower() in text for label in labels):
            return route
    return None


def _route_options(routes: list[dict[str, Any]]) -> list[dict[str, str]]:
    options = []
    for route in routes[:4]:
        direction = _route_direction(route)
        options.append({
            "direction": direction,
            "label": _text(route.get("label") or route.get("user_facing_label") or direction),
            "dataset": _text(route.get("dataset")),
        })
    return options


def _required_field_risks(route: dict[str, Any], cleaning_logs: list[dict[str, Any]]) -> list[str]:
    requirements = set(route_evidence_requirements(route))
    risky_fields = []
    for log in cleaning_logs:
        route_dataset = _text(route.get("dataset"))
        log_dataset = _text(log.get("dataset"))
        if route_dataset and log_dataset and route_dataset != log_dataset:
            continue
        decisions = log.get("decisions")
        if not isinstance(decisions, list):
            decisions = [log] if _text(log.get("decision_type")) else []
        for decision in decisions:
            if not isinstance(decision, dict) or decision.get("decision_type") != "needs_confirmation":
                continue
            column = _text(decision.get("column") or decision.get("field"))
            if column and (column in requirements or _route_requires_field_kind(route, column)):
                risky_fields.append(column)
    return _dedupe(risky_fields)


def _route_requires_field_kind(route: dict[str, Any], column: str) -> bool:
    requirements = set(route_evidence_requirements(route))
    direction = _route_direction(route)
    if column.lower() == "date" and ("date" in requirements or direction in {"trend", "period_compare"}):
        return True
    return False


def _route_direction(route: dict[str, Any]) -> str:
    return _text(route.get("route") or route.get("direction"))


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


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
