# Analysis Opportunity and Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn validated data understanding into ranked analysis opportunities, approved strategies, bounded task DAGs, evidence-driven replanning, and sufficient synthesis.

**Architecture:** AnalysisOpportunity and StrategyRecord are canonical contracts between planning and execution. Role-specific prompt builders consume only the artifacts required for interpreter, planner, executor, or synthesizer, while deterministic gates control auto-selection, confirmation, plan replacement, and evidence sufficiency.

**Tech Stack:** Python 3.11+, dataclasses, existing prompt/client abstractions, TaskManager, AnalysisSessionState, pytest.

---

### Task 1: AnalysisOpportunity Contract and Ranking

**Files:**
- Create: `src/data_agent/agent/analysis_opportunities.py`
- Create: `tests/test_analysis_opportunities.py`
- Modify: `src/data_agent/agent/analysis_state.py`

- [ ] **Step 1: Write failing contract and ranking tests**

```python
def test_goal_aligned_validated_opportunity_ranks_first():
    opportunities = build_analysis_opportunities(bundle(), user_goal="compare payer rate")
    ranked = rank_analysis_opportunities(opportunities, user_goal="compare payer rate")
    assert ranked[0]["question"] == "How does payer rate differ by source?"
    assert ranked[0]["required_relationship_ids"] == ["rel_banner_iap"]

def test_unvalidated_joint_opportunity_cannot_be_auto_selected():
    decision = select_analysis_opportunities([joint_opportunity(relationship_status="proposed")], limit=5)
    assert decision.selected == []
    assert decision.needs_confirmation[0]["id"] == "opp_joint"
```

- [ ] **Step 2: Verify RED**

Expected: missing module.

- [ ] **Step 3: Implement stable IDs, scoring, and status transitions**

```python
score = (
    goal_match * 0.30 + business_value * 0.25 + feasibility * 0.20
    + relationship_confidence * 0.15 + evidence_strength * 0.10
) - risk_penalty
```

Statuses are `proposed`, `validated`, `selected`, `completed`, `rejected`, and `needs_more_data`. Persist opportunities in AnalysisSessionState with bundle fingerprint and plan ID.

- [ ] **Step 4: Run tests**

Expected: PASS and deterministic ordering for equal scores.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/analysis_opportunities.py src/data_agent/agent/analysis_state.py tests/test_analysis_opportunities.py
git commit -m "feat: rank canonical analysis opportunities"
```

### Task 2: StrategyRecord and Auto-Selection Gate

**Files:**
- Create: `src/data_agent/agent/strategy_contracts.py`
- Create: `tests/test_strategy_contracts.py`
- Modify: `src/data_agent/agent/analysis_plan_contracts.py`

- [ ] **Step 1: Write failing validation tests**

```python
def test_strategy_requires_expected_evidence_and_stop_conditions():
    result = validate_strategy_record({
        "id": "strategy_1", "opportunity_id": "opp_1", "mode": "joint",
        "dataset_inputs": ["banner", "iap"], "relationship_ids": ["rel_1"],
        "required_checks": ["join_coverage"], "expected_evidence": [],
        "stop_conditions": [], "replan_conditions": ["join_coverage_failed"],
    }, relationships=[validated_relationship("rel_1")])
    assert result.ok is False
    assert result.error_type == "missing_expected_evidence"
```

- [ ] **Step 2: Verify RED**

Expected: missing StrategyRecord validator.

- [ ] **Step 3: Implement the gate**

```python
AUTO_SELECT_MIN_CONFIDENCE = 0.80

def strategy_requires_confirmation(strategy):
    return (
        strategy["confidence"] < AUTO_SELECT_MIN_CONFIDENCE
        or strategy["required_capability"] in HIGH_RISK_CAPABILITIES
        or any(r["status"] != "validated" for r in strategy["relationships"])
        or bool(strategy.get("scope_expansion"))
    )
```

AnalysisPlan steps reference `strategy_id` and `opportunity_id`; validators reject missing or mismatched references.

- [ ] **Step 4: Run strategy and plan tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/strategy_contracts.py src/data_agent/agent/analysis_plan_contracts.py tests/test_strategy_contracts.py
git commit -m "feat: validate multifile analysis strategies"
```

### Task 3: Role-Specific Prompt Contexts

**Files:**
- Create: `src/data_agent/agent/prompt_contexts.py`
- Modify: `src/data_agent/agent/loop.py`
- Modify: `src/data_agent/agent/prompts.py`
- Create: `tests/test_role_prompt_contexts.py`

- [ ] **Step 1: Write failing prompt visibility tests**

```python
def test_executor_context_excludes_unbound_datasets():
    context = build_executor_context(state(), task=task(dataset_inputs=["banner"]))
    assert "banner" in context
    assert "iap" not in context

def test_synthesizer_context_contains_evidence_not_raw_schema():
    context = build_synthesizer_context(state_with_evidence())
    assert "ev_banner" in context
    assert "raw_columns" not in context
```

- [ ] **Step 2: Verify RED**

Expected: the current generic prompt contains workspace-global data.

- [ ] **Step 3: Implement four context builders**

Create `build_interpreter_context`, `build_planner_context`, `build_executor_context`, and `build_synthesizer_context`. Return compact JSON-safe payloads and artifact IDs; never hydrate unrelated raw datasets.

- [ ] **Step 4: Wire the loop by current phase and task mode**

```python
role_context = build_role_context(
    state=self.context.analysis_state,
    task=current_task,
    user_input=user_input,
)
system = append_role_context(
    base_prompt=self._build_system_prompt(),
    role_context=role_context,
)
```

- [ ] **Step 5: Run prompt and comprehensive flow tests**

Expected: PASS; prompt snapshots contain no hidden datasets.

- [ ] **Step 6: Commit**

```powershell
git add src/data_agent/agent/prompt_contexts.py src/data_agent/agent/loop.py src/data_agent/agent/prompts.py tests/test_role_prompt_contexts.py
git commit -m "feat: build role-specific analysis prompts"
```

### Task 4: Strategy-to-Task DAG Projection

**Files:**
- Modify: `src/data_agent/agent/workflow_projection.py`
- Modify: `src/data_agent/session/task_manager.py`
- Create: `tests/test_strategy_task_dag.py`

- [ ] **Step 1: Write failing dependency tests**

```python
def test_joint_task_is_blocked_by_relationship_validation(manager):
    result = project_strategy_plan(manager, plan_with_joint_relationship_dependency())
    relationship_task = result.tasks_by_step["validate_rel"]
    joint_task = result.tasks_by_step["analyze_joint"]
    assert joint_task["blockedBy"] == [relationship_task["id"]]
```

- [ ] **Step 2: Verify RED**

Expected: current projection handles step IDs but not relationship/strategy dependencies.

- [ ] **Step 3: Add explicit dependency fields**

```python
task = manager.create(
    subject=step["goal"][:120],
    session_id=session_id,
    project_name=project_name,
    analysis_plan_id=plan_id,
    step_id=step["step_id"],
    dataset_inputs=step["dataset_inputs"],
    combination_mode=step["combination_mode"],
    strategy_id=step["strategy_id"],
    opportunity_id=step["opportunity_id"],
    relationship_ids=step.get("relationship_ids", []),
    required_evidence_step_ids=step.get("required_evidence_step_ids", []),
    evidence_requirements=step["evidence_requirements"],
    expected_output=step["expected_output"],
    task_kind="plan_task",
)
```

Project `blockedBy` edges from relationship checks and evidence dependencies. Reject cycles before persisting tasks.

- [ ] **Step 4: Run DAG and projection tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/workflow_projection.py src/data_agent/session/task_manager.py tests/test_strategy_task_dag.py
git commit -m "feat: project analysis strategies into task dags"
```

### Task 5: Plan Replacement and Replanning

**Files:**
- Create: `src/data_agent/agent/replanning.py`
- Modify: `src/data_agent/session/task_manager.py`
- Modify: `src/data_agent/agent/loop.py`
- Create: `tests/test_stage3c0b_replanning.py`

- [ ] **Step 1: Write failing replacement tests**

```python
def test_join_coverage_failure_replaces_plan_atomically(manager):
    old = seed_active_plan(manager, status="in_progress")
    decision = decide_replan(join_coverage=0.42, minimum_coverage=0.80)
    assert decision.reason_code == "join_coverage_failed"
    result = replace_active_plan(manager, old_plan_id=old["plan_id"], new_plan=fallback_plan(), session_id="s1", project_name="p1")
    assert all(task["status"] == "superseded" for task in manager.tasks_for_plan(old["plan_id"]))
    assert result["created"] > 0
```

- [ ] **Step 2: Verify RED**

Expected: no canonical ReplanDecision exists.

- [ ] **Step 3: Implement deterministic triggers and atomic replacement**

```python
@dataclass(frozen=True)
class ReplanDecision:
    required: bool
    reason_code: str = ""
    affected_step_ids: tuple[str, ...] = ()

def replace_active_plan(manager, *, old_plan_id, new_plan, session_id, project_name):
    manager.supersede_plan_exact(old_plan_id, session_id=session_id, project_name=project_name)
    return project_plan_to_workflow_tasks(manager, new_plan, session_id=session_id, project_name=project_name)
```

Do not auto-expand scope or use fuzzy fields as a fallback.

- [ ] **Step 4: Run replanning, task-manager, and loop tests**

Expected: PASS with exactly one active plan.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/replanning.py src/data_agent/session/task_manager.py src/data_agent/agent/loop.py tests/test_stage3c0b_replanning.py
git commit -m "feat: replan multifile analysis atomically"
```

### Task 6: Sufficiency and Evidence-Only Synthesis

**Files:**
- Create: `src/data_agent/agent/analysis_sufficiency.py`
- Modify: `src/data_agent/agent/synthesis_policy.py`
- Modify: `src/data_agent/agent/loop.py`
- Modify: `src/data_agent/agent/analysis_state.py`
- Create: `tests/test_stage3c0b_sufficiency.py`

- [ ] **Step 1: Write failing sufficiency tests**

```python
def test_sufficiency_uses_explicit_question_ids_not_token_overlap():
    result = evaluate_analysis_sufficiency(
        plan_id="plan_1",
        required_question_ids=["q_banner", "q_iap"],
        evidence_records=[evidence(question_ids=["q_banner"], plan_id="plan_1")],
        task_records=[completed_task("step_banner")],
        verification_reports=[{"overall_status": "pass"}],
    )
    assert result.status == "needs_more_analysis"
    assert result.uncovered_question_ids == ("q_iap",)
```

- [ ] **Step 2: Verify RED**

Expected: missing module.

- [ ] **Step 3: Implement evidence and question coverage**

```python
@dataclass(frozen=True)
class SufficiencyResult:
    status: str
    uncovered_question_ids: tuple[str, ...] = ()
    missing_evidence_step_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
```

Question coverage must use explicit question/opportunity IDs from EvidenceRecords, not token overlap heuristics. Only `ready_for_synthesis` permits a full final answer; `needs_more_analysis` creates a bounded follow-up plan; `blocked_by_missing_data` permits a partial answer with limitations and next steps.

- [ ] **Step 4: Run sufficiency and synthesis tests**

Expected: PASS and synthesis never reads raw workspace data.

- [ ] **Step 5: Commit**

```powershell
git add src/data_agent/agent/analysis_sufficiency.py src/data_agent/agent/synthesis_policy.py src/data_agent/agent/loop.py src/data_agent/agent/analysis_state.py tests/test_stage3c0b_sufficiency.py
git commit -m "feat: gate synthesis on explicit evidence coverage"
```

### Task 7: Execution Quality Regression Gate

**Files:**
- Create: `tests/test_analysis_opportunity_execution_regression.py`

- [ ] **Step 1: Add end-to-end tests**

```python
def test_validated_high_value_joint_opportunity_reaches_evidence(workflow_fixture):
    result = workflow_fixture.run(opportunity=validated_joint_opportunity(score=0.92))
    assert result.strategy["requires_confirmation"] is False
    assert result.task_modes == ["joint", "synthesis"]
    assert result.evidence_records
    assert result.sufficiency.status == "ready_for_synthesis"
```

- [ ] **Step 2: Run all foundation and execution suites**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
& 'D:\Project\Daily\data-agent\.venv\Scripts\python.exe' -m pytest tests/test_analysis_opportunities.py tests/test_strategy_contracts.py tests/test_role_prompt_contexts.py tests/test_strategy_task_dag.py tests/test_stage3c0b_replanning.py tests/test_stage3c0b_sufficiency.py tests/test_analysis_opportunity_execution_regression.py tests/test_verification_layer.py tests/test_synthesis_policy.py -q
```

Expected: zero failures, no old-plan task remains actionable, and every confirmed conclusion references current-plan evidence.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_analysis_opportunity_execution_regression.py
git commit -m "test: gate analysis opportunity execution"
```
