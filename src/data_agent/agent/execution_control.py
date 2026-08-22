"""Turn-level execution budgets and tool recovery state."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any


class BudgetExceeded(RuntimeError):
    """Raised when a turn should stop or avoid a tool call."""


# Meta tools: record intermediate analysis artifacts, manage tasks, interact with user.
# These are overhead, not data analysis — exempt from tool_calls budget.
_META_TOOLS: set[str] = {
    "record_evidence_record",
    "record_analysis_spec",
    "record_data_requirement",
    "record_insight_record",
    "record_analysis_plan",
    "task_create",
    "task_update",
    "task_list",
    "ask_user_question",
    "generate_formal_report",
    "generate_analysis_brief",
    "generate_report",
}


@dataclass
class ToolExecutionBudget:
    profile: str = "analysis"
    max_tool_calls: int | None = None
    max_chart_calls: int | None = None
    max_fallback_calls: int | None = None
    max_consecutive_errors: int = 3
    max_repeated_tool_errors: int = 2
    max_elapsed_seconds: float | None = None
    soft_ratio: float = 0.75
    restrict_ratio: float = 0.85
    token_budget: int | None = None

    def __post_init__(self) -> None:
        defaults = {
            "interactive": (50, 3, 30_000),
            "analysis": (130, 8, 70_000),
            "deep": (200, 15, 100_000),
        }
        tool_calls, fallback_calls, token_budget = defaults.get(self.profile, defaults["analysis"])
        if self.max_tool_calls is None:
            self.max_tool_calls = tool_calls
        if self.max_fallback_calls is None:
            self.max_fallback_calls = fallback_calls
        if self.token_budget is None:
            self.token_budget = token_budget


@dataclass
class TurnExecutionState:
    budget: ToolExecutionBudget = field(default_factory=ToolExecutionBudget)
    started_at: float = field(default_factory=time.monotonic)
    llm_rounds: int = 0
    tool_calls: int = 0
    chart_calls: int = 0
    fallback_calls: int = 0
    consecutive_errors: int = 0
    repeated_errors: dict[str, int] = field(default_factory=dict)
    seen_calls: dict[str, int] = field(default_factory=dict)
    tool_errors: list[dict[str, Any]] = field(default_factory=list)
    pending_fallback_resolution: bool = False
    estimated_tokens_used: int = 0
    _call_order: list = field(default_factory=list)

    @property
    def should_converge(self) -> bool:
        return self.tool_calls >= math.ceil((self.budget.max_tool_calls or 0) * self.budget.soft_ratio)

    @property
    def should_restrict_exploration(self) -> bool:
        tool_limit = self.tool_calls >= math.ceil((self.budget.max_tool_calls or 0) * self.budget.restrict_ratio)
        fallback_limit = self.fallback_calls >= math.ceil((self.budget.max_fallback_calls or 0) * self.budget.restrict_ratio)
        return tool_limit or fallback_limit

    @property
    def should_stop_meta_only(self) -> bool:
        count = 0
        for name in reversed(self._call_order):
            if name in _META_TOOLS:
                count += 1
            else:
                break
        return count >= 4

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def record_llm_round(self) -> None:
        self.llm_rounds += 1

    def record_token_usage(self, delta: int) -> None:
        self.estimated_tokens_used += delta

    def ensure_can_call(self, tool_name: str, args: dict[str, Any] | None = None) -> None:
        args = args or {}
        is_meta = tool_name in _META_TOOLS

        # --- Time budget applies to all tools ---
        if self.budget.max_elapsed_seconds is not None and self.elapsed_seconds >= self.budget.max_elapsed_seconds:
            raise BudgetExceeded("Time budget reached; summarize current evidence and stop calling tools.")

        # Meta tools: only error safety checks remain (bypass budget, fallback, resolution)
        if is_meta:
            key = self._error_key(tool_name, args)
            if self.repeated_errors.get(key, 0) >= self.budget.max_repeated_tool_errors:
                raise BudgetExceeded(f"Repeated tool error for {tool_name}; do not retry the same call.")
            if self.consecutive_errors >= self.budget.max_consecutive_errors:
                raise BudgetExceeded("Consecutive tool errors reached; summarize recovery path instead of calling more tools.")
            return

        # --- Budget checks (non-meta tools) ---
        if self.tool_calls >= (self.budget.max_tool_calls or 0):
            raise BudgetExceeded("Tool call budget reached; summarize current evidence and stop calling tools.")
        if tool_name == "run_python" and self.fallback_calls >= (self.budget.max_fallback_calls or 0):
            raise BudgetExceeded("Fallback Python budget reached; use structured tools or ask for clarification.")
        if self.pending_fallback_resolution and tool_name not in self._fallback_resolution_tools():
            raise BudgetExceeded(
                "Fallback Python result must be resolved into evidence, limitations, task state, or user confirmation before more exploration."
            )
        if self._is_low_value_duplicate(tool_name, args):
            raise BudgetExceeded(f"Low-value duplicate tool call for {tool_name}; reuse existing evidence or change the analysis angle.")

        # --- Error safety (non-meta tools) ---
        key = self._error_key(tool_name, args)
        if self.repeated_errors.get(key, 0) >= self.budget.max_repeated_tool_errors:
            raise BudgetExceeded(f"Repeated tool error for {tool_name}; do not retry the same call.")
        if tool_name == "run_python":
            python_errors = sum(1 for err in self.tool_errors if err.get("tool_name") == "run_python")
            if python_errors >= self.budget.max_repeated_tool_errors:
                raise BudgetExceeded("Repeated run_python failure; use structured tools or ask the user.")
        if self.consecutive_errors >= self.budget.max_consecutive_errors:
            raise BudgetExceeded("Consecutive tool errors reached; summarize recovery path instead of calling more tools.")

    def record_tool_call(self, tool_name: str, args: dict[str, Any] | None = None) -> None:
        if tool_name not in _META_TOOLS:
            self.tool_calls += 1
        key = self._error_key(tool_name, args or {})
        self.seen_calls[key] = self.seen_calls.get(key, 0) + 1
        self._call_order.append(tool_name)
        if tool_name == "create_chart":
            self.chart_calls += 1
        if tool_name == "run_python":
            self.fallback_calls += 1
            self.pending_fallback_resolution = True
        elif tool_name in self._fallback_resolution_tools():
            self.pending_fallback_resolution = False

    def record_tool_success(self) -> None:
        self.consecutive_errors = 0

    def record_tool_error(self, tool_name: str, args: dict[str, Any] | None, error: str) -> None:
        key = self._error_key(tool_name, args or {})
        self.repeated_errors[key] = self.repeated_errors.get(key, 0) + 1
        self.consecutive_errors += 1
        self.tool_errors.append({
            "tool_name": tool_name,
            "error_category": normalize_tool_error(error),
            "arguments_hash": self._args_hash(args or {}),
            "retry_count": self.repeated_errors[key],
        })

    def prompt_hint(self) -> str:
        hints = []
        if self.tool_calls == 0:
            return ""
        if self.tool_calls >= (self.budget.max_tool_calls or 0):
            hints.append("Execution budget reached. Stop calling tools and summarize evidence, limits, and next steps.")
        if self.budget.token_budget and self.estimated_tokens_used >= self.budget.token_budget:
            hints.append("Token budget reached. Stop calling tools and summarize current findings.")
        if not hints:
            if self.should_restrict_exploration:
                hints.append("Execution budget is nearly exhausted. Do not start new exploratory tool paths; only record evidence or summarize.")
            elif self.should_converge:
                hints.append("Execution budget is past the soft threshold. Converge on the current evidence and avoid unnecessary tools.")
        if self.should_stop_meta_only:
            hints.append("Too many consecutive meta tool calls. Produce user-visible output now instead of recording more artifacts.")
        return " ".join(hints)

    def _error_key(self, tool_name: str, args: dict[str, Any]) -> str:
        return f"{tool_name}:{self._args_hash(args)}"

    def _is_low_value_duplicate(self, tool_name: str, args: dict[str, Any]) -> bool:
        low_value_tools = {
            "create_chart",
            "preview_data",
            "describe_dataset",
            "quick_profile",
            "detect_data_quality",
            "transform_data",
            "assess_readiness",
        }
        if tool_name not in low_value_tools:
            return False
        return self.seen_calls.get(self._error_key(tool_name, args), 0) > 0

    @staticmethod
    def _fallback_resolution_tools() -> set[str]:
        return {
            "record_evidence_record",
            "record_analysis_spec",
            "record_analysis_plan",
            "record_data_requirement",
            "record_insight_record",
            "task_update",
            "ask_user_question",
        }

    @staticmethod
    def _args_hash(args: dict[str, Any]) -> str:
        raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def normalize_tool_error(error: str) -> str:
    text = (error or "").lower()
    if "not found" in text or "不存在" in text or "missing" in text:
        return "missing_column_or_data"
    if "invalid" in text or "cannot be interpreted" in text or "typeerror" in text:
        return "invalid_parameter"
    if "安全" in text or "sandbox" in text or "not allowed" in text:
        return "sandbox_violation"
    if "too few" in text or "数据点太少" in text:
        return "insufficient_data"
    return "tool_error"


def recovery_hint_for_error(tool_name: str, error: str) -> str:
    category = normalize_tool_error(error)
    hints = {
        "invalid_parameter": "Parameter error. Correct the arguments before retrying; do not repeat the same call.",
        "missing_column_or_data": "Missing data or column. Use list_data, preview_data, or describe_dataset to inspect available fields.",
        "insufficient_data": "Data is insufficient for this method. Record the limitation and choose a simpler method.",
        "sandbox_violation": "Sandbox blocked the code. Prefer structured tools such as describe_dataset, preview_data, transform_data, or ask the user.",
    }
    return hints.get(category, f"{tool_name} failed. Try a different structured tool or summarize the limitation.")
