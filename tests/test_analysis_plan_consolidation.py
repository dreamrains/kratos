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
