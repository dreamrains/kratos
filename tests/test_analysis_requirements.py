import pytest

import data_agent.agent.analysis_requirements as requirement_module
from data_agent.agent.analysis_requirements import (
    ANALYSIS_REQUIREMENT_CONTRACT_VERSION,
    ALLOWED_REQUIREMENT_CATEGORIES,
    ALLOWED_REQUIREMENT_NECESSITY,
    ALLOWED_REQUIREMENT_STATUSES,
    ALLOWED_UNMET_ACTIONS,
    compile_analysis_requirements,
)
from data_agent.agent.method_playbooks import PLAYBOOKS


def _plan(*requirements: str) -> dict:
    return {
        "id": "plan_requirements",
        "goal": "compare treatment outcomes",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "estimate the effect",
            "node_type": "analysis",
            "evidence_requirements": list(requirements),
        }],
    }


def test_compiler_produces_stable_ids_order_and_contract_shape():
    inputs = {
        "plan": _plan("significance", "sample_size", "effect_size", "sample_size"),
        "route": None,
        "playbook": None,
        "dataset_contracts": [],
        "user_intent": "compare treatment outcomes",
    }

    first = compile_analysis_requirements(**inputs)
    second = compile_analysis_requirements(**inputs)

    assert first == second
    assert [item["id"] for item in first] == [
        "req_step_1_effect_size",
        "req_step_1_sample_size",
        "req_step_1_significance",
    ]
    assert all(item["contract_version"] == ANALYSIS_REQUIREMENT_CONTRACT_VERSION for item in first)
    assert all(item["category"] in ALLOWED_REQUIREMENT_CATEGORIES for item in first)
    assert all(item["necessity"] in ALLOWED_REQUIREMENT_NECESSITY for item in first)
    assert all(item["status"] in ALLOWED_REQUIREMENT_STATUSES for item in first)
    assert all(item["unmet_action"] in ALLOWED_UNMET_ACTIONS for item in first)
    assert all(item["step_id"] == "step_1" for item in first)


def test_route_requirement_ids_normalize_current_and_legacy_projections():
    current = {"direction": "trend", "evidence_requirements": ["sample size", "limitations"]}
    legacy = {"direction": "trend", "expected_evidence": ["sample size", "limitations"]}

    assert requirement_module.requirement_ids_for_route(current) == ["sample_size", "limitations"]
    assert requirement_module.requirement_ids_for_route(legacy) == ["sample_size", "limitations"]


def test_satisfaction_evaluator_matches_requirement_ids_and_required_fields():
    requirements = compile_analysis_requirements(
        plan=_plan("effect_size", "sample_size", "significance"),
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="compare treatment outcomes",
    )
    records = [
        {
            "id": "evidence_effect",
            "requirement_ids": ["req_step_1_effect_size"],
            "effect_size": 0.4,
        },
        {
            "id": "evidence_sample",
            "requirement_ids": ["req_step_1_sample_size"],
            "result_summary": "sample was inspected",
        },
        {
            "id": "evidence_p_value_only",
            "requirement_ids": ["req_step_1_significance"],
            "p_value": 0.03,
        },
    ]

    evaluated = requirement_module.evaluate_requirement_satisfaction(requirements, records)

    by_name = {item["name"]: item for item in evaluated}
    assert by_name["effect_size"]["status"] == "satisfied"
    assert by_name["effect_size"]["evidence_ids"] == ["evidence_effect"]
    assert by_name["sample_size"]["status"] == "unmet"
    assert by_name["significance"]["status"] == "unmet"
    assert "p_value" not in by_name["significance"]["required_evidence_fields"]


def test_compiler_rejects_invalid_structured_requirement_contract():
    plan = _plan("sample_size")
    invalid = compile_analysis_requirements(
        plan=plan,
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="describe sample",
    )[0]
    invalid["category"] = "statistics_guess"
    plan["analysis_requirements"] = {"step_1": [invalid]}

    with pytest.raises(ValueError, match="category"):
        compile_analysis_requirements(
            plan=plan,
            route=None,
            playbook=None,
            dataset_contracts=[],
            user_intent="describe sample",
        )


def test_compiler_owns_merged_plan_route_and_playbook_inputs():
    compiled = compile_analysis_requirements(
        plan=_plan("effect_size"),
        route={"direction": "trend", "evidence_requirements": ["sample_size", "limitations"]},
        playbook={
            "evidence_policy": {"required_evidence": ["assumptions"]},
            "output_policy": {"statistical_requirements": ["confidence_interval", "effect_size"]},
        },
        dataset_contracts=[],
        user_intent="estimate and explain the treatment effect",
    )

    assert [item["id"] for item in compiled] == [
        "req_step_1_assumptions",
        "req_step_1_confidence_interval",
        "req_step_1_effect_size",
        "req_step_1_limitations",
        "req_step_1_sample_size",
    ]
    assert len({item["name"] for item in compiled}) == len(compiled)


def test_every_current_playbook_requirement_input_has_one_compiler_definition():
    for playbook in PLAYBOOKS.values():
        plan = {
            "id": f"plan_{playbook.id}",
            "goal": playbook.name,
            "method_plan": playbook.method_plan_template,
            "statistical_requirements": playbook.output_policy.get("statistical_requirements", []),
        }
        compiled = compile_analysis_requirements(
            plan=plan,
            route=None,
            playbook=playbook,
            dataset_contracts=[],
            user_intent=playbook.name,
        )
        compiled_names = {item["name"] for item in compiled}
        raw_inputs = list(playbook.evidence_policy.get("required_evidence", []))
        raw_inputs.extend(playbook.output_policy.get("statistical_requirements", []))
        for step in playbook.method_plan_template:
            raw_inputs.extend(step.get("evidence_requirements", []))
        expected_names = set(requirement_module.requirement_ids_for_route({
            "evidence_requirements": raw_inputs,
        }))

        assert expected_names <= compiled_names, playbook.id


def test_unknown_saved_requirement_string_is_preserved_as_bounded_compatibility_input():
    compiled = compile_analysis_requirements(
        plan=_plan("custom metric coverage"),
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="load a saved plan",
    )

    assert compiled == [{
        "contract_version": ANALYSIS_REQUIREMENT_CONTRACT_VERSION,
        "id": "req_step_1_custom_metric_coverage",
        "step_id": "step_1",
        "category": "output",
        "name": "custom_metric_coverage",
        "necessity": "required",
        "trigger": "explicit compiler input: custom_metric_coverage",
        "status": "pending",
        "required_evidence_fields": ["custom_metric_coverage"],
        "assumption_checks": [],
        "unmet_action": "disclose",
        "evidence_ids": [],
        "reason": "Compatibility requirement compiled from an unregistered saved input.",
    }]


def test_requirement_group_preserves_plan_step_id_while_id_uses_stable_slug():
    plan = _plan("sample_size")
    plan["method_plan"][0]["step_id"] = "Revenue Trend"

    compiled = compile_analysis_requirements(
        plan=plan,
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="analyze revenue trend",
    )

    assert compiled[0]["step_id"] == "Revenue Trend"
    assert compiled[0]["id"] == "req_revenue_trend_sample_size"
