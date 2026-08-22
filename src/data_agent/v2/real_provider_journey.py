from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import pandas as pd

from data_agent.config import AgentConfig, get_config
from data_agent.llm.client import LLMClient
from data_agent.v2.planner import (
    PLANNER_CONTRACT_GATE_VERSION,
    DatasetPlanningContext,
    StructuredAnalysisPlanner,
    build_planner_contract_gate,
)
from data_agent.v2.planning_budget import (
    PlanningContextBudget,
    resolve_model_context_window,
)


REAL_PROVIDER_JOURNEY_VERSION = "v2_real_provider_journey_preflight.v6"
UNIFIED_SCENARIO_ID = "unified_analysis_entry"
UNIFIED_FIXTURE_PATH = "tests/fixtures/v2_slice4d_combined.csv"
UNIFIED_QUESTION = (
    "销售如何变化，不同渠道是否存在可靠差异？请给出严谨结论、统计不确定性、"
    "方法局限，并仅在上下文支持时给出建议。"
)
REQUIRED_STOP_CONDITIONS = (
    "source_digest_changed",
    "dataset_fingerprint_changed",
    "analysis_unit_semantics_unconfirmed",
    "planning_context_too_large",
    "provider_error",
    "planner_contract_error",
    "unsupported_plan",
    "needs_input_without_new_authorization",
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RealProviderPreflightValidation:
    passed: bool
    reason_codes: tuple[str, ...]


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def build_real_provider_preflight(
    *,
    fixture_path: Path | str,
    source_digest: str,
    config: AgentConfig | None = None,
    token_counter: Callable[..., int] | None = None,
    confirmed_analysis_unit_column: str = "",
) -> dict[str, Any]:
    """Build the exact first-call request budget without issuing authorization."""

    cfg = config or get_config()
    fixture = Path(fixture_path)
    normalized_fixture = fixture.as_posix()
    if (
        normalized_fixture != UNIFIED_FIXTURE_PATH
        and not normalized_fixture.endswith("/" + UNIFIED_FIXTURE_PATH)
    ):
        raise ValueError("real-provider preflight requires the unified matrix fixture")
    frame = pd.read_csv(fixture)
    dataset_fingerprint = "sha256:" + hashlib.sha256(fixture.read_bytes()).hexdigest()
    context = DatasetPlanningContext.from_frame(
        filename=fixture.name,
        source_fingerprint=dataset_fingerprint,
        frame=frame,
    )
    if str(confirmed_analysis_unit_column or "").strip():
        context = context.with_confirmed_analysis_unit_column(
            confirmed_analysis_unit_column
        )
    client = LLMClient(
        model_id=cfg.model_id,
        api_base=cfg.api_base,
        api_key=cfg.api_key,
        max_tokens=cfg.max_tokens,
        temperature=0,
        timeout=120,
    )
    planner = StructuredAnalysisPlanner(client)
    planner_contract_gate = build_planner_contract_gate(context)
    if planner_contract_gate["passed"] is not True:
        raise ValueError("planner parameter contract parity gate failed")
    budget_kwargs: dict[str, Any] = {}
    if token_counter is not None:
        budget_kwargs["token_counter"] = token_counter
    budget = PlanningContextBudget(
        planner,
        model_id=client.model_id,
        context_window_tokens=resolve_model_context_window(
            client.model_id,
            cfg.model_context_window,
            api_base=client.api_base,
        ),
        reserved_output_tokens=client.max_tokens,
        **budget_kwargs,
    )
    estimate = budget.require_fits(UNIFIED_QUESTION, context)
    request_identity = {
        "source_digest": source_digest,
        "scenario_id": UNIFIED_SCENARIO_ID,
        "fixture_path": UNIFIED_FIXTURE_PATH,
        "dataset_fingerprint": dataset_fingerprint,
        "question": UNIFIED_QUESTION,
        "model_id": client.model_id,
        "planning_context": estimate.to_dict(),
        "semantic_context": context.to_prompt_dict()["semantic_context"],
        "planner_contract_gate": planner_contract_gate,
    }
    return {
        "version": REAL_PROVIDER_JOURNEY_VERSION,
        **request_identity,
        "provider_host": (urlparse(client.api_base or "").hostname or ""),
        "request_fingerprint": _fingerprint(request_identity),
        "authorization_request": {
            "mode": "per_call",
            "purpose": "analysis_planning",
            "provider_calls": 1,
        },
        "conditional_followup": {
            "allowed_only_if_status": "needs_input",
            "provider_calls": 1,
            "requires_new_user_authorization": True,
            "requires_fresh_token_estimate": True,
        },
        "stop_conditions": list(REQUIRED_STOP_CONDITIONS),
        "provider_calls_observed": 0,
        "authorization_issued": False,
        "release_readiness_claimed": False,
        "root_switch_authorized": False,
    }


def validate_real_provider_preflight(
    preflight: Any,
    *,
    expected_source_digest: str,
    expected_model_id: str,
    expected_dataset_fingerprint: str,
    expected_planner_contract_gate: dict[str, Any],
    expected_semantic_context: dict[str, str],
) -> RealProviderPreflightValidation:
    if not isinstance(preflight, dict):
        return RealProviderPreflightValidation(False, ("invalid_real_provider_preflight",))
    reasons: list[str] = []
    if preflight.get("version") != REAL_PROVIDER_JOURNEY_VERSION:
        reasons.append("invalid_real_provider_preflight_version")
    if preflight.get("source_digest") != expected_source_digest:
        reasons.append("stale_real_provider_preflight")
    if preflight.get("scenario_id") != UNIFIED_SCENARIO_ID:
        reasons.append("invalid_real_provider_scenario")
    if preflight.get("fixture_path") != UNIFIED_FIXTURE_PATH:
        reasons.append("wrong_real_provider_fixture")
    if not _SHA256.fullmatch(str(preflight.get("dataset_fingerprint") or "")):
        reasons.append("invalid_dataset_fingerprint")
    elif preflight.get("dataset_fingerprint") != expected_dataset_fingerprint:
        reasons.append("real_provider_dataset_changed")
    if preflight.get("question") != UNIFIED_QUESTION:
        reasons.append("real_provider_question_changed")
    if preflight.get("model_id") != expected_model_id:
        reasons.append("real_provider_model_changed")
    request_fingerprint = str(preflight.get("request_fingerprint") or "")
    if not _SHA256.fullmatch(request_fingerprint):
        reasons.append("invalid_real_provider_request_fingerprint")
    request_identity = {
        key: preflight.get(key)
        for key in (
            "source_digest",
            "scenario_id",
            "fixture_path",
            "dataset_fingerprint",
            "question",
            "model_id",
            "planning_context",
            "semantic_context",
            "planner_contract_gate",
        )
    }
    if request_fingerprint != _fingerprint(request_identity):
        reasons.append("real_provider_request_fingerprint_mismatch")

    semantic_context = preflight.get("semantic_context")
    if (
        not isinstance(semantic_context, dict)
        or set(semantic_context) != {"confirmed_analysis_unit_column"}
        or not isinstance(
            semantic_context.get("confirmed_analysis_unit_column"), str
        )
    ):
        reasons.append("invalid_real_provider_semantic_context")
        semantic_context = {}
    confirmed_analysis_unit = str(
        semantic_context.get("confirmed_analysis_unit_column") or ""
    ).strip()
    if not confirmed_analysis_unit:
        reasons.append("real_provider_analysis_unit_unconfirmed")
    if semantic_context != expected_semantic_context:
        reasons.append("real_provider_semantic_context_mismatch")

    planner_gate = preflight.get("planner_contract_gate")
    if not isinstance(planner_gate, dict):
        planner_gate = {}
        reasons.append("invalid_planner_contract_gate")
    if planner_gate.get("version") != PLANNER_CONTRACT_GATE_VERSION:
        reasons.append("invalid_planner_contract_gate_version")
    if planner_gate.get("passed") is not True:
        reasons.append("planner_parameter_contract_parity_failed")
    if not _SHA256.fullmatch(str(planner_gate.get("schema_fingerprint") or "")):
        reasons.append("invalid_planner_contract_schema_fingerprint")
    analysis_kinds = planner_gate.get("automatic_analysis_kinds")
    if (
        not isinstance(analysis_kinds, list)
        or len(analysis_kinds) != 7
        or len(set(str(item) for item in analysis_kinds)) != len(analysis_kinds)
    ):
        reasons.append("invalid_planner_analysis_kind_matrix")
        analysis_kinds = []
    ready_variant_count = planner_gate.get("ready_variant_count")
    if (
        isinstance(ready_variant_count, bool)
        or not isinstance(ready_variant_count, int)
        or ready_variant_count < 0
    ):
        reasons.append("invalid_planner_ready_variant_count")
        ready_variant_count = 0
    needs_input_variants = planner_gate.get("needs_input_variants")
    if not isinstance(needs_input_variants, list):
        needs_input_variants = []
        reasons.append("invalid_planner_needs_input_variants")
    if planner_gate.get("needs_input_variant_count") != len(
        needs_input_variants
    ):
        reasons.append("invalid_planner_needs_input_variant_count")
    if ready_variant_count + len(needs_input_variants) != len(analysis_kinds):
        reasons.append("invalid_planner_ready_variant_count")
        reasons.append("incomplete_planner_analysis_kind_matrix")
    if planner_gate.get("unsupported_variant_count") != 1:
        reasons.append("invalid_planner_unsupported_variant_count")
    if planner_gate.get("status_variant_count") != (
        ready_variant_count + len(needs_input_variants) + 1
    ):
        reasons.append("invalid_planner_status_variant_count")
    if planner_gate != expected_planner_contract_gate:
        reasons.append("planner_contract_gate_mismatch")
    if preflight.get("provider_calls_observed") != 0:
        reasons.append("provider_call_occurred_during_preflight")
    if preflight.get("authorization_issued") is not False:
        reasons.append("authorization_issued_during_preflight")

    authorization = preflight.get("authorization_request")
    if not isinstance(authorization, dict):
        authorization = {}
        reasons.append("invalid_authorization_request")
    if authorization.get("provider_calls") != 1:
        reasons.append("exactly_one_provider_call_required")
    if authorization.get("mode") != "per_call":
        reasons.append("per_call_authorization_required")
    if authorization.get("purpose") != "analysis_planning":
        reasons.append("invalid_provider_call_purpose")

    estimate = preflight.get("planning_context")
    if not isinstance(estimate, dict):
        estimate = {}
        reasons.append("invalid_planning_context_estimate")
    if estimate.get("model_id") != expected_model_id:
        reasons.append("planning_context_model_changed")
    for name in (
        "estimated_input_tokens",
        "model_context_window_tokens",
        "reserved_output_tokens",
        "available_input_tokens",
    ):
        value = estimate.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"invalid_planning_context:{name}")
    if estimate.get("fits") is not True:
        reasons.append("planning_context_too_large")
    if (
        isinstance(estimate.get("estimated_input_tokens"), int)
        and isinstance(estimate.get("available_input_tokens"), int)
        and estimate["estimated_input_tokens"] > estimate["available_input_tokens"]
    ):
        reasons.append("planning_context_too_large")

    if preflight.get("conditional_followup") != {
        "allowed_only_if_status": "needs_input",
        "provider_calls": 1,
        "requires_new_user_authorization": True,
        "requires_fresh_token_estimate": True,
    }:
        reasons.append("invalid_conditional_followup")
    stop_conditions = preflight.get("stop_conditions")
    if not isinstance(stop_conditions, list):
        stop_conditions = []
        reasons.append("invalid_stop_conditions")
    for condition in REQUIRED_STOP_CONDITIONS:
        if condition not in stop_conditions:
            reasons.append(f"missing_stop_condition:{condition}")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return RealProviderPreflightValidation(not unique_reasons, unique_reasons)
