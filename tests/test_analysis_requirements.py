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


def test_unknown_live_requirement_input_is_rejected():
    with pytest.raises(ValueError, match="Unknown live AnalysisRequirement input"):
        compile_analysis_requirements(
            plan=_plan("custom metric coverage"),
            route=None,
            playbook=None,
            dataset_contracts=[],
            user_intent="run a current plan",
        )


def test_requirement_group_preserves_plan_step_id_while_unsafe_id_uses_reserved_namespace():
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
    assert compiled[0]["id"].startswith("req_unsafe_")
    assert compiled[0]["id"].endswith("_sample_size")


def test_requirement_ids_are_collision_safe_for_distinct_step_ids_with_same_slug():
    plan = {
        "id": "plan_colliding_step_slugs",
        "goal": "compare revenue trends",
        "method_plan": [
            {
                "step_id": "Revenue-Trend",
                "goal": "analyze first revenue trend",
                "evidence_requirements": ["sample_size"],
            },
            {
                "step_id": "Revenue Trend",
                "goal": "analyze second revenue trend",
                "evidence_requirements": ["sample_size"],
            },
        ],
    }

    first = compile_analysis_requirements(
        plan=plan,
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="compare revenue trends",
    )
    second = compile_analysis_requirements(
        plan=plan,
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="compare revenue trends",
    )

    ids = [item["id"] for item in first]
    assert first == second
    assert len(ids) == len(set(ids)) == 2
    assert all(identifier.startswith("req_unsafe_") for identifier in ids)


def test_unsafe_requirement_id_is_stable_when_colliding_peer_is_added():
    original = {
        "id": "plan_original",
        "goal": "analyze unicode step",
        "method_plan": [{
            "step_id": "é",
            "goal": "analyze the first unicode step",
            "evidence_requirements": ["sample_size"],
        }],
    }
    evolved = {
        **original,
        "id": "plan_evolved",
        "method_plan": [
            *original["method_plan"],
            {
                "step_id": "É",
                "goal": "analyze the case-distinct unicode step",
                "evidence_requirements": ["sample_size"],
            },
        ],
    }

    original_id = compile_analysis_requirements(
        plan=original,
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="analyze unicode step",
    )[0]["id"]
    evolved_id = next(
        item["id"]
        for item in compile_analysis_requirements(
            plan=evolved,
            route=None,
            playbook=None,
            dataset_contracts=[],
            user_intent="analyze unicode steps",
        )
        if item["step_id"] == "é"
    )

    assert original_id == evolved_id
    assert original_id.startswith("req_unsafe_")


def test_requirement_ids_are_unique_for_adversarial_unicode_case_and_spacing_steps():
    step_ids = [
        "é",
        "É",
        "é 3 w6k",
        "Revenue Trend",
        "revenue trend",
        "revenue  trend",
        "step_1",
        "step_unsafe_probe",
    ]
    plan = {
        "id": "plan_adversarial_step_ids",
        "goal": "analyze adversarial step identities",
        "method_plan": [
            {
                "step_id": step_id,
                "goal": f"analyze {step_id}",
                "evidence_requirements": ["sample_size"],
            }
            for step_id in step_ids
        ],
    }

    compiled = compile_analysis_requirements(
        plan=plan,
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="analyze adversarial step identities",
    )

    ids_by_step = {item["step_id"]: item["id"] for item in compiled}
    assert set(ids_by_step) == set(step_ids)
    assert len(set(ids_by_step.values())) == len(step_ids)
    assert ids_by_step["step_1"] == "req_step_1_sample_size"
    assert ids_by_step["step_unsafe_probe"] == "req_step_unsafe_probe_sample_size"
    assert all(
        identifier.startswith("req_unsafe_")
        for step_id, identifier in ids_by_step.items()
        if not step_id.startswith("step_")
    )


def test_satisfaction_requires_explicit_successful_assumption_checks():
    requirement = compile_analysis_requirements(
        plan=_plan("significance"),
        route=None,
        playbook=None,
        dataset_contracts=[],
        user_intent="evaluate statistical support",
    )[0]
    base_record = {
        "id": "evidence_significance",
        "requirement_ids": [requirement["id"]],
        "significance": {"p_value": 0.03},
    }

    missing = requirement_module.evaluate_requirement_satisfaction(
        [requirement],
        [base_record],
    )[0]
    failed = requirement_module.evaluate_requirement_satisfaction(
        [requirement],
        [{
            **base_record,
            "assumption_checks": [{
                "name": "method_appropriate_for_design",
                "status": "failed",
                "evidence": "design mismatch",
            }],
        }],
    )[0]
    passed = requirement_module.evaluate_requirement_satisfaction(
        [requirement],
        [{
            **base_record,
            "assumption_checks": [{
                "name": "method_appropriate_for_design",
                "status": "passed",
                "evidence": "method matches the randomized design",
            }],
        }],
    )[0]

    assert missing["status"] == "unmet"
    assert "method_appropriate_for_design" in missing["reason"]
    assert failed["status"] == "unmet"
    assert passed["status"] == "satisfied"


def test_multi_step_playbook_binds_global_requirements_to_semantic_method_step():
    playbook = PLAYBOOKS["user_behavior_analysis"]
    plan = {
        "id": "plan_user_behavior",
        "goal": "analyze user behavior",
        "method_plan": playbook.method_plan_template,
        "statistical_requirements": playbook.output_policy["statistical_requirements"],
    }

    first = compile_analysis_requirements(
        plan=plan,
        route=None,
        playbook=playbook,
        dataset_contracts=[],
        user_intent="analyze user behavior",
    )
    second = compile_analysis_requirements(
        plan=plan,
        route=None,
        playbook=playbook,
        dataset_contracts=[],
        user_intent="analyze user behavior",
    )

    assert first == second
    by_step = {
        step_id: [item["name"] for item in first if item["step_id"] == step_id]
        for step_id in ("step_1", "step_2", "step_3")
    }
    assert "distribution" in by_step["step_1"]
    assert "correlation" not in by_step["step_1"]
    assert "significance" not in by_step["step_1"]
    assert "correlation" in by_step["step_3"]
    assert "significance" in by_step["step_3"]
    assert by_step["step_3"] == sorted(by_step["step_3"])
