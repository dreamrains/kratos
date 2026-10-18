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


def test_new_data_retires_the_exact_active_plan_and_preserves_completed_history(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(session_id="s1", project_name="P", goal="Old basis")
    pending = mgr.create(
        "Pending old step", session_id="s1", project_name="P", plan_id=plan["id"]
    )
    completed = mgr.create(
        "Completed old step", session_id="s1", project_name="P", plan_id=plan["id"]
    )
    mgr.update(completed["id"], status="completed")

    result = mgr.retire_active_plan_for_new_data("s1", "P")

    assert result["retired"] is True
    assert result["plan_id"] == plan["id"]
    assert result["reason"] == "new_data_upload"
    assert [task["id"] for task in result["tasks"]] == [pending["id"]]
    assert mgr.get_active_plan_id("s1", "P") == ""
    assert mgr.get(pending["id"])["status"] == "superseded"
    assert mgr.get(completed["id"])["status"] == "completed"


def test_failed_new_data_transition_restores_exact_plan_and_task_state(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = mgr.create_plan(session_id="s1", project_name="P", goal="Old basis")
    pending = mgr.create(
        "Pending old step", session_id="s1", project_name="P", plan_id=plan["id"],
        plan_status="active", limitations="keep me",
    )
    retirement = mgr.retire_active_plan_for_new_data("s1", "P")

    restored = mgr.restore_retired_plan(retirement)

    assert restored == {
        "restored": True,
        "reason": "ingestion_failed",
        "plan_id": plan["id"],
    }
    assert mgr.get_active_plan_id("s1", "P") == plan["id"]
    assert mgr.get(pending["id"])["status"] == "pending"
    assert mgr.get(pending["id"])["plan_status"] == "active"
    assert mgr.get(pending["id"])["limitations"] == "keep me"


def test_failed_new_data_transition_never_overwrites_a_successor_plan(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    old = mgr.create_plan(session_id="s1", goal="Old")
    mgr.create("Old step", session_id="s1", plan_id=old["id"])
    retirement = mgr.retire_active_plan_for_new_data("s1")
    successor = mgr.create_plan(session_id="s1", goal="Successor")

    restored = mgr.restore_retired_plan(retirement)

    assert restored["restored"] is False
    assert restored["reason"] == "successor_plan_active"
    assert mgr.get_active_plan_id("s1") == successor["id"]


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

    assert completed == []
    updated = mgr.get(task["id"])
    assert updated["status"] != "completed" and not updated["evidence_ids"]
    assert mgr.update(task["id"],status="completed")["status"]=="completed"  # General todo capability remains.


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

    assert completed == []
    assert mgr.get(cohort["id"])["status"] != "completed"
    assert mgr.get(forecast["id"])["status"] != "completed"
    assert mgr.get(confirmation["id"])["status"] != "superseded"
    assert {t["id"] for t in mgr.list_active_for_scope(session_id="s1")} == {cohort["id"],forecast["id"],confirmation["id"]}



def test_format_list_uses_active_plan_scope(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    old_plan = mgr.create_plan(session_id="s1", goal="Old", source="analysis_spec")
    mgr.create("Old pending", session_id="s1", plan_id=old_plan["id"])
    new_plan = mgr.create_plan(session_id="s1", goal="New", source="user_replan")
    mgr.create("New active", session_id="s1", plan_id=new_plan["id"])

    output = mgr.format_list(session_id="s1")

    assert "New active" in output
    assert "Old pending" not in output


# S3: registry entrypoints must honor the manager's existing session/project scope.
import pytest
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace

@pytest.fixture
def task_tool_scope(tmp_path, monkeypatch):
    from data_agent.tools import task_tools
    from data_agent.tools.registry import registry
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    monkeypatch.setattr(task_tools, "task_manager", mgr)
    ctx = AgentContext(session_id="current", project_name="P", workspace=Workspace())
    own = mgr.create("OWN", session_id="current", project_name="P")
    foreign = mgr.create("PRIVATE_OTHER_SESSION", session_id="other", project_name="P")
    peer = mgr.create("PRIVATE_OTHER_PROJECT", session_id="current", project_name="Q")
    with use_agent_context(ctx):
        yield mgr, registry, own, foreign, peer

@pytest.mark.parametrize("scope", ["session", "project"])
@pytest.mark.parametrize("tool", ["task_get", "task_update", "task_update_batch"])
def test_task_tool_scope_rejects_foreign_identity_without_disclosure_or_write(task_tool_scope, scope, tool):
    mgr, registry, own, foreign, peer = task_tool_scope
    target = foreign if scope == "session" else peer
    before = {p.name:p.read_bytes() for p in mgr.dir.glob("*.json")}
    args = {"task_id": target["id"]}
    name = tool
    if tool == "task_update": args["status"] = "completed"
    elif tool == "task_update_batch":
        name = "task_update"
        args = {"updates": json.dumps([{"task_id":own["id"],"status":"completed"},{"task_id":target["id"],"status":"deleted"}])}
    result = registry.execute(name, args)
    assert "error" in json.loads(result.summary), result.summary
    assert "PRIVATE" not in result.summary
    assert {p.name:p.read_bytes() for p in mgr.dir.glob("*.json")} == before

@pytest.mark.parametrize("key", ["addBlocks", "addBlockedBy"])
@pytest.mark.parametrize("batch", [False, True])
def test_task_tool_scope_rejects_foreign_dependencies_before_any_write(task_tool_scope, key, batch):
    mgr, registry, own, foreign, _ = task_tool_scope
    before = {p.name:p.read_bytes() for p in mgr.dir.glob("*.json")}
    update = {"task_id":own["id"], "status":"in_progress", key:[foreign["id"]]}
    args = {"updates":json.dumps([update])} if batch else dict(update, **{key:json.dumps(update[key])})
    result = registry.execute("task_update", args)
    assert "error" in json.loads(result.summary), result.summary
    assert {p.name:p.read_bytes() for p in mgr.dir.glob("*.json")} == before

@pytest.mark.parametrize("fault", ["session", "project", "top_project"])
def test_task_tool_scope_create_cannot_inject_foreign_owner_or_change_active_plan(task_tool_scope, fault):
    mgr, registry, own, foreign, _ = task_tool_scope
    plan = mgr.create_plan(session_id="current", project_name="P", goal="original")
    before = {p.name:p.read_bytes() for p in mgr.dir.glob("*.json")}
    bad = {"subject":"injected"}
    bad["session_id" if fault == "session" else "project_name"] = "other" if fault == "session" else "Q"
    args = {"tasks":json.dumps([{"subject":"valid first"},bad])} if fault != "top_project" else {"subject":"bad", "project_name":"Q"}
    result = registry.execute("task_create", args)
    assert "error" in json.loads(result.summary), result.summary
    assert {p.name:p.read_bytes() for p in mgr.dir.glob("*.json")} == before
    assert mgr.get_active_plan_id("current","P") == plan["id"]

@pytest.mark.parametrize("batch", [False, True])
def test_task_tool_scope_same_scope_lifecycle_and_dependencies_remain_usable(task_tool_scope, batch):
    mgr, registry, own, foreign, peer = task_tool_scope
    args = {"tasks":json.dumps([{"subject":"new"}])} if batch else {"subject":"new"}
    created = json.loads(registry.execute("task_create",args).summary)
    task = created["tasks"][0] if batch else created
    assert task["session_id"] == "current" and task["project_name"] == "P"
    got = json.loads(registry.execute("task_get",{"task_id":task["id"]}).summary)
    assert got["subject"] == "new"
    update = {"task_id":task["id"],"status":"in_progress", "addBlocks":[own["id"]]}
    args = {"updates":json.dumps([update])} if batch else dict(update,addBlocks=json.dumps(update["addBlocks"]))
    changed = json.loads(registry.execute("task_update",args).summary)
    assert "error" not in changed
    assert mgr.get(task["id"])["status"] == "in_progress"
    assert mgr.get(own["id"])["blockedBy"] == [task["id"]]
    complete = registry.execute("task_update", {"task_id":task["id"], "status":"completed"})
    assert "error" not in json.loads(complete.summary)
    assert mgr.get(task["id"])["status"] == "completed" and mgr.get(own["id"])["blockedBy"] == []
    listed = registry.execute("task_list",{}).summary
    assert "PRIVATE" not in listed and "new" in listed
    assert mgr.get(foreign["id"])["status"] == mgr.get(peer["id"])["status"] == "pending"


@pytest.mark.parametrize("fault", ["global", "missing", "owner_change", "bad_id", "bad_dependency"])
def test_task_tool_scope_adjacent_invalid_or_unowned_targets_are_atomic(task_tool_scope, fault):
    mgr, registry, own, foreign, peer = task_tool_scope
    global_task = mgr.create("PRIVATE_GLOBAL")
    before = {p.name:p.read_bytes() for p in mgr.dir.glob("*.json")}
    change = {"task_id":own["id"], "status":"completed"}
    if fault == "global": change["task_id"] = global_task["id"]
    elif fault == "missing": change["task_id"] = 999999
    elif fault == "owner_change": change["project_name"] = "Q"
    elif fault == "bad_id": change["task_id"] = True
    else: change["addBlocks"] = "not an ID array"
    result = registry.execute("task_update",{"updates":json.dumps([change])})
    assert "error" in json.loads(result.summary),result.summary
    assert "PRIVATE" not in result.summary
    assert {p.name:p.read_bytes() for p in mgr.dir.glob("*.json")} == before
