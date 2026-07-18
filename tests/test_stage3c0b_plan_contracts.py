import json

from data_agent.agent.analysis_plan_contracts import (
    ANALYSIS_PLAN_CONTRACT_VERSION,
    STAGE3C0B_CONTRACT_VERSION,
    validate_analysis_plan_contract,
)
from data_agent.tools.analysis_flow import record_analysis_plan


def _contract(dataset: str, contract_id: str) -> dict:
    return {"dataset": dataset, "id": contract_id, "quality_status": "ready"}


def test_valid_stage3c0b_plan_is_reviewed_and_executable():
    plan = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Compare the independent performance evidence for uploaded game files.",
        "method_plan": [
            {
                "step_id": "step_banner",
                "goal": "Analyze banner exposure and click performance.",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "Banner evidence",
                "evidence_requirements": ["impressions", "click_rate"],
            },
            {
                "step_id": "step_synthesis",
                "goal": "Synthesize verified evidence across game files.",
                "dataset_inputs": [],
                "combination_mode": "synthesis",
                "expected_output": "Cross-file synthesis",
                "evidence_requirements": ["comparative_summary"],
                "required_evidence_step_ids": ["step_banner"],
            },
        ],
    }

    result = validate_analysis_plan_contract(
        plan,
        dataset_contracts=[_contract("banner", "contract_banner")],
    )

    assert result.ok is True
    assert result.plan["review_status"] == "executable"
    assert result.plan["method_plan"][0]["plan_id"] == result.plan["id"]
    assert result.plan["method_plan"][0]["dataset_contract_ids"] == ["contract_banner"]
    assert result.plan["method_plan"][0]["combination_mode"] == "independent"


def test_unversioned_plan_is_normalized_before_execution_validation():
    result = validate_analysis_plan_contract(
        {
            "goal": "Analyze orders.",
            "method_plan": [{
                "step_id": "s1",
                "goal": "Describe order volume.",
                "dataset_inputs": ["orders"],
                "combination_mode": "independent",
                "expected_output": "Order summary",
                "evidence_requirements": ["sample_size"],
            }],
        },
        dataset_contracts=[_contract("orders", "contract_orders")],
    )

    assert result.ok is True
    assert result.plan["contract_version"] == ANALYSIS_PLAN_CONTRACT_VERSION


def test_rejects_join_hidden_as_executable_stage3c0b_mode():
    plan = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Join orders and users.",
        "method_plan": [
            {
                "step_id": "step_join",
                "goal": "Join the datasets.",
                "dataset_inputs": ["orders", "users"],
                "combination_mode": "join",
                "expected_output": "Joined table",
                "evidence_requirements": ["joined_rows"],
            }
        ],
    }

    result = validate_analysis_plan_contract(plan, dataset_contracts=[
        _contract("orders", "contract_orders"),
        _contract("users", "contract_users"),
    ])

    assert result.ok is False
    assert result.error_type == "unsupported_combination_mode"
    assert "join" in result.message


def test_rejects_independent_step_with_missing_dataset_contract():
    plan = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Analyze a missing dataset.",
        "method_plan": [
            {
                "step_id": "step_missing",
                "goal": "Analyze the missing dataset.",
                "dataset_inputs": ["missing"],
                "combination_mode": "independent",
                "expected_output": "Evidence",
                "evidence_requirements": ["metric"],
            }
        ],
    }

    result = validate_analysis_plan_contract(
        plan,
        dataset_contracts=[_contract("banner", "contract_banner")],
    )

    assert result.ok is False
    assert result.error_type == "missing_dataset_contract"
    assert result.details["dataset_inputs"] == ["missing"]


def test_rejects_oversize_execution_batch_instead_of_truncating():
    steps = [
        {
            "step_id": f"step_{i}",
            "goal": f"Analyze dataset {i}.",
            "dataset_inputs": [f"ds_{i}"],
            "combination_mode": "independent",
            "expected_output": "Evidence",
            "evidence_requirements": ["metric"],
        }
        for i in range(13)
    ]
    contracts = [_contract(f"ds_{i}", f"contract_{i}") for i in range(13)]

    result = validate_analysis_plan_contract(
        {
            "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Analyze all datasets.",
            "method_plan": steps,
        },
        dataset_contracts=contracts,
    )

    assert result.ok is False
    assert result.error_type == "execution_batch_too_large"
    assert result.details["max_executable_steps_per_batch"] == 12


def test_rejects_synthesis_with_too_many_hard_dependencies():
    result = validate_analysis_plan_contract(
        {
            "contract_version": STAGE3C0B_CONTRACT_VERSION,
            "goal": "Synthesize a large batch.",
            "method_plan": [
                {
                    "step_id": "step_synthesis",
                    "goal": "Synthesize evidence.",
                    "dataset_inputs": [],
                    "combination_mode": "synthesis",
                    "expected_output": "Synthesis",
                    "evidence_requirements": ["summary"],
                    "required_evidence_step_ids": [f"step_{i}" for i in range(9)],
                }
            ],
        },
        dataset_contracts=[],
    )

    assert result.ok is False
    assert result.error_type == "too_many_required_evidence_dependencies"


def test_record_analysis_plan_normalizes_unversioned_executable_plan(monkeypatch):
    monkeypatch.setattr("data_agent.tools.analysis_flow._current_state", lambda: None)
    monkeypatch.setattr(
        "data_agent.tools.analysis_flow._write_analysis_artifact",
        lambda kind, payload: {"saved": "artifact.json", "type": kind, "payload": payload},
    )

    result = json.loads(record_analysis_plan(json.dumps({
        "goal": "Analyze files",
        "method_plan": [{
            "step_id": "s1",
            "goal": "Analyze orders.",
            "dataset_inputs": ["orders"],
            "combination_mode": "independent",
            "expected_output": "Order summary",
            "evidence_requirements": ["sample_size"],
        }],
        "visualization_strategy": "none",
    })))

    assert "error" not in result
    assert result["analysis_plan_id"]


def test_record_analysis_plan_persists_valid_stage3c0b_plan(monkeypatch):
    monkeypatch.setattr("data_agent.tools.analysis_flow._current_state", lambda: None)
    monkeypatch.setattr(
        "data_agent.tools.analysis_flow._write_analysis_artifact",
        lambda kind, payload: {"saved": "artifact.json", "type": kind, "payload": payload},
    )

    payload = {
        "contract_version": STAGE3C0B_CONTRACT_VERSION,
        "goal": "Analyze banner independently.",
        "method_plan": [
            {
                "step_id": "step_banner",
                "goal": "Analyze banner.",
                "dataset_inputs": ["banner"],
                "combination_mode": "independent",
                "expected_output": "Banner evidence",
                "evidence_requirements": ["click_rate"],
            }
        ],
        "visualization_strategy": "none",
    }

    result = json.loads(record_analysis_plan(json.dumps(payload)))

    assert result["analysis_plan_id"]
    assert result["state_stage"] if "state_stage" in result else True
    assert "error" not in result
