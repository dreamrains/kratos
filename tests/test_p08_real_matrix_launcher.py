"""Regression checks for the real-Provider P08 launcher controls."""
from __future__ import annotations

import importlib.util
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
