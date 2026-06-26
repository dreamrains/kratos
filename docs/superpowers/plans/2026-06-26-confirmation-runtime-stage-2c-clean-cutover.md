# Confirmation Runtime Stage 2C Clean Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the confirmation runtime the only active, answerable confirmation authority across session restoration and resume flows.

**Architecture:** Add a small projection layer that converts durable runtime records into the session/frontend contract, then route session detail and resume through that contract. Remove production resume fallback to legacy root suspension files while keeping historical conversation files readable.

**Tech Stack:** Python 3, Flask blueprints, pytest, durable confirmation event store, Alpine.js frontend.

---

## Scope And Dependencies

This plan implements the approved Stage 2C design in:

- `docs/superpowers/specs/2026-06-26-confirmation-runtime-stage-2c-clean-cutover-design.md`

It deliberately does not redesign the multi-file scope UI. The only UI work here is restoring and submitting runtime confirmation cards.

## File Structure

- Modify `src/data_agent/agent/confirmation/runtime.py`
  - Add projection helpers for session payloads.
  - Keep conversion fields aligned with SSE `suspended` events.

- Modify `src/data_agent/web/blueprints/sessions.py`
  - Add `active_confirmation`, `queued_confirmation_count`, and `failed_confirmation_count` to `GET /api/sessions/<session_id>`.
  - Keep `/api/sessions/<session_id>/analysis` from presenting legacy `pending_confirmations` as an answerable blocker.

- Modify `src/data_agent/web/blueprints/chat.py`
  - Validate the new resume request before starting the SSE background thread.
  - Require `confirmation_id`, `expected_version`, and `idempotency_key`.
  - Stop accepting `suspension_id` as a resume alias.

- Modify `src/data_agent/agent/loop.py`
  - Remove production fallback from runtime confirmation lookup to `SuspensionManager.load()`.
  - Remove resume-time `SuspensionManager.remove()` calls.
  - Return or yield clear runtime errors for missing, stale, invalid, or failed confirmations.

- Modify `src/data_agent/web/static/js/app.js`
  - Restore a confirmation card from `active_confirmation` when loading or switching sessions.
  - Submit runtime fields only.
  - Keep the card visible on validation/conflict errors and show a card-level error.

- Create `tests/test_confirmation_session_api.py`
  - Cover session detail runtime projection and legacy pending non-blocker behavior.

- Modify `tests/test_confirmation_runtime.py`
  - Cover resume clean cutover and no legacy root suspension behavior.

- Modify `tests/test_web_overhaul.py`
  - Add static frontend contract tests for restoration and resume payload shape.

- Modify `tests/test_web_workbench_parity.py`
  - Update workbench summary wording/count assertions if needed.

## Task 1: Add Runtime Session Projection

**Files:**
- Modify: `src/data_agent/agent/confirmation/runtime.py`
- Test: `tests/test_confirmation_session_api.py`

- [ ] **Step 1: Write failing projection tests**

Create `tests/test_confirmation_session_api.py` with:

```python
import json

from data_agent.config import AgentConfig


def _use_tmp_config(monkeypatch, tmp_path):
    import data_agent.config as config_module

    cfg = AgentConfig(
        PROJECT_DIR=tmp_path / "project",
        SESSIONS_DIR=tmp_path / "sessions",
        SKILL_AUTO_DISCOVER=False,
    )
    monkeypatch.setattr(config_module, "_config", cfg)
    return cfg


def _write_session(cfg, session_id):
    session_dir = cfg.sessions_resolved / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "conversation.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "messages": [
                    {"role": "user", "content": "analyze revenue"},
                    {"role": "assistant", "content": "I need one answer first."},
                ],
                "summary": "Revenue analysis",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _request_runtime_confirmation(
    cfg,
    session_id,
    *,
    confirmation_id="cf_session_1",
    decision_key="metric-choice",
    resolution_action="record_confirmation_answer",
):
    from data_agent.agent.confirmation import AnswerMode, ConfirmationOption, QuestionCandidate
    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService

    service = ConfirmationService(cfg.sessions_resolved, action_registry=build_action_registry())
    service.request(
        QuestionCandidate(
            confirmation_id=confirmation_id,
            session_id=session_id,
            turn_id="turn_1",
            decision_key=f"{session_id}:{decision_key}",
            source="test",
            operation="direct_user_question",
            question="Which metric?",
            decision_impact="Metric choice changes the calculation.",
            answer_mode=AnswerMode.SINGLE_SELECT,
            options=(ConfirmationOption(label="Revenue", value="revenue"),),
            blocking_surfaces=("agent_turn",),
            skippable=True,
            resolution_action=resolution_action,
            resolution_params={
                "context": "Choose the metric.",
                "confirmation_type": "metric_scope",
                "related_task_id": 12,
                "related_spec_id": "spec_1",
            },
            data_version="messages:2",
            spec_version="spec_1",
        )
    )
    return service.checkpoint(session_id)


def test_session_detail_returns_active_runtime_confirmation(tmp_path, monkeypatch):
    cfg = _use_tmp_config(monkeypatch, tmp_path)
    session_id = "session_active_runtime"
    _write_session(cfg, session_id)
    active = _request_runtime_confirmation(cfg, session_id)

    from data_agent.web.app import create_app

    client = create_app().test_client()
    resp = client.get(f"/api/sessions/{session_id}")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["active_confirmation"]["confirmation_id"] == active.confirmation_id
    assert body["active_confirmation"]["suspension_id"] == active.confirmation_id
    assert body["active_confirmation"]["version"] == active.version
    assert body["active_confirmation"]["status"] == "suspended"
    assert body["active_confirmation"]["question"] == "Which metric?"
    assert body["active_confirmation"]["options"] == [
        {"label": "Revenue", "value": "revenue", "description": ""}
    ]
    assert body["active_confirmation"]["context"] == "Choose the metric."
    assert body["active_confirmation"]["multi_select"] is False
    assert body["active_confirmation"]["confirmation_type"] == "metric_scope"
    assert body["active_confirmation"]["blocking_reason"] == "Metric choice changes the calculation."
    assert body["active_confirmation"]["related_task_id"] == 12
    assert body["active_confirmation"]["related_spec_id"] == "spec_1"
    assert body["active_confirmation"]["skippable"] is True
    assert body["queued_confirmation_count"] == 0
    assert body["failed_confirmation_count"] == 0
```

- [ ] **Step 2: Run projection test and confirm it fails**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_session_api.py::test_session_detail_returns_active_runtime_confirmation -q
```

Expected: `FAIL` because `active_confirmation` is not yet present in the session detail response.

- [ ] **Step 3: Add projection helpers**

In `src/data_agent/agent/confirmation/runtime.py`, after `confirmation_record_to_suspended_event`, add:

```python
def confirmation_record_to_session_payload(record: ConfirmationRecord) -> dict[str, Any]:
    payload = confirmation_record_to_suspended_event(record)
    payload["status"] = record.status.value
    payload["skippable"] = bool(record.skippable)
    return payload


def confirmation_session_state(service: Any, session_id: str) -> dict[str, Any]:
    from data_agent.agent.confirmation.models import ConfirmationStatus

    records = service._store(session_id).load_records()
    active = None
    queued = 0
    failed = 0
    for record in records.values():
        if record.status == ConfirmationStatus.SUSPENDED and active is None:
            active = confirmation_record_to_session_payload(record)
        elif record.status == ConfirmationStatus.PENDING:
            queued += 1
        elif record.status == ConfirmationStatus.FAILED:
            failed += 1
            if active is None:
                active = confirmation_record_to_session_payload(record)
    return {
        "active_confirmation": active,
        "queued_confirmation_count": queued,
        "failed_confirmation_count": failed,
    }
```

Keep this helper read-only. It may call the service store because `ConfirmationService` does not yet expose a public listing method; do not add a broad service API unless the implementation becomes clearer with tests.

- [ ] **Step 4: Run projection test and confirm helper alone is not enough**

Run the same command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_session_api.py::test_session_detail_returns_active_runtime_confirmation -q
```

Expected: still `FAIL` because `sessions.py` has not attached the helper result.

## Task 2: Attach Runtime State To Session Detail

**Files:**
- Modify: `src/data_agent/web/blueprints/sessions.py`
- Test: `tests/test_confirmation_session_api.py`

- [ ] **Step 1: Add failing queue/failed and legacy pending tests**

Append to `tests/test_confirmation_session_api.py`:

```python
def test_session_detail_counts_runtime_queue_and_failed_records(tmp_path, monkeypatch):
    cfg = _use_tmp_config(monkeypatch, tmp_path)
    session_id = "session_runtime_counts"
    _write_session(cfg, session_id)

    from data_agent.agent.confirmation.service import ConfirmationResolutionFailed

    from data_agent.agent.confirmation.runtime import build_action_registry
    from data_agent.agent.confirmation.service import ConfirmationService

    registry = build_action_registry()
    registry.register("fail_for_test", lambda _context, _answer: (_ for _ in ()).throw(RuntimeError("boom")))
    service = ConfirmationService(cfg.sessions_resolved, action_registry=registry)
    failed_active = _request_runtime_confirmation(
        cfg,
        session_id,
        confirmation_id="cf_failed_1",
        decision_key="failed",
        resolution_action="fail_for_test",
    )
    try:
        service.respond(session_id, failed_active.confirmation_id, "revenue", failed_active.version, "fail_key")
    except ConfirmationResolutionFailed:
        pass
    _request_runtime_confirmation(cfg, session_id, confirmation_id="cf_count_1", decision_key="count-1")

    from data_agent.web.app import create_app

    client = create_app().test_client()
    body = client.get(f"/api/sessions/{session_id}").get_json()

    assert body["active_confirmation"]["confirmation_id"] == "cf_failed_1"
    assert body["queued_confirmation_count"] == 1
    assert body["failed_confirmation_count"] == 1


def test_session_detail_ignores_legacy_pending_confirmations(tmp_path, monkeypatch):
    cfg = _use_tmp_config(monkeypatch, tmp_path)
    session_id = "session_legacy_pending"
    _write_session(cfg, session_id)
    session_dir = cfg.sessions_resolved / session_id
    (session_dir / "analysis_state.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "pending_confirmations": [
                    {"id": "legacy_cf", "status": "pending", "question": "Legacy question?"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from data_agent.web.app import create_app

    client = create_app().test_client()
    body = client.get(f"/api/sessions/{session_id}").get_json()

    assert body["active_confirmation"] is None
    assert body["queued_confirmation_count"] == 0
    assert body["failed_confirmation_count"] == 0
```

- [ ] **Step 2: Run session API tests and confirm failures**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_session_api.py -q
```

Expected: session detail tests fail until `sessions.py` attaches runtime state.

- [ ] **Step 3: Attach runtime confirmation state in `get_session`**

In `src/data_agent/web/blueprints/sessions.py`, import nothing at module import time. Inside `get_session`, before `return jsonify(data)`, add:

```python
    from data_agent.agent.confirmation.runtime import (
        build_action_registry,
        confirmation_session_state,
    )
    from data_agent.agent.confirmation.service import ConfirmationService

    service = ConfirmationService(
        cfg.sessions_resolved,
        action_registry=build_action_registry(),
    )
    data.update(confirmation_session_state(service, session_id))
```

This must use `cfg.sessions_resolved`, not `Path("./sessions")`, so tests and configured deployments read the same runtime event store.

- [ ] **Step 4: Run session API tests and confirm pass**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_session_api.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 1 and Task 2**

Run:

```powershell
git add src/data_agent/agent/confirmation/runtime.py src/data_agent/web/blueprints/sessions.py tests/test_confirmation_session_api.py
git commit -m "feat: expose runtime confirmation state in sessions"
```

## Task 3: Restore Frontend Confirmation Cards From Session Detail

**Files:**
- Modify: `src/data_agent/web/static/js/app.js`
- Test: `tests/test_web_overhaul.py`

- [ ] **Step 1: Add failing static frontend tests**

Append to `tests/test_web_overhaul.py`:

```python
class TestConfirmationRuntimeRestore:
    def test_session_load_restores_active_confirmation(self, js):
        assert "_restoreActiveConfirmation" in js
        assert "data.active_confirmation" in js
        assert "_confirmationFromPayload(data.active_confirmation)" in js

    def test_resume_payload_uses_runtime_confirmation_contract(self, js):
        assert "confirmation_id: confirmation.confirmation_id" in js
        assert "expected_version: confirmation.version" in js
        assert "idempotency_key: confirmation._idempotencyKey" in js
        assert "suspension_id: suspensionId" not in js
```

- [ ] **Step 2: Run frontend static tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_web_overhaul.py::TestConfirmationRuntimeRestore -q
```

Expected: `FAIL` because the helper functions and runtime-only payload are not present.

- [ ] **Step 3: Add frontend helper functions**

In `src/data_agent/web/static/js/app.js`, after `_restoreState(sid)`, add:

```javascript
        _confirmationFromPayload(payload) {
            if (!payload) return null;
            return {
                confirmation_id: payload.confirmation_id,
                suspension_id: payload.confirmation_id,
                version: payload.version || 1,
                status: payload.status || 'suspended',
                question: payload.question || '',
                options: payload.options || [],
                context: payload.context || '',
                multi_select: !!payload.multi_select,
                confirmation_type: payload.confirmation_type || '',
                blocking_reason: payload.blocking_reason || '',
                related_task_id: payload.related_task_id || '',
                related_spec_id: payload.related_spec_id || '',
                skippable: payload.skippable !== false,
                _resuming: false,
                _error: '',
                _idempotencyKey: '',
                _state: this._initConfirmationState(),
            };
        },

        _restoreActiveConfirmation(state, payload) {
            const confirmation = this._confirmationFromPayload(payload);
            if (!confirmation) return;
            let turn = state.turns[state.turns.length - 1];
            if (!turn || turn.role !== 'assistant') {
                turn = {
                    role: 'assistant',
                    content: '',
                    roundIndex: this._countUserTurns(state.turns),
                    toolCalls: [],
                    artifacts: [],
                    confirmation: null,
                    isThinking: false,
                    thinkingText: '',
                    _copied: false,
                };
                state.turns.push(turn);
            }
            turn.isThinking = false;
            turn.confirmation = confirmation;
        },
```

- [ ] **Step 4: Restore from `switchSession` data**

In `switchSession(sessionId)`, after reconstructing turns and before token usage handling, add:

```javascript
                    this._restoreActiveConfirmation(state, data.active_confirmation);
                    this.turns = state.turns;
```

Also call the same helper when `state.turns.length !== 0` but fresh session detail is needed. The simplest safe implementation is to always fetch `/api/sessions/${sessionId}` in `switchSession`, then reconstruct only when needed:

```javascript
            let data = null;
            try {
                const res = await fetch(`/api/sessions/${sessionId}`);
                data = await res.json();
                if (state.turns.length === 0 && data.messages) {
                    state.turns = this._reconstructTurns(data.messages);
                }
                this._restoreActiveConfirmation(state, data.active_confirmation);
                this.turns = state.turns;
                this.activeProjectName = data.project_name || '';
                if (data.token_usage) {
                    state.tokenPct = data.token_usage.pct || 0;
                    state.tokenSupported = true;
                } else {
                    state.tokenPct = 0;
                    state.tokenSupported = false;
                }
                this.tokenPct = state.tokenPct;
                this.tokenSupported = state.tokenSupported;
                this.connectionError = '';
            } catch {
                this.connectionError = '加载会话失败';
            }
```

Keep the existing artifact, analysis, trust, and task loading after this block.

- [ ] **Step 5: Update live SSE confirmation shape**

In `_handleEvent('suspended')`, replace the inline object with:

```javascript
                    turn.confirmation = this._confirmationFromPayload({
                        confirmation_id: data.confirmation_id || data.suspension_id,
                        version: data.version || 1,
                        status: 'suspended',
                        question: data.question,
                        options: data.options || [],
                        context: data.context || '',
                        multi_select: !!data.multi_select,
                        confirmation_type: data.confirmation_type || '',
                        blocking_reason: data.blocking_reason || '',
                        related_task_id: data.related_task_id || '',
                        related_spec_id: data.related_spec_id || '',
                        skippable: data.skippable !== false,
                    });
```

- [ ] **Step 6: Run frontend static tests and confirm pass**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_web_overhaul.py::TestConfirmationRuntimeRestore -q
```

Expected: `2 passed`.

## Task 4: Submit Runtime Resume Requests Only

**Files:**
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `src/data_agent/web/blueprints/chat.py`
- Test: `tests/test_web_overhaul.py`
- Test: `tests/test_confirmation_runtime.py`

- [ ] **Step 1: Add failing backend validation tests**

Append to `tests/test_confirmation_runtime.py`:

```python
def test_resume_turn_rejects_legacy_suspension_file(tmp_path, monkeypatch):
    from data_agent.agent.loop import SuspendedForConfirmation, SuspensionManager

    _patch_direct_question_tool(monkeypatch, tmp_path)
    SuspensionManager(tmp_path).save(
        SuspendedForConfirmation(
            suspension_id="legacy_only",
            question="Legacy question?",
            options=[],
            context="",
            snapshot={"messages": []},
        )
    )
    loop = AgentLoop(client=None, session_id="resume_rejects_legacy")

    result = loop.resume_turn("legacy_only", "answer")

    assert isinstance(result, FinalResponse)
    assert "runtime confirmation legacy_only not found" in result.content


def test_resume_turn_requires_runtime_idempotency_key(tmp_path, monkeypatch):
    _patch_direct_question_tool(monkeypatch, tmp_path)
    loop = AgentLoop(client=None, session_id="resume_requires_key")
    suspended = loop._execute_single_tool(_ToolCall(), [_ToolCall()], 0)

    result = loop.resume_turn(
        suspended.confirmation_id,
        "revenue",
        expected_version=suspended.version,
        idempotency_key="",
    )

    assert isinstance(result, FinalResponse)
    assert "idempotency_key is required" in result.content
```

- [ ] **Step 2: Run backend validation tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_runtime.py::test_resume_turn_rejects_legacy_suspension_file tests/test_confirmation_runtime.py::test_resume_turn_requires_runtime_idempotency_key -q
```

Expected: at least one `FAIL` because legacy fallback and generated idempotency keys still exist.

- [ ] **Step 3: Update existing runtime resume tests to the new contract**

In `tests/test_confirmation_runtime.py`, update existing successful resume calls so they pass the runtime version and an explicit idempotency key:

```python
result = loop.resume_turn(
    suspended.confirmation_id,
    "revenue",
    expected_version=suspended.version,
    idempotency_key="answer_key",
)
```

For streaming success tests:

```python
events = list(
    loop.resume_turn_streaming(
        suspended.confirmation_id,
        "revenue",
        expected_version=suspended.version,
        idempotency_key="stream_answer_key",
    )
)
```

For the idempotency test, keep reusing the same `idempotency_key` on the repeated call:

```python
loop.resume_turn(
    suspended.confirmation_id,
    "revenue",
    expected_version=suspended.version,
    idempotency_key="client_retry_key",
)
repeated = loop.resume_turn(
    suspended.confirmation_id,
    "revenue",
    expected_version=suspended.version,
    idempotency_key="client_retry_key",
)
```

Expected: old tests now express the Stage 2C contract instead of preserving the legacy fallback behavior.

- [ ] **Step 4: Update frontend resume payload**

In `resumeConfirmation`, change the signature to:

```javascript
        async resumeConfirmation(userResponse, confirmation = null) {
```

At the start of the function, after finding `turn`, require a runtime confirmation:

```javascript
            confirmation = confirmation || turn?.confirmation;
            if (!confirmation || !confirmation.confirmation_id) {
                if (turn?.confirmation) turn.confirmation._error = '确认问题已失效，请重新加载会话。';
                state._resuming = false;
                return;
            }
            if (!confirmation._idempotencyKey) {
                confirmation._idempotencyKey = `web_${Date.now()}_${Math.random().toString(16).slice(2)}`;
            }
```

Replace the request body with:

```javascript
                    body: JSON.stringify({
                        session_id: this.currentSessionId,
                        confirmation_id: confirmation.confirmation_id,
                        expected_version: confirmation.version,
                        idempotency_key: confirmation._idempotencyKey,
                        user_response: userResponse,
                    }),
```

Update all callers:

```javascript
this.resumeConfirmation(response, c);
this.resumeConfirmation('skipped', c);
this.resumeConfirmation('cancelled', c);
```

Do not send `suspension_id`.

- [ ] **Step 5: Keep card visible on resume validation errors**

In `resumeConfirmation`, move the visible user turn append until after `response.ok` is known, or restore the confirmation in the error branch. Use this error branch:

```javascript
                if (!response.ok) {
                    const errData = await response.json().catch(() => ({ error: response.statusText }));
                    if (turn) {
                        turn.confirmation = confirmation;
                        turn.confirmation._resuming = false;
                        turn.confirmation._error = errData.error || '确认失败，请重试。';
                    }
                    state._resuming = false;
                    this.turns = [...state.turns];
                    return;
                }
```

- [ ] **Step 6: Validate resume API preflight in Flask**

In `src/data_agent/web/blueprints/chat.py`, replace request parsing in `resume_chat` with:

```python
    data = request.get_json(force=True)
    session_id = str(data.get("session_id") or "").strip()
    confirmation_id = str(data.get("confirmation_id") or "").strip()
    expected_version = data.get("expected_version")
    idempotency_key = str(data.get("idempotency_key") or "").strip()
    user_response = data.get("user_response", "")

    if not confirmation_id:
        return jsonify({"error": "confirmation_id is required"}), 400
    if expected_version is None:
        return jsonify({"error": "expected_version is required"}), 400
    if not idempotency_key:
        return jsonify({"error": "idempotency_key is required"}), 400
    try:
        expected_version = int(expected_version)
    except (TypeError, ValueError):
        return jsonify({"error": "expected_version must be an integer"}), 400
```

Then, after fetching `agent_loop`, check runtime existence before starting the thread:

```python
    try:
        agent_loop._confirmation_runtime().get(agent_loop.session_id, confirmation_id)
    except KeyError:
        return jsonify({"error": f"runtime confirmation {confirmation_id} not found"}), 404
```

- [ ] **Step 7: Remove runtime fallback in `AgentLoop`**

In `src/data_agent/agent/loop.py`, replace `_load_confirmation_for_resume` with:

```python
    def _load_confirmation_for_resume(
        self,
        confirmation_id: str,
    ) -> SuspendedForConfirmation | None:
        return self._runtime_suspension_for_resume(confirmation_id)
```

Update `resume_turn`:

```python
        susp = self._load_confirmation_for_resume(suspension_id)
        if not susp:
            return FinalResponse(content=f"Error: runtime confirmation {suspension_id} not found")
        try:
            susp = self._resolve_runtime_confirmation(
                susp,
                user_response,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            return FinalResponse(content=f"Error: {exc}")
```

Update `resume_turn_streaming` similarly:

```python
        susp = self._load_confirmation_for_resume(suspension_id)
        if not susp:
            yield {"type": "error", "message": f"runtime confirmation {suspension_id} not found"}
            return
        try:
            susp = self._resolve_runtime_confirmation(
                susp,
                user_response,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
            return
```

Remove `is_legacy` branches and all `SuspensionManager(...).remove(...)` calls from resume paths.

- [ ] **Step 8: Make idempotency key mandatory in runtime resolution**

In `_resolve_runtime_confirmation`, delete fallback generation:

```python
        idempotency_key = str(idempotency_key or "").strip()
```

Keep service calls as:

```python
                idempotency_key,
```

because `ConfirmationService._idempotency_key()` already raises `ConfirmationAnswerError("idempotency_key is required")`.

- [ ] **Step 9: Run focused resume tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_runtime.py::test_resume_turn_rejects_legacy_suspension_file tests/test_confirmation_runtime.py::test_resume_turn_requires_runtime_idempotency_key tests/test_web_overhaul.py::TestConfirmationRuntimeRestore -q
```

Expected: selected tests pass.

- [ ] **Step 10: Commit Task 3 and Task 4**

Run:

```powershell
git add src/data_agent/web/static/js/app.js src/data_agent/web/blueprints/chat.py src/data_agent/agent/loop.py tests/test_web_overhaul.py tests/test_confirmation_runtime.py
git commit -m "feat: resume runtime confirmations without legacy fallback"
```

## Task 5: Normalize Workbench Confirmation Wording

**Files:**
- Modify: `src/data_agent/web/blueprints/sessions.py`
- Modify: `src/data_agent/web/static/js/app.js`
- Test: `tests/test_web_workbench_parity.py`
- Test: `tests/test_web_overhaul.py`

- [ ] **Step 1: Update analysis summary test expectation**

In `tests/test_web_workbench_parity.py`, change `test_web_analysis_state_endpoint_and_reset` assertions to:

```python
        assert body["summary"]["workflow_notes"] == 1
        assert body["summary"]["pending_confirmations"] == 0
```

This makes legacy `AnalysisSessionState.pending_confirmations` visible as workflow metadata, not as active user-answerable confirmation state.

- [ ] **Step 2: Add static UI wording test**

Append to `tests/test_web_overhaul.py`:

```python
class TestConfirmationWorkbenchWording:
    def test_workbench_distinguishes_workflow_notes_from_active_confirmations(self, js):
        assert "workflow_notes" in js
        assert "流程备注" in js or "Workflow notes" in js
```

- [ ] **Step 3: Run wording tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_web_workbench_parity.py::test_web_analysis_state_endpoint_and_reset tests/test_web_overhaul.py::TestConfirmationWorkbenchWording -q
```

Expected: failures until API and JS wording change.

- [ ] **Step 4: Change analysis state summary**

In `_analysis_state_payload` in `src/data_agent/web/blueprints/sessions.py`, return:

```python
            "pending_confirmations": 0,
            "workflow_notes": len(pending),
```

Do not delete `state.pending_confirmations` from `state.to_dict()`. Historical metadata remains readable.

- [ ] **Step 5: Change frontend summary defaults and labels**

In `analysisSummary` default in `src/data_agent/web/static/js/app.js`, add:

```javascript
                workflow_notes: 0,
```

Find UI label/help text that describes confirmations as needing user action and change the relevant visible copy to distinguish:

```javascript
confirmations: '这是什么：当前运行时确认问题会阻塞继续分析；历史流程备注只记录风险或待澄清信息。你可以怎么做：回答聊天中的确认卡片，或查看流程备注理解分析限制。'
```

If the template directly renders `pending_confirmations`, route that display to `workflow_notes` for the workbench side panel.

- [ ] **Step 6: Run wording tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_web_workbench_parity.py::test_web_analysis_state_endpoint_and_reset tests/test_web_overhaul.py::TestConfirmationWorkbenchWording -q
```

Expected: selected tests pass.

- [ ] **Step 7: Commit Task 5**

Run:

```powershell
git add src/data_agent/web/blueprints/sessions.py src/data_agent/web/static/js/app.js tests/test_web_workbench_parity.py tests/test_web_overhaul.py
git commit -m "fix: separate workflow notes from active confirmations"
```

## Task 6: Regression Verification

**Files:**
- Modify: no production files unless verification exposes a defect
- Optional docs: `docs/superpowers/specs/2026-06-26-confirmation-runtime-stage-2c-clean-cutover-design.md`

- [ ] **Step 1: Run confirmation regression gate**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
$tests = Get-ChildItem tests -Filter 'test_confirmation_*.py' | ForEach-Object { $_.FullName }
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest @tests tests/test_interaction.py tests/test_execution_control.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run web/workbench regression gate**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_confirmation_session_api.py tests/test_web_overhaul.py::TestConfirmationRuntimeRestore tests/test_web_overhaul.py::TestConfirmationWorkbenchWording tests/test_web_workbench_parity.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Check legacy root suspension writes**

Run:

```powershell
Get-ChildItem -Path . -Recurse -Filter 'suspension_*.json' | Select-Object -ExpandProperty FullName
```

Expected: no files created by the test run under the worktree. If an existing fixture appears, inspect it before deleting or changing anything.

- [ ] **Step 4: Run whitespace and status checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors. `git status --short` should show only files intentionally changed by the current task.

- [ ] **Step 5: Record verification result**

Create or update a short verification note under `docs/superpowers/specs/` only if a test limitation appears. Use this format:

```markdown
## Stage 2C Verification

- Confirmation runtime regression: passed.
- Web/workbench regression: passed.
- Legacy suspension scan: no production root suspension files created.
- Known limitation: none observed in this run.
```

- [ ] **Step 6: Final commit**

If Step 5 creates or updates a note:

```powershell
git add docs/superpowers/specs/2026-06-26-confirmation-runtime-stage-2c-clean-cutover-design.md
git commit -m "docs: record confirmation runtime stage 2c verification"
```

If no note is needed, skip this commit and keep the branch clean after Task 5.

## Self-Review Checklist

- Spec coverage:
  - Runtime-only active confirmation authority: Tasks 1, 2, and 4.
  - Refresh/session restore: Task 3.
  - Resume rejects non-runtime IDs: Task 4.
  - Final guards remain runtime-only: covered by the existing `test_sync_loop_blocks_final_response_when_runtime_confirmation_pending` and `test_stream_loop_blocks_final_response_when_runtime_confirmation_pending` regression gate in Task 6.
  - No root `suspension_*.json` production path: Task 4 and Task 6.
  - Legacy pending cannot create visible blocker: Task 2 and Task 5.

- Risk controls:
  - Each production change is preceded by a failing test.
  - Frontend and backend contracts are checked separately.
  - Resume request validation happens before the SSE worker starts.
  - Legacy historical conversations remain readable because session history loading is not changed.

- Execution order:
  - Do Tasks 1 and 2 together because the projection helper is only useful once session detail exposes it.
  - Do Tasks 3 and 4 together because frontend resume payload and backend resume validation must agree.
  - Do Task 5 after runtime restore works, so wording changes do not mask missing active confirmation cards.
  - Do Task 6 before claiming Stage 2C complete.
