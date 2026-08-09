from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import data_agent

from data_agent.config import get_config
from data_agent.session.task_manager import task_manager
from scripts.run_analysis_release_gates import (
    build_isolated_runtime_environment,
    run_declared_deterministic_gates,
)


ROOT = Path(__file__).resolve().parents[1]


def _is_same_or_below(candidate: Path, protected: Path) -> bool:
    candidate = candidate.resolve()
    protected = protected.resolve()
    return candidate == protected or protected in candidate.parents


def _passing_harness() -> dict:
    return {
        "status": "PASS",
        "release_critical_ignored": [],
        "required_direct_runners": [],
        "reason_codes": [],
    }


def test_pytest_runtime_roots_are_isolated_from_interactive_checkout():
    cfg = get_config()
    workspace = cfg.workspace_resolved
    sessions = cfg.sessions_resolved
    tasks = task_manager.dir

    assert os.environ.get("DATA_AGENT_TEST_STATE_ROOT")
    assert not _is_same_or_below(workspace, ROOT / "workspace")
    assert not _is_same_or_below(sessions, ROOT / "sessions")
    assert _is_same_or_below(tasks, workspace)


def test_pytest_imports_application_from_current_checkout():
    imported_package = Path(data_agent.__file__).resolve()

    assert _is_same_or_below(imported_package, ROOT / "src")


def test_build_isolated_runtime_environment_rejects_interactive_roots(tmp_path):
    try:
        build_isolated_runtime_environment(
            repository_root=ROOT,
            state_root=ROOT,
            base_environment={},
        )
    except ValueError as exc:
        assert "interactive_runtime_state" in str(exc)
    else:
        raise AssertionError("interactive runtime roots must be rejected")

    environment, diagnostic = build_isolated_runtime_environment(
        repository_root=ROOT,
        state_root=tmp_path / "gate-state",
        base_environment={"EXISTING": "kept"},
    )

    assert diagnostic == {
        "name": "runtime_state_isolation",
        "status": "PASS",
        "state_isolated": True,
        "source_import_isolated": True,
        "source_root": str(ROOT / "src"),
    }
    assert environment["EXISTING"] == "kept"
    assert environment["DATA_AGENT_TEST_STATE_ROOT"]
    assert not _is_same_or_below(
        Path(environment["WORKSPACE_DIR"]), ROOT / "workspace"
    )
    assert not _is_same_or_below(
        Path(environment["SESSIONS_DIR"]), ROOT / "sessions"
    )


def test_release_gate_children_receive_isolated_runtime_roots(tmp_path):
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    report = run_declared_deterministic_gates(
        root=tmp_path,
        command_runner=fake_run,
        harness_result=_passing_harness(),
    )

    assert calls
    for _command, kwargs in calls:
        environment = kwargs["env"]
        assert environment["DATA_AGENT_TEST_STATE_ROOT"]
        assert environment["PYTHONPATH"].split(os.pathsep)[:3] == [
            str(tmp_path / "src"),
            str(tmp_path / "tests"),
            str(tmp_path),
        ]
        assert not _is_same_or_below(
            Path(environment["WORKSPACE_DIR"]), tmp_path / "workspace"
        )
        assert not _is_same_or_below(
            Path(environment["SESSIONS_DIR"]), tmp_path / "sessions"
        )

    isolation_checks = [
        check
        for check in report["gates"]["A"]["checks"]
        if check["name"] == "runtime_state_isolation"
    ]
    assert isolation_checks == [
        {
            "name": "runtime_state_isolation",
            "status": "PASS",
            "state_isolated": True,
            "source_import_isolated": True,
            "source_root": str(tmp_path / "src"),
        }
    ]


def test_isolated_child_task_write_cannot_touch_interactive_workspace(tmp_path):
    interactive_tasks = ROOT / "workspace" / "tasks"
    before = {
        path.relative_to(interactive_tasks).as_posix(): path.stat().st_mtime_ns
        for path in interactive_tasks.glob("**/*")
        if path.is_file()
    } if interactive_tasks.exists() else {}

    environment, _diagnostic = build_isolated_runtime_environment(
        repository_root=ROOT,
        state_root=tmp_path / "child-state",
        base_environment=os.environ.copy(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from data_agent.session.task_manager import task_manager; "
                "task_manager.create('isolated child', session_id='child'); "
                "print(task_manager.dir)"
            ),
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    isolated_tasks = Path(environment["WORKSPACE_DIR"]) / "tasks"
    assert list(isolated_tasks.glob("task_*.json"))
    assert str(isolated_tasks.resolve()) in completed.stdout.strip()
    after = {
        path.relative_to(interactive_tasks).as_posix(): path.stat().st_mtime_ns
        for path in interactive_tasks.glob("**/*")
        if path.is_file()
    } if interactive_tasks.exists() else {}
    assert after == before
