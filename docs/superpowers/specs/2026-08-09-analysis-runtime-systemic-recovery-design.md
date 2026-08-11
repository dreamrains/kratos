# Analysis Runtime Systemic Recovery Design

**Status:** Draft for review — no runtime implementation authorized by this document

**Date:** 2026-08-09

**Current baseline:** `main` at `9d419fe` with pre-existing uncommitted worktree changes

**Primary incident:** session `71aa1197df28`

**Comparison session:** `fe064bcfae31` is useful for behavioral comparison only; it is not a correctness oracle

**Reopens and amends:**

- `docs/superpowers/specs/2026-07-27-analysis-execution-and-publication-reliability-design.md`
- `docs/superpowers/specs/2026-07-28-measurement-identity-and-honest-release-gates-design.md`
- `docs/superpowers/specs/2026-08-08-fallback-resolution-and-compact-evidence-alias-design.md`

The 2026-08-08 implementation and gate records remain historical facts, but
they are no longer sufficient evidence that the current product is reliable.
The live `71aa1197df28` failure occurred after those contracts and gates existed
and exposed failure classes that the current completion model did not cover.

## 1. Decision summary

This incident is not a single evidence-recording bug. It is a cross-layer
failure involving mutable workflow state, execution transaction semantics,
evidence identity, publication rendering, Web event ordering, and false-green
acceptance.

The recovery therefore makes the following product and architecture decisions:

1. Mutable analysis workflow state becomes session/turn scoped and
   transactionally persisted. A process-local integer allocator writing shared
   `task_N.json` files is not an acceptable runtime authority.
2. Tool execution, computation persistence, evidence projection, workflow
   advancement, and the returned tool outcome receive explicit commit
   semantics. A committed side effect must never be reported as an unqualified
   execution failure.
3. Evidence existence is not conditional on a healthy task cursor. Workflow
   corruption may prevent verification or task completion, but it must not
   erase or hide a successfully persisted computation.
4. Canonical claim and measurement identities remain server-owned. Relaxing
   evidence into session-only or model-authored identities is rejected.
5. Publication is rebuilt from trusted computation/evidence artifacts and
   explicit gaps. It must never expose repeated internal diagnostics as the
   body of the user's answer.
6. Safe process progress is streamed; raw chain-of-thought is never displayed.
   Recoverable workflow warnings, fatal transport errors, and final answer text
   are separate event classes.
7. Browser/SSE work may be implemented as a separate workstream, but product
   completion requires one real end-to-end path covering upload, computation,
   useful publication, live display, persistence, and refresh.
8. Unit, contract, deterministic, browser, and provider gates are supporting
   evidence. None may independently declare product completion.

## 2. Confirmed incident facts

The following are verified from persisted session artifacts and current source.

### 2.1 Computation did not simply fail

- The session executed identity decomposition, dimension comparisons,
  change-window exploration, and `factor_relationship_analysis`.
- The structured regression result persisted as a successful computation and
  produced a server-projected `evidence_record.v2`.
- Manual EvidenceRecords also persisted at 14:09:08, 14:09:31, 14:09:57, and
  14:10:15, although all four were `legacy_unbound`.
- The analytical method still had substantive limitations: 31 daily rows,
  strong time dependence, severe collinearity, and time-confounded strategy
  changes. Successful execution does not make an independent or causal
  "significant factor" conclusion reliable.

### 2.2 Shared task state was overwritten

- The session created workflow tasks 244 through 247 around 14:08:25.
- `workspace/tasks/task_244.json` now belongs to a different
  `playbook_pending_gate_*` session and was created at 14:09:56.
- The first `stage3c0b_current_task_missing` response in the incident occurred
  at 14:09:57.
- `TaskManager` allocates integer IDs in process memory by scanning existing
  filenames once and saves with an unconditional `write_text` to the shared
  task path.

This is direct evidence of cross-session state collision. The name of the
overwriting session strongly suggests a test or gate process, but the exact PID
and caller are not recoverable from the current artifacts and must not be
claimed as confirmed.

### 2.3 The runtime committed side effects and returned errors

- Dataset-reading calls can be rejected by the pre-execution scope guard.
- Metadata calls such as evidence and task tools often have no dataset
  argument and pass the pre-execution guard.
- After registry execution, `AgentLoop` refreshes the workspace scope. If that
  refresh is in an error phase, it discards the real result and emits the scope
  error instead.
- Evidence files at 14:09:57 and 14:10:15 prove that this occurred during the
  incident.

This is a transaction and result-semantics defect, not merely a missing error
message.

### 2.4 Structured evidence and the planned claim contract disagreed

- Step 2 required both `significant_factors` and `effect_estimates`.
- Automatic projection selected `analysis.factor_relationship` because the
  step had more than one required claim key.
- Task completion requires the evidence claim key to be one of the task's exact
  required claim keys and ultimately requires all required keys to be
  satisfied.

Therefore a healthy task cursor alone would not have completed the step. The
claim-key projection contract must also change.

### 2.5 Publication converted an answer into internal diagnostics

The final draft contained a coherent analysis, but the deterministic audit
reported 36 failed claim checks, dominated by:

- `missing_evidence_identity`;
- `numeric_mismatch`;
- `unmet_block_claim_requirement`;
- `measurement_ambiguous`.

The renderer then replaced affected claim spans with repeated Chinese internal
diagnostics such as `无法发布该数值`. This behavior satisfied fail-closed
contract tests but failed the product requirement to return a useful and honest
answer.

### 2.6 The Web layer amplified the backend failure

- Every SSE `error` is appended directly to the assistant answer body.
- Automatic workflow transitions do not reliably emit user-visible task
  updates; task refresh is mainly associated with explicit task tool calls or
  polling.
- `turn_end` is queued before the final `loop._auto_save()` in the request
  worker.
- A new session remains `_pending_` until it is migrated during the stream, and
  the session list is refreshed again in the request `finally` path.
- Browser acceptance currently collects the complete audited answer and then
  re-emits artificial delayed chunks. This proves DOM chunk handling, not the
  production runtime's natural publication timing.

## 3. Root-cause model

The system failure is represented as six connected planes.

| Plane | Root defect | User-visible consequence |
|---|---|---|
| State | Shared mutable task files, process-local ID allocation, no transaction | Wrong or missing current task; progress stalls |
| Orchestration | Post-execution invariant failure overwrites committed tool result | Agent repeats recovery and misdiagnoses successful writes |
| Evidence | Model-dependent manual records and incompatible claim-key projection | Computations exist but cannot satisfy plan or audit |
| Publication | Claim-by-claim destructive replacement | Coherent answer becomes diagnostic fragments |
| Web | Error/progress/final events share presentation paths; save ordering is late | Errors pollute answers; content appears late or after refresh |
| Validation | Component gates and scripted timing stand in for the real product path | Thousands of passing tests coexist with obvious live failure |

No single-plane patch can close the incident chain.

## 4. Product requirements and non-goals

### 4.1 Required product behavior

For every uploaded-data analytical turn, the product must end in exactly one
of these user-meaningful terminal outcomes:

1. **Complete with supported findings:** verified and appropriately limited
   exploratory findings are published.
2. **Complete with bounded limitations:** the requested inference cannot be
   supported, but descriptive results, completed work, evidence gaps, and the
   next safe action are published coherently.
3. **Suspended for user input:** the exact missing decision or confirmation is
   visible and resumable.
4. **Fatal system failure:** no analytical assertion is published, but the
   failure is a single clear product error with a recoverable session state.

Repeated internal gate diagnostics are not a terminal product outcome.

### 4.2 Trust requirements retained

- Immutable raw uploads and versioned analysis copies.
- Exact dataset and transformation identity.
- User confirmation for meaning-changing transformations.
- Server-owned computation provenance.
- Exact measurement identity for high-confidence numeric, inferential, and
  causal claims.
- Claim-level blocking for fabricated, contradictory, stale, cross-scope, or
  causally upgraded assertions.
- Honest method and data limitations.

### 4.3 Explicit non-goals

- Displaying raw model chain-of-thought.
- Fuzzy number-only or wording-only evidence matching.
- Making every analytical sentence independently verified.
- Allowing a disclaimer to legalize an untraceable number.
- Adding another parallel assurance contract.
- Retrying analysis indefinitely until bookkeeping succeeds.
- Treating the older `fe064bcfae31` answer as the target truth.

## 5. Target runtime architecture

### 5.1 Transactional `AnalysisRun` aggregate

Each analytical user turn receives one server-owned `AnalysisRun` identity.
The aggregate owns:

- session and turn identity;
- canonical plan version;
- ordered executable steps and dependencies;
- current run and step status;
- computation artifact references;
- evidence projection outcomes;
- publication state;
- ordered domain events;
- terminal outcome and persistence version.

The model selects analytical actions within declared capabilities. It does not
own task IDs, task lifecycle transitions, evidence IDs, or the current-step
cursor.

### 5.2 State persistence decision

**Recommended authority:** SQLite using the Python standard library, with JSON
artifacts retained as immutable exports and debugging receipts.

Required database constraints include:

- globally unique run and step IDs;
- a uniqueness constraint that permits at most one `in_progress` step per
  active run;
- optimistic versioning for session/run updates;
- foreign keys from computations and evidence to the run and step;
- idempotency keys for tool outcomes and event emission;
- transactions covering step completion and next-step activation.

A per-session JSON store with atomic rename and cross-process locks is a
possible alternative, but it recreates database concerns in application code
and is not recommended for the primary mutable authority.

Tests, acceptance gates, and production/local interactive runs must use
different configured state roots or databases. Test startup must fail if it
resolves to the live workspace state path.

### 5.3 Tool outcome transaction semantics

Every tool call produces a server-owned outcome envelope with one of these
states:

- `rejected_before_execution`;
- `execution_failed_without_commit`;
- `committed`;
- `committed_with_workflow_warning`;
- `rolled_back`.

The envelope contains the computation/artifact identity when committed. A
post-execution workflow failure may downgrade task or publication state, but it
cannot replace `committed` with an execution error.

Dataset scope is checked before data-reading execution. Workflow integrity is
checked and repaired transactionally by the run coordinator, not by applying a
global postcondition to every tool result.

### 5.4 Workflow recovery semantics

The coordinator enforces the run invariant before executing a substantive
analysis step:

- if the prior step completed and exactly one next step is ready, activate it
  in the same transaction;
- if the run is terminal, do not execute another analytical tool;
- if state is missing or contradictory, mark the run `recovery_required`,
  retain committed computations, and attempt deterministic reconstruction from
  the run event log;
- if reconstruction is ambiguous, stop workflow advancement and publish a
  bounded system limitation. Do not ask the model to repair task state.

### 5.5 Evidence projection and fallback resolution

Structured computations project evidence through a capability-owned mapping
from structured output fields to canonical planned claim keys.

For a step with multiple required claim keys, the projector must emit distinct
claim-bound projections or an explicit claim-key coverage map. Falling back to
the capability ID is invalid.

Free-form Python follows a different path:

1. persist the exact computation artifact and dataset versions;
2. expose a bounded server-generated result schema;
3. resolve it once into one of: claim-bound evidence, explicit limitation,
   workflow state, or user confirmation;
4. preserve the artifact if resolution fails;
5. never require another exploratory tool merely to repair bookkeeping.

Manual `record_evidence_record` remains a compatibility and semantic-annotation
tool, not the ordinary bridge between computation and publication.

### 5.6 Publication model

Publication uses three internal result classes:

| Class | Minimum basis | Public treatment |
|---|---|---|
| `verified` | Exact current measurement identity and all blocking requirements | Publish normally |
| `computed_unverified` | Exact committed computation artifact, but incomplete validation, stability, or workflow binding | Publish with a specific limitation and no semantic upgrade |
| `unsupported` | No traceable artifact or a material contradiction/forbidden claim upgrade | Omit the assertion and explain the gap coherently |

`computed_unverified` is artifact-backed. It cannot be created from model prose
alone.

The final renderer builds a fresh answer structure from allowed claim objects:

- direct answer to the user's question;
- supported findings;
- exploratory/computed findings;
- what could not be determined;
- method and data limitations;
- safe next action.

It does not edit arbitrary draft spans into repeated diagnostic placeholders.
Internal reason codes remain in diagnostics and observability, not in the main
answer body.

The audit must support normal analytical expression, including scientific
notation, confidence intervals, tables containing estimate/standard error/p
value, and a sentence backed by multiple compatible measurements.

### 5.7 Web and SSE protocol

The backend emits domain events rather than using a generic error stream for
all abnormal conditions:

- `session_created`;
- `analysis_run_started`;
- `step_started`, `step_completed`, `step_failed`;
- `tool_started`, `tool_committed`, `tool_failed`;
- `evidence_projected`, `evidence_rejected`;
- `publication_started`;
- `answer_delta`;
- `recoverable_warning`;
- `fatal_error`;
- `turn_persisted`;
- `turn_end`.

Ordering invariants:

1. `session_created` precedes other session-bound UI updates.
2. Server-owned step transitions emit progress without requiring model task
   calls.
3. `recoverable_warning` updates a status panel and never appends `**Error:**`
   to the answer.
4. The complete audited answer is persisted before `turn_persisted`.
5. `turn_end` is the final event and is emitted only after persistence.
6. Refresh after `turn_end` returns the same answer and terminal status.

## 6. Implementation workstreams

### Workstream 0: Freeze and truth baseline

- Mark the current product release status as reopened for analysis reliability.
- Preserve the `71aa1197df28` artifacts read-only.
- Create a privacy-safe incident replay fixture derived from its structural
  behavior, not from hand-built success evidence.
- Separate current user worktree changes from the future implementation branch
  before modifying runtime code.
- Record current focused failures and invalidate source-bound receipts after the
  first source change.

### Workstream 1: Isolated transactional state

- Introduce the `AnalysisRun`/step/event persistence schema.
- Migrate task creation and lifecycle advancement behind one repository API.
- Remove process-local shared integer allocation from runtime authority.
- Add cross-process concurrency, crash-recovery, idempotency, and state-root
  isolation tests.
- Keep legacy task JSON read-only during migration; export new state to JSON
  only for inspection.

### Workstream 2: Atomic orchestration and recovery

- Replace global post-execution scope-result substitution with explicit tool
  outcome envelopes.
- Make completion plus next-step activation atomic.
- Implement deterministic run invariant repair and terminal recovery states.
- Ensure committed computations remain visible when workflow advancement
  fails.
- Remove model-facing task self-repair rituals.

### Workstream 3: Evidence and analytical semantics

- Replace capability-ID fallback with explicit multi-claim projection.
- Make structured computation-to-evidence projection idempotent.
- Define artifact-backed fallback-Python resolution.
- Repair scientific-notation and compatible multi-measurement audit handling.
- Add method-sufficiency checks so observational, autocorrelated, confounded
  data cannot be promoted to causal or reliable independent-driver claims.

### Workstream 4: Coherent publication

- Introduce structured publication claim objects and an answer assembler.
- Implement artifact-backed `computed_unverified` behavior.
- Retain hard blockers for contradictions and unsafe semantic upgrades.
- Eliminate repeated internal diagnostic placeholders from public answers.
- Add exact regression expectations for useful partial answers, not merely
  non-empty output.

### Workstream 5: Web event and persistence lifecycle

- Introduce the domain SSE event vocabulary and ordering checks.
- Register new sessions before long-running analysis begins.
- Render run progress independently from assistant answer text.
- Persist before `turn_end` and make reconnect/refresh idempotent.
- Test background session ownership, interruption, suspend/resume, recoverable
  warnings, fatal errors, and refresh.

### Workstream 6: Product acceptance and legacy removal

- Run the real upload-to-refresh path before broad full-suite closure.
- Remove artificial answer chunking from the authoritative streaming proof.
- Run multiple concurrent sessions against the same application instance.
- Run failure injection for state contention, projection failure, audit
  ambiguity, provider truncation, and browser disconnect.
- After the new path is proven, remove legacy mutable task writes and obsolete
  compatibility branches instead of retaining two authorities indefinitely.

## 7. Validation strategy

### 7.0 Test and acceptance harness validity

Test and script validity is a release prerequisite, not a documentation task.
Before any behavioral gate can contribute to a release conclusion, the harness
must prove all of the following:

- every authoritative pytest test is collected by the declared repository
  command;
- every ignored test or direct runner is explicitly allowlisted with an owner,
  purpose, replacement status, and a gate that checks its real exit code;
- no test, replay, browser fixture, provider fixture, or release subprocess can
  resolve `WORKSPACE_DIR`, `SESSIONS_DIR`, task storage, or the future
  `AnalysisRun` database to the interactive runtime paths;
- subprocesses inherit explicit temporary state roots rather than relying on
  the caller's environment;
- a script that prints `FAIL` but exits zero cannot contribute to a PASS;
- static source-text assertions cannot satisfy a user-interaction or runtime
  behavior requirement;
- scripted providers and handcrafted receipts can test contracts but cannot
  satisfy actual-browser or live-provider gates;
- the authoritative browser proof observes the application's natural event
  stream and cannot buffer the final answer and emit artificial delayed chunks;
- removed legacy scripts and tests have a recorded coverage disposition:
  migrated, proven duplicate, obsolete product behavior, or intentionally
  retained as non-authoritative diagnostics;
- the gate report records collection counts, skips, warnings, state-isolation
  status, exact commands, exit codes, source identity, and fixture identity.

The default authoritative layers are:

1. collected pytest for unit, contract, integration, mutation, and deterministic
   replay coverage;
2. an importable release-gate runner that treats any failed subprocess as a
   failed gate;
3. an actual-browser receipt produced from observed UI behavior;
4. an explicitly authorized live-provider receipt;
5. one product aggregator that returns PASS only when every required layer is
   current and PASS.

Legacy ad-hoc runners may remain temporarily for diagnosis, but their output is
never counted in the product result and their filenames and documentation must
make that status unambiguous.

### 7.1 Incident-level regression

The authoritative replay must reproduce the essential `71aa1197df28` chain:

1. create a four-step plan;
2. run free-form and structured computations;
3. concurrently create unrelated workflow state from another process;
4. persist evidence while the workflow cursor changes;
5. complete multi-claim structured projection;
6. synthesize a table with scientific notation and multiple statistics;
7. publish and refresh through the real Web path.

Pass conditions:

- no cross-session task mutation;
- no committed result is returned as an unqualified failure;
- progress advances without model task bookkeeping;
- the answer contains useful analytical content and honest limitations;
- no internal evidence marker or repeated `无法发布` diagnostic is visible;
- the final answer and terminal state are visible before and after refresh;
- the method does not overstate causal or independent significance.

### 7.2 Cross-process and recovery tests

- Two processes allocate and advance runs concurrently without collision.
- A process crash between computation commit and workflow advancement resumes
  idempotently.
- A repeated tool outcome does not duplicate computation, evidence, or events.
- A corrupt or missing step row cannot silently bind evidence to the wrong
  plan.
- Tests cannot resolve their state root to the live workspace database.

### 7.3 Publication adversarial tests

- Same-valued different metrics cannot cross-bind.
- Multiple required claim keys are independently satisfied.
- Scientific notation remains one quantity.
- Estimate, standard error, interval, and p value may coexist in a supported
  row without false ambiguity.
- A traceable computation with incomplete validation publishes only as
  `computed_unverified`.
- A genuinely untraceable number is absent from the public answer.
- The answer remains grammatically and structurally coherent after any claim
  action.

### 7.4 Browser and provider acceptance

The authoritative browser run uses the real application event stream. It may
use a deterministic provider for repeatability, but it may not buffer the full
answer and simulate streaming after completion.

A separate explicitly authorized provider gate runs representative analytical
questions repeatedly. Provider variation may change wording or select an
equivalent method; it may not produce task deadlock, internal diagnostics,
missing refresh state, or unsupported claim strengthening.

### 7.5 Semantic usefulness review

Each representative scenario is reviewed against the user question:

- Was the requested target understood correctly?
- Was the selected method sufficient for the available design and sample?
- Did the answer distinguish arithmetic construction, association,
  prediction, and causality?
- Did it provide a direct useful answer even when significance could not be
  established?
- Did limitations change the claim strength rather than merely appear as a
  disclaimer?

## 8. Migration and rollback

1. Add the new state repository and runtime behind a disabled migration flag.
2. In deterministic tests, shadow-export the new state while the legacy path
   remains the executing authority; compare state transitions only.
3. Switch dedicated incident replay and browser fixtures to the new authority.
4. Make the new authority default for new sessions after focused and incident
   gates pass.
5. Keep old sessions readable without rewriting historical evidence.
6. Roll back by routing new sessions to the legacy authority only before
   legacy writes are removed; rollback never upgrades or rewrites evidence.
7. Remove the legacy mutable task authority after a defined compatibility
   window and a successful migration audit.

Rollback flags are operational controls, not evidence that the old path is
acceptable for release.

## 9. Rejected patch approaches

The following are explicitly rejected as the primary solution:

1. Whitelisting all evidence and task tools around the current scope guard.
2. Saving strict evidence with only plan or session identity when exact step,
   claim, computation, and measurement identity are unknown.
3. Automatically treating all infrastructure-related numeric claims as
   exploratory model prose.
4. Adding another retry that calls `task_update` after
   `stage3c0b_current_task_missing`.
5. Fixing only fallback resolution or evidence marker usability.
6. Replacing diagnostic wording while preserving destructive span editing.
7. Treating artificial delayed chunks as proof of production streaming.
8. Declaring completion from the full deterministic test count alone.

## 10. Completion criteria

The systemic recovery is complete only when all of the following are true for
one frozen source identity:

1. The live/test state-isolation gate proves no runtime path shares mutable task
   state with tests or acceptance fixtures.
2. Concurrent run creation and advancement cannot overwrite another session.
3. Completion and next-step activation are atomic and crash-recoverable.
4. Committed computations always return a committed outcome identity.
5. Structured multi-claim evidence satisfies the intended canonical claim keys.
6. Free-form results have an explicit artifact-backed resolution or limitation
   path without exploration deadlock.
7. Publication emits a coherent answer with no internal diagnostic spam.
8. Audit handles scientific notation and compatible multi-measurement claims.
9. The authoritative browser path shows progress, final content, and refresh
   persistence without artificial post-hoc chunking.
10. The incident replay passes repeatedly under concurrent state pressure.
11. Representative real analytical questions return methodologically honest,
    useful answers in every required run.
12. No required gate is `NOT_RUN`, `BLOCKED`, or `FAIL`, and a human semantic
    review finds no high- or medium-severity product defect.
13. The test-harness audit reports no unowned ignored test, silent custom
    runner, runtime-state leak, artificial browser-stream proof, or obsolete
    script counted as authoritative.
14. Every retained release script has contract tests for non-zero failure exit,
    receipt status, source/fixture identity, and isolated runtime roots.

## 11. Decisions requiring review before implementation

The design recommends, but does not silently authorize, these choices:

1. Use SQLite as the mutable `AnalysisRun` and workflow authority; retain JSON
   only for immutable artifacts, exports, and compatibility reads.
2. Treat Web/SSE as a separate implementation workstream but a mandatory part
   of the same product release gate.
3. Publish exact artifact-backed computations as `computed_unverified` when
   independent validation or workflow binding is incomplete; never derive that
   status from draft prose alone.
4. Reopen the prior "product-validated" status and invalidate old receipts for
   current completion claims.
5. Require explicit user authorization before real-provider calls, merge,
   push, or destructive legacy-state migration.

After these decisions are accepted, the next document should be a file-level
implementation plan with RED tests, ownership boundaries, migration steps,
focused commands, and stop gates for each workstream.
