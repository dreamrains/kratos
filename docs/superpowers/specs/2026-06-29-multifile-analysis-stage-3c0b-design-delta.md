# Multi-File Analysis Stage 3C0B Design Delta

Date: 2026-06-29

## Status

This document records the accepted Stage 3C0B design delta after discussion on
2026-06-29. It is a design and planning source, not implementation approval.

Do not implement Stage 3C0B until a separate implementation plan is written,
reviewed, and explicitly approved. Do not begin Stage 3C1A join planning until
the Stage 3C0B stop gate in this document passes.

## Source Documents And Checkout Evidence

Read these documents in order before planning implementation:

1. `docs/superpowers/plans/2026-06-29-stage-3c-continuation-handoff.md`
2. `docs/superpowers/specs/2026-06-27-multifile-analysis-stage-3c-design.md`
3. `docs/superpowers/plans/2026-06-27-multifile-analysis-stage-3c0a-verification.md`
4. this design delta

Current checkout audit at the time of this design delta:

- Branch: `codex/multifile-analysis-stage-3c-design`
- HEAD: `547bae63ba93d94190c291f961d5ac386d39b42c`
- Stage 3C0A integrated baseline: `25c72f8`
- `547bae6` adds only the Stage 3C continuation handoff above the Stage 3C0A
  verification baseline.
- Worktree status may print environment warnings for
  `C:\Users\duguy/.config/git/ignore` and `.pytest_cache`; these warnings are
  not design evidence.

## Design Decision

Stage 3C0B will implement independent multi-dataset execution and bounded
evidence synthesis by tightening the current Stage 3C design in four ways:

1. It removes executable compatibility dual paths for new Stage 3C0B plans.
2. It makes `AnalysisPlan.method_plan` the canonical plan contract and workflow
   tasks a projection of that contract.
3. It treats evidence sufficiency and result quality as first-class gates, not
   incidental verification details.
4. It makes the workbench a user-value projection that answers what the user can
   conclude or do next, not a dump of scheduler state.

The core chain is:

```text
AnalysisPlan
  -> plan contract validation
  -> workflow task projection
  -> single-task execution boundary
  -> EvidenceRecord
  -> verification and measurement compatibility
  -> sufficiency gate
  -> synthesis
  -> workbench projection
```

Stage 3C0B executes only `independent` and `synthesis` steps. Join, union, fuzzy
matching, automatic entity mapping, executable aggregate comparison, and derived
dataset creation remain out of scope.

## Compatibility And Migration Boundary

The project has no formal production users, so Stage 3C0B should prefer a clean
contract over preserving unreasonable behavior. Compatibility must not become a
second execution line.

The following are prohibited for new Stage 3C0B plans:

- a legacy `analysis_spec` task path running beside the new `AnalysisPlan`
  contract;
- a legacy task generator that drops `step_id`, `dataset_inputs`, or
  `combination_mode`;
- a dual evidence model where old `metrics` and new `measurements` are both
  executable canonical fields;
- task completion rules that complete unrelated analysis-spec tasks after one
  generic evidence record or one successful tool call;
- prompt assembly that gives the current task all datasets when its binding
  names only one dataset;
- synthesis over historical or legacy EvidenceRecords that do not belong to the
  current executable plan.

Historical plans, tasks, and evidence are display-only after the cutover. They
may appear in history or diagnostic views, but they cannot be resumed, executed,
or synthesized as Stage 3C0B evidence.

Every executable Stage 3C0B plan carries `contract_version`. Only the new
contract version is executable. Legacy or missing-version records are rejected
for execution with a user-facing explanation and may be shown only as historical
context.

## Canonical Plan Contract

`AnalysisPlan.method_plan` is the source of truth. Workflow tasks are projections
used for scheduling and workbench display; they do not own analytical intent.

Every executable step must include:

- `plan_id`;
- stable `step_id`;
- one user-facing `goal`;
- explicit `dataset_inputs`;
- `dataset_contract_ids` resolved by the service;
- `combination_mode`, limited in Stage 3C0B to `independent` or `synthesis`;
- `expected_output`;
- evidence requirements;
- dependency references where the step has hard synthesis dependencies.

For `independent` steps:

- exactly one dataset input is allowed in Stage 3C0B;
- the dataset must be eligible and must have a current dataset contract;
- the step may read only that dataset and compact global analysis context.

For `synthesis` steps:

- the step reads EvidenceRecords, verification summaries, and compatibility
  reports;
- it does not read raw DataFrames;
- it declares only hard dependencies in `required_evidence_step_ids`;
- all other verified evidence may be used opportunistically within the synthesis
  budget.

The service, not the LLM, assigns or validates stable IDs, contract IDs, and
supported modes. The LLM proposes analysis strategy; deterministic validators
decide whether the proposal is executable.

## Plan Quality Review

Planning has three states:

```text
draft -> reviewed -> executable
```

The LLM may draft a flexible analysis strategy. The validator must not replace
the LLM's professional analysis judgment with a rigid template, but it must
block plans that are structurally unsafe or analytically insufficient.

The review checks:

- whether the plan covers the user's material questions;
- whether each selected dataset has a clear role;
- whether important eligible datasets are either bound to a task or explicitly
  marked available/not needed with a reason;
- whether the proposed methods fit the dataset contracts and route capabilities;
- whether the plan has enough exploration and validation for the user's goal;
- whether any unsupported operation is hidden in free text;
- whether the plan stays within the current execution-batch budget.

Investigation tasks are allowed. The plan does not need to know every final
finding before execution. The important requirement is that each task has a
clear evidence purpose and a bounded dataset scope.

## Execution Model And Isolation

Stage 3C0B does not introduce cross-task concurrency. There is one
`in_progress` workflow task at a time.

The execution boundary is the current task:

- the active task is selected deterministically from ready workflow tasks;
- the current task prompt receives the global user goal, compact data-role
  context, and only the dataset contracts bound to the task;
- read-only tool calls inside the current task may use the existing parallel
  execution rules;
- workspace writes and analysis-state mutations remain sequential;
- a task may not read a dataset that is not named by its `dataset_inputs`;
- synthesis may not read raw datasets.

This is workspace-level isolation, not only a tool-argument guard. Every path
that exposes loaded datasets to the current execution step must respect the
current task binding.

Resume validates each projected task before execution:

- the dataset still exists;
- the dataset remains eligible;
- the dataset contract ID is still current;
- the task's combination mode is still supported;
- required dependencies are terminal before synthesis starts.

Invalidation affects only the task and its dependent claims. It does not trigger
a global replan unless the sufficiency gate decides the analysis cannot answer
the user's question without more work.

## Workflow Task Projection

There must be one shared Plan-to-Task projector. Existing places that create
workflow tasks from analysis specs must route through this projector or be
removed from the Stage 3C0B execution path.

Projected tasks carry:

- `analysis_plan_id`;
- `step_id`;
- `dataset_inputs`;
- `dataset_contract_ids`;
- `combination_mode`;
- dependencies;
- task role and user-facing goal;
- terminal status, including explicit `failed`.

Workflow task status may be:

- pending;
- blocked;
- in_progress;
- completed;
- failed.

Completion is evidence-driven. A task is completed only when all required
evidence requirements for that step are satisfied, verification passes for the
task's claims, and no structural execution error remains. A generic successful
tool call is not sufficient.

`failed` is terminal. Synthesis waits for hard dependencies to enter a terminal
state, but it does not treat failed evidence as valid. Missing or failed required
evidence suppresses only dependent claims.

## Evidence Contract

Stage 3C0B uses one new canonical EvidenceRecord contract. Do not keep old
`metrics` as an executable canonical path.

Each Stage 3C0B EvidenceRecord includes:

- `plan_id`;
- `step_id`;
- stable `claim_key`;
- evidence ID derived from `plan_id + step_id + claim_key` for idempotent
  upsert;
- dataset name;
- dataset contract ID;
- method;
- tool calls;
- sample size or row coverage where applicable;
- limitations;
- confidence;
- evidence requirement reference;
- `measurements`.

`measurements` is the canonical numeric evidence schema. Each measurement
contains:

- metric name;
- metric definition;
- value;
- unit;
- grain;
- population scope;
- time scope;
- method or aggregation;
- denominator where relevant;
- limitations.

Numeric comparison is allowed only when metric, definition, unit, grain, time
scope, and population scope are compatible. Stage 3C0B does not perform unit
conversion, time alignment, inferred population matching, or hidden metric
mapping. Incompatible measurements may still be reported as separate findings
with an explicit limitation.

## Verification, Compatibility, And Claim Strength

Verification remains a separate deterministic layer. It checks the current
plan's EvidenceRecords and rejects or downgrades unsupported claims.

The verifier must enforce:

- evidence belongs to the current `plan_id`;
- evidence references the expected `step_id`;
- evidence references the current dataset contract;
- required fields are present;
- measurement compatibility before numeric comparison;
- limitations and confidence are reflected in claim strength.

Synthesis candidate findings must cite evidence IDs. A deterministic validator
rejects findings that:

- cite no evidence;
- cite evidence outside the current plan;
- compare incompatible measurements;
- state stronger certainty than the evidence supports;
- use missing required evidence as if it succeeded.

Existing `InsightRecord` remains the synthesis output store. Stage 3C0B does not
introduce a second synthesis store.

## Analysis Sufficiency Gate

Every execution batch ends with an analysis sufficiency gate before final
synthesis or final answer.

The gate returns one of:

- `ready_for_synthesis`;
- `needs_more_analysis`;
- `blocked_by_missing_data`.

The gate considers:

- whether hard synthesis dependencies are terminal;
- whether required evidence exists and passed verification;
- whether important user questions remain uncovered;
- whether failed optional tasks leave material gaps;
- whether incompatible measurements prevent the intended comparison;
- whether another bounded execution batch could materially improve the answer.

If the result is `needs_more_analysis`, the system may draft and review another
execution batch. The maximum of 12 executable steps applies per active batch or
wave, not to the entire session. This protects depth while keeping each prompt
and task set bounded.

If the result is `blocked_by_missing_data`, the system explains what data or
decision is needed and which question it would answer. It does not force a
conclusion.

If no valid required evidence exists, synthesis produces an insufficient-evidence
or next-steps answer with `outcome=partial`; it must not invent findings.

## Budget Policy

Budget rules are centralized and enforced during validation or projection. An
oversize plan is rejected for replanning, not silently truncated.

Initial hard caps:

- maximum 12 executable steps per active execution batch;
- independent step binds exactly 1 dataset;
- synthesis step may declare at most 8 hard required evidence step IDs;
- compact EvidenceRecord injected into prompt: at most 1 KiB;
- compact DatasetContract injected into prompt: at most 2 KiB;
- current-task prompt increment: at most 8 KiB;
- synthesis prompt increment: at most 12 KiB;
- maximum 3 important warnings in active prompt context;
- workbench first screen: at most 20 tasks plus omitted count;
- pre-plan context: at most 8 eligible dataset summaries plus omitted count.

These are engineering limits for Stage 3C0B. They may be tuned later only by a
named policy change and test update.

## Workbench Product Contract

The workbench must help the user solve the analysis problem. It should not be a
technical status pile.

Default presentation order:

1. core conclusion;
2. action board;
3. question map;
4. collapsed trust details.

The action board has three user-facing groups:

- confirmed;
- still uncertain;
- recommended next steps.

The question map shows which user questions are answered, partially answered, or
unanswered. Each answer traces to evidence IDs, datasets, metric scope, and
confidence. Technical task status, dataset contracts, verification details, and
warnings appear under "why this is trustworthy" rather than dominating the first
screen.

Technical failures are translated into user meaning:

- not `task_failed`, but "coupon impact cannot be judged from the available
  evidence yet";
- not `measurement_incompatible`, but "the statistical scopes differ, so these
  numbers should not be directly compared";
- not `missing_required_evidence`, but "this conclusion needs evidence from
  dataset X, which was not produced successfully."

Optional task failure affects only the related question. Required missing
evidence explains what is missing and what it would answer. Users may rerun an
affected part only.

Multi-file participation itself must not create a confirmation. Confirmation is
reserved for material, answerable choices or risks defined by the existing
confirmation runtime.

## Retry And Failure Semantics

Safe idempotent retries are allowed up to 2 attempts for transient task failures.
Structural failures do not auto-retry and cannot be overridden by confirmation.

Structural failures include:

- missing dataset;
- stale dataset contract;
- unsupported combination mode;
- invalid task binding;
- required evidence schema violation;
- measurement incompatibility for a requested numeric comparison.

A failed optional task leaves unrelated tasks usable. A failed required task
blocks only dependent claims. If too many material claims are blocked, the
sufficiency gate decides whether to replan, ask for more data, or deliver a
partial answer.

## Quality Protections

Stage 3C0B must not reduce the quality of single-file or ordinary analysis.

Required protections:

- reuse the existing load-data trust workflow for preview, quality, contract,
  and route proposals;
- preserve existing single-file intent recognition, cleaning, analysis-route,
  evidence, verification, and result quality behavior;
- avoid static template planning that suppresses exploration;
- allow investigation tasks when the data shape is not yet clear;
- compare before/after behavior on single-file realistic prompts;
- verify that final answers still contain enough insight, not merely enough
  valid structure.

The validator may reject unsafe structure, but it must not make the analysis
professionally shallow. If the plan is valid but insufficiently useful, the
quality review requests more analysis rather than synthesizing early.

## Implementation Units For The Future Plan

The later implementation plan should be decomposed into these independently
testable units:

1. Canonical Plan Contract
   - add/validate `contract_version`;
   - validate step IDs, bindings, modes, dependencies, and evidence
     requirements;
   - reject legacy executable records.
2. Task Projection And Execution Scope
   - centralize Plan-to-Task projection;
   - carry dataset bindings and modes through workflow tasks;
   - enforce one active task and dataset read isolation.
3. Evidence And Verification
   - migrate to canonical `measurements`;
   - add idempotent evidence upsert by `plan_id + step_id + claim_key`;
   - enforce current-plan evidence and measurement compatibility.
4. Sufficiency And Synthesis
   - add execution-batch sufficiency gate;
   - support additional batches when analysis is insufficient;
   - validate evidence-cited findings before InsightRecord creation.
5. User-Value Workbench
   - project conclusions, uncertainties, next steps, question map, and trust
     details;
   - translate technical failures into user-facing implications;
   - keep technical state folded and bounded.
6. Regression And Real Replay
   - cover single-file regressions;
   - cover multi-file independent evidence and synthesis;
   - verify with real files from `reference/test_doc`.

No unit may add a second planner, task runtime, evidence store, confirmation
system, or workbench state model.

## Required Real-Data Verification

Implementation verification must include real files from:

`D:\Project\Daily\data-agent\reference\test_doc`

Known files at design time:

- `游戏Abanner汇总数据.xlsx`
- `游戏A内购数据.xlsx`
- `游戏A激励视频汇总数据报表.xlsx`
- `游戏B留存.xlsx`
- `游戏互推.xlsx`
- `省钱卡用户最近流水_20260511.xlsx`
- `省钱卡订单_20260507.xlsx`

The real-data verification must cover:

- single-file regression on at least one realistic file;
- multi-file independent analysis over multiple game files;
- synthesis from separate evidence without a join;
- mixed-domain protection where game files and savings-card files are not forced
  into false comparisons;
- optional failure isolation;
- insufficient-evidence or incompatible-measurement output;
- workbench value projection, including conclusions, uncertainty, next steps,
  and traceability.

Verification records must include exact commands, file names, pass counts,
observed deviations, and whether any output was intentionally partial.

## Stop Gate Before Stage 3C1A

Stage 3C1A cannot begin until all answers are yes:

- every used dataset has at least one task binding;
- independent tasks run without relationship confirmation;
- single-file intent, cleaning, routing, evidence, verification, and output
  quality show no material regression;
- insufficient evidence triggers more analysis, partial output, or a missing-data
  explanation rather than forced synthesis;
- optional failure is isolated to related questions;
- all numeric comparisons pass measurement compatibility;
- the current task cannot read an unbound dataset;
- historical evidence cannot enter current-plan synthesis;
- prompt and workbench projections stay within budgets;
- the four-file or larger real-data case produces independent evidence, partial
  failure behavior where applicable, and bounded synthesis;
- every workbench suggestion is traceable to evidence or explicitly marked as a
  next-data/action recommendation;
- no executable compatibility dual path remains for new Stage 3C0B plans.

Failure of any item blocks Stage 3C1A and returns the work to Stage 3C0B design
or implementation review.

## Principal Risks And Mitigations

Risk: clean cutover breaks old sessions.

Mitigation: old sessions are display-only. Since there are no formal production
users, execution compatibility is intentionally not preserved.

Risk: stricter task binding makes the LLM create narrow, low-insight plans.

Mitigation: keep planning LLM-led, allow investigation tasks, review coverage and
method fit, and use the sufficiency gate to request more analysis when needed.

Risk: isolation hides useful context.

Mitigation: provide two-layer context: global goal and data-role summary, plus
current-task dataset access.

Risk: measurement compatibility suppresses too many conclusions.

Mitigation: report incompatible findings separately and explain the limitation
instead of pretending they are comparable.

Risk: sequential execution feels slow.

Mitigation: keep cross-task execution sequential for correctness in 3C0B, allow
read-only tool parallelism inside a task, and revisit cross-task concurrency only
after the evidence and failure semantics are stable.

Risk: the workbench becomes observability UI rather than analysis help.

Mitigation: make the first screen conclusion, uncertainty, and next action. Keep
technical task state behind the trust-details layer.

Risk: validators are bypassed by legacy helper paths.

Mitigation: centralize plan validation, task projection, evidence upsert,
measurement compatibility, and synthesis validation. Tests must cover legacy
entry points that previously created tasks, completed tasks, or synthesized
evidence.

## Open Items For The Implementation Plan

The design is closed enough for a written implementation plan, but that plan must
choose concrete code locations and tests for:

- the exact `contract_version` value and validation entry point;
- the shared Plan-to-Task projector module/function;
- the current-task dataset access guard;
- the canonical EvidenceRecord schema migration points;
- the sufficiency gate function and its prompt/context inputs;
- the real-data replay command shape and durable verification note.

These are implementation details, not design blockers.
