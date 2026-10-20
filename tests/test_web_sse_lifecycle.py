from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src" / "data_agent" / "web" / "static" / "js" / "app.js"


NODE_CONTRACT = r"""
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const appPath = process.argv[2];
const scenario = process.argv[3];
let fetchImpl = async () => { throw new Error('unexpected fetch'); };

const documentStub = {
  hidden: false,
  addEventListener() {},
  getElementById() { return null; },
};
const windowStub = {
  location: { href: 'http://localhost/' },
  history: { replaceState() {} },
};
const context = {
  console,
  TextDecoder,
  TextEncoder,
  Blob,
  crypto: require('crypto').webcrypto,
  URL,
  clearInterval,
  clearTimeout,
  document: documentStub,
  fetch: (...args) => fetchImpl(...args),
  requestAnimationFrame: callback => callback(),
  setInterval,
  setTimeout,
  window: windowStub,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(appPath, 'utf8') + '\nthis.__chatApp = chatApp;', context);

const encoder = new TextEncoder();

function makeApp() {
  const app = context.__chatApp();
  app._syncSessionUrl = () => {};
  app._scrollToBottom = () => {};
  app._renderMermaidInElement = () => {};
  app._stopThinkingCycle = () => {};
  app._debouncedLoadTasks = () => {};
  app.loadSessions = async () => {};
  app.loadTasks = async () => {};
  app.loadAnalysisState = async () => {};
  app.loadSessionArtifacts = async () => {};
  return app;
}

function streamResponse(chunks, sessionId = 'session-a') {
  const queue = chunks.map(chunk => typeof chunk === 'string' ? encoder.encode(chunk) : chunk);
  let index = 0;
  return {
    ok: true,
    status: 200,
    headers: { get: name => name === 'X-Data-Agent-Session-Id' ? sessionId : null },
    body: {
      getReader() {
        return {
          async read() {
            if (index < queue.length) return { done: false, value: queue[index++] };
            return { done: true, value: undefined };
          },
        };
      },
    },
    async json() { return {}; },
  };
}

function jsonResponse(payload) {
  return {
    ok: true,
    status: 200,
    async json() { return payload; },
  };
}

const completeSSE = [
  'event: turn_start\ndata: {"session_id":"session-a"}\n\n' +
  'event: text_delta\ndata: {"text":"done"}\n\n' +
  'event: turn_end\ndata: {"session_id":"session-a","status":"completed"}\n\n',
];

async function normalChatUsesOneCompletionRefresh() {
  const app = makeApp();
  const trustCalls = [];
  app.inputText = 'analyze';
  app.loadTrustView = async sessionId => { trustCalls.push(sessionId); };
  fetchImpl = async url => {
    assert.strictEqual(url, '/api/chat');
    return streamResponse(completeSSE);
  };

  await app.sendMessage();

  assert.strictEqual(app.currentSessionId, 'session-a');
  assert.strictEqual(app.isLoading, false);
  assert.deepStrictEqual(trustCalls, ['session-a']);
}

async function uploadedFileReferencesAreAddedExactlyOnce() {
  const app = makeApp();
  let requestBody = null;
  app.inputText = '分析这两个文件\n分析文件: M01-sales.csv';
  app.uploadedFiles = [
    {upload_id:'upload-1', filename:'M01-sales.csv'},
    {upload_id:'upload-2', filename:'M01-costs.csv'},
  ];
  app.loadTrustView = async () => {};
  fetchImpl = async (url, options) => {
    assert.strictEqual(url, '/api/chat');
    requestBody = JSON.parse(options.body);
    return streamResponse(completeSSE);
  };

  await app.sendMessage();

  const userText = app._sessionStates['session-a'].turns[0].content;
  for (const text of [requestBody.message, userText]) {
    assert.strictEqual((text.match(/^分析文件: M01-sales\.csv$/gm) || []).length, 1);
    assert.strictEqual((text.match(/^分析文件: M01-costs\.csv$/gm) || []).length, 1);
  }
  assert.deepStrictEqual(requestBody.uploads, [
    {upload_id:'upload-1', filename:'M01-sales.csv'},
    {upload_id:'upload-2', filename:'M01-costs.csv'},
  ]);
  assert.deepStrictEqual(app.uploadedFiles, []);
}

async function confirmationResumeUsesCompletionRefresh() {
  const app = makeApp();
  const trustCalls = [];
  const confirmation = {
    confirmation_id: 'confirm-1',
    version: 1,
    _idempotencyKey: 'resume-key',
    _resuming: false,
    _error: '',
  };
  const state = app._emptySessionState();
  state.turns = [{
    role: 'assistant',
    content: '',
    confirmation,
    isThinking: false,
    toolCalls: [],
    artifacts: [],
  }];
  app.currentSessionId = 'session-a';
  app._sessionStates['session-a'] = state;
  app.turns = state.turns;
  app.loadTrustView = async sessionId => { trustCalls.push(sessionId); };
  const originalProcessSSE = app._processSSE.bind(app);
  app._processSSE = async (...args) => {
    assert.strictEqual(app.isLoading, true);
    assert.strictEqual(state.isLoading, true);
    return originalProcessSSE(...args);
  };
  fetchImpl = async url => {
    assert.strictEqual(url, '/api/chat/resume');
    return streamResponse(completeSSE, null);
  };

  await app.resumeConfirmation('continue', confirmation);

  assert.strictEqual(state._resuming, false);
  assert.strictEqual(app.isLoading, false);
  assert.deepStrictEqual(trustCalls, ['session-a']);
  assert.strictEqual(
    state.turns.filter(turn => turn.role === 'assistant' && !turn.content && !turn.confirmation && !turn.isThinking).length,
    0,
  );
}

async function persistedConfirmationProtocolIsReconstructedAsFriendlyAnswer() {
  const app = makeApp();
  const turns = app._reconstructTurns([
    { role: 'user', content: '请选择拟合方法' },
    {
      role: 'user',
      content: '<confirmation_response confirmation_id="confirm-1">\nOriginal question: choose\nUser answered: confirm_method\n</confirmation_response>',
    },
    { role: 'assistant', content: '已继续分析' },
  ]);

  assert.strictEqual(turns.length, 3);
  assert.strictEqual(turns[1].content, 'confirm_method');
  assert.strictEqual(turns[1].isConfirmationResponse, true);
  assert.strictEqual(turns[1].content.includes('<confirmation_response'), false);
}

async function chunkedSSEPreservesEventStateAndFlushesEOF() {
  const app = makeApp();
  app.loadTrustView = async () => {};
  const state = app._emptySessionState();
  const turn = { role: 'assistant', content: '', isThinking: true, isResponding: true, toolCalls: [], artifacts: [] };
  const eventTypes = [];
  const originalHandleEvent = app._handleEvent.bind(app);
  app.currentSessionId = 'session-a';
  app._sessionStates['session-a'] = state;
  app._handleEvent = (...args) => {
    eventTypes.push(args[0]);
    return originalHandleEvent(...args);
  };
  const payload = encoder.encode(
    'event: turn_start\ndata: {"session_id":"session-a"}\n\n' +
    'event: text_delta\ndata: {"text":"分块完成"}\n\n' +
    'event: turn_end\ndata: {"session_id":"session-a","status":"completed"}'
  );
  const oneByteChunks = Array.from(payload, byte => Uint8Array.of(byte));

  const effectiveSessionId = await app._processSSE(
    streamResponse(oneByteChunks), turn, state, 'session-a'
  );

  assert.strictEqual(effectiveSessionId, 'session-a');
  assert.deepStrictEqual(eventTypes, ['turn_start', 'text_delta', 'turn_end']);
  assert.strictEqual(turn.content, '分块完成');
  assert.strictEqual(turn.isThinking, false);
  assert.strictEqual(turn.isResponding, false);
}

async function switchingSessionDoesNotProjectBackgroundCompletion() {
  const app = makeApp();
  const trustCalls = [];
  let releaseSecondRead;
  let markSecondReadStarted;
  const secondReadStarted = new Promise(resolve => { markSecondReadStarted = resolve; });
  const first = encoder.encode('event: turn_start\ndata: {"session_id":"session-a"}\n\n');
  const second = encoder.encode(
    'event: text_delta\ndata: {"text":"background done"}\n\n' +
    'event: turn_end\ndata: {"session_id":"session-a","status":"completed"}\n\n'
  );
  let readIndex = 0;
  const response = {
    ok: true,
    status: 200,
    headers: { get: name => name === 'X-Data-Agent-Session-Id' ? 'session-a' : null },
    body: {
      getReader() {
        return {
          async read() {
            readIndex += 1;
            if (readIndex === 1) return { done: false, value: first };
            if (readIndex === 2) {
              markSecondReadStarted();
              return new Promise(resolve => { releaseSecondRead = resolve; });
            }
            return { done: true, value: undefined };
          },
        };
      },
    },
    async json() { return {}; },
  };
  app.inputText = 'analyze in background';
  app.loadTrustView = async sessionId => { trustCalls.push(sessionId); };
  fetchImpl = async () => response;

  const sending = app.sendMessage();
  await secondReadStarted;
  const foregroundState = app._emptySessionState();
  foregroundState.turns = [{ role: 'user', content: 'foreground session' }];
  app._sessionStates['session-b'] = foregroundState;
  app.currentSessionId = 'session-b';
  app.turns = foregroundState.turns;
  releaseSecondRead({ done: false, value: second });
  await sending;

  assert.strictEqual(app.currentSessionId, 'session-b');
  assert.strictEqual(app.turns, foregroundState.turns);
  assert.strictEqual(app.turns[0].content, 'foreground session');
  assert.deepStrictEqual(trustCalls, []);
  assert.strictEqual(app._sessionStates['session-a'].isLoading, false);
}

async function staleTrustResponseCannotOverwriteNewerProjection() {
  const app = makeApp();
  const pending = [];
  app.currentSessionId = 'session-a';
  fetchImpl = async url => {
    assert.strictEqual(url, '/api/sessions/session-a/trust');
    return new Promise(resolve => { pending.push(resolve); });
  };
  const older = app.loadTrustView('session-a');
  const newer = app.loadTrustView('session-a');
  assert.strictEqual(pending.length, 2);

  pending[1](jsonResponse({ workbench: { verified_conclusions: [{ id: 'new' }] } }));
  await newer;
  pending[0](jsonResponse({ workbench: { verified_conclusions: [{ id: 'old' }] } }));
  await older;

  assert.strictEqual(app.trustView.workbench.verified_conclusions[0].id, 'new');
  assert.strictEqual(app.trustLoading, false);
}

async function executionNoticesSurviveReplayWithoutDuplication() {
  for (const status of ['failed', 'cancelled']) {
    const app = makeApp();
    const notice = status === 'failed' ? '**执行失败：** transport stopped' : '**已停止：** cancelled';
    app.inputText = 'analyze';
    app.loadTrustView = async () => {};
    fetchImpl = async () => streamResponse([
      'event: turn_start\ndata: {"session_id":"session-a"}\n\n' +
      'event: error\ndata: {"message":"transport stopped"}\n\n' +
      'event: turn_end\ndata: ' + JSON.stringify({session_id:'session-a',status,execution_notice:notice}) + '\n\n'
    ]);
    await app.sendMessage();
    const live = app.turns[app.turns.length - 1].content;
    const state = app._emptySessionState();
    state.turns = app._reconstructTurns([{role:'user',content:'analyze'}, {role:'assistant',content:notice}]);
    app._applyRunState('session-a', state, {status,notice});
    assert.strictEqual(state.turns[state.turns.length - 1].content, live);
    assert.strictEqual(live, notice);
    assert.strictEqual(state.isLoading, false);
  }
}

async function replyExportsHaveUniqueSessionOwnedFilenames() {
  const app = makeApp();
  app.currentSessionId = 'session-a';
  const downloads = [];
  documentStub.createElement = () => ({click() { downloads.push(this.download); }});
  fetchImpl = async (url, options) => {
    if (url.endsWith('/export-reply')) {
      assert.strictEqual(JSON.parse(options.body).content, 'retained result');
      return jsonResponse({artifact_path:'sessions/session-a/reports/reply.md'});
    }
    assert.strictEqual(url, '/api/files/sessions/session-a/reports/reply.md');
    return {ok:true, blob:async () => new Blob(['retained result with chart'])};
  };
  for (const format of ['markdown','html']) {
    await app.exportSingleReply({content:'retained result'}, format);
    await app.exportSingleReply({content:'retained result'}, format);
  }
  assert.strictEqual(new Set(downloads).size, 4);
  assert.ok(downloads.every(name => name.startsWith('reply-session-a-')));
  assert.ok(downloads.slice(0,2).every(name => name.endsWith('.md')));
  assert.ok(downloads.slice(2).every(name => name.endsWith('.html')));
}

async function terminalPublishesBeforeEOFAndOldEOFDoesNotUnlockNextRun() {
  for (const resumed of [false, true]) {
    const app = makeApp();
    const updates = [];
    app.loadTrustView = async sid => updates.push('trust:' + sid);
    app.loadSessions = async () => updates.push('sessions');
    app.loadAnalysisState = async () => updates.push('analysis');
    app.loadSessionArtifacts = async () => updates.push('artifacts');
    let releaseEOF, waiting;
    const waitingForEOF = new Promise(resolve => { waiting = resolve; });
    let index = 0;
    const response = streamResponse([]);
    response.body.getReader = () => ({
      async read() {
        if (index++ === 0) return {done:false,value:encoder.encode(completeSSE[0])};
        waiting();
        return new Promise(resolve => { releaseEOF = resolve; });
      },
      cancel() { throw new Error('must drain, never cancel to manufacture completion'); },
      releaseLock() {},
    });
    fetchImpl = async () => response;
    let sending;
    if (resumed) {
      app.currentSessionId = 'session-a';
      const state = app._getSessionState('session-a');
      const confirmation = {confirmation_id:'c',version:1};
      state.turns = [{role:'assistant',content:'',confirmation}];
      app.turns = state.turns;
      sending = app.resumeConfirmation('confirm_method', confirmation);
    } else {
      app.inputText = 'analyze';
      sending = app.sendMessage();
    }
    await waitingForEOF;
    assert.strictEqual(app.isLoading, false);
    assert.deepStrictEqual(updates.sort(), ['analysis','artifacts','sessions','trust:session-a']);
    const state = app._getSessionState('session-a');
    state.runGeneration += 1;
    state.runStatus = 'running';
    state.isLoading = true;
    state._resuming = true;
    app.isLoading = true;
    releaseEOF({done:true});
    await sending;
    assert.strictEqual(app.isLoading, true);
    assert.strictEqual(state._resuming, true);
    assert.strictEqual(updates.length, 4);
  }
}

async function silentSSEFallsBackToDurableRunState() {
  const app = makeApp();
  app._sseSilenceTimeoutMs = 5;
  app.inputText = 'analyze';
  let cancelled = false;
  let runStateChecks = 0;
  const response = streamResponse([]);
  response.body.getReader = () => ({
    read() { return new Promise(() => {}); },
    async cancel() { cancelled = true; },
    releaseLock() {},
  });
  fetchImpl = async url => {
    if (url === '/api/chat') return response;
    if (url === '/api/sessions/session-a/run-state') {
      runStateChecks += 1;
      return jsonResponse({turn_id:null,status:'completed',notice:''});
    }
    if (url === '/api/sessions/session-a') {
      return jsonResponse({messages:[{role:'user',content:'analyze'},{role:'assistant',content:'done'}],run_state:{status:'completed'}});
    }
    throw new Error('unexpected fetch ' + url);
  };
  app.loadTrustView = async () => {};

  await app.sendMessage();
  await new Promise(resolve => setTimeout(resolve, 20));

  assert.strictEqual(cancelled, true);
  assert.ok(runStateChecks >= 1);
  assert.strictEqual(app.isLoading, false);
  assert.strictEqual(app._getSessionState('session-a').isLoading, false);
}

async function keepalivePreventsFalseSilentStreamRecovery() {
  const app = makeApp();
  app._sseSilenceTimeoutMs = 15;
  app.inputText = 'analyze';
  let cancelled = false;
  let readIndex = 0;
  const chunks = [
    'event: turn_start\ndata: {"session_id":"session-a"}\n\n',
    ': keepalive\n\n',
    ': keepalive\n\n',
    'event: text_delta\ndata: {"text":"done"}\n\n' +
      'event: turn_end\ndata: {"session_id":"session-a","status":"completed"}\n\n',
  ];
  const response = streamResponse([]);
  response.body.getReader = () => ({
    async read() {
      if (readIndex >= chunks.length) return {done:true,value:undefined};
      await new Promise(resolve => setTimeout(resolve, 5));
      return {done:false,value:encoder.encode(chunks[readIndex++])};
    },
    async cancel() { cancelled = true; },
    releaseLock() {},
  });
  fetchImpl = async url => {
    assert.strictEqual(url, '/api/chat');
    return response;
  };
  app.loadTrustView = async () => {};

  await app.sendMessage();

  assert.strictEqual(cancelled, false);
  assert.strictEqual(app.connectionError, '');
  assert.strictEqual(app.turns[app.turns.length - 1].content, 'done');
}

function r07OriginalReplyAndFailureNoticeRemainSeparate() {
  const app = makeApp();
  const turns = app._reconstructTurns([
    {role:'user',content:'全表记录数'},
    {role:'assistant',content:'原接受答案：3行。',reply_id:'accepted_reply'},
    {role:'assistant',content:'执行失败：冲突回答。',reply_id:'failure_reply'},
  ]);
  assert.strictEqual(turns.length,3);
  assert.strictEqual(turns[1].replyId,'accepted_reply');
  assert.strictEqual(turns[1].content,'原接受答案：3行。');
  assert.strictEqual(turns[2].replyId,'failure_reply');
  assert.strictEqual(turns[2].content,'执行失败：冲突回答。');
}


function acceptedHostChartLinksRenderAtTheirExactBodyPosition() {
  const app = makeApp();
  app.currentSessionId = 'session-a';
  const own = { path: 'sessions/session-a/charts/原图_abc123.html', type: 'chart', description: '原图' };
  const foreign = { path: 'sessions/session-b/charts/原图_abc123.html', type: 'chart', description: 'foreign' };
  const body = `Before\n[原图](/api/files/${encodeURI(own.path)})\nAfter`;
  const turn = { content: body, artifacts: [own] };
  const rendered = app._replaceChartReferences(body, turn);
  assert(rendered.indexOf('Before') < rendered.indexOf('<iframe'));
  assert(rendered.indexOf('<iframe') < rendered.indexOf('After'));
  assert(rendered.includes('title="原图"') && rendered.includes('Open chart in a new tab'));
  assert.strictEqual(app.supplementalArtifacts(turn).length, 0);
  const repeated = body + `\n[[chart:原图_abc123.html]]\n[原图](/api/files/${encodeURI(own.path)})`;
  assert.strictEqual((app._replaceChartReferences(repeated, turn).match(/<iframe/g) || []).length, 1);
  assert(app._replaceChartReferences(repeated, turn).includes('查看已展示图表'));

  for (const href of [
    '/api/files/sessions/session-a/charts/原图_wronghash.html',
    '/api/files/' + encodeURI(foreign.path),
    'https://external.invalid/chart.html',
  ]) {
    const text = `[candidate](${href})`;
    assert(!app._replaceChartReferences(text, { content: text, artifacts: [own, foreign] }).includes('<iframe'));
  }
  app.sessionArtifacts = [own];
  assert(!app._replaceChartReferences(body, { content: body, artifacts: [] }).includes('<iframe'));
  // A document artifact is still a link, even when its path ends with html.
  assert(!app._replaceChartReferences(body, { content: body, artifacts: [{...own, type:'report'}] }).includes('<iframe'));
}


function acceptedWorkbenchFragmentsUseTablesWithoutArtifactAuthority() {
  context.marked = require(require('path').join(require('path').dirname(appPath), '../vendor/marked/marked-15.0.4.min.js'));
  context.katex = require(require('path').join(require('path').dirname(appPath), '../vendor/katex/katex-0.16.11.min.js'));
  const app = makeApp();
  app.currentSessionId = 'session-a';
  const fragment = 'Before\n\n| field | value |\n| --- | --- |\n| escaped\\_key | 0 |\n\n$120/12=10$\n\nAfter';
  const html = app.renderMarkdown(fragment, null, false);
  assert(html.includes('<table>') && html.includes('escaped_key') && html.includes('>0</td>'));
  assert(html.includes('tabindex="0"') && html.includes('katex'));
  assert(html.indexOf('Before') < html.indexOf('<table>') && html.indexOf('</table>') < html.indexOf('After'));
  const hostile = '<iframe src="/api/files/sessions/session-a/charts/original.html"></iframe>\n\n' +
    '[owned](/api/files/sessions/session-a/charts/original.html)\n\n' +
    '![image](https://external.invalid/p.png)\n\n' +
    '[chart:original]\n\n{"data":[{"x":[1],"y":[2]}]}\n\n' +
    '```json\n{"data":[{"x":[1],"y":[2]}]}\n```\n\n```mermaid\nflowchart LR\n A-->B\n```';
  const safe = app.renderMarkdown(hostile, {artifacts:[{path:'sessions/session-a/charts/original.html',type:'chart'}]}, false);
  assert(!/<(?:iframe|img|a)\b/.test(safe));
  assert(!safe.includes('plotly-chart') && !safe.includes('mermaid-container'));
  assert(safe.includes('&lt;iframe') && safe.includes('[owned]') && safe.includes('[chart:original]'));
  assert(safe.includes('<pre><code') && Object.keys(app._chartData).length === 0);
  const template = fs.readFileSync(require('path').join(require('path').dirname(appPath), '../../templates/index.html'), 'utf8');
  assert(template.includes('x-html="renderMarkdown(conclusion.summary, null, false)"'));
  const css = fs.readFileSync(require('path').join(require('path').dirname(appPath), '../css/app.css'), 'utf8');
  const detailRule = css.match(/\.workbench-conclusion-summary\s*\{([^}]+)\}/)[1];
  assert(/white-space:\s*normal/.test(detailRule), 'HTML details must not preserve Markdown-generated whitespace');
}

const scenarios = {
  accepted_workbench_fragment: acceptedWorkbenchFragmentsUseTablesWithoutArtifactAuthority,
  r07_identity: r07OriginalReplyAndFailureNoticeRemainSeparate,
  accepted_host_chart_links: acceptedHostChartLinksRenderAtTheirExactBodyPosition,
  terminal_before_eof: terminalPublishesBeforeEOFAndOldEOFDoesNotUnlockNextRun,
  silent_sse_recovery: silentSSEFallsBackToDurableRunState,
  sse_keepalive: keepalivePreventsFalseSilentStreamRecovery,
  reply_export_names: replyExportsHaveUniqueSessionOwnedFilenames,
  execution_notice: executionNoticesSurviveReplayWithoutDuplication,
  normal_chat: normalChatUsesOneCompletionRefresh,
  upload_file_refs: uploadedFileReferencesAreAddedExactlyOnce,
  confirmation_resume: confirmationResumeUsesCompletionRefresh,
  chunked_sse: chunkedSSEPreservesEventStateAndFlushesEOF,
  session_switch: switchingSessionDoesNotProjectBackgroundCompletion,
  stale_trust: staleTrustResponseCannotOverwriteNewerProjection,
  reconstruct_confirmation: persistedConfirmationProtocolIsReconstructedAsFriendlyAnswer,
};

(async () => {
  assert.ok(scenarios[scenario], `unknown scenario: ${scenario}`);
  await scenarios[scenario]();
  process.stdout.write(`PASS ${scenario}\n`);
})().catch(error => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
"""


@pytest.mark.parametrize(
    "scenario",
    [
        "normal_chat",
        "upload_file_refs",
        "terminal_before_eof",
        "silent_sse_recovery",
        "sse_keepalive",
        "confirmation_resume",
        "chunked_sse",
        "session_switch",
        "stale_trust",
        "reconstruct_confirmation",
        "execution_notice",
        "reply_export_names",
        "r07_identity",
        "accepted_host_chart_links",
        "accepted_workbench_fragment",
    ],
)
def test_web_sse_completion_lifecycle(tmp_path: Path, scenario: str) -> None:
    node = shutil.which("node")
    assert node, "Node.js is required for the browser lifecycle contract"
    runner = tmp_path / "web_sse_lifecycle_contract.cjs"
    runner.write_text(NODE_CONTRACT, encoding="utf-8")

    completed = subprocess.run(
        [node, str(runner), str(APP_JS), scenario],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, (
        f"Node lifecycle contract failed for {scenario}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    assert f"PASS {scenario}" in completed.stdout


def test_workbench_header_and_page_shell_have_stable_session_boundaries() -> None:
    base_html = (ROOT / "src" / "data_agent" / "web" / "templates" / "base.html").read_text(encoding="utf-8")
    index_html = (ROOT / "src" / "data_agent" / "web" / "templates" / "index.html").read_text(encoding="utf-8")

    assert '<html lang="zh-CN" class="h-full overflow-hidden">' in base_html
    assert '<body class="h-full overflow-hidden' in base_html
    assert '<div class="flex h-full min-h-0 overflow-hidden"' in index_html
    assert '<aside class="w-72 min-h-0 overflow-hidden sidebar-panel' in index_html
    assert "'w-0 overflow-hidden border-r-0'" not in index_html
    assert 'id="messages-container"' in index_html
    assert 'flex-1 min-h-0 overflow-y-auto overscroll-contain' in index_html
    assert index_html.count('flex-1 min-h-0 overflow-y-auto overscroll-contain') >= 2
    assert "('会话：' + currentSessionId)" in index_html
    assert "('会话：' + (sessionTitle || currentSessionId))" not in index_html
