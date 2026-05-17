# Task Plan Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the task panel show only the current session's active plan tasks, while preserving superseded and historical tasks for auditability.

**Architecture:** Add lightweight plan metadata to existing file-backed `TaskRecord`s and keep the active plan registry in `project/tasks/active_plans.json`. Use `TaskManager` as the single persistence boundary, then update workflow task creation and `/api/tasks` so duplicate/candidate tasks do not appear as active progress. Add conservative evidence-aware completion as a system assist rather than a replacement for explicit LLM `task_update`.

**Tech Stack:** Python, pytest, Flask blueprint tests, existing file-backed task storage.

---

## File Map

- Modify: `src/data_agent/session/task_manager.py`
  - Add plan metadata defaults.
  - Add active-plan registry helpers.
  - Add `superseded`, `blocked`, and `archived` status support.
  - Add active/history scoped list helpers.
  - Add conservative evidence-to-task completion helper.

- Modify: `src/data_agent/tools/task_tools.py`
  - Include plan fields in workflow field passthrough.
  - Create/reuse active plans when creating workflow tasks from a spec.
  - Avoid duplicate workflow task groups for the same active plan.
  - Preserve manual `task_create` behavior by attaching to the active plan when context has an analysis spec.

- Modify: `src/data_agent/agent/analysis_flow_controller.py`
  - Use `TaskManager` plan helpers in `ensure_workflow_tasks()`.
  - Generate readable task subjects from `task`, `step`, `name`, or `title`.
  - Mark confirmation tasks as active-plan confirmation tasks.

- Modify: `src/data_agent/tools/analysis_flow.py`
  - After `record_evidence_record`, call conservative task completion helper.
  - Return completed task ids in the tool result when any task is completed.

- Modify: `src/data_agent/web/blueprints/tasks.py`
  - Add `scope=active|all|history` query behavior.
  - Make active scope the default for session-scoped task queries.
  - Preserve `include_global`, `ready_only`, and `active_only` filters after scope selection.

- Modify: `tests/test_task_manager_scope.py`
  - Add unit tests for plan defaults, active plan registry, active/history filtering, supersede behavior, and evidence completion.

- Modify: `tests/test_web_workbench_parity.py`
  - Add API tests for active/history/all task scopes.

- Add: `tests/test_task_plan_versioning.py`
  - Add regression tests that model session `38465eb4172f`: candidate tasks, duplicate spec tasks, completed execution tasks, and active-panel filtering.

---

### Task 1: Add Failing Unit Tests For Plan Metadata And Active Scope

**Files:**
- Modify: `tests/test_task_manager_scope.py`

- [ ] **Step 1: Add tests for plan metadata defaults and active plan registry**

Append these tests to `tests/test_task_manager_scope.py`:

```python
def test_task_plan_fields_default_for_backward_compatibility(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")

    task = mgr.create("Legacy compatible", session_id="s1")

    assert task["plan_id"] == ""
    assert task["plan_version"] == 1
    assert task["plan_status"] == ""
    assert task["task_kind"] == "plan_task"
    assert task["source"] == ""
    assert task["superseded_by"] == ""
    assert task["completed_by"] == ""
    assert task["completed_at"] == ""


def test_create_plan_sets_active_plan_for_session(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")

    plan = mgr.create_plan(
        session_id="s1",
        project_name="Revenue",
        goal="Analyze revenue decline",
        source="analysis_spec",
        analysis_spec_id="spec_1",
        workflow_id="wf_1",
    )

    assert plan["status"] == "active"
    assert plan["version"] == 1
    assert mgr.get_active_plan_id("s1", "Revenue") == plan["id"]
```

- [ ] **Step 2: Add tests for active/history scope filtering**

Append these tests:

```python
def test_list_active_for_scope_returns_only_active_plan_tasks(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    old_plan = mgr.create_plan(session_id="s1", goal="Old", source="analysis_spec")
    old_task = mgr.create("Old pending", session_id="s1", plan_id=old_plan["id"])
    new_plan = mgr.create_plan(session_id="s1", goal="New", source="user_replan")
    new_task = mgr.create("New active", session_id="s1", plan_id=new_plan["id"])

    tasks = mgr.list_active_for_scope(session_id="s1")

    assert [t["id"] for t in tasks] == [new_task["id"]]
    assert mgr.get(old_task["id"])["status"] == "superseded"


def test_list_history_for_scope_returns_superseded_and_archived_tasks(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    first = mgr.create_plan(session_id="s1", goal="First", source="analysis_spec")
    old_task = mgr.create("Old task", session_id="s1", plan_id=first["id"])
    mgr.create_plan(session_id="s1", goal="Second", source="user_replan")

    history = mgr.list_history_for_scope(session_id="s1")

    assert [t["id"] for t in history] == [old_task["id"]]
    assert history[0]["status"] == "superseded"
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
pytest tests/test_task_manager_scope.py -q
```

Expected: FAIL with missing methods such as `create_plan`, `get_active_plan_id`, `list_active_for_scope`, or missing plan fields.

---

### Task 2: Implement Plan Metadata, Registry, And Scope Helpers

**Files:**
- Modify: `src/data_agent/session/task_manager.py`

- [ ] **Step 1: Add plan metadata defaults**

Add this constant below `WORKFLOW_FIELDS`:

```python
PLAN_FIELDS = {
    "plan_id": "",
    "plan_version": 1,
    "plan_status": "",
    "task_kind": "plan_task",
    "source": "",
    "superseded_by": "",
    "archived_at": "",
    "completed_by": "",
    "completed_at": "",
}
```

Update `_normalize()` so it fills both field groups:

```python
    def _normalize(self, task: dict) -> dict:
        for key, value in WORKFLOW_FIELDS.items():
            if key not in task:
                task[key] = list(value) if isinstance(value, list) else value
        for key, value in PLAN_FIELDS.items():
            if key not in task:
                task[key] = list(value) if isinstance(value, list) else value
        task.setdefault("session_id", "")
        task.setdefault("owner", "")
        task.setdefault("blockedBy", [])
        task.setdefault("blocks", [])
        return task
```

- [ ] **Step 2: Allow new statuses and timestamps**

In `update()`, replace the status validation block with:

```python
        if status is not None:
            allowed = ("pending", "blocked", "in_progress", "completed", "superseded", "archived", "deleted")
            if status not in allowed:
                return None
            task["status"] = status

            if status == "completed":
                task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._clear_dependency(tid)

            if status == "archived":
                task["archived_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if status == "deleted":
                self._path(tid).unlink(missing_ok=True)
                return {"id": tid, "status": "deleted"}
```

- [ ] **Step 3: Persist plan metadata passed into `create()` and `update()`**

In `create()`, after the `WORKFLOW_FIELDS` loop, add:

```python
        for key in PLAN_FIELDS:
            if key in workflow_fields and workflow_fields[key] is not None:
                task[key] = workflow_fields[key]
```

In `update()`, after the `WORKFLOW_FIELDS` loop, add:

```python
        for key in PLAN_FIELDS:
            if key in workflow_fields and workflow_fields[key] is not None:
                task[key] = workflow_fields[key]
```

- [ ] **Step 4: Add active plan registry helpers**

Add these methods inside `TaskManager`, before `list_for_scope()`:

```python
    def _active_plans_path(self) -> Path:
        return self.dir / "active_plans.json"

    def _plan_key(self, session_id: str = "", project_name: str = "") -> str:
        return f"{session_id or ''}::{project_name or ''}"

    def _read_active_plans(self) -> dict:
        path = self._active_plans_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_active_plans(self, data: dict) -> None:
        self._active_plans_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_active_plan_id(self, session_id: str = "", project_name: str = "") -> str:
        active = self._read_active_plans()
        value = active.get(self._plan_key(session_id, project_name), "")
        return str(value or "")

    def _set_active_plan_id(self, plan_id: str, session_id: str = "", project_name: str = "") -> None:
        active = self._read_active_plans()
        active[self._plan_key(session_id, project_name)] = plan_id
        self._write_active_plans(active)
```

- [ ] **Step 5: Add `create_plan()` and supersede behavior**

Add these methods:

```python
    def _session_project_tasks(self, session_id: str = "", project_name: str = "") -> list[dict]:
        return self.list_for_scope(session_id=session_id, project_name=project_name, include_global=False)

    def _supersede_active_plan(self, session_id: str = "", project_name: str = "", superseded_by: str = "") -> None:
        active_plan_id = self.get_active_plan_id(session_id, project_name)
        if not active_plan_id:
            return
        for task in self._session_project_tasks(session_id=session_id, project_name=project_name):
            if task.get("plan_id") != active_plan_id:
                continue
            if task.get("status") in ("pending", "blocked", "in_progress"):
                self.update(
                    task["id"],
                    status="superseded",
                    superseded_by=superseded_by,
                    plan_status="superseded",
                )

    def create_plan(
        self,
        session_id: str = "",
        project_name: str = "",
        goal: str = "",
        source: str = "",
        analysis_spec_id: str = "",
        workflow_id: str = "",
    ) -> dict:
        active_plan_id = self.get_active_plan_id(session_id, project_name)
        existing_versions = [
            int(t.get("plan_version") or 1)
            for t in self._session_project_tasks(session_id=session_id, project_name=project_name)
            if t.get("plan_id")
        ]
        version = max(existing_versions, default=0) + 1
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        self._supersede_active_plan(session_id=session_id, project_name=project_name, superseded_by=plan_id)
        self._set_active_plan_id(plan_id, session_id, project_name)
        return {
            "id": plan_id,
            "session_id": session_id,
            "project_name": project_name,
            "goal": goal,
            "version": version,
            "status": "active",
            "source": source,
            "previous_plan_id": active_plan_id,
            "analysis_spec_id": analysis_spec_id,
            "workflow_id": workflow_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
```

Add `import uuid` near the top of the file.

- [ ] **Step 6: Add active and history list helpers**

Add these methods:

```python
    def list_active_for_scope(
        self,
        session_id: str = "",
        project_name: str = "",
        include_global: bool = False,
    ) -> list[dict]:
        tasks = self.list_for_scope(
            session_id=session_id,
            project_name=project_name,
            include_global=include_global,
        )
        active_plan_id = self.get_active_plan_id(session_id, project_name)
        if active_plan_id:
            return [
                t for t in tasks
                if t.get("plan_id") == active_plan_id
                and t.get("task_kind") in ("plan_task", "confirmation", "evidence_gap")
                and t.get("status") not in ("deleted", "archived", "superseded")
            ]
        return [
            t for t in tasks
            if not t.get("plan_id")
            and t.get("status") not in ("deleted", "archived", "superseded")
        ]

    def list_history_for_scope(
        self,
        session_id: str = "",
        project_name: str = "",
        include_global: bool = False,
    ) -> list[dict]:
        return [
            t for t in self.list_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
            if t.get("status") in ("completed", "archived", "superseded")
            and (not self.get_active_plan_id(session_id, project_name) or t.get("plan_id") != self.get_active_plan_id(session_id, project_name))
        ]
```

- [ ] **Step 7: Run focused task manager tests**

Run:

```bash
pytest tests/test_task_manager_scope.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/data_agent/session/task_manager.py tests/test_task_manager_scope.py
git commit -m "feat: add task plan metadata"
```

---

### Task 3: Add Regression Tests For Duplicate Candidate/Spec/Execution Tasks

**Files:**
- Add: `tests/test_task_plan_versioning.py`

- [ ] **Step 1: Create the regression test file**

Create `tests/test_task_plan_versioning.py`:

```python
from data_agent.session.task_manager import TaskManager


def test_completed_execution_plan_hides_legacy_pending_duplicates(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")

    candidate_plan = mgr.create_plan(
        session_id="38465eb4172f",
        goal="Candidate retention plan",
        source="recommended_playbook",
        analysis_spec_id="candidate_spec",
        workflow_id="wf_candidate",
    )
    mgr.create(
        "build cohorts and calculate retention curve",
        session_id="38465eb4172f",
        plan_id=candidate_plan["id"],
        plan_version=candidate_plan["version"],
        workflow_id="wf_candidate",
        analysis_spec_id="candidate_spec",
        source="recommended_playbook",
    )

    spec_plan = mgr.create_plan(
        session_id="38465eb4172f",
        goal="省钱卡功能影响分析",
        source="analysis_spec",
        analysis_spec_id="spec_active",
        workflow_id="wf_active",
    )
    stale_spec_task = mgr.create(
        "分析步骤 1",
        description='{"task":"数据预处理与基础指标计算"}',
        session_id="38465eb4172f",
        plan_id=spec_plan["id"],
        plan_version=spec_plan["version"],
        workflow_id="wf_active",
        analysis_spec_id="spec_active",
        source="analysis_spec",
    )
    execution_task = mgr.create(
        "数据预处理与基础指标计算",
        session_id="38465eb4172f",
        plan_id=spec_plan["id"],
        plan_version=spec_plan["version"],
        workflow_id="wf_active",
        analysis_spec_id="spec_active",
        source="llm_plan",
    )
    mgr.update(stale_spec_task["id"], status="superseded")
    mgr.update(execution_task["id"], status="completed", result_summary="Evidence recorded")

    active = mgr.list_active_for_scope(session_id="38465eb4172f")

    assert [t["id"] for t in active] == [execution_task["id"]]
    assert active[0]["status"] == "completed"
```

- [ ] **Step 2: Add test for creating duplicate spec tasks on an existing active plan**

Append:

```python
def test_active_plan_reuse_skips_duplicate_subjects(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(
        session_id="s1",
        goal="省钱卡功能影响分析",
        source="analysis_spec",
        analysis_spec_id="spec_1",
        workflow_id="wf_1",
    )
    mgr.create(
        "数据预处理与基础指标计算",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        workflow_id="wf_1",
        analysis_spec_id="spec_1",
    )

    duplicate = mgr.find_duplicate_task(
        session_id="s1",
        plan_id=plan["id"],
        subject="数据预处理与基础指标计算",
        analysis_spec_id="spec_1",
    )

    assert duplicate is not None
    assert duplicate["subject"] == "数据预处理与基础指标计算"
```

- [ ] **Step 3: Run and verify failure for the new duplicate helper**

Run:

```bash
pytest tests/test_task_plan_versioning.py -q
```

Expected: FAIL because `find_duplicate_task()` is not implemented.

---

### Task 4: Implement Duplicate Detection And Workflow Task Plan Attachment

**Files:**
- Modify: `src/data_agent/session/task_manager.py`
- Modify: `src/data_agent/tools/task_tools.py`
- Modify: `src/data_agent/agent/analysis_flow_controller.py`
- Test: `tests/test_task_plan_versioning.py`

- [ ] **Step 1: Add duplicate-task helper to `TaskManager`**

Add this method in `TaskManager`:

```python
    def find_duplicate_task(
        self,
        session_id: str,
        plan_id: str,
        subject: str,
        analysis_spec_id: str = "",
    ) -> dict | None:
        normalized_subject = (subject or "").strip()
        for task in self.list_for_scope(session_id=session_id):
            if task.get("plan_id") != plan_id:
                continue
            if analysis_spec_id and task.get("analysis_spec_id") != analysis_spec_id:
                continue
            if task.get("status") in ("deleted", "archived", "superseded"):
                continue
            if (task.get("subject") or "").strip() == normalized_subject:
                return task
        return None
```

- [ ] **Step 2: Add workflow field passthrough for plan fields**

In `src/data_agent/tools/task_tools.py`, update `_workflow_fields_from_dict()` to include:

```python
        "plan_id",
        "plan_version",
        "plan_status",
        "task_kind",
        "source",
        "superseded_by",
        "archived_at",
        "completed_by",
        "completed_at",
```

- [ ] **Step 3: Add helper functions in `task_tools.py`**

Add these helpers above `create_workflow_tasks_from_spec()`:

```python
def _step_subject(step, idx: int) -> str:
    if isinstance(step, dict):
        return (
            step.get("task")
            or step.get("subject")
            or step.get("title")
            or step.get("step")
            or step.get("name")
            or f"分析步骤 {idx}"
        )
    return str(step)


def _step_description(step) -> str:
    if isinstance(step, dict):
        return (
            step.get("description")
            or step.get("detail")
            or step.get("method")
            or json.dumps(step, ensure_ascii=False)
        )
    return str(step)


def _ensure_active_plan_for_spec(spec: dict) -> dict:
    workflow_id = spec.get("workflow_id") or f"wf_{uuid.uuid4().hex[:8]}"
    spec["workflow_id"] = workflow_id
    spec_id = spec.get("id", "")
    active_plan_id = task_manager.get_active_plan_id(_session_id(), _project_name())
    if active_plan_id:
        active_tasks = task_manager.list_active_for_scope(session_id=_session_id(), project_name=_project_name())
        if any(t.get("analysis_spec_id") == spec_id or t.get("workflow_id") == workflow_id for t in active_tasks):
            return {
                "id": active_plan_id,
                "version": max([int(t.get("plan_version") or 1) for t in active_tasks], default=1),
                "workflow_id": workflow_id,
                "analysis_spec_id": spec_id,
            }
    return task_manager.create_plan(
        session_id=_session_id(),
        project_name=_project_name(),
        goal=spec.get("goal", ""),
        source="analysis_spec",
        analysis_spec_id=spec_id,
        workflow_id=workflow_id,
    )
```

- [ ] **Step 4: Update `create_workflow_tasks_from_spec()`**

Replace the function body with:

```python
def create_workflow_tasks_from_spec(spec: dict) -> dict:
    method_plan = spec.get("method_plan") or []
    if isinstance(method_plan, str):
        method_plan = [line.strip() for line in method_plan.splitlines() if line.strip()]
    if not isinstance(method_plan, list):
        method_plan = []

    plan = _ensure_active_plan_for_spec(spec)
    workflow_id = plan.get("workflow_id") or spec.get("workflow_id") or f"wf_{uuid.uuid4().hex[:8]}"
    spec_id = plan.get("analysis_spec_id") or spec.get("id", "")
    plan_id = plan["id"]
    plan_version = plan.get("version", 1)

    created = []
    reused = []
    for idx, step in enumerate(method_plan, 1):
        subject = _step_subject(step, idx)
        description = _step_description(step)
        if isinstance(step, dict):
            node_type = step.get("node_type") or "analysis"
            expected_output = step.get("expected_output", "")
            required_data = step.get("required_data", spec.get("required_data", []))
            required_capability = step.get("required_capability", "")
            evidence_requirements = step.get("evidence_requirements", [])
            confirmation_policy = step.get("confirmation_policy", {})
        else:
            node_type = "analysis"
            expected_output = ""
            required_data = spec.get("required_data", [])
            required_capability = ""
            evidence_requirements = []
            confirmation_policy = {}

        duplicate = task_manager.find_duplicate_task(
            session_id=_session_id(),
            plan_id=plan_id,
            subject=subject,
            analysis_spec_id=spec_id,
        )
        if duplicate:
            reused.append(duplicate)
            continue

        task = task_manager.create(
            subject=subject[:120],
            description=description,
            session_id=_session_id(),
            workflow_id=workflow_id,
            project_name=_project_name(),
            stage="execute",
            node_type=node_type,
            analysis_spec_id=spec_id,
            required_data=required_data,
            expected_output=expected_output,
            required_capability=required_capability,
            evidence_requirements=evidence_requirements,
            confirmation_policy=confirmation_policy,
            plan_id=plan_id,
            plan_version=plan_version,
            plan_status="active",
            task_kind="plan_task",
            source="analysis_spec",
        )
        created.append(task)
    return {
        "workflow_id": workflow_id,
        "plan_id": plan_id,
        "created": len(created),
        "reused": len(reused),
        "task_ids": [t["id"] for t in created + reused],
    }
```

- [ ] **Step 5: Update manual `task_create()` to attach to active plan when present**

In `task_create()`, after `current_spec = _current_analysis_spec()`, add:

```python
    active_plan_id = task_manager.get_active_plan_id(_session_id(), _project_name())
    active_tasks = task_manager.list_active_for_scope(session_id=_session_id(), project_name=_project_name()) if active_plan_id else []
    active_plan_version = max([int(t.get("plan_version") or 1) for t in active_tasks], default=1)
```

Add these common fields:

```python
        "plan_id": active_plan_id,
        "plan_version": active_plan_version,
        "plan_status": "active" if active_plan_id else "",
        "task_kind": "plan_task",
        "source": "llm_plan" if active_plan_id else "",
```

- [ ] **Step 6: Update `AnalysisFlowController.ensure_workflow_tasks()` subject extraction and plan attachment**

Inside `ensure_workflow_tasks()`, replace subject extraction:

```python
                subject = step.get("step") or step.get("name") or f"Analysis step {idx}"
```

with:

```python
                subject = step.get("task") or step.get("step") or step.get("name") or step.get("title") or f"Analysis step {idx}"
```

Before creating tasks, add:

```python
        active_plan_id = task_manager.get_active_plan_id(self.session_id, self.project_name or state.project_name or "")
        if active_plan_id:
            active_tasks = task_manager.list_active_for_scope(session_id=self.session_id, project_name=self.project_name or state.project_name or "")
            plan = {
                "id": active_plan_id,
                "version": max([int(t.get("plan_version") or 1) for t in active_tasks], default=1),
            }
        else:
            plan = task_manager.create_plan(
                session_id=self.session_id,
                project_name=self.project_name or state.project_name or "",
                goal=spec.get("goal", state.goal),
                source="analysis_spec",
                analysis_spec_id=spec_id,
                workflow_id=workflow_id,
            )
```

In each `task_manager.create()` call, pass:

```python
                plan_id=plan["id"],
                plan_version=plan.get("version", 1),
                plan_status="active",
                task_kind="plan_task",
                source="analysis_spec",
```

Update `ensure_confirmation_task()` creation with:

```python
            plan_id=task_manager.get_active_plan_id(self.session_id, self.project_name or state.project_name or ""),
            task_kind="confirmation",
            source="system_confirmation",
```

- [ ] **Step 7: Run workflow regression tests**

Run:

```bash
pytest tests/test_task_plan_versioning.py tests/test_task_manager_scope.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/data_agent/session/task_manager.py src/data_agent/tools/task_tools.py src/data_agent/agent/analysis_flow_controller.py tests/test_task_plan_versioning.py tests/test_task_manager_scope.py
git commit -m "feat: attach workflow tasks to active plans"
```

---

### Task 5: Add API Scope Tests And Implement Active/History Query Behavior

**Files:**
- Modify: `tests/test_web_workbench_parity.py`
- Modify: `src/data_agent/web/blueprints/tasks.py`

- [ ] **Step 1: Add API tests for active/history/all scopes**

Append this test to `tests/test_web_workbench_parity.py`:

```python
def test_tasks_api_defaults_to_active_plan_scope(tmp_path):
    cfg, old_sessions, old_tasks_dir = _use_tmp_state(tmp_path)
    try:
        from data_agent.session.task_manager import task_manager
        from data_agent.web.app import create_app

        old_plan = task_manager.create_plan(session_id="s_current", goal="Old", source="analysis_spec")
        old_task = task_manager.create("Old pending", session_id="s_current", plan_id=old_plan["id"])
        new_plan = task_manager.create_plan(session_id="s_current", goal="New", source="user_replan")
        new_task = task_manager.create("New active", session_id="s_current", plan_id=new_plan["id"])

        client = create_app().test_client()

        active = client.get("/api/tasks?session_id=s_current")
        assert active.status_code == 200
        assert [t["id"] for t in active.get_json()] == [new_task["id"]]

        history = client.get("/api/tasks?session_id=s_current&scope=history")
        assert history.status_code == 200
        assert [t["id"] for t in history.get_json()] == [old_task["id"]]

        all_tasks = client.get("/api/tasks?session_id=s_current&scope=all")
        assert all_tasks.status_code == 200
        assert {t["id"] for t in all_tasks.get_json()} == {old_task["id"], new_task["id"]}
    finally:
        _restore_state(cfg, old_sessions, old_tasks_dir)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_web_workbench_parity.py::test_tasks_api_defaults_to_active_plan_scope -q
```

Expected: FAIL because `/api/tasks` does not support `scope`.

- [ ] **Step 3: Update `/api/tasks` scope handling**

In `src/data_agent/web/blueprints/tasks.py`, inside `list_tasks()`, add:

```python
    scope = (request.args.get("scope") or "active").lower()
```

Replace the task selection block with:

```python
    if ready_only:
        base_tasks = mgr.list_ready(
            session_id=session_id,
            project_name=project_name,
            include_global=include_global,
        )
    elif session_id or project_name:
        if scope == "all":
            base_tasks = mgr.list_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
        elif scope == "history":
            base_tasks = mgr.list_history_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
        else:
            base_tasks = mgr.list_active_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
    else:
        base_tasks = mgr.list_all()

    tasks = base_tasks
```

Keep the existing `active_only` filter after this block.

- [ ] **Step 4: Run API tests**

Run:

```bash
pytest tests/test_web_workbench_parity.py tests/test_web_overhaul.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/web/blueprints/tasks.py tests/test_web_workbench_parity.py
git commit -m "feat: expose active task plan scope"
```

---

### Task 6: Add Evidence-Aware Task Completion

**Files:**
- Modify: `tests/test_task_manager_scope.py`
- Modify: `src/data_agent/session/task_manager.py`
- Modify: `src/data_agent/tools/analysis_flow.py`

- [ ] **Step 1: Add unit test for conservative evidence completion**

Append to `tests/test_task_manager_scope.py`:

```python
def test_complete_matching_task_from_evidence(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(session_id="s1", goal="Revenue", source="analysis_spec", analysis_spec_id="spec_1")
    task = mgr.create(
        "省钱卡收益分析",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_spec_id="spec_1",
        expected_output="计算省钱卡销售收入、代金券成本、最终净收益",
        evidence_requirements=["净收益"],
    )

    completed = mgr.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence={
            "id": "ev_1",
            "claim": "省钱卡功能直接净收益为-1,752元",
            "result_summary": "净收益=销售收入-代金券成本",
            "confidence": "high",
        },
        analysis_spec_id="spec_1",
    )

    assert completed == [task["id"]]
    updated = mgr.get(task["id"])
    assert updated["status"] == "completed"
    assert updated["evidence_ids"] == ["ev_1"]
    assert updated["completed_by"] == "evidence"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_task_manager_scope.py::test_complete_matching_task_from_evidence -q
```

Expected: FAIL because `complete_matching_tasks_from_evidence()` is missing.

- [ ] **Step 3: Implement conservative evidence matching**

Add this helper in `TaskManager`:

```python
    def _evidence_text(self, evidence: dict) -> str:
        parts = [
            evidence.get("claim", ""),
            evidence.get("result_summary", ""),
            evidence.get("method", ""),
            " ".join(str(x) for x in evidence.get("tool_calls", []) or []),
        ]
        metrics = evidence.get("metrics") or {}
        if isinstance(metrics, dict):
            parts.extend(str(k) for k in metrics.keys())
        return " ".join(str(p) for p in parts if p).lower()

    def _task_match_terms(self, task: dict) -> list[str]:
        terms = []
        for key in ("subject", "expected_output", "required_capability"):
            value = task.get(key)
            if value:
                terms.append(str(value))
        for item in task.get("evidence_requirements") or []:
            terms.append(str(item))
        return [t.lower() for t in terms if t]

    def complete_matching_tasks_from_evidence(
        self,
        session_id: str,
        evidence: dict,
        analysis_spec_id: str = "",
    ) -> list[int]:
        evidence_text = self._evidence_text(evidence)
        evidence_id = evidence.get("id", "")
        completed: list[int] = []
        for task in self.list_active_for_scope(session_id=session_id):
            if task.get("status") not in ("pending", "in_progress"):
                continue
            if analysis_spec_id and task.get("analysis_spec_id") != analysis_spec_id:
                continue
            terms = self._task_match_terms(task)
            if not any(term and term in evidence_text for term in terms):
                continue
            evidence_ids = list(task.get("evidence_ids") or [])
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
            self.update(
                task["id"],
                status="completed",
                evidence_ids=evidence_ids,
                result_summary=evidence.get("result_summary", "") or evidence.get("claim", ""),
                confidence=evidence.get("confidence", ""),
                completed_by="evidence",
            )
            completed.append(task["id"])
        return completed
```

- [ ] **Step 4: Call evidence completion from `record_evidence_record()`**

In `src/data_agent/tools/analysis_flow.py`, inside `record_evidence_record()` after `result["evidence_id"]` is set, add:

```python
    try:
        from data_agent.session.task_manager import task_manager
        session_id = state.session_id if state is not None else ""
        spec = state.analysis_spec if state is not None else {}
        completed_task_ids = task_manager.complete_matching_tasks_from_evidence(
            session_id=session_id,
            evidence=payload,
            analysis_spec_id=(spec or {}).get("id", ""),
        )
        if completed_task_ids:
            result["completed_task_ids"] = completed_task_ids
    except Exception as e:
        result["task_completion_error"] = str(e)
```

- [ ] **Step 5: Run task and flow tests**

Run:

```bash
pytest tests/test_task_manager_scope.py tests/test_comprehensive_analysis_flow.py::TestAnalysisFlow -q
```

Expected: PASS. If `TestAnalysisFlow` is not a valid class selector in this file, run `pytest tests/test_comprehensive_analysis_flow.py -q`.

- [ ] **Step 6: Commit**

```bash
git add src/data_agent/session/task_manager.py src/data_agent/tools/analysis_flow.py tests/test_task_manager_scope.py
git commit -m "feat: complete tasks from evidence records"
```

---

### Task 7: Update CLI Formatting And Frontend Compatibility Checks

**Files:**
- Modify: `src/data_agent/session/task_manager.py`
- Modify: `tests/test_web_overhaul.py`
- Modify: `tests/test_task_manager_scope.py`

- [ ] **Step 1: Add test that active formatted list excludes superseded tasks**

Append to `tests/test_task_manager_scope.py`:

```python
def test_format_list_uses_active_plan_scope(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    old_plan = mgr.create_plan(session_id="s1", goal="Old", source="analysis_spec")
    mgr.create("Old pending", session_id="s1", plan_id=old_plan["id"])
    new_plan = mgr.create_plan(session_id="s1", goal="New", source="user_replan")
    mgr.create("New active", session_id="s1", plan_id=new_plan["id"])

    output = mgr.format_list(session_id="s1")

    assert "New active" in output
    assert "Old pending" not in output
```

- [ ] **Step 2: Update `format_list()` to use active scope**

In `TaskManager.format_list()`, replace:

```python
            self.list_for_scope(
```

with:

```python
            self.list_active_for_scope(
```

Keep the arguments unchanged.

- [ ] **Step 3: Add frontend static assertion for default task query**

Append to `tests/test_web_overhaul.py`:

```python
def test_frontend_uses_default_active_task_scope(js):
    assert "fetch('/api/tasks' + query)" in js
    assert "case 'task_update'" in js
    assert "_debouncedLoadTasks()" in js
```

This test confirms the frontend keeps using the backend default active scope and still refreshes on task updates.

- [ ] **Step 4: Run focused compatibility tests**

Run:

```bash
pytest tests/test_task_manager_scope.py tests/test_web_overhaul.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/session/task_manager.py tests/test_task_manager_scope.py tests/test_web_overhaul.py
git commit -m "fix: show active plan tasks in task summaries"
```

---

### Task 8: Focused Regression Suite And Manual Session Check

**Files:**
- No planned source changes.

- [ ] **Step 1: Run task-focused regression suite**

Run:

```bash
pytest tests/test_task_manager_scope.py tests/test_task_plan_versioning.py tests/test_web_workbench_parity.py tests/test_web_overhaul.py -q
```

Expected: PASS.

- [ ] **Step 2: Run analysis-flow regression tests**

Run:

```bash
pytest tests/test_comprehensive_analysis_flow.py tests/test_execution_control.py tests/test_analysis_state_v2.py -q
```

Expected: PASS.

- [ ] **Step 3: Run a manual scoped task query for session `38465eb4172f`**

Run:

```bash
.venv\Scripts\python.exe -c "from data_agent.session.task_manager import task_manager; tasks=task_manager.list_active_for_scope(session_id='38465eb4172f'); print([(t['id'], t['status'], t['subject']) for t in tasks])"
```

Expected: The output should not contain stale pending candidate/spec tasks from the old duplicated groups. If legacy tasks have no active plan registry yet, the output may show legacy tasks until the migration task is executed.

---

### Task 9: Legacy Session Migration For `38465eb4172f`-Style Data

**Files:**
- Modify: `src/data_agent/session/task_manager.py`
- Add test: `tests/test_task_plan_versioning.py`

- [ ] **Step 1: Add regression test for legacy migration**

Append to `tests/test_task_plan_versioning.py`:

```python
def test_migrate_legacy_completed_plan_archives_pending_duplicates(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    mgr.create("build cohorts and calculate retention curve", session_id="s1", analysis_spec_id="candidate")
    mgr.create("分析步骤 1", session_id="s1", analysis_spec_id="spec_1")
    completed = mgr.create("数据预处理与基础指标计算", session_id="s1", analysis_spec_id="spec_1")
    mgr.update(completed["id"], status="completed", result_summary="done")

    result = mgr.migrate_legacy_session_active_plan(session_id="s1")

    active = mgr.list_active_for_scope(session_id="s1")
    history = mgr.list_history_for_scope(session_id="s1")
    assert result["active_plan_id"]
    assert [t["id"] for t in active] == [completed["id"]]
    assert {t["status"] for t in history} == {"superseded"}
```

- [ ] **Step 2: Implement conservative legacy migration**

Add this method to `TaskManager`:

```python
    def migrate_legacy_session_active_plan(self, session_id: str, project_name: str = "") -> dict:
        if self.get_active_plan_id(session_id, project_name):
            return {"active_plan_id": self.get_active_plan_id(session_id, project_name), "migrated": 0}
        scoped = self.list_for_scope(session_id=session_id, project_name=project_name)
        legacy = [t for t in scoped if not t.get("plan_id") and t.get("status") != "deleted"]
        completed = [t for t in legacy if t.get("status") == "completed"]
        if not completed:
            return {"active_plan_id": "", "migrated": 0}

        spec_id = completed[0].get("analysis_spec_id", "")
        plan = self.create_plan(
            session_id=session_id,
            project_name=project_name,
            goal="Migrated completed analysis plan",
            source="legacy_migration",
            analysis_spec_id=spec_id,
            workflow_id=completed[0].get("workflow_id", ""),
        )
        migrated = 0
        for task in legacy:
            if task.get("status") == "completed" and (not spec_id or task.get("analysis_spec_id") == spec_id):
                self.update(
                    task["id"],
                    plan_id=plan["id"],
                    plan_version=plan["version"],
                    plan_status="completed",
                    source=task.get("source") or "legacy_migration",
                )
                migrated += 1
            elif task.get("status") in ("pending", "blocked", "in_progress"):
                self.update(
                    task["id"],
                    status="superseded",
                    superseded_by=plan["id"],
                    source=task.get("source") or "legacy_migration",
                )
        return {"active_plan_id": plan["id"], "migrated": migrated}
```

- [ ] **Step 3: Run migration tests**

Run:

```bash
pytest tests/test_task_plan_versioning.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/data_agent/session/task_manager.py tests/test_task_plan_versioning.py
git commit -m "feat: migrate legacy task plans"
```

---

### Task 10: Final Verification And Handoff

**Files:**
- No planned source changes.

- [ ] **Step 1: Run focused suite**

Run:

```bash
pytest tests/test_task_manager_scope.py tests/test_task_plan_versioning.py tests/test_web_workbench_parity.py tests/test_web_overhaul.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader suite around analysis behavior**

Run:

```bash
pytest tests/test_comprehensive_analysis_flow.py tests/test_execution_control.py tests/test_analysis_state_v2.py tests/test_golden_scenarios.py -q
```

Expected: PASS.

- [ ] **Step 3: Inspect git diff**

Run:

```bash
git diff -- src/data_agent/session/task_manager.py src/data_agent/tools/task_tools.py src/data_agent/agent/analysis_flow_controller.py src/data_agent/tools/analysis_flow.py src/data_agent/web/blueprints/tasks.py tests/test_task_manager_scope.py tests/test_task_plan_versioning.py tests/test_web_workbench_parity.py tests/test_web_overhaul.py
```

Expected: Only planned task-plan versioning changes.

- [ ] **Step 4: Final commit if any verification-only edits were needed**

If verification required small test or implementation fixes, commit them:

```bash
git add src/data_agent/session/task_manager.py src/data_agent/tools/task_tools.py src/data_agent/agent/analysis_flow_controller.py src/data_agent/tools/analysis_flow.py src/data_agent/web/blueprints/tasks.py tests/test_task_manager_scope.py tests/test_task_plan_versioning.py tests/test_web_workbench_parity.py tests/test_web_overhaul.py
git commit -m "test: verify task plan versioning"
```

Expected: No commit is needed if the previous task commits already contain all changes.

---

## Self-Review Notes

Spec coverage:

1. Active panel only shows current plan: Tasks 2, 5, and 7.
2. Replanning and superseding: Tasks 2 and 3.
3. Historical preservation: Tasks 2, 5, and 9.
4. LLM-independent completion assistance: Task 6.
5. Durable task/runtime separation: The plan does not add runtime jobs and keeps changes inside task/workflow/API surfaces.
6. Legacy `38465eb4172f` behavior: Tasks 3 and 9.

Type consistency:

1. Plan fields use the names from the spec: `plan_id`, `plan_version`, `plan_status`, `task_kind`, `source`, `superseded_by`, `archived_at`, `completed_by`, `completed_at`.
2. New statuses are consistently listed as `pending`, `blocked`, `in_progress`, `completed`, `superseded`, `archived`, `deleted`.
3. Query scope values are consistently `active`, `all`, and `history`.
