# Workbench UI Consistency Design

- **Date:** 2026-07-13
- **Status:** Approved
- **Scope:** Workbench right-side panel, desktop web UI only

## Goal

Resolve four user-visible inconsistencies in the Workbench:

1. The two remaining tabs must fill the available tab-strip width equally.
2. The action board in **当前分析** must use the same typography, colour hierarchy, spacing, and card treatment as the established **数据明细（下钻）** and **产出与导出** surfaces.
3. The current-analysis sections must no longer look like a separate, older UI system from the drill-down sections.
4. User-facing, known English system values in **当前分析** must have Chinese labels.

## Chosen Approach

Use a focused frontend normalization rather than restructure the Workbench data contract.

- Change `.session-side-tabs` from three equal columns to two equal columns.
- Retain the current action-board data structure and its existing empty-state safety shape.
- Apply one visual hierarchy throughout the current-analysis tab:
  - major section title: `text-sm font-semibold text-stone-700 dark:text-stone-300`;
  - group title: `text-[11px] font-semibold text-stone-400 uppercase tracking-wider`;
  - card title: `text-xs font-medium text-stone-700 dark:text-stone-300`;
  - card support/meta text: `text-[10px] text-stone-500 dark:text-stone-400`;
  - use the existing `.workbench-item` padding, radius, border, and vertical rhythm for every current-analysis card.
- Add small client-side formatters for the known machine-facing values rendered by the action board. Mappings cover confidence (`high`, `medium`), analysis routes (`trend`, `period_compare`, `correlation`, `rate_analysis`), data state (`data_gap`), verification state (`not_run`), and the existing known risk messages. Unknown copy falls back to the original string so that new backend values remain visible rather than being incorrectly translated.
- Use the formatters only for user-facing presentation. The backend payload and test IDs remain unchanged.

## Alternatives Considered

1. **CSS-only tab fix:** fastest, but leaves the raw English values and the visual mismatch intact.
2. **Focused frontend normalization (chosen):** fixes all four concerns without changing read-model contracts or agent runtime behavior.
3. **Workbench template and view-model rewrite:** could consolidate more markup, but has a disproportionate regression surface for a presentation-only request.

## Boundaries

- Do not change Workbench API shape, action-board generation, analysis routing, verification semantics, or exported artifact behavior.
- Do not translate free-form model answers, evidence claims, or file names; only translate known UI/system values.
- Do not alter the established outputs-tab information architecture.
- Mobile Workbench behavior remains outside this desktop-only adjustment.

## Acceptance Criteria

- The two Tab buttons each occupy half of the tab strip.
- Action-board headings, group labels, cards, metadata, and spacing match the current drill-down/outputs hierarchy.
- The screenshot examples display Chinese labels for the two data-gap messages, `data_gap`, the four shown route names, confidence labels, and `not_run`.
- New or unknown backend text remains readable through original-text fallback.
- Existing Workbench HTML/JS contract tests and the full test suite remain green.
