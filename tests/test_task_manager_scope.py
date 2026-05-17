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
