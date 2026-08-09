"""Pytest configuration and fail-safe mutable runtime isolation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src"
for _candidate in reversed((_SOURCE_ROOT, _REPOSITORY_ROOT)):
    _candidate_text = str(_candidate)
    if _candidate_text in sys.path:
        sys.path.remove(_candidate_text)
    sys.path.insert(0, _candidate_text)

collect_ignore = [
    "test_tools_comprehensive.py",
]


@pytest.fixture(autouse=True)
def isolate_mutable_runtime_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep every collected test away from interactive workspace/session state.

    The application has module-level configuration and task-manager singletons.
    Environment-only isolation is therefore insufficient after collection has
    imported those modules.  Install both an isolated configuration authority
    and an isolated task directory for the duration of each test, while also
    exporting the roots so child processes inherit the same safety boundary.
    """

    state_root = (tmp_path / "runtime-state").resolve()
    workspace_root = state_root / "workspace"
    sessions_root = state_root / "sessions"
    workspace_root.mkdir(parents=True, exist_ok=True)
    sessions_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_AGENT_TEST_STATE_ROOT", str(state_root))
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace_root))
    monkeypatch.setenv("SESSIONS_DIR", str(sessions_root))

    from data_agent import config as config_module
    from data_agent.config import AgentConfig
    from data_agent.session.task_manager import task_manager

    original_config = config_module._config
    original_task_dir = task_manager._dir
    original_next_id = task_manager._next_id_val
    original_run_coordinator = task_manager._analysis_run_coordinator_instance
    original_projection_flag = task_manager._applying_analysis_run_projection

    config_module._config = AgentConfig(
        WORKSPACE_DIR=workspace_root,
        SESSIONS_DIR=sessions_root,
        _env_file=None,
    )
    task_manager._dir = workspace_root / "tasks"
    task_manager._next_id_val = 0
    task_manager._analysis_run_coordinator_instance = None
    task_manager._applying_analysis_run_projection = False

    try:
        yield
    finally:
        task_manager._dir = original_task_dir
        task_manager._next_id_val = original_next_id
        task_manager._analysis_run_coordinator_instance = original_run_coordinator
        task_manager._applying_analysis_run_projection = original_projection_flag
        config_module._config = original_config
