from pathlib import Path

from data_agent.config import AgentConfig


def test_workspace_dir_defaults_to_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("PROJECT_DIR", raising=False)
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
