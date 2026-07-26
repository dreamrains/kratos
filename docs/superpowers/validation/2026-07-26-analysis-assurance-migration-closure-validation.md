# Analysis Assurance Migration Closure Validation

**Date:** 2026-07-26
**Baseline:** `8fe6851` (`feat: preserve analysis assurance under context limits`)
**Scope:** Task 9 migration and compatibility-boundary closure.

## Outcome

The production audit found no second writable confirmation store, requirement compiler, evidence store, final-answer verifier, or context compressor. It did find stale public descriptions for the legacy `confirmed` Boolean in `data_clean.py`: implementation already rejected the Boolean, but the registered tool descriptions still implied that it authorized promotion. Those descriptions now state the receipt-bound behavior, and a focused regression test protects the public schema.

## Production Authority Audit

| Concern | Canonical owner and result |
| --- | --- |
| Material changes | `data_clean.apply_confirmed_transformation` resolves a `ConfirmationService` receipt and verifies its proposal, dataset version, and fingerprints. `clean_data` and `apply_type_conversion` set `approved` only from private `_approved_confirmation_id`; a public `confirmed=True` returns `confirmation_receipt_required` and cannot promote. |
| Requirements | `analysis_requirements.compile_analysis_requirements` produces `analysis_requirement.v1`; `analysis_plan_contracts.normalize_analysis_plan_contract` calls that compiler. No second compiler was found. |
| Evidence | `evidence_contracts.bind_evidence_to_computations` server-binds new assurance records as `evidence_record.v2`, including computation references and requirement IDs. `analysis_flow.record_evidence_record` routes contract-bearing/plan evidence through that binder. |
| Final claims | `verification.verify_analysis_claims` remains the claim verifier. `answer_quality.build_final_answer_audit`, invoked by `trust_workflow_runtime.audit_final_answer_draft`, provides the pre-publication final-draft audit. The optional LLM critique is an input to that deterministic audit, not an override. |
| Context | `compact.compact_history` remains the sole conversation-context compressor; loop, REPL, and web command surfaces call it rather than reimplementing compaction. |

The audit used targeted source searches for Boolean authorization, contract versions, compiler/verifier definitions, and `compact_history` call sites. No direct `confirmed=True` authorization remained. The stale user/tool wording was corrected without changing the established receipt authority.

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

## Verification

The worktree has no local virtual environment, so commands used the repository virtual environment with `PYTHONPATH=src` to ensure imports resolved to this worktree rather than the editable parent checkout.

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

Result: **274 passed** in 13.69s.

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
  tests/test_analysis_quality.py
```

Result: **376 passed, 11 skipped** in 116.46s.

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/real_data/test_golden_answer_quality.py `
  tests/real_data/test_context_budget_degradation.py
```

Result: **26 passed, 1 skipped** in 3.84s.

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m compileall -q src/data_agent
git diff --check
git status --short
```

Result: `compileall` and `git diff --check` exited 0. Before this report was added, `git status --short` showed only the intended documentation, `data_clean.py`, and focused-test changes. `artifacts/` and `tmp/` were neither modified nor staged.

## Environmental Notes and Untested Dependencies

- A combined broad command exceeded the 120-second command limit at 86% without reporting a failure. Its core and real-data portions were then rerun separately to successful completion above.
- Git emitted pre-existing environment warnings that `C:\Users\duguy\.config\git\ignore` is inaccessible and that Git will normalize LF to CRLF on the edited files. Neither warning affected test or diff-check exit status.
- Live LLM-provider calls, browser/web GUI interaction, and external service availability were not exercised; the validation covers their deterministic local contracts and fixtures only.
