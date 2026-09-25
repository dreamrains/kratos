"""Zero-call freeze and admission checks for the natural typed trial."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.testing import run_typed_trial_real as launcher


def test_launcher_direct_entrypoint_is_executable_without_provider_call():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "testing" / "run_typed_trial_real.py"),
         "--help"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "--preflight" in result.stdout and "--authorized" in result.stdout


def test_contract_freezes_two_ordered_m03_cases_without_unverified_totals():
    root = Path(__file__).parents[1]
    contract = launcher._contract(root)

    assert contract["matrix"] == ["M03-P", "M03-N"]
    assert contract["operator_protocol"]["browser"] == "Codex built-in browser / iab"
    assert all(len(case["fixtures"]) == 6 for case in contract["scenarios"].values())
    assert "cross-source total" in " ".join(contract["scenarios"]["M03-P"]["oracles"])
    assert "99 percent" in " ".join(contract["scenarios"]["M03-N"]["oracles"])


def test_preflight_is_zero_call_and_revalidation_rejects_changed_fixture(tmp_path, monkeypatch):
    root = tmp_path
    contract_path = root / launcher.CONTRACT
    contract_path.parent.mkdir(parents=True)
    contract_path.write_bytes((Path(__file__).parents[1] / launcher.CONTRACT).read_bytes())
    (root / "tmp").mkdir()
    monkeypatch.setattr(launcher, "_require_clean_source", lambda _root: None)
    monkeypatch.setattr(launcher, "_git", lambda _root, *_args: "fixed-commit")
    monkeypatch.setattr("data_agent.config.get_config", lambda: SimpleNamespace(
        model_id="test/model", api_base="https://example.test", api_key="present",
    ))

    run_dir = root / "tmp" / "natural"
    manifest = launcher.preflight(root, run_dir, 8771)

    assert manifest["source_commit"] == "fixed-commit"
    assert manifest["call_cap"] == 30 and manifest["output_cap_per_call"] == 65536
    assert len(manifest["fixture_digests"]) == 6
    assert set(manifest["scenario_digests"]) == {"M03-P", "M03-N"}
    assert not (run_dir / "provider-calls.jsonl").exists()
    assert launcher.revalidate(root, run_dir, 8771) == json.loads(
        (run_dir / "freeze.json").read_text(encoding="utf-8"),
    )
    (run_dir / "fixtures" / "F-SRC1.csv").write_text("tampered", encoding="utf-8")
    with pytest.raises(SystemExit, match="mismatch"):
        launcher.revalidate(root, run_dir, 8771)
