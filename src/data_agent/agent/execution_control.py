"""Turn-level execution budgets and tool recovery state."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence


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

_FALLBACK_RESOLUTION_TOOLS = frozenset({
    "record_evidence_record",
    "record_analysis_spec",
    "record_analysis_plan",
    "record_data_requirement",
    "record_insight_record",
    "task_update",
    "ask_user_question",
})


def fallback_resolution_tools() -> frozenset[str]:
    """Return the canonical actions that resolve a successful fallback run."""

    return _FALLBACK_RESOLUTION_TOOLS


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
    consecutive_error_recovery_attempted: bool = False
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
    requirement_failures: dict[str, dict[str, Any]] = field(default_factory=dict)
    requirement_recovery: dict[str, dict[str, int]] = field(default_factory=dict)
    analysis_continuations_used: int = 0
    quality_continuation_reason: str = ""
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

    def reclassify_phase_usage(
        self,
        amount: int,
        *,
        source_phase: str,
        target_phase: str,
    ) -> int:
        """Move already-accounted output between assurance phases.

        The provider response type is known only after a round completes.  A
        synthesis-guided response that contains tool calls is still execution,
        so its accepted tokens must not consume the final-answer reserve.  The
        total runtime estimate is unchanged; only phase ownership moves.
        """

        requested = max(0, int(amount or 0))
        source_used = self.phase_token_usage.get(source_phase, 0)
        moved = min(requested, source_used)
        if not moved or source_phase == target_phase:
            return 0
        self.phase_token_usage[source_phase] = source_used - moved
        target_used = self.phase_token_usage.get(target_phase, 0)
        target_limit = self.phase_token_limit(target_phase)
        accepted = min(moved, max(0, target_limit - target_used))
        self.phase_token_usage[target_phase] = target_used + accepted
        overflow = moved - accepted
        if overflow:
            self.phase_overflow_tokens[target_phase] = (
                self.phase_overflow_tokens.get(target_phase, 0) + overflow
            )
        return moved

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
            "analysis_continuations_used": int(self.analysis_continuations_used or 0),
            "quality_continuation_reason": str(self.quality_continuation_reason or ""),
            "requirement_recovery": {
                str(key): dict(value)
                for key, value in self.requirement_recovery.items()
                if isinstance(value, dict)
            },
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
            if not self._allow_changed_error_recovery(key):
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
        if not self._allow_changed_error_recovery(key):
            raise BudgetExceeded("Consecutive tool errors reached; summarize recovery path instead of calling more tools.")

    def _allow_changed_error_recovery(self, key: str) -> bool:
        """Allow one changed call after a burst, never an unbounded retry loop.

        Parallel tool calls are recorded sequentially.  Three independent
        validation errors in one assistant response can therefore trip the
        consecutive-error breaker before the model has seen any result and
        had a chance to correct its arguments.  Permit exactly one previously
        unseen signature to prove recovery; success resets the burst, while a
        failed recovery leaves the breaker closed.
        """

        if self.consecutive_errors < self.budget.max_consecutive_errors:
            return True
        if self.repeated_errors.get(key, 0) > 0:
            return False
        if self.consecutive_error_recovery_attempted:
            return False
        self.consecutive_error_recovery_attempted = True
        return True

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

    def record_tool_success(self, tool_name: str = "") -> None:
        self.consecutive_errors = 0
        self.consecutive_error_recovery_attempted = False
        if tool_name == "run_python":
            self.pending_fallback_resolution = True
        elif tool_name in self._fallback_resolution_tools():
            self.pending_fallback_resolution = False

    def record_requirement_failure(
        self,
        *,
        requirement_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        error_type: str,
    ) -> str:
        """Persist a deterministic fingerprint for one requirement-level failure.

        The fingerprint is a stable digest of ``requirement_id``, ``tool_name``,
        normalized ``arguments`` and ``error_type``. ``attempts`` counts how
        many times this exact signature has been recorded; later budget policy
        (Task 8) consumes it to decide whether to permit another corrected
        retry or block before registry execution.
        """

        canonical = json.dumps(
            {
                "requirement_id": requirement_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "error_type": error_type,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        entry = self.requirement_failures.setdefault(
            fingerprint,
            {
                "attempts": 0,
                "requirement_id": requirement_id,
                "tool_name": tool_name,
                "error_type": error_type,
            },
        )
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        return fingerprint

    def can_retry_failure(self, fingerprint: str) -> bool:
        """Permit the initial failure plus one corrected retry; block the third."""

        return int(self.requirement_failures.get(fingerprint, {}).get("attempts", 0)) < 2

    def can_correct_requirement(self, requirement_id: str) -> bool:
        """One corrected retry per requirement, by Task 8 budget policy."""

        return int(self.requirement_recovery.get(requirement_id, {}).get("corrected_retry", 0)) < 1

    def record_corrected_retry(self, requirement_id: str) -> None:
        entry = self.requirement_recovery.setdefault(requirement_id, {})
        entry["corrected_retry"] = int(entry.get("corrected_retry", 0)) + 1

    def can_use_fallback(self, requirement_id: str) -> bool:
        """One fallback per requirement, by Task 8 budget policy."""

        return int(self.requirement_recovery.get(requirement_id, {}).get("fallback", 0)) < 1

    def record_fallback(self, requirement_id: str) -> None:
        entry = self.requirement_recovery.setdefault(requirement_id, {})
        entry["fallback"] = int(entry.get("fallback", 0)) + 1

    def consume_quality_continuation(self, *, reason: str) -> bool:
        """Allow at most one analysis-quality continuation per turn.

        Surfaces the trigger reason via ``quality_continuation_reason`` so
        downstream diagnostics can replay which requirement forced the
        extra round without re-reading prompt content.
        """

        if int(self.analysis_continuations_used or 0) >= 1:
            return False
        self.analysis_continuations_used = int(self.analysis_continuations_used or 0) + 1
        self.quality_continuation_reason = str(reason or "")
        return True

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
        if self.pending_fallback_resolution:
            allowed = ", ".join(sorted(self._fallback_resolution_tools()))
            hints.append(
                "The previous run_python result is pending resolution. Before any "
                "additional analysis tool, resolve it with exactly one allowed "
                f"evidence, limitation, task, or user-confirmation action: {allowed}. "
                "Do not call run_python again yet."
            )
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
        return set(fallback_resolution_tools())

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


# ---------------------------------------------------------------------------
# Requirement-based bounded completion (Task 8)
# ---------------------------------------------------------------------------

CompletionStatus = Literal[
    "complete",
    "complete_with_limits",
    "blocked_by_data",
    "blocked_by_tool",
    "budget_limited",
]


@dataclass(frozen=True)
class CompletionDecision:
    """Orchestration result of :func:`evaluate_analysis_completion`.

    The decision is one of five terminal statuses plus a per-requirement
    breakdown used by the loop to inject one targeted recovery instruction.
    The loop never re-evaluates requirements itself; it consumes this
    decision's ``allow_analysis_continuation`` and ``recoverable_requirement_ids``.
    """

    status: CompletionStatus
    is_terminal: bool
    supported_claim_class: str
    satisfied_requirement_ids: tuple[str, ...]
    unmet_requirement_ids: tuple[str, ...]
    recoverable_requirement_ids: tuple[str, ...]
    allow_analysis_continuation: bool
    reason_code: str
    diagnostics: tuple[dict[str, Any], ...]


_CLAIM_CLASS_STRENGTH: dict[str, int] = {
    "exploratory_association": 1,
    "inferential_associations": 2,
    "predictive_importance": 3,
    "causal_effect": 4,
}

# Task 7 non-canonical markers and capability declarations are remapped to the
# strict claim-class enumeration used by the completion evaluator. The mapping
# is intentionally one-way (never strengthening): ``association_only`` and
# ``descriptive_attribution`` collapse to ``exploratory_association`` so the
# evaluator cannot accidentally upgrade a playbook ceiling.
_CLAIM_CLASS_REMAP: dict[str, str] = {
    "association_only": "exploratory_association",
    "descriptive_attribution": "exploratory_association",
    "association": "exploratory_association",
    "descriptive": "exploratory_association",
    "diagnostic": "exploratory_association",
}

_CAPABILITY_CLAIM_CLASS: dict[str, str] = {
    "analysis.experiment": "causal_effect",
    "analysis.causal": "causal_effect",
    "analysis.regression": "predictive_importance",
    "analysis.factor_relationship": "inferential_associations",
    "analysis.group_compare": "inferential_associations",
    "analysis.segment_compare": "inferential_associations",
    "analysis.period_compare": "inferential_associations",
    "analysis.correlation": "exploratory_association",
    "analysis.time_series": "exploratory_association",
    "data.profile": "exploratory_association",
}

_PUBLICATION_REQUIREMENT_CATEGORIES = frozenset({"limitation", "output", "provenance"})


def _canonical_claim_class(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in _CLAIM_CLASS_REMAP:
        return _CLAIM_CLASS_REMAP[text]
    if text in _CLAIM_CLASS_STRENGTH:
        return text
    return None


@dataclass(frozen=True)
class ClaimClassAuthority:
    """Canonical claim permission resolved against one declared ceiling."""

    declared: str
    canonical: str
    ceiling: str
    valid: bool
    causal_authorized: bool
    reason: str = ""


def resolve_claim_class_authority(
    value: Any,
    *,
    ceiling: Any,
) -> ClaimClassAuthority:
    """Validate and canonicalize a claim attestation without strengthening it."""

    declared = str(value or "").strip().lower()
    canonical = _canonical_claim_class(declared)
    canonical_ceiling = _canonical_claim_class(ceiling)
    if canonical is None:
        return ClaimClassAuthority(
            declared=declared,
            canonical="",
            ceiling=canonical_ceiling or "",
            valid=False,
            causal_authorized=False,
            reason="unknown_or_empty_claim_class",
        )
    if canonical_ceiling is None:
        return ClaimClassAuthority(
            declared=declared,
            canonical=canonical,
            ceiling="",
            valid=False,
            causal_authorized=False,
            reason="invalid_claim_class_ceiling",
        )
    if _CLAIM_CLASS_STRENGTH[canonical] > _CLAIM_CLASS_STRENGTH[canonical_ceiling]:
        return ClaimClassAuthority(
            declared=declared,
            canonical=canonical,
            ceiling=canonical_ceiling,
            valid=False,
            causal_authorized=False,
            reason="claim_class_exceeds_ceiling",
        )
    return ClaimClassAuthority(
        declared=declared,
        canonical=canonical,
        ceiling=canonical_ceiling,
        valid=True,
        causal_authorized=canonical == "causal_effect",
    )


def _claim_strength(value: Any) -> int:
    canonical = _canonical_claim_class(value)
    if canonical is None:
        return 0
    return _CLAIM_CLASS_STRENGTH[canonical]


def _supported_claim_class_from_refs(
    plan: dict[str, Any],
    successful_refs: list[dict[str, Any]],
) -> str:
    """Derive the strongest evidence-supported claim class.

    The plan declares a ceiling (``maximum_claim_class``). Each successful
    computation ref contributes a capability-derived claim class. The
    supported class is the minimum of the ceiling and the strongest
    capability class actually observed — never stronger than the plan allows
    and never stronger than what the executed capability warrants.
    """

    ceiling = _canonical_claim_class(plan.get("maximum_claim_class")) if isinstance(plan, dict) else None
    strongest_capability_strength = 0
    for ref in successful_refs:
        declared = ""
        if isinstance(ref, dict):
            declared = (
                ref.get("allowed_claim_class")
                or ref.get("claim_class")
                or _CAPABILITY_CLAIM_CLASS.get(str(ref.get("capability_id") or ""))
                or ""
            )
        strength = _claim_strength(declared)
        if strength > strongest_capability_strength:
            strongest_capability_strength = strength
    if strongest_capability_strength == 0:
        supported_strength = 0
    elif ceiling is None:
        supported_strength = strongest_capability_strength
    else:
        supported_strength = min(strongest_capability_strength, _CLAIM_CLASS_STRENGTH[ceiling])
    if supported_strength == 0:
        return "exploratory_association"
    for name, strength in _CLAIM_CLASS_STRENGTH.items():
        if strength == supported_strength:
            return name
    return "exploratory_association"


def _downgrade_claim_on_failure(claim_class: str) -> str:
    """Never report ``causal_effect`` after a tool/data/budget failure."""

    canonical = _canonical_claim_class(claim_class) or "exploratory_association"
    if canonical == "causal_effect":
        return "inferential_associations"
    if canonical == "predictive_importance":
        return "inferential_associations"
    if canonical == "inferential_associations":
        return "exploratory_association"
    return canonical


def _is_projection_failure(
    requirement: dict[str, Any],
    successful_refs: list[dict[str, Any]],
) -> bool:
    """A successful computation already covered this requirement's evidence.

    If the requirement is still unmet despite a successful binding, the gap
    is publication (projection/presentation), not computation. Task 8 forbids
    recomputation in that case.
    """

    requirement_id = str(requirement.get("id") or "")
    if not requirement_id:
        return False
    for ref in successful_refs:
        requirement_ids = ref.get("requirement_ids")
        if isinstance(requirement_ids, list) and requirement_id in requirement_ids:
            return True
    return False


def _categorize_execution_failures(
    computation_refs: list[dict[str, Any]],
    tool_outcomes: list[dict[str, Any]],
) -> tuple[bool, bool, list[dict[str, Any]]]:
    """Return ``(has_data_failure, has_tool_failure, diagnostics)."""

    diagnostics: list[dict[str, Any]] = []
    data_failure = False
    tool_failure = False
    for ref in computation_refs:
        binding_error = str(ref.get("binding_error_type") or "")
        if not binding_error:
            continue
        if binding_error == "missing_column_or_data" or "missing_column_or_data" in binding_error:
            data_failure = True
            diagnostics.append({
                "source": "computation_ref",
                "tool_call_id": str(ref.get("tool_call_id") or ""),
                "binding_error_type": binding_error,
                "category": "missing_data",
            })
        elif binding_error and binding_error != "analysis_step_not_bound":
            tool_failure = True
            diagnostics.append({
                "source": "computation_ref",
                "tool_call_id": str(ref.get("tool_call_id") or ""),
                "binding_error_type": binding_error,
                "category": "tool_failure",
            })
    for outcome in tool_outcomes:
        if outcome.get("success") is False:
            category = str(outcome.get("error_category") or "tool_error").lower()
            if category == "missing_column_or_data":
                data_failure = True
            elif category == "insufficient_data":
                data_failure = True
            else:
                tool_failure = True
            diagnostics.append({
                "source": "tool_outcome",
                "tool_call_id": str(outcome.get("tool_call_id") or ""),
                "tool_name": str(outcome.get("tool_name") or ""),
                "error_category": category,
            })
    return data_failure, tool_failure, diagnostics


def _recoverable_requirement_ids(
    unmet: list[dict[str, Any]],
    successful_refs: list[dict[str, Any]],
    turn_state: TurnExecutionState,
    *,
    continuation_available: bool,
    evidence_records: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Classify recoverability independently for each unmet requirement.

    Evidence for one requirement cannot turn separate execution obligations
    into publication gaps. A requirement is projection-only only when its own
    successful computation ref is present; incomplete or unrelated evidence
    does not suppress the bounded execution continuation.
    """

    diagnostics: list[dict[str, Any]] = []
    if not continuation_available:
        for requirement in unmet:
            diagnostics.append({
                "requirement_id": str(requirement.get("id") or ""),
                "recoverable": False,
                "reason": "no_continuation_budget",
            })
        return [], diagnostics
    recoverable: list[str] = []
    for requirement in unmet:
        requirement_id = str(requirement.get("id") or "")
        if not requirement_id:
            continue
        category = str(requirement.get("category") or "").strip().lower()
        bound_incomplete_evidence_count = sum(
            1
            for record in evidence_records or []
            if requirement_id in (
                record.get("requirement_ids")
                if isinstance(record.get("requirement_ids"), list)
                else []
            )
        )
        if category in _PUBLICATION_REQUIREMENT_CATEGORIES:
            diagnostics.append({
                "requirement_id": requirement_id,
                "recoverable": False,
                "reason": "publication_only",
                "bound_incomplete_evidence_count": bound_incomplete_evidence_count,
            })
            continue
        if _is_projection_failure(requirement, successful_refs):
            diagnostics.append({
                "requirement_id": requirement_id,
                "recoverable": False,
                "reason": "projection_missing",
                "bound_incomplete_evidence_count": bound_incomplete_evidence_count,
            })
            continue
        retry_available = (
            turn_state.can_correct_requirement(requirement_id)
            or turn_state.can_use_fallback(requirement_id)
        )
        if not retry_available:
            diagnostics.append({
                "requirement_id": requirement_id,
                "recoverable": False,
                "reason": "recovery_budget_exhausted",
                "bound_incomplete_evidence_count": bound_incomplete_evidence_count,
            })
            continue
        recoverable.append(requirement_id)
        diagnostics.append({
            "requirement_id": requirement_id,
            "recoverable": True,
            "reason": "execution_unmet",
            "bound_incomplete_evidence_count": bound_incomplete_evidence_count,
        })
    return recoverable, diagnostics


def evaluate_analysis_completion(
    plan: dict[str, Any] | None,
    requirements: Sequence[dict[str, Any]],
    computation_refs: Sequence[dict[str, Any]],
    evidence_records: Sequence[dict[str, Any]],
    tool_outcomes: Sequence[dict[str, Any]],
    turn_state: TurnExecutionState,
    budget_exhausted: bool,
) -> CompletionDecision:
    """Derive one of five terminal completion states from canonical evidence.

    The evaluator is orchestration only: requirement semantics come from
    :func:`evaluate_requirement_satisfaction`; per-requirement retry and
    fallback budgets come from :class:`TurnExecutionState`. It separately
    derives execution obligations (plan steps attempted; critical tools
    succeeded) from publication obligations (eligible evidence projected;
    unsupported claim classes excluded).

    A publication obligation failure never returns the loop to tool-running:
    successful traceable computation but missing projection/presentation
    yields ``complete_with_limits`` with ``allow_analysis_continuation=False``.
    """

    from data_agent.agent.analysis_requirements import evaluate_requirement_satisfaction

    plan_value = plan if isinstance(plan, dict) else {}
    requirements_list = [item for item in requirements if isinstance(item, dict)]
    refs_list = [item for item in computation_refs if isinstance(item, dict)]
    evidence_list = [item for item in evidence_records if isinstance(item, dict)]
    outcomes_list = [item for item in tool_outcomes if isinstance(item, dict)]

    evaluated = evaluate_requirement_satisfaction(requirements_list, evidence_list)
    satisfied_ids = tuple(
        str(item.get("id"))
        for item in evaluated
        if item.get("status") == "satisfied" and str(item.get("id") or "")
    )
    unmet_requirements = [
        item for item in evaluated if item.get("status") == "unmet"
    ]
    unmet_ids = tuple(
        str(item.get("id"))
        for item in unmet_requirements
        if str(item.get("id") or "")
    )

    successful_refs = [item for item in refs_list if item.get("success") is True]
    supported_claim_class = _supported_claim_class_from_refs(plan_value, successful_refs)
    has_data_failure, has_tool_failure, failure_diagnostics = _categorize_execution_failures(
        refs_list, outcomes_list
    )
    continuation_available = int(getattr(turn_state, "analysis_continuations_used", 0) or 0) < 1
    recoverable_ids, recovery_diagnostics = _recoverable_requirement_ids(
        unmet_requirements,
        successful_refs,
        turn_state,
        continuation_available=continuation_available,
        evidence_records=evidence_list,
    )

    def _decision(
        *,
        status: CompletionStatus,
        reason_code: str,
        allow_analysis_continuation: bool,
        supported_class: str | None = None,
        recoverable: tuple[str, ...] | None = None,
        extra_diagnostics: tuple[dict[str, Any], ...] = (),
    ) -> CompletionDecision:
        return CompletionDecision(
            status=status,
            is_terminal=True,
            supported_claim_class=supported_class or supported_claim_class,
            satisfied_requirement_ids=satisfied_ids,
            unmet_requirement_ids=unmet_ids,
            recoverable_requirement_ids=(
                recoverable if recoverable is not None else tuple(recoverable_ids)
            ),
            allow_analysis_continuation=allow_analysis_continuation,
            reason_code=reason_code,
            diagnostics=(*failure_diagnostics, *recovery_diagnostics, *extra_diagnostics),
        )

    if budget_exhausted:
        return _decision(
            status="budget_limited",
            reason_code="budget_exhausted",
            allow_analysis_continuation=False,
            supported_class=_downgrade_claim_on_failure(supported_claim_class),
            recoverable=(),
            extra_diagnostics=(
                {
                    "budget_exhausted": True,
                    "unmet_requirement_count": len(unmet_ids),
                },
            ),
        )

    if not successful_refs:
        # No traceable computation ref. If the agent still produced recorded
        # evidence (e.g. via meta tools), treat that as successful computation:
        # the loop has already chosen its publication path and the evaluator
        # must not reactivate tools for projection-only gaps.
        if not evidence_list:
            # Nothing ran successfully: classify the blocker.
            if has_data_failure:
                status: CompletionStatus = "blocked_by_data"
                reason_code = "missing_required_data"
            elif has_tool_failure:
                status = "blocked_by_tool"
                reason_code = "critical_tool_failed"
            elif unmet_ids:
                status = "blocked_by_tool"
                reason_code = "execution_obligations_not_attempted"
            else:
                status = "complete_with_limits"
                reason_code = "no_traceable_computation"
            return _decision(
                status=status,
                reason_code=reason_code,
                allow_analysis_continuation=bool(recoverable_ids),
                supported_class=_downgrade_claim_on_failure(supported_claim_class),
            )
        # Evidence was recorded but no traceable ref exists. Recoverable
        # unmet requirements still allow one continuation; otherwise publish
        # with limits.
        if not unmet_ids:
            return _decision(
                status="complete",
                reason_code="requirements_satisfied_via_recorded_evidence",
                allow_analysis_continuation=False,
            )
        if recoverable_ids:
            return _decision(
                status="complete_with_limits",
                reason_code="recoverable_unmet_requirements",
                allow_analysis_continuation=True,
            )
        return _decision(
            status="complete_with_limits",
            reason_code="unrecoverable_unmet_requirements",
            allow_analysis_continuation=False,
            recoverable=(),
        )

    # Has successful computation. Publication failures never reactivate tools.
    if not unmet_ids:
        return _decision(
            status="complete",
            reason_code="requirements_satisfied",
            allow_analysis_continuation=False,
        )

    if recoverable_ids:
        # Execution obligations remain and one continuation is still available.
        # If the recovery fails, the loop publishes with limits.
        return _decision(
            status="complete_with_limits",
            reason_code="recoverable_unmet_requirements",
            allow_analysis_continuation=True,
        )

    # Unmet requirements are publication-only or have their recovery budget
    # exhausted. Either way the loop must publish with limits and may not
    # reactivate tools.
    reason = (
        "unrecoverable_publication_failure"
        if all(
            str(req.get("category") or "") in _PUBLICATION_REQUIREMENT_CATEGORIES
            or _is_projection_failure(req, successful_refs)
            for req in unmet_requirements
        )
        else "recovery_budget_exhausted"
    )
    return _decision(
        status="complete_with_limits",
        reason_code=reason,
        allow_analysis_continuation=False,
        recoverable=(),
    )


def _approximate_payload_tokens(value: Any) -> int:
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return len(raw) // 4


def evidence_semantic_bindings(
    evidence_records: Sequence[dict[str, Any]],
    *,
    selected_measurement_keys: Sequence[str],
) -> list[str]:
    """Project selected evidence grain into stable cross-session bindings."""

    from data_agent.agent.evidence_contracts import (
        computation_ref_key,
        validate_evidence_record,
    )

    requested_keys = {
        str(item)
        for item in selected_measurement_keys
        if str(item)
    }
    bindings = []
    for candidate in evidence_records:
        validation = validate_evidence_record(
            candidate,
            current_plan_id=str(candidate.get("plan_id") or ""),
            require_measurement_identity=True,
        )
        if not validation.ok:
            continue
        record = validation.record
        refs_by_key = {
            computation_ref_key(ref): ref
            for ref in record.get("computation_refs") or []
            if isinstance(ref, dict)
        }
        for measurement in record.get("measurements") or []:
            if not isinstance(measurement, dict):
                continue
            identity = measurement.get("identity")
            if not isinstance(identity, dict):
                continue
            raw_measurement_key = str(identity.get("measurement_key") or "")
            if raw_measurement_key not in requested_keys:
                continue
            ref = refs_by_key.get(str(identity.get("computation_ref_id") or ""))
            if not isinstance(ref, dict):
                continue
            computation_identity = {
                "contract_version": str(ref.get("contract_version") or ""),
                "tool_name": str(ref.get("tool_name") or ""),
                "capability_id": str(ref.get("capability_id") or ""),
                "arguments_digest": str(ref.get("arguments_digest") or ""),
                "output_digest": str(ref.get("output_digest") or ""),
                "plan_id": str(ref.get("plan_id") or ""),
                "plan_digest": str(ref.get("plan_digest") or ""),
                "step_id": str(ref.get("step_id") or ""),
                "step_digest": str(ref.get("step_digest") or ""),
                "dataset_versions": sorted(
                    str(item) for item in ref.get("dataset_versions") or []
                ),
                "success": bool(ref.get("success", True)),
                "structured_checked_fields": sorted(
                    str(item)
                    for item in ref.get("structured_checked_fields") or []
                ),
                "verification_level": str(ref.get("verification_level") or ""),
                "claim_key": str(ref.get("claim_key") or ""),
                "requirement_ids": sorted(
                    str(item) for item in ref.get("requirement_ids") or []
                ),
            }
            stable_identity = {
                str(key): value
                for key, value in identity.items()
                if key not in {"measurement_key", "computation_ref_id"}
            }
            stable_identity["computation_identity"] = computation_identity
            stable_measurement_key = "sm_" + hashlib.sha256(
                json.dumps(
                    stable_identity,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()[:24]
            binding = {
                "contract_version": "evidence_semantic_binding.v1",
                "plan_id": str(record.get("plan_id") or ""),
                "step_id": str(record.get("step_id") or ""),
                "claim_key": str(record.get("claim_key") or ""),
                "dataset_versions": sorted(
                    str(item) for item in record.get("dataset_versions") or []
                ),
                "computation_identity": computation_identity,
                "selected_measurement_key": stable_measurement_key,
                "selected_measurement_identity": stable_identity,
            }
            bindings.append(
                "eb_" + hashlib.sha256(
                    json.dumps(
                        binding,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ).encode("utf-8")
                ).hexdigest()[:32]
            )
    return sorted(set(bindings))


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
