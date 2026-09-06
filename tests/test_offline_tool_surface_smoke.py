"""Run the broad tool smoke in an isolated, zero-Provider process."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "testing" / "offline_tool_surface_smoke.py"


def test_offline_tool_surface_smoke() -> None:
    env = os.environ.copy()
    env.update({
        "API_BASE": "http://127.0.0.1:9",
        "API_KEY": "offline-tool-surface-no-provider",
        "GOLDEN_LIVE_SMOKE": "0",
    })

    completed = subprocess.run(
        [sys.executable, str(SMOKE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )

    output = f"{completed.stdout}\n{completed.stderr}"
    assert completed.returncode == 0, output
    assert "PASS: 104" in output
    assert "FAIL: 0" in output
