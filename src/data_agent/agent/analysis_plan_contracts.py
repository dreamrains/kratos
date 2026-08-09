from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from data_agent.agent.analysis_requirements import (
    compile_analysis_requirements,
    is_canonical_analysis_requirement_input,
    requirement_ids_for_route,
    validate_analysis_requirement,
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
                    "properties": {
                        "step_id": {"type": "string"},
                        "goal": {"type": "string"},
                        "method": {"type": "string"},
                        "required_capability": {"type": "string"},
                        "dataset_inputs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "combination_mode": {
                            "type": "string",
                            "enum": ["independent", "synthesis"],
                        },
                        "expected_output": {"type": "string"},
                        "evidence_requirements": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "required_claim_keys": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "required_evidence_step_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
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
        ],
        "additionalProperties": True,
    }


def _enrich_executable_plan_shorthand(
    plan: dict[str, Any],
    *,
    dataset_contracts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Resolve common LLM shorthand only when the identity is deterministic."""

    normalized = dict(plan)
    normalized.setdefault("visualization_strategy", [])
    contracts = [item for item in dataset_contracts or [] if isinstance(item, dict)]
    by_dataset, by_id = _contract_indexes(contracts)
    unique_dataset = next(iter(by_dataset), "") if len(by_dataset) == 1 else ""
    generic_aliases = {
        "main",
        "data",
        "dataset",
        "current",
        "current_data",
        "当前数据",
        "当前数据集",
    }
    method_capabilities = (
        ("factor_relationship_analysis", "analysis.factor_relationship"),
        ("correlation_analysis", "analysis.correlation"),
        ("regression_analysis", "analysis.regression"),
        ("distribution_analysis", "analysis.distribution"),
        ("segmentation_analysis", "analysis.segmentation"),
        ("group_aggregate", "analysis.group_compare"),
        ("detect_data_quality", "data.quality"),
        ("describe_dataset", "data.describe"),
        ("quick_profile", "data.profile"),
        ("top_n", "analysis.top_n"),
    )
    capability_aliases = {
        "quality_check": "data.quality",
        "data_quality_check": "data.quality",
        "data_quality": "data.quality",
        "quality": "data.quality",
        "data.quality": "data.quality",
        "distribution": "analysis.distribution",
        "analysis_distribution": "analysis.distribution",
        "analysis.distribution": "analysis.distribution",
        "segmentation": "analysis.segmentation",
        "analysis_segmentation": "analysis.segmentation",
        "analysis.segmentation": "analysis.segmentation",
        "group_compare": "analysis.group_compare",
        "analysis_group_compare": "analysis.group_compare",
        "analysis.group_compare": "analysis.group_compare",
        "correlation": "analysis.correlation",
        "analysis_correlation": "analysis.correlation",
        "analysis.correlation": "analysis.correlation",
        "factor_relationship": "analysis.factor_relationship",
        "analysis_factor_relationship": "analysis.factor_relationship",
        "analysis.factor_relationship": "analysis.factor_relationship",
        "regression": "analysis.regression",
        "analysis_regression": "analysis.regression",
        "analysis.regression": "analysis.regression",
        "describe": "data.describe",
        "data_describe": "data.describe",
        "data.describe": "data.describe",
        "profile": "data.profile",
        "data_profile": "data.profile",
        "data.profile": "data.profile",
        "synthesis": "synthesis",
    }
    # Tool names are another common provider shorthand for the capability
    # they implement.  Derive these aliases from the same registry-facing
    # table used for method inference so the two paths cannot drift into
    # separate hidden enums.
    for tool_name, capability in method_capabilities:
        capability_aliases.setdefault(tool_name.casefold(), capability)
    natural_language_capabilities = (
        (
            ("数据质量", "缺失值", "缺失率", "重复值", "异常值", "data quality"),
            "data.quality",
        ),
        (
            ("pearson", "spearman", "相关系数", "相关关系", "相关性", "correlation"),
            "analysis.correlation",
        ),
        (
            ("多变量", "多因素", "影响因素", "驱动因素", "factor relationship"),
            "analysis.factor_relationship",
        ),
        (
            ("回归", "regression", "ols"),
            "analysis.regression",
        ),
        (
            ("分布", "偏度", "峰度", "distribution"),
            "analysis.distribution",
        ),
        (
            ("分群", "聚类", "segmentation", "kmeans"),
            "analysis.segmentation",
        ),
        (
            ("分组聚合", "分组对比", "group aggregate", "group compare"),
            "analysis.group_compare",
        ),
        (
            ("综合结论", "证据汇总", "业务建议", "synthesis"),
            "synthesis",
        ),
    )
    capability_requirement_defaults = {
        "data.quality": ["missingness", "sample_size", "limitations"],
        "data.describe": ["distribution", "sample_size", "limitations"],
        "data.profile": ["schema", "missingness", "sample_size", "limitations"],
        "analysis.top_n": ["dimension", "metric", "sample_size", "limitations"],
        "analysis.distribution": ["distribution", "sample_size", "limitations"],
        "analysis.segmentation": ["sample_size", "limitations"],
        "analysis.regression": ["method", "sample_size", "limitations"],
    }
    enriched_steps: list[Any] = []
    for raw_step in normalized.get("method_plan") or []:
        if not isinstance(raw_step, dict):
            enriched_steps.append(raw_step)
            continue
        step = dict(raw_step)
        if not _text(step.get("goal")):
            step["goal"] = (
                _text(step.get("task"))
                or _text(step.get("subject"))
                or _text(step.get("title"))
                or _text(step.get("name"))
                or _text(step.get("method"))
            )
        if not _text(step.get("expected_output")):
            step["expected_output"] = _text(step.get("output"))
        declared_capability = _text(step.get("required_capability"))
        alias_key = declared_capability.casefold().replace("-", "_").replace(" ", "_")
        canonical_declared = capability_aliases.get(alias_key, "")
        if canonical_declared:
            step["required_capability"] = canonical_declared
        if not _text(step.get("required_capability")):
            method = _text(step.get("method")).casefold()
            inferred_capability = next(
                (
                    capability
                    for tool_name, capability in method_capabilities
                    if tool_name in method
                ),
                "",
            )
            if not inferred_capability:
                evidence_hints = " ".join(_text_list(step.get("evidence_requirements")))
                semantic_text = " ".join(
                    value
                    for value in (
                        method,
                        _text(step.get("goal")).casefold(),
                        _text(step.get("expected_output")).casefold(),
                        evidence_hints.casefold(),
                    )
                    if value
                )
                inferred_capability = next(
                    (
                        capability
                        for markers, capability in natural_language_capabilities
                        if any(marker in semantic_text for marker in markers)
                    ),
                    "",
                )
            if inferred_capability:
                step["required_capability"] = inferred_capability
        # Requirement identities are compiler-owned. Preserve an explicit list
        # only when every value is a compiler-known canonical input. Otherwise
        # treat the natural-language values as hints and derive deterministic
        # requirements from the selected capability; accepting them verbatim
        # would make a hidden enum out of a free-form tool field.
        capability = _text(step.get("required_capability"))
        supplied_requirements = _text_list(step.get("evidence_requirements"))
        supplied_are_canonical = bool(supplied_requirements) and all(
            is_canonical_analysis_requirement_input(item)
            for item in supplied_requirements
        )
        if not supplied_are_canonical:
            defaults = capability_requirement_defaults.get(capability)
            if defaults is not None:
                step["evidence_requirements"] = list(defaults)
            elif capability in {
                "analysis.correlation",
                "analysis.factor_relationship",
            }:
                step.pop("evidence_requirements", None)
            else:
                step["evidence_requirements"] = ["method", "sample_size", "limitations"]
        if "required_claim_keys" not in step:
            default_claim_key = _text(step.get("claim_type")) or capability
            if default_claim_key:
                step["required_claim_keys"] = [default_claim_key]
        # Capability is the semantic source of truth in both directions.
        # Provider-authored review labels or copied combination modes must
        # neither turn a synthesis step into a raw-data computation nor turn
        # profiling/analysis steps into evidence-only synthesis.  The latter
        # failure strips every dataset binding and makes the main analysis
        # tools impossible to call.
        supplied_mode = _text(step.get("combination_mode"))
        mode = (
            supplied_mode
            if supplied_mode and supplied_mode not in SUPPORTED_ANALYSIS_PLAN_MODES
            else (
                "synthesis"
                if capability == "synthesis"
                else (
                    "independent"
                    if capability
                    else (supplied_mode or "independent")
                )
            )
        )
        step["combination_mode"] = mode
        if mode == "independent":
            dataset_inputs = _text_list(step.get("dataset_inputs"))
            if not dataset_inputs:
                dataset_alias = _text(step.get("dataset"))
                if dataset_alias:
                    dataset_inputs = [dataset_alias]
                elif unique_dataset:
                    dataset_inputs = [unique_dataset]
            if (
                unique_dataset
                and len(dataset_inputs) == 1
                and dataset_inputs[0].casefold() in generic_aliases
                and dataset_inputs[0] not in by_dataset
                and dataset_inputs[0] not in by_id
            ):
                dataset_inputs = [unique_dataset]
            step["dataset_inputs"] = dataset_inputs
        elif mode == "synthesis":
            # Synthesis consumes prior evidence, never raw dataset handles.
            # LLM-authored shorthand commonly repeats the current dataset on
            # every step; normalizing this deterministic redundancy prevents
            # an avoidable invalid_synthesis_binding retry.
            step["dataset_inputs"] = []
            # A synthesis step consumes prior evidence; it is not another
            # computation that must manufacture method/sample-size evidence.
            # Treating generic LLM evidence hints as execution requirements
            # makes the completion evaluator chase an impossible final tool
            # ritual after all substantive analysis is already complete.
            step["evidence_requirements"] = ["limitations"]
            if not _step_id_list(step.get("required_evidence_step_ids")):
                step["required_evidence_step_ids"] = [
                    _step_id_text(item.get("step_id"))
                    for item in enriched_steps
                    if isinstance(item, dict)
                    and _step_id_text(item.get("step_id"))
                    and _text(item.get("combination_mode")) != "synthesis"
                ]
        enriched_steps.append(step)
    normalized["method_plan"] = enriched_steps
    return normalized


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
    # ``review_status`` is provider-authored input unless accompanied by the
    # compiler-owned requirement snapshot. Never let a model-supplied label
    # bypass executable-plan enrichment and synthesis normalization.
    if require_executable and incoming_analysis_requirements is None:
        normalized = _enrich_executable_plan_shorthand(
            normalized,
            dataset_contracts=dataset_contracts,
        )

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
        # Project compiled requirement IDs onto each step so the executable
        # plan is self-describing for binding/audit. The requirements dict is
        # the canonical source; the step field is a derived projection.
        grouped_for_step = normalized.get("analysis_requirements") or {}
        step["requirement_ids"] = [
            requirement["id"]
            for requirement in (
                grouped_for_step.get(step_id, [])
                if isinstance(grouped_for_step, dict)
                else []
            )
            if isinstance(requirement, dict) and requirement.get("id")
        ]
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


def validate_compiled_analysis_plan_for_projection(
    plan: dict[str, Any],
) -> ContractValidationResult:
    """Validate state-owned compiler output without re-running the compiler."""

    if not isinstance(plan, dict):
        return _error("invalid_plan", "AnalysisPlan must be a JSON object.")
    if plan.get("contract_version") != ANALYSIS_PLAN_CONTRACT_VERSION:
        return _error(
            "unsupported_contract_version",
            "Workflow projection requires the current AnalysisPlan contract.",
        )
    if plan.get("review_status") != "executable":
        return _error(
            "analysis_plan_not_executable",
            "Workflow projection requires state-owned executable compiler output.",
        )
    grouped = plan.get("analysis_requirements")
    if not isinstance(grouped, dict):
        return _error(
            "invalid_analysis_requirements",
            "Executable AnalysisPlan requires grouped analysis_requirements.",
        )
    try:
        for raw_step_id, requirements in grouped.items():
            step_id = _step_id_text(raw_step_id)
            if not step_id or not isinstance(requirements, list):
                raise ValueError(
                    "AnalysisPlan analysis_requirements must be grouped by step_id."
                )
            for requirement in requirements:
                validate_analysis_requirement(requirement)
                if requirement["step_id"] != step_id:
                    raise ValueError(
                        "AnalysisRequirement step_id must match its plan group."
                    )
    except ValueError as exc:
        return _error("invalid_analysis_requirements", str(exc))
    return _validate_executable_plan(plan, dataset_contracts=None)
