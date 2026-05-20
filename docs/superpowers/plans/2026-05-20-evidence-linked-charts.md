# Evidence-Linked Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated charts accurate, evidence-bound, and rendered next to the analysis text they support.

**Architecture:** Keep `create_chart` as the trusted interactive chart producer. Add stricter chart metadata validation in the visualization tool, then teach chat and report rendering to place validated artifacts by chart reference or evidence relationship.

**Tech Stack:** Python, Plotly, Flask/Jinja artifacts, Alpine.js frontend, pytest.

---

## File Structure

- Modify `src/data_agent/tools/visualization.py`: chart validation, grouped rendering behavior, metadata completeness.
- Modify `src/data_agent/tools/report.py`: chart grouping and per-insight/per-evidence chart insertion.
- Modify `src/data_agent/web/templates/index.html`: move turn chart display below markdown and add supplemental chart section.
- Modify `src/data_agent/web/static/js/app.js`: parse chart references, resolve turn artifacts, render inline chart iframes, suppress duplicate supplemental display.
- Modify `src/data_agent/agent/prompts.py`: tell the agent how to reference generated charts without inventing Mermaid data charts.
- Modify `tests/test_chart_contract.py`: validation and rendering contract tests.
- Modify `tests/test_report_pipeline.py`: formal report placement tests.
- Modify `tests/test_web_gui.py` or `tests/test_web_overhaul.py`: frontend helper behavior tests where existing tests make that practical.

## Task 1: Chart Contract Tightening

- [ ] **Step 1: Add failing tests for evidence purpose and color grouping**

Add tests in `tests/test_chart_contract.py` that assert:

```python
def test_evidence_chart_requires_evidence_ids(monkeypatch):
    result = create_chart(
        chart_type="bar",
        data_json='[{"segment":"A","value":1}]',
        title="Evidence chart",
        x_col="segment",
        y_col="value",
        purpose="evidence",
    )
    assert "Error" in result
    assert "evidence_ids" in result
```

and a line or scatter case where `color_col` creates separate named traces or is rejected.

- [ ] **Step 2: Run the focused chart tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py -q`

Expected: the new tests fail before implementation.

- [ ] **Step 3: Implement minimal validation and rendering changes**

Update `src/data_agent/tools/visualization.py` so `purpose in {"evidence", "insight"}` requires non-empty `evidence_ids`, and `color_col` creates grouped traces for supported chart types.

- [ ] **Step 4: Re-run chart tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py -q`

Expected: chart contract tests pass.

## Task 2: Inline Chat Chart Placement

- [ ] **Step 1: Add frontend helper tests if existing test harness supports JS/static assertions**

Use the existing web tests to assert the template renders markdown before supplemental artifacts and exposes inline chart reference hooks.

- [ ] **Step 2: Update chat template ordering**

Move the artifact iframe loop in `src/data_agent/web/templates/index.html` from before the assistant markdown to after it. Label unmatched charts as supplemental charts.

- [ ] **Step 3: Add chart reference handling**

Update `src/data_agent/web/static/js/app.js` so `renderMarkdown()` turns `[[chart:<id-or-path>]]` into an inline chart container resolved from `turn.artifacts`.

- [ ] **Step 4: Preserve fallback behavior**

Charts not referenced inline remain visible in a supplemental section after the assistant markdown.

## Task 3: Report Chart Placement

- [ ] **Step 1: Add failing report placement test**

In `tests/test_report_pipeline.py`, create a fake chart metadata file with `evidence_ids=["EV-1"]`, generate a formal report, and assert the chart HTML appears near the section for `EV-1` instead of only after the whole markdown body.

- [ ] **Step 2: Implement chart grouping helpers**

In `src/data_agent/tools/report.py`, group validated chart entries by `chart_id` and `evidence_ids`.

- [ ] **Step 3: Insert chart placeholders into formal markdown HTML**

Render matched charts under the relevant insight or evidence block. Keep unmatched exploratory charts in a supplemental section.

- [ ] **Step 4: Run report tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_report_pipeline.py -q`

Expected: report pipeline tests pass.

## Task 4: Prompt Guidance

- [ ] **Step 1: Update prompt wording**

In `src/data_agent/agent/prompts.py`, instruct the assistant to reference a generated chart with `[[chart:<chart_id_or_path>]]` when the chart supports a specific conclusion.

- [ ] **Step 2: Add prompt test**

In `tests/test_prompt_system.py`, assert the prompt contains chart reference guidance and still forbids Mermaid fallback for data charts.

- [ ] **Step 3: Run prompt tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_prompt_system.py -q`

Expected: prompt tests pass.

## Task 5: Final Verification

- [ ] **Step 1: Run focused verification**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_chart_contract.py tests/test_report_pipeline.py tests/test_prompt_system.py tests/test_web_gui.py tests/test_web_overhaul.py -q`

Expected: all selected tests pass, aside from known `.pytest_cache` permission warnings.

- [ ] **Step 2: Inspect changed files**

Run: `git diff -- src/data_agent/tools/visualization.py src/data_agent/tools/report.py src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/agent/prompts.py tests/test_chart_contract.py tests/test_report_pipeline.py tests/test_prompt_system.py`

Expected: diff is scoped to evidence-linked chart validation and display.
