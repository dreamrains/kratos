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
    assert "let isCurrentSession = this._ownsSessionState(sessionId, state);" in block
    migration = block[block.index("case 'turn_start':") : block.index("case 'llm_call_start':")]
    assert "isCurrentSession = this._ownsSessionState(sessionId, state);" in migration
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
    assert text.index(expected) < text.index("this._scrollToBottom(")


def test_resume_uses_reactive_new_turn():
    block = _method_block("async resumeConfirmation", "_submitConfirmation(turn)")
    ownership = "const ownsOrigin = () => this._ownsSessionState(sseSessionId, state);"
    publish = "this.turns = [...state.turns];"
    synchronize = "state.turns = this.turns;"
    selected = "const newTurn = this.turns[this.turns.length - 1];"
    process = "await this._processSSE(response, newTurn, state, sseSessionId);"
    assert ownership in block
    assert block.index(publish) < block.index(synchronize) < block.index(selected) < block.index(process)


def test_session_ownership_helper_requires_expected_id_and_originating_state():
    helper = _method_block("_ownsSessionState(sessionId, state)", "// Save current reactive")
    assert "this.currentSessionId === sessionId" in helper
    assert "this._sessionStates[sessionId] === state" in helper

    send = _method_block("async sendMessage()", "// --- Confirmation helpers ---")
    assert "this._ownsSessionState(this.currentSessionId, state)" in send


def test_background_migrated_send_cannot_publish_or_save_active_session_state():
    block = _method_block("async sendMessage()", "// --- Confirmation helpers ---")
    finally_block = block[block.index("} finally {") :]
    ownership = (
        "const ownsOrigin = () => "
        "this._ownsSessionState(this.currentSessionId, state);"
    )
    assert ownership in block
    assert "const isOriginCurrent" not in finally_block
    assert finally_block.index("if (ownsOrigin())") < finally_block.index(
        "this.turns = [...state.turns];"
    )
    assert "ownsSession: ownsOrigin" in finally_block
    assert "this._queueMermaidRenderIfOwned(ownsOrigin);" in finally_block


def test_background_sse_side_effects_are_session_scoped():
    event_block = _method_block("_handleEvent(type, data, turn, state, sessionId)", "// --- Helpers ---")
    llm = event_block[
        event_block.index("case 'llm_call_start':") : event_block.index("case 'analysis_progress':")
    ]
    assert "if (isCurrentSession) {" in llm
    assert "this._startThinkingCycle(turn, sessionId, state);" in llm

    process = _method_block("async _processSSE(response, turn, state, sessionId)", "_handleEvent(type, data, turn, state, sessionId)")
    current_stream = (
        "const isCurrentStreamSession = () => "
        "this._ownsSessionState(effectiveSid, state);"
    )
    assert current_stream in process
    assert process.index("if (isCurrentStreamSession())") < process.index(
        "this.connectionError ="
    )
    assert process.count(
        "this._stopThinkingCycle(effectiveSid, state, turn);"
    ) == 2

    artifacts = _method_block("async loadSessionArtifacts", "async deleteArtifactFromModal")
    assignment = "this.sessionArtifacts = artifacts;"
    assert "const ownsTarget = () => this._ownsSessionState(sessionId, state);" in artifacts
    assert artifacts.index("if (ownsTarget()) {") < artifacts.index(assignment)
    assert "if (isCurrentSession) this.loadSessionArtifacts(sessionId);" in event_block


def test_turn_end_trust_and_mermaid_use_exact_origin_ownership():
    block = _method_block(
        "_handleEvent(type, data, turn, state, sessionId)",
        "// --- Helpers ---",
    )
    turn_end = block[block.index("case 'turn_end':") : block.index("case 'error':")]
    assert "this._stopThinkingCycle(sessionId, state, turn);" in turn_end
    assert "this.loadTrustView(sessionId, state);" in turn_end
    assert "this._queueMermaidRenderIfOwned(" in turn_end

    trust = _method_block("async loadTrustView", "multifileWorkbench()")
    assert "this._ownsSessionState(sessionId, state)" in trust


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
