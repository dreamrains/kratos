from data_agent.agent.analysis_plan_contracts import (
    STAGE3C0B_CONTRACT_VERSION,
    validate_analysis_plan_contract,
)


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


def test_rejects_legacy_or_missing_contract_version_for_execution():
    result = validate_analysis_plan_contract(
        {"goal": "legacy", "method_plan": [{"step_id": "s1"}]},
        dataset_contracts=[],
    )

    assert result.ok is False
    assert result.error_type == "legacy_plan_display_only"
    assert "contract_version" in result.message


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
