# Measurement Identity and Honest Release Gates Design

**Status:** Implemented and product-validated (uncommitted)

**Date:** 2026-07-28

**Branch:** `codex/analysis-reliability`

**Design baseline:** `776a866624cb729c87a6a6c57629b10f043b6d19`

**Amends:**

- `docs/superpowers/specs/2026-07-27-analysis-execution-and-publication-reliability-design.md`
- `docs/superpowers/plans/2026-07-27-analysis-execution-and-publication-reliability.md`

## 1. Decision summary

The original reliability design remains authoritative except where this
document explicitly amends it.

This amendment makes two load-bearing corrections:

1. Evidence is bound to a server-owned measurement identity, not inferred from
   a coincidentally equal number, unit, direction, and scope.
2. A release result is reported by gate. Deterministic backend tests, browser
   behavior, and live-provider analysis quality are separate required gates.
   Tests that were not collected or not run cannot contribute to a product
   release PASS.

The user-facing answer remains free-form Markdown. Internal evidence markers
are extended to identify one measurement:

```text
[[evidence:<evidence_id>#<measurement_key>]]
```

When exact identity cannot be independently verified, the answer is still
published completely with the affected claim classified as exploratory or
unsupported as appropriate. Missing evidence identity never restarts analysis
tools and never reduces the entire response to an empty shell.

## 2. Why the original plan must be amended

### 2.1 Specification contradiction

The original design requires current-plan claim keys for automatic evidence
projection. However, Task 9 Step 7 of the implementation plan defines
automatic attachment using:

- claim class;
- quantity;
- unit;
- direction;
- time scope;
- population or dataset scope;
- current plan ID.

It does not require the claim's metric identity to match the evidence
measurement's metric identity.

The positive example in the original plan tests only:

```text
claim:    revenue increased 12%
evidence: revenue increased 12%
```

It has no semantic-collision counterexample such as:

```text
claim:    profit increased 12%
evidence: revenue increased 12%
```

The two statements can have identical values, units, directions, time scopes,
population scopes, plan IDs, and claim classes while referring to different
metrics. Therefore the enumerated identity is insufficient for safe
publication.

### 2.2 Implementation evidence

Commit `776a866` implemented the weaker enumerated rule and passed its focused
tests. A scoped review then demonstrated that revenue evidence could verify a
same-value profit claim. The implementation also relied on hand-built evidence
shapes that were richer than records produced by the real
`project_structured_computation_evidence` path.

The review finding governs because it disproves the safety invariant. The
current `776a866` matching behavior must be removed or replaced; it is not an
acceptable compatibility path.

### 2.3 Product-flow diagnosis

The assurance gate did not directly stop analytical tool execution:

- the core analysis prompt did not become materially more conservative;
- `block_analysis` was not a mid-turn tool interrupt;
- the quality guard attempted to continue analysis rather than end it.

The observed analysis-depth loss primarily came from tool schemas, sandbox
execution, error cascades, routing, method capability, and premature
completion. Assurance nevertheless caused direct product harm because it was
placed synchronously in the publication path before ordinary successful
computations reliably became usable evidence.

The resulting failure chain was:

```text
shallow or partially failed execution
  -> computation refs exist
  -> evidence records are absent or unusable
  -> final audit cannot verify claims
  -> whole-answer fallback strips useful content
```

The repair must preserve the value of deterministic assurance without making
evidence bookkeeping a precondition for continuing or displaying useful
analysis.

## 3. Goals and non-goals

### 3.1 Goals

1. Prevent cross-metric evidence substitution even when values and scopes are
   identical.
2. Let structured tool computations create independently verifiable
   measurement identities automatically.
3. Preserve free-form Chinese Markdown answers, including headings, tables,
   lists, and limitations.
4. Keep unsupported claims from being promoted to verified while preserving a
   complete useful answer.
5. Make skipped, ignored, static-only, browser, and live-provider test status
   explicit.
6. Require product-level evidence before claiming that uploaded-file analysis
   works normally.
7. Preserve the existing canonical authorities:
   `analysis_requirement.v1`, `evidence_record.v2`, and
   `final_answer_audit.v1`.

### 3.2 Non-goals

1. Replacing the final answer with a rigid JSON response.
2. Letting an LLM invent metric aliases or decide evidence equivalence.
3. Adding a second evidence store, requirement evaluator, or final-answer
   authority.
4. Recomputing analysis solely to satisfy citation or evidence rituals.
5. Mutating historical sessions, evidence, uploaded data, or raw snapshots.
6. Disabling deterministic assurance in production.
7. Treating tool-call count, answer length, or absence of exceptions as proof
   of analytical quality.

## 4. Safety invariants

The following invariants apply in every rollout mode:

1. Equal values do not imply equal metrics.
2. A marker is a reference, not authorization. The server independently
   verifies every material identity field after resolving it.
3. Missing, incomplete, ambiguous, stale, cross-plan, cross-version, or
   cross-metric identity never verifies a claim.
4. Automatic binding never creates evidence and never reconstructs plan,
   metric, or scope identity from model prose.
5. Free-form `run_python`, unstructured output, and failed tools are not
   automatically upgraded to trusted structured evidence.
6. Missing evidence identity never schedules another analysis tool call.
7. An evidence failure acts on the affected claim, not the whole answer.
8. Internal evidence markers are removed from the published and persisted
   user-visible assistant message. Structured audit diagnostics may retain the
   resolved IDs.
9. Historical records are not backfilled into stronger evidence.
10. No production configuration disables value, direction, unit, metric,
    scope, dataset-version, failed-computation, grain, or unsupported
    causal/inferential blockers.

## 5. Server-owned measurement identity

### 5.1 Measurement identity fields

Every newly auto-projected structured measurement eligible for verified
publication receives a `measurement_identity.v1` payload owned by the server.
It contains:

| Field | Purpose |
|---|---|
| `measurement_key` | Opaque stable key for this exact projected measurement |
| `metric_key` | Canonical machine metric identity supplied by trusted tool metadata or structured output |
| `claim_key` | Canonical plan-step claim identity |
| `metric_label` | Server-trusted user-facing label |
| `metric_aliases` | Bounded deterministic aliases from trusted metadata only |
| `computation_ref_id` | Exact producing computation |
| `plan_id` and `plan_version` | Current canonical plan identity |
| `step_id` | Bound executable plan step |
| `requirement_ids` | Requirements the measurement may satisfy |
| `dataset_versions` | Exact current dataset-version set |
| `time_scope` | Normalized time scope |
| `population_scope` | Normalized population or dataset scope |
| `value` and `unit` | Canonical quantitative result |
| `direction` | Canonical effect or change direction when applicable |
| `allowed_claim_class` | Maximum semantics supported by the computation |

`metric_key` and `claim_key` serve different purposes. The metric key answers
"what was measured"; the claim key answers "which planned claim or question
does this computation address." Neither may be inferred from the numeric value.

### 5.2 Key generation

`measurement_key` is generated by the server from a canonical serialization of
the producing computation identity, metric key, claim key, plan and step
identity, dataset versions, normalized scope, value, unit, direction, and
allowed claim class.

The key:

- is deterministic for the same canonical projected measurement;
- changes when a material identity field changes;
- is opaque to the model and user;
- is not an array index;
- is not trusted without resolving the corresponding evidence record.

The exact digest algorithm is an implementation detail, but its canonical
input fields are part of this contract and require regression tests.

### 5.3 Trusted metric labels and aliases

Metric labels and aliases may come only from:

1. original dataset column names preserved by the structured computation;
2. declared structured tool-output metadata;
3. a bounded server-maintained mapping tied to a tool capability.

Model-generated semantic paraphrases are not added automatically. If a claim's
metric wording does not exactly match a trusted label or alias, the claim
remains exploratory rather than being fuzzy-matched.

This policy is intentionally conservative at the publication boundary, while
leaving the analytical tool flow unrestricted.

## 6. Synthesis and audit flow

### 6.1 Projection

After a successful structured tool call:

1. persist the existing `computation_ref.v1`;
2. verify exact execution-envelope, plan, step, requirement, and current
   dataset-version binding;
3. extract only declared structured measurements;
4. create a server-owned measurement identity for each eligible measurement;
5. validate and persist the containing `evidence_record.v2`;
6. add a bounded projection diagnostic on failure and continue the turn.

Projection failure never activates an analysis tool or evidence-recording
ritual.

### 6.2 Evidence catalog

The bounded synthesis catalog includes, for each eligible measurement:

- evidence ID;
- measurement key;
- metric key and trusted display label;
- claim key;
- value, unit, and direction;
- time and population scope;
- dataset versions;
- allowed claim class;
- required limitations.

The catalog instructs the model to place this marker adjacent to a claim that
uses the exact measurement:

```text
[[evidence:ev_123#m_revenue_change_abc]]
```

The model still writes ordinary Markdown. It is not required to serialize the
entire answer into a schema.

### 6.3 Independent final audit

For every material claim with a measurement marker, the server:

1. resolves the exact evidence ID;
2. resolves the exact measurement key within that evidence;
3. checks current plan ID and version;
4. checks exact dataset-version set equality;
5. checks step, claim key, and requirement eligibility;
6. checks value, unit, direction, time scope, and population scope;
7. checks the claim's metric wording against the trusted metric label or
   aliases;
8. checks that the claim class does not exceed the allowed class;
9. applies the existing canonical evidence and requirement verification.

The marker itself cannot bypass any check.

### 6.4 Publication outcomes

| Audit result | Claim action | Public behavior |
|---|---|---|
| Exact identity and all required checks pass | `verified` | Publish normally |
| Traceable computation exists but identity, independent validation, stability, or assumptions are incomplete | `exploratory` | Publish with a specific limitation such as `未经独立校验` |
| Value, direction, unit, metric, scope, version, grain, or permitted claim semantics contradict the evidence | `unsupported` | Replace only that assertion with a specific diagnostic |

The complete response retains:

- supported findings;
- exploratory findings and limitations;
- completed analyses;
- failed or unresolved analyses;
- method and data limitations;
- safe next actions.

It must not degrade to the historical generic English warning or a heading and
table shell with the substantive analysis removed.

### 6.5 Stable diagnostics

At minimum, the audit exposes bounded machine-readable codes:

- `measurement_identity_missing`
- `measurement_marker_invalid`
- `measurement_not_found`
- `measurement_metric_mismatch`
- `measurement_claim_key_mismatch`
- `measurement_scope_mismatch`
- `measurement_dataset_version_mismatch`
- `measurement_ambiguous`

These codes inform synthesis-only revision and observability. They never
schedule tool execution.

## 7. Compatibility and migration

### 7.1 New records

New eligible structured computations receive measurement identities. New
synthesis catalogs use the measurement-grain marker.

### 7.2 Historical records

Historical conversations and evidence are loaded unchanged.

The legacy marker:

```text
[[evidence:<evidence_id>]]
```

may verify a claim only when the referenced current evidence has exactly one
measurement and the server can independently validate the complete metric,
claim-key, plan, version, value, unit, direction, and scope identity. Otherwise
the claim is exploratory or unsupported.

Missing fields are not filled from model prose and are not silently treated as
equal.

### 7.3 Existing unsafe implementation

The number-first automatic matcher introduced by `776a866` has no legacy
authorization status. It must be replaced rather than hidden behind a feature
flag.

## 8. Rollout and rollback

The existing assurance publication modes remain `tiered` and `strict`. There
is no production `off` value.

Measurement binding receives an independent rollout setting:

| Mode | Purpose | Authorization behavior |
|---|---|---|
| `shadow` | Compare the new identity result with existing diagnostics | Never upgrades a claim solely from the shadow result |
| `soft` | Default product mode | Exact matches verify; missing or incomplete identity publishes as exploratory; contradictions remain unsupported |
| `enforced` | Strict requirement scenarios | Claims required to be verified remain unsupported when exact identity is absent; the rest of the answer still publishes |

Rollback may disable measurement-binding v2 authorization and return to
explicit validated evidence recording. It may not restore number-only matching
or disable the existing deterministic blockers.

The selected mode and comparison counts are persisted in bounded turn
diagnostics.

## 9. Honest release gates

### 9.1 Status vocabulary

Every gate reports exactly one status:

- `PASS`
- `FAIL`
- `NOT_RUN`
- `BLOCKED`

An overall release is `PASS` only when every required gate is `PASS`.
`NOT_RUN` is never treated as success.

The previous phrase "complete release gate" for a run that excluded browser
and live-provider verification is retired. That run may be reported only as a
deterministic backend gate.

### 9.2 Gate A: test-harness integrity

This gate proves that tests can fail truthfully:

1. enumerate collected and ignored release-critical tests;
2. reject release-critical files in `collect_ignore`;
3. require custom runners to exit non-zero when any internal check fails;
4. reject pytest tests that return non-`None` values instead of asserting;
5. preserve test isolation from historical sessions, tasks, datasets, and
   module-level singleton state;
6. report warnings and skips by category rather than hiding them in a total.

### 9.3 Gate B: contract and mutation tests

Focused tests cover:

- server-owned measurement-key generation;
- exact metric and claim-key matching;
- plan, step, requirement, and dataset-version equality;
- value, unit, direction, time, and population scope;
- trusted labels and aliases;
- legacy single-measurement compatibility;
- missing and ambiguous identities.

Mutation tests must fail if an implementation:

- removes metric or claim-key checking;
- treats missing identity as equal;
- accepts stale or partial dataset versions;
- trusts a marker without resolving its measurement;
- permits number-only matching.

### 9.4 Gate C: real internal end-to-end analysis

Tests start with real structured tool output and cover:

```text
tool computation
  -> computation_ref
  -> automatic evidence projection
  -> measurement identity
  -> bounded catalog
  -> free-form Markdown with marker
  -> final audit
  -> tiered publication
```

Hand-built evidence records may be used only for focused unit cases, never as
the sole proof of the production path.

Required adversarial cases include:

- revenue evidence cannot support a same-value profit claim;
- correct evidence ID with the wrong measurement key;
- correct measurement key with mismatched metric wording;
- cross-plan, cross-step, cross-version, and cross-scope reuse;
- multi-measurement ambiguity;
- omitted marker;
- incomplete historical identity;
- Chinese original column labels;
- headings and tables preserved after claim actions.

### 9.5 Gate D: analysis-quality replay

Representative privacy-safe uploaded-file scenarios test the main product
outcome, not only assurance:

- grain, target, feature scope, and missingness are inspected when applicable;
- the selected method matches the question;
- univariate and multivariable coverage is reached when required;
- stability, validation, time dependence, collinearity, or limitations are
  addressed when applicable;
- tool failure produces a bounded fallback or exact diagnostic;
- a single superficial tool cannot satisfy a multi-step analysis request;
- the final answer contains useful supported or exploratory findings;
- unsupported demographic, grain, inferential, predictive, or causal claims
  are not promoted.

Tool-call count and answer length remain diagnostics only. Deterministic replay
must verify semantic coverage and traceable computations.

### 9.6 Gate E: browser and SSE behavior

A real browser test, not a source-text assertion, verifies:

1. an uploaded file can start analysis from the UI;
2. safe progress becomes visible before final publication;
3. the DOM updates during the stream rather than only after `turn_end`;
4. the audited final answer is non-empty and visible;
5. headings, tables, Chinese text, and limitations render correctly;
6. refresh and session switching retain the final answer;
7. suspend/resume, interruption, and error paths do not strand a blank
   assistant turn.

The current `state.turns` versus Alpine reactive-proxy path is a blocking
diagnostic target. It must be reproduced or disproved in a browser before the
gate can pass.

### 9.7 Gate F: live-provider behavioral quality

When a configured provider is available, run each representative uploaded-file
scenario three times.

For the Task 12 product-completion profile, Gate F is required. If the
configured provider cannot be exercised, Gate F is `BLOCKED` and the overall
product release cannot be reported as `PASS`; deterministic implementation
work may still be reported separately by its own gate status.

Every run must:

- terminate without repeated tool or evidence-bookkeeping loops;
- reach the applicable analytical coverage or a precise terminal limitation;
- produce a complete non-empty Chinese answer;
- preserve claim strength within computed support;
- show progress before final publication.

Provider variability may change wording and selected equivalent methods. It
may not excuse missing terminal state, empty publication, semantic
overclaiming, or failure to perform the requested analysis.

## 10. Web/SSE diagnosis boundary

The backend intentionally buffers unaudited analytical findings. This does not
authorize a silent UI.

Before audit, the UI receives only server-authored method and state narration.
After audit, the final answer may be emitted as text deltas, and each delta must
be observable in the current session's reactive DOM state.

The current code obtains the assistant `turn` from `state.turns` before
assigning `this.turns = [...state.turns]`, mutates that reference on
`text_delta`, and refreshes the reactive array at `turn_end`. This is a
plausible explanation for "no live update, then all at once," but it remains a
diagnosis to prove with the browser gate rather than an assumed implementation
fix.

## 11. Implementation boundaries

### 11.1 Immediate implementation slice

The next implementation plan covers:

1. remove the unsafe `776a866` number-first binding;
2. add measurement identity to real automatic evidence projection;
3. extend the bounded catalog and hidden marker syntax;
4. independently validate metric and claim identity in final audit;
5. add real end-to-end, adversarial, compatibility, and mutation tests;
6. add honest gate reporting and test-harness integrity checks needed to
   prevent false PASS.

### 11.2 Phase C product validation

After the deterministic implementation slice is green, Phase C:

1. systematically reproduces and fixes any Web reactive/SSE defect;
2. performs real browser acceptance;
3. runs live-provider three-run analysis-quality acceptance when configured;
4. records the gate matrix;
5. marks the parent design implemented only when every required gate passes.

Browser behavior is not silently mixed into the measurement-identity patch
before reproduction, but it is a required Task 12 completion gate.

## 12. File ownership expectations

The implementation plan should prefer these existing owners:

| Concern | Existing owner |
|---|---|
| Measurement projection and evidence record validation | `src/data_agent/agent/evidence_contracts.py` |
| Evidence catalog and synthesis marker instruction | `src/data_agent/agent/synthesis_policy.py` |
| Claim extraction, attachment, and final audit | `src/data_agent/agent/answer_quality.py` |
| Runtime orchestration only | `src/data_agent/agent/loop.py` |
| Publication and rollout configuration | `src/data_agent/config.py` and existing publication owner |
| SSE mapping | `src/data_agent/web/blueprints/chat.py` |
| Reactive browser state | `src/data_agent/web/static/js/app.js` |
| Evidence projection/audit tests | existing focused evidence and final-answer suites |
| Browser and SSE acceptance | existing Web/SSE suites converted or replaced with collected executable tests |
| Release orchestration | existing Task 12 replay runner or a thin deterministic gate runner |

No new trust authority is introduced.

## 13. Acceptance criteria

The design is implemented only when:

1. Revenue evidence cannot verify a same-value profit claim.
2. Every newly auto-projected eligible measurement has a server-owned
   measurement key, metric key, claim key, and exact provenance identity.
3. The final audit independently validates the marker and all material
   measurement fields.
4. Missing or ambiguous identity cannot verify a claim and cannot restart
   analysis.
5. Complete Markdown answers survive exploratory and unsupported claim actions.
6. Historical sessions and evidence remain unchanged.
7. No production assurance-off path or number-only fallback exists.
8. Test-harness integrity proves that release-critical failures produce a
   failing process.
9. The deterministic internal pipeline passes real projection-to-publication
   tests.
10. Representative analysis replays meet method-depth and answer-quality
    requirements.
11. A real browser shows progress before the final answer and visibly updates
    the final answer without waiting solely for `turn_end`.
12. Live-provider runs pass the required repeated behavioral acceptance when a
    provider is configured.
13. The final gate matrix contains no required `NOT_RUN`, `BLOCKED`, or `FAIL`
    entry.

## 14. Supersession record

This document supersedes only:

1. the identity field list and positive-only matcher examples in Task 9 Step 7
   of the 2026-07-27 implementation plan;
2. any interpretation that equal quantity, unit, direction, scope, and plan are
   sufficient without metric and claim-key identity;
3. the number-first automatic attachment behavior introduced by `776a866`;
4. any release-status language that treats an excluded browser or live-provider
   gate as passed.

All other accepted constraints of the parent design and plan remain in force.
