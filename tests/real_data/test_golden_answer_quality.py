from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_agent.agent.golden_answer_runner import (
    load_golden_manifest,
    GoldenManifestError,
)

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = next(
    (
        p
        for p in (
            WORKTREE_ROOT / "reference" / "test_doc",
            WORKTREE_ROOT.parents[1] / "reference" / "test_doc",
        )
        if p.is_dir()
    ),
    None,
)
MANIFEST = WORKTREE_ROOT / "tests" / "real_data" / "golden_answer_manifest.json"


def test_load_golden_manifest_valid():
    manifest = load_golden_manifest(MANIFEST)
    assert manifest["schema_version"] == "golden_answer_scenarios.v1"
    ids = [s["id"] for s in manifest["scenarios"]]
    assert ids == [
        "savings_card_business_overview",
        "game_a_multimetric_synthesis",
        "game_b_retention_depth",
        "unrelated_files_false_join_prevention",
    ]
    for scenario in manifest["scenarios"]:
        assert scenario["business_question"]
        assert isinstance(scenario["required_files"], list) and scenario["required_files"]


def test_load_golden_manifest_rejects_missing_schema(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    with pytest.raises(GoldenManifestError):
        load_golden_manifest(bad)


@pytest.mark.skipif(DATA_DIR is None, reason="reference/test_doc not found")
def test_golden_manifest_files_exist():
    manifest = load_golden_manifest(MANIFEST)
    for scenario in manifest["scenarios"]:
        for name in scenario["required_files"]:
            assert (DATA_DIR / name).is_file(), f"missing {name} for {scenario['id']}"
