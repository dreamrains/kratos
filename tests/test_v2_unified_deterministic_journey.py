from __future__ import annotations

from pathlib import Path

from data_agent.v2.release import (
    ValidationLayer,
    evaluate_release_readiness,
    load_release_matrix,
)
from data_agent.v2.unified_deterministic_journey import (
    DETERMINISTIC_JOURNEY_VERSION,
    collect_unified_deterministic_evidence,
    validate_unified_deterministic_evidence,
)


FIXTURE = Path("tests/fixtures/v2_slice4d_combined.csv")
MATRIX = Path("tests/release/v2_release_matrix.json")


def _scenario():
    return next(
        item
        for item in load_release_matrix(MATRIX).scenarios
        if item.scenario_id == "unified_analysis_entry"
    )


def test_real_runtime_evidence_computes_owner_incident_and_sse_receipts(tmp_path):
    digest = "sha256:" + "a" * 64
    evidence = collect_unified_deterministic_evidence(
        tmp_path,
        fixture_path=FIXTURE,
        source_digest=digest,
    )

    result = validate_unified_deterministic_evidence(
        evidence,
        scenario=_scenario(),
        expected_source_digest=digest,
    )

    assert evidence["version"] == DETERMINISTIC_JOURNEY_VERSION
    assert evidence["owner_observations"] == {
        "immutable_dataset_versions": True,
        "findings_bound_to_commitments": True,
        "completion_computed_from_ledger": True,
        "published_blocks_bound_to_findings": True,
        "charts_bound_to_findings": True,
        "run_state_matches_publication": True,
    }
    assert all(evidence["incident_observations"].values())
    assert evidence["sse_observations"]["required_order"] is True
    assert evidence["sse_observations"]["completed_terminal_exclusive"] is True
    assert evidence["sse_observations"]["interrupted_terminal_exclusive"] is True
    assert result.passed is True
    assert result.reason_codes == ()
    assert tuple(item.layer for item in result.receipts) == (
        ValidationLayer.OWNER_CONTRACT,
        ValidationLayer.INCIDENT_REPLAY,
        ValidationLayer.SSE_TRANSPORT_CONTRACT,
    )
    decision = evaluate_release_readiness(
        load_release_matrix(MATRIX),
        result.receipts,
        current_source_digest=digest,
    )
    assert not decision.incomplete_receipt_ids


def test_validator_rejects_asserted_owner_incident_and_invalid_sse(tmp_path):
    digest = "sha256:" + "b" * 64
    evidence = collect_unified_deterministic_evidence(
        tmp_path,
        fixture_path=FIXTURE,
        source_digest=digest,
    )
    evidence["source_digest"] = "sha256:" + "c" * 64
    evidence["fixture_path"] = "tests/fixtures/v2_slice1_sales.csv"
    evidence["owner_observations"]["completion_computed_from_ledger"] = False
    evidence["incident_observations"]["final_after_interrupt_blocked"] = False
    evidence["sse_observations"]["completed_events"] = ["turn_completed"]
    evidence["sse_observations"]["required_order"] = False

    result = validate_unified_deterministic_evidence(
        evidence,
        scenario=_scenario(),
        expected_source_digest=digest,
    )

    assert result.passed is False
    assert result.receipts == ()
    assert "stale_deterministic_journey" in result.reason_codes
    assert "wrong_deterministic_dataset_fixture" in result.reason_codes
    assert "missing_owner_observation:completion_computed_from_ledger" in result.reason_codes
    assert "missing_incident_observation:final_after_interrupt_blocked" in result.reason_codes
    assert "invalid_sse_event_order" in result.reason_codes
    assert "missing_required_sse_event:turn_started" in result.reason_codes
