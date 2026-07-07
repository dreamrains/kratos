# Data Operation Readiness Decision

## Decision

Not ready: keep Stage 3C1A cross-file data operations deferred.

The current continuation evidence supports the Stage 3C0B model:

- understand data scope first;
- validate relationships as diagnostic evidence;
- execute independent dataset analyses;
- synthesize from EvidenceRecords;
- do not materialize joins or derived datasets by default.

There is not yet repeated evidence that independent evidence plus synthesis is insufficient for the real scenarios covered in this continuation slice.

## Evidence

| Scenario | User value | Independent evidence + synthesis sufficient? | Operation risk | Decision |
|---|---|---|---|---|
| Game A banner, IAP, rewarded video | Compare channel-level performance and synthesize business implications across related files | Yes. The scenario manifest uses `independent_then_synthesis` and forbids `joint` / `aggregate_then_join` | Joining would create unnecessary grain assumptions between channel summaries | No operation layer justified |
| Savings-card orders + recent user flow | Understand whether a user-key relationship exists and what risk it carries | Yes for current diagnostic need. Relationship value/risk is visible without materializing a join | Real data shows high key coverage but many-to-many cardinality, row multiplier > 1, broader flow time range, and duplicated users on both sides | Defer operation; report diagnostic relationship only |
| Unrelated files | Prevent false relationship inference | Yes. The correct behavior is exclusion or independent analysis unless the user supplies a validated business key and need | Any automatic join would be misleading | No operation |
| Relationship fault injection | Ensure duplicate keys, missing keys, and time mismatch are caught | Yes. Deterministic validation and quality rubric catch modeled faults | Executing an operation would turn known bad relationships into false authority | No operation |

## Current Source Boundary

The project already has general `data_operation` intent and basic operation tests for actions such as filter, select, sort, and group aggregation. That is not the Stage 3C1A decision surface.

Stage 3C1A would mean a reusable cross-file operation capability with records, preflight, approval, deterministic resume, idempotency, and derived-output registration. The current evidence does not justify that complexity yet.

## Why Independent Evidence Plus Synthesis Is Still Enough

Current Phase 1-4 outputs show that:

- relationship validation can explain candidate keys, cardinality, coverage, null rates, row-multiplier risk, and time/grain concerns;
- Workbench exposes relationship value and risk without presenting join authority;
- quality rubric blocks invalid relationship use only when it supports a material claim;
- synthesis can request bounded independent evidence before answering;
- unsupported claims and invalid relationship use are already visible as claim-level readiness failures.

This covers the current real-data needs without introducing a new operation lifecycle.

## Required Evidence Before Reopening Stage 3C1A

Write a Stage 3C1A operation spec only if future real scenarios repeatedly show that all of the following are true:

- the user asks for a cross-file claim that cannot be answered by independent evidence plus synthesis;
- the business value depends on a materialized row-level or aggregate-derived combination;
- relationship validation confirms key quality, cardinality, grain, and time compatibility for the proposed operation;
- the operation can be bounded to an exact two-dataset preflight;
- the user-facing result would be materially better than a diagnostic relationship plus independent analyses;
- safety mechanisms can prevent row multiplication, stale source use, hidden derived data, and accidental reuse of unapproved operations.

## If Ready Later

Stage 3C1A must include:

- immutable `DataOperationRecord`;
- exact two-dataset preflight;
- source fingerprints;
- user approval for risky operations;
- deterministic resume;
- idempotency;
- rollback or immutable derived outputs;
- derived trust artifact registration.

It must not:

- add `joint` or `aggregate_then_join` to Stage 3C0B plan modes;
- execute joins because two files share a column name;
- treat relationship diagnostics as operation approval;
- hide derived data from Workbench, evidence, or verification.

## Next Recommended Work

Keep improving golden scenarios and final-answer quality before designing operations. The next useful signal is a real user question where the current agent clearly cannot answer without a specific cross-file operation. Until then, the safer architecture is to keep operations deferred and strengthen evidence/synthesis quality.
