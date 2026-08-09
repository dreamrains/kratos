# Web SSE and Live Release Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the current Web SSE reactivity failure, replace ignored and source-only checks with collected contract tests plus actual browser evidence, run three real-provider data-analysis sessions, and make product release status PASS only when every A-F gate has actually passed.

**Architecture:** Keep the production Flask SSE route and Alpine application as the system under test. A deterministic acceptance server swaps `AgentManager` for a manager that constructs the real `AgentLoop` with a scripted provider. A transport adapter delays safe progress and splits only the already-audited final `text_delta`; the real tools, projection, audit, publication, `/api/chat`, SSE serializer, and page remain in path. An actual browser observes DOM state before `turn_end`. A separate live-provider runner uses the same real pipeline with the configured provider three times. Both executions emit versioned receipts consumed by the release-gate aggregator from the first plan.

**Tech Stack:** Python 3.11+, Flask, Alpine.js, browser control through `browser:control-in-app-browser`, pytest, Node syntax checking, JSON gate receipts, real configured LLM provider.

## Global Constraints

- Planning baseline is commit `84b3e087afa01b9fc1c39678bdc5da09992989f7`. Tasks 1-3 start after Plan A Task 6 and are part of the Phase B deterministic stop gate; Tasks 4-6 start only after that combined Phase B gate passes.
- Work only in `D:\Project\Daily\data-agent\.worktrees\analysis-reliability` on `codex/analysis-reliability`.
- Run Python with `PYTHONPATH=D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests`.
- Use `D:\Project\Daily\data-agent\.venv\Scripts\python.exe`; the shared editable install otherwise points at the main checkout.
- Test the real `src/data_agent/web/static/js/app.js`, real Flask blueprint, real SSE serialization, and real page. Do not replace production JavaScript or `/api/chat` with a test-only protocol.
- The deterministic browser fixture may replace the provider-facing
  `AgentManager`, provider client, storage roots, and event timing. Its normal
  success path must still call the real `AgentLoop`, tools, projection, final
  audit, and tiered renderer. Small scripted control-path loops are allowed
  only for suspend, interrupt, and forced-error browser cases.
- Browser Gate E requires an actual browser observation. Flask-client tests, string searches, raw HTTP, or an SSE transcript cannot satisfy it.
- Live-provider Gate F requires three completed real-provider sessions. Mocks may test aggregation but cannot satisfy it.
- A missing browser capability, provider credential, or provider response is `BLOCKED`, never `PASS` or `NOT_RUN`, under the product profile.
- Browser and live receipts bind to the exact release-source digest over tracked `src/`, `scripts/`, `tests/`, and `pyproject.toml` content. A documentation-only commit does not invalidate them; any runtime, acceptance, or test change does.
- `analysis_progress` may expose only the closed server-authored process vocabulary. Findings, values, rankings, claims, and reasoning remain buffered until audited final publication.
- Preserve all original sessions and uploaded files. Acceptance runs use isolated temporary workspace/session directories and a synthetic, privacy-safe CSV.
- Do not install Playwright, Selenium, Puppeteer, jsdom, or a browser driver. Use the already available in-app browser controller for the actual DOM gate.
- Do not merge, push, or mark Task 12 complete until all required A-F gates are PASS and both final reviews are clean.

---

## File and ownership map

| File | Responsibility after this plan |
|---|---|
| `tests/conftest.py` | Ignore only non-pytest legacy scripts; no release-critical Web test is hidden from collection. |
| `tests/test_web_sse_contract.py` | Collected Flask/SSE ordering, payload allowlist, error, and persistence contract tests. |
| `tests/test_web_sse_reactivity_contract.py` | Fast static guard for the exact Alpine ownership/reactivity invariants; not a substitute for Gate E. |
| `tests/test_analysis_progress_streaming.py` | Preserve safe progress-vocabulary and server-projection coverage. |
| `src/data_agent/web/static/js/app.js` | Keep the current session's turn as an Alpine-observed object and publish each progress/text mutation reactively. |
| `src/data_agent/web/blueprints/chat.py` | Preserve ordered unbuffered SSE and explicit terminal/error behavior. |
| `scripts/acceptance/run_web_sse_fixture.py` | Run the normal Web app with a deterministic delayed fake loop and isolated storage. |
| `scripts/acceptance/browser_gate_contract.py` | Define, validate, and persist `analysis_browser_gate.v1` receipts from actual browser observations. |
| `scripts/acceptance/release_source.py` | Compute the deterministic release-source digest shared by browser, live, and product gates. |
| `tests/test_browser_gate_contract.py` | Receipt schema, timing, DOM-snapshot, and false-green regression tests. |
| `scripts/replay_analysis_reliability.py` | Execute three real-provider analysis replays and emit `analysis_live_provider_gate.v1`. |
| `tests/test_live_provider_release_runner.py` | Unit-test live-run aggregation, completeness, and blocked behavior without satisfying Gate F. |
| `scripts/run_analysis_release_gates.py` | Validate browser/live receipts and aggregate product A-F status. |
| `tests/test_analysis_release_gate_runner.py` | Reject absent, stale, mismatched, partial, or non-PASS product receipts. |
| `docs/superpowers/specs/2026-07-28-measurement-identity-and-honest-release-gates-design.md` | Record implemented evidence only after A-F pass. |

---

### Task 1: Replace ignored Web scripts with collected SSE contract tests

**Files:**
- Create: `tests/test_web_sse_contract.py`
- Modify: `tests/conftest.py:1-11`
- Move: `tests/test_sse_reactivity.py` to `scripts/acceptance/legacy_sse_reactivity.py`
- Move: `tests/test_web_gui.py` to `scripts/acceptance/legacy_web_gui.py`
- Modify: `tests/test_analysis_release_gate_runner.py`

**Interfaces:**
- Consumes: `_feed_events`, `_sse_response`, `EventQueue`, and a fake loop generator.
- Produces: collected tests for the real server projection and a release check that fails when release-critical tests are ignored.

- [ ] **Step 1: Write the collection-honesty regression**

Add to `tests/test_analysis_release_gate_runner.py`:

```python
def test_release_critical_web_tests_are_collected():
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert '"test_sse_reactivity.py"' not in conftest
    assert '"test_web_gui.py"' not in conftest
    assert (ROOT / "tests" / "test_web_sse_contract.py").is_file()
```

Add a subprocess test:

```python
def test_release_critical_web_nodeids_are_in_collect_only():
    result = run_pytest_collect_only(
        "tests/test_web_sse_contract.py",
    )
    assert result.returncode == 0, result.stderr
    assert "test_real_chat_route_streams_progress_before_text_and_turn_end" in result.stdout
```

- [ ] **Step 2: Run the collection tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests'
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_analysis_release_gate_runner.py -k "release_critical_web" -q
```

Expected: FAIL because both legacy Web scripts are explicitly ignored and the new collected files do not exist.

- [ ] **Step 3: Create deterministic server-contract fixtures**

Create `tests/test_web_sse_contract.py` with a minimal fake loop and manager:

```python
class ScriptedLoop:
    session_id = "sse_contract"

    def __init__(self):
        self.messages = []
        self.saved = 0

    def stream_turn(self, message):
        self.messages.append({"role": "user", "content": message})
        yield {
            "type": "analysis_progress",
            "code": "analysis_plan_ready",
            "label": "分析计划已就绪",
            "status": "finished",
            "step_id": "step_profile",
            "finding": "must not cross the boundary",
        }
        yield {"type": "text_delta", "text": "第一段"}
        yield {"type": "text_delta", "text": "第二段"}
        self.messages.append({"role": "assistant", "content": "第一段第二段"})

    def _auto_save(self):
        self.saved += 1


class ScriptedManager:
    def __init__(self, loop):
        self.loop = loop

    def get_or_create(self, **_kwargs):
        return self.loop

    def get(self, session_id):
        return self.loop if session_id == self.loop.session_id else None

    def remove(self, _session_id):
        return None
```

Create the Flask fixture only after setting:

```python
monkeypatch.setattr(
    data_agent.config,
    "_config",
    AgentConfig(
        WORKSPACE_DIR=tmp_path / "workspace",
        SESSIONS_DIR=tmp_path / "sessions",
        _env_file=None,
    ),
)
```

Then call `create_app()` and replace `app.config["agent_manager"]` with this
manager. Parse the streaming response incrementally and assert:

```python
def test_real_chat_route_streams_progress_before_text_and_turn_end(app):
    response = app.test_client().post(
        "/api/chat",
        json={"message": "分析这个数据"},
        buffered=False,
    )
    events = list(parse_sse_chunks(response.response))
    types = [event for event, _data in events]
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert types == [
        "turn_start",
        "analysis_progress",
        "text_delta",
        "text_delta",
        "turn_end",
    ]
    assert events[1][1] == {
        "code": "analysis_plan_ready",
        "label": "分析计划已就绪",
        "status": "finished",
        "step_id": "step_profile",
        "phase": "",
    }
    assert "finding" not in events[1][1]
    assert events[-1][1]["status"] == "completed"
```

Also test generator failure: one `error`, then `turn_end` with `status="error"`, queue closes, and `_auto_save()` is still attempted.

- [ ] **Step 4: Move the custom scripts out of pytest collection**

Use `apply_patch` move hunks for the two legacy custom-runner scripts:

```text
*** Update File: tests/test_sse_reactivity.py
*** Move to: scripts/acceptance/legacy_sse_reactivity.py

*** Update File: tests/test_web_gui.py
*** Move to: scripts/acceptance/legacy_web_gui.py
```

Remove their names from `collect_ignore`. Do not rewrite them as authoritative gates; add a header to each stating that it is a manual legacy diagnostic and cannot satisfy Gate E.

- [ ] **Step 5: Run collection and server-contract suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest --collect-only tests/test_web_sse_contract.py -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_web_sse_contract.py tests/test_analysis_progress_streaming.py tests/test_analysis_release_gate_runner.py -q
```

Expected: collection exits 0; the real Flask route has ordered safe SSE coverage; no release-critical Web test remains hidden.

- [ ] **Step 6: Commit collection honesty and SSE contract**

```powershell
git add tests/conftest.py tests/test_web_sse_contract.py tests/test_analysis_release_gate_runner.py scripts/acceptance/legacy_sse_reactivity.py scripts/acceptance/legacy_web_gui.py
git commit -m "test: collect the web SSE release contract"
```

---

### Task 2: Repair current-turn Alpine reactivity

**Files:**
- Create: `tests/test_web_sse_reactivity_contract.py`
- Modify: `src/data_agent/web/static/js/app.js:1557-1601`
- Modify: `src/data_agent/web/static/js/app.js:1728-1764`
- Modify: `src/data_agent/web/static/js/app.js:2310-2477`
- Modify: `tests/test_analysis_progress_streaming.py:400-418`
- Modify: `tests/test_web_overhaul.py:650-682`

**Interfaces:**
- Consumes: one session-owned raw state plus Alpine's observable `this.turns`.
- Produces: a current assistant turn obtained from the reactive array, immutable-array publication after every visible mutation, and no undefined renderer call.

- [ ] **Step 1: Write exact reactivity invariant tests**

Create `tests/test_web_sse_reactivity_contract.py`:

```python
from pathlib import Path

APP_JS = (
    Path(__file__).parents[1]
    / "src/data_agent/web/static/js/app.js"
).read_text(encoding="utf-8")


def _method_block(start, end):
    return APP_JS[APP_JS.index(start):APP_JS.index(end)]


def test_send_message_passes_current_reactive_turn():
    block = _method_block("async sendMessage()", "// --- Confirmation helpers ---")
    assert "this.turns = [...state.turns];" in block
    assert (
        "const turn = this.turns[this.turns.length - 1];"
        in block
    )
    assert block.index("this.turns = [...state.turns];") < block.index(
        "const turn = this.turns[this.turns.length - 1];"
    )
    assert "await this._processSSE(response, turn, state, sseSessionId);" in block


def test_current_turn_mutations_publish_reactive_array_updates():
    block = _method_block("_handleEvent(type, data, turn, state, sessionId)", "// --- Helpers ---")
    assert "this._renderMessages()" not in block
    progress = block[
        block.index("case 'analysis_progress':"):
        block.index("case 'text_delta':")
    ]
    text = block[
        block.index("case 'text_delta':"):
        block.index("case 'tool_call':")
    ]
    expected = "if (isCurrentSession) this.turns = [...state.turns];"
    assert expected in progress
    assert expected in text


def test_resume_uses_reactive_new_turn():
    block = _method_block("async resumeConfirmation", "async interruptGeneration")
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
```

These are fast source-contract guards for the exact regression. They do not satisfy Gate E.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_web_sse_reactivity_contract.py tests/test_analysis_progress_streaming.py -q
```

Expected: FAIL because `sendMessage` takes `turn` from `state.turns`, progress calls undefined `_renderMessages()`, and text chunks do not notify Alpine.

- [ ] **Step 3: Fix ownership order in send and resume paths**

In `sendMessage`, replace:

```javascript
const turn = state.turns[state.turns.length - 1];

// Sync to reactive properties
this.turns = [...state.turns];
```

with:

```javascript
// Publish the new turn first, then keep the Alpine-observed object for SSE.
this.turns = [...state.turns];
state.turns = this.turns;
const turn = this.turns[this.turns.length - 1];
```

Apply the same order in `resumeConfirmation` after creating `newTurn`:

```javascript
this.turns = [...state.turns];
state.turns = this.turns;
const newTurn = this.turns[this.turns.length - 1];
```

Do not use a detached `assistantTurn`, `newTurn`, or `state.turns[...]` reference as the `_processSSE` mutation target.

- [ ] **Step 4: Publish each user-visible event mutation**

In `_handleEvent`, replace the undefined progress refresh:

```javascript
this._renderMessages();
```

with:

```javascript
if (isCurrentSession) this.turns = [...state.turns];
```

After appending each `text_delta`, publish the array before scrolling:

```javascript
if (isCurrentSession) {
    this.turns = [...state.turns];
    this._scrollToBottom();
}
```

Add the same current-session array publication to `llm_call_start`, `tool_call`, and `tool_result` after their visible mutations. Do not refresh the active DOM when the SSE belongs to a background session.

- [ ] **Step 5: Tighten existing fast tests**

Change the current source-only progress tests to assert:

```python
assert "this._renderMessages()" not in progress_block
assert "this.turns = [...state.turns]" in progress_block
```

Retain the assertions that progress labels are not appended to `turn.content` and forbidden finding fields never reach the browser.

- [ ] **Step 6: Run reactivity, SSE, and syntax suites**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_web_sse_reactivity_contract.py tests/test_web_sse_contract.py tests/test_analysis_progress_streaming.py tests/test_web_overhaul.py -q
node --check src/data_agent/web/static/js/app.js
```

Expected: PASS; syntax is valid, and the exact raw-reference and undefined-renderer regressions are guarded.

- [ ] **Step 7: Commit the current-turn reactivity repair**

```powershell
git add src/data_agent/web/static/js/app.js tests/test_web_sse_reactivity_contract.py tests/test_analysis_progress_streaming.py tests/test_web_overhaul.py
git commit -m "fix: render SSE progress and text incrementally"
```

---

### Task 3: Build a deterministic actual-browser fixture

**Files:**
- Create: `scripts/acceptance/__init__.py`
- Create: `scripts/acceptance/run_web_sse_fixture.py`
- Create: `scripts/acceptance/browser_gate_contract.py`
- Create: `tests/test_browser_gate_contract.py`

**Interfaces:**
- Consumes: normal `create_app()`, the real page, real JavaScript, real fetch stream, and a scripted loop.
- Produces:
  - a Web process at `http://127.0.0.1:5013`;
  - delayed progress/chunk events with server timestamps;
  - a validated `analysis_browser_gate.v1` receipt containing browser-observed DOM snapshots and timing.

- [ ] **Step 1: Write receipt false-green tests**

Create `tests/test_browser_gate_contract.py`:

```python
def _valid_observation():
    return {
        "contract_version": "analysis_browser_gate.v1",
        "status": "PASS",
        "observer": "in_app_browser",
        "fixture_id": "web_sse_fixture_v1",
        "source_digest": "sha256:" + "a" * 64,
        "source_commit": "a" * 40,
        "url": "http://127.0.0.1:5013",
        "observations": [
            {
                "name": "upload_starts_analysis",
                "observed_text": "browser_fixture.csv",
                "browser_ms": 40,
                "server_event_ms": 0,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "progress_before_answer",
                "observed_text": "正在分析字段质量",
                "browser_ms": 100,
                "server_event_ms": 80,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "first_chunk_before_second",
                "observed_text": "第一段",
                "browser_ms": 350,
                "server_event_ms": 300,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "complete_answer_before_turn_end",
                "observed_text": "第一段第二段",
                "browser_ms": 700,
                "server_event_ms": 650,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "persisted_after_refresh",
                "observed_text": "第一段第二段",
                "browser_ms": 1200,
                "server_event_ms": 900,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "markdown_table_and_limitation_rendered",
                "observed_text": "局限",
                "browser_ms": 750,
                "server_event_ms": 650,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "retained_after_session_switch",
                "observed_text": "第一段第二段",
                "browser_ms": 1400,
                "server_event_ms": 900,
                "turn_end_browser_ms": 900,
            },
            {
                "name": "suspend_resume_nonblank",
                "observed_text": "恢复后内容",
                "browser_ms": 1600,
                "server_event_ms": 1500,
                "turn_end_browser_ms": 1550,
            },
            {
                "name": "interruption_nonblank",
                "observed_text": "已中断验收",
                "browser_ms": 1800,
                "server_event_ms": 1750,
                "turn_end_browser_ms": 1760,
            },
            {
                "name": "error_nonblank",
                "observed_text": "synthetic_acceptance_error",
                "browser_ms": 2000,
                "server_event_ms": 1950,
                "turn_end_browser_ms": 1960,
            },
        ],
    }


def test_browser_receipt_requires_all_dom_observations(tmp_path):
    receipt = _valid_observation()
    receipt["observations"] = receipt["observations"][:2]
    result = validate_browser_gate_receipt(
        receipt,
        expected_source_digest="sha256:" + "a" * 64,
    )
    assert result.status == "FAIL"
    assert "missing_browser_observations" in result.reason_codes


def test_browser_receipt_rejects_post_turn_end_only_observation():
    receipt = _valid_observation()
    receipt["observations"][1]["browser_ms"] = 950
    result = validate_browser_gate_receipt(
        receipt,
        expected_source_digest="sha256:" + "a" * 64,
    )
    assert result.status == "FAIL"
    assert "not_observed_before_turn_end" in result.reason_codes


def test_raw_sse_transcript_cannot_satisfy_browser_receipt():
    receipt = _valid_observation()
    receipt["observer"] = "raw_http"
    result = validate_browser_gate_receipt(
        receipt,
        expected_source_digest="sha256:" + "a" * 64,
    )
    assert result.status == "FAIL"
    assert "invalid_browser_observer" in result.reason_codes
```

- [ ] **Step 2: Run receipt tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_browser_gate_contract.py -q
```

Expected: FAIL because the contract module does not exist.

- [ ] **Step 3: Implement the browser receipt contract**

In `browser_gate_contract.py`, define:

```python
BROWSER_GATE_CONTRACT_VERSION = "analysis_browser_gate.v1"
REQUIRED_OBSERVATIONS = {
    "upload_starts_analysis",
    "progress_before_answer",
    "first_chunk_before_second",
    "complete_answer_before_turn_end",
    "markdown_table_and_limitation_rendered",
    "persisted_after_refresh",
    "retained_after_session_switch",
    "suspend_resume_nonblank",
    "interruption_nonblank",
    "error_nonblank",
}


@dataclass(frozen=True)
class ReceiptValidation:
    status: str
    reason_codes: tuple[str, ...]


def validate_browser_gate_receipt(
    receipt: Any,
    *,
    expected_source_digest: str,
) -> ReceiptValidation:
    reasons = []
    if not isinstance(receipt, dict):
        return ReceiptValidation("FAIL", ("invalid_browser_receipt",))
    if receipt.get("contract_version") != BROWSER_GATE_CONTRACT_VERSION:
        reasons.append("invalid_browser_contract_version")
    if receipt.get("observer") != "in_app_browser":
        reasons.append("invalid_browser_observer")
    if receipt.get("source_digest") != expected_source_digest:
        reasons.append("stale_browser_receipt")
    observations = {
        item.get("name"): item
        for item in receipt.get("observations") or []
        if isinstance(item, dict)
    }
    if not REQUIRED_OBSERVATIONS.issubset(observations):
        reasons.append("missing_browser_observations")
    for name in (
        "progress_before_answer",
        "first_chunk_before_second",
        "complete_answer_before_turn_end",
    ):
        item = observations.get(name)
        if item and not (
            isinstance(item.get("browser_ms"), int)
            and isinstance(item.get("turn_end_browser_ms"), int)
            and item["browser_ms"] < item["turn_end_browser_ms"]
        ):
            reasons.append("not_observed_before_turn_end")
    return ReceiptValidation(
        "PASS" if not reasons and receipt.get("status") == "PASS" else "FAIL",
        tuple(dict.fromkeys(reasons)),
    )
```

The writer rejects direct personal identifiers, uploaded filenames, prompts, raw model reasoning, and complete production answers. It stores only the fixed synthetic fixture strings, monotonic offsets, URL, fixture ID, observer, commit, and status.

Create `release_source.py` with
`release_source_digest(root: Path) -> str`. It runs
`git ls-files -z --cached --others --exclude-standard -- src scripts tests
pyproject.toml`, excludes `__pycache__`, `*.pyc`, and generated receipts, then
hashes each UTF-8 path, a NUL separator, and the current file's Git-filtered
blob identity in sorted path order. This preserves dirty and untracked source
changes while making semantically identical LF/CRLF checkouts share one
identity; binary byte changes remain significant. The return value is
`sha256:<64 lowercase hex>`. Add tests proving a tracked source/test byte
change changes the digest, Git-normalized line endings do not, binary changes
do, and a `docs/` change does not.

- [ ] **Step 4: Implement the delayed fixture server**

`run_web_sse_fixture.py` must:

1. set `WORKSPACE_DIR` and `SESSIONS_DIR` to children of the provided output
   directory, set `data_agent.config._config = None`, and only then call
   `create_app()`;
2. replace `app.config["agent_manager"]` with `ScriptedManager`;
3. expose the normal root and `/api/chat`;
4. write an event trace under the provided temporary output directory;
5. bind only `127.0.0.1:5013`.

For observation only, replace the `EventQueue` symbol in the fixture process
with a subclass of the production queue whose `put()` first calls
`super().put(event)` and then appends
`{"event": event.event, "monotonic_ms": ..., "session_id": ...}` to a
thread-safe JSONL trace. It records no payload text. This observes the real
`_feed_events`-generated `turn_end` without replacing projection or SSE
serialization.

For the normal prompt, `ScriptedManager` creates a real `AgentLoop` with a
deterministic scripted provider. Its responses execute the real
`load_data -> quick_profile -> correlation_analysis ->
factor_relationship_analysis -> synthesis` path. The final provider draft is
diagnostic Markdown with no unaudited numeric assertion:

```python
BROWSER_FINAL_DRAFT = (
    "# 分析结果\n\n"
    "第一段：已完成合成数据的分析流程。"
    "第二段：已检查数据质量和字段范围。\n\n"
    "| 检查项 | 状态 |\n|---|---|\n"
    "| 数据质量 | 已检查 |\n| 分析流程 | 已完成 |\n\n"
    "## 局限\n\n此页面只验证合成数据的流式显示。"
)
```

The real final audit and tiered renderer must produce the text before the
adapter sees it. `DelayedAuditedLoop.stream_turn()` forwards real
progress/tool events immediately, buffers only final `text_delta` events until
the wrapped generator finishes, then splits the audited text at the fixed
`第一段`/`第二段` boundary:

```python
def stream_turn(self, message):
    if message in CONTROL_PROMPTS:
        yield from self._control_stream(message)
        return
    final_text = ""
    for event in self.inner.stream_turn(message):
        if event.get("type") == "text_delta":
            final_text += str(event.get("text") or "")
        else:
            yield event
    for chunk in split_audited_fixture_text(final_text):
        if self.interrupted.wait(0.6):
            yield {"type": "error", "message": "已中断验收"}
            return
        yield {"type": "text_delta", "text": chunk}
```

`split_audited_fixture_text` first asserts that the text is non-empty, contains
`# 分析结果`, `第一段`, `第二段`, a Markdown table, and `## 局限`; a missing
anchor fails the fixture instead of substituting text. It returns exactly
three chunks and never changes characters. Therefore the DOM receives the
actual audited publication, only with deterministic timing.

For control prompts, the adapter implements:

- `触发暂停验收`: one `suspended` event for `confirm_fixture`;
- `request_interrupt()`: set a `threading.Event`; the delayed stream returns
  one `error` with `message="已中断验收"`;
- `_confirmation_runtime().get(...)`: resolve only `confirm_fixture`;
- `resume_turn_streaming(...)`: require the exact confirmation ID/version,
  yield `text_delta="恢复后内容"`, append it to messages, and persist;
- `触发错误验收`: raise `RuntimeError("synthetic_acceptance_error")`.

The manager owns one wrapped loop per session so session switching exercises
the normal frontend state map. The wrapper delegates `messages`, `session_id`,
`_auto_save()`, and every non-control attribute to the real loop.

The fixture writes `browser_fixture.csv` under its isolated output directory
with `日期,收入,成本,渠道` and 120 deterministic synthetic rows. Gate E uploads
this file through the real upload UI before starting the normal stream.

Delay occurs only in this standalone acceptance process, never in production or pytest.

- [ ] **Step 5: Run fixture-contract tests**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_browser_gate_contract.py tests/test_web_sse_contract.py -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/acceptance/run_web_sse_fixture.py --help
```

Expected: PASS and help exits 0 without starting a server.

- [ ] **Step 6: Commit the deterministic browser fixture**

```powershell
git add scripts/acceptance/__init__.py scripts/acceptance/run_web_sse_fixture.py scripts/acceptance/browser_gate_contract.py scripts/acceptance/release_source.py tests/test_browser_gate_contract.py
git commit -m "test: add deterministic browser SSE fixture"
```

---

### Task 4: Execute actual browser Gate E

**Files:**
- Runtime output only: isolated temporary `analysis_browser_gate.v1.json`
- No production file changes unless the observation exposes another reproducible defect.

**Interfaces:**
- Consumes: committed Task 3 fixture and `browser:control-in-app-browser`.
- Produces: one PASS receipt tied to the exact release-source digest, or a BLOCKED/FAIL report with browser evidence.

- [ ] **Step 1: Start the fixture from the worktree source**

Run in a background terminal:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests'
$browserGateRoot = Join-Path $env:TEMP ("data-agent-browser-gate-" + [guid]::NewGuid().ToString("N"))
$browserReceipt = Join-Path $browserGateRoot "analysis_browser_gate.v1.json"
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/acceptance/run_web_sse_fixture.py --host 127.0.0.1 --port 5013 --output-dir $browserGateRoot
```

Read the terminal until it reports `fixture_id=web_sse_fixture_v1` and the bound URL. If the port is occupied, stop only the process started by this task and rerun with `--port 5014`; record the actual URL.

- [ ] **Step 2: Open the real page with the in-app browser**

Use `browser:control-in-app-browser` and navigate to the fixture URL. Confirm:

- the loaded JavaScript URL comes from the worktree server;
- no console error contains `_renderMessages is not a function`;
- the page is the normal Data Agent chat UI.

Upload `$browserGateRoot\browser_fixture.csv` through the normal upload UI.
Confirm the uploaded filename appears in the current session, enter the exact
prompt `运行流式显示验收`, and submit once.

- [ ] **Step 3: Capture normal-stream DOM observations**

Observe the assistant turn, not the network transcript:

1. the first non-empty server-authored progress label is visible while answer
   text is still empty, and its code/label pair belongs to the closed progress
   catalog;
2. `第一段` is visible before `第二段` arrives;
3. `第一段第二段` is visible while the fixture trace still has no `turn_end`;
4. the `分析结果` heading, the `指标/结果` table, Chinese text, and `局限`
   section are rendered after the final chunk;
5. after `turn_end`, refresh the page/session and confirm `第一段第二段`
   remains visible;
6. create a second session, send the normal prompt, switch to the first
   session, and confirm its final answer remains.

For each observation read `performance.now()` in the page at the same time as
the DOM assertion, record that browser millisecond value, the matching ordered
server-event millisecond from the fixture trace, the separately observed
`turn_end_browser_ms`, and the exact fixed synthetic visible string. Browser
and server clocks are not compared numerically. A missed timing window is FAIL;
rerun the complete fresh fixture session rather than inferring success.

- [ ] **Step 4: Exercise suspend/resume, interruption, and error paths**

Use three new fixture sessions:

1. send `触发暂停验收`, confirm the question is visible, choose `继续`, and
   confirm `恢复后内容` replaces the blank assistant state;
2. send `运行流式显示验收`, interrupt during the first delay, and confirm
   `已中断验收` is visible and the thinking indicator stops;
3. send `触发错误验收` and confirm `synthetic_acceptance_error` is visible and
   the assistant turn is not blank.

Confirm none of these sessions leaves `isThinking` active after its terminal
event and no uncaught console error breaks subsequent sends.

- [ ] **Step 5: Validate and write the receipt**

Use `write_browser_gate_receipt(...)` from `browser_gate_contract.py` with:

```python
{
    "contract_version": "analysis_browser_gate.v1",
    "status": "PASS",
    "observer": "in_app_browser",
    "fixture_id": "web_sse_fixture_v1",
    "source_digest": release_source_digest(ROOT),
    "source_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip(),
    "url": actual_url,
    "observations": observations,
}
```

The writer must validate before persisting. Then run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_browser_gate_contract.py -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/acceptance/browser_gate_contract.py validate --receipt $browserReceipt --root 'D:\Project\Daily\data-agent\.worktrees\analysis-reliability'
```

Expected: PASS. If browser control is unavailable, record Gate E as BLOCKED and stop before product PASS.

- [ ] **Step 6: Stop the fixture and report Gate E**

Stop only the known fixture process. Confirm port 5013/5014 is no longer
owned by it. Keep the receipt outside version control and report its absolute
path, release-source digest, source commit, and PASS/FAIL/BLOCKED status.

---

### Task 5: Implement and run three real-provider analysis sessions

**Files:**
- Modify: `scripts/replay_analysis_reliability.py`
- Create: `tests/test_live_provider_release_runner.py`
- Modify: `tests/test_analysis_reliability_replays.py`

**Interfaces:**
- Consumes: real configured provider, privacy-safe synthetic CSV, real `AgentLoop`, real tool execution, real evidence records, real final audit, and persisted session.
- Produces: `analysis_live_provider_gate.v1` with three per-run outcomes and no raw uploaded data or hidden reasoning.

- [ ] **Step 1: Write aggregation and blocked-state tests**

Create `tests/test_live_provider_release_runner.py`:

```python
def _passing_run(index):
    return {
        "run_id": f"live_{index}",
        "status": "PASS",
        "tool_calls": 4,
        "structured_computations": 2,
        "projected_evidence": 2,
        "final_audit_status": "pass",
        "publication_length": 1200,
        "progress_before_final": True,
        "persisted_matches_streamed": True,
        "repeated_failure_max": 1,
        "requirements": {
            "data_quality": "satisfied",
            "descriptive": "satisfied",
            "relationship": "satisfied",
            "limitations": "satisfied",
        },
    }


def test_live_gate_requires_exactly_three_passing_runs():
    receipt = build_live_provider_receipt(
        source_digest="sha256:" + "a" * 64,
        source_commit="a" * 40,
        provider_model="configured-model",
        runs=[_passing_run(1), _passing_run(2)],
    )
    assert receipt["status"] == "FAIL"
    assert "live_run_count_mismatch" in receipt["reason_codes"]


def test_one_shallow_or_empty_run_fails_entire_live_gate():
    runs = [_passing_run(1), _passing_run(2), _passing_run(3)]
    runs[1]["publication_length"] = 0
    runs[1]["requirements"]["relationship"] = "missing"
    receipt = build_live_provider_receipt(
        source_digest="sha256:" + "a" * 64,
        source_commit="a" * 40,
        provider_model="configured-model",
        runs=runs,
    )
    assert receipt["status"] == "FAIL"
    assert "live_run_failed" in receipt["reason_codes"]


def test_missing_provider_is_blocked_not_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(
        replay_analysis_reliability,
        "_run_one_live_provider_analysis",
        Mock(side_effect=ProviderConfigurationUnavailable(
            "provider_credentials_unavailable"
        )),
    )
    receipt = run_live_provider_acceptance(tmp_path, runs=3)
    assert receipt["status"] == "BLOCKED"
    assert receipt["reason_codes"] == ["provider_credentials_unavailable"]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_live_provider_release_runner.py tests/test_analysis_reliability_replays.py -k "live" -q
```

Expected: FAIL because live mode has no real three-run implementation.

- [ ] **Step 3: Define the fixed live scenario and per-run acceptance**

Generate one synthetic CSV per run with deterministic factors:

```text
customer_id,segment,channel,orders,revenue,cost,returned
C001,new,web,1,100,70,0
...
```

Use at least 120 rows and encode controlled segment/channel effects, noise, missing values, and five duplicate rows. Use a fixed seed and no personal data.

Use the same Chinese prompt for all runs:

```text
请对上传数据进行完整分析：先检查数据质量，再分析收入和成本的总体分布、
分群差异及二者关系，明确哪些结论只是描述或相关性，并给出行动建议与局限。
```

Each run must use a fresh session and the real configured provider. It passes only if:

- the upload/dataset contract is active;
- at least one data-quality computation and two substantive structured computations completed;
- real projected evidence exists for each asserted numeric/relationship claim;
- the final audit is `pass` or the renderer publishes a complete, explicitly limited exploratory tier without a generic English warning;
- all four requirement groups are satisfied or explicitly limited;
- final Chinese publication is at least 600 non-whitespace characters with findings, recommendations, and limitations;
- at least one `analysis_progress` precedes the first final `text_delta`;
- streamed final text equals persisted assistant text after marker stripping;
- no identical tool failure occurs more than twice;
- no measurement-bookkeeping reason schedules an analysis tool.

- [ ] **Step 4: Implement honest live execution and receipts**

Add:

```python
LIVE_PROVIDER_GATE_VERSION = "analysis_live_provider_gate.v1"


def run_live_provider_acceptance(
    output_dir: Path,
    *,
    runs: int = 3,
) -> dict[str, Any]:
    if runs != 3:
        raise ValueError("live provider gate requires exactly three runs")
    try:
        outcomes = [
            _run_one_live_provider_analysis(
                output_dir / f"run_{index}",
                index,
            )
            for index in range(1, 4)
        ]
    except ProviderConfigurationUnavailable as exc:
        return blocked_live_receipt(str(exc))
    return build_live_provider_receipt(
        source_digest=release_source_digest(ROOT),
        source_commit=current_git_commit(),
        provider_model=get_config().model_id,
        runs=outcomes,
    )
```

Do not infer credential requirements from `api_key` alone: local or compatible
providers may be credentialless. Attempt the real configured client.
Normalize LiteLLM missing-key/authentication configuration errors to
`ProviderConfigurationUnavailable("provider_credentials_unavailable")`;
catch provider network, rate-limit, timeout, and response errors per run as
`FAIL` with a bounded category. Do not include credentials, raw prompt
completions, chain-of-thought, or full uploaded rows. `main()` writes the
receipt atomically and exits non-zero unless status is PASS.

- [ ] **Step 5: Run mocked aggregation and deterministic regression**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_live_provider_release_runner.py tests/test_analysis_reliability_replays.py tests/test_measurement_identity_pipeline.py -q
$phaseCDeterministicRoot = Join-Path $env:TEMP ("data-agent-phase-c-deterministic-" + [guid]::NewGuid().ToString("N"))
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/replay_analysis_reliability.py --mode deterministic --output-dir $phaseCDeterministicRoot
```

Expected: tests PASS and deterministic replay remains PASS without claiming Gate F.

- [ ] **Step 6: Commit the live-provider runner**

```powershell
git add scripts/replay_analysis_reliability.py tests/test_live_provider_release_runner.py tests/test_analysis_reliability_replays.py
git commit -m "test: require three real provider analysis runs"
```

- [ ] **Step 7: Execute real Gate F**

Run:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests'
$liveGateRoot = Join-Path $env:TEMP ("data-agent-live-gate-" + [guid]::NewGuid().ToString("N"))
$liveReceipt = Join-Path $liveGateRoot "analysis_live_provider_gate.v1.json"
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/replay_analysis_reliability.py --mode live --runs 3 --output-dir $liveGateRoot --receipt $liveReceipt
```

Expected: exit 0 and `analysis_live_provider_gate.v1` status PASS with exactly three PASS runs. Credentials unavailable is BLOCKED; rate limit, provider failure, empty answer, shallow requirements, or one failed run is FAIL. Do not substitute deterministic responses.

---

### Task 6: Aggregate and execute the honest product release gate

**Files:**
- Modify: `scripts/run_analysis_release_gates.py`
- Modify: `tests/test_analysis_release_gate_runner.py`
- Modify: `docs/superpowers/specs/2026-07-28-measurement-identity-and-honest-release-gates-design.md`
- Modify: `docs/superpowers/specs/2026-07-27-analysis-execution-and-publication-reliability-design.md`

**Interfaces:**
- Consumes: deterministic A-D command results plus exact-release-source browser and live-provider receipts.
- Produces: one `analysis_reliability_release.v1` product report; exit 0 only when A-F are PASS.

- [ ] **Step 1: Write receipt-integrity regressions**

Add:

```python
@pytest.mark.parametrize(
    ("gate", "receipt"),
    [
        ("E", None),
        ("F", None),
        ("E", {"status": "PASS", "source_digest": "stale"}),
        ("F", {"status": "PASS", "source_digest": "stale"}),
    ],
)
def test_product_gate_rejects_missing_or_stale_receipt(gate, receipt):
    report = build_product_report_for_test(
        browser_receipt=receipt if gate == "E" else passing_browser_receipt(),
        live_receipt=receipt if gate == "F" else passing_live_receipt(),
        expected_source_digest="sha256:" + "a" * 64,
    )
    assert report["overall_status"] == "FAIL"
    assert report["product_release_passed"] is False
    assert report["gates"][gate]["status"] in {"FAIL", "BLOCKED"}


def test_product_gate_passes_only_all_a_through_f():
    report = build_gate_report(
        profile="product",
        gate_results={gate: "PASS" for gate in "ABCDEF"},
    )
    assert report["overall_status"] == "PASS"
    assert report["product_release_passed"] is True
```

- [ ] **Step 2: Run aggregator tests and verify RED**

Run:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_analysis_release_gate_runner.py -q
```

Expected: at least the receipt-integrity cases fail until product receipt validation is wired.

- [ ] **Step 3: Validate exact-release-source receipts**

The product CLI accepts:

```text
--profile product
--browser-receipt <analysis_browser_gate.v1.json>
--live-provider-receipt <analysis_live_provider_gate.v1.json>
```

Before running A-D, compute `release_source_digest(ROOT)` once. Validate:

- exact contract version;
- exact release-source digest;
- PASS status;
- Browser receipt uses `observer="in_app_browser"` and all required observations;
- live receipt has exactly three PASS runs and the configured model identity;
- receipt file is valid UTF-8 JSON and below 1 MiB.

Invalid/missing receipts are FAIL or BLOCKED and force non-zero exit.

- [ ] **Step 4: Run the complete deterministic A-D baseline**

Run from worktree source:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -W error::pytest.PytestReturnNotNoneWarning -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' tests/test_tools_comprehensive.py
$productDeterministicRoot = Join-Path $env:TEMP ("data-agent-product-deterministic-" + [guid]::NewGuid().ToString("N"))
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/replay_analysis_reliability.py --mode deterministic --output-dir $productDeterministicRoot
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m compileall -q src/data_agent
node --check src/data_agent/web/static/js/app.js
git diff --check
```

All commands must exit 0. The pytest gate must report that the release-critical Web contract nodeids were collected. A printed `FAIL`, exception, or non-zero direct-runner result fails its gate.

- [ ] **Step 5: Run the product aggregator**

After Step 4, recompute the release-source digest. Repeat Task 4 against that
digest and repeat Task 5 Step 7, so both receipts bind to the same final
runtime/test source. Then run:

```powershell
$productReport = Join-Path $env:TEMP ("analysis-reliability-product-" + [guid]::NewGuid().ToString("N") + ".json")
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/run_analysis_release_gates.py --profile product --browser-receipt $browserReceipt --live-provider-receipt $liveReceipt --output $productReport
```

Expected: exit 0 and:

```json
{
  "contract_version": "analysis_reliability_release.v1",
  "profile": "product",
  "overall_status": "PASS",
  "product_release_passed": true,
  "gates": {
    "A": {"status": "PASS"},
    "B": {"status": "PASS"},
    "C": {"status": "PASS"},
    "D": {"status": "PASS"},
    "E": {"status": "PASS"},
    "F": {"status": "PASS"}
  }
}
```

Any other result means Task 12 remains HOLD.

- [ ] **Step 6: Request two final reviews**

Request:

1. specification-compliance review against the approved design and both implementation plans;
2. code-quality review focused on identity trust boundaries, false-green tests, Web background-session behavior, privacy, and release receipt integrity.

Fix every confirmed high/medium finding with a RED test and rerun the affected gate. If any tracked file under `src/`, `scripts/`, `tests/`, or `pyproject.toml` changed, regenerate both browser/live receipts and rerun the product aggregator. Documentation-only changes retain the same release-source digest.

- [ ] **Step 7: Update status documentation only after PASS**

Change the approved design status from `Approved` to `Implemented and validated` and record:

- exact implementation commit;
- A-F status and report path;
- browser receipt path and observation names;
- live receipt path, configured model ID, and three-run count;
- any bounded limitations that remain;
- statement that `776a866` was superseded and never merged to `main`.

Append the Phase B/Phase C completion evidence to
`docs/superpowers/specs/2026-07-27-analysis-execution-and-publication-reliability-design.md`.
Do not rewrite the historical 2026-07-27 implementation plan or session
records.

- [ ] **Step 8: Commit the final gate and documentation**

```powershell
git add scripts/run_analysis_release_gates.py tests/test_analysis_release_gate_runner.py docs/superpowers/specs/2026-07-28-measurement-identity-and-honest-release-gates-design.md docs/superpowers/specs/2026-07-27-analysis-execution-and-publication-reliability-design.md
git commit -m "docs: record complete analysis reliability validation"
```

After the documentation-only commit, recompute the release-source digest and
confirm it is unchanged, then rerun the product aggregator with the existing
receipts. If the digest changed, stop and regenerate both receipts. Report the
worktree branch and offer explicit merge/push/keep-worktree choices; perform
none implicitly.

---

## Plan-level review and final stop gate

Task 12 is complete only when all statements below are evidenced:

1. A real upload through the Web UI starts the isolated analysis fixture.
2. The current Web page displays safe process progress before audited final text.
3. The first final text chunk appears in the DOM before the second and before `turn_end`.
4. Headings, tables, Chinese text, and limitations render, and the final answer survives refresh and session switching.
5. Suspend/resume, interruption, and error paths terminate with a nonblank assistant turn.
6. No `_renderMessages` error or swallowed SSE mutation error occurs.
7. Collected pytest covers Flask SSE projection and Alpine source invariants.
8. Gate E is based on an actual in-app browser observation, not HTTP or string matching.
9. Three fresh real-provider data-analysis sessions all pass the depth, evidence, publication, streaming, persistence, and retry criteria.
10. Gate F is BLOCKED or FAIL when the provider is unavailable or any run fails.
11. Product status is PASS only when A, B, C, D, E, and F are all PASS for the exact release-source digest.
12. Fresh specification and code-quality reviews have no unresolved high/medium findings.

If any item is absent, report the precise gate and reason, keep Task 12 on HOLD, and do not describe the project as fully validated.
