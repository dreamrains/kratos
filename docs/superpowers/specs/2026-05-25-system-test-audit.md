# System Test Audit

## Scope

Date: 2026-05-25

Focus areas:

- End-to-end data-analysis workflow coverage.
- Real-data analysis quality and reproducibility.
- Knowledge, memory, evidence indexing, and retrieval safety.
- Web management center regressions.
- Test-suite operability.

Real-data directory:

- `reference/test_doc`

## Real Data Inventory

- `游戏Abanner汇总数据.xlsx`: 248 data rows, banner ad revenue/exposure/click metrics.
- `游戏A内购数据.xlsx`: 248 data rows, active users, payers, purchase revenue, ARPU, ARPPU.
- `游戏A激励视频汇总数据报表.xlsx`: 248 data rows, rewarded video ad revenue/exposure/completion metrics.
- `游戏B留存.xlsx`: 62 data rows, daily active/new users and D1/D7/D14/D21/D30 retention.
- `游戏互推.xlsx`: 1,985 data rows, cross-promotion revenue, exposure, click, and confirmation metrics.
- `省钱卡用户最近流水_20260511.xlsx`: 13,815 data rows, user-level payment flow.
- `省钱卡订单_20260507.xlsx`: 71 data rows, card orders with payment and creation timestamps.

## Added Audit Coverage

New test file:

- `tests/test_system_data_analysis_quality_audit.py`

Covered scenarios:

- Game purchase analysis verifies ARPU reproducibility against source columns and checks trend/correlation tool output contracts.
- Game retention analysis verifies weighted retention calculation and evidence confidence downgrading when limitations/statistical significance are missing.
- Savings-card order/flow analysis verifies user-level joinability, paid total, and repeat-purchase metric reproducibility.
- Ordinary real-data analysis sessions index evidence without creating noisy memory candidates and only retrieve evidence when an explicit evidence budget is set.

Real-data metric checks observed:

- Game purchase revenue sum: `199946.0`.
- Game purchase max recomputed ARPU delta: `0.0000499`, indicating source ARPU is reproducible.
- Game retention weighted D1: `16.80%`; weighted D7: `5.03%`; simple D1: `17.08%`.
- Savings-card paid total: `2502.0`.
- Savings-card users matched to recent flow: `98.41%`.
- Savings-card repeat-purchase rate: `11.11%`.

## Verification Matrix

- Real-data and MVP suites:
  - Command: `pytest tests/test_real_data_integration.py tests/test_mvp_real_data_fixtures.py tests/test_mvp_memory_quality_real_data.py tests/test_mvp_retrieval_budget_real_data.py tests/test_system_data_analysis_quality_audit.py -q`
  - Result: `17 passed, 3 warnings`.
- Knowledge/memory/retrieval suites:
  - Command: `pytest tests/test_memory_store.py tests/test_memory_promotion.py tests/test_evidence_store.py tests/test_evidence_auto_index.py tests/test_evidence_kinds.py tests/test_knowledge_retrieval.py tests/test_knowledge_integration.py tests/test_knowledge_tools_phase1.py tests/test_knowledge_tools_phase15.py tests/test_knowledge_tools_phase2.py tests/test_memory_candidate_extractor.py tests/test_memory_candidate_auto_extract.py tests/test_memory_candidate_integration_phase2.py tests/test_retrieval_phase2.py tests/test_retrieval_budget_phase2.py -q`
  - Result: `88 passed, 1 warning`.
- Web management/workbench suites:
  - Command: `pytest tests/test_web_workbench_parity.py tests/test_web_overhaul.py tests/test_web_management.py tests/test_web_management_comprehensive.py tests/test_web_management_phase15.py tests/test_web_management_search_phase15.py tests/test_web_management_ui_phase15.py tests/test_web_memory_candidates_phase2.py tests/test_web_memory_review_ui_phase2.py -q`
  - Result: `155 passed, 1 warning`.
- Core workflow/planning/report suites:
  - Command: `pytest tests/test_analysis_flow_tools.py tests/test_analysis_state_v2.py tests/test_data_features.py tests/test_golden_scenarios.py tests/test_intent_classification.py tests/test_method_playbooks.py tests/test_pipeline_comprehensive.py tests/test_quality_control.py tests/test_report_pipeline.py tests/test_synthesis_policy.py -q`
  - Result: `427 passed, 3 failed, 30 warnings`.
- Analysis quality and optimization suites:
  - Command: `pytest tests/test_analysis_quality.py tests/test_optimization_comparison.py -q`
  - Result: `53 passed, 2 failed, 80 warnings`.
- Comprehensive analysis flow:
  - Command: `pytest tests/test_comprehensive_analysis_flow.py -q`
  - Result: `97 passed, 2 failed, 56 warnings`.
- Miscellaneous stable suites:
  - Command: `pytest tests/test_chart_contract.py tests/test_export_conversation.py tests/test_global_capabilities.py tests/test_interaction.py tests/test_llm_intent.py tests/test_migration.py tests/test_project_intent_context.py tests/test_project_manager.py tests/test_prompt_injection_safety.py tests/test_prompt_system.py -q`
  - Result: `238 passed, 1 warning`.
- Syntax checks:
  - `python -m compileall -q src\data_agent`: passed.
  - `node --check src\data_agent\web\static\js\app.js`: passed.

## Findings To Confirm

### P0/P1 Functional Risks

1. Time-grain inference misclassifies weekly, monthly, and yearly series as daily.
   - Evidence: `tests/test_data_features.py::TestInferTimeGrain::{test_weekly,test_monthly,test_yearly}` fail.
   - Impact: Trend summaries, data-characteristics cards, and downstream analysis may describe time granularity incorrectly, which can reduce analysis quality.
   - Suggested handling: Fix `src/data_agent/utils/data_features.py::_infer_time_grain` with a focused regression test.

2. Workspace persistence requires parquet engines that are not installed.
   - Evidence: `workspace.persist_dataset()` fails with missing `pyarrow`/`fastparquet`.
   - Impact: Session restore strategy B cannot work in the current environment when original source files are unavailable.
   - Suggested handling: Either add a runtime dependency or implement a CSV/JSON fallback for dataset backup.

3. Evidence-backed chart validation conflicts with an old-session regression expectation.
   - Evidence: `purpose="evidence"` now fails without `evidence_ids`.
   - Impact: This may be correct stricter behavior, but old sessions or LLM calls that set purpose first may receive validation errors.
   - Suggested handling: Confirm whether evidence charts must always provide `evidence_ids`; if yes, update old regression expectations and agent prompt/tool guidance.

### Test-Suite Operability Risks

4. `pytest tests` is not currently a reliable single command.
   - Evidence: initial full run was interrupted by `test_comparability.py` calling `sys.exit()` at import time; after adding it to `collect_ignore`, full collection still timed out at 120 seconds.
   - Mitigation applied: added `test_comparability.py` to `tests/conftest.py::collect_ignore`.
   - Suggested handling: Convert legacy script tests to pytest or keep them under a separate script-test command.

5. `test_sse_reactivity.py` is a script-style integration test with external runtime assumptions.
   - Evidence: fails during collection because `reference/workspace/test_sales.csv` is missing; printed checks also show SSE/text/reactivity failures.
   - Impact: It cannot be used as a normal pytest test and may hide real SSE regressions.
   - Suggested handling: Convert to a proper skipped integration test unless a live server and fixture are explicitly available.

6. `test_v91.py` mutates `sys.stdout`/`sys.stderr`, which breaks pytest capture in normal mode.
   - Evidence: `pytest tests/test_v91.py -q` raises `ValueError: I/O operation on closed file`; `pytest -s` exits 0 but prints several internal FAIL records.
   - Suggested handling: Split script assertions into real pytest tests and remove global stream wrapping during pytest runs.

7. `test_web_gui.py` timed out after 180 seconds.
   - Evidence: `pytest tests/test_web_gui.py -q` did not complete within timeout.
   - Suggested handling: Mark as integration/manual or add deterministic server fixture and shorter timeouts.

### Product/API Improvement Notes

8. `assess_readiness()` does not include the dataset name or recommended next actions in its JSON response.
   - Evidence: Real-data audit expected traceability fields but actual contract is `summary/overall/findings/rows/cols`.
   - Impact: Downstream reporting and UI cannot easily tie readiness output back to a dataset or guide the next analysis step.
   - Suggested handling: Add `dataset` and `recommendations` fields in a backward-compatible way.

9. Pandas 3 compatibility warning in `data_io.py`.
   - Evidence: repeated `Pandas4Warning` around `select_dtypes(include=["object"])`.
   - Impact: Future pandas upgrade may change string/object selection behavior.
   - Suggested handling: update string-column detection to explicitly include string/object as intended.

## Current Assessment

The knowledge/memory MVP path is stable under the tested scenarios: evidence indexing, candidate extraction, candidate confirmation/retrieval budget behavior, and management APIs pass focused and real-data tests.

The larger data-analysis workflow is usable, but analysis quality has three important risks before treating the system as robust:

- Time granularity inference is wrong for non-daily series.
- Session dataset restore depends on unavailable parquet support.
- Some integration/script tests are not integrated into pytest cleanly, so one-command confidence is currently weak.

Recommended next step: confirm which findings should be fixed immediately. My recommendation is to fix items 1, 2, 4, 5, and 6 before doing another full quality pass; item 3 needs product confirmation because it involves strict evidence governance versus old-session compatibility.
