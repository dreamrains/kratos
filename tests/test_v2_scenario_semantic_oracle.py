from pathlib import Path

from data_agent.v2.release import ValidationLayer, load_release_matrix
from data_agent.v2.scenario_semantic_oracle import (
    SCENARIO_SEMANTIC_ORACLE_VERSION,
    collect_scenario_semantic_evidence,
    validate_scenario_semantic_evidence,
)


MATRIX = Path("tests/release/v2_release_matrix.json")


def test_all_release_scenarios_run_through_provider_neutral_semantic_oracles(tmp_path):
    matrix = load_release_matrix(MATRIX)
    digest = "sha256:" + "a" * 64

    evidence = collect_scenario_semantic_evidence(
        tmp_path,
        matrix=matrix,
        source_digest=digest,
        repository_root=Path.cwd(),
    )
    result = validate_scenario_semantic_evidence(
        evidence,
        matrix=matrix,
        expected_source_digest=digest,
    )

    assert evidence["version"] == SCENARIO_SEMANTIC_ORACLE_VERSION
    assert evidence["provider_calls"] == 0
    assert result.passed is True
    assert result.reason_codes == ()
    assert len(result.receipts) == 9
    assert all(
        item.layer is ValidationLayer.SCENARIO_SEMANTIC_ORACLE
        for item in result.receipts
    )
    assert {item.scenario_id for item in result.receipts} == {
        item.scenario_id for item in matrix.scenarios
    }


def test_semantic_oracle_rejects_relabelled_fixture_missing_events_and_failed_assertion(
    tmp_path,
):
    matrix = load_release_matrix(MATRIX)
    digest = "sha256:" + "b" * 64
    evidence = collect_scenario_semantic_evidence(
        tmp_path,
        matrix=matrix,
        source_digest=digest,
        repository_root=Path.cwd(),
    )
    first = evidence["scenarios"][0]
    first["fixture_path"] = "tests/fixtures/relabelled.csv"
    first["observed_semantic_events"] = ["turn_completed"]
    first["assertions"]["persisted_finalized"] = False

    result = validate_scenario_semantic_evidence(
        evidence,
        matrix=matrix,
        expected_source_digest=digest,
    )

    assert result.passed is False
    assert result.receipts == ()
    assert "wrong_semantic_oracle_fixture:descriptive_analysis" in result.reason_codes
    assert "semantic_events_incomplete:descriptive_analysis" in result.reason_codes
    assert "semantic_assertion_failed:descriptive_analysis:persisted_finalized" in result.reason_codes
