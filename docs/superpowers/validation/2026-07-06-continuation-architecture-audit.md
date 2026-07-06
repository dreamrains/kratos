# Continuation Architecture Audit

Date: 2026-07-06

## Baseline Commands

- branch: `codex/stage3c0b-implementation`
- head: `39a80cc`
- status: `?? docs/superpowers/plans/2026-07-06-stage3c0b-realigned-continuation-plan.md`
- environment note: `git status` also prints `unable to access 'C:\Users\duguy/.config/git/ignore': Permission denied`; this matches prior design-delta notes about environment warnings and is not product evidence.
- safety baseline:

```text
412 passed in 34.11s
```

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_data_understanding_bundle.py `
  tests/test_relationship_validation.py `
  tests/test_stage3c0b_plan_contracts.py `
  tests/test_stage3c0b_workflow_projection.py `
  tests/test_stage3c0b_evidence_contracts.py `
  tests/test_stage3c0b_verification_compatibility.py `
  tests/test_stage3c0b_execution_scope.py `
  tests/test_scoped_workspace.py
```

## Reuse Anchors

- DataUnderstandingBundle: `src/data_agent/agent/data_understanding.py` defines `DATA_UNDERSTANDING_VERSION = "data_understanding.v1"` and `build_data_understanding_bundle()`. Existing tests cover contract versioning, identity, persistence, and active-scope references.
- relationship validation: `src/data_agent/agent/relationship_validation.py` provides deterministic relationship outcomes, stable relationship ids, cardinality, row coverage, distinct-key coverage, null-rate risk, and many-to-many rejection behavior.
- route capabilities: `src/data_agent/agent/route_capabilities.py` builds route cards from existing `route_proposals`; this remains the recommendation surface instead of adding `AnalysisOpportunity`.
- multi-file scope: `src/data_agent/agent/multi_file_scope.py` builds file eligibility, ambiguity, and assignment plans; this remains the scope-selection substrate instead of eager joins.
- plan contract and workflow projection: `src/data_agent/agent/analysis_plan_contracts.py` keeps `SUPPORTED_STAGE3C0B_MODES = {"independent", "synthesis"}`, and `src/data_agent/agent/workflow_projection.py` projects accepted plan steps into tasks.
- execution scope: `src/data_agent/agent/execution_scope.py` blocks synthesis raw-data reads with `synthesis_cannot_read_raw_dataset` and enforces task dataset bindings.
- evidence and verification: `src/data_agent/agent/evidence_contracts.py`, `src/data_agent/agent/evidence_compatibility.py`, and `src/data_agent/agent/verification.py` remain the trust substrate for claim support and measurement compatibility.
- synthesis policy: `src/data_agent/agent/synthesis_policy.py` derives runtime synthesis policy and injects synthesis instructions; bounded replenishment should extend this path instead of adding a second synthesis controller.
- Workbench/trust view: `src/data_agent/agent/trust_view.py` builds the current Trust/Workbench API. Phase 1 should replace the user-facing primary view, but reuse the current state projection where it still serves evidence quality and debugging.

## Duplicate Concepts

| Concept | Current Status | Decision |
|---|---|---|
| `dataset_bundles` | Legacy active file-bundle diagnostics and display grouping in `AnalysisSessionState` and trust view | Keep only for file grouping/display; do not use as the canonical data-understanding contract |
| `data_understanding_bundles` | Canonical `DataUnderstandingBundle` refs with active-scope tracking | Use for load-time user data brief and Workbench data-understanding section |
| `file_relationships` | Existing relationship diagnostics and candidate-key hints | Keep as relationship evidence/risk input; do not treat as proof that a join should execute |
| `route_proposals` | Existing route-card input consumed by route capabilities, prompt context, and Trust/Workbench projections | Keep as the recommendation substrate |
| `SUPPORTED_STAGE3C0B_MODES` | Current source allows only `independent` and `synthesis` | Preserve; do not add `joint` or `aggregate_then_join` in this stage |
| `AnalysisOpportunity` | Appears in old expansion specs/plans; no current source implementation | Do not implement; reuse route capabilities and multi-file scope |
| `StrategyRecord` | Appears in old expansion specs/plans; no current source implementation | Do not implement; keep LLM-led planning through existing plan contracts |
| `DataOperationRecord` | Future operation concept in Stage 3C/3C1A docs; no current source implementation | Defer to Phase 5 only if real scenarios justify executable operations |
| `DerivedDataset` | Future/old plan concept tied to join or aggregate operations; no current Stage 3C0B execution path | Defer; do not create derived outputs in Stage 3C0B |
| `aggregate_then_join` | Present only in old specs/plans and forbidden-mode checks | Keep out of Stage 3C0B execution |

## Quality Risks

- risk: preserving the old Trust Inspector as a coequal primary view would make the new Workbench noisy and user-hostile.
- mitigation: Phase 1 now requires Workbench primary-view replacement and replacement tests, not parity tests.
- risk: synthesis cannot read raw datasets, but a missing evidence path would push the LLM toward weak or overconfident conclusions.
- mitigation: Task 4 adds bounded evidence replenishment instructions plus a deterministic substrate integration test.
- risk: eager multifile joins could reduce analysis quality by joining data before grain, key quality, coverage, and business meaning are understood.
- mitigation: Stage 3C0B remains data-scope-first and evidence-synthesis-first; executable data operations are a later opt-in phase.
- risk: new hard scoring or `question_id` gates could suppress useful exploratory findings.
- mitigation: quality gates remain evidence/verification oriented and report unsupported claims without replacing professional judgment with a magic threshold.

## Compatibility Decisions

- old execution compatibility: do not preserve unreasonable legacy execution paths. New Stage 3C0B execution remains plan-contract-based and limited to `independent` and `synthesis`.
- old display-only behavior: legacy state may be used as technical drill-down only when it improves trust, verification, or debugging. It should not appear as the primary Workbench experience.
- old test behavior: old parity tests should be replaced by stricter replacement tests when they only protect old/new coexistence.
- old operation concepts: `AnalysisOpportunity`, `StrategyRecord`, `DataOperationRecord`, `DerivedDataset`, `joint`, and `aggregate_then_join` remain design history or future-phase concepts, not current implementation targets.
