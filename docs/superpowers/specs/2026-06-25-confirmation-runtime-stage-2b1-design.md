# Confirmation Runtime Stage 2B-1 Design

**Date:** 2026-06-25

**Status:** Draft for user review

**Scope:** Direct question path cutover only

## 1. Goal

Connect the verified Confirmation Runtime kernel to the concrete path that
actually displays a question to the user:

```text
ask_user_question -> AgentLoop suspension -> SSE question card -> /chat/resume
```

After this stage, a visible direct question must be backed by
`ConfirmationService`, not by root-level `suspension_*.json` files or direct
mutation of `AnalysisSessionState.pending_confirmations`.

## 2. Why This Is a Separate Stage

The current project has two different confirmation meanings:

- **Interactive confirmation:** a real question is shown and the turn waits for
  a user answer.
- **Advisory/gating metadata:** `pending_confirmations`, recommendation gates,
  task nodes, and file-relationship status describe risk or incomplete
  decisions.

Mixing both in one change would be unsafe. Stage 2B-1 cuts over only the real
interactive question path. Stage 2B-2 will convert confirmation producers such
as `question_need_detector`, high-risk method selection, cleaning decisions, and
file relationships. Stage 2C will restore questions after refresh/restart and
remove obsolete client assumptions.

## 3. In Scope

Stage 2B-1 changes:

- `ask_user_question` remains the tool model calls, but it must no longer create
  or depend on root-level suspension files.
- Agent Loop converts `UserConfirmationRequired` into a `QuestionCandidate` and
  submits it to `ConfirmationService`.
- Agent Loop checkpoints the service and emits the persisted suspended record
  as the SSE `suspended` event.
- `/api/chat/resume` answers the active confirmation through
  `ConfirmationService.respond()`.
- The final-response guard refuses to return a normal final answer while the
  session has `pending`, `suspended`, `response_received`, `applying`, or
  `failed` confirmation records.
- Direct-answer resolution uses registered actions, not arbitrary JSON merging.
- Existing CLI and non-streaming paths follow the same service-backed
  transition as streaming paths.

## 4. Out of Scope

Stage 2B-1 does not:

- convert `question_need_detector` into a confirmation producer;
- convert `data_io` file-relationship confirmation creation;
- delete `AnalysisSessionState.pending_confirmations`;
- redesign Trust View, session side panels, or data scope UI;
- add session API restoration fields;
- implement browser refresh restoration or SSE replay;
- implement server-restart recovery for in-flight continuation;
- migrate or resume historical `suspension_*.json` files.

Those remain Stage 2B-2 or Stage 2C work.

## 5. Runtime Flow

### 5.1 Creating a Direct Question

When `ask_user_question` raises `UserConfirmationRequired`, Agent Loop builds a
candidate with:

- `source`: `ask_user_question`;
- `operation`: `direct_user_question`;
- `decision_key`: stable hash of session ID, confirmation type, question text,
  options, related task/spec IDs, and current message version;
- `question`: the user-facing question;
- `decision_impact`: `blocking_reason` when supplied, otherwise a generic
  statement that the current operation cannot continue without the answer;
- `answer_mode`: single select, multi-select, or free text based on the tool
  arguments;
- `options`: normalized option values and labels;
- `blocking_surfaces`: at least `agent_turn`;
- `resolution_action`: derived from confirmation type and state-update payload;
- `resolution_params`: typed parameters needed by the action.

Then Agent Loop calls:

```text
ConfirmationService.request(candidate)
ConfirmationService.checkpoint(session_id)
```

Only the returned suspended record is emitted to SSE or returned by the
non-streaming loop.

### 5.2 Answering

`/api/chat/resume` receives:

```json
{
  "session_id": "...",
  "confirmation_id": "...",
  "expected_version": 2,
  "user_response": "...",
  "idempotency_key": "..."
}
```

For this stage, the API may continue accepting `suspension_id` from the existing
client, but the server treats it as a confirmation ID. It must not load
root-level suspension files.

The endpoint calls `ConfirmationService.respond()`. If the response resolves,
Agent Loop appends a structured confirmation-response message and continues the
turn from the in-memory loop context. If the service reports validation,
version, action, or store errors, the turn does not resume silently.

### 5.3 Final Guard

Before returning any final text, Agent Loop asks the confirmation service for
the current blocking checkpoint. If a record is active or failed, the loop
returns a suspended/error state instead of a final answer.

This guard is enforcement only. It does not create new questions.

## 6. Resolution Actions

Stage 2B-1 must not preserve arbitrary `state_updates` as a write path. It
registers a minimal set of typed actions:

- `record_confirmation_answer`: stores the answer in the confirmation record
  and appends the answer to the resumed message context; it does not mutate
  analysis state.
- `confirm_method`: applies the existing method-confirmation semantics through
  a typed parameter object.
- `resolve_file_relationship`: may be registered only as a typed action for
  direct questions that already carry a relationship ID. Automatic
  file-relationship producers remain Stage 2B-2.
- `set_analysis_stage`: may update only whitelisted stage/data-state fields
  using enum-validated values.

If `ask_user_question` supplies an unrecognized or unsafe `state_updates`
payload, the adapter must choose `record_confirmation_answer` or reject the
candidate. It must not pass the raw JSON into `AnalysisSessionState`.

## 7. Legacy Removal in This Stage

Stage 2B-1 removes production use of:

- `SuspensionManager.save()`;
- `SuspensionManager.load()` inside resume;
- `SuspensionManager.remove()` inside resume;
- root-level `sessions/suspension_<id>.json` as the active question store.

`SuspensionManager` may remain temporarily only for historical tests or until
Stage 2C deletes obsolete code. New production direct questions must not call it.

Stage 2B-1 also stops direct-question paths from calling
`AnalysisSessionState.add_confirmation()` or mutating a pending item with a
`suspension_id`. Existing advisory/gating code can remain untouched until
Stage 2B-2.

## 8. Error Handling

- Policy advisory or rejection: return a tool error explaining that the question
  is not actionable; do not continue with a hidden blocker.
- Store integrity failure: emit an error event and stop the turn.
- Invalid answer: keep the confirmation suspended and return a validation error.
- Stale or duplicate response: return a conflict-style error with current state
  for API callers; streaming emits an error and does not continue.
- Resolution action failure: persist `failed`; do not resume the turn.
- Missing in-memory loop for resume: return a clear error. Durable restart
  recovery remains Stage 2C.

## 9. Testing

Required tests:

- direct `ask_user_question` streaming creates a confirmation event log and no
  root-level suspension file;
- SSE `suspended` payload comes from the persisted confirmation record and
  includes ID, version, question, options, type, and blocking reason;
- `/chat/resume` resolves the record through `ConfirmationService.respond()`;
- duplicate resume with the same idempotency key applies the action once;
- stale version or invalid option does not resume;
- final guard blocks final text while a confirmation is pending, suspended,
  applying, or failed;
- non-streaming loop and streaming loop use the same adapter;
- legacy `SuspensionManager` tests are updated or isolated as historical-storage
  tests, not production-path tests;
- existing Stage 2A confirmation tests still pass;
- neighboring interaction, execution-control, web chat, and SSE tests pass.

## 10. Acceptance Criteria

Stage 2B-1 is complete only when:

1. every new direct question visible to the user has a corresponding
   `sessions/<session_id>/confirmations/events.jsonl` record;
2. no new direct question writes a root-level `suspension_*.json` file;
3. `/chat/resume` answers through `ConfirmationService.respond()`;
4. direct-question resolution uses registered actions only;
5. final responses are blocked while direct confirmation records remain
   unresolved or failed;
6. old advisory/gating paths remain behaviorally unchanged;
7. tests prove streaming and non-streaming paths share the same confirmation
   transition behavior.

## 11. Open Constraints for the Implementation Plan

The implementation plan should keep this stage small. If a test requires
changing `question_need_detector`, multi-file relationship producers, Trust
View, or client restoration, that test belongs to Stage 2B-2 or 2C rather than
this batch.
