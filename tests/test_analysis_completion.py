"""Requirement-based bounded completion evaluator tests.

Covers the five terminal states and the execution/publication separation
invariants required by Task 8 of the analysis-reliability plan.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_agent.agent.execution_control import (  # noqa: E402
    CompletionDecision,
    ToolExecutionBudget,
    TurnExecutionState,
    evaluate_analysis_completion,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def turn_state():
    return TurnExecutionState(ToolExecutionBudget(profile="analysis", max_tool_calls=20))


def _requirement(
    req_id: str,
    step_id: str,
    name: str,
    *,
    category: str = "measurement",
    unmet_action: str = "block_claim",
    required_evidence_fields: list[str] | None = None,
    necessity: str = "required",
) -> dict:
    return {
        "contract_version": "analysis_requirement.v1",
        "id": req_id,
        "step_id": step_id,
        "name": name,
        "trigger": f"test requirement: {name}",
        "category": category,
        "necessity": necessity,
        "status": "pending",
        "required_evidence_fields": required_evidence_fields or [name],
        "assumption_checks": [],
        "unmet_action": unmet_action,
        "evidence_ids": [],
        "reason": "",
    }


def _ref(
    *,
    plan_id: str,
    step_id: str,
    tool_call_id: str,
    tool_name: str,
    capability_id: str,
    evidence_fields: list[str],
    requirement_ids: list[str],
    success: bool = True,
    binding_error_type: str = "",
    claim_key: str = "claim",
) -> dict:
    return {
        "plan_id": plan_id,
        "step_id": step_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "success": success,
        "capability_id": capability_id,
        "evidence_fields": list(evidence_fields),
        "claim_key": claim_key,
        "requirement_ids": list(requirement_ids),
        "binding_error_type": binding_error_type,
    }


def _outcome(tool_call_id: str, tool_name: str, *, success: bool, error_category: str = "") -> dict:
    return {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "success": success,
        "error_category": error_category,
    }


@pytest.fixture
def all_satisfied(turn_state):
    return {
        "plan": {"id": "plan_simple", "maximum_claim_class": "inferential_associations"},
        "requirements": [
            _requirement(
                "req_revenue_change",
                "step_compare",
                "metric_delta",
                category="measurement",
                unmet_action="block_claim",
            ),
        ],
        "computation_refs": [
            _ref(
                plan_id="plan_simple",
                step_id="step_compare",
                tool_call_id="tc_compare",
                tool_name="compare_periods",
                capability_id="analysis.period_compare",
                evidence_fields=["metric_delta"],
                requirement_ids=["req_revenue_change"],
                claim_key="revenue_change",
            )
        ],
        "evidence_records": [
            {
                "id": "ev_compare",
                "step_id": "step_compare",
                "requirement_ids": ["req_revenue_change"],
                "metric_delta": {"value": 0.12, "unit": "ratio"},
            }
        ],
        "tool_outcomes": [
            _outcome("tc_compare", "compare_periods", success=True)
        ],
        "turn_state": turn_state,
        "budget_exhausted": False,
    }


@pytest.fixture
def inferential_unattainable_but_exploratory_success(turn_state):
    # Recovery budget for the inferential requirement is already exhausted.
    turn_state.record_corrected_retry("req_univariate_association")
    turn_state.record_fallback("req_univariate_association")
    return {
        "plan": {
            "id": "plan_factor",
            "maximum_claim_class": "inferential_associations",
        },
        "requirements": [
            _requirement(
                "req_univariate_association",
                "step_univariate",
                "univariate_association",
                category="inference",
                unmet_action="block_claim",
            ),
            _requirement(
                "req_descriptive_distribution",
                "step_profile",
                "distribution",
                category="measurement",
                unmet_action="downgrade_claim",
            ),
        ],
        "computation_refs": [
            _ref(
                plan_id="plan_factor",
                step_id="step_profile",
                tool_call_id="tc_profile",
                tool_name="describe_dataset",
                capability_id="data.profile",
                evidence_fields=["distribution"],
                requirement_ids=["req_descriptive_distribution"],
                claim_key="profile_distribution",
            )
        ],
        "evidence_records": [
            {
                "id": "ev_profile",
                "step_id": "step_profile",
                "requirement_ids": ["req_descriptive_distribution"],
                "distribution": {"status": "ready"},
            }
        ],
        "tool_outcomes": [
            _outcome("tc_profile", "describe_dataset", success=True)
        ],
        "turn_state": turn_state,
        "budget_exhausted": False,
    }


@pytest.fixture
def missing_required_columns(turn_state):
    return {
        "plan": {"id": "plan_blocked_data"},
        "requirements": [
            _requirement(
                "req_compare_metric",
                "step_compare",
                "metric_delta",
                category="measurement",
                unmet_action="block_claim",
            ),
        ],
        "computation_refs": [
            _ref(
                plan_id="plan_blocked_data",
                step_id="step_compare",
                tool_call_id="tc_compare",
                tool_name="compare_periods",
                capability_id="analysis.period_compare",
                evidence_fields=["metric_delta"],
                requirement_ids=["req_compare_metric"],
                success=False,
                binding_error_type="missing_column_or_data",
                claim_key="revenue_change",
            )
        ],
        "evidence_records": [],
        "tool_outcomes": [
            _outcome(
                "tc_compare",
                "compare_periods",
                success=False,
                error_category="missing_column_or_data",
            )
        ],
        "turn_state": turn_state,
        "budget_exhausted": False,
    }


@pytest.fixture
def critical_tool_and_fallback_failed(turn_state):
    # Both retry and fallback exhausted for the failed requirement.
    turn_state.record_corrected_retry("req_inferential_method")
    turn_state.record_fallback("req_inferential_method")
    return {
        "plan": {"id": "plan_tool_fail"},
        "requirements": [
            _requirement(
                "req_inferential_method",
                "step_method",
                "multivariable_adjustment",
                category="inference",
                unmet_action="block_claim",
            ),
        ],
        "computation_refs": [
            _ref(
                plan_id="plan_tool_fail",
                step_id="step_method",
                tool_call_id="tc_method",
                tool_name="regression_analysis",
                capability_id="analysis.factor_relationship",
                evidence_fields=["multivariable_adjustment"],
                requirement_ids=["req_inferential_method"],
                success=False,
                binding_error_type="tool_execution_failed",
                claim_key="method_fit",
            )
        ],
        "evidence_records": [],
        "tool_outcomes": [
            _outcome(
                "tc_method",
                "regression_analysis",
                success=False,
                error_category="tool_error",
            )
        ],
        "turn_state": turn_state,
        "budget_exhausted": False,
    }


@pytest.fixture
def execution_budget_exhausted(turn_state):
    return {
        "plan": {"id": "plan_budget", "maximum_claim_class": "inferential_associations"},
        "requirements": [
            _requirement(
                "req_revenue_change",
                "step_compare",
                "metric_delta",
                category="measurement",
                unmet_action="block_claim",
            ),
            _requirement(
                "req_limitations",
                "step_compare",
                "limitations",
                category="limitation",
                unmet_action="disclose",
            ),
        ],
        "computation_refs": [
            _ref(
                plan_id="plan_budget",
                step_id="step_compare",
                tool_call_id="tc_compare",
                tool_name="compare_periods",
                capability_id="analysis.period_compare",
                evidence_fields=["metric_delta"],
                requirement_ids=["req_revenue_change"],
                claim_key="revenue_change",
            )
        ],
        "evidence_records": [
            {
                "id": "ev_compare",
                "step_id": "step_compare",
                "requirement_ids": ["req_revenue_change"],
                "metric_delta": {"value": 0.12},
            }
        ],
        "tool_outcomes": [
            _outcome("tc_compare", "compare_periods", success=True)
        ],
        "turn_state": turn_state,
        "budget_exhausted": True,
    }


@pytest.fixture
def completed_computation_case(turn_state):
    """Execution succeeded for every required computation.

    Used by the projection-separation test with ``evidence_records=[]`` to
    prove a missing projection never triggers recomputation. The
    ``evidence_records`` key is intentionally omitted so the test can pass
    its own value without colliding.
    """

    return {
        "plan": {"id": "plan_complete", "maximum_claim_class": "inferential_associations"},
        "requirements": [
            _requirement(
                "req_metric_delta",
                "step_compare",
                "metric_delta",
                category="measurement",
                unmet_action="block_claim",
            ),
            _requirement(
                "req_limitations",
                "step_compare",
                "limitations",
                category="limitation",
                unmet_action="disclose",
            ),
        ],
        "computation_refs": [
            _ref(
                plan_id="plan_complete",
                step_id="step_compare",
                tool_call_id="tc_compare",
                tool_name="compare_periods",
                capability_id="analysis.period_compare",
                evidence_fields=["metric_delta"],
                requirement_ids=["req_metric_delta"],
                claim_key="revenue_change",
            )
        ],
        "tool_outcomes": [
            _outcome("tc_compare", "compare_periods", success=True)
        ],
        "turn_state": turn_state,
        "budget_exhausted": False,
    }


@pytest.fixture
def factor_plan():
    return {
        "id": "plan_factor_six_step",
        "goal": "identify factors associated with the target metric",
        "maximum_claim_class": "inferential_associations",
        "method_plan": [
            {
                "step_id": "step_grain_and_missingness_checked",
                "required_capability": "data.profile",
            },
            {
                "step_id": "step_univariate_relationship_checked",
                "required_capability": "analysis.correlation",
            },
            {
                "step_id": "step_multivariable_method_attempted",
                "required_capability": "analysis.factor_relationship",
            },
            {
                "step_id": "step_stability_and_dependence_checked",
                "required_capability": "analysis.factor_relationship",
            },
            {
                "step_id": "step_effect_or_contribution_estimated",
                "required_capability": "analysis.regression",
            },
            {
                "step_id": "step_limitations_prepared",
                "required_capability": "artifact.evidence_record",
            },
        ],
    }


def successful_profile_ref() -> dict:
    return _ref(
        plan_id="plan_factor_six_step",
        step_id="step_grain_and_missingness_checked",
        tool_call_id="tc_profile",
        tool_name="profile_data",
        capability_id="data.profile",
        evidence_fields=["grain_definition", "missingness_assessment"],
        requirement_ids=["req_grain_definition", "req_missingness_assessment"],
        claim_key="profile",
    )


def successful_tool_outcome(tool_name: str) -> dict:
    return _outcome("tc_profile", tool_name, success=True)


@pytest.fixture
def factor_completion_case():
    def _factory(
        *,
        plan: dict,
        computation_refs: list,
        evidence_records: list,
        tool_outcomes: list,
        budget_exhausted: bool,
    ) -> dict:
        return {
            "plan": plan,
            "requirements": [
                _requirement(
                    "req_grain_definition",
                    "step_grain_and_missingness_checked",
                    "grain_definition",
                    category="data",
                    unmet_action="block_analysis",
                ),
                _requirement(
                    "req_missingness_assessment",
                    "step_grain_and_missingness_checked",
                    "missingness_assessment",
                    category="data",
                    unmet_action="block_analysis",
                ),
                _requirement(
                    "req_univariate_association",
                    "step_univariate_relationship_checked",
                    "univariate_association",
                    category="inference",
                    unmet_action="block_claim",
                ),
                _requirement(
                    "req_multivariable_adjustment",
                    "step_multivariable_method_attempted",
                    "multivariable_adjustment",
                    category="inference",
                    unmet_action="block_claim",
                ),
                _requirement(
                    "req_multiplicity_control",
                    "step_multivariable_method_attempted",
                    "multiplicity_control",
                    category="inference",
                    unmet_action="block_claim",
                ),
                _requirement(
                    "req_collinearity_assessment",
                    "step_multivariable_method_attempted",
                    "collinearity_assessment",
                    category="assumption",
                    unmet_action="downgrade_claim",
                ),
                _requirement(
                    "req_stability_or_validation",
                    "step_stability_and_dependence_checked",
                    "stability_or_validation",
                    category="assumption",
                    unmet_action="downgrade_claim",
                ),
                _requirement(
                    "req_time_dependence_assessment",
                    "step_stability_and_dependence_checked",
                    "time_dependence_assessment",
                    category="assumption",
                    unmet_action="downgrade_claim",
                ),
                _requirement(
                    "req_effect_size_or_predictive_contribution",
                    "step_effect_or_contribution_estimated",
                    "effect_size_or_predictive_contribution",
                    category="inference",
                    unmet_action="block_claim",
                ),
                _requirement(
                    "req_limitations_and_alternatives",
                    "step_limitations_prepared",
                    "limitations_and_alternatives",
                    category="limitation",
                    unmet_action="disclose",
                ),
            ],
            "computation_refs": computation_refs,
            "evidence_records": evidence_records,
            "tool_outcomes": tool_outcomes,
            "turn_state": TurnExecutionState(
                ToolExecutionBudget(profile="analysis", max_tool_calls=20)
            ),
            "budget_exhausted": budget_exhausted,
        }

    return _factory


# ---------------------------------------------------------------------------
# Step 1: five terminal-state parametrized test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        ("all_satisfied", "complete"),
        ("inferential_unattainable_but_exploratory_success", "complete_with_limits"),
        ("missing_required_columns", "blocked_by_data"),
        ("critical_tool_and_fallback_failed", "blocked_by_tool"),
        ("execution_budget_exhausted", "budget_limited"),
    ],
)
def test_completion_returns_one_terminal_state(fixture_name, expected, request):
    decision = evaluate_analysis_completion(**request.getfixturevalue(fixture_name))
    assert decision.status == expected
    assert decision.is_terminal is True


# ---------------------------------------------------------------------------
# Step 2: convergence + execution/publication separation
# ---------------------------------------------------------------------------


def test_missing_projection_never_requests_another_tool(completed_computation_case):
    decision = evaluate_analysis_completion(
        **completed_computation_case,
        evidence_records=[],
    )
    assert decision.status == "complete_with_limits"
    assert decision.allow_analysis_continuation is False


def test_quality_guard_allows_only_one_recoverable_continuation(turn_state):
    assert turn_state.consume_quality_continuation(reason="missing_multivariable_method") is True
    assert turn_state.consume_quality_continuation(reason="missing_stability_check") is False


def test_one_substantive_tool_does_not_complete_six_step_factor_plan(factor_plan, factor_completion_case):
    case = factor_completion_case(
        plan=factor_plan,
        computation_refs=[successful_profile_ref()],
        evidence_records=[],
        tool_outcomes=[successful_tool_outcome("profile_data")],
        budget_exhausted=False,
    )
    decision = evaluate_analysis_completion(**case)
    assert decision.status != "complete"
    assert "req_multivariable_adjustment" in decision.unmet_requirement_ids


def test_completion_decision_is_frozen():
    decision = CompletionDecision(
        status="complete",
        is_terminal=True,
        supported_claim_class="exploratory_association",
        satisfied_requirement_ids=("req_a",),
        unmet_requirement_ids=(),
        recoverable_requirement_ids=(),
        allow_analysis_continuation=False,
        reason_code="requirements_satisfied",
        diagnostics=(),
    )
    # Frozen dataclass: mutations must raise
    with pytest.raises(Exception):
        decision.status = "blocked_by_tool"  # type: ignore[misc]


def test_factor_plan_recovers_for_one_continuation(factor_plan, factor_completion_case):
    case = factor_completion_case(
        plan=factor_plan,
        computation_refs=[successful_profile_ref()],
        evidence_records=[],
        tool_outcomes=[successful_tool_outcome("profile_data")],
        budget_exhausted=False,
    )
    decision = evaluate_analysis_completion(**case)
    # The multivariable step has neither a ref nor exhausted retries, so it is recoverable.
    assert "req_multivariable_adjustment" in decision.recoverable_requirement_ids
    assert decision.allow_analysis_continuation is True


def test_budget_exhausted_does_not_strengthen_claim(execution_budget_exhausted):
    decision = evaluate_analysis_completion(**execution_budget_exhausted)
    assert decision.status == "budget_limited"
    assert decision.allow_analysis_continuation is False
    assert decision.supported_claim_class != "causal_effect"
