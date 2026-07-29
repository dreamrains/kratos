"""Regression tests for release-gate runner collection integrity."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_pytest_collect_only(*paths: str) -> subprocess.CompletedProcess[str]:
    """Collect the specified tests using this checkout's interpreter context."""
    environment = os.environ.copy()
    source_path = str(ROOT / "src")
    tests_path = str(ROOT / "tests")
    environment["PYTHONPATH"] = os.pathsep.join((source_path, tests_path))
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", *paths, "-q"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_release_critical_web_tests_are_collected():
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert '"test_sse_reactivity.py"' not in conftest
    assert '"test_web_gui.py"' not in conftest
    assert (ROOT / "tests" / "test_web_sse_contract.py").is_file()


def test_release_critical_web_nodeids_are_in_collect_only():
    result = run_pytest_collect_only("tests/test_web_sse_contract.py")
    assert result.returncode == 0, result.stderr
    assert "test_real_chat_route_streams_progress_before_text_and_turn_end" in result.stdout
