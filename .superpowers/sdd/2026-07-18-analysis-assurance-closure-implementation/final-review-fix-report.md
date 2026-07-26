# Final review fix report

Date: 2026-07-26
Branch: `codex/analysis-assurance-closure`
Reviewed range: `0dd56ff..2dfc336`
Implementation commit: `4124b8e` (`fix: close final assurance review gaps`)

## Outcome

All eight Important findings in `final-review.md` were verified against the
current branch and fixed. No finding was rejected. Finding 1's wording was
partly stale because the public cleaning response already exposed
`confirmation_id`, but its substantive defect was valid: the production
resume path resolved the receipt without applying the approved
transformation.

The fixes preserve the plan's authority boundaries:

- transformation approval remains receipt-bound and runtime-owned;
- `analysis_requirements.py` remains the single requirement compiler;
- evidence v2 and deterministic final-answer audit remain authoritative;
- full dataset identity remains in trusted state/artifacts while only
  prompt-facing synthesis/error projections are redacted;
- limitation and diagnostic framing is retained when unsupported claims are
  removed.

## Finding-by-finding disposition

### 1. Approved cleaning receipt was not applied by the production resume path

Verdict: valid, with one stale detail in the review wording.

Evidence before the fix:

- Cleaning responses already returned `confirmation_id`.
- `AgentLoop._resolve_runtime_confirmation` only resolved the receipt.
- `apply_confirmed_transformation` was reached only by direct helper calls in
  tests, not by the normal `resume_turn` application path.

RED:

```powershell
$env:PYTHONPATH='<worktree>\src'
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_data_clean_confirmation_receipt.py::test_agent_resume_applies_an_approved_transformation_before_continuing
```

Result: `1 failed`; the active dataset version was unchanged after approval.

Fix:

- On an approved `approve_dataset_transformation` resolution,
  `AgentLoop` invokes the private application helper with the runtime-owned
  receipt ID before continuing the turn.
- Prompt identity is invalidated after the dataset version changes.
- The receipt remains idempotent; the existing helper returns the already
  applied version on replay.

GREEN:

- Isolated regression: `1 passed`.
- Affected confirmation/cleaning suites: `43 passed`.

Changed files:

- `src/data_agent/agent/loop.py`
- `tests/test_data_clean_confirmation_receipt.py`

### 2. Result follow-ups and tool-round text could bypass the publish gate

Verdict: valid.

Evidence before the fix:

- `_is_final_answer_audit_candidate` covered only `directed_analysis` and
  `comprehensive_report`.
- Both streaming loops emitted assistant text from a tool-call round before
  the terminal audited response.

RED:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_final_answer_publish_gate.py::test_streaming_result_followup_hides_tool_call_claims_until_terminal_audit
```

Result: `1 failed`; the stream contained unaudited intermediate and follow-up
claims.

Fix:

- Added `result_followup` to final-answer audit candidates.
- For audit candidates, streaming text from tool-call rounds stays buffered
  and hidden; only the terminal audited text is published.
- Applied the same rule to normal and confirmation-resume streaming loops.

GREEN:

- Isolated regression: `1 passed`.
- Affected publish/comprehensive-flow suites: `108 passed, 3 skipped`.

Changed files:

- `src/data_agent/agent/loop.py`
- `tests/test_final_answer_publish_gate.py`

### 3. `not_estimable` seasonality did not block a positive seasonality claim

Verdict: valid.

Evidence before the fix:

- Seasonality-only wording was not classified as material.
- A diagnostic `not_estimable` record could satisfy the requirement.
- The verifier did not enforce `claim_guard="block_claim"` for a positive
  seasonality assertion.

RED:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_final_answer_claim_audit.py::test_not_estimable_seasonality_blocks_only_the_positive_seasonality_claim
```

Result: `1 failed`; the draft audit passed.

Fix:

- Added English and Chinese seasonality wording to material-claim extraction.
- Classified `not estimable`/`cannot be estimated` as diagnostic wording.
- Added a deterministic, same-step seasonality claim guard. It blocks a
  positive seasonality claim when the requirement says `block_claim`, while
  allowing the limitation/diagnostic statement itself.

GREEN:

- Isolated regression: `1 passed`.
- Affected claim-audit/time-series suites: `39 passed`.

Changed files:

- `src/data_agent/agent/answer_quality.py`
- `src/data_agent/agent/verification.py`
- `tests/test_final_answer_claim_audit.py`

### 4. Version-bound evidence failed open when current dataset identity was unavailable

Verdict: valid.

Evidence before the fix:

- Dataset-version comparison ran only when
  `current_dataset_versions is not None`.
- A missing current identity therefore bypassed all version checking.

RED:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_final_answer_claim_audit.py::test_missing_current_dataset_identity_blocks_only_version_bound_evidence
```

Result: `1 failed`; version-bound evidence passed with no current identity.

Fix:

- Evidence version IDs are always collected.
- Version-bound evidence fails closed with
  `current_dataset_identity_unavailable` when current identity cannot be
  established.
- Evidence with no dataset-version binding retains its previous behavior.

GREEN:

- Isolated regression: `1 passed`.
- Affected claim-audit/verification/trust suites: `59 passed`.

Changed files:

- `src/data_agent/agent/verification.py`
- `tests/test_final_answer_claim_audit.py`

### 5. Experiment design facts had split authority

Verdict: valid.

Evidence before the fix:

- The canonical compiler introduced experiment design requirements only after
  a design such as `randomized_experiment` was already declared.
- `question_need_detector.py` independently owned aliases and a second
  per-design requirement map.

RED:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_experiment_route_requirements.py::test_experiment_compiler_owns_core_user_design_facts_before_design_selection
```

Result: `1 failed`; all six core user design facts were absent.

Fix:

- Registered canonical `design_type` and `assignment_rule` requirements.
- The compiler now owns core user-definitional design facts and labels them
  with `parameters.input_source="user_or_plan"`.
- The question detector compiles requirements and asks from that canonical
  output; its duplicate aliases and design map were removed.
- The trigger is scoped to actual experiment-design intent: causal claims,
  an explicitly declared design, or planning/detectability. A generic
  inferential two-group `ab_test` remains a statistical comparison and is not
  forced to claim randomized assignment.

GREEN:

- Isolated compiler regression: `1 passed`.
- Affected experiment/question/compiler suites: `55 passed`.

The first combined focused run then exposed a useful compatibility regression:

- RED: `test_native_ab_test_satisfies_full_comparison_contract` failed because
  the initial trigger treated every `analysis.experiment` capability as a
  randomized design.
- Fix: narrowed the canonical trigger to experiment-design intent.
- GREEN: the existing `ab_test` contract test and the new early-design test
  both passed (`2 passed`).
- Fresh focused matrix subsequently passed in full (`281 passed`).

Changed files:

- `src/data_agent/agent/analysis_requirements.py`
- `src/data_agent/agent/question_need_detector.py`
- `tests/test_experiment_route_requirements.py`

### 6. Safe fallback removed passed limitation framing

Verdict: valid.

Evidence before the fix:

- `_safe_final_answer_fallback` explicitly excluded every passed claim whose
  strength was `diagnostic`.
- Unsupported claims could therefore be removed while their necessary
  limitation framing was removed as well.

RED:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_final_answer_publish_gate.py::test_safe_fallback_keeps_passed_limitation_framing_with_supported_claims
```

Result: `1 failed`; the passed limitation was absent from the fallback.

Fix:

- Preserve every passed claim, including diagnostic/limitation statements, in
  its original order.
- Failed claims remain excluded.

GREEN:

- Isolated regression: `1 passed`.
- Full publish-gate suite: `13 passed`.

Changed files:

- `src/data_agent/agent/loop.py`
- `tests/test_final_answer_publish_gate.py`

### 7. Trust capsule leaked dataset names into synthesis/error prompts

Verdict: valid.

Evidence before the fix:

- Scoped workspace context omitted dataset names and schema, but the trust
  capsule reintroduced the active logical dataset name into the same prompt.
- Controller reproduction failed because `secret_dataset` appeared inside
  `<trust_capsule>`.

RED:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_scoped_workspace.py::test_synthesis_system_prompt_omits_dataset_names_and_schema
```

Result: `1 failed`; the prompt contained `secret_dataset`.

Fix:

- Kept the full capsule unchanged in trusted turn state, durable artifact
  references, and compaction.
- Added a prompt-only projection for synthesis/error scopes that removes
  logical dataset-name keys while retaining opaque dataset version IDs,
  source fingerprints, and the full capsule digest.
- Applied the same projection to overflow-hydrated prompt context.

GREEN:

- Isolated controller regression: `1 passed`.
- Synthesis/error/hydration checks: `3 passed`.

Changed files:

- `src/data_agent/agent/loop.py`
- `tests/test_scoped_workspace.py`

### 8. Explicit significance wording with unknown support lacked a limitation

Verdict: valid.

Evidence before the fix:

- Removing the universal significance warning was correct for descriptive
  claims generally.
- It also removed protection for a claim that explicitly said `显著` while
  recording `significance="unknown"`.

RED:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_analysis_flow_tools.py::TestRecordEvidenceRecord::test_explicit_significance_claim_requires_known_statistical_support
```

Result: `1 failed`; no claim-specific confidence downgrade was returned.

Fix:

- Detect explicit English/Chinese significance assertions in claim identity
  fields.
- Treat missing, unknown, unassessed, or unreported significance support as
  unavailable.
- Only for that claim-specific combination, add a statistical limitation and
  downgrade unsupported high confidence. This does not restore the removed
  universal significance rule.

GREEN:

- Isolated public-tool regression: `1 passed`.
- Ignored real-data controller test from the main checkout:
  `1 passed, 1 warning`.
- The warning was only a pytest-cache permission warning in the read-only main
  checkout.

Changed files:

- `src/data_agent/tools/analysis_flow.py`
- `tests/test_analysis_flow_tools.py`

## Final verification

All commands used the required interpreter:
`D:\Project\Daily\data-agent\.venv\Scripts\python.exe`, with `PYTHONPATH`
pointing to this worktree's `src`.

### Exact plan-focused matrix

Files:

- `tests/test_data_clean_confirmation_receipt.py`
- `tests/test_clean_data_copy_on_write.py`
- `tests/test_confirmation_models.py`
- `tests/test_confirmation_service.py`
- `tests/test_confirmation_runtime.py`
- `tests/test_analysis_requirements.py`
- `tests/test_statistical_route_requirements.py`
- `tests/test_time_series_route_requirements.py`
- `tests/test_experiment_route_requirements.py`
- `tests/test_causal_claim_guard.py`
- `tests/test_computation_evidence_binding.py`
- `tests/test_final_answer_claim_audit.py`
- `tests/test_final_answer_publish_gate.py`
- `tests/test_analysis_context_budget.py`

Final result: `281 passed in 9.73s`.

### Exact broad regression matrix

Files:

- `tests/test_analysis_plan_consolidation.py`
- `tests/test_analysis_state_v2.py`
- `tests/test_analysis_flow_tools.py`
- `tests/test_load_to_route_requirements.py`
- `tests/test_route_capabilities.py`
- `tests/test_analysis_entry.py`
- `tests/test_question_need_detector.py`
- `tests/test_method_playbooks.py`
- `tests/test_execution_control.py`
- `tests/test_verification_layer.py`
- `tests/test_trust_workflow_runtime.py`
- `tests/test_synthesis_policy.py`
- `tests/test_comprehensive_analysis_flow.py`
- `tests/test_analysis_quality.py`
- `tests/real_data/test_golden_answer_quality.py`
- `tests/real_data/test_context_budget_degradation.py`

Final result: `403 passed, 12 skipped in 113.47s`.

### Custom comprehensive tool runner

Command:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' tests/test_tools_comprehensive.py
```

Result: `108 PASS, 0 FAIL, 2 SKIP` (`110 total`).

### Additional checks

- Finding 7 synthesis/error/hydration checks: `3 passed`.
- Finding 8 ignored real-data controller: `1 passed, 1 warning`.
- `python -m compileall -q src/data_agent`: PASS.
- `git diff --check`: PASS.
- Cached diff check before the implementation commit: PASS.

## Warnings, skips, and remaining concerns

- The custom runner emitted a non-fatal joblib warning because Windows
  physical-core discovery was unavailable; joblib used logical core count.
- The ignored real-data controller run from the main checkout emitted a
  non-fatal pytest-cache permission warning.
- The broad matrix's 12 skips are the repository's environment/data-gated
  cases, not failures introduced by this change.
- The full repository suite was not rerun here. The controller's prior full
  run reported sixteen failures tied to unavailable ignored real-data files;
  those unavailable fixtures were not treated as code regressions.
- No live external model/provider end-to-end run was performed. Deterministic
  loop, public-tool, controller, focused, broad, compile, and custom-runner
  paths were exercised locally.

## Commit record

- `4124b8e` — `fix: close final assurance review gaps`
- This report is committed separately in the commit that contains this file.
