from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.acceptance.real_user_journey_oracles import (
    DEFAULT_MANIFEST,
    SCENARIO_MANIFEST_VERSION,
    SCENARIO_ORACLE_VERSION,
    get_scenario,
    load_scenario_manifest,
    run_scenario_oracle,
    write_scenario_oracle,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "reference" / "test_doc"
SCENARIO_IDS = (
    "retention_descriptive_v1",
    "cross_promo_funnel_v1",
    "card_multifile_paired_v1",
)


def test_real_user_journey_manifest_has_distinct_risk_scenarios():
    manifest = load_scenario_manifest()

    assert manifest["contract_version"] == SCENARIO_MANIFEST_VERSION
    assert [item["scenario_id"] for item in manifest["scenarios"]] == list(
        SCENARIO_IDS
    )
    assert manifest["risk_selection"] == {
        "provider_runtime": ["cross_promo_funnel_v1"],
        "task_evidence_recovery": [
            "cross_promo_funnel_v1",
            "card_multifile_paired_v1",
        ],
        "release_candidate": list(SCENARIO_IDS),
    }
    assert all(item["expected_confirmation"] is False for item in manifest["scenarios"])
    assert len({item["prompt"] for item in manifest["scenarios"]}) == 3


def test_manifest_rejects_duplicate_scenario_identity(tmp_path: Path):
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    manifest["scenarios"].append(dict(manifest["scenarios"][0]))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid_scenario_manifest_id"):
        load_scenario_manifest(path)


def test_manifest_scenario_prompt_is_digestable_and_not_confirmation_driven():
    scenario = get_scenario("retention_descriptive_v1")

    assert "不做因果" in scenario["prompt"]
    assert scenario["expected_confirmation"] is False
    assert scenario["oracle"]["trailing_30d_zero_rows"] == 6


@pytest.mark.skipif(not DATA_DIR.is_dir(), reason="reference/test_doc not found")
@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_real_file_scenario_oracle_is_independent_bounded_and_green(
    scenario_id: str,
    tmp_path: Path,
):
    result = run_scenario_oracle(scenario_id=scenario_id, data_dir=DATA_DIR)

    assert result["contract_version"] == SCENARIO_ORACLE_VERSION
    assert result["scenario_id"] == scenario_id
    assert result["status"] == "PASS"
    assert result["fixture_digest"].startswith("sha256:")
    assert result["prompt_digest"].startswith("sha256:")
    assert result["oracle_digest"].startswith("sha256:")
    assert len(result["assertions"]) >= 4
    assert all(assertion["passed"] for assertion in result["assertions"])
    assert all("observed" in assertion for assertion in result["assertions"])
    assert all(set(item) == {"name", "sha256"} for item in result["fixture_files"])

    output = write_scenario_oracle(tmp_path / f"{scenario_id}.json", result)
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == result
    serialized = output.read_text(encoding="utf-8")
    assert str(DATA_DIR.resolve()) not in serialized
    assert "user_id" not in serialized


@pytest.mark.skipif(not DATA_DIR.is_dir(), reason="reference/test_doc not found")
def test_oracle_digest_changes_when_assertion_identity_changes():
    retention = run_scenario_oracle(
        scenario_id="retention_descriptive_v1",
        data_dir=DATA_DIR,
    )
    cross_promo = run_scenario_oracle(
        scenario_id="cross_promo_funnel_v1",
        data_dir=DATA_DIR,
    )

    assert retention["fixture_digest"] != cross_promo["fixture_digest"]
    assert retention["prompt_digest"] != cross_promo["prompt_digest"]
    assert retention["oracle_digest"] != cross_promo["oracle_digest"]
