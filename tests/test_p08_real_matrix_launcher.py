"""Regression checks for the real-Provider P08 launcher controls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from data_agent.llm.request_policy import ONE_SHOT


def _launcher_module():
    path = Path(__file__).parents[1] / "scripts" / "testing" / "run_p08_real_matrix.py"
    spec = importlib.util.spec_from_file_location("p08_real_matrix_launcher", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_launcher_forces_one_physical_attempt_for_every_client():
    launcher = _launcher_module()

    class FakeClient:
        def __init__(self, *args, request_policy=None, **kwargs):
            self.request_policy = request_policy

    class FakeClientModule:
        LLMClient = FakeClient

    launcher._install_one_shot_request_policy(FakeClientModule)

    assert FakeClient().request_policy is ONE_SHOT
    assert FakeClient(request_policy=object()).request_policy is ONE_SHOT


def test_preflight_contract_freezes_complete_prompts_oracles_and_browser_protocol():
    launcher = _launcher_module()
    root = Path(__file__).parents[1]

    contract = launcher._frozen_matrix_contract(root, 5215)

    assert contract["matrix"] == ["M01", "M02", "M03", "M04", "M05", "M06"]
    assert contract["operator_protocol"]["browser"] == "Codex built-in browser / iab"
    assert contract["operator_protocol"]["service_port"] == 5215
    assert contract["matrix_plan"]["sha256"].startswith("sha256:")
    assert contract["contract_file"]["sha256"].startswith("sha256:")
    assert set(contract["scenario_inputs"]) == set(contract["matrix"])
    for scenario in contract["scenario_inputs"].values():
        assert scenario["prompts"]
        assert scenario["hard_oracles"]
        assert scenario["actions"]


def test_m02_contract_accepts_only_disclosed_receipt_bound_fitted_scenarios():
    launcher = _launcher_module()
    contract = launcher._frozen_matrix_contract(Path(__file__).parents[1], 5215)

    prompt = contract["scenario_inputs"]["M02"]["prompts"][0]
    oracles = "\n".join(contract["scenario_inputs"]["M02"]["hard_oracles"])

    assert "拟合情景" in prompt
    assert "R²" in prompt
    assert "未做留出验证/回测/外部验证" in prompt
    assert "host-recomputed" in oracles
    assert "D7=0.10" in oracles
    assert "unit/scale remains not_confirmed" in oracles
    assert "0.0005 on source raw scale" in oracles


def test_m04_contract_does_not_claim_unfrozen_failed_upload_rollback():
    launcher = _launcher_module()
    contract = launcher._frozen_matrix_contract(Path(__file__).parents[1], 5215)

    scenario = contract["scenario_inputs"]["M04"]
    assert "failed_v2_upload" not in scenario["actions"]
    assert not any("failed v2 upload" in oracle for oracle in scenario["hard_oracles"])


def test_preflight_stdout_is_ascii_safe_without_losing_unicode_content():
    launcher = _launcher_module()

    output = launcher._stdout_manifest("passed", {"label": "R² 拟合情景"})

    output.encode("ascii")
    assert json.loads(output) == {"preflight": "passed", "label": "R² 拟合情景"}
