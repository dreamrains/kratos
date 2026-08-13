from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import litellm

from data_agent.llm.client import prepare_provider_prompt
from data_agent.v2.planner import DatasetPlanningContext, StructuredAnalysisPlanner


class PlanningContextWindowUnknown(RuntimeError):
    """The configured model has no trustworthy context-window metadata."""


class PlanningTokenEstimateUnavailable(RuntimeError):
    """The actual Provider prompt could not be token-counted."""


class PlanningContextTooLarge(RuntimeError):
    def __init__(self, estimate: "PlanningContextEstimate") -> None:
        super().__init__("planning context exceeds the model input budget")
        self.estimate = estimate


@dataclass(frozen=True, slots=True)
class PlanningContextEstimate:
    model_id: str
    estimated_input_tokens: int
    model_context_window_tokens: int
    reserved_output_tokens: int
    available_input_tokens: int
    fits: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_OFFICIAL_PROVIDER_CONTEXT_WINDOWS = {
    ("api.deepseek.com", "deepseek-v4-flash"): 1_000_000,
    ("api.deepseek.com", "deepseek-v4-pro"): 1_000_000,
}


def resolve_model_context_window(
    model_id: str,
    configured_context_window: int | None,
    *,
    api_base: str | None = None,
) -> int:
    if configured_context_window is not None:
        if configured_context_window <= 0:
            raise ValueError("configured model context window must be positive")
        return configured_context_window
    hostname = (urlparse(api_base or "").hostname or "").casefold()
    provider_model = str(model_id or "").strip().split("/")[-1].casefold()
    official = _OFFICIAL_PROVIDER_CONTEXT_WINDOWS.get((hostname, provider_model))
    if official is not None:
        return official
    try:
        info = litellm.get_model_info(model_id)
    except Exception as exc:
        raise PlanningContextWindowUnknown(
            "model context window is unknown; configure MODEL_CONTEXT_WINDOW"
        ) from exc
    value = info.get("max_input_tokens") or info.get("max_tokens")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PlanningContextWindowUnknown(
            "model context window is unknown; configure MODEL_CONTEXT_WINDOW"
        )
    return value


class PlanningContextBudget:
    """Count the exact Planner request and enforce only the model window."""

    def __init__(
        self,
        planner: StructuredAnalysisPlanner,
        *,
        model_id: str,
        context_window_tokens: int,
        reserved_output_tokens: int,
        token_counter: Callable[..., int] = litellm.token_counter,
    ) -> None:
        self.planner = planner
        self.model_id = str(model_id or "").strip()
        if not self.model_id:
            raise ValueError("model_id is required")
        if context_window_tokens <= 0:
            raise ValueError("context_window_tokens must be positive")
        if reserved_output_tokens < 0:
            raise ValueError("reserved_output_tokens cannot be negative")
        self.context_window_tokens = context_window_tokens
        self.reserved_output_tokens = reserved_output_tokens
        self.token_counter = token_counter

    def estimate(
        self,
        question: str,
        context: DatasetPlanningContext,
        *,
        clarifications: tuple[dict[str, str], ...] | list[dict[str, str]] = (),
    ) -> PlanningContextEstimate:
        _, request = self.planner.build_request(
            question, context, clarifications=clarifications
        )
        messages, tools = prepare_provider_prompt(
            request.messages, request.tools, request.system
        )
        try:
            estimated = self.token_counter(
                model=self.model_id,
                messages=messages,
                tools=tools,
            )
        except Exception as exc:
            raise PlanningTokenEstimateUnavailable(
                "planning request token estimate is unavailable"
            ) from exc
        if isinstance(estimated, bool) or not isinstance(estimated, int) or estimated < 0:
            raise PlanningTokenEstimateUnavailable(
                "planning request token estimate is invalid"
            )
        available = max(
            0, self.context_window_tokens - self.reserved_output_tokens
        )
        return PlanningContextEstimate(
            model_id=self.model_id,
            estimated_input_tokens=estimated,
            model_context_window_tokens=self.context_window_tokens,
            reserved_output_tokens=self.reserved_output_tokens,
            available_input_tokens=available,
            fits=estimated <= available,
        )

    def require_fits(
        self,
        question: str,
        context: DatasetPlanningContext,
        *,
        clarifications: tuple[dict[str, str], ...] | list[dict[str, str]] = (),
    ) -> PlanningContextEstimate:
        estimate = self.estimate(
            question, context, clarifications=clarifications
        )
        if not estimate.fits:
            raise PlanningContextTooLarge(estimate)
        return estimate
