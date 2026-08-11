# Analysis Runtime Systemic Recovery Implementation Plan

> **Status:** Draft implementation plan. The approved design authorizes this
> planning step, not runtime code changes, real-provider calls, destructive
> migration, commit, merge, or push.

**Design:**
`docs/superpowers/specs/2026-08-09-analysis-runtime-systemic-recovery-design.md`

**Baseline observed while planning:** `main` at `9d419fe`, with pre-existing
uncommitted source, test, script, lockfile, artifact, and runtime-state changes.

**Primary incident:** `71aa1197df28`

**User supplement:** test programs and scripts must be updated so obsolete,
uncollected, self-reporting, state-polluting, artificial, or otherwise invalid
checks cannot influence an acceptance conclusion.

## Global constraints

1. Preserve the user's existing worktree changes. Do not overwrite, revert, or
   absorb them without an explicit ownership decision.
2. Begin implementation in an isolated worktree or after the current dirty
   changes have a confirmed owner and baseline.
3. Use RED tests before each behavioral implementation slice.
4. Validate one real user-visible slice early. Do not defer upload-to-refresh
   validation until after the full framework is built.
5. Preserve immutable raw data, transformation confirmations, computation
   provenance, and high-risk claim blockers.
6. Do not add a second evidence, plan, or publication authority.
7. Do not expose chain-of-thought. Stream server-authored progress and state.
8. Do not call a real provider without explicit user authorization for the
   exact bounded run.
9. Do not treat test counts, answer length, absence of exceptions, scripted
   chunks, or handcrafted PASS receipts as product evidence.
10. Any source change invalidates prior source-bound Gate E/F/product receipts.
11. A test or gate process must fail before execution if its mutable state root
    resolves to the interactive repository `workspace/` or `sessions/` paths.
12. All scripts used by a gate must return non-zero on an internal failure.

## Planning baseline and known harness findings

The current dirty worktree already contains a partial test-cleanup batch:

- deleted `scripts/acceptance/legacy_sse_reactivity.py`;
- deleted `scripts/acceptance/legacy_web_gui.py`;
- deleted `tests/regression_test.py`;
- deleted `tests/test_v10_new.py`;
- deleted `tests/test_v91.py`;
- modified `tests/conftest.py`, release-source logic, browser contracts, Web
  tests, comparability tests, and test documentation;
- retained `tests/test_tools_comprehensive.py` as a direct custom runner.

These changes are pre-existing and must be audited, not assumed correct or
reimplemented blindly.

Current collection-only baseline using `.venv\Scripts\python.exe`:

```text
2991 tests collected
```

This proves collection succeeds. It does not prove that the tests pass, use
isolated state, execute authoritative scenarios, or support a release claim.

The current release runner launches subprocesses with `PYTHONPATH` and encoding
variables but does not centrally assign temporary `WORKSPACE_DIR` and
`SESSIONS_DIR`. Multiple collected tests and the deterministic replay import
the module-level `task_manager`. This is a confirmed harness isolation gap.

## Target ownership map

| Concern | Primary files | New/changed tests |
|---|---|---|
| Test collection and state isolation | `tests/conftest.py`, `pyproject.toml` | `tests/test_test_harness_isolation.py` |
| Release-gate truthfulness | `scripts/run_analysis_release_gates.py`, `scripts/acceptance/release_source.py` | `tests/test_analysis_release_gate_runner.py` |
| Legacy test/script disposition | `tests/README.md`, legacy files listed above, `tests/test_tools_comprehensive.py` | owning retained test modules |
| Transactional run state | new `src/data_agent/session/analysis_run_store.py`, new `src/data_agent/session/analysis_run_models.py` | new `tests/test_analysis_run_store.py` |
| Legacy task compatibility | `src/data_agent/session/task_manager.py` | `tests/test_task_manager_scope.py`, `tests/test_task_plan_versioning.py` |
| Tool outcome semantics | new `src/data_agent/agent/tool_outcome.py`, `src/data_agent/agent/loop.py`, `src/data_agent/agent/execution_scope.py` | new `tests/test_tool_outcome_transactions.py`, existing scope tests |
| Workflow coordination | new `src/data_agent/agent/analysis_run_coordinator.py` | new `tests/test_analysis_run_coordinator.py` |
| Evidence projection | `src/data_agent/agent/analysis_execution.py`, `src/data_agent/agent/evidence_contracts.py`, `src/data_agent/tools/analysis_flow.py` | projection, Stage 3C0B, measurement tests |
| Fallback resolution | `src/data_agent/agent/execution_control.py`, computation artifact owner | `tests/test_execution_control.py`, new fallback transaction cases |
| Publication | new or existing publication owner, `src/data_agent/agent/answer_quality.py`, `src/data_agent/agent/verification.py`, `src/data_agent/agent/synthesis_policy.py` | final-answer, tiered publication, measurement tests |
| SSE and persistence | `src/data_agent/web/blueprints/chat.py`, event queue owner, `src/data_agent/web/static/js/app.js` | Web/SSE/reactivity tests |
| Incident replay | `tests/fixtures/analysis_reliability.py`, `scripts/replay_analysis_reliability.py` | `tests/test_analysis_reliability_replays.py`, new incident replay test |
| Browser acceptance | `scripts/acceptance/run_web_sse_fixture.py`, browser receipt contract | browser contract plus actual in-app run |
| Provider acceptance | live-provider runner and receipt contract | `tests/test_live_provider_release_runner.py` |

Exact new module names may change during implementation if an existing owner
can cleanly hold the behavior. Responsibility boundaries may not change.

## Task 0: Freeze the incident and establish an honest implementation baseline

### Files

- Read-only incident artifacts under `sessions/71aa1197df28/`
- `docs/superpowers/specs/2026-08-09-analysis-runtime-systemic-recovery-design.md`
- this implementation plan
- a new privacy-safe fixture manifest under `tests/fixtures/`

### Steps

1. Record branch, HEAD, dirty-state inventory, and ownership for every existing
   modified/deleted/untracked path.
2. Decide whether implementation starts in a new `codex/` worktree or after the
   current batch is committed by its owner.
3. Copy only structural incident facts into a privacy-safe fixture:
   four-step plan, mixed fallback/structured computations, multi-claim step,
   state contention, scientific notation, and final publication shape.
4. Do not copy raw business data into a committed fixture unless explicitly
   approved and sanitized.
5. Add a fixture contract test that fails if a handcrafted EvidenceRecord is
   substituted for the real computation-to-publication path.

### Stop gate

Do not edit shared runtime owners while uncommitted overlapping changes have no
confirmed owner.

## Task 1: Make test and gate state isolation mandatory

### Files

- `tests/conftest.py`
- `src/data_agent/config.py` only if a shared safe-path assertion belongs there
- `scripts/run_analysis_release_gates.py`
- `scripts/replay_analysis_reliability.py`
- `scripts/acceptance/run_web_sse_fixture.py`
- live-provider runner
- new `tests/test_test_harness_isolation.py`
- `tests/test_analysis_release_gate_runner.py`

### RED tests

1. A normal pytest test fails if `workspace_resolved` or `sessions_resolved`
   equals the repository's interactive runtime directories.
2. The module-level `task_manager.dir` is reset under a per-test temporary root
   before a test can create or update tasks.
3. Task IDs and active-plan state do not leak between two tests.
4. Release-gate subprocesses receive explicit temporary `WORKSPACE_DIR` and
   `SESSIONS_DIR` values.
5. Deterministic replay, browser fixture, and provider fixture inherit those
   roots and record a bounded `state_isolated=true` diagnostic.
6. Gate A fails if any child process resolves a mutable root outside the
   assigned gate directory.
7. A subprocess crash cannot leave task or session files in the interactive
   runtime roots.

### Implementation

1. Establish temporary test roots before application singletons are imported.
2. Add an autouse per-test reset for config paths, module-level task state,
   active plans, and any related mutable singleton caches.
3. Give subprocess-based gates one gate-owned temporary directory with separate
   children for workspace, sessions, browser state, and provider state.
4. Pass resolved roots through environment variables; do not rely on cwd.
5. Add a fail-fast path-identity assertion at every gate entrypoint.
6. Record only a boolean isolation result and non-sensitive root identity hash
   in receipts.

### Focused verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_test_harness_isolation.py tests/test_analysis_release_gate_runner.py -q
```

### Stop gate

No later test or implementation task may run authoritatively until state
isolation is green. A failure here invalidates all later gate conclusions.

## Task 2: Inventory, migrate, and retire invalid test programs and scripts

### Files

- `tests/conftest.py`
- `tests/README.md`
- `tests/test_tools_comprehensive.py`
- pre-existing deleted legacy test/script files
- `scripts/run_analysis_release_gates.py`
- owning retained pytest modules

### Required inventory fields

For every ignored, custom-runner, deleted, or manual diagnostic file, record:

- owner/product area;
- whether it was ever counted by a release gate;
- whether pytest collected it;
- unique behavioral assertions;
- runtime-state writes and external dependencies;
- final disposition: `migrated`, `duplicate`, `obsolete`, or
  `diagnostic_non_authoritative`;
- replacement test node IDs when migrated.

### RED tests

1. Harness inspection rejects a release-critical ignored file without a
   declared authoritative runner.
2. Harness inspection rejects dynamic `collect_ignore` mutation.
3. A custom runner that prints `FAIL` but exits zero fails Gate A.
4. A deleted legacy file with unique unmapped coverage fails the inventory
   check.
5. A source-text assertion cannot satisfy a browser interaction observation.
6. A manual diagnostic script cannot produce a product PASS receipt.
7. Collection manifest differences are visible in the gate report rather than
   silently accepted.

### Implementation

1. Audit the existing deletions before retaining them.
2. Migrate unique assertions from `test_tools_comprehensive.py` into focused
   collected pytest files; remove duplicates and obsolete report behavior.
3. After migration, remove the direct runner from `collect_ignore` and Gate A.
4. If temporary retention is unavoidable, rename/document it as a diagnostic,
   keep its non-zero exit behavior, and exclude it from product aggregation.
5. Replace static implementation-text checks with behavioral API, DOM, or
   contract tests where the requirement is behavioral.
6. Add `[tool.pytest.ini_options]` with explicit `testpaths` and file naming if
   the collection contract is currently implicit.
7. Make `tests/README.md` the authoritative test-layer map and include the
   generated collection/isolation audit command.
8. Extend Gate A to record collected count, ignored allowlist, warnings, skips,
   and direct-runner count.

### Focused verification

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_release_gate_runner.py -q
```

### Stop gate

There must be no unowned `collect_ignore`, no authoritative self-reporting
script, and no deleted unique coverage without a replacement.

## Task 3: Introduce the transactional `AnalysisRun` state store

### Files

- new `src/data_agent/session/analysis_run_models.py`
- new `src/data_agent/session/analysis_run_store.py`
- `src/data_agent/session/task_manager.py`
- new `tests/test_analysis_run_store.py`
- `tests/test_task_manager_scope.py`
- `tests/test_task_plan_versioning.py`

### RED tests

1. Two processes create runs and steps concurrently without ID collision.
2. The database enforces at most one `in_progress` step per active run.
3. Completing one step and activating the next is one transaction.
4. A crash before commit changes neither step.
5. Replaying the same idempotency key does not duplicate a step or event.
6. Session A cannot read or mutate session B's active run through a task ID.
7. Legacy task JSON remains readable but cannot overwrite new-run state.
8. Test and runtime databases cannot share a resolved path.

### Implementation

1. Define run, step, event, tool-outcome, computation, and evidence-link tables.
2. Use UUID or database-generated identities rather than scanned file numbers.
3. Add foreign keys, uniqueness constraints, optimistic versions, and explicit
   transaction boundaries.
4. Implement repository methods for create, activate, complete, suspend,
   recover, and terminate.
5. Keep `TaskManager` as a compatibility facade while new sessions use the run
   store; do not maintain two writable authorities for the same run.
6. Export immutable JSON diagnostics only after database commit.

### Focused verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_run_store.py tests/test_task_manager_scope.py tests/test_task_plan_versioning.py -q
```

## Task 4: Give tool execution explicit commit semantics

### Files

- new `src/data_agent/agent/tool_outcome.py`
- `src/data_agent/agent/loop.py`
- `src/data_agent/agent/execution_scope.py`
- computation persistence owner
- new `tests/test_tool_outcome_transactions.py`
- `tests/test_stage3c0b_execution_scope.py`

### RED tests

1. A dataset scope violation rejects before registry execution.
2. A metadata tool with a committed artifact returns `committed` even if
   workflow advancement subsequently fails.
3. A post-execution warning cannot replace or erase the tool result.
4. Streaming, synchronous, and parallel execution paths produce the same
   outcome state.
5. The outcome contains the exact artifact/computation ID and idempotency key.
6. The model-facing message distinguishes execution failure from committed
   workflow warning.

### Implementation

1. Introduce the outcome envelope states accepted by the design.
2. Keep dataset authorization as a pre-execution guard.
3. Move workflow invariant handling into the coordinator.
4. Remove generic post-scope result substitution from every loop path.
5. Record the committed outcome before emitting SSE or prompting the model.

### Stop gate

Reproduce the 14:09:57 incident condition and prove that the saved evidence ID
is returned as committed rather than hidden behind `current_task_missing`.

## Task 5: Make workflow advancement server-owned and recoverable

### Files

- new `src/data_agent/agent/analysis_run_coordinator.py`
- run store
- `src/data_agent/session/task_manager.py` compatibility facade
- new `tests/test_analysis_run_coordinator.py`
- `tests/test_analysis_completion.py`

### RED tests

1. Evidence completion atomically advances the next ready step.
2. A valid terminal run has zero `in_progress` steps and does not look corrupt.
3. A nonterminal run with zero current steps enters deterministic recovery.
4. Recovery from the event log is idempotent.
5. Ambiguous or contradictory recovery stops advancement without losing
   computations.
6. The model cannot call `task_update` to repair canonical workflow state.

### Implementation

1. Define explicit active, suspended, recovery, and terminal run states.
2. Centralize step selection and transition ownership.
3. Replace exact-one-current global assumptions with run-state-aware
   invariants.
4. Persist recovery diagnostics and expose a bounded product status.

## Task 6: Repair multi-claim evidence projection and fallback resolution

### Files

- `src/data_agent/agent/analysis_execution.py`
- `src/data_agent/agent/evidence_contracts.py`
- `src/data_agent/tools/analysis_flow.py`
- `src/data_agent/agent/execution_control.py`
- structured capability metadata owners
- projection and Stage 3C0B test suites

### RED tests

1. A step requiring `significant_factors` and `effect_estimates` receives exact
   coverage for both keys from one structured computation when supported.
2. Capability ID fallback cannot masquerade as a required claim key.
3. Unsupported required claim output remains explicitly unmet.
4. Projection is idempotent across retry/resume.
5. A successful free-form computation persists independently of fallback
   resolution.
6. Failed resolution preserves the computation and records a limitation; it
   does not reopen exploration automatically.
7. Manual legacy evidence cannot verify a new high-confidence claim.

### Implementation

1. Add capability-owned output-field-to-claim-key mapping.
2. Project separate claim-bound evidence/measurement coverage where needed.
3. Remove `_claim_key_for` fallback to capability ID for multi-key steps.
4. Make fallback resolution consume a persisted computation artifact ID.
5. Return a bounded terminal limitation if exact semantic binding is not
   possible.

### Stop gate

The structured regression artifact from the incident fixture must advance the
intended Step 2 requirements without a model-authored EvidenceRecord.

## Task 7: Replace destructive publication with an artifact-backed assembler

### Files

- publication owner selected during implementation
- `src/data_agent/agent/answer_quality.py`
- `src/data_agent/agent/verification.py`
- `src/data_agent/agent/synthesis_policy.py`
- final-answer and measurement test suites

### RED tests

1. Scientific notation such as `6.6e-05` is parsed as one quantity.
2. Estimate, standard error, confidence interval, and p value in one table row
   bind to compatible measurements without false ambiguity.
3. A sentence may use multiple exact compatible measurements.
4. Traceable but incompletely validated computation becomes
   `computed_unverified` with a specific limitation.
5. Untraceable or contradictory numeric prose is absent from publication.
6. The final answer remains coherent after unsupported claims are removed.
7. No visible answer contains internal markers or repeated `无法发布` text.
8. Headings, tables, limitations, and safe next steps remain semantically
   complete.
9. The incident fixture answers the user's question honestly: it distinguishes
   arithmetic construction, association, and unsupported causal significance.

### Implementation

1. Produce structured publication claim objects from audited artifacts.
2. Keep exact blockers in the audit layer.
3. Assemble a fresh answer from allowed objects instead of editing draft spans.
4. Store internal reason codes only in diagnostics.
5. Keep one bounded synthesis revision; do not recompute for wording failures.

### Early product slice

At this point run the backend incident replay and inspect the complete Chinese
answer before continuing to Web framework work. A technically green but useless
answer stops implementation here.

## Task 8: Correct SSE domain events and persistence ordering

### Files

- `src/data_agent/web/blueprints/chat.py`
- event queue/SSE serialization owner
- `src/data_agent/web/static/js/app.js`
- `tests/test_web_sse_contract.py`
- `tests/test_web_sse_reactivity_contract.py`
- `tests/test_analysis_progress_streaming.py`
- `tests/test_web_resume_ownership.py`

### RED tests

1. New-session identity is delivered before session-bound progress.
2. Server-owned workflow transitions emit step progress without task tools.
3. `recoverable_warning` never appends to assistant answer Markdown.
4. `fatal_error` ends the run once with a coherent product message.
5. Final answer persistence completes before `turn_persisted` and `turn_end`.
6. `turn_end` is the final SSE event.
7. Refresh returns exactly the streamed final answer and terminal run state.
8. Background session events cannot mutate the foreground answer or tasks.

### Implementation

1. Add the approved domain event vocabulary.
2. Separate progress/status state from answer content in the browser model.
3. Register sessions early and migrate `_pending_` state once.
4. Persist before terminal emission.
5. Make reconnect and duplicate terminal delivery idempotent.

## Task 9: Build the authoritative `71aa1197df28` incident replay

### Files

- `tests/fixtures/analysis_reliability.py`
- new privacy-safe incident fixture assets
- `scripts/replay_analysis_reliability.py`
- `tests/test_analysis_reliability_replays.py`
- new `tests/test_session_71aa1197df28_replay.py`

### RED scenario

1. Upload the portable workbook/fixture.
2. Ask for significant factors affecting the target.
3. Create and execute a four-step run.
4. Run free-form and structured computation paths.
5. Start a concurrent unrelated run in a second process.
6. Persist computation/evidence during a workflow transition.
7. Synthesize scientific notation and a multi-statistic table.
8. Audit and publish.
9. Reload the session from persisted state.

### Required assertions

- unrelated state cannot overwrite the run;
- no committed result is misreported;
- exact claim-key requirements progress;
- the answer contains substantive useful content;
- no internal error/marker/diagnostic spam is public;
- limitations match the small, autocorrelated, confounded design;
- replay output is deterministic enough for contract checks without requiring
  identical natural-language wording.

## Task 10: Replace false-green browser acceptance

### Files

- `scripts/acceptance/run_web_sse_fixture.py`
- `scripts/acceptance/browser_gate_contract.py`
- `tests/test_browser_gate_contract.py`
- actual in-app browser procedure and receipt schema

### RED tests

1. Browser receipt fails if the loop buffers the final answer and emits
   artificial delayed chunks.
2. Browser receipt fails without observed pre-answer progress.
3. Browser receipt fails if final content appears only after refresh.
4. Browser receipt fails if refresh differs from the streamed final text.
5. Browser receipt fails if internal errors are appended to answer content.
6. Browser receipt fails if runtime-state isolation is false.
7. A scripted provider receipt cannot claim live-provider status.

### Implementation

1. Remove `DelayedAuditedLoop` as authoritative streaming proof.
2. Drive the real application event stream with a deterministic provider for
   repeatable browser behavior.
3. Observe DOM and SSE timing directly in the in-app browser.
4. Record natural progress, answer, persistence, refresh, interruption,
   suspend/resume, error recovery, and state-isolation observations.
5. Keep contract-only fixture tests labeled as preparation, never satisfaction.

### Stop gate

Gate E remains `NOT_RUN` until an actual browser produces a current source-bound
receipt. Deterministic pytest cannot convert it to PASS.

## Task 11: Strengthen provider and product aggregation semantics

### Files

- live-provider runner and contract
- `scripts/run_analysis_release_gates.py`
- provider runner tests
- product report schema

### RED tests

1. Product PASS is impossible without current A-F PASS receipts.
2. Gate F fails if any run deadlocks, exposes internal diagnostics, loses
   refresh state, or returns a methodologically strengthened claim.
3. Gate F receipt records exact scenario and fixture identity, not only source
   digest and answer length.
4. Provider wording variation is allowed; missing terminal usefulness is not.
5. A stale or deterministic-provider receipt cannot satisfy live Gate F.
6. Human semantic review status is required and cannot be inferred from unit
   tests.

### Authorization gate

Obtain explicit user authorization immediately before the bounded real-provider
run. Approval to implement code is not approval to make provider calls.

## Task 12: Migrate, remove legacy authorities, and freeze the release

### Steps

1. Run focused owner tests after each task.
2. Run the incident replay after Tasks 5, 7, 8, and 9.
3. Run the full collected deterministic suite after shared state, loop,
   evidence, publication, and Web changes stabilize.
4. Run deterministic release gates with isolated roots.
5. Freeze the source identity.
6. Produce a fresh actual-browser receipt for that identity.
7. With explicit authorization, produce the bounded live-provider receipt.
8. Run product aggregation and human semantic review.
9. Audit legacy task JSON writes and remove the old writable authority.
10. Update old design status as historical/superseded without rewriting old
    receipts.

### Final verification commands

Commands are illustrative and must use the configured repository runtime:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts/run_analysis_release_gates.py --profile deterministic
.\.venv\Scripts\python.exe -m compileall -q src/data_agent
git diff --check
```

Actual browser and provider commands are executed only through their explicit
bounded workflows and are recorded separately.

## Required gate matrix

| Gate | Required proof | Cannot be satisfied by |
|---|---|---|
| Harness | collection, exit-code truth, state isolation, legacy inventory | printed PASS text or ignored files |
| State | cross-process isolation, atomic advancement, crash recovery | single-process unit happy path |
| Execution | committed outcome identity under post-workflow failure | file existence without returned identity |
| Evidence | exact multi-claim projection and fallback artifact resolution | legacy unbound manual evidence |
| Publication | coherent useful answer and exact blockers | non-empty string or placeholder diagnostics |
| Web | natural progress, persisted final answer, refresh identity | artificial chunk replay or source assertions |
| Provider | repeated real behavior with honest analytical semantics | scripted provider or deterministic receipt |
| Product | all current gates plus semantic review | test count, answer length, or historical receipt |

## Plan stop conditions

Stop implementation and return to design review if any of these occurs:

1. SQLite cannot be introduced without creating a second long-lived mutable
   authority.
2. Test/runtime root isolation cannot be guaranteed before module singleton
   initialization.
3. The implementation requires relaxing exact evidence identity for verified
   claims.
4. A coherent partial answer cannot be built without trusting model prose over
   computation artifacts.
5. The actual browser cannot observe the production event stream being claimed.
6. The provider gate would require unbounded calls or unapproved external use.
7. Existing user changes overlap an implementation file and ownership cannot be
   resolved safely.

## Definition of done

This plan is complete only when the design's 14 completion criteria pass for
one frozen source identity, the invalid-test/script inventory has no unresolved
entry, the `71aa1197df28` incident replay passes under concurrent pressure, and
the user receives a candid final status that distinguishes implementation,
deterministic tests, actual browser proof, live-provider proof, and product
release.
