# Test suite policy

Use the smallest authoritative layer that covers a change. Run the full suite
before release or after shared-contract changes; it is not the default inner
development loop.

## Authoritative entry points

| Need | Command | Scope |
| --- | --- | --- |
| Feature change | `python -m pytest tests/test_<owner>.py -q` | Owning unit or contract file |
| Cross-layer regression | `python -m pytest tests/real_data tests/test_<related>.py -q` | Real-data and related integration paths |
| Full deterministic suite | `python -m pytest tests -q` | All collected offline pytest contracts |
| Analysis release gates A-D | `python scripts/run_analysis_release_gates.py --profile deterministic` | Web/SSE contracts, tool runner, compile, evidence/publication, and deterministic replay |
| Product release gates A-F | `python scripts/run_analysis_release_gates.py --profile product ...` | A-D plus source-bound actual-browser and live-provider receipts |

`tests/test_tools_comprehensive.py` is the only retained custom-runner test. It
is excluded from pytest collection and executed explicitly by Gate A. A custom
runner must not be added to `collect_ignore` unless a release gate executes it
and checks its exit status.

## Functional coverage map

| Product area | Primary retained tests |
| --- | --- |
| Agent loop, execution, intent, prompts, and tool recovery | `test_comprehensive_analysis_flow.py`, `test_execution_control.py`, `test_intent_classification.py`, `test_prompt_system.py`, `test_tool_recovery.py` |
| Data loading, preparation, workspace versions, and multi-file scope | `test_data_preparation.py`, `test_scoped_workspace.py`, `test_workspace_*`, `test_multi_file_scope.py`, `test_multifile_*` |
| Statistical, causal, time-series, and comparability semantics | `test_statistical_route_requirements.py`, `test_experiment_route_requirements.py`, `test_time_series_route_requirements.py`, `test_comparability.py` |
| Charts, reports, and artifacts | `test_chart_contract.py`, `test_chart_semantics.py`, `test_report_pipeline.py` |
| Evidence, confirmation, trust, verification, and publication | `test_*evidence*`, `test_confirmation_*`, `test_trust_*`, `test_verification_layer.py`, `test_final_answer_*` |
| Web UI, API, SSE, resume, and workbench | `test_web_*`, `test_browser_gate_contract.py`, `test_analysis_progress_streaming.py` |
| Knowledge, memory, retrieval, and management center | `test_knowledge_*`, `test_memory_*`, `test_retrieval_*`, `test_web_management*` |
| Portable real-data quality and context degradation | `tests/real_data/test_*.py`, `test_golden_scenarios.py`, `test_analysis_reliability_replays.py` |

The normal pytest suite replaces optional LLM intent/playbook selection with
its deterministic rule fallback. Tests dedicated to provider and release
boundaries install explicit fake clients. Actual provider calls are never an
implicit consequence of running pytest.
