# Task 5 Implementer Report

## Outcome

Implemented the measurement-evidence binding rollout without adding a second
verification or publication authority:

- configuration accepts exactly `shadow`, `soft`, and `enforced`, defaulting
  final-answer runtime audits to `soft`;
- direct verifier and audit callers retain the safer `enforced` default;
- `soft` and `enforced` authorize only a canonical, exact measurement-grain
  v2 marker after the existing plan, step, requirement, dataset, computation,
  metric, value, unit, direction, scope, claim-class, and semantic checks;
- `shadow` performs and counts those checks but downgrades rather than
  authorizing;
- `soft` and `shadow` may downgrade exactly one markerless current-computation
  candidate to exploratory, but never attach an evidence id or measurement key
  and never return `passed`;
- zero candidates remain unsupported and multiple candidates remain ambiguous;
- record-only markers no longer recover unsafe number-first authorization in
  any mode;
- tiered publication preserves the rest of a complete answer and strips all
  internal markers.

## Candidate and diagnostic contract

Exploratory discovery is limited to current-plan `evidence_record.v2` records
with bound provenance, `computation_ref.v1`, exact current plan and step
digests, and an exact current dataset-version set. Final-answer runtime audits
also perform the existing persisted computation-artifact hydration and hash
check before a candidate can survive to publication.

Identity-bearing candidates run the canonical measurement identity checks.
Current projector-owned unbound candidates require
`identity_status="metric_identity_missing"` plus metric/definition wording and
exact value, unit, direction, time scope, population scope, and claim-class
compatibility. Historical, non-v2, stale, model-authored, and merely
number/scope-similar measurements do not qualify.

The persisted bounded diagnostic contains only:

- selected mode;
- exact v2 match count;
- v2 authorization count;
- exploratory downgrade count;
- measurement contradiction count.

It never contains claim text or measurement values.

## Publication and retry behavior

Measurement bookkeeping codes are explicitly separate from computation-repair
codes. `measurement_identity_missing` and `measurement_marker_invalid` may use
the existing single synthesis revision when evidence exists. The instruction
requires measurement-grain markers and says `Do not call tools`.

Every other measurement contradiction goes directly to claim-tier
publication. If any measurement bookkeeping code is present, even alongside a
generic computation code, the gate cannot schedule `mode="analysis"`, consume
the analysis retry flag, or restart tools. The existing synthesis counter and
budget remain unchanged and bounded.

## TDD evidence

Initial required-suite baseline at `e652329` was `138 passed, 2 failed`. Both
failures were Task 5 publication behavior: marker stripping left a doubled
space, and markerless evidence followed the obsolete publication expectation.

After adding rollout tests first, the prescribed RED command produced
`7 failed, 23 passed, 81 deselected`. Failures were the missing config field,
missing mode propagation, missing soft candidate downgrade, and missing
synthesis-only measurement repair.

An adversarial mixed-code test was also observed RED: a measurement
contradiction plus `unsupported_claim` requested `mode="analysis"` while
budget remained. The minimal gate change made the presence of measurement
bookkeeping suppress analysis retry; the focused result was `9 passed`.

## Verification

- Required publication/no-recomputation suite:
  `163 passed in 21.05s` in the fresh pre-commit run.
- Broader bounded assurance suite:
  `115 passed in 5.91s` across automatic evidence projection, computation
  evidence binding, verification-layer behavior, and Stage 3C0B compatibility.
- Focused mixed-code/bookkeeping suite: `9 passed in 2.48s`.
- `git diff --check` and Python compilation are rerun immediately before
  commit.

The full repository suite was not run; the broader run was intentionally
bounded to the measurement/provenance/publication surfaces touched here.

## Files

Production:

- `src/data_agent/config.py`
- `src/data_agent/agent/answer_quality.py`
- `src/data_agent/agent/verification.py`
- `src/data_agent/agent/trust_workflow_runtime.py`
- `src/data_agent/agent/loop.py`

Tests:

- `tests/test_workspace_config.py`
- `tests/test_final_answer_claim_audit.py`
- `tests/test_final_answer_publish_gate.py`
- `tests/test_tiered_analysis_publication.py`
- `tests/test_verification_layer.py`

## Concerns

No known correctness blocker remains. Artifact hydration requires
`sessions_root`, as in the existing verifier contract; production final-answer
runtime supplies it. Direct unit-level verifier calls without a sessions root
can validate the compact computation identity but cannot independently read
the persisted artifact, which is unchanged from the pre-Task-5 API.
