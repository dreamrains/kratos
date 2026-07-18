"""Canonical analysis-requirement compilation and satisfaction evaluation."""

from __future__ import annotations

from typing import Any


ANALYSIS_REQUIREMENT_CONTRACT_VERSION = "analysis_requirement.v1"
ALLOWED_REQUIREMENT_CATEGORIES = frozenset({
    "assumption",
    "data",
    "inference",
    "limitation",
    "measurement",
    "method",
    "output",
    "provenance",
})
ALLOWED_REQUIREMENT_NECESSITY = frozenset({"required", "conditional", "not_applicable"})
ALLOWED_REQUIREMENT_STATUSES = frozenset({"pending", "satisfied", "unmet", "not_applicable"})
ALLOWED_UNMET_ACTIONS = frozenset({"block_analysis", "block_claim", "downgrade_claim", "disclose"})

_ROUTE_REQUIREMENT_INPUTS = {
    "trend": ("time_scope", "sample_size", "trend_statistics", "limitations"),
    "period_compare": ("period_definition", "period_comparability", "metric_delta", "limitations"),
    "dimension_decomposition": ("dimension_scope", "contribution_table", "metric_delta", "limitations"),
    "rate_analysis": ("rate_definition", "denominator", "sample_size", "limitations"),
    "correlation": ("variables", "correlation_method", "sample_size", "limitations"),
    "cohort": ("id_scope", "cohort_definition", "retention_metric", "limitations"),
    "funnel": ("step_definition", "denominator", "conversion_rates", "limitations"),
}
_DEFAULT_ROUTE_REQUIREMENT_INPUTS = ("method", "sample_size", "limitations")


_REQUIREMENT_DEFINITIONS = {
    "assumptions": {
        "category": "assumption",
        "required_evidence_fields": ["assumptions"],
        "assumption_checks": [],
        "unmet_action": "disclose",
    },
    "confidence_interval": {
        "category": "inference",
        "required_evidence_fields": ["confidence_interval"],
        "assumption_checks": ["method_appropriate_for_design"],
        "unmet_action": "block_claim",
    },
    "calculation_method": {
        "category": "method",
        "required_evidence_fields": ["calculation_method"],
        "assumption_checks": [],
        "unmet_action": "block_claim",
    },
    "confidence_reason": {
        "category": "output",
        "required_evidence_fields": ["confidence_reason"],
        "assumption_checks": [],
        "unmet_action": "disclose",
    },
    "correlation": {
        "category": "inference",
        "required_evidence_fields": ["correlation"],
        "assumption_checks": ["correlation_method_appropriate"],
        "unmet_action": "block_claim",
    },
    "distribution": {
        "category": "measurement",
        "required_evidence_fields": ["distribution"],
        "assumption_checks": [],
        "unmet_action": "downgrade_claim",
    },
    "effect_size": {
        "category": "inference",
        "required_evidence_fields": ["effect_size"],
        "assumption_checks": [],
        "unmet_action": "block_claim",
    },
    "impact_estimate": {
        "category": "inference",
        "required_evidence_fields": ["impact_estimate"],
        "assumption_checks": [],
        "unmet_action": "downgrade_claim",
    },
    "sample_size": {
        "category": "data",
        "required_evidence_fields": ["sample_size"],
        "assumption_checks": [],
        "unmet_action": "downgrade_claim",
    },
    "limitations": {
        "category": "limitation",
        "required_evidence_fields": ["limitations"],
        "assumption_checks": [],
        "unmet_action": "disclose",
    },
    "significance": {
        "category": "inference",
        "required_evidence_fields": ["significance"],
        "assumption_checks": ["method_appropriate_for_design"],
        "unmet_action": "block_claim",
    },
    "time_scope": {
        "category": "measurement",
        "required_evidence_fields": ["time_scope"],
        "assumption_checks": [],
        "unmet_action": "block_claim",
    },
}


def _register_definitions(
    names: tuple[str, ...],
    *,
    category: str,
    unmet_action: str,
) -> None:
    for name in names:
        if name in _REQUIREMENT_DEFINITIONS:
            raise RuntimeError(f"Duplicate AnalysisRequirement definition: {name}")
        _REQUIREMENT_DEFINITIONS[name] = {
            "category": category,
            "required_evidence_fields": [name],
            "assumption_checks": [],
            "unmet_action": unmet_action,
        }


_register_definitions(
    (
        "cohort_size", "comparison_group", "data_grain", "data_needed", "dimension",
        "feature_exposure", "field_semantics", "forecast_window", "id_scope", "missingness",
        "outcome", "outcome_metric", "periods", "schema", "segment", "steps",
        "target_definition", "training_window", "treatment",
    ),
    category="data",
    unmet_action="block_analysis",
)
_register_definitions(
    (
        "amount", "benefit", "confidence", "contribution", "contribution_table",
        "conversion_rate", "conversion_rates", "cost", "denominator", "driver_contribution",
        "dropoff", "effect", "effect_estimate", "frequency", "impact", "largest_drop_off",
        "metric", "metric_delta", "metric_distribution", "net_value", "period_delta",
        "retention_metric", "retention_rate", "revenue", "segment_pattern", "step_conversion",
        "top_dimensions", "trend", "trend_direction", "trend_statistics", "validation_metric",
    ),
    category="measurement",
    unmet_action="block_claim",
)
_register_definitions(
    (
        "cohort_definition", "comparison_design", "correlation_method", "cost_assumptions",
        "dimension_scope", "drivers", "hypothesis", "method", "period_comparability",
        "period_definition", "rate_definition", "sensitivity_or_confidence", "step_definition",
        "validation", "variables",
    ),
    category="method",
    unmet_action="downgrade_claim",
)


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _name(value: Any) -> str:
    return "_".join(_text(value).casefold().replace("-", " ").split())


def requirement_ids_for_route(route: Any) -> list[str]:
    """Return compact canonical requirement-name inputs for a route payload."""

    if not isinstance(route, dict):
        return []
    route_value = route
    raw = route_value.get("evidence_requirements")
    if not isinstance(raw, list):
        raw = route_value.get("expected_evidence")
    if not isinstance(raw, list):
        direction = _name(route_value.get("direction") or route_value.get("route"))
        raw = list(_ROUTE_REQUIREMENT_INPUTS.get(direction, _DEFAULT_ROUTE_REQUIREMENT_INPUTS))
    result: list[str] = []
    for item in raw:
        name = _name(item)
        if name and name not in result:
            result.append(name)
    return result


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    result: dict[str, Any] = {}
    for field in ("evidence_policy", "output_policy"):
        item = getattr(value, field, None)
        if isinstance(item, dict):
            result[field] = item
    return result


def _name_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_name(item) for item in value if _name(item)]


def _validate_requirement(requirement: Any) -> None:
    if not isinstance(requirement, dict):
        raise ValueError("AnalysisRequirement must be an object.")
    if requirement.get("contract_version") != ANALYSIS_REQUIREMENT_CONTRACT_VERSION:
        raise ValueError("Unsupported AnalysisRequirement contract_version.")
    for field in ("id", "step_id", "name", "trigger"):
        if not _text(requirement.get(field)):
            raise ValueError(f"AnalysisRequirement requires {field}.")
    if requirement.get("category") not in ALLOWED_REQUIREMENT_CATEGORIES:
        raise ValueError("Invalid AnalysisRequirement category.")
    if requirement.get("necessity") not in ALLOWED_REQUIREMENT_NECESSITY:
        raise ValueError("Invalid AnalysisRequirement necessity.")
    if requirement.get("status") not in ALLOWED_REQUIREMENT_STATUSES:
        raise ValueError("Invalid AnalysisRequirement status.")
    if requirement.get("unmet_action") not in ALLOWED_UNMET_ACTIONS:
        raise ValueError("Invalid AnalysisRequirement unmet_action.")
    for field in ("required_evidence_fields", "assumption_checks", "evidence_ids"):
        value = requirement.get(field)
        if not isinstance(value, list) or not all(_text(item) for item in value):
            if value != []:
                raise ValueError(f"AnalysisRequirement {field} must be a list of strings.")
    if not isinstance(requirement.get("reason"), str):
        raise ValueError("AnalysisRequirement reason must be text.")


def _has_field(record: dict[str, Any], path: str) -> bool:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return value is not None and value != ""


def _matching_records(requirement: dict[str, Any], evidence_records: Any) -> list[dict[str, Any]]:
    records = evidence_records if isinstance(evidence_records, list) else []
    result: list[dict[str, Any]] = []
    requirement_id = requirement["id"]
    step_id = requirement["step_id"]
    required_fields = requirement["required_evidence_fields"]
    for record in records:
        if not isinstance(record, dict):
            continue
        requirement_ids = record.get("requirement_ids")
        explicit_match = isinstance(requirement_ids, list) and requirement_id in requirement_ids
        legacy_match = (
            not isinstance(requirement_ids, list)
            and _text(record.get("step_id")) == step_id
            and all(_has_field(record, field) for field in required_fields)
        )
        if explicit_match or legacy_match:
            result.append(record)
    return result


def evaluate_requirement_satisfaction(
    requirements: Any,
    evidence_records: Any,
) -> list[dict[str, Any]]:
    """Evaluate canonical requirements without inventing statistical shortcuts."""

    if not isinstance(requirements, list):
        raise ValueError("requirements must be a list.")
    evaluated: list[dict[str, Any]] = []
    for raw_requirement in requirements:
        _validate_requirement(raw_requirement)
        requirement = dict(raw_requirement)
        if requirement["necessity"] == "not_applicable":
            requirement["status"] = "not_applicable"
            requirement["evidence_ids"] = []
            evaluated.append(requirement)
            continue
        matches = _matching_records(requirement, evidence_records)
        required_fields = requirement["required_evidence_fields"]
        satisfying = [
            record
            for record in matches
            if all(_has_field(record, field) for field in required_fields)
        ]
        requirement["evidence_ids"] = [
            _text(record.get("id"))
            for record in satisfying
            if _text(record.get("id"))
        ]
        if satisfying:
            requirement["status"] = "satisfied"
            requirement["reason"] = ""
        else:
            requirement["status"] = "unmet"
            missing = ", ".join(required_fields) or "matching evidence"
            requirement["reason"] = f"Missing required evidence: {missing}."
        evaluated.append(requirement)
    return evaluated


def compile_analysis_requirements(
    *,
    plan: Any,
    route: Any,
    playbook: Any,
    dataset_contracts: Any,
    user_intent: Any,
) -> list[dict[str, Any]]:
    plan_value = plan if isinstance(plan, dict) else {}
    provided = plan_value.get("analysis_requirements")
    if provided is not None:
        if not isinstance(provided, dict):
            raise ValueError("AnalysisPlan analysis_requirements must be grouped by step_id.")
        for raw_step_id, group in provided.items():
            step_id = _text(raw_step_id)
            if not step_id or not isinstance(group, list):
                raise ValueError("AnalysisPlan analysis_requirements must be grouped by step_id.")
            for requirement in group:
                _validate_requirement(requirement)
                if requirement["step_id"] != step_id:
                    raise ValueError("AnalysisRequirement step_id must match its plan group.")
    method_plan = plan_value.get("method_plan")
    if not isinstance(method_plan, list):
        return []

    steps: list[tuple[str, dict[str, Any]]] = []
    for index, raw_step in enumerate(method_plan, 1):
        if not isinstance(raw_step, dict):
            continue
        step_id = _text(raw_step.get("step_id")) or f"step_{index}"
        steps.append((step_id, raw_step))
    if not steps:
        return []

    inputs_by_step: dict[str, dict[str, set[str]]] = {step_id: {} for step_id, _ in steps}
    for step_id, raw_step in steps:
        for name in _name_list(raw_step.get("evidence_requirements")):
            inputs_by_step[step_id].setdefault(name, set()).add("plan.method_plan.evidence_requirements")

    target_step_id = next(
        (
            step_id
            for step_id, raw_step in steps
            if _name(raw_step.get("node_type")) == "analysis"
        ),
        steps[0][0],
    )
    external_inputs: list[tuple[str, str]] = []
    external_inputs.extend(
        (name, "plan.statistical_requirements")
        for name in _name_list(plan_value.get("statistical_requirements"))
    )
    external_inputs.extend(
        (name, "route.evidence_requirements")
        for name in requirement_ids_for_route(route)
    )
    playbook_value = _mapping(playbook)
    evidence_policy = _mapping(playbook_value.get("evidence_policy"))
    output_policy = _mapping(playbook_value.get("output_policy"))
    external_inputs.extend(
        (name, "playbook.evidence_policy.required_evidence")
        for name in _name_list(evidence_policy.get("required_evidence"))
    )
    external_inputs.extend(
        (name, "playbook.output_policy.statistical_requirements")
        for name in _name_list(output_policy.get("statistical_requirements"))
    )
    for name, origin in external_inputs:
        inputs_by_step[target_step_id].setdefault(name, set()).add(origin)

    compiled: list[dict[str, Any]] = []
    for step_id, _ in steps:
        names = sorted(inputs_by_step[step_id])
        for name in names:
            definition = _REQUIREMENT_DEFINITIONS.get(name)
            compatibility_definition = definition is None
            if definition is None:
                definition = {
                    "category": "output",
                    "required_evidence_fields": [name],
                    "assumption_checks": [],
                    "unmet_action": "disclose",
                }
            compiled.append({
                "contract_version": ANALYSIS_REQUIREMENT_CONTRACT_VERSION,
                "id": f"req_{_name(step_id)}_{name}",
                "step_id": step_id,
                "category": definition["category"],
                "name": name,
                "necessity": "required",
                "trigger": f"explicit compiler input: {name}",
                "status": "pending",
                "required_evidence_fields": list(definition["required_evidence_fields"]),
                "assumption_checks": list(definition["assumption_checks"]),
                "unmet_action": definition["unmet_action"],
                "evidence_ids": [],
                "reason": (
                    "Compatibility requirement compiled from an unregistered saved input."
                    if compatibility_definition
                    else ""
                ),
            })
    return compiled
