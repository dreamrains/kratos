# Assurance Overlay Recovery — M1 (Stable & Usable) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project end-to-end stable and usable in a single normal web session — no `无法发布` placeholders, no scope-block, no confirmation hang on derived data, charts render inline, the workbench panel matches the spec — *without* depending on the plan-step binding fix (that is M2).

**Architecture:** One reliable mode. Publication is unconditionally non-destructive (Phase 0 transparent, made permanent). The overlay's gating points (execution scope, cleaning confirmation, task advancement) are converted from blocking to advisory/reflected so a normal turn always completes. The LLM runs tools → synthesizes → publishes; the overlay records diagnostics but never blocks output.

**Tech Stack:** Python 3.12, pydantic-settings, Flask + Alpine.js + Plotly, pytest. Source under `src/data_agent/`, tests under `tests/`.

**Reference spec:** `docs/superpowers/specs/2026-08-11-assurance-overlay-recovery-design.md`

## Global Constraints

- Chinese-language product: all user-visible strings stay Chinese; do not introduce English fallback text into published answers.
- Windows-first: UTF-8, no `signal`-based timeouts, forward-slash paths in shell commands.
- Offline test suite must stay green: `uv run pytest tests/ -q` (note: known order-dependent flakiness in scenario tests — re-run failures in isolation before treating as a regression). Release gates: `uv run python scripts/run_analysis_release_gates.py --profile deterministic` must report `overall_status: PASS`.
- Non-destructive publication is permanent: no task in this plan may (re)introduce deletion of claim spans or the `无法发布` / `当前可追踪证据不足` placeholders into the published path.
- Do not commit unless the task's commit step says so. Each task ends with its own commit.

## File Structure

| File | Responsibility | Touched by |
|------|----------------|------------|
| `src/data_agent/agent/loop.py` | `_render_audited_publication` always uses transparent; scope guard wired advisory | Task 1, Task 2 |
| `src/data_agent/session/workspace.py` | dataset access no longer hard-blocks on `dataset_outside_current_task_scope` | Task 2 |
| `src/data_agent/tools/data_transform.py` | same scope advisory for transform tool | Task 2 |
| `src/data_agent/tools/data_clean.py` | non-destructive derived versions apply without confirmation receipt | Task 3 |
| `src/data_agent/agent/analysis_flow_controller.py` (and/or `analysis_run_coordinator.py`) | task list advances on real tool execution | Task 4 |
| `src/data_agent/web/static/js/app.js` | chart iframe gets `html,body{height:100%}` | Task 5 |
| `src/data_agent/web/templates/index.html` | 当前分析 panel keeps only 结论 | Task 6 |
| `tests/test_assurance_overlay_m1.py` (new) | M1 integration tests | Tasks 1–4 |

---

### Task 1: Make non-destructive publication unconditional

Publication must relay the draft + annotate in **every** case, regardless of `assurance_publication_mode`. Today the loop reads `_publication_mode()` and passes it to `render_audited_analysis_answer`; if someone sets the config to `strict`/`tiered`, the destructive path runs. Close that hole: the loop always publishes transparently.

**Files:**
- Modify: `src/data_agent/agent/loop.py` (`_render_audited_publication`, ~:2947-2954)
- Test: `tests/test_assurance_overlay_m1.py` (new file)

**Interfaces:**
- Consumes: `data_agent.agent.answer_quality._render_transparent_publication` (already exists from Phase 0)
- Produces: a loop that never emits destructive publication

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assurance_overlay_m1.py
from types import SimpleNamespace
from data_agent.agent.loop import AgentLoop
from data_agent.agent import trust_workflow_runtime as runtime
from data_agent.llm.client import Response, ToolCall


def _audit_blocked_no_evidence():
    return {
        "contract_version": "final_answer_audit.v1",
        "id": "audit_block",
        "status": "blocked",
        "public_text": "",
        "claims": [{"id": "claim_1", "text": "本月收入增长了 5%。", "claim_type": "numeric", "material": True}],
        "claim_checks": [{"claim_id": "claim_1", "status": "failed", "reason_codes": ["missing_evidence_identity"]}],
    }


def test_publication_is_non_destructive_even_when_config_says_strict(monkeypatch):
    """The loop must publish transparently regardless of assurance_publication_mode."""
    loop = AgentLoop(client=object(), session_id="m1_pub")
    loop._publication_mode = lambda: "strict"  # simulate a strict config
    loop._last_turn_intent = SimpleNamespace(intent_type="directed_analysis", execution_readiness="ready")
    state = SimpleNamespace(evidence_records=[{"id": "ev_1"}], verification_reports=[], turn_diagnostics=[])
    state.append_turn_diagnostic = state.turn_diagnostics.append
    loop.context.analysis_state = state
    monkeypatch.setattr(runtime, "audit_final_answer_draft", lambda *_a, **_k: {
        "contract_version": "final_answer_audit.v1", "id": "ref", "status": "blocked",
        "artifact_path": "f.json", "artifact_digest": "0" * 64})
    monkeypatch.setattr(runtime, "hydrate_final_answer_audit_ref", lambda _r: _audit_blocked_no_evidence())
    monkeypatch.setattr(loop, "_evaluate_turn_completion", lambda: SimpleNamespace(status="complete", is_terminal=True))

    text = loop._render_audited_publication(
        "本月收入增长了 5%。这是完整分析。", _audit_blocked_no_evidence())

    assert "本月收入增长了 5%" in text            # claim relayed, NOT deleted
    assert "这是完整分析" in text
    assert "无法发布" not in text                 # no placeholder, even though config=strict
    assert "当前可追踪证据不足" not in text
    # bookkeeping-only failure produces no alarming footer (Phase 0 refinement)
    assert "局限说明" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_assurance_overlay_m1.py::test_publication_is_non_destructive_even_when_config_says_strict -q`
Expected: FAIL — current code passes `mode=self._publication_mode()` → `"strict"` → destructive path → `无法发布` appears (or claim deleted).

- [ ] **Step 3: Make publication unconditional**

In `src/data_agent/agent/loop.py`, edit `_render_audited_publication` so it ignores the configured mode and always renders transparently:

```python
    def _render_audited_publication(
        self,
        draft: str,
        audit: dict[str, Any] | None,
    ) -> str:
        """Render a draft answer. Publication is ALWAYS non-destructive
        (transparent): relay the draft and annotate. The configured
        ``assurance_publication_mode`` is consulted only for the observability
        diagnostic, never to select a destructive renderer."""

        from data_agent.agent.answer_quality import (
            PublicationResult,
            _render_transparent_publication,
        )

        completion = self._evaluate_turn_completion()
        rendered: PublicationResult = _render_transparent_publication(
            draft=draft,
            audit=audit if isinstance(audit, dict) else None,
        )
        self._record_publication_diagnostic(rendered)
        return rendered.text
```

(Keep `_publication_mode()` and `_record_publication_diagnostic` as-is — they still record the configured mode in diagnostics for observability.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_assurance_overlay_m1.py::test_publication_is_non_destructive_even_when_config_says_strict -q`
Expected: PASS.

- [ ] **Step 5: Run the publication regression suite**

Run: `uv run pytest tests/test_tiered_analysis_publication.py tests/test_final_answer_publish_gate.py tests/test_final_answer_claim_audit.py -q`
Expected: PASS (transparent path unchanged; these test the renderer directly with explicit modes).

- [ ] **Step 6: Commit**

```bash
git add src/data_agent/agent/loop.py tests/test_assurance_overlay_m1.py
git commit -m "$(cat <<'EOF'
fix: make non-destructive publication unconditional

The loop now always renders transparently regardless of
assurance_publication_mode, so no config value can re-introduce the
post-July destructive publication (claim deletion / 无法发布 placeholders).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Make execution scope advisory (stop blocking on `dataset_outside_current_task_scope`)

In session `d44c4e8387ce` the analysis was truncated because the dataset was judged outside the current task scope. Convert this from a hard block to a logged warning that still allows the operation.

**Files:**
- Modify: `src/data_agent/session/workspace.py` (~:552, ~:816)
- Modify: `src/data_agent/tools/data_transform.py` (~:384)
- Test: `tests/test_assurance_overlay_m1.py`

**Interfaces:**
- Produces: dataset access succeeds with a warning diagnostic instead of an error string, when the dataset is outside the registered task scope.

- [ ] **Step 1: Read the current enforcement to locate the exact guard**

Read `src/data_agent/session/workspace.py` around lines 540-560 and 800-820, and `src/data_agent/tools/data_transform.py` around 370-390. Identify the function that returns `"Error: dataset_outside_current_task_scope"` and how the caller reacts (does a non-empty "Error:" prefix abort the tool?).

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_assurance_overlay_m1.py
def test_out_of_scope_dataset_is_allowed_with_warning():
    """A dataset outside the current task scope must be accessible (advisory),
    not blocked. The scope layer records a warning instead of returning an error."""
    from data_agent.session.workspace import WorkspaceManager

    ws = WorkspaceManager(root=tmp_workspace_root())  # helper from tests/conftest or inline temp dir
    ws.register_dataset("brick_strategy_confirm", _make_dataframe())  # in pool but not in a task scope
    # Attempt to read it without registering a task scope that includes it:
    result = ws.get_dataset("brick_strategy_confirm")
    assert result is not None                       # access succeeds
    assert "dataset_outside_current_task_scope" not in str(result)  # not an error string
```

(If `WorkspaceManager`'s API or the conftest helper differs, adapt the test to the real method names found in Step 1 — the assertion contract is: out-of-scope access returns the dataset, not an error string, and a warning is recorded.)

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_assurance_overlay_m1.py::test_out_of_scope_dataset_is_allowed_with_warning -q`
Expected: FAIL — currently returns the error string.

- [ ] **Step 4: Convert the block to advisory**

In `workspace.py` (both ~:552 and ~:816) and `data_transform.py` (~:384): instead of returning `"Error: dataset_outside_current_task_scope"`, log a warning (via the module logger) and proceed with the dataset. Keep the `dataset_outside_current_task_scope` *symbol* available (e.g. append it to a `scope_warnings` list on the workspace, or emit a turn diagnostic) so M2 can still observe it — but it no longer blocks.

Concretely, replace the `return "Error: ..."` branches with: warn + fall through to the normal dataset access path. Preserve the existing `derived_scope_not_registered` behavior for genuinely unregistered derived datasets (that is a different, legitimate guard).

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_assurance_overlay_m1.py::test_out_of_scope_dataset_is_allowed_with_warning -q`
Expected: PASS.

- [ ] **Step 6: Run scoped-workspace regression tests and adjust intent**

Run: `uv run pytest tests/test_scoped_workspace.py -q`
Expected: tests that asserted `dataset_outside_current_task_scope` as a *block* will now fail. Update those assertions to reflect advisory behavior (access succeeds + warning recorded). Do NOT delete the tests — repurpose them to assert the new advisory contract.

- [ ] **Step 7: Commit**

```bash
git add src/data_agent/session/workspace.py src/data_agent/tools/data_transform.py tests/test_assurance_overlay_m1.py tests/test_scoped_workspace.py
git commit -m "$(cat <<'EOF'
fix: make execution scope advisory instead of blocking

Datasets outside the current task scope are now accessed with a recorded
warning rather than aborting the tool call. This unblocks normal analysis
sessions where the loaded dataset was wrongly rejected as out-of-scope.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Auto-approve non-destructive derived dataset versions

The confirmation gate hung session `fee2e889e37f` on a "creates a new analysis dataset version" prompt. Copy-on-write derived versions are non-destructive (raw retained); they should apply without a confirmation receipt. Keep confirmation for meaning-changing cleaning.

**Files:**
- Modify: `src/data_agent/tools/data_clean.py` (`requires_confirmation` logic, ~:813, :848-857, :895-975)
- Test: `tests/test_assurance_overlay_m1.py`

**Interfaces:**
- Produces: `_apply_type_conversion_impl` (and the cleaning entrypoint) apply directly when the operation is non-destructive; `requires_confirmation` stays True only when a risk signal fires.

- [ ] **Step 1: Read the risk-signal computation**

Read `src/data_agent/tools/data_clean.py` lines 840-980. Note the signals that set `operation_requires_confirmation` (`numeric_with_suffix` target, partial conversion, new nulls, cardinality loss, low confidence, type mismatch). Define: **non-destructive** = none of those signals fire AND the operation produces a derived/versioned dataset (raw retained by copy-on-write lineage).

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_assurance_overlay_m1.py
def test_non_destructive_derived_version_applies_without_confirmation():
    """A type conversion that changes no semantics (e.g. int -> str of an id
    column with zero nulls/cardinality loss) applies directly, without
    requiring an approved confirmation receipt."""
    from data_agent.tools.data_clean import _apply_type_conversion_impl  # or the public entry, per Step 1

    df = _make_dataframe()  # e.g. id column 1..5, no nulls
    result = _apply_type_conversion_impl(df, column="id", target="str", _approved_confirmation_id="")
    # Non-destructive: applies without a receipt...
    assert result.error_type in (None, "")
    assert "confirmation_required" not in str(result)
    # ...and the transformation happened.
    assert _converted_values_are_str(result)
```

(Adapt the function name and the dataframe builder to the real signature found in Step 1. The contract: no `_approved_confirmation_id` supplied AND non-destructive ⇒ applies, not blocked.)

Also add the inverse:

```python
def test_destructive_cleaning_still_requires_confirmation():
    """A meaning-changing conversion (e.g. introduces nulls / cardinality loss)
    still requires an approved confirmation receipt."""
    from data_agent.tools.data_clean import _apply_type_conversion_impl
    df = _make_dataframe_with_uncoercible_values()
    result = _apply_type_conversion_impl(df, column="x", target="int", _approved_confirmation_id="")
    assert "confirmation_required" in str(result) or result.error_type == "confirmation_required"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_assurance_overlay_m1.py -k "non_destructive or destructive" -q`
Expected: FAIL — currently `requires_confirmation = bool(auto)` and the derived-version path triggers confirmation regardless.

- [ ] **Step 4: Gate confirmation on real risk only**

In `data_clean.py`, change the confirmation decision so a non-destructive derived version sets `requires_confirmation = False`. Concretely: after computing `operation_requires_confirmation` (the risk signals), set:

```python
# A derived/versioned dataset with no risk signals is non-destructive
# (raw is retained by copy-on-write lineage). Apply directly, no receipt.
non_destructive_derived = (
    not operation_requires_confirmation
    and not (new_nulls_introduced or cardinality_loss)   # use the real signal vars from Step 1
)
if non_destructive_derived:
    requires_confirmation = False
```

Keep the existing block at ~:962-975 unchanged so that when `requires_confirmation` is still True (destructive), the confirmation receipt is still required.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_assurance_overlay_m1.py -k "non_destructive or destructive" -q`
Expected: PASS.

- [ ] **Step 6: Run cleaning regression tests**

Run: `uv run pytest tests/ -k "clean or confirm or transform" -q`
Expected: PASS; update any test that asserted a receipt for a now-non-destructive op.

- [ ] **Step 7: Commit**

```bash
git add src/data_agent/tools/data_clean.py tests/test_assurance_overlay_m1.py
git commit -m "$(cat <<'EOF'
fix: auto-approve non-destructive derived dataset versions

Copy-on-write derived versions with no risk signals (no new nulls,
cardinality loss, or semantic change) now apply without a confirmation
receipt, so analysis flows are no longer suspended on benign data prep.
Destructive/meaning-changing cleaning still requires a receipt.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Advance the task list from real tool execution

The task list is stuck at 0/8 because advancement depended on the broken capability binding. Make advancement reflect real tool execution so the panel shows progress and stops appearing forever-in-progress.

**Files:**
- Modify: `src/data_agent/agent/analysis_flow_controller.py` and/or `src/data_agent/agent/analysis_run_coordinator.py` (read first to locate the advancement function)
- Test: `tests/test_assurance_overlay_m1.py`

**Interfaces:**
- Produces: task advancement that increments when a tool executes against a plan step, independent of capability binding success.

- [ ] **Step 1: Locate the advancement function**

Grep `analysis_flow_controller.py` and `analysis_run_coordinator.py` for the function that marks a plan step complete / advances `任务 N/M`. Read it. Identify where it currently requires a successful `bind_tool_call_to_plan_step` result to advance.

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_assurance_overlay_m1.py
def test_task_advances_on_tool_execution_without_binding():
    """The task list advances when a tool executes against the active step,
    even when plan-step binding failed (analysis_step_not_found). Advancement
    must not depend on binding success."""
    # Build a minimal flow controller / coordinator per the real constructor
    # found in Step 1, with an 8-step plan and one executed run_python tool
    # whose binding result is ok=False, error_type="analysis_step_not_found".
    controller = _build_flow_controller_with_plan(steps=8)   # helper
    controller.record_tool_execution(tool="run_python", binding_ok=False, active_step="step_1")
    progress = controller.task_progress()   # returns "N/M"
    assert progress != "0/8"                # advanced on real execution
    assert int(progress.split("/")[0]) >= 1
```

(Adapt helper + method names to the real API from Step 1. Contract: advancement increments on tool execution regardless of binding outcome.)

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_assurance_overlay_m1.py::test_task_advances_on_tool_execution_without_binding -q`
Expected: FAIL — advancement currently gated on binding.

- [ ] **Step 4: Decouple advancement from binding**

In the advancement function found in Step 1: advance the active step when a tool executes against it (observed via the tool-binding diagnostic's `active_step` / plan progression), regardless of whether `bind_tool_call_to_plan_step` returned `ok`. Use the active-step tracker (first incomplete step in plan order). Mark a step complete when a tool has executed against it and produced a non-error result, then move the active pointer forward.

Do NOT touch `bind_tool_call_to_plan_step` itself — that is M2. This task only changes how *advancement* reacts to its output.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_assurance_overlay_m1.py::test_task_advances_on_tool_execution_without_binding -q`
Expected: PASS.

- [ ] **Step 6: Run flow regression tests**

Run: `uv run pytest tests/test_analysis_flow_tools.py tests/test_analysis_computation_transactions.py -q`
Expected: PASS; update assertions that assumed binding-gated advancement.

- [ ] **Step 7: Commit**

```bash
git add src/data_agent/agent/analysis_flow_controller.py src/data_agent/agent/analysis_run_coordinator.py tests/test_assurance_overlay_m1.py
git commit -m "$(cat <<'EOF'
fix: advance task list from real tool execution, not binding

Task advancement now increments when a tool executes against the active
plan step, independent of plan-step binding success. Fixes the task list
stuck at 0/8 and the panel refusing to collapse.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Render inline charts (fix blank Plotly in iframe)

The chart HTML's container is `height:100%`; inside the 450px iframe it collapses to 0 because the iframe `<body>` has no height. Inject `html,body{height:100%;margin:0}` so the chart fills the frame.

**Files:**
- Modify: `src/data_agent/web/static/js/app.js` (`injectChartPlotly`, ~:2443-2464)
- Validate: live (no unit test for JS rendering)

- [ ] **Step 1: Add the height fix to the chart iframe onload handler**

In `app.js` `injectChartPlotly`, at the top of the `try` block (right after `const doc = iframe.contentDocument;`), inject the sizing CSS before any other work:

```javascript
        injectChartPlotly(event) {
            const iframe = event.target;
            try {
                const doc = iframe.contentDocument;
                if (!doc) return;
                // Plotly chart containers use height:100%; the iframe body has no
                // height by default, so the chart collapses to 0 (blank). Give the
                // iframe document a full-height layout so the chart fills the frame.
                if (!doc.getElementById('da-chart-fill-height')) {
                    const style = doc.createElement('style');
                    style.id = 'da-chart-fill-height';
                    style.textContent = 'html,body{height:100%;margin:0;}';
                    doc.head.appendChild(style);
                }
                // ... existing logic (skip if plotly script present, inject plotly, etc.)
```

Leave the rest of the handler unchanged.

- [ ] **Step 2: Verify the JS parses**

Run: `uv run python scripts/run_analysis_release_gates.py --profile deterministic` — Gate A includes a `web_javascript_syntax` check.
Expected: that check PASS.

- [ ] **Step 3: Live-validate (in the M1 validation session, Task 7)**

Confirm the scatter plot renders inside the chat (not blank) while still opening correctly as a standalone artifact. (Captured in Task 7.)

- [ ] **Step 4: Commit**

```bash
git add src/data_agent/web/static/js/app.js
git commit -m "$(cat <<'EOF'
fix: render inline charts by sizing the chart iframe body

Plotly chart containers are height:100%; the iframe body had no height,
so inline charts collapsed to 0 (blank) while the standalone artifact
rendered fine. Inject html,body{height:100%} into chart iframes.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Workbench 当前分析 — keep only 结论

Per spec D9: the 当前分析 tab keeps only the conclusions (已确认) block; remove 仍不确定 / 建议下一步 / trust-basis / 确认门 / 分析范围 / 完整叙述 / 数据明细下钻. 产出与导出 unchanged.

**Files:**
- Modify: `src/data_agent/web/templates/index.html` (~:540-679, the 当前分析 tab content)

- [ ] **Step 1: Edit the template**

In `index.html`, within the 当前分析 tab (`x-show="sessionSidePanelTab === 'current'"`):

1. Keep the `行动看板` section but reduce it to **only** the 已确认 block (lines ~546-555) and rename the section heading `<h4>结论与下一步</h4>` (~:543) to `<h4>结论</h4>`.
2. Delete the 仍不确定 block (~:557-566), the 建议下一步 block (~:568-577), and the trust-basis line (~:579-583).
3. Delete the 确认门 section (~:587-595), the 分析范围 section (~:597-613), the 完整分析 section (~:615-625), and the 数据明细下钻 `<details>` (~:627-679).
4. Leave the 产出与导出 tab (~:537, :682+) completely unchanged.

Do not remove the Alpine.js data methods (`actionBoard()`, `workbenchScope()`, etc.) from `app.js` — only the template references are removed. Removing the methods is out of scope (workbench refactor is user-owned).

- [ ] **Step 2: Verify the template still has the kept and removed markers**

Run a quick grep check:

```bash
grep -c "action-board-confirmed" src/data_agent/web/templates/index.html   # expect 1 (kept)
grep -c "建议下一步\|完整叙述\|数据明细" src/data_agent/web/templates/index.html   # expect 0 (removed)
grep -c "产出与导出" src/data_agent/web/templates/index.html   # expect >=2 (unchanged)
```

- [ ] **Step 3: Run the web regression tests**

Run: `uv run pytest tests/test_web_overhaul.py tests/test_web_session_lifecycle.py -q`
Expected: PASS; update any assertion that referenced a removed `data-testid` (e.g. `action-board-uncertain`, `workbench-full-answer`, `workbench-breakdown`).

- [ ] **Step 4: Commit**

```bash
git add src/data_agent/web/templates/index.html tests/test_web_overhaul.py tests/test_web_session_lifecycle.py
git commit -m "$(cat <<'EOF'
feat(workbench): reduce 当前分析 panel to conclusions only

Per the recovery design, the 当前分析 tab now shows only 结论 (已确认).
Removed 仍不确定/建议下一步/trust-basis/确认门/分析范围/完整叙述/数据明细.
产出与导出 unchanged.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: M1 integration verification (offline + live)

**Files:** none (verification only)

- [ ] **Step 1: Full offline suite**

Run: `uv run pytest tests/ -q`
Expected: PASS (re-run any failures in isolation to rule out the known order-flakiness before treating as a regression).

- [ ] **Step 2: Deterministic release gates**

Run: `uv run python scripts/run_analysis_release_gates.py --profile deterministic`
Expected: `overall_status: PASS` (Gates A–D).

- [ ] **Step 3: Live A/B validation (requires the running web service)**

With the web service running, in a fresh session upload `workspace/inbox/最强砖块记录.xlsx` and ask: *"我想了解这份数据中，哪些因素是人均确认的显著影响因素 分析文件: 最强砖块记录.xlsx"*.

Confirm all of:
- The answer contains real numbers and conclusions (no `无法发布`, no `当前可追踪证据不足`).
- No `dataset_outside_current_task_scope` error; analysis is not truncated.
- No confirmation prompt hangs the flow on data prep.
- The scatter chart renders inline (not blank); opens correctly as artifact too.
- The task list advances past 0/8 and the panel collapses.
- The 当前分析 panel shows only 结论; 产出与导出 still works.

- [ ] **Step 4: Record the outcome**

If all pass, M1 is done — the project is stable and usable. If any fail, file the specific failure as a follow-up task (do not expand M1 scope silently). Commit a note in the session memory via the memory system if a non-obvious finding surfaces.

---

## Self-Review (completed)

- **Spec coverage:** M1-1/M1-2 → Task 1; M1-3 → Task 2; M1-4 → Task 3; M1-5 → Task 4; M1-6 → Task 5; M1-7 → Task 6; M1 acceptance → Task 7. All M1 items covered. (M2 = separate plan, written after M1 lands.)
- **Placeholders:** Tasks 2/3/4 begin with an explicit read step because the exact change point depends on the current code; each then has a concrete test + change contract. No "TBD/TODO/handle edge cases".
- **Type consistency:** `_render_transparent_publication` is the symbol produced by Phase 0 and consumed by Task 1; `task_progress()`, `record_tool_execution()` are named as the produced interface in Task 4 (to be matched to the real API in its Step 1).

## Out of scope for M1

- M2 (best-effort binding, projection, synthesis un-choke, audit annotation quality) — separate plan after M1.
- Removing dormant tiered/strict publication code — cleanup after M2.
- Broader workbench refactor — user-owned; only the Task 6 surgery here.
