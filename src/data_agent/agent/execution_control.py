"""Turn-level execution budgets and tool recovery state."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
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

_ASSURANCE_META_TOOLS: set[str] = {
    "record_evidence_record",
    "record_analysis_spec",
    "record_analysis_plan",
    "record_data_requirement",
    "record_insight_record",
    "ask_user_question",
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
    synthesis_reserve_tokens: int | None = None
    audit_reserve_tokens: int | None = None
    revision_reserve_tokens: int | None = None
    max_revision_attempts: int = 1

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
        total = max(0, int(self.token_budget or 0))
        if self.synthesis_reserve_tokens is None:
            self.synthesis_reserve_tokens = int(total * 0.08)
        if self.audit_reserve_tokens is None:
            self.audit_reserve_tokens = int(total * 0.05)
        if self.revision_reserve_tokens is None:
            self.revision_reserve_tokens = int(total * 0.07)
        for field_name in (
            "synthesis_reserve_tokens",
            "audit_reserve_tokens",
            "revision_reserve_tokens",
        ):
            setattr(self, field_name, max(0, int(getattr(self, field_name) or 0)))
        self.max_revision_attempts = max(0, int(self.max_revision_attempts))


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
    approximate_runtime_tokens_used: int = 0
    approximate_prompt_tokens: int = 0
    approximate_prompt_component_tokens: dict[str, int] = field(default_factory=dict)
    phase_token_usage: dict[str, int] = field(default_factory=dict)
    phase_overflow_tokens: dict[str, int] = field(default_factory=dict)
    phase_prompt_tokens: dict[str, int] = field(default_factory=dict)
    requested_max_output_tokens: dict[str, int] = field(default_factory=dict)
    prompt_assembly_count: int = 0
    trust_capsule_digest: str = ""
    revision_attempts: int = 0
    turn_id: str = field(default_factory=lambda: f"turn_{uuid.uuid4().hex}")
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

    @property
    def estimated_tokens_used(self) -> int:
        """Compatibility alias for approximate, non-provider usage accounting."""

        return self.approximate_runtime_tokens_used

    @estimated_tokens_used.setter
    def estimated_tokens_used(self, value: int) -> None:
        self.approximate_runtime_tokens_used = max(0, int(value or 0))

    @property
    def exploration_token_budget(self) -> int:
        total = max(0, int(self.budget.token_budget or 0))
        reserved = sum((
            int(self.budget.synthesis_reserve_tokens or 0),
            int(self.budget.audit_reserve_tokens or 0),
            int(self.budget.revision_reserve_tokens or 0),
        ))
        return max(0, total - reserved)

    @property
    def exploration_budget_exhausted(self) -> bool:
        return self.phase_token_usage.get("exploration", 0) >= self.exploration_token_budget

    def record_llm_round(self) -> None:
        self.llm_rounds += 1

    def record_token_usage(self, delta: int, *, phase: str = "exploration") -> None:
        """Record approximate runtime usage without claiming provider billing parity."""

        amount = max(0, int(delta or 0))
        self.approximate_runtime_tokens_used += amount
        limit = self.phase_token_limit(phase)
        used = self.phase_token_usage.get(phase, 0)
        accepted = min(amount, max(0, limit - used))
        self.phase_token_usage[phase] = used + accepted
        overflow = amount - accepted
        if overflow:
            self.phase_overflow_tokens[phase] = self.phase_overflow_tokens.get(phase, 0) + overflow

    def record_prompt_assembly(
        self,
        components: dict[str, Any],
        *,
        assembled_payload: Any | None = None,
        trust_capsule_digest: str = "",
        phase: str = "",
    ) -> None:
        """Measure approximate prompt payload size at assembly time.

        These values are diagnostics derived from serialized characters. They
        are intentionally separate from any provider-reported billed usage.
        """

        measured = {
            str(name): _approximate_payload_tokens(value)
            for name, value in sorted((components or {}).items())
        }
        self.approximate_prompt_component_tokens = measured
        payload = assembled_payload if assembled_payload is not None else components
        self.approximate_prompt_tokens = _approximate_payload_tokens(payload)
        if phase:
            self.phase_prompt_tokens[phase] = self.approximate_prompt_tokens
        self.prompt_assembly_count += 1
        if trust_capsule_digest:
            self.trust_capsule_digest = str(trust_capsule_digest)

    def can_run_phase(self, phase: str) -> bool:
        return self.phase_token_usage.get(phase, 0) < self.phase_token_limit(phase)

    def phase_token_limit(self, phase: str) -> int:
        limits = {
            "exploration": self.exploration_token_budget,
            "synthesis": int(self.budget.synthesis_reserve_tokens or 0),
            "audit": int(self.budget.audit_reserve_tokens or 0),
            "revision": int(self.budget.revision_reserve_tokens or 0),
        }
        return max(0, limits.get(phase, 0))

    def ensure_phase_capacity(self, phase: str) -> None:
        if not self.can_run_phase(phase):
            raise BudgetExceeded(
                f"{phase.capitalize()} token budget reached; do not consume another assurance phase."
            )

    def remaining_phase_tokens(self, phase: str) -> int:
        return max(0, self.phase_token_limit(phase) - self.phase_token_usage.get(phase, 0))

    def output_limit_for_phase(self, phase: str, configured_max: int) -> int:
        self.ensure_phase_capacity(phase)
        limit = max(1, min(int(configured_max), self.remaining_phase_tokens(phase)))
        self.requested_max_output_tokens[phase] = limit
        return limit

    def claim_revision_attempt(self) -> bool:
        if self.revision_attempts >= self.budget.max_revision_attempts:
            return False
        if not self.can_run_phase("revision"):
            return False
        self.revision_attempts += 1
        return True

    def budget_diagnostics(self) -> dict[str, Any]:
        return {
            "token_accounting_kind": "approximate_local_estimate",
            "approximate_runtime_tokens_used": self.approximate_runtime_tokens_used,
            "approximate_prompt_tokens": self.approximate_prompt_tokens,
            "approximate_prompt_component_tokens": dict(self.approximate_prompt_component_tokens),
            "prompt_assembly_count": self.prompt_assembly_count,
            "phase_token_usage": dict(self.phase_token_usage),
            "phase_overflow_tokens": dict(self.phase_overflow_tokens),
            "phase_prompt_tokens": dict(self.phase_prompt_tokens),
            "requested_max_output_tokens": dict(self.requested_max_output_tokens),
            "component_reserves": {
                "exploration": self.exploration_token_budget,
                "synthesis": int(self.budget.synthesis_reserve_tokens or 0),
                "audit": int(self.budget.audit_reserve_tokens or 0),
                "revision": int(self.budget.revision_reserve_tokens or 0),
            },
            "revision_attempts": self.revision_attempts,
            "trust_capsule_digest": self.trust_capsule_digest,
        }

    def ensure_can_call(self, tool_name: str, args: dict[str, Any] | None = None) -> None:
        args = args or {}
        is_meta = tool_name in _META_TOOLS

        # --- Time budget applies to all tools ---
        if self.budget.max_elapsed_seconds is not None and self.elapsed_seconds >= self.budget.max_elapsed_seconds:
            raise BudgetExceeded("Time budget reached; summarize current evidence and stop calling tools.")

        # Meta tools: only error safety checks remain (bypass budget, fallback, resolution)
        if is_meta:
            if self.exploration_budget_exhausted and tool_name not in _ASSURANCE_META_TOOLS:
                raise BudgetExceeded(
                    "Exploration token budget reached; only bounded assurance-recording meta tools remain available."
                )
            key = self._error_key(tool_name, args)
            if self.repeated_errors.get(key, 0) >= self.budget.max_repeated_tool_errors:
                raise BudgetExceeded(f"Repeated tool error for {tool_name}; do not retry the same call.")
            if self.consecutive_errors >= self.budget.max_consecutive_errors:
                raise BudgetExceeded("Consecutive tool errors reached; summarize recovery path instead of calling more tools.")
            return

        # --- Budget checks (non-meta tools) ---
        if self.exploration_budget_exhausted:
            raise BudgetExceeded(
                "Exploration token budget reached; preserve assurance reserves for synthesis, audit, and revision."
            )
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
        if self.tool_calls == 0 and not self.exploration_budget_exhausted:
            return ""
        if self.tool_calls >= (self.budget.max_tool_calls or 0):
            hints.append("Execution budget reached. Stop calling tools and summarize evidence, limits, and next steps.")
        if self.exploration_budget_exhausted:
            hints.append(
                "Exploration budget reached. Stop exploratory tools and preserve assurance reserves for final synthesis, deterministic audit, and at most one revision."
            )
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


def _approximate_payload_tokens(value: Any) -> int:
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return len(raw) // 4


def evaluate_budget_degradation(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Compare assurance invariants across budgets without comparing prose."""

    strength = {
        "diagnostic": 0,
        "exploratory": 1,
        "descriptive": 2,
        "inferential": 3,
        "causal": 4,
    }

    def strongest(outcome: dict[str, Any]) -> int:
        classes = outcome.get("claim_classes")
        if not isinstance(classes, list) or not classes:
            return 0
        return max(strength.get(str(item).strip().lower(), 0) for item in classes)

    baseline_requirements = {
        str(item) for item in baseline.get("retained_requirement_ids") or [] if str(item)
    }
    candidate_requirements = {
        str(item) for item in candidate.get("retained_requirement_ids") or [] if str(item)
    }
    baseline_evidence = {str(item) for item in baseline.get("evidence_ids") or [] if str(item)}
    candidate_evidence = {str(item) for item in candidate.get("evidence_ids") or [] if str(item)}
    audit_status = str(candidate.get("audit_status") or "not_run").lower()
    invariants = {
        "claim_strength_not_increased": strongest(candidate) <= strongest(baseline),
        "requirements_retained": baseline_requirements <= candidate_requirements,
        "evidence_binding_retained": baseline_evidence <= candidate_evidence,
        "audit_was_not_skipped": audit_status in {"pass", "revise", "blocked"},
        "terminated": bool(candidate.get("completed")),
    }
    return {
        "ok": all(invariants.values()),
        "invariants": invariants,
        "baseline_strongest_claim": strongest(baseline),
        "candidate_strongest_claim": strongest(candidate),
        "round_count": candidate.get("round_count"),
        "latency_ms": candidate.get("latency_ms"),
    }
