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


@dataclass
class ToolExecutionBudget:
    profile: str = "analysis"
    max_tool_calls: int | None = None
    max_chart_calls: int | None = None
    max_fallback_calls: int | None = None
    max_consecutive_errors: int = 3
    max_repeated_tool_errors: int = 2
    soft_ratio: float = 0.60
    restrict_ratio: float = 0.85

    def __post_init__(self) -> None:
        defaults = {
            "interactive": (30, 3, 3),
            "analysis": (80, 6, 8),
            "deep": (120, 10, 15),
        }
        tool_calls, chart_calls, fallback_calls = defaults.get(self.profile, defaults["analysis"])
        if self.max_tool_calls is None:
            self.max_tool_calls = tool_calls
        if self.max_chart_calls is None:
            self.max_chart_calls = chart_calls
        if self.max_fallback_calls is None:
            self.max_fallback_calls = fallback_calls


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
    tool_errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def should_converge(self) -> bool:
        return self.tool_calls >= math.ceil((self.budget.max_tool_calls or 0) * self.budget.soft_ratio)

    @property
    def should_restrict_exploration(self) -> bool:
        tool_limit = self.tool_calls >= math.ceil((self.budget.max_tool_calls or 0) * self.budget.restrict_ratio)
        chart_limit = self.chart_calls >= math.ceil((self.budget.max_chart_calls or 0) * self.budget.restrict_ratio)
        fallback_limit = self.fallback_calls >= math.ceil((self.budget.max_fallback_calls or 0) * self.budget.restrict_ratio)
        return tool_limit or chart_limit or fallback_limit

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def record_llm_round(self) -> None:
        self.llm_rounds += 1

    def ensure_can_call(self, tool_name: str, args: dict[str, Any] | None = None) -> None:
        args = args or {}
        if self.tool_calls >= (self.budget.max_tool_calls or 0):
            raise BudgetExceeded("Tool call budget reached; summarize current evidence and stop calling tools.")
        if tool_name == "create_chart" and self.chart_calls >= (self.budget.max_chart_calls or 0):
            raise BudgetExceeded("Chart budget reached; use text tables or summarize instead.")
        if tool_name == "run_python" and self.fallback_calls >= (self.budget.max_fallback_calls or 0):
            raise BudgetExceeded("Fallback Python budget reached; use structured tools or ask for clarification.")
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
        self.tool_calls += 1
        if tool_name == "create_chart":
            self.chart_calls += 1
        if tool_name == "run_python":
            self.fallback_calls += 1

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
        if self.tool_calls == 0:
            return ""
        if self.tool_calls >= (self.budget.max_tool_calls or 0):
            return "Execution budget reached. Stop calling tools and summarize evidence, limits, and next steps."
        if self.should_restrict_exploration:
            return "Execution budget is nearly exhausted. Do not start new exploratory tool paths; only record evidence or summarize."
        if self.should_converge:
            return "Execution budget is past the soft threshold. Converge on the current evidence and avoid unnecessary tools."
        return ""

    def _error_key(self, tool_name: str, args: dict[str, Any]) -> str:
        return f"{tool_name}:{self._args_hash(args)}"

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
