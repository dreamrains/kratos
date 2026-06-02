"""Data-aware refinement for turn intent decisions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from data_agent.agent.intent import TurnIntent


_ANALYSIS_INTENTS = {"directed_analysis", "comprehensive_report"}
_RETENTION_KEYWORDS = ("retention", "留存", "cohort")


def refine_intent_with_data(
    user_input: str,
    intent: TurnIntent,
    dataset_contracts: list[dict[str, Any]],
    route_proposals: list[dict[str, Any]],
) -> TurnIntent:
    """Adjust a turn intent using deterministic data contracts and route options."""

    blocked_contracts = [
        contract
        for contract in dataset_contracts or []
        if (contract.get("quality") or {}).get("status") == "blocked"
    ]
    if intent.intent_type in _ANALYSIS_INTENTS and blocked_contracts:
        return replace(
            intent,
            clarity="clarification_needed",
            analysis_stage="scope",
            recommended_action="ask_question",
            execution_readiness="insufficient_data",
            ambiguities=[
                *list(intent.ambiguities),
                {
                    "kind": "data_quality",
                    "issue": "One or more loaded datasets have blocking quality issues.",
                    "contracts": _contract_ids(blocked_contracts),
                },
            ],
        )

    unsupported_retention = _contracts_with_unsupported_retention(dataset_contracts or [])
    if intent.intent_type in _ANALYSIS_INTENTS and _mentions_retention(user_input) and unsupported_retention:
        return replace(
            intent,
            clarity="clarification_needed",
            analysis_stage="scope",
            recommended_action="request_data",
            execution_readiness="insufficient_data",
            ambiguities=[
                *list(intent.ambiguities),
                {
                    "kind": "unsupported_analysis",
                    "analysis_type": "user_level_retention",
                    "issue": "The loaded data cannot support user-level retention analysis.",
                    "contracts": _contract_ids(unsupported_retention),
                    "reasons": _unsupported_reasons(unsupported_retention),
                },
            ],
        )

    if intent.intent_type == "intent_negotiation" and route_proposals:
        return replace(
            intent,
            recommended_action="guide_analysis",
            ambiguities=[
                *list(intent.ambiguities),
                {
                    "kind": "analysis_route",
                    "issue": "Data-supported analysis routes are available.",
                    "routes": [_route_summary(route) for route in route_proposals[:3]],
                },
            ],
        )

    return intent


def _mentions_retention(user_input: str) -> bool:
    text = (user_input or "").lower()
    return any(keyword in text for keyword in _RETENTION_KEYWORDS)


def _contracts_with_unsupported_retention(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for contract in contracts:
        for unsupported in contract.get("unsupported_analyses") or []:
            if unsupported.get("type") == "user_level_retention":
                matches.append(contract)
                break
    return matches


def _contract_ids(contracts: list[dict[str, Any]]) -> list[str]:
    return [str(contract.get("id") or contract.get("dataset") or "") for contract in contracts]


def _unsupported_reasons(contracts: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for contract in contracts:
        for unsupported in contract.get("unsupported_analyses") or []:
            if unsupported.get("type") == "user_level_retention":
                reason = unsupported.get("reason")
                if reason:
                    reasons.append(str(reason))
    return reasons


def _route_summary(route: dict[str, Any]) -> dict[str, str]:
    direction = str(route.get("direction") or "")
    label = str(route.get("label") or direction)
    return {"label": label, "direction": direction}
