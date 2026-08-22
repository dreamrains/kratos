"""Versioned, provider-neutral material stability contract for V2 release gates.

The contract deliberately separates an exact Provider response observation from
the execution, recommendation-safety, and published-outcome gates.  Raw output
repeatability is useful diagnostics, but it is not by itself a release blocker.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping


SEMANTIC_STABILITY_CONTRACT_VERSION = "v2_semantic_stability.v1"

# These are contract values, not post-hoc allowances for one Provider response.
CORE_METRIC_ABSOLUTE_TOLERANCE = 0.05
CORE_METRIC_RELATIVE_TOLERANCE = 0.01

_SAFETY_PARAMETER_FIELDS = frozenset(
    {"recommendation_intent", "action_risk", "reversible"}
)
_ADVISORY_RISKS = frozenset({"low", "medium"})


@dataclass(frozen=True, slots=True)
class SemanticStabilityComparison:
    contract_version: str
    provider_response_repeatable: bool
    planning_semantic_stable: bool
    recommendation_safety_stable: bool
    outcome_stable: bool
    material_differences: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            self.planning_semantic_stable
            and self.recommendation_safety_stable
            and self.outcome_stable
        )


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _object(value: Any, label: str, differences: list[str]) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    differences.append(f"invalid:{label}")
    return {}


def _text(value: Any, label: str, differences: list[str]) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        differences.append(f"invalid:{label}")
    return normalized


def _planning_identity(candidate: Mapping[str, Any], differences: list[str]) -> dict[str, Any]:
    plan = _object(candidate.get("plan"), "plan", differences)
    parameters = _object(plan.get("parameters"), "plan.parameters", differences)
    status = _text(plan.get("status"), "plan.status", differences)
    analysis_kind = _text(plan.get("analysis_kind"), "plan.analysis_kind", differences)
    semantic_context = _object(plan.get("semantic_context"), "plan.semantic_context", differences)
    data_scope = _object(plan.get("data_scope"), "plan.data_scope", differences)
    execution_parameters = {
        str(key): value
        for key, value in parameters.items()
        if str(key) not in _SAFETY_PARAMETER_FIELDS
    }
    return {
        "status": status,
        "analysis_kind": analysis_kind,
        "execution_parameters": execution_parameters,
        "semantic_context": dict(semantic_context),
        "data_scope": dict(data_scope),
    }


def _recommendation_safety_identity(
    candidate: Mapping[str, Any], differences: list[str]
) -> dict[str, str]:
    plan = _object(candidate.get("plan"), "plan", differences)
    parameters = _object(plan.get("parameters"), "plan.parameters", differences)
    outcome = _object(candidate.get("outcome"), "outcome", differences)
    intent = _text(parameters.get("recommendation_intent"), "recommendation_intent", differences)
    risk = _text(parameters.get("action_risk"), "action_risk", differences)
    reversible = parameters.get("reversible")
    if not isinstance(reversible, bool):
        differences.append("invalid:reversible")
    risk_class = "high" if risk == "high" else "advisory" if risk in _ADVISORY_RISKS else "invalid"
    if risk_class == "invalid":
        differences.append("invalid:action_risk")
    return {
        "recommendation_intent": intent,
        "action_risk_class": risk_class,
        "reversible": "reversible" if reversible is True else "irreversible",
        "recommendation_safety_mode": _text(
            outcome.get("recommendation_safety_mode"),
            "outcome.recommendation_safety_mode",
            differences,
        ),
    }


def _outcome_identity(candidate: Mapping[str, Any], differences: list[str]) -> dict[str, Any]:
    outcome = _object(candidate.get("outcome"), "outcome", differences)
    metrics = _object(outcome.get("core_metrics"), "outcome.core_metrics", differences)
    directions = _object(outcome.get("directions"), "outcome.directions", differences)
    intervals = _object(outcome.get("intervals"), "outcome.intervals", differences)
    limitations = outcome.get("primary_limitations")
    if not isinstance(limitations, list) or not all(
        isinstance(value, str) and value.strip() for value in limitations
    ):
        differences.append("invalid:outcome.primary_limitations")
        limitations = []
    normalized_metrics: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            differences.append(f"invalid:outcome.core_metrics.{key}")
        else:
            normalized_metrics[str(key)] = float(value)
    return {
        "core_metrics": normalized_metrics,
        "directions": dict(directions),
        "intervals": dict(intervals),
        "claim_class": _text(outcome.get("claim_class"), "outcome.claim_class", differences),
        "primary_limitations": tuple(sorted(set(str(value).strip() for value in limitations))),
    }


def _changed_fields(
    baseline: Mapping[str, Any], observed: Mapping[str, Any], prefix: str
) -> list[str]:
    differences: list[str] = []
    for key in sorted(set(baseline) | set(observed)):
        path = f"{prefix}.{key}"
        before = baseline.get(key)
        after = observed.get(key)
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            differences.extend(_changed_fields(before, after, path))
        elif before != after:
            differences.append(path)
    return differences


def _metrics_within_tolerance(
    baseline: Mapping[str, float], observed: Mapping[str, float]
) -> bool:
    if set(baseline) != set(observed):
        return False
    return all(
        math.isclose(
            baseline[key],
            observed[key],
            rel_tol=CORE_METRIC_RELATIVE_TOLERANCE,
            abs_tol=CORE_METRIC_ABSOLUTE_TOLERANCE,
        )
        for key in baseline
    )


def compare_semantic_stability(
    baseline: Mapping[str, Any], observed: Mapping[str, Any]
) -> SemanticStabilityComparison:
    """Compare two normalized plans and deterministic outcomes fail-closed.

    Inputs are deliberately plain mappings so historical evidence can be replayed
    without a Provider client.  Invalid or incomplete inputs are material failures.
    """

    baseline_value = _object(baseline, "baseline", [])
    observed_value = _object(observed, "observed", [])
    provider_response_repeatable = _canonical(baseline_value.get("plan")) == _canonical(
        observed_value.get("plan")
    )

    validation_differences: list[str] = []
    baseline_planning = _planning_identity(baseline_value, validation_differences)
    observed_planning = _planning_identity(observed_value, validation_differences)
    baseline_safety = _recommendation_safety_identity(baseline_value, validation_differences)
    observed_safety = _recommendation_safety_identity(observed_value, validation_differences)
    baseline_outcome = _outcome_identity(baseline_value, validation_differences)
    observed_outcome = _outcome_identity(observed_value, validation_differences)

    planning_differences = _changed_fields(
        baseline_planning, observed_planning, "planning"
    )
    safety_differences = _changed_fields(
        baseline_safety, observed_safety, "recommendation"
    )
    outcome_differences = _changed_fields(
        {
            **baseline_outcome,
            "core_metrics": "within_tolerance",
        },
        {
            **observed_outcome,
            "core_metrics": (
                "within_tolerance"
                if _metrics_within_tolerance(
                    baseline_outcome["core_metrics"], observed_outcome["core_metrics"]
                )
                else "outside_tolerance"
            ),
        },
        "outcome",
    )

    material = tuple(
        dict.fromkeys(validation_differences + planning_differences + safety_differences + outcome_differences)
    )
    return SemanticStabilityComparison(
        contract_version=SEMANTIC_STABILITY_CONTRACT_VERSION,
        provider_response_repeatable=provider_response_repeatable,
        planning_semantic_stable=not validation_differences and not planning_differences,
        recommendation_safety_stable=not validation_differences and not safety_differences,
        outcome_stable=not validation_differences and not outcome_differences,
        material_differences=material,
    )
