"""Data-aware refinement for turn intent decisions."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from data_agent.agent.artifact_refs import hydrate_refs
from data_agent.agent.intent import TurnIntent
from data_agent.agent.request_language import keyword_group_state


_ANALYSIS_INTENTS = {"directed_analysis", "comprehensive_report"}
# Only an explicit user-level retention request triggers the user-grain
# limitation. Aggregate retention wording ("聚合留存", "留存曲线") describes a
# different capability and must not be blocked by the user-level gap.
_USER_LEVEL_RETENTION_KEYWORDS = (
    "个人留存", "用户级留存", "用户留存", "个体留存",
    "user-level retention", "user level retention", "user retention",
    "individual retention",
)
_AGGREGATE_RETENTION_MARKERS = (
    "聚合留存", "留存曲线", "按天留存", "每日留存", "留存率曲线",
    "aggregate retention", "retention curve",
)


def refine_intent_with_data(
    user_input: str,
    intent: TurnIntent,
    dataset_contracts: list[dict[str, Any]],
    route_proposals: list[dict[str, Any]],
    active_dataset: str = "",
) -> TurnIntent:
    """Adjust a turn intent using deterministic data contracts and route options.

    Contracts are evaluated inside the current task's data scope: quality or
    capability problems on an unrelated dataset must not block the active
    dataset's analysis, while problems on the scoped dataset still do.
    """

    contracts = _scoped_contracts(_dict_items(dataset_contracts), active_dataset)
    routes = _dict_items(route_proposals)
    blocked_contracts = [
        contract
        for contract in contracts
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
                *_copied_ambiguities(intent),
                {
                    "field": "data_quality",
                    "issue": "One or more loaded datasets have blocking quality issues.",
                    "contracts": _contract_ids(blocked_contracts),
                },
            ],
        )

    unsupported_retention = _contracts_with_unsupported_retention(contracts)
    if (
        intent.intent_type in _ANALYSIS_INTENTS
        and _requests_user_level_retention(user_input)
        and unsupported_retention
    ):
        return replace(
            intent,
            clarity="clarification_needed",
            analysis_stage="scope",
            recommended_action="request_data",
            execution_readiness="insufficient_data",
            ambiguities=[
                *_copied_ambiguities(intent),
                {
                    "field": "unsupported_analysis",
                    "analysis_type": "user_level_retention",
                    "issue": "The loaded data cannot support user-level retention analysis.",
                    "contracts": _contract_ids(unsupported_retention),
                    "reasons": _unsupported_reasons(unsupported_retention),
                    **(
                        {"partial": _aggregate_partial_note(user_input)}
                        if _aggregate_partial_note(user_input)
                        else {}
                    ),
                },
            ],
        )

    if intent.intent_type == "intent_negotiation" and routes:
        return replace(
            intent,
            recommended_action="guide_analysis",
            ambiguities=[
                *_copied_ambiguities(intent),
                {
                    "field": "analysis_route",
                    "issue": "Data-supported analysis routes are available.",
                    "routes": [_route_summary(route) for route in routes[:3]],
                },
            ],
        )

    return intent


def _scoped_contracts(
    contracts: list[dict[str, Any]],
    active_dataset: str,
) -> list[dict[str, Any]]:
    """Hydrate compact refs, then keep only the active dataset's contracts.

    Without an active dataset every contract is considered, preserving the
    previous conservative behavior for unscoped sessions.
    """
    hydrated = hydrate_refs(contracts)
    dataset = (active_dataset or "").strip()
    if not dataset:
        return hydrated
    return [
        contract
        for contract in hydrated
        if str(contract.get("dataset") or "") == dataset
    ]


def _requests_user_level_retention(user_input: str) -> bool:
    """Does the request need user-level (per-user) retention data?

    Explicit user-grain wording triggers directly. Generic retention/cohort
    wording also implies user-level analysis UNLESS the request names the
    aggregate form (aggregate retention curve fitting). A negated mention
    ("不计算个人留存") describes what the user does NOT want and never
    triggers the gate.
    """
    text = (user_input or "").lower()
    explicit = keyword_group_state(text, tuple(
        keyword.lower() for keyword in _USER_LEVEL_RETENTION_KEYWORDS
    ))
    if explicit == "affirmative":
        return True
    if any(marker in text for marker in _AGGREGATE_RETENTION_MARKERS):
        return False
    generic = keyword_group_state(text, ("retention", "留存", "cohort"))
    return generic == "affirmative"


def _aggregate_partial_note(user_input: str) -> str:
    text = (user_input or "").lower()
    if any(marker in text for marker in _AGGREGATE_RETENTION_MARKERS):
        return (
            "Aggregate retention fitting remains available with the current data; "
            "only user-level retention requires additional data."
        )
    return ""


def _contracts_with_unsupported_retention(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for contract in contracts:
        for unsupported in contract.get("unsupported_analyses") or []:
            if unsupported.get("type") == "user_level_retention":
                matches.append(contract)
                break
    return matches


def _dict_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _copied_ambiguities(intent: TurnIntent) -> list[dict[str, Any]]:
    if not isinstance(intent.ambiguities, list):
        return []
    return copy.deepcopy(intent.ambiguities)


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
    label = str(route.get("user_facing_label") or route.get("label") or direction)
    return {"label": label, "direction": direction}
