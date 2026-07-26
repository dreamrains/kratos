"""Canonical analysis-requirement compilation and satisfaction evaluation."""

from __future__ import annotations

import hashlib
import re
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

_SAFE_CANONICAL_STEP_ID = re.compile(r"step_[a-z0-9]+(?:_[a-z0-9]+)*\Z")

_COMPARISON_REQUIREMENT_INPUTS = (
    "effective_sample_size",
    "denominator",
    "missingness",
    "estimand",
    "effect_estimate",
    "calculation_method",
    "assumptions",
    "sample_adequacy",
)
_TIME_SERIES_REQUIREMENT_INPUTS = (
    "time_frequency",
    "missing_intervals",
    "window_comparability",
    "autocorrelation_awareness",
    "effective_sample_size",
    "missingness",
    "calculation_method",
    "assumptions",
)
_ROUTE_REQUIREMENT_INPUTS = {
    "trend": (
        "time_scope", "sample_size", "trend_statistics", "limitations",
        *_TIME_SERIES_REQUIREMENT_INPUTS,
    ),
    "period_compare": (
        "period_definition", "period_comparability", "metric_delta", "limitations",
        *_COMPARISON_REQUIREMENT_INPUTS,
        "time_frequency", "missing_intervals", "window_comparability",
    ),
    "dimension_decomposition": ("dimension_scope", "contribution_table", "metric_delta", "limitations"),
    "rate_analysis": ("rate_definition", "denominator", "sample_size", "limitations"),
    "correlation": ("variables", "correlation_method", "sample_size", "limitations"),
    "cohort": ("id_scope", "cohort_definition", "retention_metric", "limitations"),
    "funnel": ("step_definition", "denominator", "conversion_rates", "limitations"),
}
_DEFAULT_ROUTE_REQUIREMENT_INPUTS = ("method", "sample_size", "limitations")
_CAPABILITY_REQUIREMENT_INPUTS = {
    "analysis.experiment": (
        *_COMPARISON_REQUIREMENT_INPUTS,
        "effect_size",
        "significance",
    ),
    "analysis.group_compare": _COMPARISON_REQUIREMENT_INPUTS,
    "analysis.segment_compare": _COMPARISON_REQUIREMENT_INPUTS,
    "analysis.period_compare": (
        *_COMPARISON_REQUIREMENT_INPUTS,
        "period_definition",
        "period_comparability",
        "time_frequency",
        "missing_intervals",
        "window_comparability",
    ),
    "analysis.time_series": _TIME_SERIES_REQUIREMENT_INPUTS,
    "analysis.causal": (
        "effect_estimate",
        "confidence_interval",
        "calculation_method",
        "assumptions",
        "sample_adequacy",
        "identification_status",
    ),
    "analysis.factor_relationship": (
        "grain_definition",
        "target_definition",
        "missingness_assessment",
        "effective_sample_size",
        "univariate_association",
        "multivariable_adjustment",
        "multiplicity_control",
        "collinearity_assessment",
        "stability_or_validation",
        "time_dependence_assessment",
        "effect_size_or_predictive_contribution",
        "limitations_and_alternatives",
    ),
}
_REQUIREMENT_CAPABILITY_HINTS = {
    "assumptions": ("analysis.group_compare", "analysis.period_compare", "analysis.time_series"),
    "autocorrelation_awareness": ("analysis.time_series",),
    "calculation_method": ("analysis.group_compare", "analysis.period_compare", "analysis.time_series"),
    "confidence_interval": (
        "analysis.group_compare", "analysis.period_compare", "analysis.experiment",
        "analysis.causal", "analysis.forecast",
    ),
    "correlation": ("analysis.correlation",),
    "correlation_method": ("analysis.correlation",),
    "distribution": ("data.describe",),
    "effect": ("analysis.experiment", "analysis.causal"),
    "effect_estimate": ("analysis.experiment", "analysis.causal"),
    "effect_size": ("analysis.experiment", "analysis.causal"),
    "effective_sample_size": ("analysis.group_compare", "analysis.period_compare", "analysis.time_series"),
    "estimand": ("analysis.group_compare", "analysis.period_compare"),
    "missing_intervals": ("analysis.time_series", "analysis.period_compare"),
    "multiplicity_handling": ("analysis.segment_compare", "analysis.group_compare"),
    "metric_delta": ("analysis.period_compare",),
    "period_comparability": ("analysis.period_compare",),
    "period_definition": ("analysis.period_compare",),
    "significance": ("analysis.experiment", "analysis.correlation"),
    "sample_adequacy": ("analysis.group_compare", "analysis.period_compare"),
    "seasonality_estimability": ("analysis.time_series",),
    "time_frequency": ("analysis.time_series", "analysis.period_compare"),
    "window_comparability": ("analysis.period_compare", "analysis.time_series"),
    "assignment_unit": ("analysis.experiment",),
    "attrition": ("analysis.experiment",),
    "balance_diagnostics": ("analysis.experiment", "analysis.causal"),
    "identification_status": ("analysis.experiment", "analysis.causal"),
    "overlap_diagnostics": ("analysis.causal",),
    "parallel_trends": ("analysis.causal",),
    "power_mde": ("analysis.experiment",),
    "randomization_integrity": ("analysis.experiment",),
}


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
    "sample_adequacy": {
        "category": "assumption",
        "required_evidence_fields": ["sample_adequacy.status", "sample_adequacy.design"],
        "assumption_checks": [],
        "unmet_action": "block_claim",
    },
    "seasonality_estimability": {
        "category": "assumption",
        "required_evidence_fields": ["seasonality_estimability"],
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
        "effective_sample_size", "feature_exposure", "field_semantics", "forecast_window",
        "id_scope", "missing_intervals", "missingness",
        "outcome", "outcome_metric", "periods", "schema", "segment", "steps",
        "target_definition", "training_window", "treatment",
    ),
    category="data",
    unmet_action="block_analysis",
)
_register_definitions(
    (
        "assignment_rule", "assignment_unit", "cutoff_assignment", "design_type",
        "exposure_definition", "instrument_definition", "outcome_definition",
        "per_arm_sample_size", "treatment_arms", "treatment_timing",
    ),
    category="data",
    unmet_action="block_claim",
)
_register_definitions(
    (
        "amount", "benefit", "confidence", "contribution", "contribution_table",
        "conversion_rate", "conversion_rates", "cost", "denominator", "driver_contribution",
        "dropoff", "effect", "effect_estimate", "frequency", "impact", "largest_drop_off",
        "estimand", "metric", "metric_delta", "metric_distribution", "net_value", "period_delta",
        "retention_metric", "retention_rate", "revenue", "segment_pattern", "step_conversion",
        "time_frequency", "top_dimensions", "trend", "trend_direction", "trend_statistics",
        "validation_metric",
    ),
    category="measurement",
    unmet_action="block_claim",
)
_register_definitions(
    (
        "autocorrelation_awareness", "cohort_definition", "comparison_design",
        "correlation_method", "cost_assumptions",
        "dimension_scope", "drivers", "hypothesis", "method", "period_comparability",
        "period_definition", "rate_definition", "sensitivity_or_confidence", "step_definition",
        "validation", "variables", "window_comparability",
    ),
    category="method",
    unmet_action="downgrade_claim",
)
_register_definitions(
    (
        "attrition", "balance_diagnostics", "bandwidth_sensitivity",
        "discontinuity_diagnostics", "exclusion_restriction",
        "identification_status", "instrument_relevance", "overlap_diagnostics",
        "parallel_trends", "power_mde", "randomization_integrity",
    ),
    category="assumption",
    unmet_action="block_claim",
)

_register_definitions(
    ("alternative_explanations",),
    category="limitation",
    unmet_action="disclose",
)

_register_definitions(
    ("multiplicity_handling",),
    category="inference",
    unmet_action="block_claim",
)

# Factor-relationship method inputs (Task 7). These match the canonical
# six-step factor_relationship playbook and the analysis.factor_relationship
# capability inputs. They are explicitly categorized so the compiler can
# route each input to the right method step.
_factor_relationship_data_inputs = (
    "grain_definition",
    "missingness_assessment",
)
_register_definitions(
    _factor_relationship_data_inputs,
    category="data",
    unmet_action="block_analysis",
)
_register_definitions(
    (
        "univariate_association",
        "multivariable_adjustment",
        "multiplicity_control",
        "effect_size_or_predictive_contribution",
    ),
    category="inference",
    unmet_action="block_claim",
)
_register_definitions(
    (
        "collinearity_assessment",
        "stability_or_validation",
        "time_dependence_assessment",
    ),
    category="assumption",
    unmet_action="downgrade_claim",
)
_register_definitions(
    ("limitations_and_alternatives",),
    category="limitation",
    unmet_action="disclose",
)

# Inferential factor-relationship coefficients require an explicit method-fit
# assumption check so a malformed design cannot publish significance. Each
# inference-category factor input inherits this guard through the explicit
# definitions below.
_REQUIREMENT_DEFINITIONS["univariate_association"] = {
    "category": "inference",
    "required_evidence_fields": ["univariate_association"],
    "assumption_checks": ["method_appropriate_for_design"],
    "unmet_action": "block_claim",
}
_REQUIREMENT_DEFINITIONS["multivariable_adjustment"] = {
    "category": "inference",
    "required_evidence_fields": ["multivariable_adjustment"],
    "assumption_checks": ["method_appropriate_for_design"],
    "unmet_action": "block_claim",
}
_REQUIREMENT_DEFINITIONS["multiplicity_control"] = {
    "category": "inference",
    "required_evidence_fields": ["multiplicity_control"],
    "assumption_checks": ["method_appropriate_for_design"],
    "unmet_action": "block_claim",
}
_REQUIREMENT_DEFINITIONS["effect_size_or_predictive_contribution"] = {
    "category": "inference",
    "required_evidence_fields": ["effect_size_or_predictive_contribution"],
    "assumption_checks": ["method_appropriate_for_design"],
    "unmet_action": "block_claim",
}


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _step_id_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _step_id_component(step_id: str) -> str:
    if _SAFE_CANONICAL_STEP_ID.fullmatch(step_id):
        return step_id
    digest = hashlib.sha256(step_id.encode("utf-8")).hexdigest()
    return f"unsafe_{digest}"


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


def _step_for_external_input(
    name: str,
    steps: list[tuple[str, dict[str, Any]]],
    inputs_by_step: dict[str, dict[str, set[str]]],
) -> str:
    explicit_matches = [step_id for step_id, _ in steps if name in inputs_by_step[step_id]]
    if explicit_matches:
        return explicit_matches[0]

    capability_hints = _REQUIREMENT_CAPABILITY_HINTS.get(name, ())
    for capability in capability_hints:
        for step_id, step in steps:
            if _text(step.get("required_capability")) == capability:
                return step_id

    definition = _REQUIREMENT_DEFINITIONS.get(name) or {}
    category = definition.get("category")
    preferred_node_types = {
        "assumption": ("analysis", "evidence"),
        "data": ("data_check", "method", "analysis"),
        "inference": ("analysis",),
        "limitation": ("evidence", "analysis"),
        "measurement": ("analysis", "data_check"),
        "method": ("method", "analysis", "data_check"),
        "output": ("evidence", "analysis"),
        "provenance": ("evidence", "analysis"),
    }.get(category, ("analysis",))
    for node_type in preferred_node_types:
        for step_id, step in steps:
            if _name(step.get("node_type")) == node_type:
                return step_id
    return steps[0][0]


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


def _field_value(record: dict[str, Any], path: str) -> Any:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _requirement_evidence_is_acceptable(
    requirement: dict[str, Any],
    record: dict[str, Any],
) -> bool:
    name = requirement.get("name")
    if name == "sample_adequacy":
        return _name(_field_value(record, "sample_adequacy.status")) in {
            "adequate",
            "adequate_with_limits",
            "inadequate",
            "insufficient",
            "not_estimable",
            "estimable_with_limits",
            "satisfied",
        }
    if name == "seasonality_estimability":
        value = _field_value(record, "seasonality_estimability")
        status = value.get("status") if isinstance(value, dict) else value
        required_period = _name(
            (requirement.get("parameters") or {}).get("seasonality_period")
        )
        evidence_period = _name(
            value.get("period") or value.get("seasonality_period")
        ) if isinstance(value, dict) else ""
        return (
            _name(status) in {"estimable", "estimable_with_limits", "not_estimable"}
            and (not required_period or evidence_period == required_period)
        )
    if name == "window_comparability":
        value = _field_value(record, "window_comparability")
        status = value.get("status") if isinstance(value, dict) else value
        if isinstance(status, bool):
            return status
        return _name(status) in {
            "comparable",
            "comparable_with_adjustment",
            "not_comparable",
            "passed",
            "satisfied",
        }
    if name == "multiplicity_handling":
        value = _field_value(record, "multiplicity_handling")
        strategy = value.get("strategy") if isinstance(value, dict) else value
        normalized_strategy = _name(strategy)
        if normalized_strategy == "not_applicable":
            return bool(
                (requirement.get("parameters") or {}).get("not_applicable_allowed")
            )
        return normalized_strategy in {
            "bonferroni",
            "holm",
            "benjamini_hochberg",
            "exploratory",
            "exploratory_label",
        }
    if name == "power_mde":
        value = _field_value(record, "power_mde")
        purpose = _name(value.get("purpose")) if isinstance(value, dict) else ""
        allowed = {
            _name(item)
            for item in (requirement.get("parameters") or {}).get("allowed_purposes", [])
            if _name(item)
        }
        return bool(purpose and purpose in allowed)
    if name in {
        "balance_diagnostics", "bandwidth_sensitivity", "discontinuity_diagnostics",
        "instrument_relevance", "overlap_diagnostics", "parallel_trends",
        "randomization_integrity",
    }:
        value = _field_value(record, name)
        status = value.get("status") if isinstance(value, dict) else value
        return _name(status) in {
            "assessed", "passed", "satisfied", "failed", "not_estimable",
            "adequate", "inadequate",
        }
    if name == "identification_status":
        value = _field_value(record, "identification_status")
        status = value.get("status") if isinstance(value, dict) else value
        return _name(status) in {"identified", "partially_identified", "not_identified"}
    return True


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


def _assumption_check_succeeded(record: dict[str, Any], check_name: str) -> bool:
    checks = record.get("assumption_checks")
    if isinstance(checks, dict):
        value = checks.get(check_name)
        status = value.get("status") if isinstance(value, dict) else value
        return _name(status) in {"passed", "satisfied", "success", "successful"}
    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict):
                continue
            name = _text(item.get("name") or item.get("check") or item.get("id"))
            if name == check_name and _name(item.get("status")) in {
                "passed",
                "satisfied",
                "success",
                "successful",
            }:
                return True
    return False


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
        assumption_checks = requirement["assumption_checks"]
        satisfying = [
            record
            for record in matches
            if all(_has_field(record, field) for field in required_fields)
            and all(_assumption_check_succeeded(record, check) for check in assumption_checks)
            and _requirement_evidence_is_acceptable(requirement, record)
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
            missing_items = list(required_fields) + list(assumption_checks)
            missing = ", ".join(missing_items) or "matching evidence"
            requirement["reason"] = f"Missing required evidence: {missing}."
        evaluated.append(requirement)
    return evaluated


_COMPARISON_CAPABILITIES = {
    "analysis.experiment",
    "analysis.group_compare",
    "analysis.segment_compare",
    "analysis.period_compare",
}
_INFERENTIAL_CLAIM_TYPES = {
    "inferential",
    "generalized_difference",
    "population_difference",
}

_CAUSAL_DESIGN_ALIASES = {
    "randomized": "randomized_experiment",
    "randomized_controlled_trial": "randomized_experiment",
    "rct": "randomized_experiment",
    "ab_test": "randomized_experiment",
    "did": "difference_in_differences",
    "difference_in_difference": "difference_in_differences",
    "propensity_score_matching": "matching",
    "inverse_probability_weighting": "weighting",
    "iv": "instrumental_variables",
    "instrumental_variable": "instrumental_variables",
    "rd": "regression_discontinuity",
    "regression_discontinuity_design": "regression_discontinuity",
    "before_after": "pre_post",
    "before_after_comparison": "pre_post",
}

_CAUSAL_DESIGN_DIAGNOSTICS = {
    "randomized_experiment": (
        "assignment_unit", "treatment_arms", "exposure_definition",
        "outcome_definition", "per_arm_sample_size", "randomization_integrity",
        "balance_diagnostics", "attrition",
    ),
    "difference_in_differences": (
        "comparison_group", "treatment_timing", "parallel_trends",
    ),
    "matching": ("overlap_diagnostics", "balance_diagnostics"),
    "weighting": ("overlap_diagnostics", "balance_diagnostics"),
    "instrumental_variables": (
        "instrument_definition", "instrument_relevance", "exclusion_restriction",
    ),
    "regression_discontinuity": (
        "cutoff_assignment", "discontinuity_diagnostics", "bandwidth_sensitivity",
    ),
}
_EXPERIMENT_CORE_DESIGN_FACTS = (
    "design_type",
    "assignment_unit",
    "treatment_arms",
    "exposure_definition",
    "outcome_definition",
    "assignment_rule",
)
_CAUSAL_CORE_DESIGN_FACTS = (
    "design_type",
    "exposure_definition",
    "outcome_definition",
)
_USER_DEFINITIONAL_REQUIREMENTS = frozenset({
    *_EXPERIMENT_CORE_DESIGN_FACTS,
    *_CAUSAL_CORE_DESIGN_FACTS,
    "comparison_group",
    "treatment_timing",
    "instrument_definition",
    "exclusion_restriction",
    "cutoff_assignment",
})


def _causal_design_type(step: dict[str, Any]) -> str:
    design = _name(
        step.get("design_type")
        or step.get("causal_design")
        or step.get("identification_strategy")
    )
    return _CAUSAL_DESIGN_ALIASES.get(design, design)


def _add_requirement_metadata(
    metadata: dict[str, dict[str, Any]],
    names: tuple[str, ...],
    *,
    trigger: str,
    unmet_action: str = "block_claim",
) -> None:
    for name in names:
        metadata.setdefault(name, {
            "trigger": trigger,
            "unmet_action": unmet_action,
        })


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return None
    return converted if converted > 0 else None


def _step_requirement_metadata(
    step: dict[str, Any],
    *,
    user_intent: Any,
) -> dict[str, dict[str, Any]]:
    capability = _text(step.get("required_capability"))
    metadata: dict[str, dict[str, Any]] = {}
    claim_type = _name(step.get("claim_type") or step.get("inference_mode"))
    intent_text = _text(user_intent).casefold()

    if capability in _COMPARISON_CAPABILITIES:
        sampling_structure = _name(step.get("sampling_structure"))
        if not sampling_structure:
            sampling_structure = (
                "paired_or_repeated"
                if capability == "analysis.period_compare"
                else "independent_groups"
            )
        metadata["sample_adequacy"] = {
            "parameters": {"sampling_structure": sampling_structure},
            "trigger": f"comparison capability with {sampling_structure} sampling structure",
        }
        inferential = (
            claim_type in _INFERENTIAL_CLAIM_TYPES
            or step.get("generalize") is True
            or any(
                marker in intent_text
                for marker in ("confidence interval", "generalize", "population difference", "置信区间", "总体差异")
            )
        )
        if inferential:
            metadata["confidence_interval"] = {
                "trigger": "inferential or generalized comparison claim",
            }

        comparison_count = _positive_int(step.get("comparison_count"))
        if comparison_count is None and isinstance(step.get("segments"), list):
            comparison_count = max(0, len(step["segments"]) - 1)
        if (
            (comparison_count is not None and comparison_count > 1)
            or step.get("multiple_comparisons") is True
        ):
            metadata["multiplicity_handling"] = {
                "trigger": "multiple comparison claim",
                "parameters": {
                    "comparison_count": comparison_count or 2,
                    "exploratory_label_allowed": True,
                },
            }

    if capability == "analysis.dimension_decomposition":
        comparison_count = _positive_int(step.get("comparison_count"))
        if comparison_count is None and isinstance(step.get("segments"), list):
            comparison_count = len(step["segments"])
        if (
            (comparison_count is not None and comparison_count > 1)
            or step.get("multiple_comparisons") is True
        ):
            metadata["multiplicity_handling"] = {
                "trigger": "multiple segment comparison",
                "parameters": {
                    "comparison_count": comparison_count or 2,
                    "exploratory_label_allowed": True,
                },
            }

    seasonality_period = _name(step.get("seasonality_period"))
    if capability == "analysis.time_series" and claim_type in _INFERENTIAL_CLAIM_TYPES:
        metadata["confidence_interval"] = {
            "trigger": "inferential time-series claim",
        }
        metadata["sample_adequacy"] = {
            "trigger": "inferential time-series claim",
            "parameters": {"sampling_structure": "serially_dependent_time_series"},
        }
    if capability == "analysis.time_series" and (
        claim_type == "seasonality" or seasonality_period
    ):
        metadata["seasonality_estimability"] = {
            "trigger": "explicit seasonality claim",
            "parameters": {"seasonality_period": seasonality_period or "annual"},
        }

    design_type = _causal_design_type(step)
    causal_claim_requested = claim_type in {"causal", "causal_effect", "causal_requested"}
    experiment_design_requested = capability == "analysis.experiment" and (
        causal_claim_requested
        or bool(design_type)
        or claim_type in {"planning", "detectability"}
    )
    if experiment_design_requested:
        _add_requirement_metadata(
            metadata,
            _EXPERIMENT_CORE_DESIGN_FACTS,
            trigger="core experiment design fact",
        )
    elif capability == "analysis.causal":
        _add_requirement_metadata(
            metadata,
            _CAUSAL_CORE_DESIGN_FACTS,
            trigger="core causal design fact",
        )
    if capability == "analysis.experiment" and design_type == "randomized_experiment":
        _add_requirement_metadata(
            metadata,
            _CAUSAL_DESIGN_DIAGNOSTICS["randomized_experiment"],
            trigger="randomized experiment design",
        )
        metadata.setdefault("confidence_interval", {
            "trigger": "randomized experiment effect uncertainty",
            "unmet_action": "block_claim",
        })

    if capability in {"analysis.experiment", "analysis.causal"} and causal_claim_requested:
        diagnostics = _CAUSAL_DESIGN_DIAGNOSTICS.get(design_type, ())
        _add_requirement_metadata(
            metadata,
            diagnostics,
            trigger=f"{design_type or 'unspecified'} causal identification design",
        )
        required_diagnostics = [
            name
            for name in diagnostics
            if name in {
                "balance_diagnostics", "discontinuity_diagnostics",
                "instrument_relevance", "overlap_diagnostics", "parallel_trends",
                "randomization_integrity",
            }
        ]
        non_identifying = (
            not design_type
            or design_type in {"pre_post", "observational_comparison"}
            or (
                design_type == "pre_post"
                and step.get("control_group_available") is not True
            )
        )
        if non_identifying:
            reason = (
                "A pre/post comparison without a control does not identify a causal effect."
                if design_type == "pre_post" and step.get("control_group_available") is not True
                else "The declared observational design does not by itself identify a causal effect."
            )
            metadata["identification_status"] = {
                "trigger": "causal claim requested without an identifying design",
                "unmet_action": "downgrade_claim",
                "claim_guard": "downgrade_claim",
                "parameters": {
                    "design_type": design_type or "unspecified",
                    "identified": False,
                    "allowed_claim_class": "association",
                    "reason": reason,
                },
                "reason": reason,
            }
            metadata["alternative_explanations"] = {
                "trigger": "non-identifying design requires plausible alternative explanations",
                "unmet_action": "disclose",
            }
        else:
            metadata["identification_status"] = {
                "trigger": f"{design_type} causal claim",
                "unmet_action": "block_claim",
                "parameters": {
                    "design_type": design_type,
                    "allowed_claim_class": "causal",
                    "required_diagnostics": required_diagnostics,
                },
            }

    analysis_phase = _name(step.get("analysis_phase") or step.get("decision_type"))
    planning_text = f"{_text(step.get('goal'))} {intent_text}".casefold()
    if capability == "analysis.experiment" and (
        analysis_phase in {"planning", "detectability", "sample_size_planning"}
        or claim_type in {"planning", "detectability"}
        or any(marker in planning_text for marker in ("minimum detectable effect", " mde", "power plan"))
    ):
        metadata["power_mde"] = {
            "trigger": "prospective experiment planning or detectability decision",
            "unmet_action": "block_claim",
            "parameters": {
                "allowed_purposes": ["prospective_planning", "detectability_decision"],
                "retrospective_power_proves_effect": False,
            },
        }

    outcome_count = _positive_int(step.get("outcome_count"))
    if capability == "analysis.experiment" and outcome_count is not None and outcome_count > 1:
        metadata["multiplicity_handling"] = {
            "trigger": "multiple experiment outcomes or contrasts",
            "unmet_action": "block_claim",
            "parameters": {
                "comparison_count": outcome_count,
                "exploratory_label_allowed": True,
            },
        }
    for name in _USER_DEFINITIONAL_REQUIREMENTS.intersection(metadata):
        metadata[name].setdefault("parameters", {})["input_source"] = "user_or_plan"
    return metadata


def _contract_for_step(
    step: dict[str, Any],
    dataset_contracts: Any,
) -> dict[str, Any]:
    if not isinstance(dataset_contracts, list):
        return {}
    from data_agent.agent.artifact_refs import hydrate_refs

    contracts = hydrate_refs([item for item in dataset_contracts if isinstance(item, dict)])
    raw_inputs = step.get("dataset_inputs")
    requested = {
        _text(item)
        for item in raw_inputs
        if _text(item)
    } if isinstance(raw_inputs, list) else set()
    if requested:
        for contract in contracts:
            if requested.intersection({
                _text(contract.get("dataset")),
                _text(contract.get("id")),
            }):
                return contract
    return contracts[0] if len(contracts) == 1 else {}


def _apply_profile_guards(
    metadata: dict[str, dict[str, Any]],
    *,
    step: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    profiles = contract.get("analysis_profiles")
    if not isinstance(profiles, dict):
        return
    comparison_profile = profiles.get("comparison")
    sample_meta = metadata.get("sample_adequacy")
    if isinstance(comparison_profile, dict) and sample_meta is not None:
        group_sizes = comparison_profile.get("group_sizes")
        if isinstance(group_sizes, dict) and group_sizes:
            sample_meta.setdefault("parameters", {})["observed_group_sizes"] = group_sizes

    if isinstance(comparison_profile, dict):
        group_sizes = comparison_profile.get("group_sizes")
        selected_group_column = _text(
            step.get("group_col")
            or step.get("group_column")
            or step.get("segment_col")
            or step.get("segment_column")
            or step.get("dimension")
        )
        if not selected_group_column:
            raw_dimensions = step.get("dimensions")
            if isinstance(raw_dimensions, str):
                selected_group_column = _text(raw_dimensions.split(",", 1)[0])
            elif isinstance(raw_dimensions, list) and len(raw_dimensions) == 1:
                selected_group_column = _text(raw_dimensions[0])
        if isinstance(group_sizes, dict) and selected_group_column in group_sizes:
            selected_profiles = [group_sizes[selected_group_column]]
        elif isinstance(group_sizes, dict) and len(group_sizes) == 1:
            selected_profiles = list(group_sizes.values())
        else:
            selected_profiles = []
        observed_counts = [
            _positive_int(item.get("group_count"))
            for item in selected_profiles
            if isinstance(item, dict)
        ]
        group_count = max((item for item in observed_counts if item), default=0)
        capability = _text(step.get("required_capability"))
        if capability == "analysis.dimension_decomposition":
            comparison_count = group_count
        elif capability in {"analysis.group_compare", "analysis.segment_compare"}:
            comparison_count = max(0, group_count - 1)
        else:
            comparison_count = 0
        if comparison_count > 1:
            metadata.setdefault("multiplicity_handling", {
                "trigger": (
                    "observed multi-segment decomposition"
                    if capability == "analysis.dimension_decomposition"
                    else "observed multiple baseline comparisons"
                ),
                "parameters": {
                    "comparison_count": comparison_count,
                    "exploratory_label_allowed": True,
                },
            })

    time_profile = profiles.get("time_series")
    time_profiles_by_column = profiles.get("time_series_by_column")
    selected_time_column = _text(
        step.get("date_column")
        or step.get("date_col")
        or step.get("time_column")
        or step.get("time_col")
    )
    if (
        selected_time_column
        and isinstance(time_profiles_by_column, dict)
        and isinstance(time_profiles_by_column.get(selected_time_column), dict)
    ):
        time_profile = time_profiles_by_column[selected_time_column]
    if not isinstance(time_profile, dict):
        return

    if "window_comparability" in metadata or _text(step.get("required_capability")) in {
        "analysis.period_compare",
        "analysis.time_series",
    }:
        frequency = _name(time_profile.get("frequency"))
        missing_count = _positive_int(time_profile.get("missing_interval_count")) or 0
        if frequency in {"irregular", "not_estimable"} or missing_count:
            metadata.setdefault("window_comparability", {})
            metadata["window_comparability"].update({
                "unmet_action": "block_claim",
                "assessment_status": "requires_adjustment",
                "claim_guard": "ordinary_window_assumptions_unsupported",
                "reason": (
                    "Ordinary period-window assumptions are unsupported because the time series "
                    f"is {frequency or 'unclassified'} with {missing_count} missing intervals."
                ),
                "parameters": {
                    "frequency": frequency or "unclassified",
                    "missing_interval_count": missing_count,
                },
            })

    seasonality_meta = metadata.get("seasonality_estimability")
    if seasonality_meta is None:
        return
    period = _name(seasonality_meta.get("parameters", {}).get("seasonality_period")) or "annual"
    seasonality = time_profile.get("seasonality")
    assessment = seasonality.get(period) if isinstance(seasonality, dict) else None
    if not isinstance(assessment, dict):
        return
    estimability = _name(assessment.get("status"))
    seasonality_meta["parameters"] = {
        "seasonality_period": period,
        "frequency": _name(time_profile.get("frequency")) or "unclassified",
        "period_observations": int(assessment.get("period_observations") or 0),
        "minimum_complete_cycles": int(assessment.get("minimum_complete_cycles") or 0),
        "complete_cycles": int(assessment.get("complete_cycles") or 0),
        "estimability": estimability or "not_estimable",
    }
    seasonality_meta["reason"] = _text(assessment.get("reason"))
    if estimability == "not_estimable":
        seasonality_meta.update({
            "unmet_action": "block_claim",
            "assessment_status": "not_estimable",
            "claim_guard": "block_claim",
        })
    elif estimability == "estimable_with_limits":
        seasonality_meta["unmet_action"] = "downgrade_claim"
        seasonality_meta["assessment_status"] = "estimable_with_limits"
        seasonality_meta["claim_guard"] = "downgrade_claim"
    else:
        seasonality_meta["assessment_status"] = estimability or "unknown"


def compile_analysis_requirements(
    *,
    plan: Any,
    route: Any,
    playbook: Any,
    dataset_contracts: Any,
    user_intent: Any,
    _allow_legacy_unknown: bool = False,
) -> list[dict[str, Any]]:
    plan_value = plan if isinstance(plan, dict) else {}
    provided = plan_value.get("analysis_requirements")
    provided_by_step_name: dict[str, dict[str, dict[str, Any]]] = {}
    if provided is not None:
        if not isinstance(provided, dict):
            raise ValueError("AnalysisPlan analysis_requirements must be grouped by step_id.")
        for raw_step_id, group in provided.items():
            step_id = _step_id_text(raw_step_id)
            if not step_id or not isinstance(group, list):
                raise ValueError("AnalysisPlan analysis_requirements must be grouped by step_id.")
            for requirement in group:
                _validate_requirement(requirement)
                if requirement["step_id"] != step_id:
                    raise ValueError("AnalysisRequirement step_id must match its plan group.")
                provided_by_step_name.setdefault(step_id, {})[requirement["name"]] = requirement
    method_plan = plan_value.get("method_plan")
    if not isinstance(method_plan, list):
        return []

    steps: list[tuple[str, dict[str, Any]]] = []
    for index, raw_step in enumerate(method_plan, 1):
        if not isinstance(raw_step, dict):
            continue
        step_id = _step_id_text(raw_step.get("step_id")) or f"step_{index}"
        steps.append((step_id, raw_step))
    if not steps:
        return []

    inputs_by_step: dict[str, dict[str, set[str]]] = {step_id: {} for step_id, _ in steps}
    metadata_by_step: dict[str, dict[str, dict[str, Any]]] = {
        step_id: {} for step_id, _ in steps
    }
    has_canonical_records = any(provided_by_step_name.values())
    for step_id, raw_step in steps:
        for name in provided_by_step_name.get(step_id, {}):
            inputs_by_step[step_id].setdefault(name, set()).add("plan.analysis_requirements")
        if not has_canonical_records:
            for name in _name_list(raw_step.get("evidence_requirements")):
                inputs_by_step[step_id].setdefault(name, set()).add(
                    "plan.method_plan.evidence_requirements"
                )
        capability = _text(raw_step.get("required_capability"))
        for name in _CAPABILITY_REQUIREMENT_INPUTS.get(capability, ()):
            inputs_by_step[step_id].setdefault(name, set()).add("plan.method_plan.required_capability")
        step_metadata = _step_requirement_metadata(raw_step, user_intent=user_intent)
        _apply_profile_guards(
            step_metadata,
            step=raw_step,
            contract=_contract_for_step(raw_step, dataset_contracts),
        )
        for name, metadata in step_metadata.items():
            inputs_by_step[step_id].setdefault(name, set()).add("deterministic_requirement_rule")
            metadata_by_step[step_id][name] = metadata

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
        step_id = _step_for_external_input(name, steps, inputs_by_step)
        inputs_by_step[step_id].setdefault(name, set()).add(origin)

    compiled: list[dict[str, Any]] = []
    for step_id, _ in steps:
        step_id_component = _step_id_component(step_id)
        names = sorted(inputs_by_step[step_id])
        for name in names:
            definition = _REQUIREMENT_DEFINITIONS.get(name)
            compatibility_definition = definition is None
            if definition is None:
                if not _allow_legacy_unknown:
                    raise ValueError(f"Unknown live AnalysisRequirement input: {name}")
                definition = {
                    "category": "output",
                    "required_evidence_fields": [name],
                    "assumption_checks": [],
                    "unmet_action": "disclose",
                }
            provided_requirement = provided_by_step_name.get(step_id, {}).get(name, {})
            metadata = metadata_by_step[step_id].get(name, {})
            status = metadata.get("status", provided_requirement.get("status", "pending"))
            reason = metadata.get("reason")
            if reason is None:
                reason = (
                    "Compatibility requirement compiled from an unregistered saved input."
                    if compatibility_definition
                    else str(provided_requirement.get("reason") or "")
                )
            requirement = {
                "contract_version": ANALYSIS_REQUIREMENT_CONTRACT_VERSION,
                "id": f"req_{step_id_component}_{name}",
                "step_id": step_id,
                "category": definition["category"],
                "name": name,
                "necessity": "required",
                "trigger": str(metadata.get("trigger") or f"explicit compiler input: {name}"),
                "status": status,
                "required_evidence_fields": list(definition["required_evidence_fields"]),
                "assumption_checks": list(definition["assumption_checks"]),
                "unmet_action": metadata.get("unmet_action", definition["unmet_action"]),
                "evidence_ids": list(provided_requirement.get("evidence_ids") or []),
                "reason": str(reason),
            }
            parameters = metadata.get("parameters", provided_requirement.get("parameters"))
            if isinstance(parameters, dict):
                requirement["parameters"] = dict(parameters)
            for field_name in ("assessment_status", "claim_guard"):
                field_value = metadata.get(field_name, provided_requirement.get(field_name))
                if field_value:
                    requirement[field_name] = str(field_value)
            compiled.append(requirement)
    return compiled
