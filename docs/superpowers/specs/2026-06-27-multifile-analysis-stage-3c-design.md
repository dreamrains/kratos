# Multi-File Analysis Stage 3C Design

Date: 2026-06-27

## Decision

Stage 3C will complete multi-file analysis through four additive, independently
verifiable slices:

1. Stage 3C0A makes file eligibility and analysis assignment trustworthy.
2. Stage 3C0B executes independent per-dataset tasks and synthesizes verified
   evidence without requiring a join.
3. Stage 3C1A creates immutable, non-mutating join plans with deterministic risk
   classification.
4. Stage 3C1B resumes approved join plans deterministically, executes them
   atomically, validates the result, and registers derived trust artifacts.

The design deliberately does not treat "all files participate" as "all files
must be joined." Participation, task assignment, and combination method are
separate decisions.

## Design Status And Continuation Handoff

This specification was reviewed section by section with the user and accepted on
2026-06-27. It is the source of truth for Stage 3C design decisions.

Current repository status at the time of design:

- Stage 1 chart-contract and renderability repairs are complete and remain a
  separate concern.
- Stage 2A through Stage 2C unified-confirmation runtime work is complete and must
  be reused rather than replaced.
- Stage 3A/3B participation-first scope and workbench changes are complete at
  baseline commit `f66c7ce`.
- No Stage 3C production implementation has started.

The next allowed action after user review of this document is to invoke the
writing-plans workflow for Stage 3C0A only. Do not implement Stage 3C0B, Stage
3C1A, or Stage 3C1B in the Stage 3C0A plan. Each later slice requires the prior
slice to pass its stop gate, a separate plan, and explicit approval.

If conversation context is compressed, resume by reading this document, checking
the current branch and worktree, and comparing the implementation against the
slice stop gates. Do not reconstruct requirements from chat memory when this
document provides the answer.

## Confirmed Decisions And Invariants

The following decisions have already been discussed and accepted. They should not
be reopened during implementation unless repository evidence proves that a
decision is unsafe or impossible:

1. Confirmation is risk-based. Explicit, deterministic, low-risk operations may
   execute automatically; not every cross-file action asks the user.
2. User confirmation is not a universal safety override. Structural and resource
   blocks remain blocked after confirmation.
3. The first operation capability is exact two-dataset join. Union, fuzzy
   matching, entity mapping, automatic repair, and executable many-to-many joins
   are deferred.
4. File participation does not require a relationship, and relationship evidence
   cannot decide participation.
5. Multiple files may all contribute to one analysis through independent tasks
   and evidence synthesis even if only a subset can join.
6. A file is not "used" until an AnalysisPlan step binds it. Uploading or being
   eligible is not sufficient.
7. The system should ask about a file choice only when ambiguity is material and
   independent progress is not safe.
8. Operation-specific ambiguity discovered by data preflight uses the same
   confirmation runtime as existing intent and method questions.
9. Confirmation must approve and resume an immutable operation reference, not a
   newly generated LLM tool call.
10. Derived join output must pass through the existing dataset preview, quality,
    contract, and route workflow before downstream analysis uses it.
11. Evidence based on derived data must carry operation lineage and must be
    downgraded or rejected when that lineage is invalid.
12. Full operation details remain in artifacts. Prompt context receives bounded
    compact references only.
13. Existing AnalysisPlan, workflow tasks, confirmation runtime, trust contracts,
    evidence verification, and workbench are extended in place. Parallel systems
    for the same responsibilities are prohibited.
14. Delivery is additive and gated. Reliable smaller capabilities are preferred
    over an ambitious first version that guesses unsupported behavior.
15. Export and artifact-delivery behavior are outside this stage.

The project currently has few users and no material migration burden. Stage 3C
does not require in-place migration of historical sessions or preservation of
obsolete relationship-driven behavior. A temporary compatibility projection is
allowed only within a slice when an existing caller still needs it; it must not
become a second source of truth or survive the slice without an explicit reason.

## Why This Stage Exists

Stage 3A/3B separated file participation from pairwise relationship uncertainty
and replaced relationship-first sidebar language with a user-facing workbench.
That repair removed false blockers, but it did not yet complete downstream
multi-file execution.

The current implementation still has important gaps:

- `multi_file_scope.py` mixes factual availability, goal relevance, and actual
  use in one participation value.
- A pending or confirmed legacy relationship can still cause a file to become
  `included`, even though relationships should not decide participation.
- Filename and goal token overlap can include a file without contract-level
  evidence.
- `needs_scope_decision` exists in the contract but the current classifier does
  not produce it.
- `active_scope` has one `active_dataset`, and `analysis_entry.py` filters trust
  contracts through that single value. Multi-file scope is therefore not yet
  the downstream execution source of truth.
- `transform_data(operation="merge")` calls `pandas.merge` directly without a
  preflight, cardinality validation, output-size estimate, confirmation gate,
  or postcondition audit.
- Derived datasets created by `transform_data` do not automatically pass through
  the same preview, quality, dataset-contract, and route-generation workflow as
  loaded datasets.
- Claim verification considers evidence and cleaning risk, but does not know
  whether evidence depends on a risky or stale cross-dataset operation.
- Confirmation resume currently re-enters the LLM loop. Without an immutable
  operation reference, the resumed tool call could differ from the operation the
  user approved.

These are related dependencies, but they should not be repaired in one large
implementation change. Each slice below has its own contract, regression gate,
and stop condition.

## Goals

- Correctly determine which uploaded or historical files are technically usable.
- Correctly determine which usable files are needed for the current analysis.
- Explain every used, available, not-needed, decision, and unavailable state.
- Allow multiple files to contribute through independent analysis and evidence
  synthesis even when no pairwise join is possible.
- Bind every analysis step to explicit dataset inputs and one supported
  combination mode.
- Join only the minimum subset of datasets needed by a step.
- Preflight exact joins before mutation and classify them as safe, confirmable,
  or blocked.
- Reuse the unified confirmation runtime and resume the exact approved plan.
- Validate and register derived data through the existing trust workflow.
- Keep prompt context bounded as files, tasks, and operation history grow.
- Preserve analysis quality when one optional dataset or task fails.

## Non-Goals

This stage will not implement:

- union or append operations;
- executable many-to-many joins;
- one-shot joins across three or more datasets;
- fuzzy record linkage;
- automatic business-entity mapping;
- automatic key type conversion;
- automatic deduplication or aggregation to make a join pass;
- a general cross-dataset aggregate-comparison engine;
- a second confirmation runtime, task engine, evidence model, or data profiler;
- a redesign of artifact delivery or export.

## Core Model: Three Independent Decisions

Every file is evaluated on three orthogonal axes.

### 1. Eligibility

Eligibility answers only whether the data can be used by analysis tools.

- `eligible`: the dataset is loaded, readable, and has a usable trust contract.
- `unavailable`: loading, inspection, or contract generation failed.

Eligibility must not depend on relationship evidence or filename similarity.

### 2. Assignment

Assignment answers whether an eligible dataset is needed for the current goal.

- `used`: at least one current analysis step references the dataset.
- `available`: usable, but no current step references it yet.
- `not_needed`: considered and intentionally not used, with an explicit reason.
- `needs_decision`: user input is materially required to choose whether it is in
  scope.

Before an AnalysisPlan exists, eligible files may remain `available`. After the
plan is recorded, `used` must be derived from task bindings rather than theme or
relationship heuristics.

### 3. Combination Mode

Combination mode belongs to an analysis step, not to a file globally.

- `independent`: analyze one dataset on its own.
- `join`: combine two exact-key datasets through Stage 3C1.
- `aggregate_compare`: reserved for a later executable capability.
- `synthesis`: combine verified EvidenceRecords, not raw rows.

Stage 3C0B exposes only `independent` and `synthesis` as executable modes. Stage
3C1 adds `join`. Unsupported modes must not be emitted as executable work.

## Source-Of-Truth Hierarchy

When records disagree, consumers use this order:

1. Explicit current user inclusion or exclusion.
2. Dataset eligibility derived from actual load, profile, and trust-contract
   state.
3. AnalysisPlan step bindings for current `used` assignment.
4. DataOperationRecord for join parameters, risk, approval, execution, and
   lineage.
5. Unified confirmation runtime for whether a material decision is actively
   suspended, resolved, failed, or cancelled.
6. EvidenceRecord and verification reports for supported conclusions.
7. Trust view and workbench as projections of the above records.

`file_relationships`, filename similarity, the workbench display model, and the
legacy transform log are never authoritative over this hierarchy.

## Representative Four-File Scenario

Use this scenario as the minimum mental model and acceptance fixture:

- `orders`: order-level revenue and purchase events;
- `users`: user-level profile attributes;
- `coupons`: coupon issue and redemption events;
- `campaigns`: campaign-level activity and spend.

All four files may be eligible and explicitly required by the user. A valid plan
can be:

1. Join `orders` and `users` only when a user-level revenue task requires fields
   from both datasets.
2. Analyze `coupons` independently for issue, redemption, and discount evidence.
3. Analyze `campaigns` independently for campaign trend and spend evidence.
4. Synthesize the verified evidence from those tasks without joining coupon or
   campaign rows into the user-level table.

If the user's narrower goal needs only orders and users, coupons and campaigns
remain eligible but become `available` or `not_needed` with explicit reasons.
They are not forced into the join and are not silently labeled as used.

## Stage 3C0A: Trustworthy Participation Scope

### File Decision Contract

Each file must produce a compact, user-explainable decision:

```json
{
  "file_id": "orders",
  "dataset": "orders",
  "eligibility": "eligible",
  "assignment": "used",
  "reason_code": "explicit_current_request",
  "reason": "The user explicitly requested this dataset for the current analysis.",
  "confidence": "high",
  "task_refs": ["task_user_revenue"]
}
```

`reason_code` is stable and testable. `reason` is localized user-facing text.
`task_refs` is empty until the AnalysisPlan binds the dataset.

### Decision Priority

The scope classifier applies these rules in order:

1. An explicit user exclusion produces `not_needed`.
2. A dataset that cannot be loaded, inspected, or contracted is `unavailable`.
3. A file explicitly named in the current request is `used` once a plan step is
   bound to it. Before planning it is `available` with reason code
   `explicit_in_scope_pending_plan`, so the UI does not falsely claim execution.
4. If the user asks to analyze all files uploaded for the current request, every
   eligible file must receive at least one independent profile or analysis task.
5. AnalysisPlan task bindings are the authoritative source for `used`.
6. Historical eligible files are `available` by default.
7. A file becomes `not_needed` only after the planner has considered it and can
   state why no current task needs it.

Explicit user intent outranks automated relevance estimates. Technical
eligibility still cannot be overridden by intent: an unreadable required file
blocks only the tasks that require it.

### Relationship Boundary

The following signals must never set eligibility or assignment:

- `possibly_linked`;
- shared ID columns;
- candidate join keys;
- filename or business-theme similarity;
- historical `requires_confirmation` flags.

They may contribute candidate-key evidence only after a plan step has selected
`combination_mode=join`.

### Confirmation Standard

`needs_decision` is emitted only when all conditions hold:

1. Two or more reasonable file choices exist.
2. The choice materially changes analysis scope or conclusions.
3. User intent and existing dataset contracts cannot resolve the choice.
4. The system cannot safely proceed by analyzing the candidates independently.

Examples include an instruction to use "the older sales file" when multiple
files match and their age cannot be established. Relationship uncertainty alone
does not qualify.

All scope decisions that require an answer use the existing confirmation runtime
and visible confirmation card.

### Stage 3C0A Acceptance

- Four explicitly supplied readable files can all become eligible.
- A file cannot become used solely because a relationship is pending or confirmed.
- Historical unrelated files remain available until considered by the plan.
- Explicit exclusion wins over all automated signals.
- Required unreadable data blocks only dependent work.
- `needs_decision` has real reachable test cases and a visible runtime question.
- Every non-default decision has a stable reason code and user-facing reason.
- Context output remains capped and reports omitted counts.

## Stage 3C0B: Independent Multi-Dataset Execution

### Reuse The Existing AnalysisPlan

Stage 3C0B extends `AnalysisPlan.method_plan`; it does not create another planner.

```json
{
  "step_id": "step_user_revenue",
  "goal": "Analyze user-level revenue and repeat purchase behavior.",
  "dataset_inputs": ["orders"],
  "combination_mode": "independent",
  "expected_output": "User revenue evidence",
  "evidence_requirements": ["revenue", "user_count", "repeat_rate"]
}
```

Every executable step must have:

- a stable step ID;
- one explicit goal;
- explicit dataset inputs;
- one currently supported combination mode;
- expected output;
- evidence requirements.

The current task generator remains responsible for converting plan steps into
workflow tasks. Dataset bindings and combination mode must flow through that
existing task contract.

### Planning Rules

1. Start from eligible files in the current participation scope.
2. Read each dataset's existing contract and supported routes.
3. Decompose the user goal into evidence-producing steps.
4. Bind each step to the minimum necessary datasets.
5. Give every `used` dataset at least one task reference.
6. Keep files with no task as `available` or explain why they are `not_needed`.
7. Create a synthesis step only after its input evidence requirements are known.

The planner receives an explicit capability list. In Stage 3C0B the list contains
only `independent` and `synthesis`. It must not silently encode an unsupported
join, union, entity mapping, or aggregate comparison in free text or tool calls.

### Execution And Isolation

- An independent task may read only its declared dataset inputs.
- Only the current task's compact contracts and relevant recent evidence enter
  the prompt.
- Existing read-only tools may use the current parallel execution rules.
- Workspace and analysis-state mutations remain sequential.
- Failure in one optional task does not rerun or block unrelated tasks.
- Failure in a required task blocks only dependent synthesis claims.

`active_dataset` remains a UI focus and compatibility field. It is not the source
of truth for multi-file execution. Before a plan exists, analysis entry evaluates
the eligible current scope. After a plan exists, it evaluates only the datasets
bound to the current step.

### Evidence Synthesis

Every EvidenceRecord produced by a Stage 3C0B task must include:

- `task_id`;
- dataset name;
- dataset contract ID;
- method and tool calls;
- metric definition, grain, and time range;
- limitations and confidence.

The synthesis step consumes verified EvidenceRecords, not all raw datasets.
Results may be numerically compared only when definitions, units, grain, and time
scope are compatible. Otherwise the system presents separate findings and an
explicit compatibility limitation.

### Stage 3C0B Acceptance

- Every used file has at least one task binding.
- Independent tasks proceed without relationship confirmation.
- A failed optional task does not stop unrelated tasks.
- A missing required EvidenceRecord prevents dependent synthesis claims.
- Unsupported combination modes cannot be marked executable.
- Four-file analysis can produce separate evidence and one bounded synthesis.

## Stage 3C1A: Non-Mutating Join Preflight

### Supported Join Surface

The first executable join surface supports:

- exactly two datasets per operation;
- single or composite exact keys;
- same-name or left/right key pairs;
- `inner`, `left`, `right`, and `outer` joins;
- `one_to_one`, `many_to_one`, and confirmable `one_to_many` cardinality.

Many-to-many plans are blocked. A multi-table workflow must be expressed as
multiple two-table operations, with the derived dataset contracted and checked
again before it becomes input to the next operation.

### DataOperationRecord

Join planning and execution use one aggregate record rather than separate plan,
run, and lineage stores.

```json
{
  "operation_id": "join_<stable-id>",
  "operation_type": "join",
  "plan": {},
  "lifecycle_status": "planned",
  "confirmation_ref": "",
  "execution_result": null,
  "derived_dataset_refs": []
}
```

The nested plan is immutable and contains:

- session and source dataset refs;
- source dataset fingerprints and contract IDs;
- key pairs and join type;
- whether each material parameter is explicit or inferred;
- row counts, key null rates, distinct counts, and duplicate distributions;
- matching-key coverage;
- inferred cardinality;
- estimated output rows and expansion ratio;
- expected row loss for inner joins;
- non-key column collisions;
- expected output grain;
- risk classification, risk codes, and remediation.

The source fingerprint is a SHA-256 digest over the normalized dataset name,
row count, ordered column names and dtypes, and the full value/index hash from
`pandas.util.hash_pandas_object`. The operation ID is derived from the normalized
join parameters, source fingerprints, and risk-policy version.

Changing a material parameter creates a new record and marks the previous record
`superseded`. Confirmed records are never edited in place.

### Lifecycle

```text
planned
  + safe_to_execute -> executing
  + requires_confirmation -> awaiting_confirmation -> approved -> executing
  + blocked -> blocked
  -> cancelled

executing
  -> succeeded
  -> failed
  -> stale
```

`safe_to_execute`, `requires_confirmation`, and `blocked` are risk decisions.
Lifecycle status remains `planned`, `awaiting_confirmation`, `approved`,
`executing`, `succeeded`, `failed`, `stale`, `cancelled`, `superseded`, or
`blocked`. Keeping these fields separate prevents a risk result from being
mistaken for an execution state.

Stage 3C1A stops before `executing` and does not modify workspace data.

### Preflight Checks

The planner checks:

- source existence and eligibility;
- source contract and fingerprint availability;
- key existence and exact type compatibility;
- key null counts and ratios;
- unique counts and duplicate distributions;
- matching-key counts and coverage;
- cardinality;
- estimated output rows and expansion;
- expected unmatched or discarded rows for the requested join type;
- non-key column collisions;
- expected grain change;
- configured resource ceilings.

Candidate keys from relationship diagnostics are hints only. They cannot replace
data-based preflight.

### Risk Policy

`safe_to_execute` requires all of the following:

- datasets, key pairs, and join type were explicitly specified;
- key types match exactly;
- cardinality is one-to-one or safe-direction many-to-one;
- no warning threshold or resource ceiling is crossed;
- output grain and field collisions are unambiguous.

`requires_confirmation` includes:

- inferred key pairs or join type;
- one-to-many expansion within resource limits;
- warning-level unmatched, null-key, or row-loss ratios;
- planned suffix handling for non-key collisions;
- preflight cardinality that differs from the user's stated expectation.

`blocked` includes:

- missing datasets or keys;
- incompatible key types;
- many-to-many cardinality;
- output size above a hard resource ceiling;
- missing or invalid contracts or fingerprints;
- inability to estimate output size safely.

Confirmation cannot override blocked results.

### Central Thresholds

The risk function reads centralized configuration:

- `join_unmatched_warning_ratio`;
- `join_null_key_warning_ratio`;
- `join_max_expansion_ratio`;
- `join_max_output_rows`.

Business and resource thresholds are not hard-coded inside the classifier.
Tests supply explicit threshold fixtures. The initial conservative defaults are:

- unmatched or discarded row warning ratio: `0.20`;
- null-key warning ratio: `0.05`;
- maximum output expansion ratio: `5.0`;
- maximum output rows: `1_000_000`.

Every confirmation card shows the configured threshold and observed value that
triggered the warning. Changing a threshold changes the risk-policy version and
therefore invalidates prior operation IDs and approvals.

### Stage 3C1A Acceptance

- Every fixture deterministically returns safe, confirmable, or blocked.
- Identical data and parameters produce the same operation ID.
- Preflight does not change workspace or analysis state beyond the compact record
  reference.
- Many-to-many and resource blocks cannot be confirmed away.
- One high-confidence inferred key still requires confirmation.
- Multiple plausible keys produce one visible, answerable choice.
- Full statistics remain in artifacts; prompt summaries stay bounded.

## Stage 3C1B: Deterministic Confirmation And Execution

### Unified Confirmation Runtime

Stage 3C1B registers a data-operation approval action in the existing confirmation
action registry. It does not add another confirmation store, UI, or status model.

The question contains:

- operation ID;
- concise dataset, key, join-type, and cardinality summary;
- material risks and observed values;
- user-facing impact;
- execute, modify, and cancel actions.

Approval changes only the operation lifecycle status. It does not perform the
data mutation inside the confirmation resolution action.

### Deterministic Resume

The existing ContinuationRecord gains an operation reference. It must not copy
the mutable join arguments.

After approval:

1. The confirmation service records an idempotent approval receipt.
2. Resume loads the exact operation reference from the continuation.
3. The executor reloads the immutable plan by operation ID.
4. The executor runs before the LLM receives control again.
5. The execution result is appended to the resumed turn.
6. The LLM continues from the concrete result rather than recreating the call.

Modify cancels the approved version and starts a new plan. Cancel ends only the
join task; unrelated independent tasks may continue.

### Atomic Execution

Execution follows this order:

1. Acquire the session operation lock.
2. Return the existing receipt if the operation already succeeded.
3. Recompute and compare all source fingerprints.
4. Execute the join in a temporary DataFrame.
5. Run postcondition checks against the immutable plan.
6. Build preview, quality, dataset contract, and route artifacts in memory.
7. Verify that all required trust artifacts can be persisted.
8. Commit the derived dataset, operation record, compact state refs, and trust
   artifacts.
9. Append the legacy transform-log projection only after successful commit.

The executor never overwrites an existing dataset. If the requested output name
already belongs to the same succeeded operation, it returns the existing receipt.
If the name belongs to another source or operation, execution is blocked and a
new output name is required.

If a commit step fails, the executor uses the existing `workspace.remove()`
capability only for a dataset created by the current transaction, removes
temporary artifacts, leaves the active task incomplete, and marks the operation
failed with diagnostics. It must never remove a pre-existing name during rollback.

### Postcondition Validation

Postconditions check:

- actual versus estimated row count;
- resource ceilings;
- actual versus planned cardinality;
- match and null behavior;
- unexpected field collisions;
- explainable output grain;
- derived contract quality status.

Validation returns `pass`, `pass_with_warnings`, or `fail`. Only the first two
may commit. Warning codes become mandatory limitations on downstream evidence.

If source data changed after approval, execution returns `stale`, performs no
mutation, and creates a new preflight before any new question is asked.

### Derived Dataset Semantics

- The derived dataset is the output of one task, not a replacement for the whole
  multi-file scope.
- Source datasets remain eligible and available to other tasks.
- Downstream steps reference the derived dataset explicitly in `dataset_inputs`.
- The workbench shows its source datasets, operation ID, and validation status.
- Full lineage lives in the DataOperationRecord.

### Stage 3C1B Acceptance

- A safe plan executes once without confirmation.
- A confirmable plan suspends with one visible confirmation card.
- Approval executes the exact immutable operation.
- Repeated answers and retries do not duplicate execution or output datasets.
- Modify and cancel do not create derived data.
- Stale approval cannot execute.
- Failed postconditions leave no derived dataset or active task completion.
- Successful derived data receives existing preview, contract, quality, and route
  artifacts.
- Non-merge transform behavior remains unchanged.
- Join failure does not stop unrelated independent tasks.

## Reuse And Ownership Boundaries

Stage 3C must reuse these existing components:

- confirmation policy, service, store, action registry, and visible card;
- ContinuationRecord integrity and idempotency mechanisms;
- AnalysisPlan and workflow task generation;
- dataset preview and understanding contracts;
- quality scanning and route proposals;
- EvidenceRecord and claim verification;
- AnalysisSessionState compact-reference pattern;
- workspace sequential mutation and removal;
- workbench current-context and technical-detail sections.

The following existing records are not operation truth:

- `file_relationships` are diagnostics and candidate-key hints;
- `dataset_bundles` describe participation grouping;
- `active_dataset` is a current focus;
- `analysis_plan` describes analysis tasks;
- the legacy transform log is a compatibility projection.

The DataOperationRecord is new because no existing record owns immutable
cross-dataset parameters, preflight evidence, approval, execution receipt, and
derived lineage. It must remain the single source of truth for those concerns.

### Existing Integration Points

Implementation plans should begin from these existing ownership boundaries:

- `src/data_agent/agent/multi_file_scope.py`: eligibility and assignment
  projection, compact scope budgeting, and reason codes.
- `src/data_agent/agent/analysis_state.py`: compact refs and active-focus state;
  it must not become a second full operation store.
- `src/data_agent/agent/analysis_entry.py` and
  `src/data_agent/agent/route_capabilities.py`: select contracts for the current
  scope or task bindings rather than one global active dataset.
- `src/data_agent/tools/analysis_flow.py` and the existing task tools: extend
  AnalysisPlan step bindings and evidence records.
- `src/data_agent/agent/confirmation/`: policy, persistence, idempotency,
  resolution actions, and continuation integrity.
- `src/data_agent/tools/data_transform.py`: retain the public merge entry only as
  an adapter to the operation service; it must not keep a bypassing `pandas.merge`
  path.
- `src/data_agent/tools/data_io.py` and
  `src/data_agent/agent/trust_contracts.py`: extract and reuse the existing trust
  artifact workflow for derived data.
- `src/data_agent/agent/verification.py`: enforce operation lineage for derived
  evidence.
- `src/data_agent/agent/trust_view.py` and the existing web workbench: render
  compact user-facing projections, not independent status.

Before creating a new module or state collection, the implementation plan must
state why none of these owners can correctly hold the responsibility. This is a
required duplicate-system check, not an optional refactor preference.

## Trust Workflow Integration

The current load-data trust workflow should be extracted into a reusable internal
service that accepts a dataset name and DataFrame. Both source loading and derived
join output call the same service.

The service creates:

- preview digest;
- quality result and cleaning decision log where applicable;
- dataset understanding contract;
- route proposals;
- compact AnalysisSessionState refs.

Evidence created from a derived dataset must reference its dataset contract and
operation record. Claim verification must downgrade or fail evidence when the
referenced operation is missing, stale, failed, or carries an unacknowledged
critical warning.

A join audit is not stored as a cleaning decision. Cleaning and data operations
remain distinct artifacts so their semantics do not become ambiguous.

## Context Budget

Full plans, key distributions, preflight tables, and execution reports remain in
session artifacts. They are never injected wholesale into the system prompt.

Prompt context contains only:

- the current step ID and goal;
- current dataset bindings and combination mode;
- compact source contract refs;
- current operation ID, status, key summary, and risk class;
- no more than three material warnings;
- counts for older or omitted records.

Analysis state summary includes only operation counts and the most recent compact
refs. Superseded, cancelled, and historical operations are excluded from active
context. Identical source fingerprints and parameters reuse the same plan rather
than appending duplicates.

Tests must assert a fixed upper bound for the compact representation as file and
operation history grows.

## Workbench Contract

The workbench should answer:

1. Which files are technically usable?
2. Which files are actually used by the current plan?
3. What task does each used file support?
4. Why is another file available, not needed, or unavailable?
5. Is a join planned, awaiting a decision, executing, or validated?

The primary panel remains user-facing. Full key statistics and technical join
diagnostics stay collapsed. A waiting-confirmation label appears only when the
confirmation runtime has an active suspension for the operation.

Artifact production and export remain unchanged.

## Delivery Order And Stop Gates

### Slice 1: Stage 3C0A

- Replace the mixed participation classifier with eligibility and assignment.
- Remove relationship-driven assignment.
- add reachable material scope decisions;
- update workbench labels and reasons;
- run scope, confirmation, trust-view, and web regressions.

Stop if the four-file acceptance session cannot explain every file state.

### Slice 2: Stage 3C0B

- Extend AnalysisPlan and task bindings;
- remove single-active-dataset filtering as multi-file execution truth;
- execute independent tasks and evidence synthesis;
- enforce the supported combination-mode capability list.

Stop if independent tasks cannot produce isolated, verified evidence.

### Slice 3: Stage 3C1A

- Add DataOperationRecord and persistence;
- implement exact join preflight and risk policy;
- add compact operation refs to state and workbench;
- keep execution unavailable.

Stop if material fixtures cannot be deterministically classified.

### Slice 4: Stage 3C1B

- Register operation approval action;
- extend deterministic continuation by operation reference;
- add transactional executor and rollback;
- reuse the trust-artifact service for derived data;
- connect operation lineage to evidence verification.

Stop if idempotency, stale-plan protection, rollback, or trust-artifact generation
is not reliable.

Each slice receives its own implementation plan, red-green tests, commit, and
post-merge regression run. A later slice cannot compensate for an incomplete
earlier contract.

## Test Strategy

### Unit Tests

- eligibility and assignment priority;
- stable reason codes;
- material `needs_decision` policy;
- plan step dataset binding validation;
- capability-mode enforcement;
- source fingerprint and operation ID stability;
- cardinality and output-size estimation;
- risk policy thresholds;
- operation lifecycle transitions;
- evidence lineage checks;
- compact context limits.

### Integration Tests

- analysis entry before and after a multi-dataset plan;
- unified confirmation request, display, resolve, and resume;
- exact operation resume after approval;
- duplicate answer idempotency;
- workspace rollback after trust-artifact failure;
- derived dataset contract and route creation;
- independent task continuation after join failure;
- workbench parity with runtime state.

### Regression Tests

- non-merge `transform_data` operations remain unchanged;
- orphan relationship flags remain non-actionable;
- no final answer is emitted while a real blocking confirmation is unresolved;
- chart contract and report generation suites remain green;
- context compaction preserves active task and operation refs;
- existing single-file analysis behavior remains unchanged.

### End-To-End Acceptance

Replay session `5ba97a7bb7db` and verify:

- all four readable files receive correct eligibility and assignment;
- independently useful files contribute evidence without a join;
- only the necessary subset becomes a join candidate;
- no relationship uncertainty creates a ghost confirmation;
- a real join ambiguity creates one answerable confirmation card;
- approval resumes the exact plan;
- derived data has trust artifacts and bounded evidence limitations;
- the workbench explains scope, task roles, and operation status;
- prompt context remains bounded.

### Verified Baseline Before Stage 3C

At baseline commit `f66c7ce`, the following focused regression command passed
with `129 passed`:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_multi_file_scope.py `
  tests/test_multifile_regressions.py `
  tests/test_confirmation_session_api.py `
  tests/test_web_overhaul.py `
  tests/test_web_workbench_parity.py -q
```

`node -c src/data_agent/web/static/js/app.js` and `git diff --check` also passed.
The environment may emit a benign warning when pytest cannot write
`.pytest_cache`; this warning is not a test failure.

Every Stage 3C slice must rerun the relevant focused tests plus all tests affected
by its new ownership boundary. Passing only new unit tests is insufficient.

## Principal Risks And Mitigations

Risk: The new scope model silently replaces one mixed heuristic with another.

Mitigation: Eligibility is factual, assignment is task-derived, relationships are
excluded, and every non-default state has a stable reason code.

Risk: Multi-file planning creates unsupported operations in prose.

Mitigation: The planner receives and validates an explicit combination-mode
capability list.

Risk: Confirmation approval drifts into a different tool call.

Mitigation: Approval references an immutable operation and deterministic resume
executes it before returning control to the LLM.

Risk: Join output weakens downstream analytical rigor.

Mitigation: Derived data passes through the same trust workflow and evidence must
reference operation lineage.

Risk: Operation history inflates prompt context.

Mitigation: Full artifacts remain out of prompt; only one current compact record,
three warnings, and bounded recent refs are injected.

Risk: A large implementation causes broad regressions.

Mitigation: Four gated slices, no cross-slice shortcuts, and full confirmation,
trust-workflow, web, chart, and single-file regression checks at each boundary.

## Final Acceptance Criteria

- File usability, current use, and combination method are independent facts.
- Every used file is bound to at least one analysis task.
- Multiple files can contribute without any join.
- Only an explicit join task can start join preflight.
- Safe joins, confirmable joins, and blocked joins are deterministic.
- Blocked structural risks cannot be approved away.
- Confirmation resumes the exact immutable operation.
- Execution is idempotent, stale-safe, and rollback-capable.
- Derived datasets receive existing trust artifacts and evidence lineage.
- Independent analysis survives unrelated task and join failures.
- Workbench state matches confirmation runtime and task truth.
- Context growth remains bounded.
- Union, fuzzy mapping, many-to-many execution, and automatic repair remain out of
  scope until this closed loop is proven stable.

## Compression-Resistant Resume Checklist

After any context reset or handoff:

1. Read this specification completely.
2. Check branch, worktree status, and recent commits before editing.
3. Identify the current slice; never infer that approval of this design approved
   implementation of every slice at once.
4. Re-read that slice's goals, non-goals, acceptance criteria, and stop gate.
5. Inspect the existing integration points before proposing new abstractions.
6. Write and obtain approval for the slice implementation plan before code.
7. Use red-green tests for each behavior change.
8. Run focused and cross-system regressions before committing.
9. Record implementation decisions, deviations, verification commands, and
   results in the slice plan or verification note.
10. Stop and return to design review if repository evidence conflicts with this
    specification or reveals a new cross-system risk.

As of this document revision, the design is complete and no Stage 3C production
code has been implemented. The next planned deliverable is the Stage 3C0A
implementation plan.
