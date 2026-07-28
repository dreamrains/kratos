# Task 12 Phase B Report: Release Regressions and Deterministic Release Gate

## Status and scope

**DONE_WITH_CONCERNS**

Phase B is complete on `codex/analysis-reliability`, based on
`df84de08de17a2f422f8dddb047909e45134f387`.

This phase:

- diagnosed and closed the golden, order-dependent, and direct-script release
  regressions;
- closed the one code-verified deferred contract gap that was safe to close;
- recorded evidence-based rulings for the two deferred interfaces that cannot
  safely be wired yet;
- reran the deterministic replay gate, both focused lists, and the complete
  release gate.

Phase C was not performed: no browser acceptance, no live-provider runs, and no
design-status edits.

## Root causes, RED evidence, and changes

### 1. Revenue-decline golden assertion was stale after the canonical-plan cutover

#### RED

Command:

```powershell
$env:PYTHONPATH='D:\Project\Daily\data-agent\.worktrees\analysis-reliability\src;D:\Project\Daily\data-agent\.worktrees\analysis-reliability\tests'
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_golden_scenarios.py tests/real_data/test_context_budget_degradation.py -q
```

Result:

```text
FAILED tests/test_golden_scenarios.py::test_golden_revenue_decline_attribution
1 failed, 6 passed in 60.70s
```

The failed assertion required the literal word `exclude` in
`state.analysis_plan`.

#### Root cause

`record_analysis_spec` is now an explicitly deprecated, display-only adapter.
The sole writable authority is the server-selected canonical
`analysis_plan.v1`. The golden test already asserted the adapter was
display-only, but then contradicted that contract by requiring a legacy
`method_plan` sentence to overwrite the canonical plan.

The canonical `driver_decomposition` plan retained the required behavior:

- `analysis.period_compare`;
- `analysis.dimension_decomposition`;
- a deterministic prohibition against causal overclaim.

This was changed legitimate assurance behavior, not a production regression.

#### Change

`tests/test_golden_scenarios.py` now asserts the two structured capabilities and
the canonical causal-forbidden policy. It no longer treats display-only legacy
wording as a second planning authority.

#### GREEN

```text
7 passed in 60.74s
```

### 2. Same-turn file analysis reused persistent session/task state

#### RED

The selector in the Phase B brief was stale:

```text
tests/test_comprehensive_analysis_flow.py::TestComprehensiveAnalysisFlow::...
ERROR: not found
```

The real test is under `TestConversationFlow`. Running the corrected selector:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_comprehensive_analysis_flow.py::TestConversationFlow::test_same_turn_file_plus_analysis_does_not_end_after_profile -q
```

failed consistently:

```text
FAILED ... list_datasets() returned {}
1 failed in 12.71s
```

Failure instrumentation exposed the real tool result:

```json
{
  "error": "The active Stage 3C0B plan has no unique in-progress task.",
  "error_type": "stage3c0b_current_task_missing"
}
```

#### Root cause

The test used the fixed session ID `same_turn_load_analyze` while leaving
`AgentConfig` and the module-level `task_manager` on repository runtime paths.
Historical runs had accumulated:

- `workspace/tasks/active_plans.json` for that session;
- multiple `workspace/tasks/task_*.json` records;
- `sessions/same_turn_load_analyze/...`.

The execution-scope controller correctly failed closed because the reused
active plan had no unique in-progress task. The workspace scope was not
relaxed.

#### Change

The test now:

- uses the existing `tmp_project` fixture for temporary project/session roots;
- binds `task_manager._dir` and its ID counter to the test `tmp_path`;
- preserves the loop-owned workspace assertion and includes tool messages only
  as failure diagnostics.

No historical session or task file was deleted or edited.

#### GREEN

```text
1 passed in 3.80s
```

### 3. Legacy direct chart check tested obsolete error text and swallowed exit status

#### RED

Command:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' tests/test_tools_comprehensive.py
```

Result:

```text
PASS: 107
FAIL: 1
SKIP: 2
TOTAL: 110
FAIL: chart: 无数据 — should error when no data available
process exit: 0
```

#### Root cause

There were two independent test-harness defects:

1. the no-data check recognized only a string containing `Error`, while Task 5
   intentionally returns the structured exact-identity error
   `chart_dataset_ambiguous` with `eligible_datasets: []`;
2. the script printed its internal failure total but never converted it to a
   process failure.

The chart implementation itself correctly retained exact dataset identity; it
did not need a production change.

#### Change

`tests/test_tools_comprehensive.py` now:

- parses the chart error JSON;
- requires `error_type == "chart_dataset_ambiguous"`;
- requires `eligible_datasets == []`;
- exits `1` when its internal `FAIL` count is non-zero and `0` otherwise.

The original failing direct command was the acceptance RED for the process-exit
contract.

#### GREEN

Final direct run:

```text
PASS: 108
FAIL: 0
SKIP: 2
TOTAL: 110
process exit: 0
```

### 4. Auto-projected evidence omitted top-level dataset versions

#### RED

A focused assertion was added to the real projection path, followed by catalog
rendering:

```powershell
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_automatic_evidence_projection.py::test_bound_structured_computation_auto_projects_v2_evidence -q
```

Result before production change:

```text
KeyError: 'dataset_versions'
1 failed in 0.57s
```

#### Root cause

`_build_projected_record` retained the full computation ref, including its
dataset versions, but did not project those versions to the evidence record's
top level. `build_bounded_evidence_catalog` reads the top-level field, so the
required dataset-version line was absent.

#### Production change

`src/data_agent/agent/evidence_contracts.py` now copies the exact
`computation_ref["dataset_versions"]` list to the projected record. It does not
infer, replace, or broaden dataset identity.

#### GREEN

```text
focused test: 1 passed in 0.48s
tests/test_automatic_evidence_projection.py: 9 passed in 0.49s
```

The focused test also proves the bounded catalog contains the exact
`dataset_versions=<version>` line.

### 5. Full-suite streaming cleanup failures were a stale Task 11 event-order assumption

#### RED

The first complete suite run produced:

```text
17 failed, 2593 passed, 11 skipped, 36 warnings in 458.65s
```

The failures were:

- 12 parameterizations in `tests/test_streaming_context_cleanup.py`;
- 4 workspace-restore tests;
- 1 system data-quality test.

Phase-1 isolation:

```text
tests/test_streaming_context_cleanup.py: 12 failed
tests/test_workspace_restore_versions.py: 4 passed
test_game_purchase_analysis_outputs_reproducible_metric_quality: 1 passed
```

The streaming test expected the first event to be a `text_delta`. Task 11 now
correctly emits `analysis_progress` before final text. The first parameterized
case failed at that stale assertion while the generator was still open, leaving
the loop context bound. That poisoned the remaining parameterizations and the
later workspace tests. The independently green downstream files proved they
were victims, not separate defects.

#### Change

`tests/test_streaming_context_cleanup.py` now consumes leading
`analysis_progress` events while asserting that the loop context is bound.
It still asserts:

- the caller context is unchanged before generator execution;
- the loop context is bound while events are produced;
- close, exception, and exhaustion restore the outer context;
- no context remains after the test.

On normal exhaustion, any remaining events must be safe `analysis_progress`
events. No fixture or production gate was relaxed.

#### GREEN

```text
streaming file: 12 passed in 2.20s
streaming + workspace restore + quality test: 17 passed in 3.66s
complete suite: 2610 passed, 11 skipped, 36 warnings in 444.24s
```

## Deferred contract rulings

### Auto-projected `dataset_versions`: CLOSED

Code and a focused RED proved the catalog contract was broken. The exact
computation versions are now exposed at the evidence record's top level and
rendered by the bounded catalog.

### `attach_unique_exact_evidence_ids` in production final-answer audit: DEFERRED

Code inspection verified:

- `build_final_answer_audit` extracts claims and calls
  `verify_analysis_claims` directly;
- `attach_unique_exact_evidence_ids` has no production caller;
- extracted claims have generated `claim_N` keys, no `plan_id`, no exact
  dataset scope, and quantities/units represented as lists rather than the
  matcher's scalar material fields;
- auto-projected evidence carries structured values in `measurements`, not in
  the matcher's top-level scalar fields.

Therefore a current-plan exact match is not safely available. Supplying the
current plan ID or flattening one measurement would synthesize missing claim
identity and could bind the wrong claim. Zero/multiple-match behavior remains
tested and unbound. No matcher was wired in Phase B.

Exact blocker for final review: the claim-extraction contract must first expose
server-verifiable claim identity at the same grain as evidence measurements.

### Requirement-level corrected retry/fallback accounting: DEFERRED

Repository-wide call inspection verified:

- `record_corrected_retry` and `record_fallback` are used only by focused tests;
- no requirement-level recovery dispatcher exists in `AgentLoop`;
- the real loop continuation path is
  `TurnExecutionState.consume_quality_continuation`;
- `analysis_continuations_used` is bounded to one per turn and is used by both
  completion evaluation and the loop.

Wiring requirement counters without a dispatcher would guess which requirement
a generic continuation corrected or fell back from. The methods remain inert.
The existing turn-level convergence gate is exercised by focused and replay
tests.

### Other deferred minors: NOT TOUCHED

No reproduced failure implicated the remaining ledger minors, so Phase B did
not expand into unrelated cleanup.

## Deterministic and release-gate verification

All commands used the required worktree `PYTHONPATH`.

### Deterministic replay

```text
pytest tests/test_analysis_reliability_replays.py -q
4 passed in 73.00s
```

CLI:

```json
{
  "accepted": true,
  "mode": "deterministic",
  "factor_relationship": true,
  "sandbox_recovery": true,
  "unicode_boundary": true,
  "aggregate_profile_boundary": true
}
```

Process exit: `0`.

### Focused lists

First exact Task 12 focused list:

```text
153 passed in 111.04s
```

Second exact Task 12 focused list:

```text
141 passed in 79.44s
```

### Complete release gate

```text
python -m pytest -q
2610 passed, 11 skipped, 36 warnings in 444.24s
exit 0

python tests/test_tools_comprehensive.py
PASS 108 / FAIL 0 / SKIP 2 / TOTAL 110
exit 0

python -m compileall -q src/data_agent
exit 0

node --check src/data_agent/web/static/js/app.js
exit 0

git diff --check
exit 0
```

`git status --short` contained only the seven Phase B files listed below. No
`artifacts/` or `tmp/` output appeared.

## Files changed

- `src/data_agent/agent/evidence_contracts.py`
- `tests/test_automatic_evidence_projection.py`
- `tests/test_comprehensive_analysis_flow.py`
- `tests/test_golden_scenarios.py`
- `tests/test_streaming_context_cleanup.py`
- `tests/test_tools_comprehensive.py`
- `.superpowers/sdd/2026-07-27-analysis-execution-and-publication-reliability/task-12-phase-b-report.md`

## Self-review

- The only production change is the missing exact dataset-version projection.
- `analysis_requirement.v1`, `evidence_record.v2`, and
  `final_answer_audit.v1` remain the sole authorities.
- No publication, evidence-eligibility, scope, trace-depth, completion, or
  progress-no-leak gate was weakened.
- The golden test now checks stronger structured behavior instead of legacy
  prose.
- The order-dependent test isolates its own state instead of deleting or
  mutating historical state.
- The streaming cleanup test accepts only the Task 11 safe progress event
  class before/after text and continues to prove context cleanup.
- The direct runner reports truthful process status.
- No browser, live-provider, or design-status Phase C work was performed.

## Concerns

- The direct comprehensive script emits a non-failing `joblib` warning because
  Windows physical-core discovery cannot launch its helper. The script still
  reports 108/0/2 and exits 0; this is environmental and unrelated to the
  release contracts.
- The deterministic CLI emits LiteLLM's own debug/help banner and expected
  sandbox `Tool error` log lines. Replay assertions prove the user-facing
  answers do not contain the forbidden generic English warning.
- Exact evidence-ID auto-attachment and per-requirement recovery counters
  remain intentionally deferred for the blockers documented above.
