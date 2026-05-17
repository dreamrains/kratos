from data_agent.session.task_manager import TaskManager


def test_list_for_scope_is_strict_by_default(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    current = mgr.create("Current", session_id="s1")
    mgr.create("Other", session_id="s2")
    mgr.create("Global")

    tasks = mgr.list_for_scope(session_id="s1")

    assert [t["id"] for t in tasks] == [current["id"]]


def test_list_for_scope_can_include_global(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    current = mgr.create("Current", session_id="s1")
    global_task = mgr.create("Global")

    tasks = mgr.list_for_scope(session_id="s1", include_global=True)

    assert {t["id"] for t in tasks} == {current["id"], global_task["id"]}


def test_list_for_scope_with_session_and_project_requires_both(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    matching = mgr.create("Matching", session_id="s1", project_name="P")
    mgr.create("Same session other project", session_id="s1", project_name="Other")
    mgr.create("Same project other session", session_id="s2", project_name="P")
    global_task = mgr.create("Global")

    tasks = mgr.list_for_scope(session_id="s1", project_name="P", include_global=True)

    assert [t["id"] for t in tasks] == [matching["id"], global_task["id"]]


def test_list_ready_excludes_blocked_and_non_pending(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    blocker = mgr.create("Blocker", session_id="s1")
    blocked = mgr.create("Blocked", session_id="s1")
    ready = mgr.create("Ready", session_id="s1")
    done = mgr.create("Done", session_id="s1")

    mgr.update(blocked["id"], addBlockedBy=[blocker["id"]])
    mgr.update(done["id"], status="completed")

    ready_tasks = mgr.list_ready(session_id="s1")

    assert [t["id"] for t in ready_tasks] == [blocker["id"], ready["id"]]


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
    archived_task = mgr.create("Archived task", session_id="s1", plan_id=first["id"])
    mgr.update(archived_task["id"], status="archived")
    mgr.create_plan(session_id="s1", goal="Second", source="user_replan")

    history = mgr.list_history_for_scope(session_id="s1")

    assert [t["id"] for t in history] == [old_task["id"], archived_task["id"]]
    assert [t["status"] for t in history] == ["superseded", "archived"]
