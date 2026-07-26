# Analysis Assurance Migration Closure Validation

**Date:** 2026-07-26
**Baseline:** `8fe6851` (`feat: preserve analysis assurance under context limits`)
**Reviewed implementation baseline:** `2dfc336` (`fix: reproduce assurance migration audit`)
**Final assurance follow-up baseline:** `88010b7` (`fix: close final assurance review follow-ups`)
**Scope:** Task 9 migration, compatibility-boundary closure, and final whole-branch assurance review.

## Outcome

The production audit found no second writable confirmation store, requirement compiler, evidence store, final-answer verifier, or context compressor. It did find stale public descriptions for the legacy `confirmed` Boolean in `data_clean.py`: implementation already rejected the Boolean, but the registered tool descriptions still implied that it authorized promotion. Those descriptions now state the receipt-bound behavior, and a focused regression test protects the public schema.

The final whole-branch review found eight additional end-to-end gaps. They are
closed without introducing parallel authorities: approved cleaning receipts
now apply through the production resume path; result follow-ups and tool-round
text remain behind the publish gate; seasonality insufficiency blocks positive
claims while English and Chinese not-estimable diagnostics remain publishable;
version-bound evidence fails closed when current dataset identity is
unavailable; experiment design questions use the canonical requirement
compiler; safe fallback retains passed limitation framing; synthesis/error
prompts redact logical dataset names while retaining opaque identity; and
explicit significance claims receive claim-specific protection when
statistical support is unknown or clearly unassessed.

## Production Authority Audit

| Concern | Canonical owner and result |
| --- | --- |
| Material changes | `data_clean.apply_confirmed_transformation` resolves a `ConfirmationService` receipt and verifies its proposal, dataset version, and fingerprints. `clean_data` and `apply_type_conversion` set `approved` only from private `_approved_confirmation_id`; a public `confirmed=True` returns `confirmation_receipt_required` and cannot promote. |
| Requirements | `analysis_requirements.compile_analysis_requirements` produces `analysis_requirement.v1`; `analysis_plan_contracts.normalize_analysis_plan_contract` calls that compiler. No second compiler was found. |
| Evidence | `evidence_contracts.bind_evidence_to_computations` server-binds new assurance records as `evidence_record.v2`, including computation references and requirement IDs. `analysis_flow.record_evidence_record` routes contract-bearing/plan evidence through that binder. |
| Final claims | `verification.verify_analysis_claims` remains the claim verifier. `answer_quality.build_final_answer_audit`, invoked by `trust_workflow_runtime.audit_final_answer_draft`, provides the pre-publication final-draft audit. The optional LLM critique is an input to that deterministic audit, not an override. |
| Context | `compact.compact_history` remains the sole conversation-context compressor; loop, REPL, and web command surfaces call it rather than reimplementing compaction. |

The audit used targeted source searches for Boolean authorization, contract versions, compiler/verifier definitions, and `compact_history` call sites. No direct `confirmed=True` authorization remained. The stale user/tool wording was corrected without changing the established receipt authority.

### Reproducible Production Searches

Run these commands from the repository root. They are production-code audits, not tests.

```powershell
rg -n -i --glob '*.py' "confirmed\s*[=:]\s*(True|true)|_approved_confirmation_id|confirmation_receipt_required" src/data_agent/tools/data_clean.py
```

Result: the promotion paths use `_approved_confirmation_id` at the two `approved = bool(...)` decisions; public Boolean handling returns `confirmation_receipt_required`. The only literal `confirmed=true` is the corrected user-facing statement that it is deprecated and cannot authorize promotion.

```powershell
rg -n -i --glob '*.py' "def +compile.*requirement|analysis_requirement\.v1" src/data_agent/agent src/data_agent/tools
```

Result: `analysis_requirements.py` contains the single `compile_analysis_requirements` definition and the `analysis_requirement.v1` contract constant. No second compiler definition was returned.

```powershell
rg -n --glob '*.py' "EVIDENCE_RECORD_CONTRACT_VERSION|evidence_record\.v2|bind_evidence_to_computations" src/data_agent/agent src/data_agent/tools/analysis_flow.py
```

Result: `evidence_contracts.py` owns `EVIDENCE_RECORD_CONTRACT_VERSION` and `bind_evidence_to_computations`, which writes the v2 contract. `analysis_flow.py` imports and calls that binder for contract-bearing/plan evidence. `analysis_state.py` only recognizes non-v2 persisted evidence as `legacy_unbound` while loading state.

```powershell
rg -n --glob '*.py' "def verify_analysis_claims|def audit_final_answer_draft|build_final_answer_audit\(" src/data_agent/agent
```

Result: the only claim-verification entry point is `verification.verify_analysis_claims`; final-answer auditing is built by `answer_quality.build_final_answer_audit` and invoked from `trust_workflow_runtime.audit_final_answer_draft`. The second `build_final_answer_audit` occurrence is the builder's internal use, not a second verifier.

```powershell
rg -n --glob '*.py' "compact_history\(" src/data_agent
```

Result: `compact.compact_history` is the sole implementation. Loop, REPL, and web command handlers call it; no additional context-compressor definition was returned.

## Compatibility Boundaries and Removal Conditions

- `analysis_plan_contracts` accepts `stage3c0b.v1`, `analysis_spec_id`, and legacy plan fields only while normalizing a loaded payload. `analysis_state.from_dict` is the persisted-state boundary. Remove these readers when supported persisted sessions contain no legacy plan version/field and no supported extension imports the legacy aliases.
- `analysis_state.from_dict` may load legacy evidence but marks it `legacy_unbound`; it cannot acquire v2 provenance through that read path. The `validate_stage3c0b_*` names are read-only aliases to canonical validators. Remove them when supported persisted sessions contain no legacy evidence and downstream callers have migrated their imports.
- `clean_data` and `apply_type_conversion` retain the public `confirmed` argument only to reject existing client or queued requests safely. It is never a writable approval path. Remove it after no supported client or persisted queued tool request can emit the field.

## User-Visible Guarantees

- Raw uploads and raw snapshots remain immutable; transformations operate on versioned analysis copies.
- A material cleaning or conversion promotion requires a resolved receipt bound to the exact dataset version and transformation proposal.
- Statistical, time-series, experiment, and causal claims have method-specific requirements and explicit insufficiency outcomes rather than a universal significance shortcut.
- Material final claims are audited against current evidence and requirements before publication; a deterministic blocker cannot be overridden by an optional judge.
- Under context pressure, the bounded trust capsule preserves critical identities. The agent may narrow an answer but cannot strengthen an unsupported claim.

## Final Whole-Branch Assurance Review Closure

The final review verified and closed these durable behavior gaps:

1. `AgentLoop.resume_turn` applies an approved dataset-transformation receipt
   before analysis continues. The receipt ID remains runtime-owned and
   idempotent.
2. `result_followup` is a final-answer audit candidate. Assistant text from
   tool-call rounds is not streamed before the terminal audit.
3. A `seasonality_estimability` requirement with
   `claim_guard="block_claim"` blocks a positive seasonality assertion.
   Not-estimable disclosures remain diagnostic, including `不可估计` and
   `无法估计`.
4. Version-bound evidence fails closed with
   `current_dataset_identity_unavailable` when the active dataset identity
   cannot be established. Non-versioned evidence keeps its compatibility
   behavior.
5. Core experiment and causal design facts are compiled by
   `analysis_requirements.py`; the question detector consumes those canonical
   requirements instead of maintaining a second design map. Generic
   inferential `ab_test` comparisons are not mislabeled as randomized designs.
6. The supported fallback retains passed limitation and diagnostic framing
   while excluding failed claims.
7. Full trust-capsule identity stays in trusted state and artifacts.
   Synthesis/error prompt projections omit logical dataset names and schema
   while retaining dataset version IDs, fingerprints, and the capsule digest.
8. Statistical limitations and high-confidence calibration are generated only
   when a claim explicitly asserts significance and its support is missing,
   unknown, unassessed, not applicable, or otherwise clearly unreported. This
   does not restore a universal significance requirement for descriptive
   claims.

## Verification

The worktree has no local virtual environment, so commands used the repository virtual environment with `PYTHONPATH=src` to ensure imports resolved to this worktree rather than the editable parent checkout.

### Real-data fixture closure

The ignored source fixtures under
`D:\Project\Daily\data-agent\reference\test_doc` were copied into the isolated
worktree's ignored `reference/test_doc` directory. Only the nine canonical
source workbooks are present; no ignored compatibility aliases are required.

Tracked tests now resolve `reference/test_doc` relative to their checkout and
use the current canonical workbook names. In particular, the former
`省钱卡用户最近流水_20260511.xlsx` references use
`省钱卡0201到0510购卡用户付费数据.xlsx`, while former
`省钱卡订单_20260507.xlsx` references use `省钱卡订单.xlsx` and its actual
`售价` field. The three former backup-directory names use their current
`省钱卡`-prefixed workbooks. Availability gates check the required files, not
only whether the directory exists.

The workspace-restore fixture also owns an isolated temporary task-manager
directory and reads restored data inside the restored loop's context, matching
the context-scoped workspace contract.

After deleting the five initially created compatibility aliases, the focused
RED run was **15 failed, 101 passed**. After migrating the tracked tests to the
canonical fixture inventory, the same command was GREEN:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_mvp_real_data_fixtures.py `
  tests/test_optimization_comparison.py `
  tests/test_phase_comprehensive.py `
  -p no:cacheprovider
```

Result: **116 passed** with 24 pre-existing NumPy correlation warnings.

The remaining migrated real-data modules were also exercised directly:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_analysis_quality.py `
  tests/test_comprehensive_analysis_flow.py `
  tests/test_pipeline_comprehensive.py `
  tests/test_system_data_analysis_quality_audit.py `
  tests/test_real_data_integration.py `
  -p no:cacheprovider
```

Result: **225 passed** with 27 non-fatal numerical warnings.

### Full repository suite

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests -p no:cacheprovider
```

Result: **2466 passed, 11 skipped** in 356.65s. Pytest reported 35
non-fatal numerical warnings and no failures. This closes the earlier 16
fixture-related failures without relying on ignored compatibility aliases;
nine previously skipped real-data cases now execute and pass.

After the full run, the isolated canonical-fixture contract was rerun against
the nine-workbook inventory:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_mvp_real_data_fixtures.py -p no:cacheprovider
```

Result: **2 passed**.

### Follow-up RED/GREEN evidence

- Chinese seasonality diagnostics: RED was `2 failed`; both `年季节性不可估计`
  and `年季节性无法估计` were incorrectly blocked. After extending only the
  diagnostic classifier, GREEN was `2 passed`; the positive seasonality claim
  remained blocked by the deterministic guard.
- Unsupported significance states: RED was `2 failed, 1 passed`;
  `unassessed` and `not applicable` bypassed claim-specific protection while
  `unknown` already behaved correctly. After normalizing those two clearly
  unsupported states, GREEN was `3 passed`.

### Affected behavior

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_final_answer_claim_audit.py `
  tests/test_analysis_flow_tools.py `
  tests/test_time_series_route_requirements.py
```

Result: **69 passed** in 2.62s.

### Plan-focused matrix

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_data_clean_confirmation_receipt.py `
  tests/test_clean_data_copy_on_write.py `
  tests/test_confirmation_models.py `
  tests/test_confirmation_service.py `
  tests/test_confirmation_runtime.py `
  tests/test_analysis_requirements.py `
  tests/test_statistical_route_requirements.py `
  tests/test_time_series_route_requirements.py `
  tests/test_experiment_route_requirements.py `
  tests/test_causal_claim_guard.py `
  tests/test_computation_evidence_binding.py `
  tests/test_final_answer_claim_audit.py `
  tests/test_final_answer_publish_gate.py `
  tests/test_analysis_context_budget.py
```

Result: **282 passed** in 11.90s.

### Broad regression matrix

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_analysis_plan_consolidation.py `
  tests/test_analysis_state_v2.py `
  tests/test_analysis_flow_tools.py `
  tests/test_load_to_route_requirements.py `
  tests/test_route_capabilities.py `
  tests/test_analysis_entry.py `
  tests/test_question_need_detector.py `
  tests/test_method_playbooks.py `
  tests/test_execution_control.py `
  tests/test_verification_layer.py `
  tests/test_trust_workflow_runtime.py `
  tests/test_synthesis_policy.py `
  tests/test_comprehensive_analysis_flow.py `
  tests/test_analysis_quality.py `
  tests/real_data/test_golden_answer_quality.py `
  tests/real_data/test_context_budget_degradation.py
```

Result: **405 passed, 12 skipped** in 116.78s.

### Custom tool runner

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' tests/test_tools_comprehensive.py
```

Result: **108 PASS, 0 FAIL, 2 SKIP**.

### Static and repository checks

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m compileall -q src/data_agent
git diff --check
git status --short
```

Result: `compileall` and `git diff --check` exited 0. The final fixture-closure
status showed exactly the intended validation update and eight test-file
changes. `artifacts/`, `tmp/`, and the ignored fixture workbooks were not
staged.

## Environmental Notes and Untested Dependencies

- The custom runner emitted a non-fatal joblib warning because Windows
  physical-core discovery was unavailable; joblib used the logical-core count.
- Git emitted pre-existing environment warnings that
  `C:\Users\duguy\.config\git\ignore` is inaccessible, the worktree
  `.pytest_cache/` directory cannot be opened because of permission denial,
  and Git will normalize LF to CRLF on edited files. These warnings did not
  affect test or custom-runner exit status.
- The 12 broad-suite skips are environment/data-gated cases, not failures.
- The full-suite run completed with 11 pytest-marked skips and no failures.
  The copied fixture workbooks remain ignored test inputs and are not part of
  the Git commit.
- Live LLM-provider calls, browser/web GUI interaction, and external service availability were not exercised; the validation covers their deterministic local contracts and fixtures only.
