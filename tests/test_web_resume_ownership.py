"""Behavior-level races for confirmation resume session ownership."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

NODE_RACE = r"""
const fs = require('fs');
const vm = require('vm');

vm.runInThisContext(
  fs.readFileSync('src/data_agent/web/static/js/app.js', 'utf8'),
  { filename: 'app.js' },
);

global.requestAnimationFrame = () => {};

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function setup() {
  const app = chatApp();
  const actualLoadSessions = app.loadSessions.bind(app);
  const actualLoadTrustView = app.loadTrustView.bind(app);
  const actualProcessSSE = app._processSSE.bind(app);
  const actualScrollToBottom = app._scrollToBottom.bind(app);
  const confirmation = {
    confirmation_id: 'confirmation-a',
    version: 3,
    _idempotencyKey: 'resume-a',
  };
  const turnA = {
    role: 'assistant',
    content: 'A suspended',
    confirmation: { ...confirmation },
    isThinking: false,
  };
  const stateA = app._emptySessionState();
  stateA.turns = [turnA];
  const stateB = app._emptySessionState();
  stateB.turns = [{ role: 'assistant', content: 'B visible' }];
  app._sessionStates = { A: stateA, B: stateB };
  app.currentSessionId = 'A';
  app.turns = stateA.turns;
  app.isLoading = true;
  app.connectionError = '';

  const loadSessionOptions = [];
  app.loadSessions = async (options = {}) => {
    loadSessionOptions.push(options);
    if (!options.preserveConnectionError) app.connectionError = '';
  };
  app.loadTasks = async () => {};
  let scrolls = 0;
  let mermaidRefreshes = 0;
  app._scrollToBottom = () => { scrolls += 1; };
  global.requestAnimationFrame = () => { mermaidRefreshes += 1; };
  let processed = null;
  app._processSSE = async (_response, turn, state, sessionId) => {
    processed = { turn, state, sessionId };
    return sessionId;
  };

  return {
    app,
    confirmation,
    stateA,
    stateB,
    actualLoadSessions,
    actualLoadTrustView,
    actualProcessSSE,
    actualScrollToBottom,
    loadSessionOptions,
    get scrolls() { return scrolls; },
    get mermaidRefreshes() { return mermaidRefreshes; },
    get processed() { return processed; },
  };
}

function switchOwnershipToB(ctx) {
  ctx.app.currentSessionId = 'B';
  ctx.app.turns = ctx.stateB.turns;
  ctx.app.isLoading = false;
  ctx.app.connectionError = 'B warning';
}

async function runSuccess(background) {
  const ctx = setup();
  const originalTurns = ctx.app.turns;
  const gate = deferred();
  global.fetch = () => gate.promise;
  const pending = ctx.app.resumeConfirmation('approve', ctx.confirmation);
  await Promise.resolve();
  if (background) switchOwnershipToB(ctx);
  gate.resolve({ ok: true });
  await pending;
  const activeTurns = background ? ctx.stateB.turns : ctx.stateA.turns;
  return {
    activeTurnsPreserved: ctx.app.turns === activeTurns,
    foregroundPublishedNewArray: !background && ctx.app.turns !== originalTurns,
    originatingStateSynchronized: ctx.stateA.turns === ctx.app.turns,
    processedReactiveTurn:
      !!ctx.processed
      && ctx.processed.turn === ctx.stateA.turns[ctx.stateA.turns.length - 1],
    activeError: ctx.app.connectionError,
    preserveConnectionError:
      !!ctx.loadSessionOptions[0]?.preserveConnectionError,
    scrolls: ctx.scrolls,
    mermaidRefreshes: ctx.mermaidRefreshes,
  };
}

async function runHttpFailure() {
  const ctx = setup();
  const gate = deferred();
  global.fetch = () => gate.promise;
  const pending = ctx.app.resumeConfirmation('approve', ctx.confirmation);
  await Promise.resolve();
  switchOwnershipToB(ctx);
  gate.resolve({
    ok: false,
    status: 409,
    statusText: 'Conflict',
    json: async () => ({ error: 'stale confirmation' }),
  });
  await pending;
  return {
    activeTurnsPreserved: ctx.app.turns === ctx.stateB.turns,
    activeError: ctx.app.connectionError,
    originError: ctx.stateA.turns[0].confirmation._error,
    preserveConnectionError:
      !!ctx.loadSessionOptions[0]?.preserveConnectionError,
  };
}

async function runFetchException() {
  const ctx = setup();
  const gate = deferred();
  global.fetch = () => gate.promise;
  const pending = ctx.app.resumeConfirmation('approve', ctx.confirmation);
  await Promise.resolve();
  switchOwnershipToB(ctx);
  gate.reject(new Error('resume offline'));
  await pending;
  return {
    activeTurnsPreserved: ctx.app.turns === ctx.stateB.turns,
    activeError: ctx.app.connectionError,
    originContent: ctx.stateA.turns[0].content,
    preserveConnectionError:
      !!ctx.loadSessionOptions[0]?.preserveConnectionError,
  };
}

async function runFinallyAwaitRace(kind) {
  const ctx = setup();
  const sessionsStarted = deferred();
  const sessionJson = deferred();
  const loadOptions = [];
  ctx.app.loadSessions = async (options = {}) => {
    loadOptions.push(options);
    return ctx.actualLoadSessions(options);
  };
  global.fetch = (url) => {
    if (url === '/api/sessions') {
      sessionsStarted.resolve();
      return Promise.resolve({
        ok: true,
        json: () => sessionJson.promise,
      });
    }
    if (url === '/api/chat/resume' || url === '/api/chat') {
      return Promise.resolve({ ok: true });
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  let pending;
  if (kind === 'resume') {
    pending = ctx.app.resumeConfirmation('approve', ctx.confirmation);
  } else {
    ctx.app.isLoading = false;
    ctx.app.inputText = 'analyze';
    pending = ctx.app.sendMessage();
  }

  await sessionsStarted.promise;
  switchOwnershipToB(ctx);
  sessionJson.resolve([{ session_id: 'A' }, { session_id: 'B' }]);
  await pending;
  return {
    activeTurnsPreserved: ctx.app.turns === ctx.stateB.turns,
    activeError: ctx.app.connectionError,
    mermaidRefreshes: ctx.mermaidRefreshes,
    passedOwnershipGuard: typeof loadOptions[0]?.ownsSession === 'function',
  };
}

function sseResponseGate() {
  const gate = deferred();
  let delivered = false;
  return {
    gate,
    response: {
      body: {
        getReader() {
          return {
            read() {
              if (!delivered) {
                delivered = true;
                return gate.promise;
              }
              return Promise.resolve({ done: true });
            },
          };
        },
      },
    },
  };
}

function encodeEvents(events) {
  const frames = events.map(({ type, data }) => (
    `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
  )).join('');
  return new TextEncoder().encode(frames);
}

async function runReplacedStateSse() {
  const ctx = setup();
  const oldState = ctx.stateA;
  const oldTurn = oldState.turns[0];
  const replacement = ctx.app._emptySessionState();
  replacement.turns = [{ role: 'assistant', content: 'replacement visible' }];
  let thinkingStarts = 0;
  let thinkingStops = 0;
  let trustLoads = 0;
  ctx.app._startThinkingCycle = () => { thinkingStarts += 1; };
  const stopThinkingCycle = ctx.app._stopThinkingCycle.bind(ctx.app);
  ctx.app._stopThinkingCycle = (...args) => {
    const timerBefore = ctx.app._thinkingTimer;
    stopThinkingCycle(...args);
    if (timerBefore && ctx.app._thinkingTimer !== timerBefore) {
      thinkingStops += 1;
    }
  };
  ctx.app.loadTrustView = () => { trustLoads += 1; };
  ctx.app._debouncedLoadTasks = () => {};
  ctx.app.isLoading = true;
  ctx.app.tokenPct = 11;
  ctx.app.connectionError = 'replacement warning';

  const stream = sseResponseGate();
  const pending = ctx.actualProcessSSE(stream.response, oldTurn, oldState, 'A');
  ctx.app._sessionStates.A = replacement;
  ctx.app.turns = replacement.turns;
  stream.gate.resolve({
    done: false,
    value: encodeEvents([
      { type: 'llm_call_start', data: { pct: 50 } },
      {
        type: 'analysis_progress',
        data: { code: 'analysis_plan_ready', label: 'Planning', status: 'running' },
      },
      { type: 'text_delta', data: { text: ' stale delta' } },
      {
        type: 'tool_call',
        data: { tool_call_id: 'tool-old', name: 'old_tool', arguments: {} },
      },
      {
        type: 'tool_result',
        data: { tool_call_id: 'tool-old', duration_ms: 2, web: { summary: 'done' } },
      },
      { type: 'turn_end', data: { pct: 90 } },
    ]),
  });
  await pending;
  return {
    activeTurnsPreserved: ctx.app.turns === replacement.turns,
    activeContent: ctx.app.turns[0].content,
    activeError: ctx.app.connectionError,
    activeLoading: ctx.app.isLoading,
    activeTokenPct: ctx.app.tokenPct,
    oldContent: oldTurn.content,
    oldStepStatus: oldState.activeSteps[0]?.status,
    replacementStepCount: replacement.activeSteps.length,
    scrolls: ctx.scrolls,
    thinkingStarts,
    thinkingStops,
    trustLoads,
  };
}

async function runPendingMigrationSse() {
  const ctx = setup();
  const state = ctx.app._emptySessionState();
  const turn = { role: 'assistant', content: '', isThinking: true };
  state.turns = [turn];
  ctx.app._sessionStates = { _pending_: state };
  ctx.app.currentSessionId = '_pending_';
  ctx.app.turns = state.turns;
  ctx.app.isLoading = true;
  ctx.app._debouncedLoadTasks = () => {};
  ctx.app._stopThinkingCycle = () => {};

  const stream = sseResponseGate();
  const pending = ctx.actualProcessSSE(
    stream.response,
    turn,
    state,
    '_pending_',
  );
  stream.gate.resolve({
    done: false,
    value: encodeEvents([
      { type: 'turn_start', data: { session_id: 'real-session' } },
      { type: 'text_delta', data: { text: 'visible delta' } },
      { type: 'turn_end', data: {} },
    ]),
  });
  await pending;
  return {
    currentSessionId: ctx.app.currentSessionId,
    migratedStateOwned: ctx.app._sessionStates['real-session'] === state,
    pendingStateRemoved: !ctx.app._sessionStates._pending_,
    visibleContent: ctx.app.turns[0].content,
    scrolls: ctx.scrolls,
  };
}

async function runReplacedPendingMigrationSse() {
  const ctx = setup();
  const oldState = ctx.app._emptySessionState();
  const oldTurn = { role: 'assistant', content: 'old pending' };
  oldState.turns = [oldTurn];
  const replacement = ctx.app._emptySessionState();
  replacement.turns = [{ role: 'assistant', content: 'new pending visible' }];
  ctx.app._sessionStates = { _pending_: oldState };
  ctx.app.currentSessionId = '_pending_';
  ctx.app.turns = oldState.turns;
  ctx.app._debouncedLoadTasks = () => {};
  ctx.app._stopThinkingCycle = () => {};

  const stream = sseResponseGate();
  const pending = ctx.actualProcessSSE(
    stream.response,
    oldTurn,
    oldState,
    '_pending_',
  );
  ctx.app._sessionStates._pending_ = replacement;
  ctx.app.turns = replacement.turns;
  stream.gate.resolve({
    done: false,
    value: encodeEvents([
      { type: 'turn_start', data: { session_id: 'stale-real-session' } },
      { type: 'text_delta', data: { text: ' stale delta' } },
      { type: 'turn_end', data: {} },
    ]),
  });
  await pending;
  return {
    currentSessionId: ctx.app.currentSessionId,
    replacementStillPending:
      ctx.app._sessionStates._pending_ === replacement,
    staleRealSessionAbsent:
      !ctx.app._sessionStates['stale-real-session'],
    visibleContent: ctx.app.turns[0].content,
    oldContent: oldTurn.content,
    scrolls: ctx.scrolls,
  };
}

async function runQueuedMermaidRace(kind) {
  const ctx = setup();
  const callbacks = [];
  let renders = 0;
  global.requestAnimationFrame = (callback) => { callbacks.push(callback); };
  global.document = {
    getElementById: () => ({ id: 'messages-container' }),
  };
  ctx.app._renderMermaidInElement = () => { renders += 1; };
  global.fetch = (url) => {
    if (url === '/api/chat' || url === '/api/chat/resume') {
      return Promise.resolve({ ok: true });
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  if (kind === 'resume') {
    await ctx.app.resumeConfirmation('approve', ctx.confirmation);
  } else {
    ctx.app.isLoading = false;
    ctx.app.inputText = 'analyze';
    await ctx.app.sendMessage();
  }
  switchOwnershipToB(ctx);
  for (const callback of callbacks) callback();
  return {
    queuedCallbacks: callbacks.length,
    renders,
    activeTurnsPreserved: ctx.app.turns === ctx.stateB.turns,
  };
}

function doneResponse() {
  return {
    body: {
      getReader() {
        return {
          read: async () => ({ done: true }),
        };
      },
    },
  };
}

async function runOldTimerTerminal(withNewTimer) {
  const ctx = setup();
  let nextTimer = 0;
  const cleared = [];
  global.setInterval = () => ({ timer: ++nextTimer });
  global.clearInterval = (timer) => { cleared.push(timer.timer); };
  ctx.app._debouncedLoadTasks = () => {};
  const turnA = ctx.stateA.turns[0];
  ctx.app._handleEvent(
    'llm_call_start',
    {},
    turnA,
    ctx.stateA,
    'A',
  );
  const timerA = ctx.app._thinkingTimer;

  switchOwnershipToB(ctx);
  let timerB = null;
  const turnB = ctx.stateB.turns[0];
  if (withNewTimer) {
    ctx.app._handleEvent(
      'llm_call_start',
      {},
      turnB,
      ctx.stateB,
      'B',
    );
    timerB = ctx.app._thinkingTimer;
  }
  ctx.app._handleEvent(
    'turn_end',
    {},
    turnA,
    ctx.stateA,
    'A',
  );
  return {
    timerAWasCreated: !!timerA,
    timerCleared: ctx.app._thinkingTimer === null,
    bTimerRetained: !!timerB && ctx.app._thinkingTimer === timerB,
    bOwnerRetained:
      !!ctx.app._thinkingTimerOwner
      && ctx.app._thinkingTimerOwner.sessionId === 'B'
      && ctx.app._thinkingTimerOwner.state === ctx.stateB
      && ctx.app._thinkingTimerOwner.turn === turnB,
    cleared,
  };
}

function runQueuedScrollRace() {
  const ctx = setup();
  const callbacks = [];
  const container = { scrollTop: 0, scrollHeight: 80 };
  global.requestAnimationFrame = (callback) => { callbacks.push(callback); };
  global.document = {
    getElementById: () => container,
  };
  const ownsA = () => ctx.app._ownsSessionState('A', ctx.stateA);
  ctx.actualScrollToBottom(ownsA);
  switchOwnershipToB(ctx);
  for (const callback of callbacks) callback();
  return {
    queuedCallbacks: callbacks.length,
    scrollTop: container.scrollTop,
  };
}

function runObserverMermaidRace() {
  const ctx = setup();
  const callbacks = [];
  const container = { id: 'messages-container' };
  let observerCallback = null;
  let renders = 0;
  global.requestAnimationFrame = (callback) => { callbacks.push(callback); };
  global.document = {
    getElementById: () => container,
  };
  global.MutationObserver = class {
    constructor(callback) {
      observerCallback = callback;
    }
    observe() {}
  };
  ctx.app.isLoading = false;
  ctx.app._renderMermaidInElement = () => { renders += 1; };
  ctx.app._setupRenderObserver();
  observerCallback([{
    addedNodes: [{
      nodeType: 1,
      querySelector: () => ({ className: 'mermaid' }),
      matches: () => false,
    }],
  }]);
  switchOwnershipToB(ctx);
  for (const callback of callbacks) callback();
  return {
    queuedCallbacks: callbacks.length,
    renders,
  };
}

async function runSameIdTrustReplacement() {
  const ctx = setup();
  const gate = deferred();
  global.fetch = () => Promise.resolve({
    ok: true,
    json: () => gate.promise,
  });
  const pending = ctx.actualLoadTrustView('A', ctx.stateA);
  const replacement = ctx.app._emptySessionState();
  replacement.turns = [{ role: 'assistant', content: 'replacement' }];
  ctx.app._sessionStates.A = replacement;
  ctx.app.turns = replacement.turns;
  ctx.app.trustView = { owner: 'replacement' };
  ctx.app.trustLoading = false;
  ctx.app.trustError = 'replacement warning';
  gate.resolve({ owner: 'stale A' });
  await pending;
  return {
    trustView: ctx.app.trustView,
    trustLoading: ctx.app.trustLoading,
    trustError: ctx.app.trustError,
  };
}

async function runCrossSessionTrustSwitch() {
  const ctx = setup();
  const gate = deferred();
  global.fetch = () => Promise.resolve({
    ok: true,
    json: () => gate.promise,
  });
  const pending = ctx.actualLoadTrustView('A', ctx.stateA);
  switchOwnershipToB(ctx);
  ctx.app.trustView = { owner: 'B' };
  ctx.app.trustLoading = false;
  ctx.app.trustError = 'B warning';
  gate.resolve({ owner: 'stale A' });
  await pending;
  return {
    trustView: ctx.app.trustView,
    trustLoading: ctx.app.trustLoading,
    trustError: ctx.app.trustError,
  };
}

async function runSwitchSessionResponseAfterOwnershipChange() {
  const app = chatApp();
  const stateA = app._emptySessionState();
  const stateB = app._emptySessionState();
  stateB.turns = [{ role: 'assistant', content: 'B visible' }];
  app._sessionStates = { A: stateA, B: stateB };
  app.currentSessionId = 'B';
  app.turns = stateB.turns;
  app.activeProjectName = 'project-b';
  app.tokenPct = 17;
  app.tokenSupported = true;
  app.connectionError = 'B warning';

  const sessionJson = deferred();
  let sessionFetches = 0;
  global.fetch = (url) => {
    if (url !== '/api/sessions/A') {
      throw new Error(`unexpected fetch ${url}`);
    }
    sessionFetches += 1;
    if (sessionFetches === 1) {
      return Promise.resolve({
        ok: true,
        json: () => sessionJson.promise,
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ active_confirmation: null }),
    });
  };
  app.loadAnalysisState = async () => {};
  app.loadTrustView = async () => {};
  app.loadSessionArtifacts = async () => {};
  app.loadTasks = async () => {};
  app._scrollToBottom = () => {};

  const pending = app.switchSession('A');
  await Promise.resolve();
  app.currentSessionId = 'B';
  app.turns = stateB.turns;
  app.activeProjectName = 'project-b';
  app.tokenPct = 17;
  app.tokenSupported = true;
  app.connectionError = 'B warning';
  sessionJson.resolve({
    messages: [{ role: 'assistant', content: 'A stale response' }],
    project_name: 'project-a',
    token_usage: { pct: 88 },
  });
  await pending;
  return {
    currentSessionId: app.currentSessionId,
    activeTurnsPreserved: app.turns === stateB.turns,
    activeContent: app.turns[0].content,
    activeProjectName: app.activeProjectName,
    activeTokenPct: app.tokenPct,
    activeConnectionError: app.connectionError,
    backgroundStateHydrated: stateA.turns[0]?.content,
  };
}

async function runSameIdAnalysisReplacement() {
  const app = chatApp();
  const stateA = app._emptySessionState();
  app._sessionStates = { A: stateA };
  app.currentSessionId = 'A';
  app.analysisState = { owner: 'initial' };
  const gate = deferred();
  global.fetch = () => Promise.resolve({
    ok: true,
    json: () => gate.promise,
  });
  const pending = app.loadAnalysisState('A', stateA);
  const replacement = app._emptySessionState();
  app._sessionStates.A = replacement;
  app.analysisState = { owner: 'replacement' };
  gate.resolve({ owner: 'stale A' });
  await pending;
  return app.analysisState;
}

async function runSameIdArtifactsReplacement() {
  const app = chatApp();
  const stateA = app._emptySessionState();
  app._sessionStates = { A: stateA };
  app.currentSessionId = 'A';
  app.sessionArtifacts = [{ owner: 'initial' }];
  app.turns = stateA.turns;
  const gate = deferred();
  global.fetch = () => Promise.resolve({
    ok: true,
    json: () => gate.promise,
  });
  const pending = app.loadSessionArtifacts('A', stateA);
  const replacement = app._emptySessionState();
  app._sessionStates.A = replacement;
  app.turns = replacement.turns;
  app.sessionArtifacts = [{ owner: 'replacement' }];
  gate.resolve([{ owner: 'stale A' }]);
  await pending;
  return app.sessionArtifacts;
}

(async () => {
  const results = {
    backgroundSuccess: await runSuccess(true),
    backgroundHttpFailure: await runHttpFailure(),
    backgroundFetchException: await runFetchException(),
    foregroundSuccess: await runSuccess(false),
    resumeFinallyAwaitRace: await runFinallyAwaitRace('resume'),
    sendFinallyAwaitRace: await runFinallyAwaitRace('send'),
    replacedStateSse: await runReplacedStateSse(),
    pendingMigrationSse: await runPendingMigrationSse(),
    replacedPendingMigrationSse: await runReplacedPendingMigrationSse(),
    resumeQueuedMermaidRace: await runQueuedMermaidRace('resume'),
    sendQueuedMermaidRace: await runQueuedMermaidRace('send'),
    oldTimerTerminal: await runOldTimerTerminal(false),
    oldTerminalWithBTimer: await runOldTimerTerminal(true),
    queuedScrollRace: runQueuedScrollRace(),
    observerMermaidRace: runObserverMermaidRace(),
    sameIdTrustReplacement: await runSameIdTrustReplacement(),
    crossSessionTrustSwitch: await runCrossSessionTrustSwitch(),
    switchSessionOwnershipRace: await runSwitchSessionResponseAfterOwnershipChange(),
    sameIdAnalysisReplacement: await runSameIdAnalysisReplacement(),
    sameIdArtifactsReplacement: await runSameIdArtifactsReplacement(),
  };
  process.stdout.write(JSON.stringify(results));
})().catch((error) => {
  process.stderr.write(error.stack || String(error));
  process.exitCode = 1;
});
"""


@pytest.fixture(scope="module")
def resume_race_results():
    result = subprocess.run(
        ["node", "-e", NODE_RACE],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_background_resume_success_keeps_active_session_ui(resume_race_results):
    result = resume_race_results["backgroundSuccess"]
    assert result == {
        "activeTurnsPreserved": True,
        "foregroundPublishedNewArray": False,
        "originatingStateSynchronized": False,
        "processedReactiveTurn": True,
        "activeError": "B warning",
        "preserveConnectionError": True,
        "scrolls": 0,
        "mermaidRefreshes": 0,
    }


def test_background_resume_http_failure_keeps_active_session_ui(resume_race_results):
    result = resume_race_results["backgroundHttpFailure"]
    assert result == {
        "activeTurnsPreserved": True,
        "activeError": "B warning",
        "originError": "stale confirmation",
        "preserveConnectionError": True,
    }


def test_background_resume_fetch_exception_keeps_active_session_ui(
    resume_race_results,
):
    result = resume_race_results["backgroundFetchException"]
    assert result["activeTurnsPreserved"] is True
    assert result["activeError"] == "B warning"
    assert "resume offline" in result["originContent"]
    assert result["preserveConnectionError"] is True


def test_foreground_resume_publishes_reactive_turn(resume_race_results):
    result = resume_race_results["foregroundSuccess"]
    assert result == {
        "activeTurnsPreserved": True,
        "foregroundPublishedNewArray": True,
        "originatingStateSynchronized": True,
        "processedReactiveTurn": True,
        "activeError": "",
        "preserveConnectionError": False,
        "scrolls": 1,
        "mermaidRefreshes": 1,
    }


@pytest.mark.parametrize(
    "scenario",
    ["resumeFinallyAwaitRace", "sendFinallyAwaitRace"],
)
def test_session_switch_during_session_list_refresh_keeps_active_ui(
    resume_race_results,
    scenario,
):
    assert resume_race_results[scenario] == {
        "activeTurnsPreserved": True,
        "activeError": "B warning",
        "mermaidRefreshes": 0,
        "passedOwnershipGuard": True,
    }


def test_same_session_id_with_replaced_state_cannot_publish_stale_sse(
    resume_race_results,
):
    assert resume_race_results["replacedStateSse"] == {
        "activeTurnsPreserved": True,
        "activeContent": "replacement visible",
        "activeError": "replacement warning",
        "activeLoading": True,
        "activeTokenPct": 11,
        "oldContent": "A suspended stale delta",
        "oldStepStatus": "done",
        "replacementStepCount": 0,
        "scrolls": 0,
        "thinkingStarts": 0,
        "thinkingStops": 0,
        "trustLoads": 0,
    }


def test_pending_turn_start_migration_retains_exact_state_ownership(
    resume_race_results,
):
    assert resume_race_results["pendingMigrationSse"] == {
        "currentSessionId": "real-session",
        "migratedStateOwned": True,
        "pendingStateRemoved": True,
        "visibleContent": "visible delta",
        "scrolls": 2,
    }


def test_stale_pending_turn_start_cannot_migrate_replacement_state(
    resume_race_results,
):
    assert resume_race_results["replacedPendingMigrationSse"] == {
        "currentSessionId": "_pending_",
        "replacementStillPending": True,
        "staleRealSessionAbsent": True,
        "visibleContent": "new pending visible",
        "oldContent": "old pending stale delta",
        "scrolls": 0,
    }


@pytest.mark.parametrize(
    "scenario",
    ["resumeQueuedMermaidRace", "sendQueuedMermaidRace"],
)
def test_queued_mermaid_callback_rechecks_session_ownership(
    resume_race_results,
    scenario,
):
    assert resume_race_results[scenario] == {
        "queuedCallbacks": 1,
        "renders": 0,
        "activeTurnsPreserved": True,
    }


def test_old_stream_terminal_clears_its_orphaned_thinking_timer(
    resume_race_results,
):
    assert resume_race_results["oldTimerTerminal"] == {
        "timerAWasCreated": True,
        "timerCleared": True,
        "bTimerRetained": False,
        "bOwnerRetained": False,
        "cleared": [1],
    }


def test_old_stream_terminal_does_not_clear_new_session_timer(
    resume_race_results,
):
    assert resume_race_results["oldTerminalWithBTimer"] == {
        "timerAWasCreated": True,
        "timerCleared": False,
        "bTimerRetained": True,
        "bOwnerRetained": True,
        "cleared": [1],
    }


def test_queued_scroll_callback_rechecks_session_ownership(resume_race_results):
    assert resume_race_results["queuedScrollRace"] == {
        "queuedCallbacks": 1,
        "scrollTop": 0,
    }


def test_observer_mermaid_callback_rechecks_session_ownership(
    resume_race_results,
):
    assert resume_race_results["observerMermaidRace"] == {
        "queuedCallbacks": 1,
        "renders": 0,
    }


def test_same_id_replacement_rejects_stale_trust_result(resume_race_results):
    assert resume_race_results["sameIdTrustReplacement"] == {
        "trustView": {"owner": "replacement"},
        "trustLoading": False,
        "trustError": "replacement warning",
    }


def test_cross_session_switch_rejects_stale_trust_result(resume_race_results):
    assert resume_race_results["crossSessionTrustSwitch"] == {
        "trustView": {"owner": "B"},
        "trustLoading": False,
        "trustError": "B warning",
    }


def test_switch_session_response_cannot_overwrite_new_active_session(
    resume_race_results,
):
    assert resume_race_results["switchSessionOwnershipRace"] == {
        "currentSessionId": "B",
        "activeTurnsPreserved": True,
        "activeContent": "B visible",
        "activeProjectName": "project-b",
        "activeTokenPct": 17,
        "activeConnectionError": "B warning",
        "backgroundStateHydrated": "A stale response",
    }


def test_same_id_state_replacement_rejects_stale_analysis_result(
    resume_race_results,
):
    assert resume_race_results["sameIdAnalysisReplacement"] == {
        "owner": "replacement"
    }


def test_same_id_state_replacement_rejects_stale_artifact_result(
    resume_race_results,
):
    assert resume_race_results["sameIdArtifactsReplacement"] == [
        {"owner": "replacement"}
    ]
