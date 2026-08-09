from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from data_agent.agent.loop import AgentLoop
from data_agent.agent.tool_outcome import (
    ToolOutcomeState,
    committed_tool_outcome,
    render_committed_tool_content,
)
from data_agent.llm.client import ToolCall
from data_agent.session.task_manager import TaskManager
from data_agent.tools.registry import ToolDefinition, registry


def test_post_execution_scope_error_preserves_evidence_result_and_identity():
    result = json.dumps(
        {"saved": True, "evidence_id": "evidence-71aa", "state_stage": "analyze"}
    )
    scope = SimpleNamespace(
        phase="error",
        error_type="stage3c0b_current_task_missing",
        message="The active plan has no current task.",
    )

    outcome = committed_tool_outcome(result, scope)
    rendered = json.loads(render_committed_tool_content(result, outcome))

    assert outcome.state == ToolOutcomeState.COMMITTED_WITH_WARNING
    assert outcome.artifact_ids == ("evidence-71aa",)
    assert rendered["saved"] is True
    assert rendered["evidence_id"] == "evidence-71aa"
    assert rendered["_tool_outcome"]["state"] == "committed_with_warning"
    assert (
        rendered["_tool_outcome"]["workflow_warning"]["error_type"]
        == "stage3c0b_current_task_missing"
    )


def test_successful_refresh_keeps_tool_content_byte_for_byte():
    content = "plain committed result"
    outcome = committed_tool_outcome(
        content,
        SimpleNamespace(phase="execution", error_type="", message=""),
    )

    assert outcome.state == ToolOutcomeState.COMMITTED
    assert render_committed_tool_content(content, outcome) == content


def test_non_json_result_is_wrapped_only_when_commit_warning_exists():
    outcome = committed_tool_outcome(
        "analysis completed",
        SimpleNamespace(
            phase="error",
            error_type="workflow_refresh_error",
            message="Workflow refresh failed.",
        ),
    )

    rendered = json.loads(render_committed_tool_content("analysis completed", outcome))

    assert rendered["result"] == "analysis completed"
    assert rendered["_tool_outcome"]["state"] == "committed_with_warning"


def test_loop_persists_outcome_to_pre_execution_step_before_terminal_refresh(
    tmp_path,
    monkeypatch,
):
    import data_agent.session.task_manager as task_manager_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = manager.create_plan(
        session_id="session-71aa",
        goal="factor analysis",
        source="analysis_plan",
    )
    task = manager.create(
        "record regression evidence",
        session_id="session-71aa",
        plan_id=plan["id"],
        task_kind="plan_task",
        analysis_plan_id="analysis-plan-71aa",
        step_id="regression-step",
        dataset_inputs=[],
    )
    run_info = manager.materialize_analysis_run(
        session_id="session-71aa",
        project_name="",
        plan_id=plan["id"],
        tasks=[manager.get(task["id"])],
    )
    monkeypatch.setattr(task_manager_module, "task_manager", manager)

    def commit_evidence():
        manager.update(task["id"], status="completed")
        return json.dumps(
            {"saved": True, "evidence_id": "evidence-71aa"},
            ensure_ascii=False,
        )

    monkeypatch.setitem(
        registry._tools,
        "commit_evidence_transaction",
        ToolDefinition(
            name="commit_evidence_transaction",
            description="commit evidence",
            func=commit_evidence,
            parameters={"type": "object", "properties": {}},
            capability=None,
        ),
    )
    loop = AgentLoop(client=object(), session_id="session-71aa")
    loop.context.analysis_state = None
    call = ToolCall(
        id="tool-call-71aa",
        name="commit_evidence_transaction",
        arguments={},
    )

    loop._execute_single_tool(
        call,
        [call],
        0,
        _scope_guard=lambda *_args: "",
    )

    payload = json.loads(loop.messages[-1]["content"])
    assert payload["saved"] is True
    assert payload["evidence_id"] == "evidence-71aa"
    assert "_tool_outcome" not in payload
    coordinator = manager._analysis_run_coordinator(create=False)
    with sqlite3.connect(coordinator.store.path) as connection:
        row = connection.execute(
            """SELECT run_id, step_id, state, artifact_id
            FROM analysis_tool_outcomes WHERE idempotency_key = ?""",
            ("tool-call:tool-call-71aa",),
        ).fetchone()
    run = coordinator.store.get_run(run_info["run_id"])
    assert row == (
        run.run_id,
        run.steps[0].step_id,
        "committed",
        "evidence-71aa",
    )
