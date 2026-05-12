# Expert Analysis Flow Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore professional default analysis quality by making complete analysis plan-driven, statistically explained, chart-supported, and no longer defaulting to thin briefs.

**Architecture:** Phase 1 keeps the existing EvidenceRecord and playbook architecture, but changes their role. EvidenceRecord becomes the internal support layer; final user output and formal reports must include expert interpretation, statistical explanation, charts, limitations, and next analysis directions.

**Tech Stack:** Python, pytest, existing `data_agent.agent.prompts`, `data_agent.agent.method_playbooks`, `data_agent.tools.analysis_flow`, `data_agent.tools.report`, session artifacts, and project skills.

---

### Task 1: Define Analysis Completeness Contract

**Files:**
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `src/data_agent/tools/analysis_flow.py`
- Test: `tests/test_quality_control.py`

- [ ] **Step 1: Write failing tests for completeness checks**

Add tests that assert a core analysis is incomplete when it lacks statistics, statistics, presentation sufficiency, or next directions.

```python
def test_analysis_completeness_flags_missing_core_quality_fields():
    from data_agent.agent.analysis_state import analysis_completeness_summary, AnalysisSessionState

    state = AnalysisSessionState(session_id="complete_check", goal="evaluate savings card")
    state.evidence_records.append({
        "id": "ev_1",
        "claim": "璐崱鍚庝粯璐逛笅闄?,
        "dataset": "orders",
        "method": "before-after",
        "tool_calls": ["compare_periods"],
        "result_summary": "涓嬮檷 31.8%",
        "limitations": "缂哄皯瀵圭収缁?,
        "confidence": "medium",
        "statistical_detail_status": "missing",
        "statistical_detail_gaps": ["sample_size", "significance"],
    })

    summary = analysis_completeness_summary(state, deprecated_require_charts=True)

    assert summary["status"] == "incomplete"
    assert "statistical_details" in summary["missing"]
    assert "presentation_sufficiency" in summary["missing"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_quality_control.py::test_analysis_completeness_flags_missing_core_quality_fields -q
```

Expected: fails because `analysis_completeness_summary` does not exist.

- [ ] **Step 3: Implement minimal completeness helper**

Add helper in `analysis_state.py`:

```python
def analysis_completeness_summary(state: AnalysisSessionState | None, deprecated_require_charts: bool = False) -> dict[str, Any]:
    if state is None:
        return {"status": "incomplete", "missing": ["analysis_state"], "counts": {}}
    records = list(state.evidence_records or [])
    missing = []
    if not records:
        missing.append("evidence_records")
    if any(record.get("statistical_detail_status") == "missing" for record in records):
        missing.append("statistical_details")
    if not state.insight_records:
        missing.append("expert_synthesis")
    if deprecated_require_charts:
        chart_ids = [
            chart_id
            for insight in state.insight_records or []
            for chart_id in (insight.get("chart_ids") or [])
        ]
        if not chart_ids:
            missing.append("presentation_sufficiency")
    return {
        "status": "complete" if not missing else "incomplete",
        "missing": sorted(set(missing)),
        "counts": {
            "evidence_records": len(records),
            "insight_records": len(state.insight_records or []),
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run the same pytest command. Expected: pass.

---

### Task 2: Stop Default Complete Analysis From Using Brief As Final Output

**Files:**
- Modify: `src/data_agent/agent/prompts.py`
- Modify: `src/data_agent/agent/repl.py`
- Test: `tests/test_project_intent_context.py`

- [ ] **Step 1: Write failing prompt contract test**

Add a test asserting complete analysis prompt treats `generate_analysis_brief` as auxiliary, not final.

```python
def test_complete_analysis_prompt_positions_brief_as_auxiliary():
    from data_agent.agent.prompts import build_system_prompt

    prompt = build_system_prompt(
        tool_list="record_evidence_record, create_chart, generate_analysis_brief, generate_formal_report",
        session_context="- main: 10 rows x 3 cols, columns: user_id, revenue, date",
        user_input="璇峰畬鏁村垎鏋愮渷閽卞崱鏁堟灉锛屽苟鍛婅瘔鎴戣繕鏈夊摢浜涚淮搴﹀彲浠ュ垎鏋?,
    )

    assert "generate_analysis_brief 浠呯敤浜庡揩閫熸憳瑕? in prompt
    assert "榛樿鏈€缁堣緭鍑哄繀椤绘槸涓撲笟鍒嗘瀽缁撴灉" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_project_intent_context.py::test_complete_analysis_prompt_positions_brief_as_auxiliary -q
```

Expected: fails until prompt is updated.

- [ ] **Step 3: Update prompt rules**

In `AGENT_ANALYSIS_ENGINE` and `AGENT_FULL`, add:

```text
generate_analysis_brief 浠呯敤浜庡揩閫熸憳瑕併€佷腑闂磋繘搴﹀鍑烘垨璇佹嵁缂哄彛鎽樿銆?瀹屾暣鍒嗘瀽/鍏ㄩ潰鍒嗘瀽/鎶ュ憡绫昏姹傜殑榛樿鏈€缁堣緭鍑哄繀椤绘槸涓撲笟鍒嗘瀽缁撴灉锛?鏍稿績缁撹銆佹寚鏍囪〃銆佺粺璁¤鏄庛€佸浘琛ㄣ€佷笟鍔¤В閲娿€侀檺鍒躲€佸缓璁拰涓嬩竴姝ュ垎鏋愭柟鍚戙€?```

- [ ] **Step 4: Run test to verify it passes**

Run the same pytest command. Expected: pass.

---

### Task 3: Add Business Goal Golden Scenario

**Files:**
- Modify: `tests/test_golden_scenarios.py`
- Modify: `src/data_agent/agent/method_playbooks.py`

- [ ] **Step 1: Write failing golden scenarios**

Add deterministic tests that use representative business-goal requests and verify playbook selection includes business problem playbooks. The savings-card request is one example of a broader class: feature or policy effect evaluation with revenue and behavior questions.

```python
def test_feature_effect_goal_selects_business_playbook_stack():
    from data_agent.agent.intent import plan_turn_intent
    from data_agent.agent.method_playbooks import select_playbooks

    ctx = "- orders: 7206 rows x 8 cols, columns: user_id, payment, pay_time, user_type\n- card_orders: 71 rows x 5 cols, columns: user_id, product_name, price, pay_time"
    user_input = "鍒嗘瀽鐪侀挶鍗″姛鑳藉鐢ㄦ埛浠樿垂琛屼负鐨勫奖鍝嶏紝鍖呭惈鏀剁泭銆佷粯璐瑰墠鍚庡彉鍖栵紝骞跺憡璇夋垜杩樿兘鍒嗘瀽鍝簺缁村害"
    intent = plan_turn_intent(user_input, ctx)

    selection = select_playbooks(user_input, intent, dataset_profile=ctx)
    ids = [selection.primary_playbook_id] + selection.supporting_playbook_ids

    assert "product_feature_analysis" in ids
    assert "effect_evaluation" in ids
    assert "revenue_profitability" in ids
    assert "user_behavior_analysis" in ids


def test_marketing_campaign_goal_selects_business_playbook_stack():
    from data_agent.agent.intent import plan_turn_intent
    from data_agent.agent.method_playbooks import select_playbooks

    ctx = "- campaign_orders: 5000 rows x 9 cols, columns: user_id, campaign_id, revenue, cost, order_time, channel, is_exposed"
    user_input = "鍒嗘瀽杩欐钀ラ攢娲诲姩鏄惁鏈夋晥锛屽寘鍚敹鍏ャ€佹垚鏈€佺敤鎴疯涓哄彉鍖栵紝骞剁粰鍑鸿繕鑳界户缁垎鏋愮殑鏂瑰悜"
    intent = plan_turn_intent(user_input, ctx)

    selection = select_playbooks(user_input, intent, dataset_profile=ctx)
    ids = [selection.primary_playbook_id] + selection.supporting_playbook_ids

    assert "effect_evaluation" in ids
    assert "revenue_profitability" in ids
    assert "user_behavior_analysis" in ids
    assert "growth_opportunity" in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_golden_scenarios.py::test_feature_effect_goal_selects_business_playbook_stack tests/test_golden_scenarios.py::test_marketing_campaign_goal_selects_business_playbook_stack -q
```

Expected: fails because these playbooks do not exist.

- [ ] **Step 3: Add business playbook definitions**

In `method_playbooks.py`, add playbooks:

- `product_feature_analysis`
- `effect_evaluation`
- `revenue_profitability`
- `user_behavior_analysis`
- `growth_opportunity`

Each must include:

```python
method_plan=[
    {"step": "...", "required_capability": "...", "evidence_requirements": [...]},
]
evidence=[...]
limitations=[...]
```

Include output policies with visualization strategy and statistical requirements.

- [ ] **Step 4: Update selection rules**

Update `_choose_primary` and `_choose_supporting` so terms like `鐪侀挶鍗, `鍔熻兘`, `鏁堟灉`, `鏀剁泭`, `浠樿垂琛屼负`, `杩樿兘鍒嗘瀽鍝簺缁村害` build the expected stack.

- [ ] **Step 5: Run test to verify it passes**

Run the same pytest command. Expected: pass.

---

### Task 4: Promote visualization strategy Into AnalysisSpec

**Files:**
- Modify: `src/data_agent/agent/method_playbooks.py`
- Modify: `src/data_agent/agent/analysis_flow_controller.py`
- Test: `tests/test_method_playbooks.py`

- [ ] **Step 1: Write failing test for visualization strategy**

```python
def test_business_playbook_analysis_spec_contains_visualization_strategy_and_stats():
    from data_agent.agent.intent import plan_turn_intent
    from data_agent.agent.method_playbooks import select_playbooks

    ctx = "- main: 100 rows x 5 cols, columns: user_id, revenue, pay_time, card_type, period"
    intent = plan_turn_intent("鍒嗘瀽鐪侀挶鍗℃晥鏋滃拰鏀剁泭", ctx)
    selection = select_playbooks("鍒嗘瀽鐪侀挶鍗℃晥鏋滃拰鏀剁泭", intent, dataset_profile=ctx)

    spec = selection.analysis_spec

    assert spec is not None
    assert "visualization_strategy" in spec
    assert "statistical_requirements" in spec
    assert "effect_size" in spec["statistical_requirements"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_method_playbooks.py::test_business_playbook_analysis_spec_contains_visualization_strategy_and_stats -q
```

Expected: fails because spec lacks these fields.

- [ ] **Step 3: Extend MethodPlaybook output policy**

Add `visualization_strategy`, `statistical_requirements`, and `output_sections` to each new business playbook's `output_policy`.

- [ ] **Step 4: Merge requirements into AnalysisSpec**

In `_build_analysis_spec`, merge output policy from primary and supporting playbooks:

```python
spec["visualization_strategy"] = sorted(set(...))
spec["statistical_requirements"] = sorted(set(...))
spec["output_sections"] = [...]
```

- [ ] **Step 5: Run test to verify it passes**

Run the same pytest command. Expected: pass.

---

### Task 5: Make Formal Report Surface Expert Synthesis Before Evidence Lists

**Files:**
- Modify: `src/data_agent/tools/report.py`
- Test: `tests/test_report_pipeline.py`

- [ ] **Step 1: Write failing report structure test**

```python
def test_formal_report_prioritizes_expert_synthesis_over_raw_evidence(tmp_path):
    cfg, old_sessions = _use_tmp_sessions(tmp_path)
    ctx = AgentContext(session_id="expert_report", workspace=Workspace())
    ctx.analysis_state = AnalysisSessionState(session_id="expert_report", goal="鐪侀挶鍗″垎鏋?)
    ctx.analysis_state.evidence_records.append({
        "id": "ev_1",
        "claim": "璐崱鍚庝粯璐逛笅闄?,
        "dataset": "orders",
        "method": "Mann-Whitney U",
        "tool_calls": ["ab_test"],
        "result_summary": "p=0.25, d=-0.22",
        "limitations": "缂哄皯瀵圭収缁?,
        "confidence": "medium",
        "sample_size": 123,
        "significance": {"p_value": 0.25},
    })
    ctx.analysis_state.insight_records.append({
        "title": "鏈兘璇佹槑鐪侀挶鍗℃彁鍗囦粯璐?,
        "summary": "璐崱鍓嶅悗宸紓涓嶆樉钁楋紝涓旂己灏戞湭璐崱瀵圭収缁勩€?,
        "evidence_ids": ["ev_1"],
        "chart_ids": [],
        "recommendation": "琛ュ厖鏈喘鍗″鐓х粍鍚庡仛 DID 鎴栧尮閰嶅垎鏋愩€?,
        "limitations": "瑙傚療鎬у墠鍚庡姣斾笉鑳借瘉鏄庡洜鏋溿€?,
        "confidence": "medium",
        "output_type": "finding",
    })

    try:
        with use_agent_context(ctx):
            result = json.loads(report.generate_formal_report(format="markdown"))
        content = (tmp_path / result["artifact_path"]).read_text(encoding="utf-8")
        assert content.index("鏍稿績缁撹涓庝笟鍔″惈涔?) < content.index("Evidence `ev_1`")
        assert "琛ュ厖鏈喘鍗″鐓х粍鍚庡仛 DID" in content
    finally:
        cfg.sessions_dir = old_sessions
```

- [ ] **Step 2: Run test to verify it fails if structure regresses**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_report_pipeline.py::test_formal_report_prioritizes_expert_synthesis_over_raw_evidence -q
```

Expected: pass if current structure already supports this; fail only if synthesis is missing.

- [ ] **Step 3: Adjust report markdown if needed**

Ensure report order is:

1. One-page conclusion
2. Core conclusions and business meaning
3. Core metrics and statistical explanation
4. Charts
5. Evidence index
6. Limitations and next analysis directions

- [ ] **Step 4: Run report tests**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_report_pipeline.py -q
```

Expected: pass.

---

### Task 6: Verification

**Files:**
- Test: `tests/test_report_pipeline.py`
- Test: `tests/test_quality_control.py`
- Test: `tests/test_method_playbooks.py`
- Test: `tests/test_golden_scenarios.py`
- Test: `tests/test_project_intent_context.py`

- [ ] **Step 1: Run targeted regression suite**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_report_pipeline.py tests/test_quality_control.py tests/test_method_playbooks.py tests/test_project_intent_context.py -q
```

Expected: all pass.

- [ ] **Step 2: Run golden scenario tests**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_golden_scenarios.py -q
```

Expected: all pass.

- [ ] **Step 3: Check full_report skill**

```bash
.\.venv\Scripts\python.exe -c "from pathlib import Path; from data_agent.skills.loader import SkillLoader; s=SkillLoader([Path('project/skills')]); s.discover(); full=next(x for x in s.list_available() if x.name=='full_report'); assert 'generate_formal_report' in full.tools_required; assert 'record_evidence_record' in full.tools_required; assert 'create_chart' in full.tools_required; print('full_report skill ok')"
```

Expected: `full_report skill ok`.


