# Multi-File Analysis Stage 3C0A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace relationship-driven multi-file participation with a deterministic eligibility-and-assignment contract, remove obsolete relationship confirmations, and expose one explainable, bounded scope truth through the confirmation runtime and workbench.

**Architecture:** `multi_file_scope.py` remains the sole owner of file eligibility and current assignment. It derives technical eligibility from data-pool and dataset-contract state, derives `used` only from explicit AnalysisPlan dataset bindings, and emits material file-choice decisions without using relationship evidence. Existing relationship records remain diagnostic only; the existing confirmation runtime asks real scope-selection questions, while trust view and the web workbench become projections of the new contract.

**Tech Stack:** Python 3.11+, dataclasses/dicts, pytest, Flask view models, Alpine.js templates, existing confirmation runtime, PowerShell verification commands.

---

## Scope Boundary

This plan implements Stage 3C0A only.

It does not:

- add `dataset_inputs` validation to AnalysisPlan or workflow tasks;
- execute independent multi-dataset tasks;
- implement join planning or execution;
- change EvidenceRecord lineage;
- implement union, aggregate comparison, entity mapping, or automatic repair.

Stage 3C0A may read `dataset_inputs` from an already structured plan to derive
assignment, but writing and enforcing those bindings belongs to Stage 3C0B.

## Final Contract For This Slice

`build_analysis_scope_plan()` returns:

```python
{
    "scope_status": "ready_with_notes",
    "goal": "analyze all uploaded files",
    "file_decisions": [],
    "eligible_files": [],
    "used_files": [],
    "available_files": [],
    "not_needed_files": [],
    "decision_files": [],
    "unavailable_files": [],
    "notes": [],
    "context_budget": {
        "eligible_file_count": 0,
        "used_file_count": 0,
        "available_file_count": 0,
        "not_needed_file_count": 0,
        "decision_file_count": 0,
        "unavailable_file_count": 0,
        "total_file_count": 0,
        "returned_file_count": 0,
        "omitted_file_count": 0,
        "max_scope_files": 5,
    },
}
```

Each item in `file_decisions` contains:

```python
{
    "file_id": "file_orders",
    "filename": "orders.csv",
    "dataset": "orders",
    "dataset_contract_id": "duc_orders",
    "grain": "order_level",
    "canonical_fields": {"user": ["user_id"], "order": ["order_id"], "coupon": [], "time": []},
    "eligibility": "eligible",
    "assignment": "available",
    "reason_code": "explicit_in_scope_pending_plan",
    "reason": "The file is explicitly in scope and is waiting for an analysis task binding.",
    "confidence": "high",
    "task_refs": [],
}
```

The group arrays contain compact references, not a second copy of the full
decision:

```python
{
    "file_id": "file_orders",
    "filename": "orders.csv",
    "dataset": "orders",
    "reason_code": "plan_task_binding",
}
```

`file_decisions` is the user-facing detail source. Group arrays exist for fast
status checks, confirmation options, and counts without duplicating grain,
canonical fields, reasons, confidence, and task refs.

Remove `included_files`, `unused_files`, `excluded_files`, `pending_files`, and
`assumptions` from the final contract and all first-party consumers. Do not keep
them as long-lived aliases.

## Reason Codes

Use only these Stage 3C0A reason codes:

```python
REASON_MISSING_FILE_IDENTITY = "missing_file_identity"
REASON_LOAD_FAILED = "load_failed"
REASON_MISSING_DATASET_CONTRACT = "missing_dataset_contract"
REASON_CONTRACT_BLOCKED = "contract_blocked"
REASON_AMBIGUOUS_FILE_REFERENCE = "ambiguous_file_reference"
REASON_EXPLICIT_USER_EXCLUSION = "explicit_user_exclusion"
REASON_PLAN_TASK_BINDING = "plan_task_binding"
REASON_NO_CURRENT_TASK = "no_current_task"
REASON_EXPLICIT_IN_SCOPE_PENDING_PLAN = "explicit_in_scope_pending_plan"
REASON_EXPLICIT_ALL_PENDING_PLAN = "explicit_all_pending_plan"
REASON_ELIGIBLE_NOT_YET_ASSIGNED = "eligible_not_yet_assigned"
```

---

### Task 1: Replace Mixed Participation With Eligibility And Assignment

**Files:**
- Modify: `src/data_agent/agent/multi_file_scope.py`
- Modify: `tests/test_multi_file_scope.py`
- Modify: `tests/test_multifile_regressions.py`

- [ ] **Step 1: Replace relationship-oriented scope tests with failing contract tests**

Add helpers and tests that provide real dataset-contract refs:

```python
def _add_contract(state, dataset, *, status="ready"):
    state.dataset_contracts.append({
        "id": f"duc_{dataset}",
        "dataset": dataset,
        "quality_status": status,
    })


def test_scope_separates_eligibility_from_plan_assignment():
    state = AnalysisSessionState(session_id="scope_contract", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "orders", "filename": "orders.csv", "dataset": "orders", "status": "loaded"},
        {"file_id": "users", "filename": "users.csv", "dataset": "users", "status": "loaded"},
        {"file_id": "campaigns", "filename": "campaigns.csv", "dataset": "campaigns", "status": "loaded"},
    ]
    for dataset in ("orders", "users", "campaigns"):
        _add_contract(state, dataset)
    state.analysis_plan = {
        "method_plan": [
            {"step_id": "task_orders", "dataset_inputs": ["orders"]},
            {"step_id": "task_users", "dataset_inputs": ["users"]},
        ]
    }

    plan = build_analysis_scope_plan(state, "analyze orders, users, and campaigns")

    assert [item["file_id"] for item in plan["eligible_files"]] == ["orders", "users", "campaigns"]
    assert [item["file_id"] for item in plan["used_files"]] == ["orders", "users"]
    assert [item["file_id"] for item in plan["not_needed_files"]] == ["campaigns"]
    assert plan["used_files"][0]["reason_code"] == "plan_task_binding"
    assert plan["not_needed_files"][0]["reason_code"] == "no_current_task"
    assert "included_files" not in plan
    assert "pending_files" not in plan


def test_scope_keeps_explicit_files_available_until_plan_has_bindings():
    state = AnalysisSessionState(session_id="scope_pending_plan", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "orders", "filename": "orders.csv", "dataset": "orders", "status": "loaded"},
        {"file_id": "users", "filename": "users.csv", "dataset": "users", "status": "loaded"},
    ]
    _add_contract(state, "orders")
    _add_contract(state, "users")
    state.analysis_plan = {"method_plan": [{"step": "legacy step without dataset bindings"}]}

    plan = build_analysis_scope_plan(state, "analyze orders.csv and users.csv")

    assert plan["used_files"] == []
    assert [item["reason_code"] for item in plan["available_files"]] == [
        "explicit_in_scope_pending_plan",
        "explicit_in_scope_pending_plan",
    ]


def test_relationship_flags_never_change_eligibility_or_assignment():
    state = AnalysisSessionState(session_id="scope_relationship_diagnostic", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "orders", "filename": "orders.csv", "dataset": "orders", "status": "loaded"},
        {"file_id": "coupon", "filename": "coupon.csv", "dataset": "coupon", "status": "loaded"},
    ]
    _add_contract(state, "orders")
    _add_contract(state, "coupon")
    state.file_relationships = [{
        "relationship_id": "rel_orders_coupon",
        "file_ids": ["orders", "coupon"],
        "status": "possibly_linked",
        "requires_confirmation": True,
    }]

    plan = build_analysis_scope_plan(state, "analyze the uploaded files")

    assert plan["used_files"] == []
    assert [item["file_id"] for item in plan["available_files"]] == ["orders", "coupon"]
    assert plan["decision_files"] == []


def test_unavailable_optional_file_does_not_block_eligible_work():
    state = AnalysisSessionState(session_id="scope_optional_unavailable", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "orders", "filename": "orders.csv", "dataset": "orders", "status": "loaded"},
        {"file_id": "broken", "filename": "broken.csv", "dataset": "broken", "status": "failed"},
    ]
    _add_contract(state, "orders")

    plan = build_analysis_scope_plan(state, "analyze orders")

    assert plan["scope_status"] == "ready_with_notes"
    assert plan["unavailable_files"][0]["reason_code"] == "load_failed"


def test_unavailable_explicit_file_blocks_scope():
    state = AnalysisSessionState(session_id="scope_required_unavailable", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "broken", "filename": "broken.csv", "dataset": "broken", "status": "failed"},
    ]

    plan = build_analysis_scope_plan(state, "analyze broken.csv")

    assert plan["scope_status"] == "blocked"
    assert plan["unavailable_files"][0]["reason_code"] == "load_failed"
```

- [ ] **Step 2: Run the focused tests and verify the old contract fails**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_multi_file_scope.py `
  tests/test_multifile_regressions.py -q
```

Expected: FAIL because `eligible_files`, `used_files`, `not_needed_files`,
`eligibility`, `assignment`, and reason fields do not exist, and relationship
flags still affect current classification.

- [ ] **Step 3: Implement contract indexing and plan-binding helpers**

Add these helpers to `multi_file_scope.py`:

```python
def _contracts_by_dataset(state: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for contract in _list_items(getattr(state, "dataset_contracts", None)):
        dataset = _text(contract.get("dataset"))
        if dataset:
            result[dataset] = contract
    return result


def _plan_dataset_bindings(state: Any) -> tuple[bool, dict[str, list[str]]]:
    plan = getattr(state, "analysis_plan", None)
    if not isinstance(plan, dict):
        return False, {}
    method_plan = plan.get("method_plan")
    if not isinstance(method_plan, list):
        return False, {}
    has_binding_contract = False
    bindings: dict[str, list[str]] = {}
    for index, step in enumerate(method_plan, start=1):
        if not isinstance(step, dict) or "dataset_inputs" not in step:
            continue
        has_binding_contract = True
        step_id = _text(step.get("step_id")) or f"step_{index}"
        for dataset in _text_list(step.get("dataset_inputs")):
            bindings.setdefault(dataset, []).append(step_id)
    return has_binding_contract, bindings


def _profile_aliases(profile: dict[str, Any]) -> list[str]:
    filename = _text(profile.get("filename") or profile.get("name"))
    stem = re.sub(r"\.[^.]+$", "", filename)
    values = [
        _text(profile.get("file_id") or profile.get("id")),
        filename,
        stem,
        _text(profile.get("dataset") or profile.get("dataset_name")),
    ]
    return _dedupe([_normalize_alias(value) for value in values if value])


def _goal_mentions_profile(profile: dict[str, Any], goal: str) -> bool:
    normalized_goal = _normalize_alias(goal)
    return any(alias and alias in normalized_goal for alias in _profile_aliases(profile))


def _goal_requests_all_files(goal: str) -> bool:
    normalized = _normalize_alias(goal)
    phrases = (
        "alluploadedfiles",
        "allfiles",
        "alluploadeddata",
        "全部上传文件",
        "所有上传文件",
        "全部文件",
        "所有文件",
    )
    return any(_normalize_alias(phrase) in normalized for phrase in phrases)


def _goal_excludes_profile(profile: dict[str, Any], goal: str) -> bool:
    normalized_goal = _normalize_alias(goal)
    exclusion_terms = ("exclude", "ignore", "skip", "排除", "忽略", "不要使用", "不分析")
    for alias in _profile_aliases(profile):
        if not alias:
            continue
        for term in exclusion_terms:
            marker = _normalize_alias(term)
            if f"{marker}{alias}" in normalized_goal or f"{alias}{marker}" in normalized_goal:
                return True
    return False
```

- [ ] **Step 4: Implement eligibility and assignment decisions**

Replace the old relationship-aware classifier with a decision function whose
only inputs are profile, contract, goal, plan bindings, and ambiguous IDs:

```python
def _decide_file(
    profile: dict[str, Any],
    *,
    contract: dict[str, Any] | None,
    goal: str,
    has_binding_contract: bool,
    task_refs: list[str],
    ambiguous_file_ids: set[str],
) -> dict[str, Any]:
    file_id = _text(profile.get("file_id") or profile.get("id"))
    dataset = _text(profile.get("dataset") or profile.get("dataset_name"))
    decision = _file_summary(profile, contract)
    status = _normalize_alias(_text(profile.get("status")))
    if not file_id or not dataset:
        eligibility = "unavailable"
        eligibility_reason_code = "missing_file_identity"
        eligibility_reason = "The file cannot be identified as a usable dataset."
    elif status in {"failed", "error", "unavailable", "unreadable"}:
        eligibility = "unavailable"
        eligibility_reason_code = "load_failed"
        eligibility_reason = "The file could not be loaded or inspected."
    elif contract is None:
        eligibility = "unavailable"
        eligibility_reason_code = "missing_dataset_contract"
        eligibility_reason = "The file has no usable dataset contract."
    elif _text(contract.get("quality_status")) == "blocked":
        eligibility = "unavailable"
        eligibility_reason_code = "contract_blocked"
        eligibility_reason = "The dataset contract blocks analysis until data quality is repaired."
    else:
        eligibility = "eligible"
        eligibility_reason_code = "eligible_not_yet_assigned"
        eligibility_reason = "The file is loaded and has a usable dataset contract."

    assignment = "available"
    reason_code = eligibility_reason_code
    reason = eligibility_reason
    confidence = "high" if eligibility == "unavailable" else "medium"

    if _goal_excludes_profile(profile, goal):
        assignment = "not_needed"
        reason_code = "explicit_user_exclusion"
        reason = "The user explicitly excluded this file from the current analysis."
        confidence = "high"
    elif eligibility == "eligible" and file_id in ambiguous_file_ids:
        assignment = "needs_decision"
        reason_code = "ambiguous_file_reference"
        reason = "The request matches multiple usable files and needs one explicit selection."
        confidence = "high"
    elif eligibility == "eligible" and task_refs:
        assignment = "used"
        reason_code = "plan_task_binding"
        reason = "The current AnalysisPlan binds this file to an analysis task."
        confidence = "high"
    elif eligibility == "eligible" and has_binding_contract:
        assignment = "not_needed"
        reason_code = "no_current_task"
        reason = "The current AnalysisPlan does not need this usable file."
        confidence = "high"
    elif eligibility == "eligible" and _goal_mentions_profile(profile, goal):
        reason_code = "explicit_in_scope_pending_plan"
        reason = "The file is explicitly in scope and is waiting for an analysis task binding."
        confidence = "high"
    elif eligibility == "eligible" and _goal_requests_all_files(goal):
        reason_code = "explicit_all_pending_plan"
        reason = "The user requested all files; this usable file is waiting for a task binding."
        confidence = "high"

    decision.update({
        "eligibility": eligibility,
        "assignment": assignment,
        "reason_code": reason_code,
        "reason": reason,
        "confidence": confidence,
        "task_refs": list(task_refs),
    })
    return decision
```

Change `_file_summary()` so it accepts the matching contract rather than a
relationship and adds `dataset_contract_id`. Do not place relationship metadata
inside a file decision.

- [ ] **Step 5: Build the final bounded scope plan**

Implement `build_analysis_scope_plan()` so it:

1. builds contract and binding indexes;
2. computes ambiguous file IDs with the exact-reference helper introduced in
   Task 4;
3. derives all decisions;
4. prioritizes `needs_decision`, unavailable required files, used, available,
   not-needed, then optional unavailable;
5. returns at most `MAX_SCOPE_FILES` detailed decisions while counts cover all;
6. always retains at least one decision item when one exists;
7. sets `blocked` only when an unavailable file is explicitly referenced or has
   task refs and its assignment is not `not_needed`; an explicitly excluded file
   never blocks the current goal;
8. sets `needs_decision` before `ready_with_notes`;
9. derives all group arrays from `file_decisions`.

Use this grouping code after bounding:

```python
def _group_ref(item: dict[str, Any]) -> dict[str, str]:
    return {
        "file_id": _text(item.get("file_id")),
        "filename": _text(item.get("filename")),
        "dataset": _text(item.get("dataset")),
        "reason_code": _text(item.get("reason_code")),
    }


eligible_files = [_group_ref(item) for item in returned if item["eligibility"] == "eligible"]
used_files = [_group_ref(item) for item in returned if item["assignment"] == "used"]
available_files = [
    _group_ref(item)
    for item in returned
    if item["assignment"] == "available" and item["eligibility"] == "eligible"
]
not_needed_files = [_group_ref(item) for item in returned if item["assignment"] == "not_needed"]
decision_files = [_group_ref(item) for item in returned if item["assignment"] == "needs_decision"]
unavailable_files = [_group_ref(item) for item in returned if item["eligibility"] == "unavailable"]
```

Keep relationship notes out of the primary plan. Technical relationship
diagnostics remain available through `trust_view._relationship_diagnostics()`.

- [ ] **Step 6: Run the scope tests and make them pass**

Run the command from Step 2.

Expected: PASS. The only acceptable warning is pytest cache write denial.

- [ ] **Step 7: Commit the scope contract**

```powershell
git add -- src/data_agent/agent/multi_file_scope.py tests/test_multi_file_scope.py tests/test_multifile_regressions.py
git commit -m "feat: separate file eligibility from analysis assignment"
```

---

### Task 2: Stop Creating Relationship-Driven Scope And Confirmations At Load Time

**Files:**
- Modify: `src/data_agent/tools/data_io.py`
- Modify: `tests/test_data_bundle.py`
- Test: `tests/test_trustworthy_load_data_integration.py`

- [ ] **Step 1: Write failing tests for diagnostic-only relationships**

Replace `test_register_loaded_data_bundle_adds_answerable_file_relationship_confirmation`
and update the active-bundle test:

```python
def test_register_loaded_data_bundle_keeps_relationship_as_diagnostic_only(tmp_path, monkeypatch):
    state = AnalysisSessionState(session_id="file_diagnostic", data_state="data_loaded")
    state.add_data_pool_file({
        "file_id": "file_old",
        "filename": "orders.xlsx",
        "dataset": "orders",
        "key_fields": ["user_id"],
        "status": "loaded",
    })
    state.set_active_bundle({
        "bundle_id": "bundle_session_files",
        "file_ids": ["file_old"],
        "dataset_names": ["orders"],
        "version": 1,
    })
    monkeypatch.setattr(data_io, "_save_trust_state", lambda *_args, **_kwargs: None)

    data_io._register_loaded_data_bundle(
        state=state,
        session_id="file_diagnostic",
        path=tmp_path / "activity.xlsx",
        dataset="activity",
        df=pd.DataFrame({"user_id": [1, 2], "event_time": ["2026-01-01", "2026-01-02"]}),
        contract={
            "id": "duc_activity",
            "field_roles": {"ids": ["user_id"], "date": ["event_time"]},
            "time_range": {},
        },
        user_input="analyze revenue",
    )

    relationship = state.file_relationships[-1]
    assert relationship["diagnostic_only"] is True
    assert relationship["requires_confirmation"] is False
    assert relationship["confirmation_type"] == ""
    assert state.pending_confirmations == []
    assert state.active_bundle()["dataset_names"] == ["orders", "activity"]
    assert state.data_pool[-1]["dataset_contract_id"] == "duc_activity"
```

- [ ] **Step 2: Run load/bundle tests and verify failure**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_data_bundle.py `
  tests/test_trustworthy_load_data_integration.py -q
```

Expected: FAIL because load registration still creates a pending relationship
confirmation and leaves the prior bundle unchanged.

- [ ] **Step 3: Make relationship writes diagnostic-only**

In `_register_loaded_data_bundle()`:

```python
relationship = classify_file_relationship([file_ref], existing_files, user_input=user_input)
relationship.update({
    "relationship_id": f"rel_{file_id}",
    "file_ids": _unique_values(existing_file_ids + [file_id]),
    "diagnostic_only": True,
    "requires_confirmation": False,
    "confirmation_type": "",
})
state.add_file_relationship(relationship)

if previous_bundle:
    state.set_active_bundle({
        **previous_bundle,
        "file_ids": _unique_values(list(previous_bundle.get("file_ids") or []) + [file_id]),
        "dataset_names": _unique_values(list(previous_bundle.get("dataset_names") or []) + [dataset]),
        "version": int(previous_bundle.get("version") or 1) + 1,
        "relationship_status": "diagnostic_only",
    })
else:
    state.set_active_bundle({
        "bundle_id": "bundle_session_files",
        "label": "Session files",
        "file_ids": [file_id],
        "dataset_names": [dataset],
        "version": 1,
        "relationship_status": "diagnostic_only",
    })
```

Add `"dataset_contract_id": _text(contract.get("id"))` to the data-pool ref.
Use an existing local text helper or `str(contract.get("id") or "").strip()`;
do not introduce a second normalization utility.

Delete `_add_file_relationship_confirmation()`, `_file_relationship_reason()`,
`_file_relationship_question()`, and `_file_relationship_options()` from
`data_io.py` after all call sites are removed.

- [ ] **Step 4: Run load/bundle tests and make them pass**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Commit the load-time cutover**

```powershell
git add -- src/data_agent/tools/data_io.py tests/test_data_bundle.py tests/test_trustworthy_load_data_integration.py
git commit -m "fix: keep file relationships diagnostic at load time"
```

---

### Task 3: Remove Obsolete Relationship Confirmation Gates And Actions

**Files:**
- Modify: `src/data_agent/agent/confirmation_policy.py`
- Modify: `src/data_agent/agent/loop.py`
- Modify: `src/data_agent/agent/question_need_detector.py`
- Modify: `src/data_agent/agent/confirmation/runtime.py`
- Modify: `src/data_agent/agent/analysis_state.py`
- Modify: `tests/test_confirmation_policy.py`
- Modify: `tests/test_confirmation_runtime.py`
- Modify: `tests/test_question_need_detector.py`
- Modify: `tests/test_analysis_state_v2.py`
- Modify: `tests/test_analysis_entry.py`

- [ ] **Step 1: Write failing tests that obsolete records are inert**

Add to `tests/test_confirmation_policy.py`:

```python
@pytest.mark.parametrize("confirmation_type", [
    "file_relationship_confirmation",
    "file_exclusion_confirmation",
    "join_logic_confirmation",
])
def test_pending_confirmation_gate_ignores_obsolete_relationship_questions(confirmation_type):
    state = AnalysisSessionState(session_id="legacy_relationship_gate")
    state.pending_confirmations = [{
        "id": "legacy_relation",
        "status": "pending",
        "confirmation_type": confirmation_type,
        "question": "Should these files be related?",
        "options": [{"label": "Yes", "value": "yes"}],
        "state_updates": {"stage": "scope"},
    }]

    assert pending_confirmation_gate(state) is None
```

Add to `tests/test_confirmation_runtime.py`:

```python
def test_auto_suspend_ignores_obsolete_relationship_pending_record(tmp_path, monkeypatch):
    loop = AgentLoop(client=None, session_id="ignore_legacy_relationship")
    state = AnalysisSessionState(session_id="ignore_legacy_relationship")
    state.pending_confirmations = [{
        "id": "legacy_relation",
        "status": "pending",
        "confirmation_type": "file_relationship_confirmation",
        "question": "Should these files be related?",
        "options": [{"label": "Together", "value": "together"}],
        "state_updates": {"stage": "scope"},
    }]
    loop.context.analysis_state = state
    loop._turn_question_need = {"status": "clear"}

    assert loop._pending_confirmation_for_auto_suspend(state) is None
```

Replace relationship-gate tests in `tests/test_question_need_detector.py` with:

```python
def test_relationship_diagnostics_never_create_question_need():
    state = _state()
    state.file_relationships = [{
        "relationship_id": "rel_orders_history",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "join_logic_confirmation",
    }]

    gate = detect_question_need("analyze revenue trend", _intent(), state)

    assert gate["status"] == "clear"
```

Replace `test_pending_file_relationship_returns_ask_user_question_gate()` in
`tests/test_analysis_entry.py` with a regression that compares the decision to an
otherwise identical state without relationship metadata:

```python
def test_file_relationship_diagnostic_does_not_change_analysis_entry():
    baseline_state = _state()
    relationship_state = _state()
    relationship_state.file_relationships = [{
        "relationship_id": "rel_sales_history",
        "status": "possibly_linked",
        "requires_confirmation": True,
        "confirmation_type": "join_logic_confirmation",
    }]

    baseline = decide_analysis_entry("show revenue trend", _intent(), baseline_state)
    actual = decide_analysis_entry("show revenue trend", _intent(), relationship_state)

    assert actual == baseline
```

- [ ] **Step 2: Run confirmation tests and verify legacy paths fail**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_confirmation_policy.py `
  tests/test_confirmation_runtime.py `
  tests/test_question_need_detector.py `
  tests/test_analysis_state_v2.py `
  tests/test_analysis_entry.py -q
```

Expected: FAIL because relationship records are still treated as gates and the
relationship resolution action is still registered.

- [ ] **Step 3: Centralize the obsolete-type filter**

Add to `confirmation_policy.py`:

```python
OBSOLETE_RELATIONSHIP_CONFIRMATION_TYPES = frozenset({
    "file_relationship_confirmation",
    "file_exclusion_confirmation",
    "join_logic_confirmation",
})


def is_actionable_pending_confirmation(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if _text(item.get("status") or "pending") != "pending":
        return False
    confirmation_type = _text(item.get("confirmation_type"))
    return confirmation_type not in OBSOLETE_RELATIONSHIP_CONFIRMATION_TYPES
```

Use this helper in `pending_confirmation_gate()` and in
`AgentLoop._pending_confirmation_for_auto_suspend()`. In the loop, filter the
initial `pending_items` collection itself:

```python
pending_items = [
    item
    for item in getattr(state, "pending_confirmations", []) or []
    if is_actionable_pending_confirmation(item)
]
if not pending_items:
    return None
```

Do not keep obsolete records in `pending_items` and then return `False` because
none are answerable. Returning `None` is required so a new material
`_turn_question_need` can still enter the unified runtime.

- [ ] **Step 4: Delete relationship-derived question detection**

In `question_need_detector.py`:

- remove the `_pending_file_relationship_gate()` call from
  `detect_question_need()`;
- delete `_pending_file_relationship_gate()`, relationship reason/question/
  options helpers, and relationship-only constants no longer referenced;
- retain route, metric, time-window, method, and data-quality questions.

Do not replace relationship detection in this step. Material scope selection is
added in Task 4 from the new scope contract.

- [ ] **Step 5: Delete the obsolete resolution action and state mutation**

In `confirmation/runtime.py`:

- remove `resolve_file_relationship` from `build_action_registry()`;
- remove `_validate_file_relationship_action()`;
- remove relationship branches from `_resolution_action_for()` and
  `_resolution_params_for()`.

In `analysis_state.py`:

- remove `_normalize_file_relationship_action()`;
- remove `file_relationship_confirmation` handling from `apply_state_updates()`;
- remove `_apply_file_relationship_confirmation()`, `_find_file_relationship()`,
  and `_set_relationship_bundle()`.

Keep `file_relationships`, `dataset_bundles`, and their read/diagnostic methods.
They remain inspectable metadata.

- [ ] **Step 6: Run confirmation tests and make them pass**

Run the Step 2 command.

Expected: PASS. Existing direct, method, time-window, metric, and data-quality
confirmation tests must remain green.

- [ ] **Step 7: Commit the legacy confirmation removal**

```powershell
git add -- `
  src/data_agent/agent/confirmation_policy.py `
  src/data_agent/agent/loop.py `
  src/data_agent/agent/question_need_detector.py `
  src/data_agent/agent/confirmation/runtime.py `
  src/data_agent/agent/analysis_state.py `
  tests/test_confirmation_policy.py `
  tests/test_confirmation_runtime.py `
  tests/test_question_need_detector.py `
  tests/test_analysis_state_v2.py `
  tests/test_analysis_entry.py
git commit -m "refactor: retire relationship confirmation workflow"
```

---

### Task 4: Route Material File Selection Through The Unified Runtime

**Files:**
- Modify: `src/data_agent/agent/multi_file_scope.py`
- Modify: `src/data_agent/agent/question_need_detector.py`
- Modify: `tests/test_multi_file_scope.py`
- Modify: `tests/test_question_need_detector.py`
- Modify: `tests/test_confirmation_runtime.py`

- [ ] **Step 1: Write a failing exact-reference ambiguity test**

Add:

```python
def test_duplicate_explicit_file_reference_creates_material_decision():
    state = AnalysisSessionState(session_id="ambiguous_scope", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "sales_a", "filename": "sales.csv", "dataset": "sales_a", "status": "loaded"},
        {"file_id": "sales_b", "filename": "sales.csv", "dataset": "sales_b", "status": "loaded"},
    ]
    _add_contract(state, "sales_a")
    _add_contract(state, "sales_b")

    plan = build_analysis_scope_plan(state, "analyze sales.csv")

    assert plan["scope_status"] == "needs_decision"
    assert [item["file_id"] for item in plan["decision_files"]] == ["sales_a", "sales_b"]
    assert all(item["reason_code"] == "ambiguous_file_reference" for item in plan["decision_files"])
```

Add a resolved-reference test where `"analyze sales.csv using sales_b"` returns no
decision because the exact file ID uniquely selects one profile.

- [ ] **Step 2: Write failing detector and runtime tests**

Add to `tests/test_question_need_detector.py`:

```python
def _ambiguous_sales_state():
    state = AnalysisSessionState(session_id="ambiguous_sales", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "sales_a", "filename": "sales.csv", "dataset": "sales_a", "status": "loaded"},
        {"file_id": "sales_b", "filename": "sales.csv", "dataset": "sales_b", "status": "loaded"},
    ]
    state.dataset_contracts = [
        {"id": "duc_sales_a", "dataset": "sales_a", "quality_status": "ready"},
        {"id": "duc_sales_b", "dataset": "sales_b", "quality_status": "ready"},
    ]
    return state


def test_material_scope_decision_returns_file_selection_question():
    state = _ambiguous_sales_state()

    gate = detect_question_need("analyze sales.csv", _intent(), state)

    assert gate["status"] == "hard_question"
    assert gate["question_type"] == "file_scope_selection"
    assert gate["state_updates"] == {"stage": "scope"}
    assert [option["value"] for option in gate["options"]] == ["sales_a", "sales_b"]
```

Add this runtime test and import `AnalysisSessionState` plus
`detect_question_need` at the top of the test module:

```python
from types import SimpleNamespace


def _runtime_scope_intent():
    return SimpleNamespace(intent_type="directed_analysis", clarity="clear")


def _runtime_ambiguous_sales_state():
    state = AnalysisSessionState(session_id="runtime_scope_selection", data_state="data_loaded")
    state.data_pool = [
        {"file_id": "sales_a", "filename": "sales.csv", "dataset": "sales_a", "status": "loaded"},
        {"file_id": "sales_b", "filename": "sales.csv", "dataset": "sales_b", "status": "loaded"},
    ]
    state.dataset_contracts = [
        {"id": "duc_sales_a", "dataset": "sales_a", "quality_status": "ready"},
        {"id": "duc_sales_b", "dataset": "sales_b", "quality_status": "ready"},
    ]
    return state


def test_material_scope_question_auto_suspends_in_runtime(tmp_path, monkeypatch):
    import data_agent.agent.loop as loop_module

    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path)
    monkeypatch.setattr(cfg, "skill_auto_discover", False)
    monkeypatch.setattr(loop_module, "get_config", lambda: cfg)

    state = _runtime_ambiguous_sales_state()
    loop = AgentLoop(client=None, session_id="runtime_scope_selection")
    loop.context.analysis_state = state
    loop._turn_existing_pending_ids = set()
    loop._turn_question_need = detect_question_need("analyze sales.csv", _runtime_scope_intent(), state)

    suspended = loop._maybe_auto_suspend_for_required_question()

    assert suspended is not None
    assert suspended.confirmation_type == "file_scope_selection"
    assert suspended.question
    assert [option["value"] for option in suspended.options] == ["sales_a", "sales_b"]
    assert suspended.confirmation_id == suspended.suspension_id
```

- [ ] **Step 3: Run the new tests and verify failure**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_multi_file_scope.py `
  tests/test_question_need_detector.py `
  tests/test_confirmation_runtime.py -q
```

Expected: FAIL because exact-reference ambiguity and the scope-selection gate do
not exist.

- [ ] **Step 4: Implement deterministic ambiguity detection**

In `multi_file_scope.py`, build an alias index only from eligible profiles. An
alias is material only when it is present in the normalized goal and maps to more
than one file. A unique explicit file ID in the goal resolves broader duplicate
filename aliases.

```python
def _ambiguous_file_ids(
    profiles: list[dict[str, Any]],
    eligible_ids: set[str],
    goal: str,
) -> set[str]:
    normalized_goal = _normalize_alias(goal)
    uniquely_named = {
        _text(profile.get("file_id") or profile.get("id"))
        for profile in profiles
        if _text(profile.get("file_id") or profile.get("id")) in eligible_ids
        and _normalize_alias(_text(profile.get("file_id") or profile.get("id"))) in normalized_goal
    }
    if uniquely_named:
        return set()
    aliases: dict[str, list[str]] = {}
    for profile in profiles:
        file_id = _text(profile.get("file_id") or profile.get("id"))
        if file_id not in eligible_ids:
            continue
        for alias in _profile_aliases(profile):
            if alias and alias in normalized_goal:
                aliases.setdefault(alias, []).append(file_id)
    result: set[str] = set()
    for file_ids in aliases.values():
        if len(set(file_ids)) > 1:
            result.update(file_ids)
    return result
```

- [ ] **Step 5: Add the scope-selection gate before route questions**

Immediately after consulting-intent handling in `detect_question_need()`:

```python
scope_plan = build_analysis_scope_plan(state, user_goal=user_input)
decision_files = scope_plan.get("decision_files")
if isinstance(decision_files, list) and decision_files:
    return _hard_gate(
        "file_scope_selection",
        "The request matches multiple usable files and the selected file changes analysis scope.",
        "The request matches multiple files. Which file should be used for this analysis?",
        options=[
            {
                "label": _text(item.get("filename") or item.get("dataset") or item.get("file_id")),
                "value": _text(item.get("file_id")),
                "description": _text(item.get("dataset")) or "Use this file for the current analysis.",
            }
            for item in decision_files
        ],
        blocking_surfaces=BLOCKED_SURFACES_ALL,
        state_updates={"stage": "scope"},
        metadata={"file_ids": [_text(item.get("file_id")) for item in decision_files]},
    )
```

Import `build_analysis_scope_plan` from `multi_file_scope`. Do not persist a
second scope decision record. The confirmation record and resumed explicit file
ID are sufficient for the current turn; Stage 3C0B later persists task bindings.

- [ ] **Step 6: Run the focused tests and make them pass**

Run the Step 3 command.

Expected: PASS.

- [ ] **Step 7: Commit material scope confirmation**

```powershell
git add -- `
  src/data_agent/agent/multi_file_scope.py `
  src/data_agent/agent/question_need_detector.py `
  tests/test_multi_file_scope.py `
  tests/test_question_need_detector.py `
  tests/test_confirmation_runtime.py
git commit -m "feat: ask only for material file scope choices"
```

---

### Task 5: Project The New Contract Into Trust View And Workbench

**Files:**
- Modify: `src/data_agent/agent/trust_view.py`
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `tests/test_trust_view.py`
- Modify: `tests/test_trust_inspector_api.py`
- Modify: `tests/test_multifile_regressions.py`
- Modify: `tests/test_web_overhaul.py`
- Modify: `tests/test_web_workbench_parity.py`
- Modify: `tests/test_trust_inspector_ui.py`

- [ ] **Step 1: Write failing trust-view contract tests**

Update empty and populated workbench assertions to the final contract:

```python
assert view["workbench"]["current_context"] == {
    "goal": "",
    "scope_status": "ready",
    "file_decisions": [],
    "eligible_files": [],
    "used_files": [],
    "available_files": [],
    "not_needed_files": [],
    "decision_files": [],
    "unavailable_files": [],
    "notes": [],
}
```

Add a populated test asserting that a used decision carries `reason`,
`reason_code`, and `task_refs`, while a relationship diagnostic remains
`actionable=False` without a runtime suspension.

- [ ] **Step 2: Write failing web wording and helper tests**

In `tests/test_web_overhaul.py`, assert the template contains:

```python
assert "文件可用" in html
assert "本次使用" in html
assert "本次不需要" in html
assert "需要你选择" in html
assert "暂不可用" in html
assert "formatWorkbenchFileReason(file)" in html
assert "included_files" not in html
assert "unused_files" not in html
assert "trustView.active_bundle.relationship_status" not in html
assert "formatActiveBundleSummary(trustView.active_bundle)" not in html
```

Assert `app.js` contains `formatWorkbenchAssignmentLabel` and
`formatWorkbenchFileReason`, and no longer defines `formatWorkbenchFiles`,
`formatActiveBundleSummary`, or `formatBundleFileSummary`.

Replace `test_current_data_shows_active_bundle_and_file_relationship_state()` in
`tests/test_trust_inspector_ui.py` with assertions that the current-data panel
uses `workbenchContext().file_decisions`, does not display active-bundle
relationship status, and keeps `workbenchRelationshipDiagnostics()` only under a
native `<details>` technical section.

- [ ] **Step 3: Run view/web tests and verify failure**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_trust_view.py `
  tests/test_trust_inspector_api.py `
  tests/test_multifile_regressions.py `
  tests/test_web_overhaul.py `
  tests/test_web_workbench_parity.py `
  tests/test_trust_inspector_ui.py -q
```

Expected: FAIL because trust view and the template still expose the Stage 3A/3B
aliases.

- [ ] **Step 4: Switch trust view to the new projection**

Update `_empty_view()` and `_workbench_summary()` to project exactly:

```python
"current_context": {
    "goal": _text(plan.get("goal")) or _text(getattr(state, "goal", "")),
    "scope_status": _text(plan.get("scope_status")) or "ready",
    "file_decisions": _list_items(plan.get("file_decisions")),
    "eligible_files": _list_items(plan.get("eligible_files")),
    "used_files": _list_items(plan.get("used_files")),
    "available_files": _list_items(plan.get("available_files")),
    "not_needed_files": _list_items(plan.get("not_needed_files")),
    "decision_files": _list_items(plan.get("decision_files")),
    "unavailable_files": _list_items(plan.get("unavailable_files")),
    "notes": _text_list(plan.get("notes")),
},
```

Do not derive confirmation status from a decision file inside trust view. The
confirmation panel remains a projection of the unified runtime gate.

- [ ] **Step 5: Render one decision list instead of overlapping group strings**

Replace the current six summary paragraphs in `index.html` with one
`x-for="file in workbenchContext().file_decisions"` list. Each row shows:

- filename or dataset;
- eligibility/assignment label;
- user-facing reason;
- task count only when `task_refs` is non-empty.

Also:

- use `workbenchContext().file_decisions.length` for the current-context count;
- remove the active-bundle card, its relationship-status pill, and its file list
  from the primary current-context panel;
- keep the generic dataset-card fallback only when `file_decisions` is empty;
- move `workbenchRelationshipDiagnostics()` into a native `<details>` block with
  the summary label `技术关系说明` so it is collapsed by default;
- keep top-level `active_bundle` and `file_relationships` in the API for historical
  inspection, but do not use either as current-scope truth.

Add these JS helpers:

```javascript
formatWorkbenchAssignmentLabel(file) {
    if (!file || file.eligibility === 'unavailable') return '暂不可用';
    const labels = {
        used: '本次使用',
        available: '文件可用',
        not_needed: '本次不需要',
        needs_decision: '需要你选择',
    };
    return labels[file.assignment || ''] || '状态未知';
},

formatWorkbenchFileReason(file) {
    if (!file) return '';
    const reason = String(file.reason || '').trim();
    const taskRefs = Array.isArray(file.task_refs) ? file.task_refs : [];
    return taskRefs.length ? `${reason} / ${taskRefs.length} 个分析任务` : reason;
},
```

Use existing `trustStatusClass()` with a small mapping from assignment to visual
status; do not create another state store in JavaScript.

Delete `formatActiveBundleSummary()` and `formatBundleFileSummary()` from
`app.js` after their template call sites are gone. Keep
`formatRelationshipMode()` because technical relationship diagnostics still use
it.

- [ ] **Step 6: Run view/web tests and JavaScript syntax check**

Run the Step 3 command, then:

```powershell
node -c src/data_agent/web/static/js/app.js
```

Expected: all pytest tests PASS and Node exits `0`.

- [ ] **Step 7: Commit the workbench cutover**

```powershell
git add -- `
  src/data_agent/agent/trust_view.py `
  src/data_agent/web/templates/index.html `
  src/data_agent/web/static/js/app.js `
  tests/test_trust_view.py `
  tests/test_trust_inspector_api.py `
  tests/test_multifile_regressions.py `
  tests/test_web_overhaul.py `
  tests/test_web_workbench_parity.py `
  tests/test_trust_inspector_ui.py
git commit -m "feat: explain file eligibility and assignment in workbench"
```

---

### Task 6: Enforce Context Bounds And Replay The Four-File Session

**Files:**
- Modify: `tests/test_multi_file_scope.py`
- Modify: `tests/test_multifile_regressions.py`
- Create: `docs/superpowers/plans/2026-06-27-multifile-analysis-stage-3c0a-verification.md`

- [ ] **Step 1: Add a failing fixed-budget test**

```python
def test_scope_contract_stays_bounded_with_large_file_history():
    state = AnalysisSessionState(session_id="bounded_scope", data_state="data_loaded")
    state.data_pool = [
        {
            "file_id": f"file_{index}",
            "filename": f"dataset_{index}.csv",
            "dataset": f"dataset_{index}",
            "status": "loaded",
        }
        for index in range(20)
    ]
    state.dataset_contracts = [
        {"id": f"duc_dataset_{index}", "dataset": f"dataset_{index}", "quality_status": "ready"}
        for index in range(20)
    ]

    plan = build_analysis_scope_plan(state, "analyze all files")

    assert len(plan["file_decisions"]) == 5
    assert plan["context_budget"]["total_file_count"] == 20
    assert plan["context_budget"]["omitted_file_count"] == 15
    assert len(json.dumps(plan, ensure_ascii=False)) < 6000
```

Add a decision-priority variant proving at least one `needs_decision` item remains
visible when more than five eligible files exist.

- [ ] **Step 2: Run the bounded tests and fix only budget regressions**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_multi_file_scope.py `
  tests/test_multifile_regressions.py -q
```

Expected: PASS after the bounded ordering from Task 1 is complete. If the JSON
size exceeds 6000 characters, reduce repeated decision fields in grouped arrays
by returning compact references there; do not raise the bound without design
review.

- [ ] **Step 3: Run the complete Stage 3C0A focused regression suite**

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest `
  tests/test_multi_file_scope.py `
  tests/test_multifile_regressions.py `
  tests/test_data_bundle.py `
  tests/test_trustworthy_load_data_integration.py `
  tests/test_confirmation_policy.py `
  tests/test_confirmation_runtime.py `
  tests/test_confirmation_session_api.py `
  tests/test_question_need_detector.py `
  tests/test_analysis_entry.py `
  tests/test_analysis_state_v2.py `
  tests/test_trust_view.py `
  tests/test_trust_inspector_api.py `
  tests/test_trust_inspector_ui.py `
  tests/test_web_overhaul.py `
  tests/test_web_workbench_parity.py -q
node -c src/data_agent/web/static/js/app.js
git diff --check
```

Expected: all tests PASS; Node and diff checks exit `0`. A pytest cache warning
is acceptable; failures are not.

- [ ] **Step 4: Replay session `5ba97a7bb7db` without writing it**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
@'
from data_agent.agent.analysis_state import load_analysis_state
from data_agent.agent.confirmation_policy import pending_confirmation_gate
from data_agent.agent.multi_file_scope import build_analysis_scope_plan

state = load_analysis_state("5ba97a7bb7db")
before_updated_at = state.updated_at
plan = build_analysis_scope_plan(state, state.goal)

assert len(state.data_pool) == 4
assert len(plan["eligible_files"]) == 4
assert plan["used_files"] == []
assert len(plan["available_files"]) == 4
assert plan["decision_files"] == []
assert all(item["eligibility"] == "eligible" for item in plan["file_decisions"])
gate = pending_confirmation_gate(state)
assert gate is not None
assert gate["confirmation_type"] == "method_confirmation"
assert state.updated_at == before_updated_at
print("session_replay_ok", len(plan["eligible_files"]), gate["confirmation_type"])
'@ | .\.venv\Scripts\python.exe -
```

Expected:

```text
session_replay_ok 4 method_confirmation
```

This proves the three historical relationship confirmations are ignored while
the unrelated valid method confirmation remains active. Do not call `state.save()`
and do not edit the session fixture.

- [ ] **Step 5: Record verification evidence**

Create `docs/superpowers/plans/2026-06-27-multifile-analysis-stage-3c0a-verification.md`
after the verification commands finish. The document must contain these sections
and only observed values:

- `# Stage 3C0A Verification`
- `Date` and the output of `git rev-parse HEAD`
- `Scope`, listing the five implemented surfaces from this plan
- `Commands And Results`, copying the exact pytest command, pass count, warnings,
  Node exit status, diff-check exit status, and the literal four-file replay line
- `Deviations`, using `None` only when implementation matches this plan
- `Stop-Gate Decision`, with Stage 3C0A acceptance and permission to plan Stage
  3C0B

If any deviation affects the confirmed design, record the evidence and set both
stop-gate answers to `no` until the design impact is reviewed. Do not invent pass
counts before running the commands.

- [ ] **Step 6: Commit tests and verification record**

```powershell
git add -- `
  tests/test_multi_file_scope.py `
  tests/test_multifile_regressions.py `
  docs/superpowers/plans/2026-06-27-multifile-analysis-stage-3c0a-verification.md
git commit -m "docs: record stage 3c0a verification"
```

---

## Final Review Checklist

- [ ] `file_relationships` influence only technical diagnostics.
- [ ] New loads never create relationship confirmation records.
- [ ] Historical relationship confirmations are ignored without mutating old sessions.
- [ ] `used` comes only from `dataset_inputs` task bindings.
- [ ] Files explicitly in scope but not yet bound remain `available`, not falsely used.
- [ ] `needs_decision` is reachable only for material exact-reference ambiguity.
- [ ] Scope questions suspend through the unified confirmation runtime.
- [ ] Workbench labels and reasons match the backend decision contract.
- [ ] Old scope aliases are absent from first-party code and tests.
- [ ] File detail and serialized context remain bounded.
- [ ] Session `5ba97a7bb7db` replays read-only with four eligible files and no relationship gate.
- [ ] Stage 3C0B, Stage 3C1A, and Stage 3C1B remain unimplemented.
