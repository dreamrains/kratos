---
title: Assurance Overlay Recovery — Single-Mode Reliable Path with Best-Effort Rigor
status: draft
date: 2026-08-11
supersedes:
  - docs/superpowers/specs/2026-08-09-analysis-runtime-systemic-recovery-design.md (refines; drops its strict-gate publication model)
  - the strict/shadow dual-track proposed earlier in this thread
amends:
  - Phase 0 transparent publication (already merged in working tree) becomes the unconditional, permanent publication behavior
---

# 1. Problem

Since the boundary commit `04ef1c6` (2026-07-18) a multi-layer "Stage 3C0B trust/verification overlay" was inserted between the analysis engine and the user. It is **coupled**, and its foundation is broken, so failures cascade end-to-end. Evidence: three live sessions (`fee2e889e37f`, `d44c4e8387ce`, the 2026-08-09 `71aa1197df28` baseline) all show the same pattern.

### The broken stack

```
LLM tool call
  │
  ① Plan-step binding   bind_tool_call_to_plan_step  (analysis_execution.py:276)
     ✗ 100% failure across sessions: analysis_step_not_found / _not_bound / ambiguous
     Root cause (concrete): the binder requires exact capability + exact dataset match
     with exactly one candidate. But the LLM calls many supporting tools per step
     (run_python, read_file, create_chart, list_data, record_evidence) that declare no
     matching capability, and run_python declares no dataset input. factor_relationship_
     analysis matches two steps (duplicate capability) → ambiguous.
  │  (binding fails → downstream starves)
  ▼
  ② Task/dataset scope   execution_scope.py (:349/603/623), workspace.py (:552/816)
     ✗ rejects the analysis dataset itself: dataset_outside_current_task_scope
       (d44c4e8387ce) → analysis truncated
  ▼
  ③ Task advancement   ✗ never advances (stuck 0/8); frontend panel won't collapse
  ▼
  ④ Evidence projection   project_structured_computation_evidence (evidence_contracts.py:3520)
     ✗ no bound step → projection fails (13 rejection points); run_python never upgraded
  ▼
  ⑤ Measurement identity   ✗ no [[evidence:aeNN#amNN]] markers → every material claim
       flagged missing_evidence_identity
  ▼
  ⑥ Verification   overall_status = fail
  ▼
  ⑦ Publication   answer_quality.py render_audited_analysis_answer
       • tiered/strict (old default): DELETES unsupported claims → placeholder  (original paralysis)
       • transparent (Phase 0, now default): relays draft + annotates  (fixed)
```

Cross-cutting: confirmation gates hang the flow on non-destructive derived versions; synthesis policy chokes depth to "light" and suppresses recommendations; compaction truncates tool outputs.

**Key fact:** the analysis engine itself is fine. Same prompt on `最强砖块记录.xlsx` → 2835-char rigorous answer on 2026-07-11, 854-char placeholder on 2026-08-09, 2244-char real answer after Phase 0 transparent mode. The overlay was *censoring* correct output. The user goal: a **stable, fully-usable project** whose analysis output is rigorous; rigor is layered on top without ever making usability depend on it.

# 2. Decisions

- **D1 — Single mode.** No strict/shadow dual-track. One path: best-effort binding → advisory projection → scoring audit → **non-destructive** publication. (The dual-track complexity is eliminated by not building it.)
- **D2 — Publication is unconditionally non-destructive.** Relay the draft verbatim (evidence markers stripped) and append annotations. **No mode ever deletes a claim or injects a `无法发布` placeholder.** This is Phase 0's transparent behavior, made permanent. (Implements codex Task 7 correctly — assemble/annotate, never edit draft spans into diagnostics.)
- **D3 — Best-effort plan-step binding.** (Codex Task 6, done properly.) Attribute supporting tools (`run_python`, `read_file`, `create_chart`, `list_data`, `record_evidence`) to the **currently-active step** (tracked by plan progression) without requiring capability match; only primary analysis tools use capability match; plan generation **deduplicates** `required_capability` across steps. Binding is best-effort: failure degrades annotation quality, never blocks.
- **D4 — Advisory evidence projection.** Projection still runs; when binding succeeds it produces real measurement identity so audit annotations are meaningful ("claim verified against computation X"). When it fails, nothing is gated — the draft is still published with a soft note.
- **D5 — Audit scores; never deletes.** Verification classifies claims; publication annotates the subset that genuinely contradicts computed evidence (numeric/direction/scope mismatch, fabricated, stale, causal-invalid). Pure bookkeeping failures (missing marker identity, unbound step) are **not** surfaced — they are not a quality signal. (Phase 0 footer refinement already implements this distinction.)
- **D6 — Non-destructive derived versions auto-approved.** Copy-on-write derived dataset versions (no semantic change, raw retained) are applied without a confirmation receipt. Confirmation is kept only for **truly destructive / meaning-changing** cleaning.
- **D7 — Execution scope is advisory.** `dataset_outside_current_task_scope` logs a warning and allows the dataset; it never blocks a tool call.
- **D8 — Task advancement reflects real execution.** The task list advances on actual tool execution / step completion observable from the loop, not from the broken capability binding.
- **D9 — Workbench "当前分析" surgery.** Keep **only** the 结论 (conclusions) block. Delete 建议下一步, 完整叙述（AI 原文）, 数据明细（下钻）. "产出与导出" tab unchanged.
- **D10 — Inline chart rendering.** Plotly chart `div` is `height:100%`; inside the 450px iframe it collapses to 0 (blank) because the iframe `<body>` has no height. Inject `html,body{height:100%;margin:0}` into chart iframes so the chart fills the frame. (Works standalone today; only inline is broken.)

# 3. Architecture (single-mode reliable path)

```
User turn
  → AgentLoop runs LLM with active tools
  → tool calls execute (scope = advisory D7; no blocking)
  → each tool call: best-effort bind to current step (D3) → record diagnostic
  → evidence projection runs advisory (D4); succeeds when binding resolves
  → task list advances on real execution (D8)
  → non-destructive derived data ops auto-applied (D6); destructive still confirm
  → LLM synthesizes final draft (synthesis policy un-choked: depth up to deep,
       recommendations allowed, may report tool-computed results)
  → audit scores claims against projected evidence (D5)
  → publication relays draft + annotates only substantive contradictions (D2/D5)
  → user sees the full analysis, with honest notes only where real conflicts exist
```

The overlay (binding/projection/audit) becomes a **scoring/annotation layer**, not a gate. Its value (traceability, fabricated-number detection) is delivered through annotation, never deletion.

# 4. Component changes

### M1 — Stable & usable (must land first; makes the project work end-to-end)

| ID | Area | Change |
|----|------|--------|
| M1-1 | `config.py` | The strict/shadow dual-track is **not built** (it was only a proposal earlier in this thread). `assurance_publication_mode` keeps `transparent` (Phase 0) as the sole default; tiered/strict remain defined but are invoked nowhere at runtime (dormant, pending cleanup). |
| M1-2 | `answer_quality.py` | Make transparent the unconditional publication path. Keep `_render_transparent_publication` (Phase 0 + footer refinement) as the only renderer used at runtime. |
| M1-3 | `loop.py` (`_current_task_scope_guard` dispatch, :545) + `execution_scope.py` | Scope guard becomes advisory: on `dataset_outside_current_task_scope`, log + allow, never return a blocking error. |
| M1-4 | `data_clean.py` (`requires_confirmation`, :813/848-857/895-975) | Non-destructive derived versions (copy-on-write, no semantic change) set `requires_confirmation=False` and apply directly. Keep confirmation for meaning-changing ops. |
| M1-5 | task advancement (`analysis_flow_controller.py` / `analysis_run_coordinator.py`) | Advance the task list from observed tool execution, not capability binding. The "任务 N/M" reflects real progress; the panel collapse guard no longer thinks a task is forever in-progress. |
| M1-6 | `web/static/js/app.js` (`injectChartPlotly`, :2443) + `templates/index.html` (:277 iframe) | Inject `html,body{height:100%;margin:0}` into chart iframe docs so the 100%-height Plotly div fills the frame. Fixes blank-inline-chart. |
| M1-7 | `web/templates/index.html` "当前分析" panel (:537-684) | Keep only 结论. Delete 建议下一步 (:569), 完整叙述（AI 原文） (:619), 数据明细（下钻） (:627-629). 产出与导出 (:537/684) untouched. |

Acceptance for M1: a normal web session (upload → ask an analysis question → get answer) runs end-to-end with **no** `无法发布`/`当前可追踪证据不足` placeholders, **no** scope-block, **no** confirmation hang on derived versions, charts render inline, task list advances and collapses, and the workbench panel shows only 结论 + 产出与导出.

### M2 — Rigor (codex Task 6, done right; non-blocking because M1 already guarantees usability)

| ID | Area | Change |
|----|------|--------|
| M2-1 | `analysis_execution.py` `bind_tool_call_to_plan_step` (:276-377) | Best-effort current-step attribution. Track the active step from plan progression; attribute supporting tools (an allowlist: `run_python`, `read_file`, `create_chart`, `list_data`, `list_files`, `record_evidence`) to the active step without capability match. Primary analysis tools still use capability match. Never return a hard failure that downstream gates on — return the best binding + a confidence flag. |
| M2-2 | plan generation (where `method_plan` is built) | Deduplicate `required_capability` across steps so a primary tool matches exactly one step (no more ambiguous). |
| M2-3 | `evidence_contracts.py` `project_structured_computation_evidence` (:3520) | When binding resolves (M2-1), project computation → measurement identity. Promote successful `run_python` computations to evidence on a best-effort basis (instead of "never upgraded"). Projection failure remains non-gating. |
| M2-4 | `synthesis_policy.py` | Un-choke in single mode: `insight_depth` up to `deep`/`standard`; stop default-suppressing `decision_recommendation`; stop forcing `business_translation="cautious"`; drop the "return partial answer if no catalog evidence" directive (:270-276) — allow reporting tool-computed results. |
| M2-5 | `verification.py` + `answer_quality.py` | Audit annotates substantive contradictions only (D5). Annotations become meaningful because projection (M2-3) now supplies real identity. |

Acceptance for M2: on a clean run, the publication footer carries **specific, real** annotations only when a claim actually contradicts computed evidence; on a normal run with no contradictions, no footer. The audit's verdict is non-empty and traceable (binding succeeded), not uniformly `missing_evidence_identity`.

### Cleanup (after M2)

- Remove dormant tiered/strict publication branches in `answer_quality.py`; rewrite the tests that assert destructive behavior (`test_final_answer_publish_gate.py` tiered-pinned tests, the destructive cases in `test_tiered_analysis_publication.py`) to assert the non-destructive contract.
- Retire `assurance_publication_mode` config if no longer load-bearing.

# 5. Sequencing rationale

M1 first because the user's stated goal is a **stable, usable project**. M1 makes the project work end-to-end *without* depending on the binding fix. This is the lesson from codex's failure: they made usability depend on binding (Task 6) that they couldn't finish. M2 then realizes the rigor value of the structure on top of a project that already works. If M2's binding work proves harder than expected, M1 still delivers a usable project.

# 6. Testing

- **M1:** add integration tests that a turn runs with scope/binding/confirmation non-blocking and produces non-placeholder output. Keep the existing 187 publication tests green (transparent path). Full suite + deterministic release gates A–D must pass.
- **M2:** add tests for best-effort binding (supporting tool → current step; primary tool → capability; duplicate-capability dedup), best-effort projection (run_python promoted when bound), and audit annotation quality (substantive vs bookkeeping).
- Live validation: re-run the `最强砖块记录.xlsx` A/B prompt after M1 (expect: real answer, no placeholders, no hang, chart renders, panel correct) and after M2 (expect: meaningful or absent footer).

# 7. Out of scope / deferred

- Full workbench refactor (user-owned). Only the M1-7 panel surgery is in scope here.
- Making strict/tiered publication pass real sessions (codex Tasks 6-7 strict variant) — explicitly dropped (D1). Strict gating, if ever wanted for release hardening, is a separate future effort.
- Recovery plan's Gate E/F (browser/provider) receipt mechanics — not blocking; revisit after M1/M2.
- Pre-July session-format migrations, MCP/skills changes — unrelated.
