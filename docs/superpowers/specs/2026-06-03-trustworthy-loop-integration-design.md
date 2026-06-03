# Trustworthy Loop Integration Design

## Purpose

The previous trustworthy analysis workflow MVP added deterministic building blocks:

- dataset understanding contracts
- cleaning decision logs
- preview digests
- route proposals
- data-aware intent refinement
- deterministic claim verification
- verification-aware synthesis policy
- compact trust context in analysis state summaries

This phase connects those blocks to the real conversation loop so they affect normal user turns, not only unit tests or isolated helper calls.

The goal is to make the agent behave like a guided, evidence-bounded analysis system:

1. Understand what the loaded data supports.
2. Refine vague or unsupported user intent before tool planning.
3. Verify evidence-backed claims before final synthesis.
4. Let verification status shape the final answer policy.

## Scope

This phase covers loop integration only.

In scope:

- Apply `refine_intent_with_data(...)` after base intent classification in the real loop.
- Generate one verification report before final synthesis when the current turn has new evidence.
- Store verification report references in `AnalysisSessionState`.
- Ensure `derive_synthesis_policy(...)` sees the latest verification status.
- Add loop-level or near-loop regression tests for the integration paths.

Out of scope:

- Web UI route cards.
- Human-readable verification report pages.
- LLM-based verification.
- New analysis methods.
- Changing the semantics of `record_evidence_record`.
- Broad refactoring of `loop.py`.

## Design Choice

Use a small loop orchestration module rather than putting all integration logic directly into `loop.py`.

Create `src/data_agent/agent/trust_workflow_runtime.py` to own runtime glue:

- `refine_turn_intent_with_state(user_input, intent, state) -> TurnIntent`
- `maybe_verify_turn_claims(user_input, state, *, force=False) -> dict | None`
- small helpers for extracting claims, selecting evidence, and storing compact verification refs

`loop.py` remains responsible for turn sequencing. The new module is responsible for applying trust workflow rules to the current state.

This keeps the loop readable and gives the runtime glue its own focused tests.

## Runtime Flow

### 1. Intent Refinement

Current flow:

```text
_prepare_analysis_turn()
  -> plan_turn_intent(user_input, session_ctx)
  -> store intent on context
  -> controller.prepare_turn(...)
```

New flow:

```text
_prepare_analysis_turn()
  -> plan_turn_intent(user_input, session_ctx)
  -> load analysis state
  -> refine_turn_intent_with_state(user_input, intent, state)
  -> store refined intent on context
  -> controller.prepare_turn(...)
```

The runtime helper reads:

- `state.dataset_contracts`
- `state.route_proposals`

It calls:

- `refine_intent_with_data(user_input, intent, dataset_contracts, route_proposals)`

Expected behavior:

- Vague requests after data load gain an `analysis_route` ambiguity listing supported route options.
- Unsupported user-level retention requests become `clarification_needed` / `request_data`.
- Blocked data quality prevents directed analysis and asks for clarification first.

### 2. Verification Before Final Synthesis

Chosen trigger: once per turn, before final answer synthesis, when the turn has evidence.

Current synthesis hook:

```text
_maybe_inject_synthesis_policy(user_input)
  -> reads state.evidence_records
  -> derive_synthesis_policy(...)
  -> inject prompt instruction
```

New flow:

```text
_maybe_inject_synthesis_policy(user_input)
  -> maybe_verify_turn_claims(user_input, state)
  -> derive_synthesis_policy(...)
  -> inject prompt instruction
```

The verification helper should:

- Only run when `state.evidence_records` is non-empty.
- Run at most once per user turn.
- Prefer evidence from the current turn when available.
- Fall back to latest evidence records if turn-level evidence tracking is not available yet.
- Call `verify_analysis_claims(...)`.
- Save a compact verification ref through `state.add_verification_report_ref(...)`.

The full report may be stored as an artifact if an existing artifact helper is available and safe to use. If artifact storage is not introduced in this phase, the ref should still include enough compact fields:

- `id`
- `overall_status`
- `claim_count`
- `failed_count`
- `downgraded_count`

### 3. Claim Extraction

Verification needs claims. In this phase, keep extraction deterministic and conservative.

Primary source:

- `EvidenceRecord.claim` from `state.evidence_records`

No free-form final-answer claim extraction is required in this phase.

Rationale:

- Evidence records are already the intended unit of analysis support.
- Extracting claims from final text would require language parsing and risks false positives.
- The synthesis policy only needs to know whether recorded evidence has verification issues before the final answer.

### 4. Turn-Level Deduplication

The loop should not generate multiple reports for the same evidence set in one turn.

Recommended mechanism:

- Add a private loop flag such as `_turn_verification_injected`.
- Reset it in `_reset_turn_tracking()`.
- Set it after successful verification generation.

Additionally, runtime helper can compute a stable evidence signature to avoid repeated state refs if called twice with the same evidence IDs:

- evidence IDs joined in order
- route proposal IDs joined in order
- cleaning log IDs joined in order

If a verification report with the same signature already exists as the latest report, skip adding a duplicate.

### 5. Synthesis Policy

No production behavior change is needed inside `synthesis_policy.py`; this was completed in the previous phase.

This phase only ensures the latest verification report is present before `derive_synthesis_policy(...)` runs.

Expected outcome:

- `overall_status == "fail"` or `"pass_with_downgrades"` suppresses `decision_recommendation`.
- `limitation` is required.
- final wording is cautious.

## Error Handling

The trust workflow must not crash the conversation loop.

Rules:

- Intent refinement failure falls back to the original intent.
- Verification failure logs a warning and skips report generation for that turn.
- Existing final-answer behavior continues if trust integration fails.
- Failures should be visible in logs, not injected into the user response unless the loop already has a system-facing diagnostic mechanism.

## Testing Strategy

### Unit Tests

Add tests for `trust_workflow_runtime.py`:

- Refines vague intent using route proposals from state.
- Marks unsupported retention request as insufficient data.
- Skips refinement safely when state is missing or refs are malformed.
- Generates verification report from evidence records.
- Does not duplicate verification reports for the same evidence signature.
- Handles malformed state refs without crashing.

### Loop-Level Regression Tests

Add focused tests around `AgentLoop` or the closest existing loop harness:

- `_prepare_analysis_turn()` stores the refined intent when state contains route proposals.
- Unsupported retention request changes the prepared intent to request data.
- `_maybe_inject_synthesis_policy()` creates a verification report before deriving policy.
- A downgraded verification report affects the injected synthesis instruction.

### Existing Suites

Run at minimum:

- `tests/test_intent_refinement.py`
- `tests/test_verification_layer.py`
- `tests/test_synthesis_policy.py`
- `tests/test_analysis_state_v2.py`
- new runtime integration tests

## Success Criteria

This phase is complete when:

- Real loop intent preparation uses dataset contracts and route proposals.
- Real loop final synthesis has a verification report available when evidence exists.
- Verification status affects final synthesis policy in loop context.
- Regression tests prove the behavior without relying on external LLM calls.
- Existing trustworthy workflow MVP tests still pass.

## Risks And Mitigations

### Risk: Loop Integration Becomes Too Invasive

Mitigation:

- Keep trust glue in `trust_workflow_runtime.py`.
- Add only small calls from `loop.py`.

### Risk: Verification Generates Noisy Repeated Reports

Mitigation:

- One report per turn.
- Evidence signature deduplication.

### Risk: Verification Claims Are Too Narrow

Mitigation:

- Use evidence records as the claim source for this phase.
- Defer final-text claim extraction to a later phase.

### Risk: Missing Full Artifact Storage

Mitigation:

- Store compact verification refs first.
- Add full artifact rendering in the later UX/display phase.

## Later Follow-Up

After this phase, the next useful phase is user-visible trust UX:

- route recommendation cards in the Web UI
- cleaning decisions requiring confirmation
- verification downgrade explanations
- artifact reader tools for trust reports
