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
