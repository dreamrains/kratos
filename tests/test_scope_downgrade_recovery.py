"""P0-1: manual task_create must not silently supersede an active stage plan.

Root cause of the R21 Codex M02 session death (8885cd032ffe): the model called
``record_analysis_plan`` and ``task_create`` in one block; the batch branch of
task_create created a new "llm plan" which SUPERSEDED the active Stage3C0B
plan (its projected tasks included). The resolver then saw "tasks but no stage
tasks" and returned legacy; the authoritative transition validation converted
execution->legacy into a permanent error-phase scope and every later tool call
died with "The authoritative workspace scope disappeared".

The fix: an active structured plan may only be retired by the sanctioned
upload path; manual task creation and plan creation must refuse with a clear
tool error instead of mutating the plan authority.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from data_agent.agent.context import use_agent_context
from data_agent.agent.loop import AgentLoop
from data_agent.session.task_manager import task_manager
from data_agent.session.workspace import workspace
from data_agent.tools.registry import registry


@pytest.fixture
def scoped_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(task_manager, "_dir", tmp_path / "tasks")
    monkeypatch.setattr(task_manager, "_next_id_val", 0)
    loop = AgentLoop(client=object(), session_id="scope-death")
    with use_agent_context(loop.context):
        workspace.add("M02-retention", pd.DataFrame({
            "day": [1, 2, 3, 4, 5, 6, 7],
            "retention": [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10],
        }))
        # Build the state record_analysis_plan's projection would have built:
        # an active analysis plan with projected stage tasks, one started.
        plan = task_manager.create_plan(
            session_id="scope-death", goal="retention analysis", source="analysis_plan",
        )
        for step in ("S1", "S2"):
            task_manager.create(
                f"{step} step", session_id="scope-death",
                plan_id=plan["id"], analysis_plan_id="analysis_plan_1",
                step_id=step,
            )
        task_manager.start_next_ready_stage3c0b_task(
            session_id="scope-death", project_name=""
        )
        loop.context.refresh_workspace_scope()
    return loop, plan


REAL_MANUAL_TASKS = json.dumps([
    {"subject": "S1 描述 D1–D7 留存与衰减", "description": "计算留存值与衰减率",
     "expected_output": "留存表", "stage": "analysis"},
    {"subject": "S2 曲线拟合多模型族", "description": "拟合三族",
     "expected_output": "各族 R² 与参数", "stage": "analysis"},
], ensure_ascii=False)


def _run_tool(loop, name: str, arguments: dict) -> str:
    scope_error = loop._current_task_scope_guard(name, arguments)
    if scope_error:
        return scope_error
    return str(registry.execute(name, arguments))


def test_task_create_during_active_stage_plan_is_refused_without_supersede(scoped_loop):
    loop, plan = scoped_loop
    with use_agent_context(loop.context):
        assert getattr(loop.context.workspace_scope, "phase", None) == "execution"

        result = _run_tool(loop, "task_create", {"tasks": REAL_MANUAL_TASKS})

        # A clear refusal is acceptable; silent plan mutation is not.
        assert "disappeared" not in result
        assert json.loads(result).get("error"), result
        # The active plan must still be the analysis plan, unsuperseded.
        assert task_manager.get_active_plan_id("scope-death", "") == plan["id"]
        tasks = [
            t for t in task_manager.list_all(include_stale=True)
            if t.get("session_id") == "scope-death"
        ]
        assert all(t.get("plan_id") == plan["id"] for t in tasks), tasks
        assert any(t.get("status") == "in_progress" for t in tasks)

        # The scope must survive for subsequent tool calls.
        follow_up = _run_tool(loop, "run_python", {"code": "x=1"})
        assert "disappeared" not in follow_up, follow_up
        assert getattr(loop.context.workspace_scope, "phase", None) != "error"


def test_last_completed_stage_task_keeps_scope_until_publication(scoped_loop):
    loop, plan = scoped_loop
    with use_agent_context(loop.context):
        tasks = [task for task in task_manager.list_all(include_stale=True)
                 if task.get("plan_id") == plan["id"]]
        for task in sorted(tasks, key=lambda item: item["id"]):
            stored=task_manager._load(task["id"]);stored["status"]="completed";task_manager._save(stored)  # Reader-only terminal fixture.
        # Install the complete terminal reader fixture atomically. A partial
        # manual mutation (no in-progress task but pending siblings) is invalid.
        loop._current_task_scope_guard("task_update", {"task_id": tasks[-1]["id"]})
        scope = loop.context.workspace_scope
        assert scope.phase == "synthesis"
        assert scope.plan_id == plan["id"]
        assert scope.error_type == ""
        assert task_manager.get_active_plan_id("scope-death", "") == plan["id"]


def test_create_plan_refuses_to_supersede_active_stage_plan(scoped_loop):
    _loop, plan = scoped_loop
    with pytest.raises(RuntimeError, match="active structured plan"):
        task_manager.create_plan(session_id="scope-death", goal="manual side plan")
    assert task_manager.get_active_plan_id("scope-death", "") == plan["id"]


def test_create_plan_still_allowed_without_active_stage_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(task_manager, "_dir", tmp_path / "tasks2")
    monkeypatch.setattr(task_manager, "_next_id_val", 0)
    plan = task_manager.create_plan(session_id="free", goal="plain workflow")
    assert task_manager.get_active_plan_id("free", "") == plan["id"]
    # Creating a second plan when the first has no non-terminal stage tasks is
    # still a legitimate supersede (the historical behaviour).
    plan2 = task_manager.create_plan(session_id="free", goal="replacement")
    assert task_manager.get_active_plan_id("free", "") == plan2["id"]
