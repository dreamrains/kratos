# Workbench Tabs Cleanup — Design

- **Date:** 2026-07-12
- **Status:** Approved (approach B + Tab 1 redesign)
- **Owner:** young
- **Related:** `docs/superpowers/specs/2026-07-09-workbench-action-board-design.md` (preceding work)

## Context

The web GUI's right-side **分析工作台 (Workbench)** currently has three tabs. User feedback: besides the outputs tab, the other two feel useless — one shows duplicated content when expanded and has a visually inconsistent first module; the other's purpose is incomprehensible. The user's instinct was to delete both non-output tabs.

Investigation corrected the framing:

- The three tabs' real labels are **当前分析 / 验证详情 / 产出与导出** (`index.html:536-538`). What the user called "推荐分析方向" and "用户反馈" are content blocks inside those tabs, not tab names.
- **Tab 1「当前分析」is NOT useless** — its first module is the **action board** (结论与下一步), the conclusion-first view deliberately rebuilt 2 days ago (commits `78c6aab` → `8bb1c8f`). The user's "duplication" and "style mismatch" complaints are real but are presentation problems, not a value problem.
- **Tab 2「验证详情」IS genuinely thin** — it surfaces a confirmation gate that is `clear` ~99% of the time and only lights up when the agent is blocked waiting on user input. The rest is verification counts that duplicate the action board's `trust_basis`.

The real problems are therefore: (1) data-level redundancy inside Tab 1, (2) inconsistent styling between the action board and the other sections, (3) Tab 2 being an inert shell most of the time.

## Goals

1. Remove the data-level duplication inside Tab 1 (same facts rendered 2–3×).
2. Unify the visual style of Tab 1's sections.
3. Delete Tab 2 as a standalone tab; preserve its two genuinely-useful pieces (分析范围 + 确认门) by merging them into Tab 1.
4. Remove the now-dead backend fields and their builders (no orphaned contract surface / tech debt).
5. Tab 3「产出与导出」unchanged.

## Non-goals

- Do **not** fold `scope`/`confirmation` into `action_board` or delete the `details` block entirely (that was approach C — rejected; marginal benefit not worth the extra contract churn).
- Do **not** change `route_capabilities`, `analysis_state`, or any runtime/write path. This is a read-only view-layer change end to end.
- Do **not** touch mobile workbench rendering (still desktop-only below `xl`; tracked as a pre-existing deferral).
- Do **not** redesign the outputs tab.

## Decisions (confirmed with user)

1. **Direction:** Keep & clean Tab 1; merge Tab 2's useful bits into Tab 1; delete the Tab 2 shell. Three tabs → two tabs.
2. **Backend cleanup aggressiveness:** Approach B — frontend redesign **plus** removal of the three now-unrendered backend fields and their builders, with contract tests updated. (Approach A = leave dead fields, rejected as tech debt. Approach C = also reshape `details` away, rejected as low ROI.)
3. **`full_answer` (查看完整分析):** Keep, but **rename to 「完整叙述（AI 原文）」** so it reads as "the agent's full narrative" rather than a duplicate of the structured conclusions. Stays collapsed by default.

## Current state (as of this commit)

Workbench panel: `web/templates/index.html:504-774`. Tab buttons `:535-539`.

**Tab 1「当前分析」** (`x-show="sessionSidePanelTab === 'current'"`) has three blocks:
- **action board** 「结论与下一步」 — `index.html:541-586`, `data-testid="action-board"`. Internal structure: 已确认 / 仍不确定 / 建议下一步 + trust-basis footer. Backed by `build_action_board` (`workbench_view.py:55-137`).
- **查看完整分析** (expandable) — `index.html:588-598`, `data-testid="workbench-full-answer"`. Renders `full_answer` (last assistant message) as markdown. Backed by `trust_view._latest_full_answer` (`trust_view.py:31-54`).
- **数据明细（下钻）** (collapsible `<details>`) — `index.html:600-690`, `data-testid="workbench-breakdown"`, containing four sub-sections:
  - `multifile-data-understanding` (`:604-629`)
  - `multifile-relationships` (`:631-648`)
  - `multifile-analysis-directions` (`:650-667`) ← **duplicate**
  - `multifile-answer-coverage` (`:669-688`) ← **duplicate**

**Tab 2「验证详情」** (`x-show="sessionSidePanelTab === 'details'"`) — `index.html:692-740`, `data-testid="workbench-details"`:
- 分析范围 (scope) — `:693-711`
- 确认与验证 (confirmation + verification) — `:713-726`
- 关系依据 (relationship evidence) — `:728-739`

**Tab 3「产出与导出」** — `index.html:742-772`. Unchanged.

JS accessors in `web/static/js/app.js`: `multifileWorkbench() :1227`, `actionBoard() :1231`, `fullAnswer() :1232`, `workbenchDetails() :1234`, `workbenchScope() :1238`, `workbenchConfirmation() :1242`, `workbenchVerification() :1246`, `multifileDataUnderstanding() :1250`, `multifileRelationships() :1254`, `multifileAnalysisDirections() :1258`, `multifileAnswerCoverage() :1262`. Tab state `sessionSidePanelTab: 'current'` at `:76`.

## Redundancy proofs (why these are safe to remove)

Both flagged duplicates are **the same data source rendered twice**, not independent summaries:

1. **Analysis Directions ≡ action board「建议下一步」.**
   - `_analysis_direction_section` (`workbench_view.py:197-220`) iterates `capabilities.executable + exploratory`.
   - `build_action_board` next_steps (`workbench_view.py:99-112`) iterates the **same** `capabilities.executable + exploratory`, **plus** `needed_confirmations`.
   - ⇒ The action board's 建议下一步 is a strict superset. Removing Analysis Directions loses nothing.

2. **Answer Coverage ≈ action board (confirmed/uncertain/trust_basis).**
   - Answer Coverage `covered_claims` = `evidence[:6]` high/medium (`workbench_view.py:239-247`) — same source as action board `confirmed` (`:70-91`).
   - Answer Coverage `limitations` (`:248`) — same as action board `uncertain` limitation items (`:93-94`).
   - Answer Coverage counts (evidence/verified/failed/status, `:227-238`) — all present in action board `trust_basis` (`:114-131`).
   - ⇒ Fully covered by the action board.

## Target design

### Tab 1「当前分析」(top → bottom)

1. **确认门 banner** *(conditional)* — `x-show="workbenchConfirmation().status === 'needs_confirmation'"`. Amber banner showing `question || blocking_reason`. Invisible unless the agent is blocked. Merged from old Tab 2.
2. **action board「结论与下一步」** — structure unchanged (已确认/仍不确定/建议下一步/信任依据). **Restyled** for typographic consistency (see Style unification). `data-testid="action-board"` retained.
3. **分析范围** — merged from old Tab 2 (`workbenchScope()`): goal + file list + reason. Rendered only when it has content (goal or files).
4. **完整叙述（AI 原文）** — formerly「查看完整分析」. **Renamed.** Collapsed by default (`expandedFullAnswer`), markdown-rendered. `data-testid="workbench-full-answer"` retained.
5. **数据明细（下钻）** — collapsible. Now contains:
   - Data Understanding (kept; `data-testid="multifile-data-understanding"`)
   - Relationships (kept; enriched — see below; `data-testid="multifile-relationships"`)
   - ~~Analysis Directions~~ removed
   - ~~Answer Coverage~~ removed

Relationships enrichment: the old Tab 2「关系依据」block (`:728-739`) rendered `relationship.evidence` + `relationship.uncertainties`. Fold this into the breakdown Relationships section as an expandable per-relationship detail so the deeper evidence is not lost.

### Tab 2「验证详情」 — DELETED

- Remove the tab button (`index.html:537`).
- Remove the entire `workbench-details` div (`index.html:692-740`).
- `'details'` is no longer a valid `sessionSidePanelTab` value.

### Tab 3「产出与导出」 — unchanged.

### Style unification

Today the action board uses heavier typography (block title `text-sm font-semibold` at `:544`; group labels `text-xs font-semibold uppercase` at `:548/559/570`) while the breakdown sub-sections use `h3 text-[11px] font-semibold uppercase tracking-wider` (`:606/633/652/671`). Unify to one hierarchy:

- **Block title** (one per major block: 结论与下一步, 分析范围, 完整叙述, 数据明细 summary): `text-sm font-semibold text-stone-700 dark:text-stone-300`.
- **Group/sub-section label** (已确认/仍不确定/建议下一步, and breakdown sub-section headers): `text-[11px] font-semibold text-stone-400 uppercase tracking-wider`.
- **Item rows** (`workbench-item`): one consistent padding + text size across action board and breakdown.

Concretely: change the action board's three group labels from `text-xs ... uppercase tracking-wider` to the `text-[11px]` form, and ensure `workbench-item` inside the action board matches the breakdown's. Minimal CSS; mostly Tailwind class alignment in the template. Keep `workbench-primary-section` (`app.css:368`) as-is (it only sets `scroll-margin-top`).

## Backend contract changes

`agent/workbench_view.py`:
- `build_multifile_workbench_view` (`:37-49`): drop the `analysis_directions` and `answer_coverage` keys. Returns only `{data_understanding, relationships}`.
- Delete `_analysis_direction_section` (`:197-220`).
- Delete `_answer_coverage_section` (`:223-249`).
- `_details_section` (`:252-295`): drop the `verification` sub-block (`:285-294`). `details` becomes `{scope, confirmation}`.
- `_flatten_limitations` (`:298-306`): keep — still used by `build_action_board` (`:93`).

`agent/trust_view.py`:
- `_has_workbench_content` (`:72-91`) currently reads `primary["answer_coverage"]` (`:77`), `primary.get("analysis_directions")` (`:86`), and `details["verification"]` (`:90`). These become KeyError / dead after the removals. Update:
  - Remove `coverage = primary["answer_coverage"]` (`:77`) and `coverage.get("evidence_count")` (`:87`). No replacement needed — the evidence-count signal is subsumed: `data_state == "data_loaded"` (`:73`) short-circuits to ready, and the action-board content check at `:80` (confirmed/uncertain/next_steps) covers the non-loaded fallback.
  - Remove `primary.get("analysis_directions")` (`:86`) — its signal is covered by `action.next_steps` (checked at `:80`).
  - Remove `details["verification"].get("status") != "not_run"` (`:90`) — verification status already lives in `action_board.trust_basis.verification_status`, and is not the primary ready-signal anyway.
  - Net: `_has_workbench_content` no longer touches the removed fields; add/keep a test asserting `status == "ready"` for a loaded session to guard the `status`-keyed UI.

`agent/trust_view.build_trust_view` (`:10-28`): no structural change — still returns `{status, session_id, updated_at, workbench}` where `workbench = {action_board, multifile_analysis, details, full_answer}`. Only `multifile_analysis` and `details` get slimmer.

**Final contract:**
```
workbench = {
  action_board: { confirmed, uncertain, next_steps, trust_basis },
  multifile_analysis: { data_understanding, relationships },   # was 4 keys
  details: { scope, confirmation },                            # was 3 keys
  full_answer: str | None,
}
```

## Frontend changes

`web/templates/index.html`:
- Tab buttons (`:535-539`): remove the 验证详情 button (`:537`). Two buttons remain.
- Add 确认门 banner at top of Tab 1 (conditional on `workbenchConfirmation().status === 'needs_confirmation'`).
- action board (`:541-586`): keep, apply style unification (group labels → `text-[11px] uppercase tracking-wider`; `workbench-item` sizing consistent).
- Insert 分析范围 section (port markup from `:693-711`) after the action board, gated on having content.
- full-answer section (`:588-598`): rename button text 「查看完整分析」→「完整叙述（AI 原文）」(and the expanded toggle label accordingly).
- breakdown (`:600-690`): delete the `multifile-analysis-directions` section (`:650-667`) and the `multifile-answer-coverage` section (`:669-688`). Enrich `multifile-relationships` (`:631-648`) with expandable `evidence` + `uncertainties` per relationship (port from `:731-735`).
- Delete the `workbench-details` div (`:692-740`).

`web/static/js/app.js`:
- Remove accessors `workbenchDetails() :1234`, `workbenchVerification() :1246`, `multifileAnalysisDirections() :1258`, `multifileAnswerCoverage() :1262`.
- `workbenchScope() :1238` and `workbenchConfirmation() :1242` currently route through `workbenchDetails()`; inline them to read `this.trustView.workbench.details.scope` / `.confirmation` directly (or keep a private helper) since `workbenchDetails` is being removed.
- `sessionSidePanelTab` (`:76`): default stays `'current'`; `'details'` is no longer set anywhere.

`web/static/css/app.css`:
- Only if inspection finds action-board-specific rules that diverge from `workbench-item`/section norms. Expected to be minimal (most styling is Tailwind utility classes in the template).

## Test changes

Contract/shape tests assert the fields being removed and must be updated (mechanical):

- `tests/test_multifile_workbench_view.py`
  - `test_multifile_workbench_view_has_four_user_value_sections` (`:70`): rename / change to assert the two remaining sections (`data_understanding`, `relationships`). Drop asserts at `:78-79` (`analysis_directions`, `answer_coverage` in the key set), `:81` (`analysis_directions[0].source`), `:82` (`answer_coverage.evidence_count`).
- `tests/test_trust_view.py`
  - Key-set assert (`:17-20`): remove `analysis_directions`, `answer_coverage`.
  - `test_trust_view_exposes_only_workbench_and_bounded_validation_details` (`:99`): the `details` key set assert (`:107-110`) drops `verification` → `{scope, confirmation}`.
  - `test_analysis_directions_are_suggestions_and_never_auto_submit` (`:104`): delete (the projection is gone; its intent — routes are suggestions, never auto-submit — is still enforced via `action_board.next_steps[*].auto_submit == False`, covered by `test_web_workbench_action_board`).
  - `answer_coverage` status assert (`:134`): remove.
- `tests/test_trust_inspector_api.py`
  - `:88` (`multifile_analysis.analysis_directions[0].auto_submit`) → remove.
  - `:89` (`details.verification.claim_count == 2`) → remove. (If the test's intent was "verification counts are surfaced", redirect the assertion to `action_board.trust_basis` which now holds those counts.)
- `tests/test_trust_inspector_ui.py`
  - `test_analysis_directions_are_read_only_suggestions` (`:54`): delete (HTML section removed).

**Plan-phase requirement:** before finalizing the plan, grep the full `tests/` tree for `analysis_directions`, `answer_coverage`, `workbenchVerification`, `workbenchDetails`, `multifileAnalysisDirections`, `multifileAnswerCoverage`, `data-testid="multifile-analysis-directions"`, `data-testid="multifile-answer-coverage"`, `data-testid="workbench-details"`, and `sessionSidePanelTab === 'details'` to catch any remaining references (e.g., in `test_web_workbench_action_board.py`, `test_web_workbench_replacement.py`, `test_web_overhaul.py`, `test_multifile_regressions.py` which also matched earlier greps). Update or delete each.

## File-by-file change list

| File | Change |
|---|---|
| `src/data_agent/web/templates/index.html` | Tab 1 restructure; delete Tab 2 button + div; remove 2 breakdown sub-sections; rename full-answer; enrich Relationships; style unify. |
| `src/data_agent/web/static/js/app.js` | Delete 4 accessors; reroute scope/confirmation reads; drop `'details'` tab value. |
| `src/data_agent/web/static/css/app.css` | Minor, only if divergent action-board rules found. |
| `src/data_agent/agent/workbench_view.py` | Drop `analysis_directions`+`answer_coverage` from multifile view; delete their builders; drop `verification` from `_details_section`. |
| `src/data_agent/agent/trust_view.py` | Update `_has_workbench_content` to not reference removed fields. |
| `tests/test_multifile_workbench_view.py` | Update section-count + field asserts. |
| `tests/test_trust_view.py` | Update key-set + details-set asserts; delete directions test; drop coverage assert. |
| `tests/test_trust_inspector_api.py` | Drop directions + verification asserts. |
| `tests/test_trust_inspector_ui.py` | Delete directions HTML test. |
| (other test files) | Per plan-phase grep, update any remaining references. |

## Out of scope / deferred

- Pre-existing deferrals from the action-board work (empty-state guard hardening in `actionBoard()`, mobile workbench, runtime `_execute_tools_parallel` contextvars race) — untouched.
- Approach C (collapse `details` into `action_board`) — explicitly rejected.
- Whether 分析范围 should be multifile-only — current design shows it whenever it has content; revisit if it feels noisy for single-file sessions.

## Risks & verification

- **Risk:** `_has_workbench_content` regression changes top-level `status` ("ready" vs "empty"), affecting any UI keyed off `trustView.status`. **Mitigation:** keep `data_state == "data_loaded"` and action_board content as the primary ready-signals (they already cover the practical cases); add/keep a test asserting `status == "ready"` for a loaded session.
- **Risk:** a contract test outside the four listed still references a removed field. **Mitigation:** the plan-phase full grep above.
- **Verification:** `uv run pytest tests/ -v` green; manual check in the web GUI that Tab 1 shows action board → 分析范围 → 完整叙述（AI 原文） → 数据明细（Data Understanding + Relationships only), Tab 2 is gone, outputs tab unchanged, and a session with `pending_confirmations` surfaces the confirmation banner.
