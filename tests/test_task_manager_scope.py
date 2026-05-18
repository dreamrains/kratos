import json

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


def test_create_plan_version_counts_stale_active_tasks(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    old_plan = mgr.create_plan(session_id="s1", goal="Old", source="analysis_spec")
    old_task = mgr.create(
        "Old pending",
        session_id="s1",
        plan_id=old_plan["id"],
        plan_version=old_plan["version"],
    )
    task_path = mgr._path(old_task["id"])
    task_data = json.loads(task_path.read_text(encoding="utf-8"))
    task_data["created_at"] = "2000-01-01 00:00:00"
    task_path.write_text(json.dumps(task_data, ensure_ascii=False, indent=2), encoding="utf-8")

    new_plan = mgr.create_plan(session_id="s1", goal="New", source="user_replan")

    assert new_plan["version"] == old_plan["version"] + 1
    assert mgr.get(old_task["id"])["status"] == "superseded"


def test_list_active_for_scope_returns_only_active_plan_tasks(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    old_plan = mgr.create_plan(session_id="s1", goal="Old", source="analysis_spec")
    old_task = mgr.create("Old pending", session_id="s1", plan_id=old_plan["id"])
    new_plan = mgr.create_plan(session_id="s1", goal="New", source="user_replan")
    new_task = mgr.create("New active", session_id="s1", plan_id=new_plan["id"])

    tasks = mgr.list_active_for_scope(session_id="s1")

    assert [t["id"] for t in tasks] == [new_task["id"]]
    assert mgr.get(old_task["id"])["status"] == "superseded"


def test_active_plan_scope_includes_stale_pending_active_tasks(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(session_id="s1", goal="Active", source="analysis_spec")
    task = mgr.create("Stale active", session_id="s1", plan_id=plan["id"])
    task_path = mgr._path(task["id"])
    task_data = json.loads(task_path.read_text(encoding="utf-8"))
    task_data["created_at"] = "2000-01-01 00:00:00"
    task_path.write_text(json.dumps(task_data, ensure_ascii=False, indent=2), encoding="utf-8")

    tasks = mgr.list_active_for_scope(session_id="s1")

    assert [t["id"] for t in tasks] == [task["id"]]


def test_session_only_active_scope_includes_project_active_plan(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(
        session_id="s1",
        project_name="Revenue",
        goal="Analyze revenue decline",
        source="analysis_spec",
    )
    task = mgr.create(
        "Project active",
        session_id="s1",
        project_name="Revenue",
        plan_id=plan["id"],
    )

    tasks = mgr.list_active_for_scope(session_id="s1")

    assert [t["id"] for t in tasks] == [task["id"]]


def test_project_only_active_scope_includes_session_project_active_plan(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(
        session_id="s1",
        project_name="Revenue",
        goal="Analyze revenue decline",
        source="analysis_spec",
    )
    task = mgr.create(
        "Project active",
        session_id="s1",
        project_name="Revenue",
        plan_id=plan["id"],
    )

    tasks = mgr.list_active_for_scope(project_name="Revenue")
    history = mgr.list_history_for_scope(project_name="Revenue")

    assert [t["id"] for t in tasks] == [task["id"]]
    assert task["id"] not in {t["id"] for t in history}


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


def test_supersede_active_plan_includes_stale_pending_tasks(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    old_plan = mgr.create_plan(session_id="s1", goal="Old", source="analysis_spec")
    old_task = mgr.create("Old pending", session_id="s1", plan_id=old_plan["id"])
    task_path = mgr._path(old_task["id"])
    task_data = json.loads(task_path.read_text(encoding="utf-8"))
    task_data["created_at"] = "2000-01-01 00:00:00"
    task_path.write_text(json.dumps(task_data, ensure_ascii=False, indent=2), encoding="utf-8")

    mgr.create_plan(session_id="s1", goal="New", source="user_replan")

    assert mgr.get(old_task["id"])["status"] == "superseded"
    history = mgr.list_history_for_scope(session_id="s1")
    assert [t["id"] for t in history] == [old_task["id"]]


def test_complete_matching_task_from_evidence(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(
        session_id="s1",
        goal="Revenue",
        source="analysis_spec",
        analysis_spec_id="spec_1",
    )
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


def test_evidence_completes_analysis_spec_plan_when_terms_do_not_match(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(
        session_id="s1",
        goal="Fit retention formula",
        source="analysis_spec",
        analysis_spec_id="spec_1",
    )
    cohort = mgr.create(
        "build cohorts and calculate retention curve",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_spec_id="spec_1",
        expected_output="retention table by cohort and period",
        required_capability="analysis.cohort",
        evidence_requirements=["retention_rate"],
        source="analysis_spec",
    )
    forecast = mgr.create(
        "supporting check: Forecast & Decision Simulation",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_spec_id="spec_1",
        expected_output="Forecast metrics and support decisions.",
        required_capability="analysis.forecast",
        source="analysis_spec",
    )
    confirmation = mgr.create(
        "Confirm analysis method and metric scope",
        session_id="s1",
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_spec_id="spec_1",
        node_type="confirmation",
        task_kind="confirmation",
        source="system_confirmation",
    )

    completed = mgr.complete_matching_tasks_from_evidence(
        session_id="s1",
        evidence={
            "id": "ev_1",
            "claim": "游戏B的新用户留存率遵循幂律衰减模型。",
            "result_summary": "幂律模型R²=0.9825，已生成拟合曲线和预测曲线。",
            "tool_calls": ["run_python", "create_chart"],
            "metrics": {"sample_size": 56, "r2": 0.9825},
        },
        analysis_spec_id="spec_1",
    )

    assert completed == [cohort["id"], forecast["id"]]
    assert mgr.get(cohort["id"])["status"] == "completed"
    assert mgr.get(forecast["id"])["status"] == "completed"
    assert mgr.get(confirmation["id"])["status"] == "superseded"
    assert [t["id"] for t in mgr.list_active_for_scope(session_id="s1")] == [cohort["id"], forecast["id"]]


def test_format_list_uses_active_plan_scope(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    old_plan = mgr.create_plan(session_id="s1", goal="Old", source="analysis_spec")
    mgr.create("Old pending", session_id="s1", plan_id=old_plan["id"])
    new_plan = mgr.create_plan(session_id="s1", goal="New", source="user_replan")
    mgr.create("New active", session_id="s1", plan_id=new_plan["id"])

    output = mgr.format_list(session_id="s1")

    assert "New active" in output
    assert "Old pending" not in output
