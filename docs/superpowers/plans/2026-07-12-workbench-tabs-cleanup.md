# Workbench Tabs Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove data-level duplication and style inconsistency in the Workbench「当前分析」tab, delete the inert「验证详情」tab, and merge its two useful pieces (分析范围 + 确认门) into「当前分析」— three tabs → two tabs, with the now-dead backend fields and their builders removed.

**Architecture:** Read-only view-layer change end to end. Backend: slim the `workbench` contract (`multifile_analysis` 4→2 keys, `details` 3→2 keys) in `workbench_view.py` and adapt `trust_view._has_workbench_content`. Frontend: restructure the `index.html` Workbench panel (remove Tab 2 + two duplicate breakdown sections; add confirmation banner + scope section; enrich Relationships; rename full-answer; unify label typography) and drop the dead JS accessors in `app.js`. Tests updated to match.

**Tech Stack:** Python 3 (pydantic), Flask, Alpine.js + Tailwind CSS in Jinja2 templates, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-07-12-workbench-tabs-cleanup-design.md`

## Global Constraints

- **Branch:** Work on a feature branch (e.g. `feat/workbench-tabs-cleanup`). The project's `CLAUDE.md` requires branching before committing on `main`.
- **Test command:** `uv run pytest tests/ -v` (single test: `uv run pytest tests/<file>::<test> -v`).
- **No runtime/write-path changes.** This plan touches only the read-only Workbench view model (`workbench_view.py`, `trust_view.py`) and the web frontend (`index.html`, `app.js`, `app.css`). Do NOT modify `route_capabilities.py`, `analysis_state.py`, `confirmation_policy.py`, or any tool/session persistence.
- **Chinese-language UI.** New user-facing strings are Simplified Chinese, matching existing tone.
- **`test_stage3c0b_evidence_replenishment_flow.py:39,94`** contains the string `"answer_coverage"` inside a route's `evidence_requirements` list — this is a **route-capability label, NOT the workbench field**. Do NOT touch this file.
- **Windows:** Use forward-slash paths; the repo runs on win32 with UTF-8.

## File Structure

| File | Responsibility | This plan |
|---|---|---|
| `src/data_agent/agent/workbench_view.py` | Builds the read-only `workbench` contract (action_board, multifile_analysis, details) | Slim multifile_analysis + details; delete 2 builders |
| `src/data_agent/agent/trust_view.py` | Wraps workbench + `full_answer`; computes top-level `status` | Update `_has_workbench_content` |
| `src/data_agent/web/templates/index.html` | Workbench panel DOM (3 tabs) | Restructure Tab 1; delete Tab 2; rename; style unify |
| `src/data_agent/web/static/js/app.js` | Alpine accessors over `trustView.workbench` | Delete 4 dead accessors; reroute 2 |
| `src/data_agent/web/static/css/app.css` | Workbench CSS | No change expected (verify only) |
| `tests/test_multifile_workbench_view.py` | Shape tests for multifile + action board | Update to 2-section contract |
| `tests/test_trust_view.py` | Shape + behavior tests for trust view | Update sets; replace directions test |
| `tests/test_trust_inspector_api.py` | `/trust` endpoint contract | Redirect 2 asserts to action_board |
| `tests/test_multifile_regressions.py` | Regression: details shape | Drop verification block |
| `tests/test_trust_inspector_ui.py` | HTML/JS string asserts | Rewrite for 2-tab, 2-section layout |
| `tests/test_web_workbench_replacement.py` | HTML/JS string asserts | Rewrite for new layout |
| `tests/test_web_overhaul.py` | Workbench wording asserts | Drop `workbenchDetails` + `关系依据` asserts |

---

### Task 1: Slim the backend `workbench` contract

**Files:**
- Modify: `src/data_agent/agent/workbench_view.py:37-49`, `:197-249`, `:252-295`
- Modify: `src/data_agent/agent/trust_view.py:72-91`
- Test: `tests/test_multifile_workbench_view.py:70-115`
- Test: `tests/test_trust_view.py:15-20`, `:65-71`, `:104-134`
- Test: `tests/test_trust_inspector_api.py:88-89`
- Test: `tests/test_multifile_regressions.py:144-150`

**Interfaces:**
- Consumes: `build_route_capabilities(state)` (unchanged source of route proposals), `build_analysis_scope_plan`, `build_user_data_brief`.
- Produces: a slimmer `workbench` dict. New contract:
  ```
  workbench = {
    action_board: { confirmed, uncertain, next_steps, trust_basis },   # unchanged
    multifile_analysis: { data_understanding, relationships },          # was 4 keys
    details: { scope, confirmation },                                   # was 3 keys
    full_answer: str | None,                                            # unchanged
  }
  ```
  `build_action_board` is unchanged and remains the single home for next_steps (incl. `auto_submit: False`) and trust_basis counts.

- [ ] **Step 1: Update the shape/contract tests to the new contract (they will fail against current code)**

  In `tests/test_multifile_workbench_view.py`, replace `test_multifile_workbench_view_has_four_user_value_sections` (lines 70-88) with:

  ```python
  def test_multifile_workbench_view_has_data_and_relationship_sections():
      from data_agent.agent.workbench_view import build_multifile_workbench_view

      view = build_multifile_workbench_view(_state_with_multifile_context())

      assert set(view) == {"data_understanding", "relationships"}
      assert view["relationships"][0]["evidence"] == ["shared user_id"]
      assert view["relationships"][0]["uncertainties"] == ["different time windows"]
      assert view["relationships"][0]["diagnostic_only"] is True
      rendered = json.dumps(view, ensure_ascii=False)
      assert "artifact_path" not in rendered
      assert "scheduler" not in rendered.lower()
  ```

  In the same file, in `test_trust_view_exposes_only_workbench_and_bounded_validation_details` (lines 107-111), change the `details` key-set assertion to:

  ```python
      assert set(view["workbench"]["details"]) == {"scope", "confirmation"}
  ```

  In `tests/test_trust_view.py`:
  - Lines 15-20: change the `multifile_analysis` key-set assertion to:
    ```python
      assert set(view["workbench"]["multifile_analysis"]) == {
          "data_understanding",
          "relationships",
      }
    ```
  - Lines 65-71: delete the `details["verification"] == {...}` assertion block (the 6 lines starting `assert details["verification"] == {`). Keep lines 60-64 (scope/confirmation) and 72-75 (no-leak asserts).
  - Replace `test_analysis_directions_are_suggestions_and_never_auto_submit` (lines 104-125) with a version pointed at the action board:
    ```python
    def test_action_board_next_steps_are_suggestions_and_never_auto_submit() -> None:
        state = AnalysisSessionState(session_id="directions", data_state="data_loaded")
        state.active_scope.update({"active_dataset": "orders", "active_mode": "data_loaded"})
        state.dataset_contracts = [{
            "id": "duc_orders",
            "dataset": "orders",
            "field_roles": {"date": ["date"], "metrics": ["gmv"]},
            "quality_status": "ready",
        }]
        state.route_proposals = [{
            "id": "route_trend",
            "dataset": "orders",
            "direction": "trend",
            "label": "GMV trend",
            "reason": "Date and GMV are available.",
            "evidence_requirements": ["daily GMV"],
        }]

        next_steps = build_trust_view(state)["workbench"]["action_board"]["next_steps"]

        assert next_steps
        route_steps = [n for n in next_steps if n.get("kind") == "route"]
        assert route_steps
        assert all(n.get("auto_submit") is False for n in route_steps)
    ```
  - Line 134: delete `assert view["workbench"]["multifile_analysis"]["answer_coverage"]["status"] == "not_started"`. Keep line 133 (`assert view["status"] == "ready"`).

  In `tests/test_trust_inspector_api.py`, replace lines 88-89 with:
  ```python
      next_steps = payload["workbench"]["action_board"]["next_steps"]
      assert next_steps
      assert all(n.get("auto_submit") is False for n in next_steps if n.get("kind") == "route")
      assert payload["workbench"]["action_board"]["trust_basis"]["verified_claim_count"] == 2
  ```

  In `tests/test_multifile_regressions.py`, delete lines 144-150 (the `assert view["workbench"]["details"]["verification"] == { ... }` block). Keep lines 137-143 (status + scope asserts).

- [ ] **Step 2: Run the tests to verify they fail**

  Run: `uv run pytest tests/test_multifile_workbench_view.py tests/test_trust_view.py tests/test_trust_inspector_api.py tests/test_multifile_regressions.py -v`
  Expected: FAILURES — `KeyError: "analysis_directions"` / `"answer_coverage"` / `"verification"`, and set-mismatch assertion errors. (The `test_action_board_next_steps_are_suggestions...` may already pass — that's fine.)

- [ ] **Step 3: Slim `build_multifile_workbench_view` and delete the two dead builders**

  In `src/data_agent/agent/workbench_view.py`, replace `build_multifile_workbench_view` (lines 37-49) with:

  ```python
  def build_multifile_workbench_view(
      state: Any,
      *,
      capabilities: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
      """Build a read-only Workbench model from existing state.

      Sections: data understanding + relationships. Analysis directions live in
      the action board (next_steps); answer coverage lives in the action board
      (confirmed / uncertain / trust_basis).
      """
      return {
          "data_understanding": _data_understanding_section(state),
          "relationships": _relationship_section(state),
      }
  ```

  Delete the entire `_analysis_direction_section` function (lines 197-220) and the entire `_answer_coverage_section` function (lines 223-249). Leave `_flatten_limitations` (it is still used by `build_action_board`).

- [ ] **Step 4: Drop `verification` from `_details_section`**

  In `src/data_agent/agent/workbench_view.py`, replace `_details_section` (lines 252-295) with:

  ```python
  def _details_section(
      state: Any,
      scope_plan: dict[str, Any],
      confirmation: dict[str, Any],
  ) -> dict[str, Any]:
      file_decisions = _list_items(scope_plan.get("file_decisions"))
      return {
          "scope": {
              "goal": _text(scope_plan.get("goal")) or _text(getattr(state, "goal", "")),
              "status": _text(scope_plan.get("scope_status")) or "ready",
              "files": [
                  {
                      "file_id": _text(item.get("file_id")),
                      "dataset": _text(item.get("dataset")),
                      "filename": _text(item.get("filename")),
                      "assignment": _text(item.get("assignment")),
                      "eligibility": _text(item.get("eligibility")),
                      "reason": _text(item.get("reason")),
                      "task_count": len(item.get("task_refs") or [])
                      if isinstance(item.get("task_refs"), list)
                      else 0,
                  }
                  for item in file_decisions
              ],
              "notes": _text_list(scope_plan.get("notes")),
          },
          "confirmation": {
              "status": _text(confirmation.get("status")) or "clear",
              "question": _text(confirmation.get("question")),
              "blocking_reason": _text(confirmation.get("blocking_reason")),
          },
      }
  ```

- [ ] **Step 5: Update `_has_workbench_content` to not reference removed fields**

  In `src/data_agent/agent/trust_view.py`, replace `_has_workbench_content` (lines 72-91) with:

  ```python
  def _has_workbench_content(state: Any, workbench: dict[str, Any]) -> bool:
      if _text(getattr(state, "data_state", "")) == "data_loaded":
          return True
      primary = workbench["multifile_analysis"]
      understanding = primary["data_understanding"]
      details = workbench["details"]
      action = workbench.get("action_board") or {}
      if action.get("confirmed") or action.get("uncertain") or action.get("next_steps"):
          return True
      return bool(
          understanding.get("datasets")
          or understanding.get("quality_findings")
          or primary.get("relationships")
          or details["scope"].get("files")
          or details["confirmation"].get("status") == "needs_confirmation"
      )
  ```

- [ ] **Step 6: Run the tests to verify they pass**

  Run: `uv run pytest tests/test_multifile_workbench_view.py tests/test_trust_view.py tests/test_trust_inspector_api.py tests/test_multifile_regressions.py -v`
  Expected: ALL PASS.

- [ ] **Step 7: Run the full suite to catch any other reference**

  Run: `uv run pytest tests/ -v`
  Expected: FAILURES only in the **frontend** test files (`test_trust_inspector_ui.py`, `test_web_workbench_replacement.py`, `test_web_overhaul.py`) — these assert the old HTML/JS and are fixed in Task 2. All non-frontend tests must PASS. If any non-frontend test fails, grep for `analysis_directions|answer_coverage|details.verification|workbenchVerification` and fix before proceeding.

- [ ] **Step 8: Commit**

  ```bash
  git checkout -b feat/workbench-tabs-cleanup
  git add src/data_agent/agent/workbench_view.py src/data_agent/agent/trust_view.py \
          tests/test_multifile_workbench_view.py tests/test_trust_view.py \
          tests/test_trust_inspector_api.py tests/test_multifile_regressions.py
  git commit -m "refactor(workbench): drop analysis_directions/answer_coverage/verification from contract

  analysis_directions duplicated action_board.next_steps and answer_coverage
  duplicated action_board confirmed/uncertain/trust_basis. details.verification
  duplicated trust_basis counts. Remove the fields, their builders, and update
  contract tests. Frontend consumers updated in the next commit.

  Co-Authored-By: Claude <noreply@anthropic.com>"
  ```

---

### Task 2: Restructure the Workbench frontend (3 tabs → 2 tabs)

**Files:**
- Modify: `src/data_agent/web/templates/index.html:535-539` (tab buttons), `:542-586` (action board labels), insert after `:586` (confirmation banner + scope), `:589-598` (rename full-answer), `:631-648` (enrich relationships), delete `:650-688` (two breakdown sections), delete `:692-740` (Tab 2)
- Modify: `src/data_agent/web/static/js/app.js:1234-1248`, `:1258-1264` (accessors)
- Test: `tests/test_trust_inspector_ui.py`
- Test: `tests/test_web_workbench_replacement.py`
- Test: `tests/test_web_overhaul.py:646-661`

**Interfaces:**
- Consumes: the Task 1 slimmed `workbench` contract (`action_board`, `multifile_analysis.{data_understanding,relationships}`, `details.{scope,confirmation}`, `full_answer`).
- Produces: a two-tab Workbench (当前分析 / 产出与导出). Tab 1 「当前分析」 renders, top-to-bottom: conditional 确认门 banner → action board → 分析范围 → 完整叙述（AI 原文） → 数据明细下钻 (Data Understanding + Relationships only).

- [ ] **Step 1: Update the frontend tests to the target layout (they will fail against current HTML/JS)**

  In `tests/test_trust_inspector_ui.py`:
  - Replace `test_workbench_has_exactly_five_primary_sections` (lines 20-27) with:
    ```python
    def test_workbench_has_expected_primary_sections() -> None:
        html = _index_html()

        # action-board + workbench-scope + data-understanding + relationships
        assert html.count("workbench-primary-section") == 4
        assert 'data-testid="action-board"' in html
        assert 'data-testid="workbench-scope"' in html
        assert 'data-testid="multifile-data-understanding"' in html
        assert 'data-testid="multifile-relationships"' in html
        assert 'data-testid="multifile-analysis-directions"' not in html
        assert 'data-testid="multifile-answer-coverage"' not in html
    ```
  - Replace `test_primary_sections_surface_quality_constraints_and_answer_limits` (lines 30-35) with:
    ```python
    def test_primary_sections_surface_quality_constraints_and_limitations() -> None:
        html = _index_html()

        assert "multifileDataUnderstanding().quality_findings" in html
        assert "multifileDataUnderstanding().analysis_constraints" in html
        # limitations now surface inside the action board's uncertain block
        assert 'data-testid="action-board-uncertain"' in html
    ```
  - Replace `test_validation_details_are_secondary_and_bounded` (lines 38-51) with:
    ```python
    def test_workbench_does_not_leak_internal_ids_or_dead_helpers() -> None:
        html = _index_html()
        js = _app_js()

        assert "task_refs" not in html
        assert "evidence_signature" not in html
        assert "sessionSidePanelTab === 'details'" not in html
        assert "workbenchDetails()" not in js
        assert "workbenchVerification()" not in js
        assert "multifileAnalysisDirections()" not in js
        assert "multifileAnswerCoverage()" not in js
    ```
  - Delete `test_analysis_directions_are_read_only_suggestions` (lines 54-64) entirely.
  - In `test_workbench_empty_states_hide_during_loading_or_error` (lines 92-105), remove the `"No analysis direction yet.",` line from the `for label in (...)` tuple (keep the other two labels).
  - Leave `test_legacy_trust_and_history_surfaces_are_removed`, `test_artifact_links_do_not_render_raw_paths_as_text`, `test_workbench_helpers_read_only_the_current_contract`, and `test_workbench_css_contract_remains_responsive_and_readable` unchanged.

  In `tests/test_web_workbench_replacement.py`:
  - In `test_current_panel_uses_multifile_workbench_as_primary_surface` (lines 15-22): change `assert html.count("workbench-primary-section") == 5` to `== 4`, and delete the two lines asserting `"multifile-analysis-directions"` and `"multifile-answer-coverage"` (keep data-understanding + relationships).
  - In `test_multifile_workbench_helpers_read_new_view_model` (lines 35-43): delete the two lines `assert "multifileAnalysisDirections()" in js` and `assert "multifileAnswerCoverage()" in js`.
  - Replace `test_secondary_details_support_validation_without_legacy_history_routes` (lines 46-57) with:
    ```python
    def test_workbench_keeps_validation_helpers_without_legacy_history_routes():
        html = _index_html()
        js = _app_js()

        assert "workbenchScope()" in js
        assert "workbenchConfirmation()" in js
        assert "sessionSidePanelTab === 'details'" not in html
        assert "workbenchDetails()" not in js
        assert "workbenchVerification()" not in js
        assert "trustView.history" not in html
        assert "selectTrustRoute" not in js
        assert "historyRoutes" not in html
    ```
  - Replace `test_four_sections_demoted_to_drill_down` (lines 87-97) with:
    ```python
    def test_two_sections_in_drill_down():
        html = _index_html()
        assert 'data-testid="workbench-breakdown"' in html
        for testid in ("multifile-data-understanding", "multifile-relationships"):
            assert f'data-testid="{testid}"' in html
        assert 'data-testid="multifile-analysis-directions"' not in html
        assert 'data-testid="multifile-answer-coverage"' not in html
    ```

  In `tests/test_web_overhaul.py`, in `test_sidebar_uses_assignment_scope_and_nonblocking_relationship_diagnostics` (lines 653-661): delete the line `assert "workbenchDetails()" in js`, and change the line `assert "关系依据" in html` to `assert "multifile-relationships" in html`. Leave the other lines (`workbenchScope().files`, `relationship.evidence`, `relationship.uncertainties`, `diagnostic_only`/`关系待确认`/`等待确认` not in html) unchanged.

- [ ] **Step 2: Run the frontend tests to verify they fail**

  Run: `uv run pytest tests/test_trust_inspector_ui.py tests/test_web_workbench_replacement.py tests/test_web_overhaul.py -v`
  Expected: FAILURES (assertions on removed/renamed elements).

- [ ] **Step 3: Remove the 验证详情 tab button**

  In `src/data_agent/web/templates/index.html`, delete line 537 (the 验证详情 button). The tab-button block becomes two buttons:
  ```html
  <div class="session-side-tabs">
      <button type="button" class="session-side-tab" :class="{ 'is-active': sessionSidePanelTab === 'current' }" @click="sessionSidePanelTab = 'current'">当前分析</button>
      <button type="button" class="session-side-tab" :class="{ 'is-active': sessionSidePanelTab === 'outputs' }" @click="sessionSidePanelTab = 'outputs'">产出与导出</button>
  </div>
  ```

- [ ] **Step 4: Unify action-board group label typography**

  In the action-board section (`index.html:542-586`), there are three group-label divs (已确认 at ~548, 仍不确定 at ~559, 建议下一步 at ~570). Each currently has class `text-xs font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider`. Change all three to:
  ```html
  text-[11px] font-semibold text-stone-400 uppercase tracking-wider
  ```
  (This matches the breakdown sub-section `h3` style at lines 606/633, giving a single label hierarchy. Leave the block title `结论与下一步` at line 544 as `text-sm font-semibold`.)

- [ ] **Step 5: Insert the confirmation banner and 分析范围 section after the action board**

  In `src/data_agent/web/templates/index.html`, immediately after the action-board `</section>` (line 586) and before the `<!-- 完整分析（可展开） -->` comment (line 588), insert:

  ```html
            <!-- 确认门（仅当 agent 阻塞等待确认时显示） -->
            <section class="trust-section" data-testid="workbench-confirmation-banner"
                     x-show="sessionSidePanelTab === 'current' && workbenchConfirmation().status === 'needs_confirmation'">
              <div class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-3 py-2">
                <div class="text-[11px] font-semibold text-amber-700 dark:text-amber-300 uppercase tracking-wider mb-1">需确认</div>
                <p class="text-xs text-amber-800 dark:text-amber-200"
                   x-text="workbenchConfirmation().question || workbenchConfirmation().blocking_reason"></p>
              </div>
            </section>

            <!-- 分析范围 -->
            <section class="trust-section workbench-primary-section" data-testid="workbench-scope"
                     x-show="sessionSidePanelTab === 'current' && (workbenchScope().goal || (workbenchScope().files && workbenchScope().files.length))">
              <h4 class="text-sm font-semibold text-stone-700 dark:text-stone-300">分析范围</h4>
              <p x-show="workbenchScope().goal" class="text-xs text-stone-600 dark:text-stone-300 mt-1 mb-1.5" x-text="workbenchScope().goal"></p>
              <div class="space-y-1.5 mt-1">
                <template x-for="(file, fi) in (workbenchScope().files || [])" :key="file.file_id || fi">
                  <div class="workbench-item">
                    <div class="flex items-center justify-between gap-2">
                      <p class="text-xs font-medium text-stone-700 dark:text-stone-300 truncate" x-text="file.dataset || file.filename || file.file_id"></p>
                      <span class="text-[10px] text-stone-400" x-text="trustStatusLabel(file.assignment || file.eligibility || 'unknown')"></span>
                    </div>
                    <p x-show="file.reason" class="text-[10px] text-stone-500 dark:text-stone-400 mt-1" x-text="file.reason"></p>
                  </div>
                </template>
              </div>
            </section>
  ```

- [ ] **Step 6: Rename the full-answer block**

  In the full-answer section (`index.html:589-598`), change the button label expression at line 592 from:
  ```html
  <span x-text="expandedFullAnswer ? '收起完整分析' : '查看完整分析'"></span>
  ```
  to:
  ```html
  <span x-text="expandedFullAnswer ? '收起完整叙述' : '完整叙述（AI 原文）'"></span>
  ```

- [ ] **Step 7: Enrich the Relationships breakdown section with evidence + uncertainties**

  In the `multifile-relationships` section (`index.html:631-648`), inside the `workbench-item` div, after the existing value/risk `<p>` (line 643), add two lines:
  ```html
                            <p x-show="relationship.evidence && relationship.evidence.length" class="text-[10px] text-stone-500 dark:text-stone-400 mt-1" x-text="'依据：' + relationship.evidence.join('；')"></p>
                            <p x-show="relationship.uncertainties && relationship.uncertainties.length" class="text-[10px] text-amber-600 dark:text-amber-300 mt-1" x-text="'不确定性：' + relationship.uncertainties.join('；')"></p>
  ```

- [ ] **Step 8: Delete the two duplicate breakdown sections**

  In `src/data_agent/web/templates/index.html`, delete the entire `multifile-analysis-directions` section (lines 650-667) and the entire `multifile-answer-coverage` section (lines 669-688). The breakdown `<details>` now contains only Data Understanding + Relationships.

- [ ] **Step 9: Delete the entire Tab 2 (验证详情) block**

  In `src/data_agent/web/templates/index.html`, delete lines 692-740 — the whole `<div data-testid="workbench-details" x-show="sessionSidePanelTab === 'details'" ...>...</div>` block (分析范围 + 确认与验证 + 关系依据). Its useful content (scope, confirmation, relationship evidence) has been merged into Tab 1 in Steps 5 and 7.

- [ ] **Step 10: Remove dead JS accessors and reroute scope/confirmation**

  In `src/data_agent/web/static/js/app.js`, replace lines 1234-1248 (the `workbenchDetails`, `workbenchScope`, `workbenchConfirmation`, `workbenchVerification` accessors) with:
  ```js
        workbenchScope() {
            return this.trustView?.workbench?.details?.scope || {};
        },

        workbenchConfirmation() {
            return this.trustView?.workbench?.details?.confirmation || {};
        },
  ```
  (This deletes `workbenchDetails` and `workbenchVerification`, and reroutes scope/confirmation to read `details` directly.)

  Then delete the `multifileAnalysisDirections` accessor (lines 1258-1260) and the `multifileAnswerCoverage` accessor (lines 1262-1264).

- [ ] **Step 11: Run the frontend tests to verify they pass**

  Run: `uv run pytest tests/test_trust_inspector_ui.py tests/test_web_workbench_replacement.py tests/test_web_overhaul.py -v`
  Expected: ALL PASS.

- [ ] **Step 12: Run the full suite**

  Run: `uv run pytest tests/ -v`
  Expected: ALL PASS. (If `test_web_workbench_action_board.py` or others fail on a removed string, grep `tests/` for the failing token and update.)

- [ ] **Step 13: Commit**

  ```bash
  git add src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js \
          tests/test_trust_inspector_ui.py tests/test_web_workbench_replacement.py tests/test_web_overhaul.py
  git commit -m "feat(workbench): two-tab workbench, merge scope+confirmation into 当前分析

  Delete the 验证详情 tab and the two duplicate breakdown sections
  (analysis-directions = action_board next_steps; answer-coverage = action_board
  confirmed/uncertain/trust_basis). Merge 分析范围 and a conditional 确认门 banner
  into 当前分析, fold relationship evidence into the Relationships drill-down,
  rename 查看完整分析 -> 完整叙述（AI 原文）, and unify group-label typography.
  Drop the four now-dead JS accessors.

  Co-Authored-By: Claude <noreply@anthropic.com>"
  ```

---

### Task 3: Full verification and memory update

**Files:**
- Verify: full test suite, web GUI
- Update: `C:\Users\duguy\.claude\projects\D--Project-Daily-data-agent\memory\workbench-action-board.md`

**Interfaces:** None (verification + docs).

- [ ] **Step 1: Run the complete test suite**

  Run: `uv run pytest tests/ -v`
  Expected: ALL PASS. Note any order-dependent flakiness (per existing memory `test-suite-order-dependent-flakiness`) — re-run the failing test in isolation to distinguish real failures from the known flakiness.

- [ ] **Step 2: Manual GUI verification**

  Start the web GUI: `python -m data_agent.web.entry` (port 5001). Open a session that has run analysis. Confirm:
  - The Workbench has exactly **two** tabs: 当前分析 / 产出与导出.
  - 当前分析 shows, in order: action board (结论与下一步) → 分析范围 → 完整叙述（AI 原文，collapsed) → 数据明细（下钻，collapsible, contains only Data Understanding + Relationships).
  - Expanding 完整叙述 renders markdown; the conclusions are NOT duplicated elsewhere (no Analysis Directions / Answer Coverage blocks).
  - The action-board group labels (已确认 / 仍不确定 / 建议下一步) visually match the breakdown sub-section headers.
  - 产出与导出 is unchanged (export buttons + artifacts list).
  - (If available) a session with a pending confirmation shows the amber 需确认 banner at the top of 当前分析.

- [ ] **Step 3: Update the workbench memory**

  Update `C:\Users\duguy\.claude\projects\D--Project-Daily-data-agent\memory\workbench-action-board.md`: append a short note that the 验证详情 tab was removed and scope/confirmation merged into 当前分析; `multifile_analysis` is now `{data_understanding, relationships}` and `details` is now `{scope, confirmation}` (analysis_directions / answer_coverage / details.verification removed). Keep the deferred-follow-ups list.

- [ ] **Step 4: Commit memory/docs if tracked**

  The memory file lives outside the repo (user Claude dir) — no repo commit needed for it. If the spec/plan are to be committed, they were already staged with their respective tasks or can be committed now:
  ```bash
  git add docs/superpowers/specs/2026-07-12-workbench-tabs-cleanup-design.md \
          docs/superpowers/plans/2026-07-12-workbench-tabs-cleanup.md
  git commit -m "docs(workbench): spec + plan for tabs cleanup

  Co-Authored-By: Claude <noreply@anthropic.com>"
  ```

---

## Self-Review (completed during authoring)

- **Spec coverage:** Every spec section maps to a task — backend contract changes → Task 1; frontend restructure (Tab 1 layout, Tab 2 deletion, style unification, full-answer rename, Relationships enrichment) → Task 2; verification + memory → Task 3. The spec's "Plan-phase requirement" grep was performed and its findings (7 test files, incl. `test_web_overhaul.py`, `test_multifile_regressions.py`) are incorporated.
- **Placeholder scan:** No TBD/TODO. Every code step shows the exact target code.
- **Type/name consistency:** `workbenchScope()` / `workbenchConfirmation()` keep the same names (callers in `index.html` unchanged except new usages); the four deleted accessors (`workbenchDetails`, `workbenchVerification`, `multifileAnalysisDirections`, `multifileAnswerCoverage`) are removed from both JS and all tests. New testids `workbench-scope`, `workbench-confirmation-banner` are asserted in Task 2 Step 1. The `workbench-primary-section` count is consistently 4 across both test files (Task 2 Step 1).
