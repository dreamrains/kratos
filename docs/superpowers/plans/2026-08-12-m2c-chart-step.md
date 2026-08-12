# M2-C (Chart Step) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Make the analysis agent generate charts again. Root cause: the method plan has NO visualization step, and plan-completeness is now enforced (unlike 7/11), so the agent never calls `create_chart`. Fix: append one `visual.chart` step in `_build_analysis_plan`, making charting part of method-completeness.

**Architecture:** `visual.chart` is already registered for `create_chart` (registry.py:545), already in the capability categories (registry.py:570/572-576), already accepted by the executable-plan validator, and the binder already maps `create_chart`→`visual.chart` (analysis_execution.py:223). The only missing piece is the step itself. Single emission point: `_build_analysis_plan` (method_playbooks.py:1057-1157). The existing `chart_suggestions`/`visualization_strategy` already tell the agent WHAT to chart; the new step makes charting required.

**Tech Stack:** Python 3.12, pytest. Source `src/data_agent/`.

**Spec:** `docs/superpowers/specs/2026-08-12-m2-rigor-richness-design.md` (M2-C, method-completeness).

## Global Constraints

- Chinese-language product.
- Single-point change: append the step in `_build_analysis_plan` only (method_playbooks.py:1079 area). Do NOT edit every playbook template.
- Do NOT touch the `visual.chart` registration / validator / binder — they already work.
- Offline suite green; release gates A–D PASS.
- Branch from `main`; one commit.

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/data_agent/agent/method_playbooks.py` | append a `visual.chart` step in `_build_analysis_plan` (:1079) | Task 1 |
| `tests/test_method_playbooks.py` | update the step-count assertion (:554) + add a chart-step-present assertion | Task 1 |

---

### Task 1: Append a visualization step to every analysis method plan

**Files:**
- Modify: `src/data_agent/agent/method_playbooks.py` (`_build_analysis_plan`, insert after the supporting-check append loop ~:1079, before the `if not steps:` fallback ~:1080-1081)
- Test: `tests/test_method_playbooks.py` (update `:554` count; add chart-step assertion)

**Interfaces:** produces plans whose `method_plan` always ends with a `visual.chart` step.

- [ ] **Step 1: Read `_build_analysis_plan` (method_playbooks.py:1057-1157)**

Confirm the steps list is built at :1065-1079 and emitted at :1138. Confirm the insertion point (after supporting-check appends, before the empty-fallback). Confirm `_step_conflicts_with_constraints` (:1003-1035) never filters `visual.chart`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_method_playbooks.py — add
def test_analysis_plan_includes_visualization_step():
    """Every analysis method plan ends with a visual.chart step so the agent
    generates charts as part of method-completeness (create_chart maps to
    visual.chart)."""
    from data_agent.agent.method_playbooks import _build_analysis_plan  # or select_playbooks/build_plan — use the real entry the existing tests use
    plan = _build_analysis_plan(...)   # adapt to the real signature/call used by tests at :554
    caps = [step.get("required_capability") for step in plan["method_plan"]]
    assert "visual.chart" in caps
    chart_step = next(s for s in plan["method_plan"] if s.get("required_capability") == "visual.chart")
    assert chart_step.get("expected_output")  # non-empty
```

(Adapt the plan-build call to the real one used in `tests/test_method_playbooks.py` around :554 — mirror it. Contract: the plan's method_plan contains a `visual.chart` step.)

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_method_playbooks.py -k "visualization_step" -q`
Expected: FAIL (no visual.chart step today).

- [ ] **Step 4: Append the step**

In `_build_analysis_plan`, after the supporting-check append loop and before the empty-fallback, append:

```python
steps.append({
    "step": "visualize key findings",
    "node_type": "evidence",
    "required_capability": "visual.chart",
    "expected_output": "chart artifact(s) for the headline findings",
    "evidence_requirements": ["chart"],
})
```

(If the existing step dicts use additional keys like `step_id`/`goal`/`category`, match their shape so downstream code is consistent — read one existing step and mirror its keys, keeping `required_capability="visual.chart"`.)

- [ ] **Step 5: Update the step-count assertion + run tests**

Update `tests/test_method_playbooks.py:554` (`len(first_tasks) == len(plan["method_plan"])`) to the new count (+1), or relax it to `>=` if it pins an exact count. Run: `uv run pytest tests/test_method_playbooks.py -q`. Expected PASS.

- [ ] **Step 6: Full offline + release gates**

Run: `uv run pytest tests/ -q` (green; known golden flake in isolation) + `uv run python scripts/run_analysis_release_gates.py --profile deterministic` (overall_status PASS).

- [ ] **Step 7: Commit**

```bash
git add src/data_agent/agent/method_playbooks.py tests/test_method_playbooks.py
git commit -m "feat(plan): add a visualization step to every analysis method plan

The method plan had no chart/visualization step, and plan-completeness is
now enforced, so the agent never called create_chart (charts absent).
Append a visual.chart step in _build_analysis_plan — create_chart already
maps to visual.chart and the validator/binder already accept it. Charting
is now part of method-completeness."
```

---

### Task 2: M2-C verification (offline + live)

- [ ] **Step 1:** (covered by Task 1 Step 6 — offline green.)
- [ ] **Step 2: Live validation (fresh real-LLM session, 最强砖块记录.xlsx, same prompt)** — confirm ≥1 inline chart renders this run (the critical deliverable), rich method-compliant answer, no placeholders, analysis completes reliably.
- [ ] **Step 3:** Record outcome. If charts present, the project is stable + usable + rigorous + rich (incl. charts): M1 + M1.1 + M2-A + M2-B + M2-C.

## Self-Review
- Spec coverage: chart absence root cause (no plan step) → Task 1; charts-validated → Task 2.
- Single-point change; reuses already-registered capability; no infrastructure touched.
