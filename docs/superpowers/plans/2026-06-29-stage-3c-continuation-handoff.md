# Stage 3C Continuation Handoff And Roadmap

Date: 2026-06-29

## Purpose

This document is the compression-resistant handoff for continuing multi-file
analysis work in a new conversation. It records what is implemented, which
decisions are already settled, what remains open for discussion, and the order
in which later slices may be planned.

This is a discussion and sequencing document. It is not approval to implement
Stage 3C0B, Stage 3C1A, or Stage 3C1B. Each slice still requires a separate,
detailed implementation plan and explicit approval.

## New-Conversation Source Of Truth

Read these files in order:

1. `docs/superpowers/plans/2026-06-29-stage-3c-continuation-handoff.md`
2. `docs/superpowers/specs/2026-06-27-multifile-analysis-stage-3c-design.md`
3. `docs/superpowers/plans/2026-06-27-multifile-analysis-stage-3c0a-verification.md`
4. The current code and tests named by the next slice.

The older design document still contains historical wording that says Stage 3C
production work has not started. That status is superseded by this handoff and
the Stage 3C0A verification record; its architectural decisions and later-slice
contracts remain authoritative.

Do not reconstruct requirements from chat history when these documents provide
the answer.

## Current Repository State

- Branch: `codex/multifile-analysis-stage-3c-design`
- Current integrated commit: `25c72f8`
- Stage 3C0A was fast-forward merged locally.
- The Stage 3C0A feature branch was deleted and its Git worktree registration was
  removed.
- The main worktree was clean immediately after merge and verification.
- Stage 3C0A focused verification after merge: `390 passed`.
- JavaScript syntax and `git diff --check` passed.
- The repository-wide pytest run reached 58% without an observed failure, then
  exceeded the 300-second command limit. It must not be described as a full pass.
- Pytest may warn that `.pytest_cache` is not writable. This does not change test
  results, but it remains an environment issue.
- A deregistered physical directory may remain at
  `.worktrees/multifile-analysis-stage-3c0a` because Windows denied access to its
  `.pytest_cache` ACL. It is not a Git worktree and must not be used as source.
  Cleanup requires an account that can repair that ACL.

At the start of the new conversation, verify rather than assume:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git log -8 --oneline
git worktree list
```

Expected branch and HEAD are the values above unless later work intentionally
changed them.

## Completed Capability Boundary

### Separate Track: Chart Reliability

Chart-contract, renderability, axis semantics, and related chart repairs were
completed before Stage 3C. Keep chart regressions in their own maintenance track;
do not fold unrelated chart work into multi-file execution plans.

### Unified Confirmation Runtime

The project now has one confirmation policy, durable runtime, visible question
surface, continuation model, and resolution path. Retired relationship,
exclusion, and join-logic confirmations no longer block analysis or reappear
through old state, durable ledgers, stale browser IDs, or legacy payloads.

Future slices must extend this runtime. They must not add another confirmation
store, question detector, sidebar-only pending state, or action lifecycle.

### Stage 3C0A: Trustworthy File Scope

Stage 3C0A is implemented and accepted:

- technical eligibility and current analysis assignment are separate facts;
- `used` is derived only from an explicit AnalysisPlan task binding;
- usable but unbound files remain `available`;
- unavailable files block only when the current task actually requires them;
- relationship evidence is diagnostic only;
- successful loads enter the active bundle without creating relationship gates;
- material exact-reference ambiguity uses the unified confirmation runtime;
- selected file IDs and global upload ordinals narrow the actual task binding,
  not merely the displayed question;
- scope details and prompt context remain bounded;
- the workbench shows one user-facing decision list and keeps relationship
  details in a collapsed technical section.

The four-file session `5ba97a7bb7db` replays read-only as:

```text
eligible=4 used=0 available=4 decisions=0 gate=method_confirmation
```

All 54 files under that real session directory were unchanged by the replay.

## Decisions That Must Not Be Reopened Casually

These decisions were explicitly reviewed and accepted:

1. All participating files do not need to be related or joined.
2. Participation, task assignment, and combination method are separate.
3. Relationships cannot decide file eligibility or current use.
4. A file is not used until an existing AnalysisPlan step binds it.
5. Independent progress should continue unless an ambiguity materially changes
   the result and cannot be resolved safely.
6. Confirmation is risk-based, not mandatory for every cross-file action.
7. Confirmation cannot override structural or resource blocks.
8. Existing AnalysisPlan, workflow tasks, evidence records, verification,
   confirmation runtime, and workbench must be extended in place.
9. Parallel planners, evidence stores, confirmation systems, or scope state are
   prohibited.
10. Full artifacts stay outside prompt context; prompts receive bounded compact
    references.
11. Delivery remains additive and gated. A smaller reliable capability is
    preferred over a broad heuristic implementation.
12. Union, fuzzy matching, automatic entity mapping, many-to-many join execution,
    and automatic repair remain out of scope.

Reopen one of these only when current repository evidence proves it unsafe or
impossible. Record that evidence before changing the design.

## Concrete Multi-File Execution Model

Use this example to prevent the design from drifting back to relationship-first
reasoning:

- The user uploads files A, B, C, and D.
- All four are technically eligible and relevant to the analysis goal.
- A and B may support an exact join.
- C and D do not need to join anything.

Stage 3C0B should be able to execute independent tasks over A, B, C, and D and
synthesize their verified evidence. The possible A-B join is irrelevant unless
an explicit later task requires combined row-level data. Only that explicit join
task may enter Stage 3C1 preflight.

Therefore:

- eligible files can be broader than used files;
- used files can be broader than joined files;
- a synthesis may consume evidence from all four files without reading all four
  raw datasets into one prompt or DataFrame;
- join failure must not erase valid independent evidence from C or D.

## Recommended Next Sequence

### Phase 0: New-Session Audit

Goal: confirm the handoff still matches the checkout before discussing changes.

Actions:

1. Run the repository-state commands above.
2. Read the Stage 3C0B section of the accepted design.
3. Inspect current `AnalysisPlan`, workflow-task generation, evidence records,
   synthesis policy, and context assembly before proposing new types.
4. Identify any code drift since `25c72f8`.
5. Do not edit production code during this audit.

Output: a short delta report listing what Stage 3C0B can reuse directly, what
requires extension, and any design conflict that must return to discussion.

### Phase 1: Discuss And Plan Stage 3C0B

Goal: execute independent per-dataset tasks and synthesize verified evidence
without requiring a join.

Stage 3C0B must extend the existing `AnalysisPlan.method_plan`. Every executable
step needs:

- stable `step_id`;
- one explicit goal;
- explicit `dataset_inputs`;
- `combination_mode` limited to `independent` or `synthesis`;
- expected output;
- evidence requirements.

The implementation plan should be split into independently testable units:

1. Validate and persist dataset bindings and supported combination modes through
   the existing AnalysisPlan and workflow-task contract.
2. Execute independent tasks with dataset-level read isolation and sequential
   state mutation.
3. Record evidence lineage and compatibility metadata using the existing
   EvidenceRecord path.
4. Synthesize verified evidence with bounded context and explicit compatibility
   limitations.
5. Project task progress and failure isolation into the existing workbench.
6. Replay the real four-file scenario and write a Stage 3C0B verification note.

Stage 3C0B explicitly does not:

- execute a join or union;
- infer entity mappings;
- create a second planner or task runner;
- send all raw datasets into one prompt;
- allow synthesis to invent missing evidence;
- implement Stage 3C1 operation records.

### Phase 2: Stage 3C0B Stop Gate

Do not plan joins until all answers are yes:

- Does every `used` file have at least one task binding?
- Can independent tasks proceed without relationship confirmation?
- Does an optional task failure leave unrelated tasks usable?
- Does a missing required EvidenceRecord block only dependent synthesis claims?
- Are unsupported combination modes non-executable?
- Can the four-file case produce separate evidence and one bounded synthesis?
- Are single-file analysis quality and existing verification behavior unchanged?
- Is prompt and state growth measured and within explicit budgets?

Record exact commands, pass counts, deviations, and one real-session replay.

### Phase 3: Discuss And Plan Stage 3C1A

Goal: create a deterministic, non-mutating preflight for an exact two-dataset
join.

Only begin after the Stage 3C0B stop gate passes. Stage 3C1A should introduce one
immutable `DataOperationRecord` aggregate, deterministic source fingerprints,
data-based cardinality and expansion checks, centralized thresholds, and one of
three risk results: `safe_to_execute`, `requires_confirmation`, or `blocked`.

Stage 3C1A stops before execution and does not mutate workspace data. Candidate
keys from relationship diagnostics remain hints; measured data decides risk.

### Phase 4: Stage 3C1A Stop Gate

Required before execution planning:

- identical inputs and parameters produce the same operation ID;
- preflight is read-only;
- many-to-many and hard resource limits are blocked;
- blocked results cannot be approved away;
- inferred material parameters require an answerable confirmation;
- full statistics remain in artifacts while prompt summaries remain bounded.

### Phase 5: Discuss And Plan Stage 3C1B

Goal: resume an approved immutable operation, execute it atomically, validate the
result, and register a derived dataset through the existing trust workflow.

Stage 3C1B must reuse the confirmation action registry and ContinuationRecord.
Approval records the operation reference; deterministic resume executes the
exact stored plan before control returns to the LLM. Execution must be
idempotent, stale-safe, rollback-capable, and unable to overwrite existing data.

Derived data must receive the existing preview, quality, contract, route, and
evidence-lineage artifacts. Failure must not stop unrelated independent tasks.

## Stage 3C0B Discussion Agenda

The new conversation should refine these questions before writing code:

1. **Required versus optional tasks**
   - Which existing field or deterministic rule marks a task required for a
     synthesis claim?
   - Avoid adding a second dependency graph if workflow tasks already carry the
     necessary dependency information.

2. **Binding persistence and resume**
   - Where should validated `dataset_inputs` and `combination_mode` live so a
     resumed turn uses the same plan?
   - How will stale contracts or removed datasets invalidate a task safely?

3. **Execution isolation**
   - Which existing read-only operations may run concurrently?
   - Which state and workspace writes must remain sequential?
   - How are retry and idempotency inherited from the current task runtime?

4. **Evidence compatibility**
   - Which existing fields represent metric definition, unit, grain, time range,
     method, limitations, and confidence?
   - Which fields genuinely need extension rather than duplication?
   - What exact compatibility rules allow a numerical comparison?

5. **Synthesis contract**
   - How does synthesis reference required EvidenceRecords without copying raw
     datasets into context?
   - What is the deterministic behavior when evidence is missing, downgraded, or
     incompatible?

6. **Context budget**
   - Set explicit limits for per-task contracts, recent evidence refs, synthesis
     inputs, warnings, and workbench projection.
   - Add serialized-size tests before accepting the slice.

7. **User experience**
   - Show task progress, used datasets, optional failures, and synthesis limits
     in the existing workbench.
   - Do not expose technical scheduler state as unexplained status labels.
   - Do not create a confirmation merely because multiple files participate.

8. **Analysis quality and regressions**
   - Compare single-file results before and after routing changes.
   - Verify that data overview, contracts, routes, evidence verification, and
     claim-strength controls are reused rather than bypassed.

## Required Risk Audit For Every Slice

Before approving a slice plan, explicitly answer:

1. Could this change reduce current single-file or main-agent analysis quality?
2. Could context grow with total file or task history instead of a fixed budget?
3. Does the design reuse data overview, dataset contracts, route capability,
   evidence verification, confirmation runtime, and workbench projections?
4. Is any proposed type or store duplicating an existing source of truth?
5. Are optional failures isolated from unrelated work?
6. Are structural and resource blocks deterministic and non-overridable?
7. Is every user question material, visible, answerable, and resumable?
8. Are implementation claims separated from design-only behavior?

Any unclear answer blocks implementation-plan approval until repository evidence
resolves it.

## Separate Backlog Tracks

Do not bundle these into Stage 3C0B unless they directly block its acceptance:

- full-repository pytest runtime and the 300-second timeout;
- `.pytest_cache` ACL and the deregistered orphan worktree directory;
- unrelated chart enhancements;
- union, fuzzy matching, entity resolution, automatic repair, and many-to-many
  join execution;
- broader domain playbooks, hypothesis-system expansion, or general article and
  documentation work.

Track them independently so Stage 3C does not become an unreviewable catch-all.

## Recommended First Deliverable In The New Conversation

Do not begin with code. Produce a short Stage 3C0B design-delta note containing:

1. current reusable components with file and symbol references;
2. the minimum contract extensions required;
3. rejected duplicate abstractions;
4. context and failure-isolation budgets;
5. unresolved questions requiring user confirmation;
6. a proposed decomposition into independently verifiable implementation tasks.

After the user confirms that note, write a separate detailed Stage 3C0B
implementation plan using TDD steps, exact file paths, commands, expected
failures, commits, focused regressions, real-session replay, and a stop-gate
verification document.

## Copyable New-Conversation Prompt

```text
请继续 data-agent 的多文件分析 Stage 3C 工作。先不要写代码。

请依次阅读：
1. docs/superpowers/plans/2026-06-29-stage-3c-continuation-handoff.md
2. docs/superpowers/specs/2026-06-27-multifile-analysis-stage-3c-design.md
3. docs/superpowers/plans/2026-06-27-multifile-analysis-stage-3c0a-verification.md

然后检查当前分支、HEAD、工作区和相关实现，输出 Stage 3C0B 的设计差异审计：
- 哪些现有能力可以直接复用；
- 需要扩展的最小合同；
- 如何避免重复 planner、task runtime、evidence store、confirmation 和 UI 状态；
- 对主分析质量、单文件流程、上下文预算、数据概览和证据系统的风险；
- 需要我确认的开放问题；
- 建议的分阶段实施与停机门。

在我确认设计差异审计前，不要实施 Stage 3C0B，也不要提前设计或实现 Join。
```

## Resume Checklist

- [ ] Read the three source documents in order.
- [ ] Verify branch, HEAD, status, log, and worktree registrations.
- [ ] Treat `25c72f8` as the Stage 3C0A integrated baseline unless Git evidence
      shows a later intentional change.
- [ ] Keep completed and designed-only capabilities clearly separated.
- [ ] Start with Stage 3C0B design-delta discussion, not implementation.
- [ ] Reuse existing ownership boundaries before proposing a new abstraction.
- [ ] Define context budgets and failure isolation before code.
- [ ] Obtain explicit approval for a detailed Stage 3C0B plan.
- [ ] Require a separate stop gate before Stage 3C1A.
- [ ] Keep Stage 3C1A and Stage 3C1B in separate plans.

