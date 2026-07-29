# Task 6 Implementer Report

## Outcome

Implemented and proved the real persisted-computation -> automatic projection
-> evidence catalog -> dynamic measurement marker -> final-answer audit ->
tiered publication chain. The factor replay no longer scripts
`record_evidence_record`; it publishes only from server-projected, bound
measurements produced by real `quick_profile`, `correlation_analysis`, and
`factor_relationship_analysis` calls.

## Approved scope amendment

The plan assumption that Task 6 required fixture-only wiring was disproved by
the initial RED run: 15 pipeline failures and replay projection counts of
profile=0, correlation=0, factor=0 exposed shared contract gaps. Under the
approved Scheme A amendment, the implementation therefore also changed:

- `src/data_agent/agent/evidence_contracts.py`
- `src/data_agent/agent/verification.py`
- `src/data_agent/tools/registry.py`
- focused compatibility tests for the affected shared contracts

Production changes are limited to truthful quick-profile evidence fields,
trusted `var1`/`var2` and coefficient-term measurement contexts, structured
requirement-semantic projection, unitless-value handling, and tightly
qualified cross-step prerequisite satisfaction.

## TDD and fail-closed evidence

- RED: new pipeline test initially reported 15 failures.
- RED: real factor replay projected no usable evidence; after truthful registry
  fields it exposed missing metric contexts and structured requirement fields.
- GREEN: 13 identity mutations, same-value/different-metric, and two-pair
  identity uniqueness all pass.
- GREEN: the untampered dynamic factor marker passes the real audit.
- GREEN: changed prerequisite field semantics, changed assumption, stale plan
  digest, dataset mismatch, and `legacy_unbound` provenance all block.
- GREEN: six repeated profile calls cannot satisfy multivariable or
  collinearity requirements and cannot publish a significant-effect claim.

Cross-step prerequisite evidence is accepted only when its canonical semantic
contract is exactly equivalent and the record has a valid v2 identity, active
requirement membership, current plan and step digests, exact dataset versions,
bound provenance, and a hydratable persisted computation artifact. Selected
measurement metric/value/unit/direction/scope checks are unchanged.

## Verification

- `tests/test_measurement_identity_pipeline.py -q`: 16 passed.
- `tests/test_analysis_reliability_replays.py -q`: 7 passed.
- Focused release/compatibility suite: 166 passed.
- Deterministic replay CLI: `accepted: true`; all four scenarios true.
- Targeted post-review semantic/shallow checks: 2 passed.
- `git diff --check` and `py_compile` passed.
- Bounded `pytest tests -q` ran for 300 seconds to 34% with no failures shown
  and 9 skips, then hit the explicit time cap.

## Self-review

No hand-built evidence or mock verifier remains in the successful factor
path. Replay acceptance is requirement-driven, not tool-count-driven.
Production ambiguity remains fail-closed; only the replay supplies an explicit
authoritative preferred step for the factor call. Limitation downgrades require
a matching published limitation token rather than any limitation text.

## Fix Round 1 — qualified requirement evidence and semantic authority

### Outcome

Closed the review findings without weakening measurement authority:

- Exact-ID prerequisite satisfaction now uses the same current, bound,
  hydratable evidence qualification as semantic-equivalent satisfaction.
- Correlation design assumptions come only from the real tool's explicit
  structured attestation; the projector no longer invents an assumption from
  the presence of a method name.
- Requirement semantics contain labels, statuses, and measurement references,
  but no copied numeric results. Numeric authority remains exclusively in
  canonical measurements.
- Compact and full `quick_profile` outputs now share a truthful stable
  capability contract.
- A real driver-decomposition replay binds the persisted tool computation to
  the current plan step and proves observed segment coverage plus
  hypothesis-only exploratory opportunity candidates. The same plan without
  decomposition leaves both requirements unmet.
- `contribute_decomposition` explicitly emits
  `allowed_claim_class="descriptive_attribution"`; execution control normalizes
  that ceiling downward to exploratory association, and projected opportunity
  semantics set `causal_authorization="none"`.

### RED/GREEN evidence

- RED: five same-ID mutations (stale plan, stale step, dataset mismatch,
  `legacy_unbound`, and unavailable computation artifact) incorrectly
  satisfied the prerequisite before evidence qualification.
- RED: a correlation method name alone incorrectly satisfied the design
  assumption.
- RED: projected requirement semantics duplicated numeric sample, coefficient,
  multiplicity, collinearity, time-dependence, and fit values.
- RED: compact `quick_profile` did not produce the advertised
  `columns.missing_pct`.
- RED: driver decomposition initially had no measurement identity for its
  categorical `value` labels, then correctly failed closed until the real tool
  attested a noncausal claim class.
- GREEN: the exact-ID positive and all five negative mutations pass; explicit
  assumptions, nonnumeric semantics, compact profile, and real
  driver-decomposition positive/negative replays all pass.

### Verification

- Measurement identity pipeline: 24 passed.
- Deterministic replay suite: 9 passed.
- Tool capability truthfulness: 10 passed.
- Affected projector/audit/publish/statistical compatibility suite: 204 passed.
- Deterministic replay CLI: `accepted: true`; all four canonical scenarios true.
- `py_compile` and `git diff --check`: passed.
- Bounded `pytest tests -q` reached 28% in 300.4 seconds with 9 skips and no
  displayed failures, then hit the explicit timeout. This is not reported as a
  full-suite pass.

### Self-review

The driver replay uses a normal production plan binding and a persisted real
tool output; the replay and projector do not synthesize claim class,
requirements, candidates, or numeric values. Categorical decomposition labels
participate in measurement identity only when `value` is a string, avoiding a
numeric-context shortcut. Requirement satisfaction remains fail-closed for
stale, unbound, mismatched, or unhydratable evidence. Remaining concern is only
the incomplete bounded broad-suite run; all affected focused gates are green.
