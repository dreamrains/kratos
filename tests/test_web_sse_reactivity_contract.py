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
INDEX_HTML = (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")

NODE_SPLIT_FRAME = r"""
const fs = require('fs');
const vm = require('vm');

vm.runInThisContext(
  fs.readFileSync('src/data_agent/web/static/js/app.js', 'utf8'),
  { filename: 'app.js' },
);

global.requestAnimationFrame = (callback) => callback();

(async () => {
  const app = chatApp();
  const state = app._emptySessionState();
  const turn = {
    role: 'assistant', content: '', toolCalls: [], artifacts: [],
    confirmation: null, isThinking: true,
  };
  state.turns = [turn];
  state.isLoading = true;
  app._sessionStates = { A: state };
  app.currentSessionId = 'A';
  app.turns = state.turns;
  app.isLoading = true;
  app._debouncedLoadTasks = () => {};
  app.loadTrustView = async () => {};
  app._scrollToBottom = () => {};
  app._queueMermaidRenderIfOwned = () => {};
  app._stopThinkingCycle = () => {};

  const observed = [];
  const actualHandle = app._handleEvent.bind(app);
  app._handleEvent = (...args) => {
    observed.push(args[0]);
    return actualHandle(...args);
  };
  app._yieldAfterVisibleSSEMutation = async () => { observed.push('paint'); };

  const encoder = new TextEncoder();
  const chunks = [
    encoder.encode('event: text_delta\n'),
    encoder.encode('data: {"text":"first"}\n\nevent: turn_end\n'),
    encoder.encode('data: {"status":"completed"}\n\n'),
  ];
  let index = 0;
  const response = {
    body: {
      getReader() {
        return {
          async read() {
            if (index >= chunks.length) return { done: true, value: undefined };
            return { done: false, value: chunks[index++] };
          },
        };
      },
    },
  };

  await app._processSSE(response, turn, state, 'A');
  process.stdout.write(JSON.stringify({ content: turn.content, observed }));
})().catch((error) => {
  process.stderr.write(error.stack || String(error));
  process.exitCode = 1;
});
"""

NODE_UI_CONFIRMATION = r"""
const fs = require('fs');
const vm = require('vm');
vm.runInThisContext(
  fs.readFileSync('src/data_agent/web/static/js/app.js', 'utf8'),
  { filename: 'app.js' },
);

(async () => {
  const app = chatApp();
  const acceptedPromise = app._confirmAction('stop now');
  const opened = { ...app.confirmDialog };
  app._resolveUiConfirmation(true);
  const accepted = await acceptedPromise;
  const cancelledPromise = app._confirmAction('delete later');
  app._resolveUiConfirmation(false);
  const cancelled = await cancelledPromise;
  process.stdout.write(JSON.stringify({ opened, accepted, cancelled, closed: app.confirmDialog }));
})().catch((error) => {
  process.stderr.write(error.stack || String(error));
  process.exitCode = 1;
});
"""


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


def test_analysis_progress_refreshes_the_task_projection():
    block = _method_block("_handleEvent(type, data, turn, state, sessionId)", "// --- Helpers ---")
    progress = block[
        block.index("case 'analysis_progress':") : block.index("case 'text_delta':")
    ]
    assert "this._debouncedLoadTasks();" in progress


def test_sse_parser_preserves_frames_across_network_chunks_and_yields_before_terminal():
    result = subprocess.run(
        ["node", "-e", NODE_SPLIT_FRAME],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = __import__("json").loads(result.stdout)
    assert payload == {
        "content": "first",
        "observed": ["text_delta", "paint", "turn_end"],
    }


def test_app_confirmation_is_explicit_and_does_not_use_native_confirm():
    assert "confirm(" not in APP_JS
    assert 'x-show="confirmDialog.show"' in INDEX_HTML
    assert '@click="_resolveUiConfirmation(false)"' in INDEX_HTML
    assert '@click="_resolveUiConfirmation(true)"' in INDEX_HTML

    result = subprocess.run(
        ["node", "-e", NODE_UI_CONFIRMATION],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = __import__("json").loads(result.stdout)
    assert payload == {
        "opened": {"show": True, "message": "stop now"},
        "accepted": True,
        "cancelled": False,
        "closed": {"show": False, "message": ""},
    }


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
