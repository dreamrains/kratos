from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

from data_agent.config import AgentConfig
from data_agent.v2.real_provider_journey import (
    REAL_PROVIDER_JOURNEY_VERSION,
    build_real_provider_preflight,
    validate_real_provider_preflight,
)
from data_agent.v2.release import load_release_matrix
from data_agent.v2.representative_provider_preflight import (
    REPRESENTATIVE_PROVIDER_PREFLIGHT_VERSION,
    build_representative_provider_preflight,
    validate_representative_provider_preflight,
)


FIXTURE = Path("tests/fixtures/v2_slice4d_combined.csv")


def _fixture_fingerprint() -> str:
    return "sha256:" + hashlib.sha256(FIXTURE.read_bytes()).hexdigest()


def _config() -> AgentConfig:
    return AgentConfig(
        MODEL_ID="openai/deepseek-v4-flash",
        API_BASE="https://api.deepseek.com/v1",
        API_KEY="not-used-by-preflight",
        MAX_TOKENS=8000,
    )


def _token_counter(**kwargs) -> int:
    if "tools" in kwargs:
        return 357
    if "messages" in kwargs:
        return 100
    return 200


def test_preflight_counts_full_request_without_authorizing_or_calling_provider():
    digest = "sha256:" + "a" * 64
    preflight = build_real_provider_preflight(
        fixture_path=FIXTURE,
        source_digest=digest,
        config=_config(),
        token_counter=_token_counter,
        confirmed_analysis_unit_column="unit_id",
    )

    result = validate_real_provider_preflight(
        preflight,
        expected_source_digest=digest,
        expected_model_id="openai/deepseek-v4-flash",
        expected_dataset_fingerprint=_fixture_fingerprint(),
        expected_planner_contract_gate=preflight["planner_contract_gate"],
        expected_semantic_context=preflight["semantic_context"],
    )

    assert preflight["version"] == REAL_PROVIDER_JOURNEY_VERSION
    assert preflight["provider_calls_observed"] == 0
    assert preflight["authorization_issued"] is False
    assert preflight["authorization_request"]["provider_calls"] == 1
    assert preflight["authorization_request"]["mode"] == "per_call"
    assert preflight["planner_contract_gate"] == {
            "version": "v2_planner_contract_parity.v5",
        "passed": True,
        "schema_fingerprint": preflight["planner_contract_gate"][
            "schema_fingerprint"
        ],
        "automatic_analysis_kinds": [
            "descriptive",
            "factor_relationship",
            "date_transformation",
            "group_comparison",
            "time_trend",
            "forecast",
            "multi_finding_synthesis",
            "curve_fitting",
        ],
            "ready_variant_count": 6,
            "needs_input_variants": [
                {
                    "analysis_kind": "factor_relationship",
                    "missing_prerequisites": ["compatible_column_binding"],
                },
                {
                    "analysis_kind": "curve_fitting",
                    "missing_prerequisites": ["curve_binding"],
                },
            ],
            "needs_input_variant_count": 2,
            "unsupported_variant_count": 1,
            "status_variant_count": 9,
    }
    assert preflight["planner_contract_gate"]["schema_fingerprint"].startswith(
        "sha256:"
    )
    assert preflight["planning_context"] == {
        "model_id": "openai/deepseek-v4-flash",
        "estimated_input_tokens": 357,
        "model_context_window_tokens": 1_000_000,
        "reserved_output_tokens": 8000,
        "available_input_tokens": 992_000,
        "fits": True,
    }
    assert preflight["conditional_followup"] == {
        "allowed_only_if_status": "needs_input",
        "provider_calls": 1,
        "requires_new_user_authorization": True,
        "requires_fresh_token_estimate": True,
    }
    assert result.passed is True
    assert result.reason_codes == ()


def test_preflight_rejects_missing_explicit_analysis_unit_confirmation():
    digest = "sha256:" + "e" * 64
    preflight = build_real_provider_preflight(
        fixture_path=FIXTURE,
        source_digest=digest,
        config=_config(),
        token_counter=_token_counter,
    )

    result = validate_real_provider_preflight(
        preflight,
        expected_source_digest=digest,
        expected_model_id="openai/deepseek-v4-flash",
        expected_dataset_fingerprint=_fixture_fingerprint(),
        expected_planner_contract_gate=preflight["planner_contract_gate"],
        expected_semantic_context=preflight["semantic_context"],
    )

    assert result.passed is False
    assert "real_provider_analysis_unit_unconfirmed" in result.reason_codes


def test_preflight_binds_explicit_confirmed_analysis_unit_before_first_call():
    digest = "sha256:" + "f" * 64
    preflight = build_real_provider_preflight(
        fixture_path=FIXTURE,
        source_digest=digest,
        config=_config(),
        token_counter=_token_counter,
        confirmed_analysis_unit_column="unit_id",
    )

    assert preflight["semantic_context"] == {
        "confirmed_analysis_unit_column": "unit_id"
    }
    assert preflight["planner_contract_gate"]["ready_variant_count"] == 6
    assert preflight["planner_contract_gate"]["needs_input_variants"] == [
        {
            "analysis_kind": "factor_relationship",
            "missing_prerequisites": ["compatible_column_binding"],
        },
        {
            "analysis_kind": "curve_fitting",
            "missing_prerequisites": ["curve_binding"],
        },
    ]

    tampered = deepcopy(preflight)
    tampered["semantic_context"] = {
        "confirmed_analysis_unit_column": "channel"
    }
    result = validate_real_provider_preflight(
        tampered,
        expected_source_digest=digest,
        expected_model_id="openai/deepseek-v4-flash",
        expected_dataset_fingerprint=_fixture_fingerprint(),
        expected_planner_contract_gate=preflight["planner_contract_gate"],
        expected_semantic_context={
            "confirmed_analysis_unit_column": "unit_id"
        },
    )

    assert result.passed is False
    assert "real_provider_request_fingerprint_mismatch" in result.reason_codes
    assert "real_provider_semantic_context_mismatch" in result.reason_codes


def test_preflight_rejects_stale_source_hidden_retry_and_blanket_two_call_authorization():
    digest = "sha256:" + "b" * 64
    preflight = build_real_provider_preflight(
        fixture_path=FIXTURE,
        source_digest=digest,
        config=_config(),
        token_counter=_token_counter,
        confirmed_analysis_unit_column="unit_id",
    )
    expected_planner_contract_gate = deepcopy(preflight["planner_contract_gate"])
    preflight["source_digest"] = "sha256:" + "c" * 64
    preflight["authorization_request"]["provider_calls"] = 2
    preflight["authorization_request"]["mode"] = "blanket"
    preflight["dataset_fingerprint"] = "sha256:" + "d" * 64
    preflight["stop_conditions"].remove("provider_error")
    preflight["planner_contract_gate"]["passed"] = False
    preflight["planner_contract_gate"]["ready_variant_count"] = 5

    result = validate_real_provider_preflight(
        preflight,
        expected_source_digest=digest,
        expected_model_id="openai/deepseek-v4-flash",
        expected_dataset_fingerprint=_fixture_fingerprint(),
        expected_planner_contract_gate=expected_planner_contract_gate,
        expected_semantic_context={
            "confirmed_analysis_unit_column": "unit_id"
        },
    )

    assert result.passed is False
    assert "stale_real_provider_preflight" in result.reason_codes
    assert "exactly_one_provider_call_required" in result.reason_codes
    assert "per_call_authorization_required" in result.reason_codes
    assert "real_provider_dataset_changed" in result.reason_codes
    assert "real_provider_request_fingerprint_mismatch" in result.reason_codes
    assert "missing_stop_condition:provider_error" in result.reason_codes
    assert "planner_parameter_contract_parity_failed" in result.reason_codes
    assert "invalid_planner_ready_variant_count" in result.reason_codes
    assert "planner_contract_gate_mismatch" in result.reason_codes


def test_grouped_preflight_freezes_exactly_two_matrix_representatives_without_authorizing():
    digest = "sha256:" + "7" * 64
    matrix = load_release_matrix("tests/release/v2_release_matrix.json")

    preflight = build_representative_provider_preflight(
        repository_root=Path.cwd(),
        matrix=matrix,
        source_digest=digest,
        config=_config(),
        token_counter=_token_counter,
        confirmed_analysis_unit_column="unit_id",
    )
    result = validate_representative_provider_preflight(
        preflight,
        repository_root=Path.cwd(),
        matrix=matrix,
        expected_source_digest=digest,
        expected_model_id="openai/deepseek-v4-flash",
    )

    assert preflight["version"] == REPRESENTATIVE_PROVIDER_PREFLIGHT_VERSION
    assert preflight["provider_calls_observed"] == 0
    assert preflight["authorization_issued"] is False
    assert preflight["authorization_request"] == {
        "mode": "grouped_exact_calls",
        "purpose": "analysis_planning",
        "provider_calls": 2,
    }
    assert [item["scenario_id"] for item in preflight["calls"]] == [
        "unified_analysis_entry",
        "backtested_forecast",
    ]
    assert all(
        item["authorization_request"]["provider_calls"] == 1
        for item in preflight["calls"]
    )
    assert preflight["calls"][0]["semantic_context"] == {
        "confirmed_analysis_unit_column": "unit_id"
    }
    assert preflight["calls"][1]["semantic_context"] == {
        "confirmed_analysis_unit_column": ""
    }
    assert result.passed is True
    assert result.reason_codes == ()


def test_grouped_preflight_rejects_budget_order_and_nested_request_drift():
    digest = "sha256:" + "8" * 64
    matrix = load_release_matrix("tests/release/v2_release_matrix.json")
    preflight = build_representative_provider_preflight(
        repository_root=Path.cwd(),
        matrix=matrix,
        source_digest=digest,
        config=_config(),
        token_counter=_token_counter,
        confirmed_analysis_unit_column="unit_id",
    )
    preflight["authorization_request"]["provider_calls"] = 3
    preflight["calls"].reverse()
    preflight["calls"][0]["fixture_path"] = "tests/fixtures/relabelled.csv"

    result = validate_representative_provider_preflight(
        preflight,
        repository_root=Path.cwd(),
        matrix=matrix,
        expected_source_digest=digest,
        expected_model_id="openai/deepseek-v4-flash",
    )

    assert result.passed is False
    assert "representative_provider_call_budget_mismatch" in result.reason_codes
    assert "representative_provider_target_order_changed" in result.reason_codes
    assert "representative_provider_group_fingerprint_mismatch" in result.reason_codes
