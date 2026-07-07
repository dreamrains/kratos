# Data Agent Continuation Validation Report

## Summary

The continuation roadmap improved the trustworthy-analysis loop without adding
new heavy execution contracts.

Validated outcomes:

- Stage 3C0B remains limited to `independent` and `synthesis` execution modes.
- Load-time data understanding is exposed through a compact User Data Brief.
- Workbench is the single primary trust surface with four user-value sections.
- Synthesis remains evidence-centered and can request bounded independent
  replenishment without reading raw datasets directly.
- Real-data regression scenarios protect against false joins, invalid
  relationship use, unsupported material claims, and time/grain mismatch.
- Stage 3C1A data operations are explicitly deferred until real scenarios show
  independent evidence plus synthesis is insufficient.

## Final Suite

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
  tests/test_scoped_workspace.py `
  tests/test_stage3c0b_load_data_brief.py `
  tests/test_multifile_workbench_view.py `
  tests/test_stage3c0b_evidence_replenishment.py `
  tests/test_stage3c0b_evidence_replenishment_flow.py `
  tests/real_data/test_multifile_real_data_scenarios.py `
  tests/real_data/test_multifile_analysis_quality.py `
  tests/test_analysis_quality.py `
  tests/test_system_data_analysis_quality_audit.py `
  tests/test_trust_view.py `
  tests/test_trust_inspector_api.py `
  tests/test_trust_inspector_ui.py `
  tests/test_web_workbench_replacement.py `
  tests/test_synthesis_policy.py `
  tests/test_execution_control.py
```

Output:

```text
518 passed, 12 skipped, 16 warnings in 56.06s
```

Warnings were NumPy correlation divide warnings in existing analysis-quality
tests. They did not fail the suite.

Additional full-suite evidence from the same continuation pass:

```text
2121 passed, 21 skipped, 28 warnings in 481.37s
```

## Real-Data Scenario Script

Command:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/run_multifile_quality_scenarios.py --data-dir 'D:\Project\Daily\data-agent\reference\test_doc'
```

Output:

```text
D:\Project\Daily\data-agent\.worktrees\stage3c0b-implementation\artifacts\multifile-quality\20260707T054016.330931Z\results.json
```

Result summary:

- schema: `multifile_quality_results.v1`;
- forbidden modes: `joint`, `aggregate_then_join`;
- `global_publish_gate`: `null`, because the runner validates scenario
  readiness and does not publish claims;
- all scenarios were `ready_for_execution`;
- all scenarios had `executed_join=false`;
- runner note: relationship diagnostics never authorize an executed join.

Real-data files covered:

```text
娓告垙Abanner姹囨€绘暟鎹?xlsx
娓告垙A鍐呰喘鏁版嵁.xlsx
娓告垙A婵€鍔辫棰戞眹鎬绘暟鎹姤琛?xlsx
娓告垙B鐣欏瓨.xlsx
鐪侀挶鍗＄敤鎴锋渶杩戞祦姘確20260511.xlsx
鐪侀挶鍗¤鍗昣20260507.xlsx
```

The generated artifact was used as validation evidence only and is not part of
the committed source change.

## Frontend And Whitespace Checks

Command:

```powershell
node -c src\data_agent\web\static\js\app.js
```

Output:

```text
<no output; exit 0>
```

Command:

```powershell
git diff --check
```

Output:

```text
<no output; exit 0>
```

During intermediate checks, Git printed Windows LF/CRLF normalization warnings
for modified files. Those warnings were not whitespace errors.

## Non-Slippage Checks

Planned command:

```powershell
rg -n "AnalysisOpportunity|StrategyRecord|DataOperationRecord|safe_to_execute|join preflight|operation_id|aggregate_then_join|DerivedDataset" src tests
```

Output:

```text
tests\real_data\scenario_manifest.json:5:    "aggregate_then_join"
tests\real_data\test_multifile_real_data_scenarios.py:47:    assert manifest["forbidden_modes"] == ["joint", "aggregate_then_join"]
```

Interpretation:

- These are allowed negative assertions proving forbidden modes remain
  forbidden.
- The original check is too broad because it treats tests that guard against
  slippage as slippage.

Corrected executable-code check:

```powershell
rg -n "AnalysisOpportunity|StrategyRecord|DataOperationRecord|safe_to_execute|join preflight|operation_id|aggregate_then_join|DerivedDataset" src
```

Output:

```text
<no output; exit 1>
```

Corrected tests-minus-negative-assertions check:

```powershell
rg -n "AnalysisOpportunity|StrategyRecord|DataOperationRecord|safe_to_execute|join preflight|operation_id|aggregate_then_join|DerivedDataset" tests -g "!**/scenario_manifest.json" -g "!**/test_multifile_real_data_scenarios.py"
```

Output:

```text
<no output; exit 1>
```

Plan-mode leak check:

```powershell
rg -n "SUPPORTED_STAGE3C0B_MODES\s*=\s*\{[^}]*joint|SUPPORTED_STAGE3C0B_MODES\s*=\s*\{[^}]*aggregate_then_join" src tests
```

Output:

```text
<no output; exit 1>
```

Conclusion: no executable Stage 3C0B code admits `joint`,
`aggregate_then_join`, `DataOperationRecord`, or `DerivedDataset`.

## Quality Rubric Results

The regression rubric protects hard analytical integrity without replacing
professional judgment with a total score:

- unsupported material claim -> `claim_delivery_ready=false`;
- invalid relationship used for a claim -> `claim_delivery_ready=false`;
- relationship time-scope mismatch used for a claim -> `global_publish_gate=false`;
- diagnostic-only rejected relationship -> reportable without blocking
  independent analysis;
- soft warnings remain visible but do not decide readiness.

This preserves both rigor and analytical breadth.

## Workbench UX Evidence

Workbench is now the single primary trust surface:

- API contract is bounded to `status`, `session_id`, `updated_at`, and
  `workbench`;
- `workbench.multifile_analysis` contains four primary sections:
  `data_understanding`, `relationships`, `analysis_directions`,
  `answer_coverage`;
- `workbench.details` carries scope, confirmation, verification, relationship
  evidence, and uncertainty details;
- raw artifact paths, task references, evidence signatures, legacy route
  history, active bundles, and duplicate risk projections are not exposed as
  primary UI text;
- route suggestions remain display-only and do not auto-submit chat requests.

Known UX caveats:

- dense side Workbench remains desktop-oriented and hidden under the existing
  `xl` breakpoint;
- the pre-existing 390px shell overflow needs a separate mobile interaction
  design;
- Tailwind CDN still emits the existing production warning during browser QA.

## Unsupported Claims And Invalid Relationships

Current protection path:

- `record_evidence_record()` validates Stage 3C0B evidence and calibrates
  high confidence when evidence quality is weak;
- `verify_analysis_claims()` fails unsupported claims, downgrades incomplete
  evidence, downgrades causal language without causal methods, checks current
  plan evidence scope, and checks comparison compatibility;
- `derive_synthesis_policy()` suppresses decision recommendations when latest
  verification is `fail` or `pass_with_downgrades`;
- bounded replenishment lets synthesis request one independent evidence task
  when a material claim lacks support;
- quality rubric blocks invalid relationship use only when the relationship is
  used to support a material claim.

This keeps unsupported conclusions from being delivered as strong findings
without suppressing useful diagnostics or partial answers.

## Cleanup And Compatibility Decisions

Clean breaks taken:

- old Trust Inspector primary projections were removed instead of kept in
  parallel;
- artifact ref hydration was extracted to a shared helper instead of embedded
  in multiple view modules;
- legacy display-only specs remain display-only and do not project workflow
  tasks;
- no compatibility branch was added for `joint`, `aggregate_then_join`,
  `AnalysisOpportunity`, `StrategyRecord`, `DataOperationRecord`, or
  `DerivedDataset`.

This reduces UI and workflow duplication while preserving reusable trust
substrates.

## Stage 3C1A Decision Status

Stage 3C1A data operations are **not ready**.

Reason:

- current real scenarios are answered by relationship diagnostics,
  independent analyses, and synthesis;
- savings-card real data shows many-to-many row multiplication risk;
- unrelated-file and fault-injection scenarios validate false-join prevention;
- no repeated scenario shows that a materialized cross-file operation is
  necessary for user value.

Reopen Stage 3C1A only when a future real scenario proves that independent
evidence plus synthesis is insufficient and that an exact, bounded two-dataset
operation would materially improve the answer.

## Remaining Caveats

- Final-answer depth is not yet deterministically measured; future
  golden-question tests should capture shallow-output regressions before adding
  an audit phase.
- The scenario runner validates readiness and file coverage; it does not score
  a published analysis by itself.
- Current real-data filenames display as mojibake in the repository
  environment; tests intentionally use the filenames as present on disk.

## Next Recommended Task

Add a small set of golden final-answer scenarios that evaluate professional
depth, evidence citation, limitation phrasing, and synthesis usefulness on the
real-data cases. This should come before designing heavier audit or operation
systems.
