# Confirmation Runtime Design

**Date:** 2026-06-21

**Status:** Approved design; Stage 2A verified, Stage 2B and 2C pending

**Scope:** Stage 2 confirmation lifecycle only

## 1. Goal

Build one durable, auditable, fail-closed question-confirmation capability for the agent. Every confirmation source must use the same contract, persistence model, state machine, recovery behavior, and final-response guard.

The target guarantees are:

- failures block unsafe continuation;
- interrupted confirmations can be restored;
- answers and state changes are idempotent;
- every transition is auditable;
- only actionable decisions are shown to the user;
- a blocking question cannot coexist with a final answer.

This is a hard replacement of the legacy confirmation implementation. No compatibility layer, dual write, or historical-state migration is required.

## 2. Root Cause

The project currently has several mechanisms that share the word confirmation but do not share ownership or lifecycle semantics:

- `ask_user_question` raises an exception and creates a runtime suspension;
- `AnalysisSessionState.pending_confirmations` stores declarative workflow risks;
- `question_need_detector` independently identifies hard questions;
- `confirmation_policy` treats any pending record as a recommendation gate;
- tasks carry confirmation metadata;
- the Web client reconstructs questions only from live SSE events;
- suspension files are stored globally rather than within a session.

These mechanisms were added incrementally to solve local problems such as CLI questions, SSE delivery, high-risk analysis gates, method selection, cleaning decisions, and file relationships. They never became one confirmation subsystem. This causes the reported failure mode: a workflow can record pending confirmations without producing a suspension or visible question, while other surfaces still describe the session as blocked.

The architectural correction is to create one Confirmation Runtime as the only writer and transition authority.

## 3. Non-Goals

Stage 2 does not:

- change multi-file relationship classification;
- redesign the current-session data scope panel;
- change chart behavior;
- migrate or resume legacy confirmations;
- convert the whole agent to event sourcing;
- infer relationships or business decisions on the user's behalf;
- begin Stage 3 multi-file participation work.

## 4. Trigger Policy

A question is created only when all of the following are true:

1. A concrete operation is about to execute.
2. The operation lacks a necessary decision.
3. Different answers materially change the operation, result validity, side effects, or risk.
4. No reliable and explainable safe default exists.
5. The question has a concrete answer mode and actionable outcomes.
6. No still-valid answer already covers the same decision for the current data and analysis-spec version.

Valid trigger categories include:

- ambiguous core metric, time window, cohort, or comparison definition;
- unresolved semantics or cleaning policy for a required field;
- ambiguous join, union, deduplication, or aggregation grain immediately before that operation;
- predictive, causal, experimental, ROI, or other high-risk analysis immediately before execution;
- destructive, overwriting, externally visible, or otherwise consequential side effects;
- a tool result that reveals a decision required by the next dependent operation;
- an explicit user request to ask before proceeding.

The following do not trigger a confirmation:

- general uncertainty that can be stated as a limitation;
- optional future analysis paths;
- high-risk steps that have not been selected for execution;
- speculative file relationships discovered during loading;
- low-risk behavior with a safe, documented default;
- legacy pending records;
- model-generated questions that omit the affected operation or decision impact.

`ask_user_question` is not a bypass. It submits a request to the same policy and may be accepted, rejected, or downgraded to an advisory.

## 5. Decision Identity and Deduplication

Each request has a stable `decision_key` derived from:

```text
session + operation type + decision subject + data/spec version
```

The runtime uses the key to suppress duplicate questions and reuse a still-valid answer. A previous answer expires only when the relevant operation, data version, analysis specification, or decision subject materially changes.

## 6. Domain Model

The runtime uses three representations:

- `ConfirmationRequest`: validated input from a producer;
- `ConfirmationRecord`: current authoritative state;
- `ConfirmationEvent`: immutable state-transition record.

A record contains at least:

- confirmation, session, and turn IDs;
- version and decision key;
- source and related operation, tool, task, or analysis specification;
- user-facing question and decision impact;
- answer mode: single select, multi-select, or free text;
- allowed options or answer validation contract;
- blocked surfaces;
- `skippable` policy;
- typed resolution action and validated action parameters;
- lifecycle status and timestamps;
- continuation reference;
- failure and terminal-state metadata when applicable.

Informational uncertainty uses an `advisory` result and never enters the confirmation state machine.

## 7. State Machine

```text
pending
  -> suspended
  -> response_received
  -> applying
  -> resolved

pending/suspended -> skipped
pending/suspended -> cancelled
pending/suspended -> expired
applying          -> failed
```

Rules:

1. Transitions are one-way and validated against the current version.
2. One session has at most one `suspended` confirmation.
3. Additional confirmations remain pending in deterministic creation order.
4. `resolved` requires successful, idempotent application of the resolution action.
5. `failed` remains blocking until explicitly handled; the agent cannot continue silently.
6. Invalid or repeated transitions return the current state and do not apply side effects.

## 8. Components

### 8.1 ConfirmationService

The only public write and transition API:

```text
request()
checkpoint()
respond()
skip()
cancel()
expire()
restore()
```

No producer may write confirmation files or mutate confirmation status directly.

### 8.2 QuestionPolicy

Validates trigger criteria, blocked surfaces, answerability, decision reuse, skip policy, and downgrade-to-advisory behavior.

### 8.3 ConfirmationStore

Each session owns its store:

```text
sessions/<session_id>/confirmations/events.jsonl
sessions/<session_id>/confirmations/snapshot.json
```

The event log is authoritative and append-only. The snapshot is a reconstructable cache written through a temporary file and atomic replacement. Writes are protected by a per-session lock.

If the snapshot is damaged, it is rebuilt from events. If the event log has a truncated tail, valid events are read up to the last complete record and the runtime enters an explicit degraded or failed state rather than trusting partial data.

### 8.4 ResolutionActionRegistry

Replaces arbitrary `state_updates` JSON with registered, typed, idempotent handlers such as:

```text
choose_metric
choose_time_window
approve_cleaning
confirm_method
approve_join_grain
cancel_operation
```

Handlers validate answers and parameters before applying state changes. Every invocation uses a resolution ID so crash recovery cannot apply the same side effect twice.

### 8.5 ContinuationManager

Persists the safe resume point:

- session and turn IDs;
- message snapshot version;
- completed tool-call IDs;
- blocked next operation;
- original request identity;
- continuation status.

Restoration continues from persisted messages and completed tool results. It does not repeat completed tools or side effects.

## 9. Runtime Flow

```text
producer
  -> ConfirmationService.request
  -> QuestionPolicy validation
  -> persist requested event
  -> checkpoint selects queue head
  -> persist suspended event
  -> emit SSE or render CLI question
  -> validate user response, version, and idempotency key
  -> persist response_received event
  -> apply typed resolution action
  -> persist resolved event
  -> restore the blocked turn
```

Checkpoints run:

1. before a consequential operation;
2. after each tool result or completed parallel tool batch;
3. before requesting the next model round;
4. before returning a final response.

The final checkpoint does not invent new questions. It enforces already registered blockers.

Sync, streaming, and CLI execution use the same service and transition path. SSE and CLI are presentation adapters only.

## 10. Concurrency and Delivery

- A session exposes one active suspended confirmation.
- Pending confirmations use deterministic FIFO ordering within the blocked turn.
- Every response includes the expected record version and an idempotency key.
- The first valid response wins.
- Concurrent, duplicate, stale, or expired responses return HTTP 409 plus current state.
- SSE events carry stable event IDs so reconnects do not create duplicate cards.
- The suspended transition is persisted before an SSE event is sent.
- A failed SSE delivery leaves a recoverable suspended confirmation.

## 11. Session and Client Contract

The session API returns canonical runtime state:

```json
{
  "active_confirmation": null,
  "queued_confirmation_count": 0
}
```

The Web client restores the active question from this field. It does not infer confirmation state from chat text, Trust View, legacy pending records, or root-level suspension files.

Confirmation-card restoration is part of Stage 2 reliability. The broader side-panel information architecture remains deferred.

## 12. User Actions

- **Submit:** validate the answer, apply the resolution action, then resume.
- **Skip:** available only when `skippable=true`; record the limitation and cancel or downgrade the affected step.
- **Cancel:** terminate the blocked operation; it is not an answer value.
- **Close page:** preserve the suspended state.
- **Expire:** invalidate the question when its operation, data, or analysis specification is superseded.
- **Re-ask:** expire the old version before creating a new record linked through the decision key.

## 13. Failure Handling

The runtime is fail-closed.

| Failure | Required behavior |
|---|---|
| Incomplete question contract | Reject the request and report a producer error; do not show a partial question |
| Persistence failure | Do not emit a question or execute the blocked operation |
| SSE delivery failure | Keep the persisted suspension for refresh recovery |
| Invalid answer | Keep the question active and return a validation error |
| Duplicate or stale response | Return conflict and current state |
| Resolution handler failure | Enter `failed`; do not resume the agent |
| Crash during action application | Recover using the resolution ID and idempotent handler |
| Missing or damaged continuation | Cancel the original operation and keep an audit record |
| Damaged event store | Stop confirmation processing and report the integrity failure |
| Blocking confirmation before final response | Return the active suspension instead of a final answer |

Tasks cannot transition to complete while a required confirmation remains unresolved. Model-generated ordinary text cannot bypass the final guard.

## 14. Privacy and Observability

Logs record confirmation ID, source, operation type, transition, version, and failure reason. They do not log unrestricted free-text answers or secrets. User-facing content does not expose internal tool names, file IDs, stack traces, or storage paths.

Illegal state transitions, store-integrity failures, duplicate resolution attempts, and final-guard violations are observable errors rather than silent warnings.

## 15. Hard Cutover

Stage 2 removes the legacy production paths:

- no new writes to `AnalysisSessionState.pending_confirmations`;
- no legacy pending-confirmation reads for active gating;
- no reads or writes of root-level `suspension_*.json`;
- no legacy SSE resume protocol;
- no dual write or reverse synchronization;
- all producers use ConfirmationService or produce an advisory.

Historical conversations and artifacts remain readable. Historical pending records and suspension files are ignored, cannot be resumed, and do not block new work. They are not automatically deleted.

## 16. Delivery Stages

### Stage 2A: Domain Kernel

Implement the domain model, policy, event store, state machine, action registry, concurrency control, and unit tests. Do not connect it to production loops yet.

### Stage 2B: Runtime Cutover

Connect Agent Loop, tool execution, question detection, CLI, streaming, final-response guarding, and all confirmation producers. Delete legacy production reads and writes.

### Stage 2C: Recovery and Client

Add session API state, server-restart recovery, confirmation-card reconstruction, idempotent response handling, SSE replay behavior, and removal of obsolete client paths.

Each stage is implemented with TDD, committed independently, and followed by targeted and full regression tests. A failed stage blocks the next stage.

## 17. Test Strategy

### State Machine

Test every legal transition, every illegal transition, record-version conflicts, deduplication, queue ordering, and the single-suspension invariant.

### Persistence and Recovery

Test damaged snapshots, truncated JSONL tails, write failures, crashes before and after action application, action replay, restart recovery, duplicate answers, and concurrent clients.

### End-to-End Interaction

For sync, streaming, and CLI modes, verify:

```text
create question
-> suspend current turn
-> present question
-> refresh or restart
-> restore the same question
-> accept one answer
-> apply one action
-> resume the original operation
-> allow final response
```

The matrix includes direct model questions, detector questions, post-tool questions, queued questions, skip, cancel, expire, session switching, multiple tabs, final-response blocking, and task completion blocking.

## 18. Acceptance Criteria

1. No actionable pending state exists without a visible and answerable question.
2. No final response is produced while a blocking confirmation exists.
3. Refresh and service restart restore the same active question.
4. A response and its state action are applied at most once.
5. One session never exposes competing suspended questions.
6. Every confirmation producer uses the same contract and service.
7. Legacy confirmation paths have no production readers or writers.
8. Invalid state transitions and store corruption fail explicitly.
9. Sync, streaming, CLI, reload, restart, concurrency, and failure-injection tests pass.
10. The complete project regression suite passes before Stage 3 begins.

## 19. Stage 2A Verification

Stage 2A implements the dormant domain kernel only. It does not connect any
Agent Loop, CLI, SSE, Web API, task, or legacy confirmation producer to the new
runtime.

Verification completed on 2026-06-22:

- confirmation kernel: 58 passed;
- neighboring legacy confirmation paths: 189 passed;
- pytest-compatible project suite: 1610 passed, 13 skipped across 92 modules;
- script-style tool suite: 108 passed, 2 skipped, 0 failed;
- confirmation package compilation and `git diff --check`: passed.

The kernel now provides strict request contracts, deterministic trigger policy,
decision deduplication, append-only events, reconstructable snapshots, explicit
integrity failures, a single lifecycle transition authority, per-session queue
serialization, optimistic versions, typed idempotent resolution actions, and
checksummed continuation records.

Residual limitations are intentional stage boundaries, not production claims:

- no production confirmation path uses `ConfirmationService` until Stage 2B;
- continuation records are not yet attached to Agent Loop suspension/resume;
- action receipts are process-local, so crash recovery while `applying` remains
  part of Stage 2C durable recovery work;
- session API restoration, SSE replay, client reconstruction, and final-response
  guards remain unimplemented until Stage 2C;
- legacy confirmation readers and writers remain unchanged until the Stage 2B
  hard cutover.
