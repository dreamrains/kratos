# Legacy test and script disposition

This inventory prevents ignored or manual programs from silently influencing
release conclusions. A removed file is acceptable only when its unique behavior
is mapped to collected pytest coverage or declared obsolete.

| Legacy file | Prior problem | Disposition | Authoritative replacement |
|---|---|---|---|
| `regression_test.py` | Filename was not collected; custom counters executed at import; not owned by a release gate | Duplicate/obsolete, remove | intent, prompt, pipeline, history, and compilation contracts in collected pytest plus Gate A compile |
| `test_v10_new.py` | Explicitly ignored custom runner containing a mixture of unique and duplicate V10 checks | Migrate unique coverage, then remove | `test_tool_utils.py`, `test_simulation_tools.py`, `test_pipeline_comprehensive.py`, `test_phase_comprehensive.py`, `test_chart_contract.py`, capability/registry tests |
| `test_v91.py` | Explicitly ignored system script dominated by source-string assertions and deprecated report behavior | Obsolete/duplicate, remove | behavioral `test_web_*`, `test_chart_contract.py`, intent tests, pipeline tests, and actual-browser Gate E |
| `test_comparability.py` | Explicitly ignored custom runner despite current business-critical period normalization behavior | Migrate | converted into ordinary collected pytest in the same file |
| `acceptance/legacy_sse_reactivity.py` | Manual HTTP/SSE diagnostic; could not prove reactive DOM behavior or actual-browser acceptance | Diagnostic superseded, remove | `test_web_sse_contract.py`, `test_web_sse_reactivity_contract.py`, progress/confirmation tests, actual-browser Gate E |
| `acceptance/legacy_web_gui.py` | Manual endpoint script mixed HTTP checks with self-managed PASS counters | Diagnostic superseded, remove | collected `test_web_*` API/behavior contracts plus actual-browser Gate E |
| `test_tools_comprehensive.py` | Direct custom runner; runs outside pytest and mixes many owners | Temporarily retained and gate-owned; migrate incrementally | Gate A executes its exit code until unique checks move to focused collected pytest |
| `test_phase_comprehensive.py` external Excel cases | Historical integration checks depend on private `reference/test_doc/*.xlsx` files that are not tracked and are absent in isolated release worktrees | Keep portable cases collected; explicitly skip only external-fixture cases when files are absent | tracked synthetic/portable real-data tests, focused tool contracts, deterministic replay, and Gate E |

Rules:

- `collect_ignore` may contain only a temporarily retained direct runner listed
  in the release gate's explicit allowlist.
- Deleted legacy files never count as executed coverage.
- Static source assertions do not replace behavioral Web or browser tests.
- Missing private reference workbooks are reported as explicit skips and never
  as product regressions or passing portable coverage.
- The direct tool runner must be removed after its unique checks are mapped;
  it is not a permanent exception.
