from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import pandas as pd

from data_agent.config import AgentConfig, get_config
from data_agent.v2.planner import DatasetPlanningContext, build_planner_contract_gate
from data_agent.v2.real_provider_journey import (
    FORECAST_FIXTURE_PATH,
    FORECAST_QUESTION,
    FORECAST_SCENARIO_ID,
    UNIFIED_FIXTURE_PATH,
    UNIFIED_QUESTION,
    UNIFIED_SCENARIO_ID,
    build_real_provider_preflight,
    validate_real_provider_preflight,
)
from data_agent.v2.release import ReleaseMatrix


REPRESENTATIVE_PROVIDER_PREFLIGHT_VERSION = (
    "v2_representative_provider_preflight.v1"
)


@dataclass(frozen=True, slots=True)
class RepresentativeProviderPreflightValidation:
    passed: bool
    reason_codes: tuple[str, ...]


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _group_identity(preflight: dict[str, Any]) -> dict[str, Any]:
    calls = preflight.get("calls")
    if not isinstance(calls, list):
        calls = []
    return {
        "source_digest": preflight.get("source_digest"),
        "model_id": preflight.get("model_id"),
        "provider_host": preflight.get("provider_host"),
        "provider_call_budget": preflight.get("provider_call_budget"),
        "targets": [
            {
                "scenario_id": item.get("scenario_id"),
                "fixture_path": item.get("fixture_path"),
                "request_fingerprint": item.get("request_fingerprint"),
            }
            for item in calls
            if isinstance(item, dict)
        ],
    }


def build_representative_provider_preflight(
    *,
    repository_root: Path | str,
    matrix: ReleaseMatrix,
    source_digest: str,
    config: AgentConfig | None = None,
    token_counter: Callable[..., int] | None = None,
    confirmed_analysis_unit_column: str,
) -> dict[str, Any]:
    """Freeze the matrix's bounded Provider calls without authorizing any call."""

    cfg = config or get_config()
    root = Path(repository_root)
    calls = [
        build_real_provider_preflight(
            fixture_path=root / target.fixture,
            source_digest=source_digest,
            config=cfg,
            token_counter=token_counter,
            confirmed_analysis_unit_column=(
                confirmed_analysis_unit_column
                if target.scenario_id == UNIFIED_SCENARIO_ID
                else ""
            ),
            scenario_id=target.scenario_id,
        )
        for target in matrix.representative_provider_targets
    ]
    provider_host = urlparse(cfg.api_base or "").hostname or ""
    preflight = {
        "version": REPRESENTATIVE_PROVIDER_PREFLIGHT_VERSION,
        "source_digest": source_digest,
        "model_id": cfg.model_id,
        "provider_host": provider_host,
        "provider_call_budget": matrix.provider_call_budget,
        "calls": calls,
        "authorization_request": {
            "mode": "grouped_exact_calls",
            "purpose": "analysis_planning",
            "provider_calls": matrix.provider_call_budget,
        },
        "stop_policy": {
            "stop_after_any_non_ready": True,
            "retry": False,
            "repair": False,
            "fallback": False,
            "automatic_followup": False,
            "needs_input_requires_new_authorization": True,
        },
        "provider_calls_observed": 0,
        "authorization_issued": False,
        "release_readiness_claimed": False,
        "root_switch_authorized": False,
    }
    preflight["group_fingerprint"] = _fingerprint(_group_identity(preflight))
    return preflight


def _expected_call_contract(
    scenario_id: str,
) -> tuple[str, str, bool]:
    if scenario_id == UNIFIED_SCENARIO_ID:
        return UNIFIED_FIXTURE_PATH, UNIFIED_QUESTION, True
    if scenario_id == FORECAST_SCENARIO_ID:
        return FORECAST_FIXTURE_PATH, FORECAST_QUESTION, False
    raise ValueError(f"unsupported representative Provider scenario: {scenario_id}")


def validate_representative_provider_preflight(
    preflight: Any,
    *,
    repository_root: Path | str,
    matrix: ReleaseMatrix,
    expected_source_digest: str,
    expected_model_id: str,
    expected_provider_host: str = "api.deepseek.com",
) -> RepresentativeProviderPreflightValidation:
    if not isinstance(preflight, dict):
        return RepresentativeProviderPreflightValidation(
            False, ("invalid_representative_provider_preflight",)
        )
    reasons: list[str] = []
    if preflight.get("version") != REPRESENTATIVE_PROVIDER_PREFLIGHT_VERSION:
        reasons.append("invalid_representative_provider_preflight_version")
    if preflight.get("source_digest") != expected_source_digest:
        reasons.append("stale_representative_provider_preflight")
    if preflight.get("model_id") != expected_model_id:
        reasons.append("representative_provider_model_changed")
    if preflight.get("provider_host") != expected_provider_host:
        reasons.append("representative_provider_host_changed")
    if preflight.get("provider_call_budget") != matrix.provider_call_budget:
        reasons.append("representative_provider_call_budget_mismatch")
    authorization = preflight.get("authorization_request")
    expected_authorization = {
        "mode": "grouped_exact_calls",
        "purpose": "analysis_planning",
        "provider_calls": matrix.provider_call_budget,
    }
    if authorization != expected_authorization:
        reasons.append("representative_provider_call_budget_mismatch")
    if preflight.get("provider_calls_observed") != 0:
        reasons.append("provider_call_occurred_during_group_preflight")
    if preflight.get("authorization_issued") is not False:
        reasons.append("authorization_issued_during_group_preflight")
    if preflight.get("stop_policy") != {
        "stop_after_any_non_ready": True,
        "retry": False,
        "repair": False,
        "fallback": False,
        "automatic_followup": False,
        "needs_input_requires_new_authorization": True,
    }:
        reasons.append("invalid_representative_provider_stop_policy")
    calls = preflight.get("calls")
    if not isinstance(calls, list):
        calls = []
        reasons.append("invalid_representative_provider_calls")
    expected_targets = list(matrix.representative_provider_targets)
    if len(calls) != matrix.provider_call_budget:
        reasons.append("representative_provider_call_budget_mismatch")
    observed_order = [
        str(item.get("scenario_id") or "")
        for item in calls
        if isinstance(item, dict)
    ]
    expected_order = [item.scenario_id for item in expected_targets]
    if observed_order != expected_order:
        reasons.append("representative_provider_target_order_changed")

    root = Path(repository_root)
    for index, target in enumerate(expected_targets):
        if index >= len(calls) or not isinstance(calls[index], dict):
            continue
        call = calls[index]
        expected_fixture, expected_question, unit_required = _expected_call_contract(
            target.scenario_id
        )
        fixture = root / target.fixture
        dataset_fingerprint = "sha256:" + hashlib.sha256(fixture.read_bytes()).hexdigest()
        frame = pd.read_csv(fixture)
        context = DatasetPlanningContext.from_frame(
            filename=fixture.name,
            source_fingerprint=dataset_fingerprint,
            frame=frame,
        )
        if unit_required:
            confirmed = str(
                (call.get("semantic_context") or {}).get(
                    "confirmed_analysis_unit_column"
                )
                or ""
            )
            if confirmed:
                context = context.with_confirmed_analysis_unit_column(confirmed)
        expected_semantic_context = context.to_prompt_dict()["semantic_context"]
        nested = validate_real_provider_preflight(
            call,
            expected_source_digest=expected_source_digest,
            expected_model_id=expected_model_id,
            expected_dataset_fingerprint=dataset_fingerprint,
            expected_planner_contract_gate=build_planner_contract_gate(context),
            expected_semantic_context=expected_semantic_context,
            expected_scenario_id=target.scenario_id,
            expected_fixture_path=expected_fixture,
            expected_question=expected_question,
            analysis_unit_required=unit_required,
        )
        if call.get("provider_host") != expected_provider_host:
            reasons.append(f"representative_provider_call_host_changed:{target.scenario_id}")
        if not nested.passed:
            reasons.append(f"representative_provider_call_invalid:{target.scenario_id}")
    if preflight.get("group_fingerprint") != _fingerprint(_group_identity(preflight)):
        reasons.append("representative_provider_group_fingerprint_mismatch")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return RepresentativeProviderPreflightValidation(not unique_reasons, unique_reasons)
