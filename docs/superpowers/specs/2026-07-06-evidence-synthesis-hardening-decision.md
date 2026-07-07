# Evidence And Synthesis Hardening Decision

## Decision

No new hardening implementation is needed in the current continuation slice.

Keep the Phase 4 path as **monitor and tune with scenario evidence**:

- keep `analysis_quality_rubric.score_analysis_quality()` as a regression helper, not runtime synthesis policy;
- keep bounded evidence replenishment as prompt guidance plus deterministic substrate tests;
- do not add a new claim extraction phase, independent audit phase, or publish-time hard score gate yet;
- use future golden-question failures to justify either prompt-only tuning or a targeted verification improvement.

This decision avoids adding a second synthesis/audit pipeline before there is evidence that the current evidence, verification, and synthesis layers are failing real scenarios.

## Evidence Reviewed

### Quality Rubric

`docs/superpowers/validation/2026-07-06-analysis-quality-rubric.md` defines two fatal defects:

- material claims without supporting evidence;
- claims that rely on rejected, unconfirmed, or time-incompatible relationships.

It deliberately avoids a total score, because broad or polished analysis should not compensate for unsupported material claims.

### Current Scenario Runner Result

Generated during this decision pass as a transient local validation result:

```text
artifacts/multifile-quality/20260707T053525.933928Z/results.json
```

Summary:

- schema: `multifile_quality_results.v1`;
- forbidden modes: `joint`, `aggregate_then_join`;
- `global_publish_gate`: `null`, because the runner verifies scenario readiness rather than publishing claims;
- all four scenarios are `ready_for_execution`;
- no scenario executed a join;
- runner notes explicitly state that relationship diagnostics never authorize an executed join.

### Real-Data And Fault Tests

The current tests cover:

- unsupported material claim blocks delivery without a magic total score;
- rejected relationship diagnostics remain reportable when not used for a claim;
- rejected relationship use blocks delivery when it supports a claim;
- relationship time-scope mismatch blocks relationship-based claims;
- savings-card orders plus user-flow data produce high key coverage but many-to-many risk and no join authority;
- missing-key and many-to-many fault injection are rejected.

### Runtime Layers

Current implementation layers reviewed:

- `verification.verify_analysis_claims()` fails unsupported claims, downgrades incomplete evidence, downgrades causal language without causal evidence, checks comparison evidence compatibility, and respects current plan evidence scope;
- `trust_workflow_runtime.maybe_verify_turn_claims()` extracts claims from current-plan `EvidenceRecord`s and stores compact verification refs with failed/downgraded counts;
- `synthesis_policy.derive_synthesis_policy()` suppresses decision recommendations and requires limitations when latest verification is `fail` or `pass_with_downgrades`;
- `synthesis_policy.build_synthesis_instruction()` includes bounded evidence replenishment and preserves the synthesis raw-data boundary;
- `analysis_flow.record_analysis_plan()` validates executable `stage3c0b.v1` plans before workflow projection;
- `analysis_flow.record_evidence_record()` validates Stage 3C0B evidence, calibrates high confidence, and completes matching tasks from evidence.

## Failure Classification

| Failure | Existing layer catches it? | Needed change |
|---|---|---|
| Unsupported material claim | Yes for claims represented as EvidenceRecord-backed verification inputs and in quality rubric scenarios | No new hardening now. Keep bounded replenishment instruction and claim-level verification. Add runtime claim extraction only if final-answer claims repeatedly escape EvidenceRecord-backed verification. |
| Weak or incomplete evidence | Partly. Evidence validation, missing required evidence fields, confidence calibration, cleaning-risk downgrades, and quality-rubric blockers cover the modeled cases | No new hard gate. Add targeted verification checks only when a golden scenario shows a specific weak-evidence pattern that current checks miss. |
| Invalid relationship used for a claim | Yes in regression rubric and real-data/fault scenarios; relationship diagnostics alone do not block independent analysis | No runtime synthesis change now. Keep relationship evidence diagnostic-only unless explicitly used for a material claim. |
| Relationship time-scope mismatch | Yes in quality rubric scenarios | No change. Keep as claim-level blocker when relationship evidence supports the claim. |
| Shallow synthesis | Not deterministically measured yet | Do not add an audit phase now. First add golden-question expected-outcome tests if real outputs are shallow; then tune prompt/synthesis policy before considering a new checker. |
| Over-rigid synthesis | Guarded by current design choices: no total score, no `question_id` gate, no universal publish threshold, partial answers allowed | No change. Avoid introducing hard readiness gates that suppress useful exploratory analysis. |

## Rationale

The highest-risk mechanisms already have direct coverage:

- unsupported claims become failed checks or blocked quality results;
- weak evidence is downgraded rather than silently treated as strong;
- invalid relationships are useful as diagnostics but cannot justify claims;
- synthesis can request bounded independent evidence without reading raw datasets directly.

The remaining concern is not a missing deterministic guardrail; it is whether real final answers are deep enough, broad enough, and professionally useful. That is a golden-question and output-quality problem. Adding claim extraction or an independent audit phase before observing those failures would add complexity and a second judgment surface without proving better analysis quality.

## Follow-Up Trigger

Write a separate implementation plan before code changes if any future real-data or golden-question run shows one of these repeated failures:

- final answer introduces a material claim that is not represented by an `EvidenceRecord`;
- synthesis ignores a failed or downgraded verification report;
- relationship diagnostics are phrased as if they authorize a join or causal/business-impact claim;
- bounded evidence replenishment fails to isolate unsupported claims and instead blocks the whole answer;
- answers are repeatedly shallow despite adequate evidence and route context.

Preferred escalation order:

1. Add or tighten a golden scenario.
2. Apply prompt-only or synthesis-policy wording changes.
3. Add a targeted verification rule.
4. Consider claim extraction/readiness helper.
5. Consider an independent audit phase only if the previous layers cannot catch the failure without harming useful exploratory analysis.
