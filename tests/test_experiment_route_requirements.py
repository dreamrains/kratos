from types import SimpleNamespace

import pytest

from data_agent.agent.analysis_entry import decide_analysis_entry
from data_agent.agent.analysis_requirements import (
    compile_analysis_requirements,
    evaluate_requirement_satisfaction,
)
from data_agent.agent.question_need_detector import (
    computable_route_evidence,
    detect_question_need,
)


def _compile(step):
    return compile_analysis_requirements(
        plan={
            "id": "plan_effect",
            "goal": "evaluate intervention impact",
            "method_plan": [{
                "step_id": "step_effect",
                "goal": "estimate the intervention effect",
                "node_type": "analysis",
                "evidence_requirements": [],
                **step,
            }],
        },
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="evaluate intervention impact",
    )


def _names(requirements):
    return {item["name"] for item in requirements}


def _intent():
    return SimpleNamespace(
        intent_type="directed_analysis",
        clarity="clear",
        recommended_action="execute_analysis",
    )


def _state(plan, *, routes=None):
    return SimpleNamespace(
        analysis_plan=plan,
        dataset_contracts=[],
        route_proposals=routes or [],
        cleaning_logs=[],
        pending_confirmations=[],
        active_scope={},
    )


def test_randomized_causal_experiment_compiles_design_and_publication_guards():
    requirements = _compile({
        "required_capability": "analysis.experiment",
        "claim_type": "causal",
        "design_type": "randomized_experiment",
        "outcome_count": 3,
    })
    by_name = {item["name"]: item for item in requirements}

    assert {
        "assignment_unit",
        "treatment_arms",
        "exposure_definition",
        "outcome_definition",
        "per_arm_sample_size",
        "randomization_integrity",
        "balance_diagnostics",
        "attrition",
        "estimand",
        "confidence_interval",
        "multiplicity_handling",
        "identification_status",
    } <= set(by_name)
    assert by_name["assignment_unit"]["unmet_action"] == "block_claim"
    assert by_name["identification_status"]["parameters"] == {
        "design_type": "randomized_experiment",
        "allowed_claim_class": "causal",
        "required_diagnostics": ["randomization_integrity", "balance_diagnostics"],
    }
    assert by_name["multiplicity_handling"]["parameters"]["comparison_count"] == 3


def test_experiment_compiler_owns_core_user_design_facts_before_design_selection():
    requirements = _compile({
        "required_capability": "analysis.experiment",
        "claim_type": "causal",
    })
    by_name = {item["name"]: item for item in requirements}

    assert {
        "design_type",
        "assignment_unit",
        "treatment_arms",
        "exposure_definition",
        "outcome_definition",
        "assignment_rule",
    } <= set(by_name)
    assert all(
        by_name[name]["parameters"]["input_source"] == "user_or_plan"
        for name in {
            "design_type",
            "assignment_unit",
            "treatment_arms",
            "exposure_definition",
            "outcome_definition",
            "assignment_rule",
        }
    )


def test_power_mde_is_prospective_and_not_retrospective_proof():
    planning = _compile({
        "required_capability": "analysis.experiment",
        "claim_type": "planning",
        "design_type": "randomized_experiment",
        "analysis_phase": "planning",
    })
    observed = _compile({
        "required_capability": "analysis.experiment",
        "claim_type": "inferential",
        "design_type": "randomized_experiment",
        "analysis_phase": "effect_estimation",
    })
    power = next(item for item in planning if item["name"] == "power_mde")

    assert "power_mde" not in _names(observed)
    assert power["parameters"] == {
        "allowed_purposes": ["prospective_planning", "detectability_decision"],
        "retrospective_power_proves_effect": False,
    }

    retrospective = evaluate_requirement_satisfaction([power], [{
        "id": "ev_retrospective",
        "requirement_ids": [power["id"]],
        "power_mde": {
            "purpose": "retrospective_observed_effect_validation",
            "power": 0.9,
        },
    }])
    prospective = evaluate_requirement_satisfaction([power], [{
        "id": "ev_prospective",
        "requirement_ids": [power["id"]],
        "power_mde": {
            "purpose": "prospective_planning",
            "minimum_detectable_effect": 0.03,
        },
    }])

    assert retrospective[0]["status"] == "unmet"
    assert prospective[0]["status"] == "satisfied"


@pytest.mark.parametrize(
    ("design_type", "expected"),
    [
        ("difference_in_differences", {"parallel_trends", "comparison_group", "treatment_timing"}),
        ("matching", {"overlap_diagnostics", "balance_diagnostics"}),
        ("weighting", {"overlap_diagnostics", "balance_diagnostics"}),
        ("instrumental_variables", {"instrument_relevance", "exclusion_restriction"}),
        ("regression_discontinuity", {"discontinuity_diagnostics", "cutoff_assignment", "bandwidth_sensitivity"}),
    ],
)
def test_causal_designs_compile_their_identification_diagnostics(design_type, expected):
    requirements = _compile({
        "required_capability": "analysis.causal",
        "claim_type": "causal",
        "design_type": design_type,
    })

    assert expected <= _names(requirements)


def test_pre_post_without_control_is_bounded_to_association_and_alternatives():
    requirements = _compile({
        "required_capability": "analysis.causal",
        "claim_type": "causal",
        "design_type": "pre_post",
        "control_group_available": False,
    })
    by_name = {item["name"]: item for item in requirements}

    assert by_name["identification_status"]["parameters"] == {
        "design_type": "pre_post",
        "identified": False,
        "allowed_claim_class": "association",
        "reason": "A pre/post comparison without a control does not identify a causal effect.",
    }
    assert by_name["identification_status"]["claim_guard"] == "downgrade_claim"
    assert "alternative_explanations" in by_name


def test_only_missing_material_design_fact_is_asked_not_computable_diagnostics():
    step = {
        "step_id": "step_effect",
        "required_capability": "analysis.experiment",
        "claim_type": "causal",
        "design_type": "randomized_experiment",
        "treatment_arms": ["control", "treatment"],
        "exposure_definition": "assigned campaign",
        "outcome_definition": "30-day revenue",
        "assignment_rule": "server-side random allocation",
    }
    plan = {"id": "plan_effect", "playbook_id": "effect_evaluation", "method_plan": [step]}

    question = detect_question_need(
        "Estimate the causal experiment effect",
        _intent(),
        _state(plan),
    )

    assert question["question_type"] == "causal_design_definition"
    assert question["risk_fields"] == ["assignment_unit"]
    assert "balance_diagnostics" not in question["risk_fields"]
    assert "attrition" not in question["risk_fields"]

    step["assignment_unit"] = "user_id"
    clear = detect_question_need(
        "Estimate the causal experiment effect",
        _intent(),
        _state(plan),
    )

    assert clear["status"] == "clear"


def test_causal_route_schedules_diagnostics_and_exposes_association_boundary():
    route = {
        "id": "route_causal",
        "dataset": "orders",
        "direction": "causal",
        "design_type": "pre_post",
        "control_group_available": False,
        "allowed_claim_class": "association",
        "evidence_requirements": [
            "effect_estimate", "parallel_trends", "balance_diagnostics", "attrition",
        ],
    }
    plan = {
        "id": "plan_effect",
        "playbook_id": "effect_evaluation",
        "method_plan": [{
            "step_id": "step_effect",
            "required_capability": "analysis.causal",
            "claim_type": "causal",
            "design_type": "pre_post",
            "control_group_available": False,
            "exposure_definition": "campaign exposure",
            "outcome_definition": "revenue",
        }],
    }

    assert computable_route_evidence(route) == [
        "effect_estimate", "parallel_trends", "balance_diagnostics", "attrition",
    ]

    decision = decide_analysis_entry(
        "Did the campaign cause the revenue increase?",
        _intent(),
        _state(plan, routes=[route]),
    )

    assert decision["decision"] == "direct_analysis"
    assert decision["allowed_claim_class"] == "association"
