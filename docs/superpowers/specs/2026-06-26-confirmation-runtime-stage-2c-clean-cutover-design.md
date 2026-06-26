# Confirmation Runtime Stage 2C Clean Cutover Design

**Date:** 2026-06-26

**Status:** Approved direction, design draft for implementation planning

**Scope:** Clean confirmation cutover, runtime restoration, and legacy active-confirmation removal

## 1. Decision Record

The project currently has little historical usage, so Stage 2C should solve the
confirmation lifecycle cleanly instead of preserving compatibility with old
active-confirmation paths.

Approved decisions:

- Historical unfinished `suspension_*.json` questions are not migrated and are
  not resumable.
- Historical conversations remain readable.
- `ConfirmationService` is the only authority for active, answerable,
  blocking confirmations.
- `/api/chat/resume` should only answer runtime confirmation records.
- `AnalysisSessionState.pending_confirmations` must not be used as an active
  blocker or visible question source.
- Any remaining `pending_confirmations` usage is temporary producer metadata
  and should later be renamed or redesigned.

This document exists to preserve the context and avoid losing the plan during
conversation compaction.

## 2. Current State After Stage 2B

Implemented in the current branch:

- Direct `ask_user_question` requests are adapted into runtime
  `QuestionCandidate` records.
- Automatic hard questions from `question_need_detector` and answerable legacy
  producer metadata are adapted into runtime records.
- Runtime confirmations are persisted under:

```text
sessions/<session_id>/confirmations/events.jsonl
sessions/<session_id>/confirmations/snapshot.json
```

- Sync and streaming agent loops checkpoint runtime confirmations before
  returning final text.
- SSE `suspended` events include `confirmation_id`, `suspension_id`,
  `version`, question payload, type, and related IDs.
- The Web client already stores `confirmation_id` and `version` on live SSE
  confirmation cards.

Known leftovers:

- `SuspensionManager` still exists and is still used as a fallback in resume.
- `/api/chat/resume` still accepts `suspension_id` as a legacy alias.
- Session APIs do not expose canonical runtime confirmation state.
- Frontend refresh/session switching cannot reconstruct an active confirmation
  card from session state.
- Some Trust View / analysis workbench surfaces still count
  `pending_confirmations`, which is no longer the active confirmation source.
- `_register_confirmation()` and `_resolve_confirmation()` remain for legacy
  CLI/old suspension flows.

## 3. Goal

After Stage 2C:

1. A visible, answerable, blocking question can only come from
   `ConfirmationService`.
2. Refreshing the page or re-opening a session restores the active runtime
   confirmation card.
3. `/api/chat/resume` rejects non-runtime IDs instead of silently falling back
   to old suspension files.
4. Final answer guards use runtime confirmation state only.
5. No production path writes or reads root-level `suspension_*.json` files for
   active confirmation behavior.
6. Legacy `pending_confirmations` cannot create user-visible blocker state.

## 4. Non-Goals

Stage 2C does not:

- redesign the multi-file analysis scope UI;
- rename or delete the `pending_confirmations` field everywhere;
- remove Trust View or analysis-state historical metadata;
- implement server-side continuation replay after a process restart;
- replay SSE event history;
- migrate historical active confirmations;
- solve multi-file relationship inference.

Those belong to later cleanup or Stage 3 multi-file scope work.

## 5. Runtime Session Contract

The session detail endpoint should expose canonical confirmation state.

Recommended shape:

```json
{
  "session_id": "abc123",
  "messages": [],
  "active_confirmation": {
    "confirmation_id": "auto_...",
    "suspension_id": "auto_...",
    "version": 2,
    "status": "suspended",
    "question": "Which route should be used?",
    "options": [
      {
        "label": "Trend",
        "value": "trend",
        "description": ""
      }
    ],
    "context": "",
    "multi_select": false,
    "confirmation_type": "route_selection",
    "blocking_reason": "Different routes change the analysis output.",
    "related_task_id": 0,
    "related_spec_id": "",
    "skippable": true
  },
  "queued_confirmation_count": 0,
  "failed_confirmation_count": 0
}
```

Rules:

- `active_confirmation` is `null` when no runtime record is `suspended` or
  failed-blocking.
- `queued_confirmation_count` counts runtime `pending` records that are not
  currently suspended.
- `failed_confirmation_count` counts runtime `failed` records that still block
  continuation.
- The endpoint must not infer active confirmation state from chat text,
  `pending_confirmations`, Trust View, or root-level suspension files.

## 6. Frontend Restoration Behavior

When loading or switching to a session:

1. The frontend loads session detail as it does today.
2. If `active_confirmation` is present, the latest assistant turn receives a
   restored `turn.confirmation` object using the same shape as live SSE
   `suspended` events.
3. The restored card is visually identical to the live SSE card.
4. Submitting the answer calls `/api/chat/resume` with:

```json
{
  "session_id": "abc123",
  "confirmation_id": "auto_...",
  "expected_version": 2,
  "idempotency_key": "client-generated-stable-key",
  "user_response": "trend"
}
```

5. The frontend should not send `suspension_id` once Stage 2C is complete.

Error handling:

- If resume returns a validation error, keep the confirmation card visible and
  show a user-facing error near the card.
- If resume returns stale version/conflict, reload session confirmation state
  and show the current card.
- If the confirmation no longer exists, clear the card after reloading session
  state and show a short message that the question is no longer active.

## 7. Resume API Contract

`POST /api/chat/resume` accepts only runtime confirmation identifiers.

Request:

```json
{
  "session_id": "abc123",
  "confirmation_id": "auto_...",
  "expected_version": 2,
  "idempotency_key": "client-generated-stable-key",
  "user_response": "trend"
}
```

Rules:

- `confirmation_id` is required.
- `expected_version` is required for normal submit/skip/cancel actions.
- `idempotency_key` is required. The frontend should generate one stable key per
  submit attempt and reuse it on retry.
- `suspension_id` is no longer accepted as a public contract.
- The endpoint must not call `SuspensionManager.load()`.
- If the runtime record is missing, return a clear 404-style error.
- If the version is stale, return a conflict-style error with enough state for
  the client to reload.
- If answer validation fails, return a validation error and keep the record
  suspended.
- If action application fails, persist `failed` and return an error without
  resuming the turn.

Streaming response can remain SSE, but the preflight validation should fail
before creating a streaming response when the request is obviously malformed
or the confirmation does not exist.

## 8. Legacy Path Removal

Remove production usage of:

- `SuspensionManager.save()` for active questions;
- `SuspensionManager.load()` in resume;
- `SuspensionManager.remove()` in resume;
- root-level `sessions/suspension_<id>.json` as a live active-question store;
- `/api/chat/resume` fallback from runtime ID to legacy suspension ID;
- active blocker logic that reads `AnalysisSessionState.pending_confirmations`
  as though it were an answerable question.

Allowed temporary leftovers:

- `SuspensionManager` class may remain for historical-storage unit tests until
  a later cleanup commit deletes those tests and the class together.
- `pending_confirmations` may remain in `AnalysisSessionState` only as
  non-active producer metadata. Any UI label must not imply the user can answer
  those records directly unless a runtime `active_confirmation` exists.
- `_register_confirmation()` and `_resolve_confirmation()` should either be
  removed from production paths or explicitly limited to CLI legacy code with a
  follow-up deletion ticket. The preferred Stage 2C outcome is no production
  callers.

## 9. Analysis Workbench and Trust View Wording

Current workbench summary counts `pending_confirmations`. After Stage 2C this
count is misleading if displayed as "waiting for confirmation".

Stage 2C should make the user-facing distinction explicit:

- Runtime `active_confirmation`: "Waiting for your answer" and shows a card.
- Runtime queued/failed confirmations: "Blocked by confirmation runtime" with
  clear action or error state.
- Legacy `pending_confirmations`: "Workflow notes" or "risk metadata", not
  "waiting for confirmation".

If wording changes are too broad for Stage 2C, the minimum requirement is that
session/detail APIs and chat confirmation cards use runtime state only. The
full side-panel redesign belongs to the multi-file scope stage.

## 10. Testing Strategy

Required new tests:

1. Session API returns `active_confirmation` from runtime `suspended` record.
2. Session API returns queue and failed counts from runtime store.
3. Session API does not create `active_confirmation` from legacy
   `pending_confirmations`.
4. Frontend session-load logic restores a confirmation card from
   `active_confirmation`.
5. `/api/chat/resume` rejects missing `confirmation_id`.
6. `/api/chat/resume` rejects an ID that exists only as a legacy
   `suspension_*.json` file.
7. `/api/chat/resume` uses `ConfirmationService.respond/skip/cancel` only.
8. Invalid answer keeps the confirmation active and visible.
9. Stale version returns conflict and does not resume the agent.
10. Any direct or automatic question path still writes
    `confirmations/events.jsonl` and does not write root `suspension_*.json`.
11. Final response guard still blocks sync and streaming final answers while a
    runtime blocker exists.

Regression gates:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
$tests = Get-ChildItem tests -Filter 'test_confirmation_*.py' | ForEach-Object { $_.FullName }
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest @tests tests/test_interaction.py tests/test_execution_control.py -q
```

Additional likely gates:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
D:\Project\Daily\data-agent\.venv\Scripts\python.exe -m pytest tests/test_web_workbench_parity.py tests/test_trust_view.py tests/test_analysis_state_v2.py -q
```

If `tests/test_sse_reactivity.py` is still blocked by the missing
`reference/workspace/test_sales.csv` fixture in the isolated worktree, document
that limitation and cover the changed frontend logic with focused static or
unit-style tests.

## 11. Implementation Slices

### Slice 1: Runtime State Projection

Add a helper that projects `ConfirmationRecord` into the session/frontend
payload. Reuse the same conversion fields as SSE `suspended` events.

Expected files:

- `src/data_agent/agent/confirmation/runtime.py`
- `src/data_agent/web/blueprints/sessions.py`
- `tests/test_confirmation_runtime.py` or a new web-session test file

### Slice 2: Session API Restoration Contract

Extend session detail payloads with `active_confirmation`,
`queued_confirmation_count`, and `failed_confirmation_count`.

Expected files:

- `src/data_agent/web/blueprints/sessions.py`
- existing session/web parity tests

### Slice 3: Frontend Card Restoration

Make the Web client restore `turn.confirmation` from session
`active_confirmation`.

Expected files:

- `src/data_agent/web/static/js/app.js`
- focused frontend/static tests

### Slice 4: Resume API Clean Cutover

Remove legacy resume fallback and require runtime fields.

Expected files:

- `src/data_agent/web/blueprints/chat.py`
- `src/data_agent/agent/loop.py`
- confirmation/runtime tests

### Slice 5: Legacy Active Path Guardrails

Add tests proving no production path writes root `suspension_*.json` or treats
legacy pending records as active confirmation cards.

Expected files:

- `tests/test_confirmation_runtime.py`
- `tests/test_execution_control.py`
- possibly `tests/test_web_workbench_parity.py`

## 12. Acceptance Criteria

Stage 2C is complete when:

1. Refreshing a session with a suspended runtime confirmation restores the same
   confirmation card.
2. `/api/chat/resume` cannot resume legacy suspension files.
3. Runtime validation, conflict, and failure errors are visible to the user and
   do not silently continue the turn.
4. No production path writes root-level `suspension_*.json`.
5. No active blocker is inferred from `pending_confirmations`.
6. Confirmation-related regression gates pass.
7. The implementation plan and verification results are committed so future
   work can continue after context compaction.

## 13. Follow-Up After Stage 2C

After clean confirmation cutover, move to multi-file analysis scope:

- define "analysis participation scope" as the primary concept;
- stop forcing relationship inference as the first step;
- ask join/union/grain questions only immediately before operations that depend
  on them;
- redesign the right side panel around user-facing scope status rather than
  technical relationship status.

## 14. Stage 2C Verification

- Confirmation runtime regression: `158 passed in 23.13s`.
- Web/workbench regression: `10 passed in 2.63s`.
- Legacy suspension scan: historical `sessions/suspension_*.json` files still
  exist in the worktree, but `git status --short -- sessions` showed no
  modified or newly tracked session files after the regression run.
- Latest historical legacy suspension file observed during verification:
  `2026-06-25 23:25:35`.
- Known limitation: Stage 2C stops production resume fallback and validates
  runtime-only confirmation state, but it does not delete historical session
  artifacts.
