"""Runtime glue for trustworthy analysis workflow integration."""

from __future__ import annotations

from typing import Any

from data_agent.agent.intent import TurnIntent
from data_agent.agent.intent_refinement import refine_intent_with_data
from data_agent.utils.logging import get_logger


logger = get_logger("trust_workflow_runtime")


def refine_turn_intent_with_state(user_input: str, intent: TurnIntent, state: Any) -> TurnIntent:
    """Refine a turn intent using trustworthy state refs without breaking the loop."""

    try:
        return refine_intent_with_data(
            user_input=user_input,
            intent=intent,
            dataset_contracts=_list_attr(state, "dataset_contracts"),
            route_proposals=_list_attr(state, "route_proposals"),
        )
    except Exception as exc:
        logger.warning(
            "Trust workflow intent refinement skipped",
            extra={"extra_data": {"error": str(exc)}},
        )
        return intent


def _list_attr(state: Any, name: str) -> list[dict[str, Any]]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
