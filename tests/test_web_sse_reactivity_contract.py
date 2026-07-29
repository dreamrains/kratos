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
    publish = "this.turns = [...state.turns];"
    synchronize = "state.turns = this.turns;"
    selected = "const turn = this.turns[this.turns.length - 1];"
    process = "await this._processSSE(response, turn, state, sseSessionId);"
    assert block.index(publish) < block.index(synchronize) < block.index(selected) < block.index(process)


def test_current_turn_mutations_publish_reactive_array_updates():
    block = _method_block("_handleEvent(type, data, turn, state, sessionId)", "// --- Helpers ---")
    assert "this._renderMessages()" not in block
    expected = "if (isCurrentSession) this.turns = [...state.turns];"
    events = (
        ("analysis_progress", "text_delta"),
        ("text_delta", "tool_call"),
        ("llm_call_start", "analysis_progress"),
        ("tool_call", "tool_result"),
        ("tool_result", "task_update"),
    )
    for event, following in events:
        case = block[
            block.index(f"case '{event}':") : block.index(f"case '{following}':")
        ]
        assert expected in case, event

    text = block[block.index("case 'text_delta':") : block.index("case 'tool_call':")]
    assert text.index(expected) < text.index("this._scrollToBottom();")


def test_resume_uses_reactive_new_turn():
    block = _method_block("async resumeConfirmation", "_submitConfirmation(turn)")
    publish = "this.turns = [...state.turns];"
    synchronize = "state.turns = this.turns;"
    selected = "const newTurn = this.turns[this.turns.length - 1];"
    process = "await this._processSSE(response, newTurn, state, sseSessionId);"
    assert block.index(publish) < block.index(synchronize) < block.index(selected) < block.index(process)


def test_background_migrated_send_cannot_publish_or_save_active_session_state():
    block = _method_block("async sendMessage()", "// --- Confirmation helpers ---")
    finally_block = block[block.index("} finally {") :]
    current_origin = "const isOriginCurrent = this._sessionStates[this.currentSessionId] === state;"
    assert current_origin in finally_block
    guard = finally_block[finally_block.index(current_origin) :]
    assert guard.index("if (isOriginCurrent)") < guard.index("this.turns = [...state.turns];")
    assert guard.index("if (isOriginCurrent)") < guard.index("this._saveCurrentState();")
    assert guard.index("if (isOriginCurrent)") < guard.index("requestAnimationFrame")


def test_background_sse_side_effects_are_session_scoped():
    event_block = _method_block("_handleEvent(type, data, turn, state, sessionId)", "// --- Helpers ---")
    llm = event_block[
        event_block.index("case 'llm_call_start':") : event_block.index("case 'analysis_progress':")
    ]
    assert "if (isCurrentSession) this._startThinkingCycle(turn);" in llm

    process = _method_block("async _processSSE(response, turn, state, sessionId)", "_handleEvent(type, data, turn, state, sessionId)")
    current_stream = "const isCurrentStreamSession = () => ("
    assert current_stream in process
    for side_effect in ("this.connectionError =", "this._stopThinkingCycle();"):
        assert process.index("if (isCurrentStreamSession())") < process.index(side_effect)

    artifacts = _method_block("async loadSessionArtifacts", "async deleteArtifactFromModal")
    assignment = "this.sessionArtifacts = artifacts;"
    assert artifacts.index("if (sessionId === this.currentSessionId) {") < artifacts.index(assignment)
    assert "if (isCurrentSession) this.loadSessionArtifacts(sessionId);" in event_block


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
