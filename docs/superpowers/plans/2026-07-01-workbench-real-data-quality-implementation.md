# Workbench and Real-Data Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a user-value-first Workbench for multifile understanding and prove the redesigned workflow preserves or improves analysis quality on real project data.

**Architecture:** A backend read model converts canonical bundles, relationships, opportunities, evidence, and sufficiency into four user-facing sections. The existing Web Workbench renders those sections without exposing raw technical state, while reproducible real-data scenarios and a quality rubric gate completion.

**Tech Stack:** Python 3.11+, Flask, Alpine.js, existing HTML/CSS, pandas/openpyxl through the project environment, pytest.

---

### Task 1: User-Value Workbench Read Model

**Files:**
- Modify: `src/data_agent/agent/trust_view.py`
- Create: `src/data_agent/agent/workbench_view.py`
- Create: `tests/test_multifile_workbench_view.py`

- [ ] **Step 1: Write failing read-model tests**

```python
def test_workbench_answers_four_user_questions():
    view = build_multifile_workbench_view(state_fixture())
    assert set(view) == {"data_understanding", "relationships", "analysis_directions", "answer_coverage"}
    assert view["analysis_directions"][0]["why_it_matters"]
    assert "artifact_path" not in json.dumps(view)
```

Test sensitive preview suppression, rejected relationship explanations, auto-selected badges, insufficient-data recovery, and no raw TASK/tool-log dump.

- [ ] **Step 2: Verify RED**

Expected: the existing workbench has technical sections but no canonical four-section read model.

- [ ] **Step 3: Implement the read model**

```python
def build_multifile_workbench_view(state):
    bundle = latest_valid_bundle(state)
    return {
        "data_understanding": build_user_data_brief(bundle),
        "relationships": relationship_cards(bundle),
        "analysis_directions": opportunity_cards(state.analysis_opportunities),
        "answer_coverage": coverage_card(latest_sufficiency(state)),
    }
```

Integrate under `trust_view["workbench"]["multifile_analysis"]` without retaining a second legacy rendering path for the same content.

- [ ] **Step 4: Run trust/workbench tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/workbench_view.py src/data_agent/agent/trust_view.py tests/test_multifile_workbench_view.py
git commit -m "feat: build user-value multifile workbench view"
```

### Task 2: Workbench UI and Accessible States

**Files:**
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `src/data_agent/web/static/css/app.css`
- Modify: `tests/test_trust_inspector_ui.py`
- Modify: `tests/test_web_workbench_parity.py`

- [ ] **Step 1: Write failing UI contract tests**

```python
def test_workbench_template_contains_user_value_sections(client):
    html = client.get("/").get_data(as_text=True)
    for section_id in ("data-understanding", "relationships", "analysis-directions", "answer-coverage"):
        assert f'id="{section_id}"' in html
    assert 'aria-live="polite"' in html
```

- [ ] **Step 2: Verify RED**

Expected: required labels and bindings are absent.

- [ ] **Step 3: Replace technical-first layout with four user sections**

```html
<section id="data-understanding" aria-labelledby="data-understanding-title">
  <h3 id="data-understanding-title">我理解的数据</h3>
</section>
<section id="relationships" aria-labelledby="relationships-title">
  <h3 id="relationships-title">文件关系</h3>
</section>
<section id="analysis-directions" aria-labelledby="analysis-directions-title">
  <h3 id="analysis-directions-title">建议分析方向</h3>
</section>
<section id="answer-coverage" aria-labelledby="answer-coverage-title" aria-live="polite">
  <h3 id="answer-coverage-title">当前结论覆盖</h3>
</section>
```

Use concise cards, progressive disclosure for technical details, and visible explanations for rejected/uncertain relationships. Do not expose raw IDs as primary labels.

- [ ] **Step 4: Run UI, parity, and API tests**

Expected: PASS.

- [ ] **Step 5: Verify in the in-app browser**

Load the local app, inspect desktop and narrow layouts, verify all states, and save screenshots under `artifacts/workbench-qa/` for review.

- [ ] **Step 6: Commit**

```powershell
git add src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/web/static/css/app.css tests/test_trust_inspector_ui.py tests/test_web_workbench_parity.py artifacts/workbench-qa
git commit -m "feat: present multifile analysis in workbench"
```

### Task 3: Reproducible Real-Data Scenario Harness

**Files:**
- Create: `tests/real_data/test_multifile_real_data_scenarios.py`
- Create: `tests/real_data/scenario_manifest.json`
- Create: `scripts/run_multifile_quality_scenarios.py`

- [ ] **Step 1: Define exact scenario inputs and expected gates**

```json
{
  "game_a_evidence_synthesis": {
    "files": ["游戏Abanner汇总数据.xlsx", "游戏A内购数据.xlsx", "游戏A激励视频汇总数据报表.xlsx"],
    "required_modes": ["independent", "synthesis"],
    "minimum_evidence_records": 3
  },
  "saving_card_joint_analysis": {
    "files": ["省钱卡用户最近流水_20260511.xlsx", "省钱卡订单_20260507.xlsx"],
    "required_checks": ["cardinality", "join_coverage", "grain", "time_alignment"]
  }
}
```

- [ ] **Step 2: Write failing scenario tests**

```python
@pytest.mark.parametrize("scenario_name", ["game_a_evidence_synthesis", "saving_card_joint_analysis"])
def test_real_data_scenario_meets_declared_gates(scenario_name, scenario_runner):
    result = scenario_runner.run(scenario_name)
    assert result.errors == []
    assert result.bundle_id
    assert result.gates_passed == result.gates_required
```

- [ ] **Step 3: Verify RED**

Expected: scenario harness or required new artifacts are missing.

- [ ] **Step 4: Implement the runner**

The script writes machine-readable results to `artifacts/multifile-quality/<timestamp>/results.json` and never modifies source spreadsheets.

- [ ] **Step 5: Run real-data scenarios**

Run: `$env:PYTHONPATH=(Resolve-Path 'src').Path; & 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' scripts/run_multifile_quality_scenarios.py --data-dir 'D:\Project\Daily\data-agent\reference\test_doc'`

Expected: every scenario completes with its declared gates; rejected relationships include reasons rather than silent fallback.

- [ ] **Step 6: Commit**

```powershell
git add tests/real_data/test_multifile_real_data_scenarios.py tests/real_data/scenario_manifest.json scripts/run_multifile_quality_scenarios.py
git commit -m "test: add multifile real-data scenarios"
```

### Task 4: Analysis Quality Baseline and Regression Rubric

**Files:**
- Create: `src/data_agent/agent/analysis_quality_rubric.py`
- Create: `tests/real_data/test_multifile_analysis_quality.py`
- Create: `docs/superpowers/validation/2026-07-01-multifile-quality-rubric.md`

- [ ] **Step 1: Write failing rubric tests**

```python
def test_quality_score_blocks_unsupported_claims():
    score = score_analysis_quality(result_with_unsupported_claim())
    assert score.ready is False
    assert "unsupported_claim" in score.blockers
```

Score question coverage, evidence citation, measurement completeness, relationship validity, unsupported claims, limitation visibility, insight depth, actionable implications, and user-facing clarity. Unsupported claims and invalid joins are blockers, not weighted away.

- [ ] **Step 2: Verify RED**

Expected: rubric module missing.

- [ ] **Step 3: Implement deterministic scoring and reviewer fields**

```python
@dataclass(frozen=True)
class AnalysisQualityScore:
    ready: bool
    total: float
    blockers: tuple[str, ...]
    dimensions: dict[str, float]
```

Automated checks cover structural facts; insight depth and actionability use a saved reviewer rubric with explicit evidence excerpts, never an untracked free-form judgment.

- [ ] **Step 4: Compare scoped and baseline single-file analysis**

Run the same questions through the current baseline fixture and new workflow. The new workflow must not reduce question coverage, valid metric count, evidence completeness, or insight-depth rating.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/analysis_quality_rubric.py tests/real_data/test_multifile_analysis_quality.py docs/superpowers/validation/2026-07-01-multifile-quality-rubric.md
git commit -m "test: enforce multifile analysis quality rubric"
```

### Task 5: Final Verification and Handoff

**Files:**
- Create: `docs/superpowers/validation/2026-07-01-multifile-stage3c0b-validation-report.md`

- [ ] **Step 1: Run unit and integration suites**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_data_understanding_bundle.py tests/test_relationship_validation.py tests/test_scoped_workspace.py tests/test_derived_dataset_scope.py tests/test_analysis_opportunities.py tests/test_strategy_contracts.py tests/test_role_prompt_contexts.py tests/test_strategy_task_dag.py tests/test_stage3c0b_replanning.py tests/test_stage3c0b_sufficiency.py tests/test_multifile_workbench_view.py tests/test_trust_inspector_ui.py tests/test_web_workbench_parity.py -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_phase_comprehensive.py -q
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_comprehensive_analysis_flow.py -q
```

- [ ] **Step 2: Run all real-data scenarios and quality comparisons**

Record exact commands, pass/fail counts, scenario artifact paths, discovered data limitations, and any skipped checks.

- [ ] **Step 3: Inspect the final Workbench in the in-app browser**

Verify that a user can identify what data means, which files relate, which directions are recommended, what evidence exists, and what remains unanswered without reading technical logs.

- [ ] **Step 4: Write the validation report**

The report must separate implemented behavior from design, list blockers and caveats, summarize analysis-quality changes, and link saved real-data results and screenshots.

- [ ] **Step 5: Run the final full review**

Request spec-compliance and code-quality reviews for the entire three-plan implementation. Fix every Critical and Important issue and rerun affected tests.

- [ ] **Step 6: Commit**

```powershell
git add docs/superpowers/validation/2026-07-01-multifile-stage3c0b-validation-report.md
git commit -m "docs: validate multifile stage 3c0b workflow"
```
