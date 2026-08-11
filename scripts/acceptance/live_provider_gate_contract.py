"""Shared contract for the three-run real-provider analysis gate."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from scripts.acceptance.browser_gate_contract import (
    validate_browser_user_journey_receipt,
)
from scripts.acceptance.real_user_journey_oracles import (
    scenario_oracle_names,
    scenario_prompt_digest,
    scenario_risk_selection,
)


LIVE_PROVIDER_GATE_VERSION = "analysis_live_provider_gate.v1"
LIVE_USER_JOURNEY_GATE_VERSION = "analysis_live_user_journey.v2"
LIVE_REQUIREMENT_GROUPS = (
    "data_quality",
    "descriptive",
    "relationship",
    "limitations",
)
_TOP_LEVEL_FIELDS = frozenset(
    {
        "contract_version",
        "status",
        "reason_codes",
        "accepted",
        "overall_status",
        "live_provider_status",
        "source_digest",
        "source_commit",
        "provider_model",
        "runs",
    }
)
_RUN_FIELDS = frozenset(
    {
        "run_id",
        "status",
        "reason_codes",
        "upload_contract_active",
        "tool_calls",
        "data_quality_computations",
        "structured_computations",
        "projected_evidence",
        "final_audit_status",
        "publication_actions",
        "publication_length",
        "publication_language",
        "has_findings",
        "has_recommendations",
        "has_limitations",
        "generic_warning_present",
        "progress_before_final",
        "persisted_matches_streamed",
        "repeated_failure_max",
        "unresolved_fallback_blocked_calls",
        "verified_material_claims",
        "measurement_bookkeeping_scheduled_analysis",
        "requirements",
    }
)
_PUBLICATION_ACTIONS = frozenset({"verified", "exploratory", "unsupported"})
_REQUIREMENT_VALUES = frozenset({"satisfied", "limited", "missing"})
_CLAIM_ID_RE = re.compile(r"^claim_[A-Za-z0-9_.:-]{1,80}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SCENARIO_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,79}$")
_V2_TOP_LEVEL_FIELDS = frozenset({
    "contract_version",
    "status",
    "reason_codes",
    "accepted",
    "source_digest",
    "source_commit",
    "provider_model",
    "selection",
    "authorization",
    "runs",
})
_V2_RUN_FIELDS = frozenset({
    "scenario_id",
    "status",
    "provider_session_index",
    "browser_journey",
    "human_review",
})
_V2_SELECTION_FIELDS = frozenset({"risk_class", "required_scenario_ids"})
_V2_AUTHORIZATION_FIELDS = frozenset({"max_sessions", "used_sessions", "policy"})
_V2_HUMAN_REVIEW_FIELDS = frozenset({
    "question_understood",
    "method_appropriate",
    "claim_strength_appropriate",
    "limitations_material",
})
_RISK_SCENARIOS = scenario_risk_selection()


@dataclass(frozen=True)
class LiveProviderGateValidation:
    status: str
    reason_codes: tuple[str, ...] = ()


def _integer(value: Any) -> int:
    return value if type(value) is int else -1


def _run_privacy_reason_codes(run: Any) -> list[str]:
    if not isinstance(run, dict):
        return ["unsafe_live_run_field"]
    reasons: list[str] = []
    if set(run) - _RUN_FIELDS:
        reasons.append("unsafe_live_run_field")
    actions = run.get("publication_actions")
    if actions is not None and not isinstance(actions, dict):
        reasons.append("unsafe_live_publication_action")
    elif isinstance(actions, dict) and any(
        not isinstance(claim_id, str)
        or not _CLAIM_ID_RE.fullmatch(claim_id)
        or action not in _PUBLICATION_ACTIONS
        for claim_id, action in actions.items()
    ):
        reasons.append("unsafe_live_publication_action")
    requirements = run.get("requirements")
    if requirements is not None and (
        not isinstance(requirements, dict)
        or set(requirements) - set(LIVE_REQUIREMENT_GROUPS)
        or any(value not in _REQUIREMENT_VALUES for value in requirements.values())
    ):
        reasons.append("unsafe_live_requirement_field")
    return reasons


def evaluate_live_provider_run(run: Any) -> dict[str, Any]:
    """Evaluate bounded run observables against the release thresholds."""

    source = copy.deepcopy(run) if isinstance(run, dict) else {}
    privacy_reasons = _run_privacy_reason_codes(source)
    sanitized = {
        key: copy.deepcopy(value)
        for key, value in source.items()
        if key in _RUN_FIELDS
    }
    raw_actions = sanitized.get("publication_actions")
    sanitized["publication_actions"] = (
        {
            str(claim_id): str(action)
            for claim_id, action in raw_actions.items()
            if isinstance(claim_id, str)
            and _CLAIM_ID_RE.fullmatch(claim_id)
            and action in _PUBLICATION_ACTIONS
        }
        if isinstance(raw_actions, dict)
        else {}
    )
    raw_requirements = sanitized.get("requirements")
    sanitized["requirements"] = (
        {
            name: value if value in _REQUIREMENT_VALUES else "missing"
            for name, value in raw_requirements.items()
            if name in LIVE_REQUIREMENT_GROUPS
        }
        if isinstance(raw_requirements, dict)
        else {}
    )
    raw_reasons = sanitized.get("reason_codes")
    reasons = (
        [str(code) for code in raw_reasons if isinstance(code, str) and code]
        if isinstance(raw_reasons, list)
        else ["invalid_live_run_reason_codes"]
    )
    reasons.extend(privacy_reasons)
    if sanitized.get("status") != "PASS":
        reasons.append("provider_run_failed")
    if sanitized.get("upload_contract_active") is not True:
        reasons.append("upload_contract_missing")
    if _integer(sanitized.get("data_quality_computations")) < 1:
        reasons.append("data_quality_computation_missing")
    if _integer(sanitized.get("structured_computations")) < 2:
        reasons.append("structured_computation_depth_missing")
    if _integer(sanitized.get("projected_evidence")) < 1:
        reasons.append("projected_evidence_missing")
    audit_passed = sanitized.get("final_audit_status") == "pass"
    publication_actions = sanitized.get("publication_actions")
    exploratory_published = bool(
        isinstance(publication_actions, dict)
        and publication_actions
        and sanitized.get("has_limitations") is True
        and sanitized.get("generic_warning_present") is False
    )
    if not (audit_passed or exploratory_published):
        reasons.append("final_audit_or_exploratory_publication_missing")
    if _integer(sanitized.get("publication_length")) < 600:
        reasons.append("publication_too_short")
    if sanitized.get("publication_language") != "zh":
        reasons.append("publication_not_chinese")
    for field in ("has_findings", "has_recommendations", "has_limitations"):
        if sanitized.get(field) is not True:
            reasons.append(f"publication_{field.removeprefix('has_')}_missing")
    if sanitized.get("generic_warning_present") is not False:
        reasons.append("generic_english_warning_present")
    if sanitized.get("progress_before_final") is not True:
        reasons.append("progress_not_before_final")
    if sanitized.get("persisted_matches_streamed") is not True:
        reasons.append("persisted_streamed_mismatch")
    repeated_failure_max = _integer(sanitized.get("repeated_failure_max"))
    if repeated_failure_max < 0 or repeated_failure_max > 2:
        reasons.append("repeated_tool_failure_exceeded")
    unresolved_fallback_blocked_calls = _integer(
        sanitized.get("unresolved_fallback_blocked_calls")
    )
    if unresolved_fallback_blocked_calls != 0:
        reasons.append("unresolved_fallback_cascade")
    verified_material_claims = _integer(
        sanitized.get("verified_material_claims")
    )
    if verified_material_claims < 1:
        reasons.append("verified_material_claim_missing")
    verified_publication_actions = sum(
        action == "verified"
        for action in (
            publication_actions.values()
            if isinstance(publication_actions, dict)
            else ()
        )
    )
    if verified_material_claims != verified_publication_actions:
        reasons.append("verified_material_claim_count_mismatch")
    if sanitized.get("measurement_bookkeeping_scheduled_analysis") is not False:
        reasons.append("measurement_bookkeeping_scheduled_analysis")
    requirements = sanitized.get("requirements")
    requirements = requirements if isinstance(requirements, dict) else {}
    for requirement in LIVE_REQUIREMENT_GROUPS:
        if requirements.get(requirement) not in {"satisfied", "limited"}:
            reasons.append(f"{requirement}_requirement_missing")
    sanitized["reason_codes"] = list(dict.fromkeys(reasons))
    sanitized["status"] = "PASS" if not sanitized["reason_codes"] else "FAIL"
    return sanitized


def build_live_provider_gate_receipt(
    *,
    source_digest: str,
    source_commit: str,
    provider_model: str,
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    evaluated = [evaluate_live_provider_run(run) for run in runs]
    reasons: list[str] = []
    if len(evaluated) != 3:
        reasons.append("live_run_count_mismatch")
    if any(run.get("status") != "PASS" for run in evaluated):
        reasons.append("live_run_failed")
    status = "PASS" if not reasons else "FAIL"
    return {
        "contract_version": LIVE_PROVIDER_GATE_VERSION,
        "status": status,
        "reason_codes": reasons,
        "accepted": status == "PASS",
        "overall_status": status,
        "live_provider_status": status,
        "source_digest": str(source_digest),
        "source_commit": str(source_commit),
        "provider_model": str(provider_model),
        "runs": evaluated,
    }


def validate_live_provider_gate_receipt(
    receipt: Any,
    *,
    expected_source_digest: str,
) -> LiveProviderGateValidation:
    """Validate a source-bound live-provider receipt for product release."""

    if not isinstance(receipt, dict):
        return LiveProviderGateValidation("FAIL", ("invalid_receipt",))

    reasons: list[str] = []
    if set(receipt) - _TOP_LEVEL_FIELDS:
        reasons.append("unsafe_live_receipt_field")
    if receipt.get("contract_version") != LIVE_PROVIDER_GATE_VERSION:
        reasons.append("invalid_live_provider_contract_version")
    raw_status = receipt.get("status")
    if raw_status not in {"PASS", "FAIL", "BLOCKED"}:
        reasons.append("invalid_live_provider_status")
    source_digest = receipt.get("source_digest")
    if not isinstance(source_digest, str) or not _SHA256_RE.fullmatch(source_digest):
        reasons.append("invalid_live_provider_source_digest")
    if source_digest != expected_source_digest:
        reasons.append("stale_live_provider_receipt")

    raw_reason_codes = receipt.get("reason_codes")
    if not (
        isinstance(raw_reason_codes, list)
        and all(isinstance(reason, str) and reason for reason in raw_reason_codes)
    ) and raw_reason_codes != []:
        reasons.append("invalid_live_provider_reason_codes")

    if raw_status in {"PASS", "FAIL", "BLOCKED"}:
        expected_accepted = raw_status == "PASS"
        if (
            receipt.get("accepted") is not expected_accepted
            or receipt.get("overall_status") != raw_status
            or receipt.get("live_provider_status") != raw_status
        ):
                reasons.append("inconsistent_live_provider_status")

    runs = receipt.get("runs")
    if not isinstance(runs, list):
        reasons.append("invalid_live_provider_runs")
    else:
        for run in runs:
            reasons.extend(_run_privacy_reason_codes(run))

    if raw_status == "PASS":
        if raw_reason_codes != []:
            reasons.append("passing_live_receipt_has_reasons")
        if not isinstance(receipt.get("provider_model"), str) or not receipt.get(
            "provider_model"
        ).strip():
            reasons.append("live_provider_model_missing")
        source_commit = receipt.get("source_commit")
        if not isinstance(source_commit, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}", source_commit
        ):
            reasons.append("invalid_live_provider_source_commit")
        if not isinstance(runs, list) or len(runs) != 3:
            reasons.append("live_run_count_mismatch")
        else:
            if [run.get("run_id") if isinstance(run, dict) else None for run in runs] != [
                "live_1",
                "live_2",
                "live_3",
            ]:
                reasons.append("invalid_live_run_ids")
            if any(
                not isinstance(run, dict)
                or evaluate_live_provider_run(run).get("status") != "PASS"
                or run.get("status") != "PASS"
                or run.get("reason_codes") != []
                for run in runs
            ):
                reasons.append("invalid_live_run_contract")
    elif raw_status in {"FAIL", "BLOCKED"}:
        if not isinstance(raw_reason_codes, list) or not raw_reason_codes:
            reasons.append("failed_live_receipt_missing_reasons")

    provider_model = receipt.get("provider_model")
    if provider_model and (
        not isinstance(provider_model, str) or not _MODEL_RE.fullmatch(provider_model)
    ):
        reasons.append("invalid_live_provider_model")

    if reasons:
        return LiveProviderGateValidation("FAIL", tuple(dict.fromkeys(reasons)))
    return LiveProviderGateValidation(
        str(raw_status),
        tuple(raw_reason_codes or []),
    )


def validate_live_user_journey_receipt(
    receipt: Any,
    *,
    expected_source_digest: str,
) -> LiveProviderGateValidation:
    """Validate Gate F v2 as risk-selected real Web user journeys."""

    if not isinstance(receipt, dict):
        return LiveProviderGateValidation("FAIL", ("invalid_live_user_journey_receipt",))

    reasons: list[str] = []
    if set(receipt) - _V2_TOP_LEVEL_FIELDS:
        reasons.append("unsafe_live_user_journey_field")
    if receipt.get("contract_version") != LIVE_USER_JOURNEY_GATE_VERSION:
        reasons.append("invalid_live_user_journey_contract_version")
    status = receipt.get("status")
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        reasons.append("invalid_live_user_journey_status")
    source_digest = receipt.get("source_digest")
    if not isinstance(source_digest, str) or not _SHA256_RE.fullmatch(source_digest):
        reasons.append("invalid_live_user_journey_source_digest")
    if source_digest != expected_source_digest:
        reasons.append("stale_live_user_journey_receipt")
    source_commit = receipt.get("source_commit")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        reasons.append("invalid_live_user_journey_source_commit")
    provider_model = receipt.get("provider_model")
    if not isinstance(provider_model, str) or not _MODEL_RE.fullmatch(provider_model):
        reasons.append("invalid_live_user_journey_model")

    raw_reason_codes = receipt.get("reason_codes")
    if not isinstance(raw_reason_codes, list) or any(
        not isinstance(code, str) or not code for code in raw_reason_codes
    ):
        reasons.append("invalid_live_user_journey_reason_codes")
        raw_reason_codes = []
    if receipt.get("accepted") is not (status == "PASS"):
        reasons.append("inconsistent_live_user_journey_status")

    selection = receipt.get("selection")
    if not isinstance(selection, dict):
        selection = {}
        reasons.append("invalid_live_user_journey_selection")
    risk_class = selection.get("risk_class")
    expected_scenarios = _RISK_SCENARIOS.get(risk_class)
    required_scenarios = selection.get("required_scenario_ids")
    if expected_scenarios is None or required_scenarios != list(expected_scenarios or ()):
        reasons.append("invalid_live_user_journey_selection")
    if isinstance(selection, dict) and set(selection) - _V2_SELECTION_FIELDS:
        reasons.append("unsafe_live_user_journey_selection_field")

    authorization = receipt.get("authorization")
    if not isinstance(authorization, dict):
        authorization = {}
        reasons.append("invalid_live_user_journey_authorization")
    max_sessions = _integer(authorization.get("max_sessions"))
    used_sessions = _integer(authorization.get("used_sessions"))
    if (
        max_sessions < 0
        or used_sessions < 0
        or used_sessions > max_sessions
        or authorization.get("policy") != "fail_fast"
    ):
        reasons.append("invalid_live_user_journey_authorization")
    if isinstance(authorization, dict) and set(authorization) - _V2_AUTHORIZATION_FIELDS:
        reasons.append("unsafe_live_user_journey_authorization_field")

    runs = receipt.get("runs")
    if not isinstance(runs, list):
        runs = []
        reasons.append("invalid_live_user_journey_runs")
    if used_sessions >= 0 and len(runs) != used_sessions:
        reasons.append("live_user_journey_session_count_mismatch")

    observed_scenarios: list[str] = []
    fixture_digests: list[str] = []
    prompt_digests: list[str] = []
    oracle_digests: list[str] = []
    for index, run in enumerate(runs, start=1):
        if not isinstance(run, dict) or set(run) - _V2_RUN_FIELDS:
            reasons.append("unsafe_live_user_journey_run_field")
            continue
        scenario_id = run.get("scenario_id")
        if not isinstance(scenario_id, str) or not _SCENARIO_RE.fullmatch(scenario_id):
            reasons.append("invalid_live_user_journey_scenario")
        else:
            observed_scenarios.append(scenario_id)
        if run.get("provider_session_index") != index:
            reasons.append("invalid_live_user_journey_session_index")
        if run.get("status") != "PASS":
            reasons.append("live_user_journey_run_failed")

        journey = run.get("browser_journey")
        journey_validation = validate_browser_user_journey_receipt(
            journey,
            expected_source_digest=expected_source_digest,
        )
        if journey_validation.status != "PASS":
            reasons.append("invalid_live_browser_user_journey")
            reasons.extend(journey_validation.reason_codes)
        elif isinstance(journey, dict) and journey.get("scenario_id") != scenario_id:
            reasons.append("live_user_journey_scenario_mismatch")
        if isinstance(journey, dict) and isinstance(scenario_id, str):
            try:
                expected_prompt_digest = scenario_prompt_digest(scenario_id)
                required_oracles = set(scenario_oracle_names(scenario_id))
            except KeyError:
                reasons.append("unknown_live_user_journey_scenario")
            else:
                if journey.get("prompt_digest") != expected_prompt_digest:
                    reasons.append("live_user_journey_prompt_mismatch")
                observed_oracles = {
                    item.get("name")
                    for item in journey.get("oracle_assertions") or []
                    if isinstance(item, dict) and item.get("passed") is True
                }
                if not required_oracles.issubset(observed_oracles):
                    reasons.append("live_user_journey_oracles_incomplete")
            fixture_digests.append(str(journey.get("fixture_digest") or ""))
            prompt_digests.append(str(journey.get("prompt_digest") or ""))
            oracle_digests.append(str(journey.get("oracle_digest") or ""))

        human_review = run.get("human_review")
        required_review_fields = (
            "question_understood",
            "method_appropriate",
            "claim_strength_appropriate",
            "limitations_material",
        )
        if not isinstance(human_review, dict) or any(
            human_review.get(field) is not True for field in required_review_fields
        ):
            reasons.append("live_user_journey_human_review_failed")
        if isinstance(human_review, dict) and set(human_review) - _V2_HUMAN_REVIEW_FIELDS:
            reasons.append("unsafe_live_user_journey_human_review_field")

    if len(set(observed_scenarios)) != len(observed_scenarios):
        reasons.append("duplicate_live_user_journey_scenarios")
    if len(observed_scenarios) > 1 and any(
        len(set(values)) != len(values)
        for values in (fixture_digests, prompt_digests, oracle_digests)
    ):
        reasons.append("duplicate_live_user_journey_identity")
    if status == "PASS":
        if raw_reason_codes:
            reasons.append("passing_live_user_journey_has_reasons")
        if expected_scenarios is not None and observed_scenarios != list(expected_scenarios):
            reasons.append("required_live_user_journey_scenarios_missing")
    elif status in {"FAIL", "BLOCKED"} and not raw_reason_codes:
        reasons.append("nonpassing_live_user_journey_missing_reasons")

    if reasons:
        return LiveProviderGateValidation("FAIL", tuple(dict.fromkeys(reasons)))
    return LiveProviderGateValidation(str(status), tuple(raw_reason_codes))
