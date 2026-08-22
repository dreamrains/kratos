from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from data_agent.v2.stability import (
    SEMANTIC_STABILITY_CONTRACT_VERSION,
    compare_semantic_stability,
)


FIXTURE_PATH = Path("tests/fixtures/v2_semantic_stability_contract.json")


@pytest.fixture
def stability_cases() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _changed(case: dict, path: tuple[str, ...], value):
    changed = copy.deepcopy(case)
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return changed


def test_low_and_medium_advisory_risk_are_not_a_planning_failure_when_all_semantics_match(
    stability_cases,
):
    comparison = compare_semantic_stability(
        stability_cases["baseline"], stability_cases["equivalent_low_risk"]
    )

    assert comparison.contract_version == SEMANTIC_STABILITY_CONTRACT_VERSION
    assert comparison.provider_response_repeatable is False
    assert comparison.planning_semantic_stable is True
    assert comparison.recommendation_safety_stable is True
    assert comparison.outcome_stable is True
    assert comparison.passed is True
    assert comparison.material_differences == ()


@pytest.mark.parametrize(
    ("path", "value", "expected_difference"),
    [
        (("plan", "parameters", "action_risk"), "high", "action_risk"),
        (("plan", "parameters", "reversible"), False, "reversible"),
        (("plan", "parameters", "recommendation_intent"), "act", "recommendation_intent"),
        (("plan", "analysis_kind"), "time_trend", "analysis_kind"),
        (("plan", "parameters", "metric"), "orders", "metric"),
        (("plan", "parameters", "analysis_unit"), "channel", "analysis_unit"),
        (("plan", "parameters", "aggregation"), "mean", "aggregation"),
        (("plan", "parameters", "frequency"), "weekly", "frequency"),
        (("plan", "data_scope", "time_range"), "2025-12-01/2026-02-11", "data_scope"),
    ],
)
def test_material_planning_or_safety_drift_fails_closed(
    stability_cases, path, value, expected_difference
):
    observed = _changed(stability_cases["baseline"], path, value)

    comparison = compare_semantic_stability(stability_cases["baseline"], observed)

    assert comparison.passed is False
    assert any(expected_difference in item for item in comparison.material_differences)


def test_ready_to_needs_input_fails_closed_when_the_complete_semantic_context_is_unchanged(
    stability_cases,
):
    observed = copy.deepcopy(stability_cases["baseline"])
    observed["plan"] = {
        "status": "needs_input",
        "pending_analysis_kind": "multi_finding_synthesis",
        "missing_prerequisites": ["analysis_unit_semantics"],
        "semantic_context": copy.deepcopy(
            stability_cases["baseline"]["plan"]["semantic_context"]
        ),
        "data_scope": copy.deepcopy(stability_cases["baseline"]["plan"]["data_scope"]),
    }

    comparison = compare_semantic_stability(stability_cases["baseline"], observed)

    assert comparison.passed is False
    assert any("status" in item for item in comparison.material_differences)


def test_recommendation_safety_mode_drift_fails_even_when_the_plan_bindings_match(
    stability_cases,
):
    observed = _changed(
        stability_cases["equivalent_low_risk"],
        ("outcome", "recommendation_safety_mode"),
        "operational_action",
    )

    comparison = compare_semantic_stability(stability_cases["baseline"], observed)

    assert comparison.passed is False
    assert any(
        "recommendation_safety_mode" in item
        for item in comparison.material_differences
    )


@pytest.mark.parametrize(
    ("outcome_key", "expected_stable"),
    [
        ("outcome_within_tolerance", True),
        ("outcome_outside_tolerance", False),
    ],
)
def test_outcome_numeric_tolerance_is_versioned_and_does_not_hide_material_drift(
    stability_cases, outcome_key, expected_stable
):
    observed = copy.deepcopy(stability_cases["baseline"])
    observed["outcome"]["core_metrics"].update(stability_cases[outcome_key])

    comparison = compare_semantic_stability(stability_cases["baseline"], observed)

    assert comparison.outcome_stable is expected_stable
    assert comparison.passed is expected_stable
    if not expected_stable:
        assert any("core_metrics" in item for item in comparison.material_differences)


@pytest.mark.parametrize(
    ("path", "value", "expected_difference"),
    [
        (("outcome", "directions", "daily_trend"), "negative", "directions"),
        (("outcome", "claim_class"), "causal", "claim_class"),
        (("outcome", "primary_limitations"), ["observational"], "primary_limitations"),
    ],
)
def test_outcome_direction_claim_or_primary_limitations_never_downgrade_to_diagnostic_noise(
    stability_cases, path, value, expected_difference
):
    observed = _changed(stability_cases["baseline"], path, value)

    comparison = compare_semantic_stability(stability_cases["baseline"], observed)

    assert comparison.passed is False
    assert any(expected_difference in item for item in comparison.material_differences)
