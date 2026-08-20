from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


JOURNEY_VERSION = "v2_provider_neutral_browser_journey.v1"
JOURNEY_FIXTURE_ID = "v2_workbench_planning_failure_retry.v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

# Each checkpoint declares the exact cumulative number of deterministic fake
# Planner invocations and one-call authorization records. The validator treats
# any additional invocation as a hidden retry.
PROVIDER_NEUTRAL_CHECKPOINTS = (
    ("loaded", 0, 0, 0),
    ("estimated", 0, 0, 0),
    ("needs_input", 1, 1, 1),
    ("answer_estimated", 1, 1, 1),
    ("failed", 2, 2, 2),
    ("failure_stable", 2, 2, 2),
    ("retry_estimated", 2, 2, 2),
    ("completed", 3, 3, 3),
    ("refreshed", 3, 3, 3),
)

_OBSERVED_INTERACTIONS = (
    "upload",
    "planning_estimate_without_authorization",
    "explicit_planning_confirmation",
    "needs_input",
    "planning_answer_persisted",
    "planning_failure_stable",
    "explicit_planning_retry",
    "live_progress",
    "task_overlay_collapsed",
    "refresh_restore",
)


@dataclass(frozen=True, slots=True)
class BrowserJourneyValidation:
    passed: bool
    reason_codes: tuple[str, ...]
    observed_interactions: tuple[str, ...] = ()


def _nonnegative_integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def validate_provider_neutral_journey(
    receipt: Any,
    *,
    expected_source_digest: str,
) -> BrowserJourneyValidation:
    """Validate actual-browser observations without implying product readiness."""

    if not isinstance(receipt, dict):
        return BrowserJourneyValidation(False, ("invalid_browser_journey",))

    reasons: list[str] = []
    if receipt.get("version") != JOURNEY_VERSION:
        reasons.append("invalid_browser_journey_version")
    if receipt.get("observer") != "actual_browser":
        reasons.append("actual_browser_observer_required")
    if receipt.get("fixture_id") != JOURNEY_FIXTURE_ID:
        reasons.append("invalid_browser_journey_fixture")
    source_digest = receipt.get("source_digest")
    if not isinstance(source_digest, str) or not _SHA256.fullmatch(source_digest):
        reasons.append("invalid_browser_journey_source_digest")
    elif source_digest != expected_source_digest:
        reasons.append("stale_browser_journey")
    if receipt.get("scenario_id") != "unified_analysis_entry":
        reasons.append("invalid_browser_journey_scenario")
    if receipt.get("provider_calls") != 0:
        reasons.append("real_provider_call_in_provider_neutral_journey")
    console_errors = receipt.get("console_errors")
    if not isinstance(console_errors, list) or console_errors:
        reasons.append("browser_console_error")

    answer_characters = receipt.get("answer_characters")
    before_digest = receipt.get("answer_before_digest")
    after_digest = receipt.get("answer_after_digest")
    if (
        not _nonnegative_integer(answer_characters)
        or answer_characters == 0
        or not isinstance(before_digest, str)
        or not _SHA256.fullmatch(before_digest)
        or before_digest != after_digest
    ):
        reasons.append("full_planning_answer_not_observed")

    checkpoints = receipt.get("checkpoints")
    if not isinstance(checkpoints, list):
        reasons.append("invalid_browser_checkpoints")
        checkpoints = []
    if len(checkpoints) != len(PROVIDER_NEUTRAL_CHECKPOINTS):
        reasons.append("invalid_browser_checkpoint_sequence")
    for observed, expected in zip(checkpoints, PROVIDER_NEUTRAL_CHECKPOINTS):
        name, planner_calls, issued, consumed = expected
        if not isinstance(observed, dict) or observed.get("name") != name:
            reasons.append("invalid_browser_checkpoint_sequence")
            continue
        if (
            observed.get("planner_invocations") != planner_calls
            or observed.get("authorizations_issued") != issued
            or observed.get("authorizations_consumed") != consumed
        ):
            reasons.append("invalid_checkpoint_counts")
        if not str(observed.get("visible_state") or "").strip():
            reasons.append("missing_visible_browser_state")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return BrowserJourneyValidation(
        passed=not unique_reasons,
        reason_codes=unique_reasons,
        observed_interactions=_OBSERVED_INTERACTIONS if not unique_reasons else (),
    )
