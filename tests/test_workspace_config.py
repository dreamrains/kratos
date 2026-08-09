from pathlib import Path

import pytest
from pydantic import ValidationError

from data_agent.config import AgentConfig


def test_workspace_dir_defaults_to_workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = AgentConfig(_env_file=None)
    assert cfg.workspace_resolved == tmp_path / "workspace"


def test_workspace_dir_prefers_workspace_env(tmp_path, monkeypatch):
    target = tmp_path / "custom_workspace"
    monkeypatch.setenv("WORKSPACE_DIR", str(target))
    cfg = AgentConfig(_env_file=None)
    assert cfg.workspace_resolved == target


def test_project_dir_is_development_fallback(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy_project"
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("PROJECT_DIR", str(legacy))
    cfg = AgentConfig(_env_file=None)
    assert cfg.workspace_resolved == legacy


def test_measurement_binding_mode_defaults_to_soft():
    cfg = AgentConfig(_env_file=None)

    assert cfg.measurement_evidence_binding_mode == "soft"


@pytest.mark.parametrize("mode", ["shadow", "soft", "enforced"])
def test_measurement_binding_modes_are_valid(mode):
    cfg = AgentConfig(
        MEASUREMENT_EVIDENCE_BINDING_MODE=mode,
        _env_file=None,
    )

    assert cfg.measurement_evidence_binding_mode == mode


def test_measurement_binding_mode_has_no_off_value():
    with pytest.raises(ValidationError):
        AgentConfig(
            MEASUREMENT_EVIDENCE_BINDING_MODE="off",
            _env_file=None,
        )
