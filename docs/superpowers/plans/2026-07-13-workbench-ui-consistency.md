# Workbench UI Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the two Workbench tabs fill the tab strip, visually align the current-analysis surface with drill-down and outputs, and localize known system-facing current-analysis copy.

**Architecture:** This is a frontend-only presentation change. The template calls one new JavaScript formatter for known raw values, retaining the backend action-board contract and falling back to original text for unrecognized values. CSS changes only the stale three-column tab layout; markup utilities align action-board text and spacing to existing drill-down cards.

**Tech Stack:** Flask/Jinja2 templates, Alpine.js, static CSS, pytest, uv.

## Global Constraints

- Work only in the Workbench template, JavaScript helpers, CSS, and static UI regression tests.
- Preserve `actionBoard()`'s complete pre-load empty shape and every existing `data-testid`.
- Do not translate free-form model answers, evidence claims, dataset names, file names, or unknown backend values.
- Run the targeted regression test and `uv run pytest tests/ -q` before committing implementation.

---

### Task 1: Lock the corrected desktop UI contract with a failing regression test

**Files:**
- Modify: `tests/test_web_workbench_replacement.py`
- Reads: `src/data_agent/web/templates/index.html`, `src/data_agent/web/static/js/app.js`, `src/data_agent/web/static/css/app.css`

**Interfaces:**
- Consumes: static Workbench sources.
- Produces: source-contract coverage for two tab columns, formatter use in action-board markup, current-tab labels, and formatter mappings.

- [ ] **Step 1: Add a CSS reader and the failing UI contract test**

```python
def _app_css() -> str:
    return (ROOT / "src/data_agent/web/static/css/app.css").read_text(encoding="utf-8")


def test_current_analysis_uses_two_equal_tabs_unified_cards_and_chinese_system_labels():
    html = _index_html()
    js = _app_js()
    css = _app_css()

    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "formatWorkbenchText(c.confidence, 'confidence')" in html
    assert "formatWorkbenchText(u.label, 'risk')" in html
    assert "formatWorkbenchText(u.reason, 'kind')" in html
    assert "formatWorkbenchText(n.direction, 'route')" in html
    assert "formatWorkbenchText(n.kind, 'kind')" in html
    assert "formatWorkbenchText(actionBoard().trust_basis.verification_status || 'not_run', 'verification')" in html
    assert ">数据理解<" in html
    assert ">数据关系<" in html
    assert "暂无数据理解摘要。" in html
    assert "暂无数据关系信息。" in html
    assert "formatWorkbenchText(value, category = '')" in js
    for translation in ("高置信度", "中等置信度", "趋势分析", "周期对比", "相关性分析", "比率分析", "数据缺口", "尚未验证"):
        assert translation in js
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
uv run pytest tests/test_web_workbench_replacement.py::test_current_analysis_uses_two_equal_tabs_unified_cards_and_chinese_system_labels -q
```

Expected: one assertion failure for the still-present three-column tab declaration or missing formatter.

### Task 2: Normalize the current-analysis presentation and localize known system values

**Files:**
- Modify: `src/data_agent/web/static/css/app.css:329-339`
- Modify: `src/data_agent/web/static/js/app.js:1284-1313`
- Modify: `src/data_agent/web/templates/index.html:541-675`
- Test: `tests/test_web_workbench_replacement.py`

**Interfaces:**
- Consumes: `actionBoard()` items with `confidence`, `label`, `reason`, `direction`, `kind`, and `trust_basis.verification_status`; `formatRiskMessage(message)`; current multifile helper payloads.
- Produces: `formatWorkbenchText(value, category = '')`, which returns a Chinese label for known system values and original text for unknown values.

- [ ] **Step 1: Replace the stale tab grid declaration**

```css
.session-side-tabs {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.25rem;
    border: 1px solid #e7e5e4;
    border-radius: 0.5rem;
    background: rgba(231, 229, 228, 0.45);
    padding: 0.25rem;
}
```

- [ ] **Step 2: Add the formatter next to `formatRiskMessage`**

```javascript
        formatWorkbenchText(value, category = '') {
            const text = String(value || '');
            const labels = {
                confidence: { high: '高置信度', medium: '中等置信度', low: '低置信度' },
                route: {
                    trend: '趋势分析',
                    period_compare: '周期对比',
                    correlation: '相关性分析',
                    rate_analysis: '比率分析',
                },
                kind: { route: '推荐分析方向', data_gap: '数据缺口' },
                verification: { not_run: '尚未验证' },
                data: { 'Grain not identified': '未识别数据粒度' },
            };
            const translated = labels[category]?.[text];
            if (translated) return translated;
            return category === 'risk' || category === 'data'
                ? this.formatRiskMessage(text)
                : text;
        },
```

- [ ] **Step 3: Align action-board markup to drill-down card rhythm and route known values through the formatter**

```html
<div class="space-y-4 mt-2">
  <div data-testid="action-board-confirmed" class="space-y-1.5">
    <div class="text-[11px] font-semibold text-stone-400 uppercase tracking-wider">已确认</div>
    <template x-for="(c, i) in actionBoard().confirmed" :key="'conf-'+i">
      <div class="workbench-item">
        <div class="text-xs font-medium text-stone-700 dark:text-stone-300" x-text="c.claim"></div>
        <div class="text-[10px] text-stone-500 dark:text-stone-400 mt-1"><span x-text="formatWorkbenchText(c.confidence, 'confidence')"></span><span x-show="c.dataset"> · </span><span x-text="c.dataset"></span></div>
      </div>
    </template>
  </div>
</div>
```

Apply the same `space-y-1.5`, `text-xs`, and `text-[10px]` hierarchy to the uncertain and next-step groups. Their text bindings must be:

```html
<div class="text-xs font-medium text-stone-700 dark:text-stone-300" x-text="formatWorkbenchText(u.label, 'risk')"></div>
<div class="text-[10px] text-stone-500 dark:text-stone-400 mt-1" x-text="formatWorkbenchText(u.reason, 'kind')"></div>
<div class="text-xs font-medium text-stone-700 dark:text-stone-300" x-text="formatWorkbenchText(n.direction, 'route')"></div>
<div class="text-[10px] text-stone-500 dark:text-stone-400 mt-1" x-text="formatWorkbenchText(n.kind, 'kind')"></div>
<span x-text="formatWorkbenchText(actionBoard().trust_basis.verification_status || 'not_run', 'verification')"></span>
```

- [ ] **Step 4: Localize static and known fallback values in the drill-down portion of the current-analysis tab**

```html
<h3 class="text-[11px] font-semibold text-stone-400 uppercase tracking-wider">数据理解</h3>
<span class="trust-pill" :class="trustStatusClass(trustView ? trustView.status : 'empty')" x-text="trustLoading ? '加载中' : trustStatusLabel(trustView ? trustView.status : 'empty')"></span>
<p class="text-xs font-medium text-stone-700 dark:text-stone-300 truncate" x-text="dataset.dataset || '数据集'"></p>
<span class="text-[10px] text-stone-400" x-text="(dataset.rows || 0) + ' 行'"></span>
<p class="text-[10px] text-stone-500 dark:text-stone-400 mt-1" x-text="formatWorkbenchText(dataset.grain || 'Grain not identified', 'data')"></p>
<p x-show="!trustLoading && !trustError && (!multifileDataUnderstanding().datasets || multifileDataUnderstanding().datasets.length === 0)" class="text-xs text-stone-400 py-1">暂无数据理解摘要。</p>
<h3 class="text-[11px] font-semibold text-stone-400 uppercase tracking-wider">数据关系</h3>
<p x-show="!trustLoading && !trustError && multifileRelationships().length === 0" class="text-xs text-stone-400 py-1">暂无数据关系信息。</p>
```

Use `formatWorkbenchText(value, 'risk')` for `file.reason`, relationship value/risk, relationship evidence, relationship uncertainties, quality findings, and analysis constraints so only known translations change and unknown backend content remains visible.

- [ ] **Step 5: Run the focused regression test and verify it passes**

Run:

```powershell
uv run pytest tests/test_web_workbench_replacement.py::test_current_analysis_uses_two_equal_tabs_unified_cards_and_chinese_system_labels -q
```

Expected: `1 passed`.

### Task 3: Verify the Workbench regression surface and commit the implementation

**Files:**
- Verify: `tests/test_web_workbench_replacement.py`
- Verify: `tests/test_web_workbench_action_board.py`
- Verify: `tests/test_web_workbench_parity.py`
- Verify: `tests/`

**Interfaces:**
- Consumes: completed Tasks 1 and 2.
- Produces: fresh evidence that markup contracts and the full Python suite remain compatible.

- [ ] **Step 1: Run the focused Workbench test group**

```powershell
uv run pytest tests/test_web_workbench_replacement.py tests/test_web_workbench_action_board.py tests/test_web_workbench_parity.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the full suite**

```powershell
uv run pytest tests/ -q
```

Expected: process exits with code `0` and no failures.

- [ ] **Step 3: Inspect the final diff for whitespace errors and unintended files**

```powershell
git diff --check
git status --short
git diff -- src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/web/static/css/app.css tests/test_web_workbench_replacement.py
```

Expected: no `git diff --check` output; only the four implementation files are uncommitted.

- [ ] **Step 4: Commit the implementation**

```powershell
git add src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/web/static/css/app.css tests/test_web_workbench_replacement.py
git commit -m "fix(workbench): unify current analysis UI"
```

