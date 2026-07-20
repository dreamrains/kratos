from pathlib import Path

from data_agent.agent.analysis_plan_contracts import (
    ANALYSIS_PLAN_CONTRACT_VERSION,
    analysis_plan_id_from_mapping,
    normalize_analysis_plan_contract,
)
from data_agent.agent.analysis_state import AnalysisSessionState


def test_legacy_contract_version_normalizes_to_product_version():
    result = normalize_analysis_plan_contract({
        "contract_version": "stage3c0b.v1",
        "goal": "analyze revenue",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "describe revenue",
            "combination_mode": "independent",
            "dataset_inputs": ["orders"],
            "expected_output": "summary",
            "evidence_requirements": ["sample_size"],
        }],
    }, require_executable=True)

    assert result.ok is True
    assert result.plan["contract_version"] == ANALYSIS_PLAN_CONTRACT_VERSION


def test_required_claim_keys_are_typed_exact_and_survive_state_reload():
    plan = {
        "id": "plan_claim_keys",
        "goal": "calculate exact business outputs",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "calculate revenue and retention",
            "evidence_requirements": ["metric", "sample_size"],
            "required_claim_keys": ["revenue_per_user", "day7_retention"],
        }],
    }

    normalized = normalize_analysis_plan_contract(plan, require_executable=False)
    assert normalized.ok is True
    assert normalized.plan["method_plan"][0]["required_claim_keys"] == [
        "revenue_per_user",
        "day7_retention",
    ]

    reloaded = AnalysisSessionState.from_dict({
        "session_id": "claim-key-reload",
        "analysis_plan": normalized.plan,
    }, "claim-key-reload")
    assert reloaded.analysis_plan["method_plan"][0]["required_claim_keys"] == [
        "revenue_per_user",
        "day7_retention",
    ]


def test_required_claim_keys_reject_non_string_values():
    result = normalize_analysis_plan_contract({
        "id": "plan_invalid_claim_keys",
        "goal": "calculate exact business outputs",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "calculate revenue",
            "evidence_requirements": ["metric"],
            "required_claim_keys": ["revenue_per_user", 7],
        }],
    }, require_executable=False)

    assert result.ok is False
    assert result.error_type == "invalid_required_claim_keys"


def test_legacy_analysis_spec_loads_into_single_plan_field():
    state = AnalysisSessionState.from_dict({
        "session_id": "legacy",
        "analysis_spec": {"id": "plan_legacy", "goal": "legacy goal"},
    }, "legacy")

    assert state.analysis_plan["id"] == "plan_legacy"
    assert state.analysis_spec is state.analysis_plan
    assert "analysis_spec" not in state.to_dict()


def test_analysis_spec_property_is_not_a_second_write_path():
    state = AnalysisSessionState(session_id="single-writer")

    try:
        state.analysis_spec = {"goal": "bypass"}
    except AttributeError:
        pass
    else:
        raise AssertionError("analysis_spec must be read-only")


def test_runtime_does_not_assign_analysis_spec_directly():
    root = Path(__file__).resolve().parents[1] / "src" / "data_agent"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if ".analysis_spec =" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_persisted_confirmation_plan_id_has_one_legacy_reader():
    assert analysis_plan_id_from_mapping({"analysis_plan_id": "plan_current"}) == "plan_current"
    assert analysis_plan_id_from_mapping({"analysis_spec_id": "plan_legacy"}) == "plan_legacy"


def test_display_only_plan_compiles_structured_requirements_grouped_by_step():
    result = normalize_analysis_plan_contract({
        "id": "plan_display",
        "goal": "describe revenue",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "describe revenue",
            "evidence_requirements": ["sample_size", "limitations"],
        }],
    }, require_executable=False)

    assert result.ok is True
    assert list(result.plan["analysis_requirements"]) == ["step_1"]
    assert [item["id"] for item in result.plan["analysis_requirements"]["step_1"]] == [
        "req_step_1_limitations",
        "req_step_1_sample_size",
    ]
    assert result.plan["method_plan"][0]["evidence_requirements"] == ["limitations", "sample_size"]


def test_executable_plan_cannot_delete_compiler_required_hard_requirement():
    plan = {
        "id": "plan_executable",
        "goal": "estimate revenue effect",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "estimate revenue effect",
            "node_type": "analysis",
            "required_capability": "analysis.experiment",
            "combination_mode": "independent",
            "dataset_inputs": ["orders"],
            "expected_output": "effect estimate",
            "evidence_requirements": ["sample_size", "effect_size"],
        }],
    }
    compiled = normalize_analysis_plan_contract(plan, require_executable=False).plan
    compiled["analysis_requirements"]["step_1"] = [
        item
        for item in compiled["analysis_requirements"]["step_1"]
        if item["name"] != "effect_size"
    ]

    result = normalize_analysis_plan_contract(compiled, require_executable=True)

    assert result.ok is False
    assert result.error_type == "missing_compiled_hard_requirement"
    assert result.details["missing_requirement_ids"] == ["req_step_1_effect_size"]


def test_saved_plan_legacy_evidence_projection_loads_through_bounded_normalization():
    state = AnalysisSessionState.from_dict({
        "session_id": "legacy-requirements",
        "analysis_plan": {
            "id": "plan_legacy_requirements",
            "goal": "describe orders",
            "method_plan": [{
                "step_id": "step_1",
                "goal": "describe orders",
                "expected_evidence": ["sample size"],
            }],
        },
    }, "legacy-requirements")

    assert state.analysis_plan["method_plan"][0]["evidence_requirements"] == ["sample_size"]
    assert state.analysis_plan["analysis_requirements"]["step_1"][0]["id"] == "req_step_1_sample_size"


def test_state_passes_active_route_as_compiler_input_when_recording_plan():
    state = AnalysisSessionState(session_id="route-plan", data_state="data_loaded")
    state.active_scope["active_route"] = "trend"
    state.route_proposals = [{
        "id": "route_trend",
        "direction": "trend",
        "evidence_requirements": ["time_scope", "limitations"],
    }]

    plan = state.set_analysis_plan({
        "id": "plan_route",
        "goal": "analyze the revenue trend",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "analyze the revenue trend",
            "node_type": "analysis",
            "evidence_requirements": ["metric"],
        }],
    })

    names = [item["name"] for item in plan["analysis_requirements"]["step_1"]]
    assert names == ["limitations", "metric", "time_scope"]


def test_executable_plan_cannot_override_compiler_owned_definition():
    plan = {
        "id": "plan_conflict",
        "goal": "estimate revenue effect",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "estimate revenue effect",
            "node_type": "analysis",
            "combination_mode": "independent",
            "dataset_inputs": ["orders"],
            "expected_output": "effect estimate",
            "evidence_requirements": ["effect_size"],
        }],
    }
    compiled = normalize_analysis_plan_contract(plan, require_executable=False).plan
    compiled["analysis_requirements"]["step_1"][0]["unmet_action"] = "disclose"

    result = normalize_analysis_plan_contract(compiled, require_executable=True)

    assert result.ok is False
    assert result.error_type == "conflicting_compiled_requirement"
    assert result.details["conflicting_requirement_ids"] == ["req_step_1_effect_size"]


def test_compiled_route_projection_is_idempotent_when_plan_becomes_executable():
    route = {"direction": "trend", "evidence_requirements": ["time_scope"]}
    plan = {
        "id": "plan_route_idempotent",
        "goal": "analyze revenue trend",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "analyze revenue trend",
            "node_type": "analysis",
            "combination_mode": "independent",
            "dataset_inputs": ["orders"],
            "expected_output": "trend summary",
            "evidence_requirements": ["sample_size"],
        }],
    }
    display = normalize_analysis_plan_contract(
        plan,
        route=route,
        require_executable=False,
    ).plan

    executable = normalize_analysis_plan_contract(
        display,
        route=route,
        require_executable=True,
    )

    assert executable.ok is True
    assert executable.plan["method_plan"][0]["evidence_requirements"] == ["sample_size", "time_scope"]


def test_saved_state_compiles_legacy_plan_with_saved_active_route_input():
    state = AnalysisSessionState.from_dict({
        "session_id": "saved-route-plan",
        "active_scope": {"active_route": "trend"},
        "route_proposals": [{
            "id": "route_trend",
            "direction": "trend",
            "evidence_requirements": ["time_scope"],
        }],
        "analysis_plan": {
            "id": "plan_saved_route",
            "goal": "analyze trend",
            "method_plan": [{
                "step_id": "step_1",
                "goal": "analyze trend",
                "node_type": "analysis",
                "evidence_requirements": ["sample_size"],
            }],
        },
    }, "saved-route-plan")

    names = [item["name"] for item in state.analysis_plan["analysis_requirements"]["step_1"]]
    assert names == ["sample_size", "time_scope"]


def test_canonical_only_saved_plan_loads_and_rebuilds_compatibility_projection():
    compiled = normalize_analysis_plan_contract({
        "id": "plan_canonical_only",
        "goal": "estimate effect",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "estimate effect",
            "node_type": "analysis",
            "evidence_requirements": ["effect_size", "sample_size"],
        }],
    }, require_executable=False).plan
    compiled["analysis_requirements"]["step_1"][0]["status"] = "satisfied"
    compiled["analysis_requirements"]["step_1"][0]["evidence_ids"] = ["evidence_effect"]
    compiled["method_plan"][0].pop("evidence_requirements")

    state = AnalysisSessionState.from_dict({
        "session_id": "canonical-only",
        "analysis_plan": compiled,
    }, "canonical-only")

    requirements = state.analysis_plan["analysis_requirements"]["step_1"]
    assert [item["name"] for item in requirements] == ["effect_size", "sample_size"]
    assert requirements[0]["status"] == "satisfied"
    assert requirements[0]["evidence_ids"] == ["evidence_effect"]
    assert state.analysis_plan["method_plan"][0]["evidence_requirements"] == [
        "effect_size",
        "sample_size",
    ]


def test_canonical_requirements_override_stale_compatibility_projection_on_load():
    compiled = normalize_analysis_plan_contract({
        "id": "plan_stale_projection",
        "goal": "estimate effect",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "estimate effect",
            "node_type": "analysis",
            "evidence_requirements": ["effect_size", "sample_size"],
        }],
    }, require_executable=False).plan
    compiled["method_plan"][0]["evidence_requirements"] = [
        "effect_size",
        "sample_size",
        "time_scope",
    ]

    state = AnalysisSessionState.from_dict({
        "session_id": "stale-projection",
        "analysis_plan": compiled,
    }, "stale-projection")

    names = [
        item["name"]
        for item in state.analysis_plan["analysis_requirements"]["step_1"]
    ]
    assert names == ["effect_size", "sample_size"]
    assert state.analysis_plan["method_plan"][0]["evidence_requirements"] == names


def test_executable_plan_rejects_deletion_from_canonical_and_compatibility_projection():
    compiled = normalize_analysis_plan_contract({
        "id": "plan_double_delete",
        "goal": "estimate experiment effect",
        "method_plan": [{
            "step_id": "step_1",
            "goal": "estimate experiment effect",
            "node_type": "analysis",
            "required_capability": "analysis.experiment",
            "combination_mode": "independent",
            "dataset_inputs": ["orders"],
            "expected_output": "effect estimate",
            "evidence_requirements": ["effect_size", "sample_size"],
        }],
    }, require_executable=False).plan
    compiled["analysis_requirements"]["step_1"] = [
        item
        for item in compiled["analysis_requirements"]["step_1"]
        if item["name"] != "effect_size"
    ]
    compiled["method_plan"][0]["evidence_requirements"] = ["sample_size"]

    result = normalize_analysis_plan_contract(compiled, require_executable=True)

    assert result.ok is False
    assert result.error_type == "missing_compiled_hard_requirement"
    assert "req_step_1_effect_size" in result.details["missing_requirement_ids"]


def test_legacy_saved_plan_accepts_unknown_requirement_only_at_load_boundary():
    state = AnalysisSessionState.from_dict({
        "session_id": "legacy-unknown",
        "analysis_plan": {
            "id": "plan_legacy_unknown",
            "goal": "load old custom analysis",
            "method_plan": [{
                "step_id": "step_1",
                "goal": "load old custom analysis",
                "evidence_requirements": ["custom metric coverage"],
            }],
        },
    }, "legacy-unknown")

    requirement = state.analysis_plan["analysis_requirements"]["step_1"][0]
    assert requirement["name"] == "custom_metric_coverage"
    assert requirement["unmet_action"] == "disclose"
    assert requirement["reason"] == (
        "Compatibility requirement compiled from an unregistered saved input."
    )
