from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "reference" / "test_doc"
SCRIPT = ROOT / "scripts" / "run_reference_data_acceptance.py"


@pytest.mark.skipif(not DATA_DIR.is_dir(), reason="reference/test_doc not found")
def test_reference_data_acceptance_covers_all_files_and_semantic_risks(tmp_path: Path) -> None:
    output = tmp_path / "reference-data-acceptance.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--data-dir",
            str(DATA_DIR),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["contract"] == "reference_data_acceptance.v1"
    assert result["status"] == "passed"
    assert result["file_count"] == 9
    assert all(item["passed"] for item in result["checks"])
    check_ids = {item["id"] for item in result["checks"]}
    assert {
        "game_a_shared_population_metrics_match",
        "published_game_a_formulas_match_with_rounding",
        "cross_promotion_numeric_conversion_is_explicit",
        "savings_card_duplicates_are_observable",
        "coupon_used_order_price_identity",
        "row_independence_violation_is_blocked",
        "paired_user_level_before_after_analysis_succeeds",
        "source_workbooks_unchanged",
    } <= check_ids
    warning_ids = {item["id"] for item in result["warnings"]}
    assert {
        "retention_right_censoring_candidate",
        "cross_promotion_quality_issues",
        "savings_card_duplicate_rows",
    } <= warning_ids
