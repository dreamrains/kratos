# M2-B (Binding/Scope Race Fix) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Stop the binding/scope race from breaking analysis mid-turn. Symptom (live session `232ddcb78534`): when a task advances to terminal state, the scope layer releases dataset access, so later tool calls (e.g. `create_chart`) get `current_task_dataset_unavailable` ("Dataset X is bound to the current task but is not loaded") → charts fail, and on bad luck the whole turn aborts. Fix: make `current_task_dataset_unavailable` ADVISORY (log + allow), exactly as M1 Task 2 did for `dataset_outside_current_task_scope`. This unblocks reliable completion + chart generation — the critical path the user flagged.

**Architecture:** identical pattern to M1 Task 2. The scope guard (`loop.py _create_scope_guard_descriptor` → `execution_scope.ensure_dataset_*`) returns a blocking `current_task_dataset_unavailable`; convert every emission to record an advisory warning + allow. The dataset IS still in the workspace (the agent re-registered it mid-turn; the binding is stale, the data is present), so allowing access is correct. The advisory warning is retained for observability (M2-C may use it for the deeper binding redesign).

**Tech Stack:** Python 3.12, pytest. Source `src/data_agent/`.

**Spec:** `docs/superpowers/specs/2026-08-12-m2-rigor-richness-design.md` (M2-B section).

## Global Constraints

- Chinese-language product; no English fallback in published answers.
- Mirror M1 Task 2's advisory pattern (`record_advisory_scope_warning` in `execution_scope.py` — reuse it).
- Do NOT touch `derived_scope_not_registered` (different, legitimate guard).
- Offline suite green; release gates A–D PASS.
- Branch from `main`; one commit per task.

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/data_agent/agent/execution_scope.py` | the `current_task_dataset_unavailable` emission points (:461, :720, :784, :801) → advisory | Task 1 |
| `tests/test_assurance_overlay_m1.py` | advisory-contract test | Task 1 |
| `tests/test_scoped_workspace.py` / `tests/test_stage3c0b_execution_scope.py` | update block-assertions to advisory | Task 1 |

---

### Task 1: Make `current_task_dataset_unavailable` advisory

**Files:**
- Modify: `src/data_agent/agent/execution_scope.py` (~:461, :720, :784, :801)
- Test: `tests/test_assurance_overlay_m1.py`; update `tests/test_scoped_workspace.py`, `tests/test_stage3c0b_execution_scope.py`

**Interfaces:** consumes the existing `record_advisory_scope_warning` (M1 Task 2); produces allowed scope-guard results for the previously-blocking case.

- [ ] **Step 1: Read-first — locate every emission**

`grep -n "current_task_dataset_unavailable" src/data_agent/agent/execution_scope.py` → 4 sites (:461, :720, :784, :801). Read each function. Confirm each returns a blocking `ScopeGuardResult(False, "current_task_dataset_unavailable", ...)`.

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_assurance_overlay_m1.py
def test_unavailable_dataset_is_advisory_not_blocking():
    """When the scope layer believes a dataset is 'bound to the current task
    but not loaded' (the stale-binding race on terminal task state), the guard
    must ALLOW access with a recorded warning, not block — so mid-analysis tool
    calls (e.g. create_chart) don't abort the turn."""
    from data_agent.agent.execution_scope import (
        consume_advisory_scope_warnings,
        ensure_dataset_allowed_for_current_task,
    )
    consume_advisory_scope_warnings()
    # Build a TaskManager + task whose scope references a dataset that is NOT
    # in the active workspace (the 'bound but not loaded' state). Adapt names
    # to the real API found in Step 1 — mirror test_out_of_scope_dataset_is_allowed_with_warning.
    manager = ...  # as in the M1 Task 2 test
    denied = ensure_dataset_allowed_for_current_task(manager, "<session>", dataset="<not-loaded-name>")
    assert denied.allowed is True
    assert "current_task_dataset_unavailable" not in (denied.message or "")
    warnings = consume_advisory_scope_warnings()
    assert any(w["warning"] == "current_task_dataset_unavailable" for w in warnings)
```

(Adapt the manager/dataset setup to the real `ensure_dataset_allowed_for_current_task` signature used in the existing M1 Task 2 test `test_out_of_scope_dataset_is_allowed_with_warning`. Contract: the previously-blocking case now allows + records a warning.)

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_assurance_overlay_m1.py::test_unavailable_dataset_is_advisory_not_blocking -q`
Expected: FAIL (current code blocks).

- [ ] **Step 4: Convert the 4 emission sites to advisory**

At each of the 4 sites, replace the blocking `return ScopeGuardResult(False, "current_task_dataset_unavailable", ...)` with `record_advisory_scope_warning(<dataset>, task_id=...)` + `return ScopeGuardResult(True)`. Reuse the M1 Task 2 `record_advisory_scope_warning` helper (extend its symbol set if it currently only records `dataset_outside_current_task_scope` — accept the symbol as a parameter or add a sibling recorder). Keep `derived_scope_not_registered` blocking.

- [ ] **Step 5: Run test + scoped-workspace regression**

Run: `uv run pytest tests/test_assurance_overlay_m1.py tests/test_scoped_workspace.py tests/test_stage3c0b_execution_scope.py -q`
Expected: PASS; update tests that asserted `current_task_dataset_unavailable` as a block → assert advisory (allow + warning). Do not delete; repurpose.

- [ ] **Step 6: Commit**

```bash
git add src/data_agent/agent/execution_scope.py tests/
git commit -m "fix(scope): make current_task_dataset_unavailable advisory

When a task advances to terminal state the scope layer released dataset
access, so mid-analysis tool calls (create_chart) got
'current_task_dataset_unavailable' and charts failed / turns aborted. The
dataset is still in the workspace (stale binding, present data), so allow
access with a recorded warning — mirroring M1 Task 2's advisory treatment
of dataset_outside_current_task_scope."
```

---

### Task 2: M2-B verification (offline + live)

**Files:** none (verification only)

- [ ] **Step 1: Full offline suite + release gates**

Run: `uv run pytest tests/ -q` (green, known golden flake in isolation) + `uv run python scripts/run_analysis_release_gates.py --profile deterministic` (overall_status PASS).

- [ ] **Step 2: Live validation (fresh real-LLM session, 最强砖块记录.xlsx, same prompt)**

Confirm:
- The analysis completes reliably (no `current_task_dataset_unavailable` abort).
- Charts ARE generated this run (≥1 inline chart renders) — the critical deliverable.
- Rich method-compliant answer (M2-A richness preserved), no `无法发布` placeholders.
- Conclusions data-grounded; footer absent or meaningful.

- [ ] **Step 3: Record outcome.** If green + charts present, the project is stable + usable + rigorous + rich (M1 + M1.1 + M2-A + M2-B). Note whether the deeper best-effort binding (M2-C, for meaningful per-claim annotations) is still desired.

---

## Deferred (M2-C, optional — only if meaningful per-claim annotations are wanted)

Best-effort `bind_tool_call_to_plan_step` (attribute supporting tools to the active step; dedup capabilities) → projection produces real measurement identity → audit verifies real claims → meaningful per-claim footer. This is the harder, codex-resistant piece; NOT required for stability/usability/richness (delivered by M1+M2-A+M2-B). Pursue only if the user wants the rigor annotations beyond the current honest data-grounded disclosure.

## Self-Review

- Spec coverage: the binding/scope race (the live-blocker) → Task 1; reliable completion + charts → Task 2. The deeper binding redesign is explicitly deferred (M2-C) — honest scoping.
- Pattern reuse: Task 1 mirrors M1 Task 2 (proven, reviewed-clean approach).
