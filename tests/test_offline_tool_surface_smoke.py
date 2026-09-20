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
        # This process imports and executes the full ML/plotting tool surface.
        # A cold Windows run is normally ~80s on the acceptance host, leaving
        # the former 90s limit vulnerable to scheduler noise while all 104
        # assertions still progress. Keep a finite bound without making a
        # healthy cold-cache run flaky.
        timeout=180,
        check=False,
    )

    output = f"{completed.stdout}\n{completed.stderr}"
    assert completed.returncode == 0, output
    assert "PASS: 104" in output
    assert "FAIL: 0" in output
