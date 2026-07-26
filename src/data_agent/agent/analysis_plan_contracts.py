from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from data_agent.agent.analysis_requirements import (
    compile_analysis_requirements,
    requirement_ids_for_route,
)


ANALYSIS_PLAN_CONTRACT_VERSION = "analysis_plan.v1"
LEGACY_ANALYSIS_PLAN_CONTRACT_VERSIONS = {"stage3c0b.v1"}
SUPPORTED_ANALYSIS_PLAN_MODES = {"independent", "synthesis"}

# Read-only compatibility aliases for external imports during migration.
STAGE3C0B_CONTRACT_VERSION = "stage3c0b.v1"
SUPPORTED_STAGE3C0B_MODES = SUPPORTED_ANALYSIS_PLAN_MODES
MAX_EXECUTABLE_STEPS_PER_BATCH = 12
MAX_SYNTHESIS_REQUIRED_EVIDENCE = 8


@dataclass
class ContractValidationResult:
    ok: bool
    plan: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _step_id_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _step_id_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_step_id_text(item) for item in value if _step_id_text(item)]


def _required_claim_keys(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("AnalysisPlan required_claim_keys must be a list of strings.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _text(item):
            raise ValueError("AnalysisPlan required_claim_keys must be a list of non-empty strings.")
        claim_key = _text(item)
        if claim_key not in result:
            result.append(claim_key)
    return result


def analysis_plan_id_from_mapping(value: Mapping[str, Any] | Any) -> str:
    """Read the canonical plan id with one legacy persisted-field fallback."""
    if not isinstance(value, Mapping):
        return ""
    return _text(value.get("analysis_plan_id") or value.get("analysis_spec_id"))


def _contract_indexes(dataset_contracts: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    by_dataset: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for contract in dataset_contracts:
        dataset = _text(contract.get("dataset"))
        contract_id = _text(contract.get("id") or contract.get("contract_id"))
        if dataset and contract_id:
            by_dataset[dataset] = contract_id
        if contract_id:
            by_id[contract_id] = contract_id
    return by_dataset, by_id


def _error(error_type: str, message: str, **details: Any) -> ContractValidationResult:
    return ContractValidationResult(False, error_type=error_type, message=message, details=details)


def _resolve_contract_ids(dataset_inputs: list[str], by_dataset: dict[str, str], by_id: dict[str, str]) -> list[str]:
    resolved: list[str] = []
    for dataset in dataset_inputs:
        contract_id = by_dataset.get(dataset) or by_id.get(dataset)
        if contract_id:
            resolved.append(contract_id)
    return resolved


def analysis_plan_tool_object_schema() -> dict[str, Any]:
    """Return the canonical LLM-visible AnalysisPlan object boundary."""
    return {
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "method_plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
            "visualization_strategy": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "array"},
                    {"type": "object"},
                ],
            },
        },
        "required": [
            "goal",
            "method_plan",
            "visualization_strategy",
        ],
        "additionalProperties": True,
    }


def normalize_analysis_plan_contract(
    plan: dict[str, Any],
    *,
    dataset_contracts: list[dict[str, Any]] | None = None,
    require_executable: bool = False,
    route: dict[str, Any] | str | None = None,
    playbook: Any = None,
    user_intent: Any = None,
    _legacy_saved_plan_loading: bool = False,
) -> ContractValidationResult:
    if not isinstance(plan, dict):
        return _error("invalid_plan", "AnalysisPlan must be a JSON object.")

    normalized = dict(plan)
    incoming_analysis_requirements = normalized.get("analysis_requirements")
    incoming_version = _text(normalized.get("contract_version"))
    if incoming_version in LEGACY_ANALYSIS_PLAN_CONTRACT_VERSIONS:
        normalized["migrated_from_contract_version"] = incoming_version
        incoming_version = ANALYSIS_PLAN_CONTRACT_VERSION
    if incoming_version and incoming_version != ANALYSIS_PLAN_CONTRACT_VERSION:
        return _error(
            "unsupported_contract_version",
            f"Unsupported AnalysisPlan contract version: {incoming_version}",
        )
    normalized["contract_version"] = ANALYSIS_PLAN_CONTRACT_VERSION
    normalized.setdefault("id", f"plan_{uuid.uuid4().hex[:10]}")
    normalized.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    raw_method_plan = normalized.get("method_plan")
    if isinstance(raw_method_plan, list):
        compatibility_steps: list[Any] = []
        for raw_step in raw_method_plan:
            if not isinstance(raw_step, dict):
                compatibility_steps.append(raw_step)
                continue
            step = dict(raw_step)
            if "required_claim_keys" in step:
                try:
                    step["required_claim_keys"] = _required_claim_keys(step["required_claim_keys"])
                except ValueError as exc:
                    return _error(
                        "invalid_required_claim_keys",
                        str(exc),
                        step_id=_step_id_text(step.get("step_id")) or f"step_{len(compatibility_steps) + 1}",
                    )
            if isinstance(step.get("evidence_requirements"), list) or isinstance(step.get("expected_evidence"), list):
                step["evidence_requirements"] = requirement_ids_for_route(step)
                step.pop("expected_evidence", None)
            compatibility_steps.append(step)
        normalized["method_plan"] = compatibility_steps

    route_input = route if route is not None else normalized.get("route")
    if isinstance(route_input, str):
        route_input = {"direction": route_input}
    try:
        compiled_requirements = compile_analysis_requirements(
            plan=normalized,
            route=route_input,
            playbook=playbook if playbook is not None else normalized,
            dataset_contracts=dataset_contracts or [],
            user_intent=user_intent if user_intent is not None else normalized.get("goal"),
            _allow_legacy_unknown=_legacy_saved_plan_loading,
        )
    except ValueError as exc:
        return _error("invalid_analysis_requirements", str(exc))
    grouped_requirements: dict[str, list[dict[str, Any]]] = {}
    for requirement in compiled_requirements:
        grouped_requirements.setdefault(requirement["step_id"], []).append(requirement)
    if require_executable and incoming_analysis_requirements is not None:
        incoming_by_id = {
            _text(requirement.get("id")): requirement
            for group in incoming_analysis_requirements.values()
            for requirement in group
            if isinstance(requirement, dict) and _text(requirement.get("id"))
        }
        missing_requirement_ids = [
            requirement["id"]
            for requirement in compiled_requirements
            if requirement["necessity"] == "required" and requirement["id"] not in incoming_by_id
        ]
        if missing_requirement_ids:
            return _error(
                "missing_compiled_hard_requirement",
                "Executable AnalysisPlan cannot remove compiler-required hard requirements.",
                missing_requirement_ids=missing_requirement_ids,
            )
        compiler_owned_fields = (
            "contract_version",
            "id",
            "step_id",
            "category",
            "name",
            "necessity",
            "trigger",
            "required_evidence_fields",
            "assumption_checks",
            "unmet_action",
            "parameters",
            "assessment_status",
            "claim_guard",
        )
        conflicting_requirement_ids = [
            requirement["id"]
            for requirement in compiled_requirements
            if requirement["id"] in incoming_by_id
            and any(
                incoming_by_id[requirement["id"]].get(field) != requirement.get(field)
                for field in compiler_owned_fields
            )
        ]
        if conflicting_requirement_ids:
            return _error(
                "conflicting_compiled_requirement",
                "Executable AnalysisPlan cannot override compiler-owned requirement definitions.",
                conflicting_requirement_ids=conflicting_requirement_ids,
            )
    normalized["analysis_requirements"] = grouped_requirements
    projected_steps: list[Any] = []
    for index, raw_step in enumerate(normalized.get("method_plan") or [], 1):
        if not isinstance(raw_step, dict):
            projected_steps.append(raw_step)
            continue
        step = dict(raw_step)
        step_id = _step_id_text(step.get("step_id")) or f"step_{index}"
        if step_id in grouped_requirements or "evidence_requirements" in step:
            step["evidence_requirements"] = [
                requirement["name"]
                for requirement in grouped_requirements.get(step_id, [])
            ]
        projected_steps.append(step)
    normalized["method_plan"] = projected_steps

    if not require_executable:
        normalized.setdefault("review_status", "display_only")
        return ContractValidationResult(True, plan=normalized)
    return _validate_executable_plan(normalized, dataset_contracts=dataset_contracts)


def _validate_executable_plan(
    plan: dict[str, Any],
    *,
    dataset_contracts: list[dict[str, Any]] | None = None,
) -> ContractValidationResult:
    method_plan = plan.get("method_plan")
    if not isinstance(method_plan, list) or not method_plan:
        return _error("missing_method_plan", "AnalysisPlan requires a non-empty method_plan.")
    if len(method_plan) > MAX_EXECUTABLE_STEPS_PER_BATCH:
        return _error(
            "execution_batch_too_large",
            "AnalysisPlan execution batch exceeds the maximum executable step budget.",
            max_executable_steps_per_batch=MAX_EXECUTABLE_STEPS_PER_BATCH,
            actual=len(method_plan),
        )

    normalized = dict(plan)
    normalized.setdefault("id", f"plan_{uuid.uuid4().hex[:10]}")
    normalized.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    normalized["review_status"] = "reviewed"

    # ``dataset_contracts=None`` keeps the validator usable for pure plan-shape
    # checks; any provided contract list, including an empty one, is enforced.
    enforce_dataset_contracts = dataset_contracts is not None
    by_dataset, by_id = _contract_indexes(dataset_contracts or [])
    normalized_steps: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    for index, raw_step in enumerate(method_plan, 1):
        if not isinstance(raw_step, dict):
            return _error("invalid_step", f"method_plan step {index} must be an object.")
        step = dict(raw_step)
        step_id = _step_id_text(step.get("step_id")) or f"step_{index}"
        if step_id in seen_step_ids:
            return _error("duplicate_step_id", f"Duplicate step_id: {step_id}", step_id=step_id)
        seen_step_ids.add(step_id)
        mode = _text(step.get("combination_mode")) or "independent"
        if mode not in SUPPORTED_ANALYSIS_PLAN_MODES:
            return _error(
                "unsupported_combination_mode",
                f"AnalysisPlan supports only independent and synthesis, not {mode}.",
                step_id=step_id,
                combination_mode=mode,
            )
        dataset_inputs = _text_list(step.get("dataset_inputs"))
        if mode == "independent" and len(dataset_inputs) != 1:
            return _error(
                "invalid_independent_binding",
                "AnalysisPlan independent steps must bind exactly one dataset.",
                step_id=step_id,
                dataset_inputs=dataset_inputs,
            )
        if mode == "synthesis" and dataset_inputs:
            return _error(
                "invalid_synthesis_binding",
                "AnalysisPlan synthesis steps consume evidence, not raw datasets.",
                step_id=step_id,
            )
        resolved_contract_ids = (
            _resolve_contract_ids(dataset_inputs, by_dataset, by_id)
            if enforce_dataset_contracts
            else _text_list(step.get("dataset_contract_ids"))
        )
        if mode == "independent" and enforce_dataset_contracts and len(resolved_contract_ids) != 1:
            return _error(
                "missing_dataset_contract",
                "AnalysisPlan independent steps require exactly one current dataset contract.",
                step_id=step_id,
                dataset_inputs=dataset_inputs,
                dataset_contract_ids=resolved_contract_ids,
            )
        required_evidence = _step_id_list(step.get("required_evidence_step_ids"))
        if mode == "synthesis" and len(required_evidence) > MAX_SYNTHESIS_REQUIRED_EVIDENCE:
            return _error(
                "too_many_required_evidence_dependencies",
                "Synthesis declares too many hard required evidence dependencies.",
                step_id=step_id,
                max_required_evidence_step_ids=MAX_SYNTHESIS_REQUIRED_EVIDENCE,
                actual=len(required_evidence),
            )
        if not _text(step.get("goal")):
            return _error("missing_step_goal", "Every AnalysisPlan step needs a goal.", step_id=step_id)
        if not _text(step.get("expected_output")):
            return _error("missing_expected_output", "Every AnalysisPlan step needs expected_output.", step_id=step_id)
        if not _text_list(step.get("evidence_requirements")):
            return _error(
                "missing_evidence_requirements",
                "Every AnalysisPlan step needs evidence_requirements.",
                step_id=step_id,
            )

        step["plan_id"] = normalized["id"]
        step["step_id"] = step_id
        step["combination_mode"] = mode
        step["dataset_inputs"] = dataset_inputs
        step["dataset_contract_ids"] = resolved_contract_ids
        step["required_evidence_step_ids"] = required_evidence
        if "required_claim_keys" in step:
            try:
                step["required_claim_keys"] = _required_claim_keys(step["required_claim_keys"])
            except ValueError as exc:
                return _error(
                    "invalid_required_claim_keys",
                    str(exc),
                    step_id=step_id,
                )
        normalized_steps.append(step)

    normalized["method_plan"] = normalized_steps
    normalized["review_status"] = "executable"
    return ContractValidationResult(True, plan=normalized)


def validate_analysis_plan_contract(
    plan: dict[str, Any],
    *,
    dataset_contracts: list[dict[str, Any]] | None = None,
) -> ContractValidationResult:
    return normalize_analysis_plan_contract(
        plan,
        dataset_contracts=dataset_contracts,
        require_executable=True,
    )
