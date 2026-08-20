from __future__ import annotations

import hashlib
from pathlib import Path

from data_agent.config import AgentConfig
from data_agent.v2.real_provider_journey import (
    REAL_PROVIDER_JOURNEY_VERSION,
    build_real_provider_preflight,
    validate_real_provider_preflight,
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


def test_preflight_counts_exact_request_without_authorizing_or_calling_provider():
    digest = "sha256:" + "a" * 64
    preflight = build_real_provider_preflight(
        fixture_path=FIXTURE,
        source_digest=digest,
        config=_config(),
        token_counter=lambda **_: 357,
    )

    result = validate_real_provider_preflight(
        preflight,
        expected_source_digest=digest,
        expected_model_id="openai/deepseek-v4-flash",
        expected_dataset_fingerprint=_fixture_fingerprint(),
    )

    assert preflight["version"] == REAL_PROVIDER_JOURNEY_VERSION
    assert preflight["provider_calls_observed"] == 0
    assert preflight["authorization_issued"] is False
    assert preflight["authorization_request"]["provider_calls"] == 1
    assert preflight["authorization_request"]["mode"] == "per_call"
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


def test_preflight_rejects_stale_source_hidden_retry_and_blanket_two_call_authorization():
    digest = "sha256:" + "b" * 64
    preflight = build_real_provider_preflight(
        fixture_path=FIXTURE,
        source_digest=digest,
        config=_config(),
        token_counter=lambda **_: 357,
    )
    preflight["source_digest"] = "sha256:" + "c" * 64
    preflight["authorization_request"]["provider_calls"] = 2
    preflight["authorization_request"]["mode"] = "blanket"
    preflight["dataset_fingerprint"] = "sha256:" + "d" * 64
    preflight["stop_conditions"].remove("provider_error")

    result = validate_real_provider_preflight(
        preflight,
        expected_source_digest=digest,
        expected_model_id="openai/deepseek-v4-flash",
        expected_dataset_fingerprint=_fixture_fingerprint(),
    )

    assert result.passed is False
    assert "stale_real_provider_preflight" in result.reason_codes
    assert "exactly_one_provider_call_required" in result.reason_codes
    assert "per_call_authorization_required" in result.reason_codes
    assert "real_provider_dataset_changed" in result.reason_codes
    assert "real_provider_request_fingerprint_mismatch" in result.reason_codes
    assert "missing_stop_condition:provider_error" in result.reason_codes
