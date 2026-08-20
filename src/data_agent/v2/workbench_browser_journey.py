from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from data_agent.v2.release import (
    LayerStatus,
    ReleaseReceipt,
    ScenarioRequirement,
    ValidationLayer,
)


JOURNEY_VERSION = "v2_provider_neutral_browser_journey.v1"
JOURNEY_FIXTURE_ID = "v2_workbench_planning_failure_retry.v1"
INTERACTION_JOURNEY_VERSION = "v2_provider_neutral_interaction_journey.v1"
INTERACTION_FIXTURE_ID = "v2_workbench_interactions.v1"
UNIFIED_DATASET_FIXTURE = "tests/fixtures/v2_slice4d_combined.csv"
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

_REQUIRED_INTERACTION_OBSERVATIONS = (
    "upload",
    "live_progress",
    "draft_while_running",
    "queued_steer_persisted",
    "queued_steer_completed",
    "stop_receipt_persisted",
    "turn_interrupted",
    "no_final_after_interrupt",
    "task_overlay_collapsed",
    "refresh_completed_restore",
    "refresh_interrupted_restore",
    "session_isolation",
    "error_recovery",
)

_INTERACTION_NAMES = (
    "upload",
    "live_progress",
    "draft_while_running",
    "queued_steer",
    "stop",
    "error_recovery",
    "session_isolation",
    "task_overlay_collapsed",
    "refresh_restore",
)


@dataclass(frozen=True, slots=True)
class BrowserJourneyValidation:
    passed: bool
    reason_codes: tuple[str, ...]
    observed_interactions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowserReleaseComposition:
    passed: bool
    reason_codes: tuple[str, ...]
    receipts: tuple[ReleaseReceipt, ...] = ()


def _nonnegative_integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _validate_dataset_fixture(receipt: dict[str, Any], reasons: list[str]) -> None:
    if receipt.get("fixture_path") != UNIFIED_DATASET_FIXTURE:
        reasons.append("wrong_browser_dataset_fixture")


def _evidence_ref(kind: str, receipt: dict[str, Any]) -> str:
    serialized = json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"actual-browser:{kind}:sha256:{hashlib.sha256(serialized).hexdigest()}"


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
    _validate_dataset_fixture(receipt, reasons)
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
    if (
        receipt.get("chart_observation") != "rendered"
        or not _nonnegative_integer(receipt.get("chart_count"))
        or receipt.get("chart_count") < 1
    ):
        reasons.append("required_inline_chart_not_observed")

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


def validate_provider_neutral_interaction_journey(
    receipt: Any,
    *,
    expected_source_digest: str,
) -> BrowserJourneyValidation:
    """Validate the actual-DOM stop, steer, refresh, and isolation journey."""

    if not isinstance(receipt, dict):
        return BrowserJourneyValidation(False, ("invalid_browser_journey",))
    reasons: list[str] = []
    if receipt.get("version") != INTERACTION_JOURNEY_VERSION:
        reasons.append("invalid_browser_journey_version")
    if receipt.get("observer") != "actual_browser":
        reasons.append("actual_browser_observer_required")
    if receipt.get("fixture_id") != INTERACTION_FIXTURE_ID:
        reasons.append("invalid_browser_journey_fixture")
    _validate_dataset_fixture(receipt, reasons)
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

    sessions = receipt.get("sessions")
    if not isinstance(sessions, dict):
        reasons.append("invalid_browser_sessions")
    else:
        identities = tuple(str(sessions.get(key) or "").strip() for key in ("steer", "stop", "isolation"))
        if not all(identities) or len(set(identities)) != len(identities):
            reasons.append("browser_sessions_not_isolated")

    observations = receipt.get("observations")
    if not isinstance(observations, dict):
        reasons.append("invalid_browser_observations")
        observations = {}
    for name in _REQUIRED_INTERACTION_OBSERVATIONS:
        if observations.get(name) is not True:
            reasons.append(f"missing_browser_interaction:{name}")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return BrowserJourneyValidation(
        passed=not unique_reasons,
        reason_codes=unique_reasons,
        observed_interactions=_INTERACTION_NAMES if not unique_reasons else (),
    )


def compose_provider_neutral_workbench_release_receipts(
    planning_receipt: Any,
    interaction_receipt: Any,
    *,
    scenario: ScenarioRequirement,
    expected_source_digest: str,
) -> BrowserReleaseComposition:
    """Combine two actual-browser observations without broadening their claims."""

    planning = validate_provider_neutral_journey(
        planning_receipt, expected_source_digest=expected_source_digest
    )
    interaction = validate_provider_neutral_interaction_journey(
        interaction_receipt, expected_source_digest=expected_source_digest
    )
    reasons = [*planning.reason_codes, *interaction.reason_codes]
    if scenario.scenario_id != "unified_analysis_entry":
        reasons.append("invalid_release_scenario")
    if scenario.fixture.replace("\\", "/") != UNIFIED_DATASET_FIXTURE:
        reasons.append("invalid_release_scenario_fixture")

    observed = tuple(
        dict.fromkeys((*planning.observed_interactions, *interaction.observed_interactions))
    )
    if not set(observed) >= set(scenario.required_interactions):
        reasons.append("combined_browser_interactions_incomplete")
    if not isinstance(planning_receipt, dict) or not isinstance(interaction_receipt, dict):
        reasons.append("invalid_browser_journey")

    unique_reasons = tuple(dict.fromkeys(reasons))
    if unique_reasons:
        return BrowserReleaseComposition(False, unique_reasons)

    evidence_refs = (
        _evidence_ref("planning", planning_receipt),
        _evidence_ref("interaction", interaction_receipt),
    )
    identity_seed = "|".join(evidence_refs).encode("utf-8")
    identity = hashlib.sha256(identity_seed).hexdigest()[:16]
    browser = ReleaseReceipt(
        receipt_id=f"receipt_unified_browser_{identity}",
        source_digest=expected_source_digest,
        scenario_id=scenario.scenario_id,
        layer=ValidationLayer.BROWSER_INTERACTION_JOURNEY,
        status=LayerStatus.PASS,
        evidence_refs=evidence_refs,
        oracle_identity="v2_provider_neutral_workbench_composer.v1",
        observed_interactions=observed,
        chart_observation=planning_receipt["chart_observation"],
    )
    refresh = ReleaseReceipt(
        receipt_id=f"receipt_unified_refresh_{identity}",
        source_digest=expected_source_digest,
        scenario_id=scenario.scenario_id,
        layer=ValidationLayer.REFRESH_PERSISTENCE_JOURNEY,
        status=LayerStatus.PASS,
        evidence_refs=evidence_refs,
        oracle_identity="v2_provider_neutral_workbench_composer.v1",
        observed_interactions=("refresh_restore",),
    )
    return BrowserReleaseComposition(True, (), (browser, refresh))
