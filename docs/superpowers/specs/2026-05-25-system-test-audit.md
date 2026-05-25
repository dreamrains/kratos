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

## Repair Pass

Date: 2026-05-25

Resolved findings:

1. Fixed time-grain inference for weekly, monthly, and yearly series.
   - Changed `_infer_time_grain()` to compare real pandas timedeltas instead of integer day buckets.
   - Regression coverage: `tests/test_data_features.py::TestInferTimeGrain`.

2. Fixed workspace dataset backup when parquet engines are unavailable.
   - `Workspace.persist_dataset()` now prefers parquet and falls back to pickle on missing optional parquet engines.
   - Agent restore strategy B now loads parquet first and pickle fallback second.

3. Confirmed stricter evidence chart governance.
   - `purpose="evidence"` still requires `evidence_ids`.
   - Updated legacy regression expectations to use `purpose="exploratory"` when no evidence binding exists.

4. Restored one-command pytest operability.
   - Legacy script-style tests are ignored by normal pytest collection:
     `test_comparability.py`, `test_sse_reactivity.py`, `test_tools_comprehensive.py`,
     `test_v10_new.py`, `test_v91.py`, and `test_web_gui.py`.
   - These remain candidates for future conversion into proper pytest or manual integration suites.

5. Added traceability fields to readiness output.
   - `assess_readiness()` now includes `dataset` and `recommendations` while preserving existing response fields.

6. Fixed pandas string dtype compatibility in field classification.
   - String date columns such as `日期` are now classified as time columns under pandas 3 string dtypes.
   - Time range detection safely parses string date columns before calculating spans.
   - Mixed string columns remain non-numeric after auto-clean when numeric coercion confidence is below threshold.

7. Fixed project-manager singleton behavior under runtime config changes.
   - `get_project_manager()` now refreshes the singleton when `projects_dir` changes, which keeps isolated tests and dynamic configs correct.

8. Reduced pandas compatibility warning noise.
   - Text-column injection scanning now explicitly includes both object and string dtypes.
   - Date-probe warnings during exploratory type detection are suppressed where expected.

## Final Verification

- `python -m compileall src tests`: passed.
- `pytest tests --collect-only -q`: `1301 tests collected`.
- `pytest tests/test_phase_comprehensive.py tests/test_project_intent_context.py -q`: `99 passed`.
- `pytest tests -q`: `1299 passed, 2 skipped, 29 warnings`.

Remaining warnings:

- Expected numpy/scipy warnings for constant or degenerate statistical edge-case tests.
- A local `.pytest_cache` permission warning in this workspace.

## Current Assessment

The data-analysis workflow, real-data audit scenarios, knowledge/memory MVP, retrieval budget behavior, evidence indexing, and management APIs are stable under the current automated suite.

The main remaining quality work is not a blocker for this repair pass: convert ignored script-style tests into deterministic pytest/integration tests when those flows become part of the release gate.
