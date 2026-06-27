# Multi-File Scope Workbench Stage 3AB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace relationship-first multi-file blocking with participation-first scope and user-facing workbench state.

**Architecture:** `multi_file_scope.py` becomes the source of truth for file participation groups, while relationship records remain diagnostics. `trust_view.py` maps the scope plan into workbench display groups and non-actionable relationship diagnostics. The web sidebar reads the new groups and only labels something as action needed when the confirmation runtime has an active pending confirmation.

**Tech Stack:** Python dataclass-backed session state, pytest, Alpine.js template helpers, static JavaScript syntax validation with Node.

---

## File Structure

- Modify: `src/data_agent/agent/multi_file_scope.py`
  - Owns participation classification, compatibility fields, context budget counts, and diagnostic notes.
- Modify: `src/data_agent/agent/trust_view.py`
  - Owns workbench projection, relationship diagnostics, and empty-view compatibility.
- Modify: `src/data_agent/web/templates/index.html`
  - Owns visible right-panel wording and whether relationship diagnostics look actionable.
- Modify: `src/data_agent/web/static/js/app.js`
  - Owns formatting helpers and Chinese labels for participation and diagnostics.
- Modify: `tests/test_multi_file_scope.py`
  - Updates old relationship-first assertions and adds participation-first coverage.
- Modify: `tests/test_multifile_regressions.py`
  - Adds regression coverage for orphan relationship flags and workbench grouping.
- Modify: `tests/test_web_overhaul.py`
  - Adds or updates sidebar wording assertions if existing fixture coverage reaches the relevant template fragments.

## Task 1: Stage 3A Scope Contract Tests

**Files:**
- Modify: `tests/test_multi_file_scope.py`
- Modify: `tests/test_multifile_regressions.py`

- [ ] **Step 1: Write failing scope tests**

In `tests/test_multi_file_scope.py`, change the old relationship-pending assertion so `coupon` is included and relationship evidence is a note:

```python
assert [item["file_id"] for item in plan["included_files"]] == ["orders", "coupon"]
assert plan["decision_files"] == []
assert plan["pending_files"] == []
assert [item["file_id"] for item in plan["unused_files"]] == ["game"]
assert plan["scope_status"] == "ready_with_notes"
assert any("coupon" in note and "join" in note.lower() for note in plan["notes"])
```

In `tests/test_multifile_regressions.py`, update `test_scope_plan_keeps_orders_and_coupon_profiles_linkable_by_user_aliases`:

```python
assert [item["file_id"] for item in plan["included_files"]] == ["orders", "coupon"]
assert plan["decision_files"] == []
assert plan["pending_files"] == []
assert plan["scope_status"] == "ready_with_notes"
assert any("coupon" in note and "join" in note.lower() for note in plan["notes"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path; .\.venv\Scripts\python.exe -m pytest tests/test_multi_file_scope.py::test_scope_plan_includes_relevant_user_files_and_excludes_unrelated_game_file tests/test_multifile_regressions.py::test_scope_plan_keeps_orders_and_coupon_profiles_linkable_by_user_aliases -q
```

Expected: FAIL because `coupon` is still in `pending_files` and `scope_status` is still `needs_confirmation`.

## Task 2: Stage 3A Minimal Backend Implementation

**Files:**
- Modify: `src/data_agent/agent/multi_file_scope.py`

- [ ] **Step 1: Implement participation groups**

Update `build_analysis_scope_plan` to derive:

```python
included_files = [item["summary"] for item in returned if item["participation"] == "included"]
available_files = [item["summary"] for item in returned if item["participation"] == "available"]
unused_files = [item["summary"] for item in returned if item["participation"] == "unused"]
decision_files = [item["summary"] for item in returned if item["participation"] == "needs_scope_decision"]
unavailable_files = [item["summary"] for item in returned if item["participation"] == "unavailable"]
pending_files = decision_files
notes = _dedupe([
    note
    for item in returned
    for note in _relationship_diagnostic_notes(item["summary"], item["relationship"])
])
```

Update status derivation:

```python
if any(item["participation"] == "unavailable" for item in classified):
    scope_status = "blocked"
elif any(item["participation"] == "needs_scope_decision" for item in classified):
    scope_status = "needs_decision"
elif notes or available_files or unused_files:
    scope_status = "ready_with_notes"
else:
    scope_status = "ready"
```

- [ ] **Step 2: Replace relationship-first classification**

Update `_classify_scope_file` so relationship status never creates a scope decision:

```python
if not file_id:
    participation, priority = "unavailable", 6
elif _is_explicitly_unrelated(profile, goal):
    participation, priority = "unused", 5
elif file_id in active_file_ids:
    participation, priority = "included", 0
elif _relationship_is_confirmed(relationship):
    participation, priority = "included", 1
elif _has_strong_goal_theme_overlap(profile, goal):
    participation, priority = "included", 2
else:
    participation, priority = "available", 4
```

Keep `scope` as a compatibility alias:

```python
"scope": _legacy_scope(participation),
"participation": participation,
```

with:

```python
def _legacy_scope(participation: str) -> str:
    if participation == "included":
        return "included"
    if participation in {"unused", "unavailable"}:
        return "excluded"
    if participation == "needs_scope_decision":
        return "pending"
    return "available"
```

- [ ] **Step 3: Run focused tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path; .\.venv\Scripts\python.exe -m pytest tests/test_multi_file_scope.py tests/test_multifile_regressions.py -q
```

Expected: either PASS or remaining failures that point to old assertions needing update to the new contract.

## Task 3: Finish Scope Test Migration

**Files:**
- Modify: `tests/test_multi_file_scope.py`
- Modify: `tests/test_multifile_regressions.py`
- Modify: `src/data_agent/agent/multi_file_scope.py`

- [ ] **Step 1: Update old pending semantics**

Update tests that previously expected ambiguous or historical files in `pending_files`:

```python
assert [item["file_id"] for item in plan["available_files"]] == ["ambiguous"]
assert plan["decision_files"] == []
assert plan["pending_files"] == []
assert plan["scope_status"] == "ready_with_notes"
```

For user alias fields in available files:

```python
assert [item["file_id"] for item in plan["available_files"]] == [f"profile_{alias}"]
assert plan["pending_files"] == []
assert any(alias in note for note in plan["notes"])
```

- [ ] **Step 2: Preserve deterministic budget behavior**

Update context budget assertions to include new counts:

```python
"available_file_count": len(plan["available_files"]),
"unused_file_count": len(plan["unused_files"]),
"decision_file_count": len(plan["decision_files"]),
"unavailable_file_count": len(plan["unavailable_files"]),
```

- [ ] **Step 3: Re-run scope tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path; .\.venv\Scripts\python.exe -m pytest tests/test_multi_file_scope.py tests/test_multifile_regressions.py -q
```

Expected: PASS.

## Task 4: Stage 3B Workbench Contract Tests

**Files:**
- Modify: `tests/test_multifile_regressions.py`

- [ ] **Step 1: Add failing workbench regression**

In `test_orphan_relationship_flag_does_not_create_an_actionable_confirmation_gate`, add:

```python
context = view["workbench"]["current_context"]
assert context["decision_files"] == []
assert context["pending_files"] == []
assert view["workbench"]["relationship_diagnostics"][0]["actionable"] is False
assert "active confirmation" in view["workbench"]["relationship_diagnostics"][0]["note"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path; .\.venv\Scripts\python.exe -m pytest tests/test_multifile_regressions.py::test_orphan_relationship_flag_does_not_create_an_actionable_confirmation_gate -q
```

Expected: FAIL because `relationship_diagnostics` and `decision_files` are not exposed yet.

## Task 5: Stage 3B Workbench Backend Implementation

**Files:**
- Modify: `src/data_agent/agent/trust_view.py`

- [ ] **Step 1: Extend empty and normal workbench context**

Add these fields to normal and empty workbench current context:

```python
"available_files": _list_items(plan.get("available_files")),
"unused_files": _list_items(plan.get("unused_files")),
"decision_files": _list_items(plan.get("decision_files")),
"unavailable_files": _list_items(plan.get("unavailable_files")),
"notes": _text_list(plan.get("notes")),
```

- [ ] **Step 2: Add relationship diagnostics**

Add to `_workbench_summary`:

```python
"relationship_diagnostics": _relationship_diagnostics(_list_attr(state, "file_relationships"), confirmation_gate),
```

Implement:

```python
def _relationship_diagnostics(relationships: list[dict[str, Any]], confirmation_gate: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    active_type = _text(confirmation_gate.get("confirmation_type"))
    diagnostics = []
    for relationship in reversed(relationships):
        relationship_id = _text(relationship.get("relationship_id") or relationship.get("id"))
        if not relationship_id:
            continue
        actionable = (
            _text(relationship.get("confirmation_type")) == active_type
            and _text(confirmation_gate.get("status")) == "needs_confirmation"
        )
        diagnostics.append({
            "relationship_id": relationship_id,
            "status": _text(relationship.get("status")),
            "actionable": actionable,
            "note": "Requires the active confirmation card." if actionable else "Historical relationship metadata; not an active confirmation.",
            "file_ids": _text_list(relationship.get("file_ids"))[:3],
            "evidence": _text_list(relationship.get("evidence"))[:2],
            "uncertainties": _text_list(relationship.get("uncertainties"))[:2],
        })
        if len(diagnostics) >= limit:
            break
    return diagnostics
```

- [ ] **Step 3: Run workbench backend tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path; .\.venv\Scripts\python.exe -m pytest tests/test_multifile_regressions.py tests/test_confirmation_session_api.py -q
```

Expected: PASS.

## Task 6: Stage 3B Sidebar Wording And Helper Tests

**Files:**
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `tests/test_web_overhaul.py`

- [ ] **Step 1: Add or update web wording assertion**

If `tests/test_web_overhaul.py` has static template tests, add assertions that the template contains user-facing wording:

```python
assert "本次使用" in template
assert "可用但本次暂未使用" in template
assert "技术关系说明" in template
assert "等待确认" not in relationship_section_without_confirmation
```

- [ ] **Step 2: Run web test to verify it fails**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path; .\.venv\Scripts\python.exe -m pytest tests/test_web_overhaul.py -q
```

Expected: FAIL if old relationship-first sidebar wording is still present.

- [ ] **Step 3: Update template and JS helpers**

In `index.html`, replace primary context rendering with:

```html
<p x-show="formatWorkbenchFiles(workbenchContext().included_files)" x-text="'本次使用：' + formatWorkbenchFiles(workbenchContext().included_files)"></p>
<p x-show="formatWorkbenchFiles(workbenchContext().available_files)" x-text="'可用但本次暂未使用：' + formatWorkbenchFiles(workbenchContext().available_files)"></p>
<p x-show="formatWorkbenchFiles(workbenchContext().unused_files)" x-text="'未使用：' + formatWorkbenchFiles(workbenchContext().unused_files)"></p>
<p x-show="formatWorkbenchFiles(workbenchContext().decision_files)" x-text="'需要你决定：' + formatWorkbenchFiles(workbenchContext().decision_files)"></p>
<p x-show="workbenchContext().notes && workbenchContext().notes.length" x-text="'说明：' + workbenchContext().notes.join('；')"></p>
```

Move relationship display under "技术关系说明" and render non-actionable diagnostics with wording that does not say waiting confirmation unless `diagnostic.actionable` is true.

- [ ] **Step 4: Validate JavaScript syntax**

Run:

```powershell
node -c src/data_agent/web/static/js/app.js
```

Expected: exit code 0.

## Task 7: Full Verification And Commit

**Files:**
- All modified files from previous tasks

- [ ] **Step 1: Run focused Python regression suite**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path; .\.venv\Scripts\python.exe -m pytest tests/test_multi_file_scope.py tests/test_multifile_regressions.py tests/test_confirmation_session_api.py tests/test_web_overhaul.py::TestConfirmationRuntimeRestore tests/test_web_overhaul.py::TestConfirmationWorkbenchWording tests/test_web_workbench_parity.py -q
```

Expected: PASS.

- [ ] **Step 2: Run JavaScript syntax check**

Run:

```powershell
node -c src/data_agent/web/static/js/app.js
```

Expected: exit code 0.

- [ ] **Step 3: Inspect diff**

Run:

```powershell
git diff --stat
git diff --check
```

Expected: only Stage 3A/3B files changed and no whitespace errors.

- [ ] **Step 4: Commit**

Run:

```powershell
git add docs/superpowers/plans/2026-06-26-multifile-scope-workbench-stage-3ab.md src/data_agent/agent/multi_file_scope.py src/data_agent/agent/trust_view.py src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js tests/test_multi_file_scope.py tests/test_multifile_regressions.py tests/test_web_overhaul.py
git commit -m "feat: separate multifile scope from relationships"
```

Expected: commit succeeds on branch `codex/multifile-scope-workbench-stage-3ab`.
