"""Source contracts for reactive current-turn SSE rendering.

These fast guards target the object-ownership order that Alpine needs. They
do not replace the real-browser release gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")


def _method_block(start, end):
    return APP_JS[APP_JS.index(start) : APP_JS.index(end)]


def test_send_message_passes_current_reactive_turn():
    block = _method_block("async sendMessage()", "// --- Confirmation helpers ---")
    assert "this.turns = [...state.turns];" in block
    assert "const turn = this.turns[this.turns.length - 1];" in block
    assert block.index("this.turns = [...state.turns];") < block.index(
        "const turn = this.turns[this.turns.length - 1];"
    )
    assert "await this._processSSE(response, turn, state, sseSessionId);" in block


def test_current_turn_mutations_publish_reactive_array_updates():
    block = _method_block("_handleEvent(type, data, turn, state, sessionId)", "// --- Helpers ---")
    assert "this._renderMessages()" not in block
    progress = block[block.index("case 'analysis_progress':") : block.index("case 'text_delta':")]
    text = block[block.index("case 'text_delta':") : block.index("case 'tool_call':")]
    expected = "if (isCurrentSession) this.turns = [...state.turns];"
    assert expected in progress
    assert expected in text


def test_resume_uses_reactive_new_turn():
    block = _method_block("async resumeConfirmation", "_submitConfirmation(turn)")
    assert "this.turns = [...state.turns];" in block
    assert "const newTurn = this.turns[this.turns.length - 1];" in block
    assert "await this._processSSE(response, newTurn" in block


def test_reactivity_contract_nodeid_is_collected():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "tests/test_web_sse_reactivity_contract.py",
            "-q",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "test_current_turn_mutations_publish_reactive_array_updates" in result.stdout
