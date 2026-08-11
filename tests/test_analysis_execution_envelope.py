"""Task 6: server-owned canonical execution envelope and exact step binding."""

from __future__ import annotations

import pytest

from data_agent.agent.analysis_execution import (
    EnvelopeResult,
    StepBindingResult,
    bind_tool_call_to_plan_step,
    ensure_canonical_execution_envelope,
)
from data_agent.agent.analysis_plan_contracts import normalize_analysis_plan_contract
from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.intent import TurnIntent
from data_agent.tools.registry import registry


def _user_behavior_playbook(*args, **kwargs):
    """Mock that forces the user_behavior_analysis playbook (which has correlation)."""
    return {"primary": "user_behavior_analysis", "supporting": []}


def directed_intent() -> TurnIntent:
    return TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="plan",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )


def dataset_contract(name: str, version: str = "v1") -> dict:
    return {
        "dataset": name,
        "id": f"duc_{name}_{version}",
        "version": version,
        "quality_status": "ready",
    }


@pytest.fixture
def intent() -> TurnIntent:
    return directed_intent()


@pytest.fixture
def state(intent) -> AnalysisSessionState:
    """A fresh state with no persisted analysis plan.

    The envelope is responsible for materializing the canonical executable
    plan from the selected playbook; the fixture asserts the failure path
    leaves this empty and the success path replaces it.
    """

    state = AnalysisSessionState(session_id="envelope_test", data_state="data_loaded")
    state.analysis_plan = {}
    return state


@pytest.fixture
def envelope(state, intent, monkeypatch) -> EnvelopeResult:
    monkeypatch.setattr(
        "data_agent.agent.llm_playbook.select_playbook_llm",
        _user_behavior_playbook,
    )
    return ensure_canonical_execution_envelope(
        state=state,
        intent=intent,
        user_input="分析哪些因素与目标值显著相关",
        active_dataset_contracts=[dataset_contract("factors", version="v1")],
    )


def _build_executable_plan_with_two_correlation_steps() -> dict:
    """Construct a minimal executable plan with two correlation-compatible steps."""

    return {
        "id": "plan_ambiguous_association",
        "contract_version": "analysis_plan.v1",
        "review_status": "executable",
        "goal": "test ambiguous binding",
        "analysis_requirements": {
            "step_association_a": [
                {"id": "req_step_association_a_correlation", "name": "correlation"}
            ],
            "step_association_b": [
                {"id": "req_step_association_b_correlation", "name": "correlation"}
            ],
        },
        "method_plan": [
            {
                "step_id": "step_association_a",
                "plan_id": "plan_ambiguous_association",
                "goal": "association A",
                "node_type": "analysis",
                "required_capability": "analysis.correlation",
                "expected_output": "correlation summary A",
                "evidence_requirements": ["correlation"],
                "dataset_inputs": ["factors"],
                "combination_mode": "independent",
                "requirement_ids": ["req_step_association_a_correlation"],
            },
            {
                "step_id": "step_association_b",
                "plan_id": "plan_ambiguous_association",
                "goal": "association B",
                "node_type": "analysis",
                "required_capability": "analysis.correlation",
                "expected_output": "correlation summary B",
                "evidence_requirements": ["correlation"],
                "dataset_inputs": ["factors"],
                "combination_mode": "independent",
                "requirement_ids": ["req_step_association_b_correlation"],
            },
        ],
    }


@pytest.fixture
def envelope_with_two_matches() -> EnvelopeResult:
    return EnvelopeResult(ok=True, plan=_build_executable_plan_with_two_correlation_steps())


# --- Step 1: envelope materialization and exact binding ----------------------


def test_directed_turn_gets_executable_envelope_without_model_plan(state, intent, monkeypatch):
    monkeypatch.setattr(
        "data_agent.agent.llm_playbook.select_playbook_llm",
        _user_behavior_playbook,
    )
    result = ensure_canonical_execution_envelope(
        state=state,
        intent=intent,
        user_input="分析哪些因素与目标值显著相关",
        active_dataset_contracts=[dataset_contract("factors", version="v1")],
    )
    assert result.ok is True
    assert result.plan["review_status"] == "executable"
    assert result.plan["id"].startswith("plan_")
    assert all(step["dataset_inputs"] == ["factors"] for step in result.plan["method_plan"])
    assert all(step["requirement_ids"] for step in result.plan["method_plan"])


def test_single_compatible_pending_step_binds_deterministically(envelope):
    binding = bind_tool_call_to_plan_step(
        plan=envelope.plan,
        tool_name="correlation_analysis",
        capability=registry.capability_for("correlation_analysis"),
        dataset_names=["factors"],
        preferred_step_id="",
    )
    assert binding.ok is True
    assert binding.claim_key
    assert binding.claim_keys == (binding.claim_key,)
    assert binding.requirement_ids


def test_multi_claim_step_binding_preserves_every_exact_required_claim_key(envelope):
    step = next(
        item
        for item in envelope.plan["method_plan"]
        if item.get("required_capability") == "analysis.correlation"
    )
    step["required_claim_keys"] = ["significant_factors", "effect_estimates"]

    binding = bind_tool_call_to_plan_step(
        plan=envelope.plan,
        tool_name="correlation_analysis",
        capability=registry.capability_for("correlation_analysis"),
        dataset_names=["factors"],
        preferred_step_id=step["step_id"],
    )

    assert binding.ok is True
    assert binding.claim_key == "significant_factors"
    assert binding.claim_keys == ("significant_factors", "effect_estimates")


# --- Step 2: ambiguity and envelope failure ----------------------------------


def test_ambiguous_step_binding_remains_computation_only(envelope_with_two_matches):
    binding = bind_tool_call_to_plan_step(
        plan=envelope_with_two_matches.plan,
        tool_name="correlation_analysis",
        capability=registry.capability_for("correlation_analysis"),
        dataset_names=["factors"],
        preferred_step_id="",
    )
    assert binding.ok is False
    assert binding.error_type == "ambiguous_analysis_step"
    assert sorted(binding.candidate_step_ids) == ["step_association_a", "step_association_b"]


def test_envelope_failure_cannot_report_complete(state):
    result = ensure_canonical_execution_envelope(
        state=state,
        intent=directed_intent(),
        user_input="分析显著影响因素",
        active_dataset_contracts=[],
    )
    assert result.ok is False
    assert result.error_type == "analysis_dataset_identity_missing"
    assert state.analysis_plan == {}


# --- Additional depth/identity assertions -------------------------------------


def test_zero_compatible_steps_returns_analysis_step_not_found(envelope):
    binding = bind_tool_call_to_plan_step(
        plan=envelope.plan,
        tool_name="correlation_analysis",
        capability=registry.capability_for("correlation_analysis"),
        dataset_names=["unknown_dataset"],
        preferred_step_id="",
    )
    assert binding.ok is False
    assert binding.error_type == "analysis_step_not_found"


def test_preferred_step_id_binds_when_compatible(envelope):
    correlation_step_id = next(
        step["step_id"]
        for step in envelope.plan["method_plan"]
        if step.get("required_capability") == "analysis.correlation"
    )
    binding = bind_tool_call_to_plan_step(
        plan=envelope.plan,
        tool_name="correlation_analysis",
        capability=registry.capability_for("correlation_analysis"),
        dataset_names=["factors"],
        preferred_step_id=correlation_step_id,
    )
    assert binding.ok is True
    assert binding.step_id == correlation_step_id


@pytest.mark.parametrize("provider_label", ["python", "run_python"])
def test_provider_python_capability_alias_uses_registry_identity(provider_label):
    result = normalize_analysis_plan_contract(
        {
            "goal": "run a custom calculation",
            "method_plan": [
                {
                    "step_id": "step_python",
                    "goal": "calculate a metric not covered by a structured tool",
                    "required_capability": provider_label,
                    "dataset_inputs": ["factors"],
                    "expected_output": "custom calculation",
                    "evidence_requirements": ["limitations"],
                }
            ],
        },
        dataset_contracts=[dataset_contract("factors")],
        require_executable=True,
    )

    assert result.ok is True
    assert result.plan["method_plan"][0]["required_capability"] == "fallback.python"


def test_executable_plan_rejects_unregistered_required_capability():
    result = normalize_analysis_plan_contract(
        {
            "goal": "run an unavailable method",
            "method_plan": [
                {
                    "step_id": "step_unknown",
                    "goal": "invoke an unavailable method",
                    "required_capability": "analysis.not_registered",
                    "dataset_inputs": ["factors"],
                    "expected_output": "unknown output",
                    "evidence_requirements": ["limitations"],
                }
            ],
        },
        dataset_contracts=[dataset_contract("factors")],
        require_executable=True,
    )

    assert result.ok is False
    assert result.error_type == "unsupported_required_capability"
    assert result.details["step_id"] == "step_unknown"


def test_preferred_run_python_step_binds_before_runtime_dataset_discovery():
    plan = {
        "id": "plan_runtime_dataset",
        "method_plan": [
            {
                "step_id": "step_python",
                "required_capability": "fallback.python",
                "dataset_inputs": ["factors"],
                "required_claim_keys": ["custom_metric"],
            }
        ],
    }

    binding = bind_tool_call_to_plan_step(
        plan=plan,
        tool_name="run_python",
        capability=registry.capability_for("run_python"),
        dataset_names=[],
        preferred_step_id="step_python",
    )

    assert binding.ok is True
    assert binding.step_id == "step_python"
    assert binding.claim_keys == ("custom_metric",)


def test_runtime_discovered_dataset_binding_still_requires_current_step_identity():
    plan = {
        "id": "plan_runtime_dataset",
        "method_plan": [
            {
                "step_id": "step_python",
                "required_capability": "fallback.python",
                "dataset_inputs": ["factors"],
            }
        ],
    }

    unscoped = bind_tool_call_to_plan_step(
        plan=plan,
        tool_name="run_python",
        capability=registry.capability_for("run_python"),
        dataset_names=[],
        preferred_step_id="",
    )
    conflicting = bind_tool_call_to_plan_step(
        plan=plan,
        tool_name="run_python",
        capability=registry.capability_for("run_python"),
        dataset_names=["other"],
        preferred_step_id="step_python",
    )

    assert unscoped.ok is False
    assert unscoped.error_type == "analysis_step_not_found"
    assert conflicting.ok is False
    assert conflicting.error_type == "analysis_step_not_found"


def test_step_binding_result_is_frozen(envelope):
    binding = bind_tool_call_to_plan_step(
        plan=envelope.plan,
        tool_name="correlation_analysis",
        capability=registry.capability_for("correlation_analysis"),
        dataset_names=["factors"],
        preferred_step_id="",
    )
    assert binding.ok is True
    with pytest.raises(Exception):
        binding.step_id = "tampered"  # type: ignore[misc]


def test_envelope_records_turn_diagnostic_on_failure(state, intent):
    original_diagnostics = list(state.turn_diagnostics)
    ensure_canonical_execution_envelope(
        state=state,
        intent=intent,
        user_input="分析显著影响因素",
        active_dataset_contracts=[],
    )
    # Failure must not produce spurious diagnostics that claim a plan exists.
    assert state.turn_diagnostics == original_diagnostics


def test_envelope_does_not_persist_failed_executable_validation(state, intent, monkeypatch):
    """If the validator rejects the candidate, the prior plan stays untouched."""

    state.analysis_plan = {
        "id": "plan_existing",
        "contract_version": "analysis_plan.v1",
        "review_status": "display_only",
        "goal": "existing display-only plan",
        "method_plan": [
            {"step_id": "step_1", "goal": "x", "expected_output": "y", "evidence_requirements": ["sample_size"]},
        ],
    }
    monkeypatch.setattr(
        "data_agent.agent.llm_playbook.select_playbook_llm",
        _user_behavior_playbook,
    )
    result = ensure_canonical_execution_envelope(
        state=state,
        intent=intent,
        user_input="分析哪些因素与目标值显著相关",
        active_dataset_contracts=[dataset_contract("factors")],
    )
    # Whatever the envelope decides, it must not corrupt the existing plan silently.
    if not result.ok:
        assert state.analysis_plan["id"] == "plan_existing"


def test_envelope_returns_existing_executable_plan_without_rematerializing(state, intent):
    """An explicit executable plan (e.g. from record_analysis_plan) is not replaced."""

    explicit_plan = {
        "id": "plan_explicit_executable",
        "contract_version": "analysis_plan.v1",
        "review_status": "executable",
        "goal": "explicit",
        "method_plan": [
            {
                "step_id": "step_1",
                "goal": "explicit step",
                "node_type": "analysis",
                "required_capability": "analysis.correlation",
                "expected_output": "summary",
                "evidence_requirements": ["correlation"],
                "dataset_inputs": ["factors"],
                "combination_mode": "independent",
                "plan_id": "plan_explicit_executable",
                "dataset_contract_ids": ["duc_factors_v1"],
                "required_evidence_step_ids": [],
                "requirement_ids": [],
            },
        ],
        "analysis_requirements": {"step_1": []},
    }
    state.analysis_plan = dict(explicit_plan)
    result = ensure_canonical_execution_envelope(
        state=state,
        intent=intent,
        user_input="analyze correlation",
        active_dataset_contracts=[dataset_contract("factors")],
    )
    assert result.ok is True
    assert result.plan["id"] == "plan_explicit_executable"


# --- Legacy-fallback is plan-level, not per-step (Issue #1 regression) --------


def _build_mixed_capability_plan() -> dict:
    """A mixed plan: one capability-declaring step + one capability-less synthesis step.

    The synthesis step has empty ``dataset_inputs``, which ``_dataset_inputs_match``
    treats as compatible with every dataset. A wrong-capability tool must NOT
    silently fall through to the synthesis step and gain trusted step identity.
    """

    return {
        "id": "plan_mixed_capability",
        "contract_version": "analysis_plan.v1",
        "review_status": "executable",
        "goal": "mixed capability + synthesis",
        "analysis_requirements": {
            "step_corr": [{"id": "req_corr", "name": "correlation"}],
            "step_synth": [],
        },
        "method_plan": [
            {
                "step_id": "step_corr",
                "plan_id": "plan_mixed_capability",
                "goal": "correlation analysis",
                "node_type": "analysis",
                "required_capability": "analysis.correlation",
                "expected_output": "correlation summary",
                "evidence_requirements": ["correlation"],
                "dataset_inputs": ["factors"],
                "combination_mode": "independent",
                "requirement_ids": ["req_corr"],
            },
            {
                "step_id": "step_synth",
                "plan_id": "plan_mixed_capability",
                "goal": "synthesize findings",
                "node_type": "synthesis",
                "required_capability": "",
                "expected_output": "narrative",
                "evidence_requirements": [],
                "dataset_inputs": [],
                "combination_mode": "synthesis",
                "requirement_ids": [],
            },
        ],
    }


def test_mixed_plan_wrong_capability_does_not_bind_to_synthesis_step():
    """A wrong-capability tool must not bind to the capability-less synthesis step.

    Regression for the per-step legacy fallback: previously the synthesis step
    (empty ``required_capability``, empty ``dataset_inputs``) was a per-step
    legacy candidate, so a tool whose capability matched NEITHER step silently
    bound to it and gained trusted step identity. The fallback must be plan-level:
    because ``step_corr`` declares capability, the lax path is disabled.
    """

    plan = _build_mixed_capability_plan()
    binding = bind_tool_call_to_plan_step(
        plan=plan,
        tool_name="t_test",
        capability={"capability_id": "analysis.t_test"},
        dataset_names=["factors"],
        preferred_step_id="",
    )
    assert binding.ok is False
    assert binding.error_type == "analysis_step_not_found"
    assert binding.step_id == ""
    assert binding.claim_key == ""


def test_mixed_plan_correct_capability_binds_to_capability_step():
    """Complement of the regression: a correct-capability tool still binds to the
    capability-declaring step in a mixed plan (synthesis step must not steal it)."""

    plan = _build_mixed_capability_plan()
    binding = bind_tool_call_to_plan_step(
        plan=plan,
        tool_name="correlation_analysis",
        capability={"capability_id": "analysis.correlation"},
        dataset_names=["factors"],
        preferred_step_id="",
    )
    assert binding.ok is True
    assert binding.step_id == "step_corr"
    assert binding.claim_key == "analysis.correlation"
    assert binding.requirement_ids == ("req_corr",)
