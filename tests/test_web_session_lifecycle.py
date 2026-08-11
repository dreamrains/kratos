from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def _run_node(body: str) -> dict:
    script = rf"""
const fs = require('fs');
const vm = require('vm');
vm.runInThisContext(
  fs.readFileSync('src/data_agent/web/static/js/app.js', 'utf8'),
  {{ filename: 'app.js' }},
);
global.document = {{
  addEventListener() {{}},
  getElementById() {{ return null; }},
  hidden: false,
}};
global.requestAnimationFrame = callback => callback();
const values = new Map();
global.localStorage = {{
  getItem(key) {{ return values.has(key) ? values.get(key) : null; }},
  setItem(key, value) {{ values.set(key, String(value)); }},
  removeItem(key) {{ values.delete(key); }},
}};
{body}
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_init_restores_the_remembered_session_and_its_unified_views():
    result = _run_node(r"""
(async () => {
  const app = chatApp();
  localStorage.setItem('data-agent.current-session', 'session-b');
  app.loadSessions = async () => {
    app.sessions = [
      { session_id: 'session-a' },
      { session_id: 'session-b' },
    ];
  };
  app.loadProjects = async () => {};
  app.loadCapabilities = async () => {};
  app.loadModelInfo = async () => {};
  app.loadTasks = async () => {};
  app._setupRenderObserver = () => {};
  app._updateTaskPollInterval = () => {};
  const restored = [];
  app.switchSession = async sessionId => {
    restored.push(sessionId);
    app.currentSessionId = sessionId;
  };

  await app.init();
  process.stdout.write(JSON.stringify({ restored, current: app.currentSessionId }));
})().catch(error => { console.error(error); process.exit(1); });
""")

    assert result == {"restored": ["session-b"], "current": "session-b"}


def test_init_restores_latest_session_when_no_remembered_session_exists():
    result = _run_node(r"""
(async () => {
  const app = chatApp();
  app.loadSessions = async () => {
    app.sessions = [
      { session_id: 'latest-session' },
      { session_id: 'older-session' },
    ];
  };
  app.loadProjects = async () => {};
  app.loadCapabilities = async () => {};
  app.loadModelInfo = async () => {};
  app.loadTasks = async () => {};
  app._setupRenderObserver = () => {};
  app._updateTaskPollInterval = () => {};
  const restored = [];
  app.switchSession = async sessionId => {
    restored.push(sessionId);
    app.currentSessionId = sessionId;
  };

  await app.init();
  process.stdout.write(JSON.stringify({ restored, current: app.currentSessionId }));
})().catch(error => { console.error(error); process.exit(1); });
""")

    assert result == {
        "restored": ["latest-session"],
        "current": "latest-session",
    }


def test_new_session_identity_immediately_binds_workbench_and_persists_choice():
    result = _run_node(r"""
(() => {
  const app = chatApp();
  const state = app._emptySessionState();
  const turn = {
    role: 'assistant', content: '', toolCalls: [], artifacts: [],
    confirmation: null, isThinking: true,
  };
  state.turns = [turn];
  app._sessionStates = { _pending_: state };
  app.currentSessionId = '_pending_';
  const loads = [];
  app.loadAnalysisState = (sid, owner) => loads.push(['analysis', sid, owner === state]);
  app.loadTrustView = (sid, owner) => loads.push(['workbench', sid, owner === state]);
  app.loadSessionArtifacts = (sid, owner) => loads.push(['artifacts', sid, owner === state]);
  app.loadTasks = () => loads.push(['tasks', 'real-session', true]);
  app.loadSessions = () => loads.push(['sessions', 'real-session', true]);

  app._handleEvent(
    'turn_start',
    { session_id: 'real-session', turn_id: 'turn-1' },
    turn,
    state,
    '_pending_',
  );
  process.stdout.write(JSON.stringify({
    current: app.currentSessionId,
    remembered: localStorage.getItem('data-agent.current-session'),
    loads,
  }));
})();
""")

    assert result == {
        "current": "real-session",
        "remembered": "real-session",
        "loads": [
            ["analysis", "real-session", True],
            ["workbench", "real-session", True],
            ["artifacts", "real-session", True],
            ["tasks", "real-session", True],
            ["sessions", "real-session", True],
        ],
    }


def test_suspended_turn_keeps_the_real_question_instead_of_empty_reply_state():
    result = _run_node(r"""
(() => {
  const app = chatApp();
  const state = app._emptySessionState();
  const turn = {
    role: 'assistant', content: '', toolCalls: [], artifacts: [],
    confirmation: null, isThinking: true,
  };
  state.turns = [turn];
  app._sessionStates = { A: state };
  app.currentSessionId = 'A';
  app.turns = state.turns;
  app._handleEvent('suspended', {
    confirmation_id: 'confirmation-1',
    version: 1,
    question: '是否仅进行描述性分析？',
    options: [{ label: '是', value: 'descriptive_only' }],
  }, turn, state, 'A');
  process.stdout.write(JSON.stringify({
    question: turn.confirmation.question,
    options: turn.confirmation.options,
    emptyReplyVisible: !turn.content && !turn.isThinking
      && turn.artifacts.length === 0 && !turn.confirmation,
  }));
})();
""")

    assert result == {
        "question": "是否仅进行描述性分析？",
        "options": [{"label": "是", "value": "descriptive_only"}],
        "emptyReplyVisible": False,
    }


def test_runtime_error_is_status_state_not_raw_answer_markdown():
    result = _run_node(r"""
(() => {
  const app = chatApp();
  const state = app._emptySessionState();
  const turn = {
    role: 'assistant', content: '', toolCalls: [], artifacts: [],
    confirmation: null, isThinking: true,
  };
  state.turns = [turn];
  app._sessionStates = { A: state };
  app.currentSessionId = 'A';
  app.turns = state.turns;
  app._handleEvent(
    'error',
    { message: 'secret provider stack detail' },
    turn,
    state,
    'A',
  );
  process.stdout.write(JSON.stringify({
    content: turn.content,
    runtimeError: turn.runtimeError,
    connectionError: app.connectionError,
  }));
})();
""")

    assert "secret provider stack detail" not in result["content"]
    assert "分析未能完成" in result["content"]
    assert result["runtimeError"] == "secret provider stack detail"
    assert result["connectionError"] == "secret provider stack detail"


def test_task_progress_moves_from_zero_to_complete_for_one_session():
    result = _run_node(r"""
(() => {
  const app = chatApp();
  app.currentSessionId = 'A';
  app.tasks = [
    { id: 1, session_id: 'A', status: 'in_progress', task_kind: 'plan_task' },
    { id: 2, session_id: 'A', status: 'pending', task_kind: 'plan_task' },
    { id: 3, session_id: 'B', status: 'completed', task_kind: 'plan_task' },
  ];
  const initial = app.taskProgress;
  app.tasks[0].status = 'completed';
  app.tasks[1].status = 'completed';
  const completed = app.taskProgress;
  process.stdout.write(JSON.stringify({ initial, completed }));
})();
""")

    assert result == {"initial": "0/2", "completed": "2/2"}


def test_background_task_response_cannot_replace_foreground_session_tasks():
    result = _run_node(r"""
(async () => {
  const app = chatApp();
  const stateA = app._emptySessionState();
  const stateB = app._emptySessionState();
  app._sessionStates = { A: stateA, B: stateB };
  app.currentSessionId = 'A';
  let releaseResponse;
  global.fetch = () => new Promise(resolve => { releaseResponse = resolve; });

  const oldLoad = app.loadTasks('A', stateA);
  app.currentSessionId = 'B';
  app.tasks = [{ id: 2, session_id: 'B', status: 'pending' }];
  releaseResponse({
    json: async () => [{ id: 1, session_id: 'A', status: 'completed' }],
  });
  await oldLoad;

  process.stdout.write(JSON.stringify({
    current: app.currentSessionId,
    taskSessions: app.tasks.map(task => task.session_id),
  }));
})().catch(error => { console.error(error); process.exit(1); });
""")

    assert result == {"current": "B", "taskSessions": ["B"]}
