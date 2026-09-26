"""Regression checks for the real-Provider P08 launcher controls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_agent.llm.request_policy import ONE_SHOT


def _launcher_module():
    path = Path(__file__).parents[1] / "scripts" / "testing" / "run_p08_real_matrix.py"
    spec = importlib.util.spec_from_file_location("p08_real_matrix_launcher", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _http_driver_module():
    path = Path(__file__).parents[1] / "scripts" / "testing" / "run_p08_http_matrix.py"
    spec = importlib.util.spec_from_file_location("p08_http_matrix_driver", path)
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


def test_existing_provider_ledger_records_nonstream_usage_without_content(tmp_path):
    launcher = _launcher_module()
    path = tmp_path / "provider-calls.jsonl"
    ledger = launcher.ProviderLedger(path, 1)
    completion = ledger.wrap(lambda **_kwargs: SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=21, completion_tokens=7, total_tokens=28),
    ))
    completion(model="test-model", stream=False)
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [item["event"] for item in events] == ["started", "dispatched"]
    assert events[-1]["prompt_tokens"] == 21
    assert events[-1]["completion_tokens"] == 7
    assert events[-1]["total_tokens"] == 28


def test_preflight_contract_freezes_complete_prompts_oracles_and_http_protocol():
    launcher = _launcher_module()
    root = Path(__file__).parents[1]

    contract = launcher._frozen_matrix_contract(root, 5215)

    assert contract["matrix"] == ["M01", "M02", "M03", "M04", "M05", "M06"]
    assert contract["operator_protocol"]["control_route"] == "local_http_api"
    assert contract["http_driver_digest"].startswith("sha256:")
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


def test_m04_contract_freezes_two_ordered_upload_stages_in_one_session():
    launcher = _launcher_module()
    contract = launcher._frozen_matrix_contract(Path(__file__).parents[1], 5215)

    assert contract["scenario_inputs"]["M04"]["upload_stages"] == [
        {"before_prompt": 1, "fixtures": ["M04-hyp-v1.csv"]},
        {"before_prompt": 2, "fixtures": ["M04-hyp-v2.csv"],
         "same_session": True, "after_first_turn_terminal": True},
    ]
    assert "M04 alone uses two ordered upload stages" in contract["operator_protocol"]["upload_policy"]


def test_preflight_stdout_is_ascii_safe_without_losing_unicode_content():
    launcher = _launcher_module()

    output = launcher._stdout_manifest("passed", {"label": "R² 拟合情景"})

    output.encode("ascii")
    assert json.loads(output) == {"preflight": "passed", "label": "R² 拟合情景"}


def test_http_driver_requires_one_terminal_matching_persisted_state(monkeypatch):
    driver = _http_driver_module()

    class Response:
        headers = {"X-Data-Agent-Session-Id": "s1"}

        def __init__(self, event_lines):
            self.event_lines = event_lines

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self, **_kwargs):
            return self.event_lines

    lines = ["event: turn_start", "data: {}", "", "event: turn_end",
             'data: {"status":"completed"}', ""]
    monkeypatch.setattr(driver.requests, "post", lambda *_args, **_kwargs: Response(lines))
    monkeypatch.setattr(driver, "_request_json", lambda *_args, **_kwargs: {"status": "completed"})
    result = driver._stream("http://127.0.0.1:1", "/api/chat", {"message": "fixed"})
    assert result["session_id"] == "s1" and result["terminal"] == "completed"

    resumed = driver._stream("http://127.0.0.1:1", "/api/chat/resume", {"session_id": "s1"})
    assert resumed["session_id"] == "s1" and resumed["terminal"] == "completed"

    monkeypatch.setattr(driver.requests, "post", lambda *_args, **_kwargs: Response(lines + lines[3:]))
    with pytest.raises(RuntimeError, match="turn_end integrity failure"):
        driver._stream("http://127.0.0.1:1", "/api/chat", {"message": "fixed"})


def test_http_driver_confirmation_uses_visible_option_value():
    driver = _http_driver_module()
    options = [{"label": "A. 仅代金券成本", "value": "voucher_only"},
               {"label": "B. 代金券成本 + 渠道成本", "value": "voucher_and_channel"}]
    assert driver._option_value(options, "B. 代金券成本 + 渠道成本") == "voucher_and_channel"
    assert driver._option_value(options, "C. 无此选项") is None


def test_http_driver_accepts_frozen_b_cost_scope_with_natural_option_label():
    driver = _http_driver_module()
    options = [
        {"label": "口径A：净收益 = 促销收入 − 代金券成本", "value": "voucher_only"},
        {"label": "口径B：净收益 = 促销收入 − 代金券成本 − 渠道成本",
         "value": "voucher_and_channel"},
    ]
    assert driver._option_value(options, "B. 代金券成本 + 渠道成本") == "voucher_and_channel"
