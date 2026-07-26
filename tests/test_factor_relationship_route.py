"""Factor-relationship route separation and claim-class tests (Task 7, Step 1).

These tests pin down the routing contract for "哪些因素显著影响目标值" style
questions: they must select the dedicated ``factor_relationship`` playbook
(not the period ``driver_decomposition`` path) and produce a six-step plan
whose claim class is bounded to ``inferential_associations`` — no causal
upgrade, no shallow data-understanding detour.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_agent.agent.intent import classify_intent
from data_agent.agent.method_playbooks import build_plan, select_playbooks


def _no_llm_playbook(*args, **kwargs):
    """Mock that simulates LLM unavailability for deterministic keyword routing."""
    return None


@pytest.mark.parametrize("text", [
    "哪些因素显著影响目标值？",
    "哪些变量与收入相关？",
    "find factors associated with conversion",
])
@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_factor_questions_select_factor_relationship_not_period_driver(text):
    intent = classify_intent(text, data_loaded=True)
    selection = select_playbooks(text, intent=intent)
    assert selection.primary_id == "factor_relationship"
    assert selection.primary_id != "driver_decomposition"


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_significance_plan_contains_required_depth_and_no_causal_upgrade():
    plan = build_plan("哪些因素显著影响目标值", dataset="factors")
    codes = [step["analysis_code"] for step in plan["method_plan"]]
    assert codes == [
        "grain_and_missingness_checked",
        "univariate_relationship_checked",
        "multivariable_method_attempted",
        "stability_and_dependence_checked",
        "effect_or_contribution_estimated",
        "limitations_prepared",
    ]
    assert plan["maximum_claim_class"] == "inferential_associations"


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_driver_decline_wording_still_routes_to_driver_decomposition():
    """Regression guard: explicit period-change wording must not migrate to
    factor_relationship just because it asks about causes."""
    text = "why did revenue decline"
    intent = classify_intent(text, data_loaded=True)
    selection = select_playbooks(text, intent=intent)
    assert selection.primary_id == "driver_decomposition"


@patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm_playbook)
def test_predictive_factor_wording_caps_claim_class_at_predictive_importance():
    """Predictive wording on a factor question must not invent significance."""
    plan = build_plan("预测哪些因素影响目标值", dataset="factors")
    assert plan["maximum_claim_class"] == "predictive_importance"
