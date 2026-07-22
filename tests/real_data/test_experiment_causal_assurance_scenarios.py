"""Focused realistic scenarios for experiment and causal claim boundaries."""

from data_agent.agent.analysis_requirements import compile_analysis_requirements
from data_agent.agent.verification import verify_analysis_claims


def _compile(step):
    return compile_analysis_requirements(
        plan={
            "id": "plan_campaign",
            "goal": "evaluate campaign impact",
            "method_plan": [{"step_id": "step_effect", **step}],
        },
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="did the campaign cause the revenue change",
    )


def test_before_after_campaign_without_control_is_association_only():
    requirements = _compile({
        "required_capability": "analysis.causal",
        "claim_type": "causal",
        "design_type": "pre_post",
        "control_group_available": False,
    })
    identification = next(item for item in requirements if item["name"] == "identification_status")

    assert identification["parameters"]["allowed_claim_class"] == "association"
    assert identification["claim_guard"] == "downgrade_claim"


def test_randomized_campaign_keeps_attrition_uncertainty_and_multiplicity_visible():
    names = {
        item["name"]
        for item in _compile({
            "required_capability": "analysis.experiment",
            "claim_type": "causal",
            "design_type": "randomized_experiment",
            "outcome_count": 4,
        })
    }

    assert {"attrition", "confidence_interval", "multiplicity_handling"} <= names


def test_observational_campaign_result_remains_useful_as_association():
    evidence = {
        "id": "ev_campaign",
        "claim": "Campaign exposure was associated with 8% higher revenue.",
        "dataset": "orders",
        "method": "adjusted observational comparison",
        "sample_size": 8400,
        "time_scope": "2026-04",
        "calculation_method": "covariate-adjusted comparison",
        "method_detail": "adjusted for baseline revenue and channel",
        "limitations": ["self-selection and unmeasured confounding remain possible"],
        "confidence": "medium",
        "identification_status": {
            "status": "not_identified",
            "design_type": "observational_comparison",
            "allowed_claim_class": "association",
        },
        "alternative_explanations": ["self-selection", "concurrent channel mix changes"],
    }
    report = verify_analysis_claims(
        claims=[{"text": evidence["claim"], "evidence_id": evidence["id"]}],
        evidence_records=[evidence],
        route_proposals=[],
        cleaning_logs=[],
    )

    assert report["overall_status"] == "pass"

