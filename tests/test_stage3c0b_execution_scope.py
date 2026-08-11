from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.analysis_state import AnalysisSessionState, analysis_state_summary
from data_agent.agent.loop import AgentLoop
from data_agent.llm.client import Response, ToolCall
from data_agent.session.task_manager import TaskManager
from data_agent.session.workspace import Workspace
from data_agent.tools.registry import ToolCapability, ToolDefinition, ToolResult, registry


def _scoped_task(
    manager: TaskManager,
    *,
    session_id: str = "s1",
    project_name: str = "",
    datasets: list[str] | None = None,
    contracts: list[str] | None = None,
    mode: str = "single",
    step_id: str = "step_banner",
) -> dict:
    plan = manager.create_plan(
        session_id=session_id,
        project_name=project_name,
        goal="Analyze banner",
        source="analysis_plan",
    )
    task = manager.create(
        "Analyze banner",
        session_id=session_id,
        project_name=project_name,
        plan_id=plan["id"],
        plan_version=plan["version"],
        analysis_plan_id="analysis_plan_banner",
        step_id=step_id,
        dataset_inputs=datasets if datasets is not None else ["banner"],
        dataset_contract_ids=contracts if contracts is not None else ["contract_banner"],
        combination_mode=mode,
    )
    manager.update(task["id"], status="in_progress")
    return task


def _install_tool(monkeypatch, name, func, parameters, capability):
    definition = ToolDefinition(
        name=name,
        description="test tool",
        func=func,
        parameters=parameters,
        capability=capability,
    )
    monkeypatch.setitem(registry._tools, name, definition)
    if capability is not None:
        monkeypatch.setitem(registry._capabilities, name, capability)


def test_current_execution_scope_selects_unique_in_progress_task(tmp_path):
    from data_agent.agent.execution_scope import current_execution_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    task = _scoped_task(manager, datasets=["  banner  ", ""], contracts=[" contract_banner "])

    scope = current_execution_scope(manager, "s1")

    assert scope.active is True
    assert scope.task_id == task["id"]
    assert scope.step_id == "step_banner"
    assert scope.combination_mode == "single"
    assert scope.allowed_datasets == {"banner"}
    assert scope.dataset_contract_ids == {"contract_banner"}


def test_execution_scope_is_immutable_and_has_independent_sets():
    from data_agent.agent.execution_scope import ExecutionScope

    first = ExecutionScope(active=False)
    second = ExecutionScope(active=False)

    assert first.allowed_datasets is not second.allowed_datasets
    with pytest.raises(FrozenInstanceError):
        first.active = True


def test_no_in_progress_or_legacy_in_progress_task_keeps_scope_inactive(tmp_path):
    from data_agent.agent.execution_scope import current_execution_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    legacy = manager.create("Legacy task", session_id="s1")
    manager.update(legacy["id"], status="in_progress")

    scope = current_execution_scope(manager, "s1")

    assert scope.active is False
    assert scope.error_type == ""


def test_multiple_in_progress_stage3c0b_tasks_fail_closed(tmp_path):
    from data_agent.agent.execution_scope import current_execution_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    second = manager.create(
        "Analyze IAP",
        session_id="s1",
        plan_id=manager.get_active_plan_id("s1"),
        analysis_plan_id="analysis_plan_banner",
        step_id="step_iap",
        dataset_inputs=["iap"],
    )
    manager.update(second["id"], status="in_progress")

    scope = current_execution_scope(manager, "s1")

    assert scope.active is False
    assert scope.error_type == "multiple_in_progress_tasks"
    assert "only one" in scope.message.lower()


def test_scope_isolated_by_session_and_project(tmp_path):
    from data_agent.agent.execution_scope import current_execution_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, session_id="s1", project_name="p1", datasets=["banner"])
    _scoped_task(manager, session_id="s1", project_name="p2", datasets=["iap"], step_id="step_iap")

    scope = current_execution_scope(manager, "s1", "p1")

    assert scope.allowed_datasets == {"banner"}
    assert scope.step_id == "step_banner"


def test_dataset_guard_advises_on_unbound_dataset_and_allows_bound_dataset(tmp_path):
    from data_agent.agent.execution_scope import (
        consume_advisory_scope_warnings,
        ensure_dataset_allowed_for_current_task,
    )

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    consume_advisory_scope_warnings()  # drain warnings from prior tests

    advised = ensure_dataset_allowed_for_current_task(manager, "s1", dataset="iap")
    allowed = ensure_dataset_allowed_for_current_task(manager, "s1", dataset=" banner ")

    # D7: execution scope is advisory — an unbound dataset is allowed (not blocked),
    # with a recorded warning. A bound dataset is allowed as before.
    assert allowed.allowed is True
    assert advised.allowed is True
    assert advised.error_type == ""
    warnings = consume_advisory_scope_warnings()
    assert any(
        w["dataset"] == "iap"
        and w["warning"] == "dataset_outside_current_task_scope"
        for w in warnings
    )


def test_dataset_guard_blocks_synthesis_from_raw_dataset(tmp_path):
    from data_agent.agent.execution_scope import ensure_dataset_allowed_for_current_task

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, mode="synthesis")

    result = ensure_dataset_allowed_for_current_task(manager, "s1", dataset="banner")

    assert result.allowed is False
    assert result.error_type == "synthesis_cannot_read_raw_dataset"


def test_run_python_get_dataset_cannot_read_unbound_dataset(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.sandbox as sandbox

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    ws = Workspace()
    ws.add("banner", pd.DataFrame({"value": [1]}))
    ws.add("iap", pd.DataFrame({"secret": [9876]}))
    # Do NOT replace sandbox.workspace with the raw store: under the advisory
    # scope (D7) the loop-level guard no longer blocks, so data isolation for
    # unbound datasets is enforced by the scope-aware proxy (workspace.get →
    # None → dataset_not_found), which is the production access path.
    ctx = AgentContext(session_id="s1", workspace=ws)

    with use_agent_context(ctx):
        payload = json.loads(sandbox.run_python("get_dataset('iap')['secret'].iloc[0]"))

    # The advisory scope guard no longer blocks the call; data isolation for
    # the unbound dataset is enforced by the scope-aware proxy, which hides
    # "iap" (returns None → dataset_not_found).
    assert payload["error_type"] == "dataset_not_found"
    assert "dataset_outside_current_task_scope" not in payload["error"]
    assert "9876" not in payload.get("result", "")


def test_run_python_get_dataset_blocks_raw_reads_during_synthesis(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.sandbox as sandbox

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=[], mode="synthesis")
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    ws = Workspace()
    ws.add("banner", pd.DataFrame({"secret": [9876]}))
    monkeypatch.setattr(sandbox, "workspace", ws)
    ctx = AgentContext(session_id="s1", workspace=ws)

    with use_agent_context(ctx):
        payload = json.loads(sandbox.run_python("get_dataset('banner')['secret'].iloc[0]"))

    assert payload["error_type"] == "sandbox_execution_error"
    assert "synthesis_cannot_read_raw_dataset" in payload["error"]
    assert "9876" not in payload.get("result", "")


def test_run_python_get_dataset_keeps_allowed_and_inactive_reads_working(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.sandbox as sandbox

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    ws = Workspace()
    ws.add("banner", pd.DataFrame({"value": [42]}))
    ws.add("iap", pd.DataFrame({"value": [84]}))

    with use_agent_context(AgentContext(session_id="s1", workspace=ws)):
        allowed = json.loads(sandbox.run_python("get_dataset('banner')['value'].iloc[0]"))
    with use_agent_context(AgentContext(session_id="legacy", workspace=ws)):
        inactive = json.loads(sandbox.run_python("get_dataset('iap')['value'].iloc[0]"))

    assert allowed["result"] == "42"
    assert inactive["result"] == "84"
    assert "list_datasets" not in sandbox._build_safe_globals()
    assert "get_metadata" not in sandbox._build_safe_globals()


def test_interpret_dataset_does_not_scan_unbound_datasets(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.data_understand as data_understand

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    ws = Workspace()
    ws.add("banner", pd.DataFrame({"user_id": [1, 2], "value": [10, 20]}))
    ws.add("iap", pd.DataFrame({"user_id": [1, 2], "secret": [9876, 9877]}))
    monkeypatch.setattr(data_understand, "workspace", ws)
    monkeypatch.setattr("data_agent.tools._utils.workspace", ws)

    with use_agent_context(AgentContext(session_id="s1", workspace=ws)):
        result = data_understand.interpret_dataset("banner")

    assert isinstance(result, ToolResult)
    assert result.data is not None
    assert result.data.get("cross_dataset_hints", []) == []
    assert "iap" not in result.summary


def test_interpret_dataset_blocks_synthesis_before_inspecting_data(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.data_understand as data_understand

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=[], mode="synthesis")
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    ws = Workspace()
    ws.add("banner", pd.DataFrame({"secret": [9876]}))
    monkeypatch.setattr(data_understand, "workspace", ws)
    monkeypatch.setattr("data_agent.tools._utils.workspace", ws)
    inspected = []
    monkeypatch.setattr(
        data_understand,
        "_classify_columns",
        lambda df: inspected.append(df) or {},
    )

    with use_agent_context(AgentContext(session_id="s1", workspace=ws)):
        result = data_understand.interpret_dataset("banner")

    payload = json.loads(result)
    assert payload["error_type"] == "synthesis_cannot_read_raw_dataset"
    assert inspected == []


def test_interpret_dataset_keeps_relationships_within_allowed_scope(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.data_understand as data_understand

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner", "iap"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    ws = Workspace()
    ws.add("banner", pd.DataFrame({"user_id": [1, 2], "value": [10, 20]}))
    ws.add("iap", pd.DataFrame({"user_id": [1, 2], "value": [30, 40]}))
    monkeypatch.setattr(data_understand, "workspace", ws)
    monkeypatch.setattr("data_agent.tools._utils.workspace", ws)

    with use_agent_context(AgentContext(session_id="s1", workspace=ws)):
        result = data_understand.interpret_dataset("banner")

    assert isinstance(result, ToolResult)
    assert result.data is not None
    assert any(
        hint["other_dataset"] == "iap"
        for hint in result.data.get("cross_dataset_hints", [])
    )


def test_single_tool_guard_runs_advisory_before_registry_execution(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.agent.execution_scope import consume_advisory_scope_warnings

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    consume_advisory_scope_warnings()
    called = []
    capability = ToolCapability("data.test_read", category="data_view")
    _install_tool(
        monkeypatch,
        "scope_test_read",
        lambda name: called.append(name) or "executed",
        {"type": "object", "properties": {"name": {"type": "string"}}},
        capability,
    )
    loop = AgentLoop(client=object(), session_id="s1")
    tc = ToolCall(id="tc_single", name="scope_test_read", arguments={"name": "iap"})

    result = loop._execute_single_tool(tc, [tc], 0)

    # D7: advisory — the tool executes (not blocked); a warning is recorded.
    assert result is None
    assert called == ["iap"]
    assert loop.messages[-1]["content"] == "executed"
    warnings = consume_advisory_scope_warnings()
    assert any(
        w["dataset"] == "iap" and w["warning"] == "dataset_outside_current_task_scope"
        for w in warnings
    )


def test_streaming_tool_guard_runs_advisory_before_registry_execution(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.agent.execution_scope import consume_advisory_scope_warnings

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    consume_advisory_scope_warnings()
    called = []
    capability = ToolCapability("data.test_stream_read", category="data_view")
    _install_tool(
        monkeypatch,
        "scope_test_stream_read",
        lambda name: called.append(name) or "executed",
        {"type": "object", "properties": {"name": {"type": "string"}}},
        capability,
    )
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context.analysis_state = None
    tc = ToolCall(id="tc_stream", name="scope_test_stream_read", arguments={"name": "iap"})

    list(loop._process_tool_calls(Response(tool_calls=[tc]), round_num=1))

    # D7: advisory — the streaming path also runs the tool (not blocked).
    assert called == ["iap"]
    warnings = consume_advisory_scope_warnings()
    assert any(
        w["dataset"] == "iap" and w["warning"] == "dataset_outside_current_task_scope"
        for w in warnings
    )


def test_record_analysis_plan_survives_post_tool_scope_refresh(tmp_path, monkeypatch):
    """A successful plan mutation must establish, not violate, current scope."""

    import data_agent.agent.loop as loop_module
    import data_agent.session.task_manager as task_manager_module
    from types import SimpleNamespace
    from data_agent.tools import analysis_flow, task_tools  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    cfg = loop_module.get_config()
    monkeypatch.setattr(cfg, "sessions_dir", tmp_path / "sessions")
    monkeypatch.setattr(cfg, "skill_auto_discover", False)

    loop = AgentLoop(client=object(), session_id="plan_scope_refresh")
    loop.context.workspace.add("banner", pd.DataFrame({"revenue": [10, 12]}))
    state = AnalysisSessionState(session_id="plan_scope_refresh")
    state.dataset_contracts = [{
        "id": "contract_banner",
        "dataset": "banner",
        "quality_status": "ready",
    }]
    loop.context.analysis_state = state
    loop._flow_controller = SimpleNamespace(
        check_tool_regression=lambda *args, **kwargs: None
    )
    call = ToolCall(
        id="tc_plan",
        name="record_analysis_plan",
        arguments={
            "plan": {
                "goal": "Analyze banner revenue",
                "method_plan": [{
                    "task": "Check data quality",
                    "method": "detect_data_quality",
                    "output": "Quality findings",
                    "evidence_requirements": ["data quality status"],
                }],
            }
        },
    )

    events = list(
        loop._process_tool_calls(Response(tool_calls=[call]), round_num=1)
    )

    errors = [event for event in events if event.get("type") == "error"]
    assert errors == []
    payload = json.loads(loop.messages[-1]["content"])
    assert "error" not in payload
    tasks = manager.list_active_for_scope(session_id="plan_scope_refresh")
    assert len(tasks) == 1
    assert tasks[0]["status"] == "in_progress"
    assert tasks[0]["dataset_inputs"] == ["banner"]


def test_parallel_guard_validates_every_dataset_argument(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.agent.execution_scope import consume_advisory_scope_warnings

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    consume_advisory_scope_warnings()
    called = []
    capability = ToolCapability("analysis.test_compare", category="relationship")
    _install_tool(
        monkeypatch,
        "scope_test_compare",
        lambda left, right: called.append((left, right)) or "executed",
        {
            "type": "object",
            "properties": {
                "left": {"type": "string"},
                "right": {"type": "string"},
            },
        },
        capability,
    )
    loop = AgentLoop(client=object(), session_id="s1")
    calls = [
        ToolCall(
            id="tc_parallel_1",
            name="scope_test_compare",
            arguments={"left": "banner", "right": "iap"},
        ),
        ToolCall(
            id="tc_parallel_2",
            name="scope_test_compare",
            arguments={"left": "banner", "right": "banner"},
        ),
    ]

    results = loop._execute_tools_parallel(calls)

    # D7: advisory — both calls execute; the out-of-scope "iap" reference is
    # allowed with a recorded warning instead of aborting the parallel call.
    # (Order is non-deterministic under parallel execution.)
    assert len(called) == 2
    assert set(called) == {("banner", "iap"), ("banner", "banner")}
    assert results[0][1] == "executed"
    assert results[1][1] == "executed"
    warnings = consume_advisory_scope_warnings()
    assert any(
        w["dataset"] == "iap" and w["warning"] == "dataset_outside_current_task_scope"
        for w in warnings
    )


def test_tool_guard_checks_all_references_even_when_first_is_advised(tmp_path, monkeypatch):
    import data_agent.agent.execution_scope as execution_scope
    from data_agent.agent.execution_scope import consume_advisory_scope_warnings

    consume_advisory_scope_warnings()
    capability = ToolCapability("analysis.test_compare", category="relationship")
    _install_tool(
        monkeypatch,
        "scope_test_all_references",
        lambda left, right: "unused",
        {
            "type": "object",
            "properties": {
                "left": {"type": "string"},
                "right": {"type": "string"},
            },
        },
        capability,
    )
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner"])

    class TrackingManager:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.list_calls = 0

        def get_active_plan_id(self, *args, **kwargs):
            return self.wrapped.get_active_plan_id(*args, **kwargs)

        def list_all(self, *args, **kwargs):
            self.list_calls += 1
            return self.wrapped.list_all(*args, **kwargs)

    tracking_manager = TrackingManager(manager)

    result = execution_scope.ensure_tool_allowed_for_current_task(
        registry,
        tracking_manager,
        "s1",
        "",
        "scope_test_all_references",
        {"left": "iap", "right": "banner"},
    )

    # D7: advisory — the guard still inspects every dataset reference (the
    # scope is resolved exactly once), but the out-of-scope "iap" is allowed
    # with a recorded warning rather than blocking the tool call.
    assert result.allowed is True
    assert result.error_type == ""
    assert tracking_manager.list_calls == 1
    warnings = consume_advisory_scope_warnings()
    assert any(
        w["dataset"] == "iap" and w["warning"] == "dataset_outside_current_task_scope"
        for w in warnings
    )


def test_legacy_native_dataset_reader_is_classified_without_capability(monkeypatch):
    from data_agent.agent.execution_scope import dataset_arguments_for_tool

    _install_tool(
        monkeypatch,
        "interpret_dataset",
        lambda name: "unused",
        {"type": "object", "properties": {"name": {"type": "string"}}},
        None,
    )

    assert dataset_arguments_for_tool(registry, "interpret_dataset", {"name": "iap"}) == ["iap"]


def test_unrelated_tool_with_name_argument_is_not_falsely_guarded(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    called = []
    capability = ToolCapability("workflow.rename", category="workflow")
    _install_tool(
        monkeypatch,
        "scope_test_rename",
        lambda name: called.append(name) or "renamed",
        {"type": "object", "properties": {"name": {"type": "string"}}},
        capability,
    )
    loop = AgentLoop(client=object(), session_id="s1")
    tc = ToolCall(id="tc_rename", name="scope_test_rename", arguments={"name": "iap"})

    loop._execute_single_tool(tc, [tc], 0)

    assert called == ["iap"]
    assert loop.messages[-1]["content"] == "renamed"


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("create_chart", {"chart_type": "bar", "data": "iap"}),
        (
            "export_output",
            {"output_type": "data", "name": "iap", "path": "data/iap.csv"},
        ),
    ],
)
def test_real_dataset_output_tools_run_advisory_on_unbound_datasets(
    tmp_path,
    monkeypatch,
    tool_name,
    arguments,
):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.agent.execution_scope import consume_advisory_scope_warnings
    from data_agent.tools import data_io, visualization  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    consume_advisory_scope_warnings()
    executed = []
    monkeypatch.setattr(
        registry,
        "execute",
        lambda name, params: executed.append((name, params)) or ToolResult(summary="executed"),
    )
    loop = AgentLoop(client=object(), session_id="s1")
    tc = ToolCall(id=f"tc_{tool_name}", name=tool_name, arguments=arguments)

    loop._execute_single_tool(tc, [tc], 0)

    # D7: advisory — the scope guard records a warning for the unbound dataset
    # reference instead of blocking on ``dataset_outside_current_task_scope``.
    warnings = consume_advisory_scope_warnings()
    assert any(
        w["warning"] == "dataset_outside_current_task_scope" and w["dataset"] == "iap"
        for w in warnings
    )
    if tool_name == "export_output":
        # No further guard → the tool executes.
        assert len(executed) == 1
        assert executed[0][0] == tool_name
    else:
        # create_chart still hits the separate ``current_task_dataset_unavailable``
        # guard (a different, pre-existing check unrelated to this advisory
        # change), so it does not execute.
        assert executed == []
        assert (
            "current_task_dataset_unavailable" in loop.messages[-1]["content"]
        )


def test_create_chart_without_dataset_is_forced_to_unique_current_scope_dataset(
    tmp_path,
    monkeypatch,
):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.tools import visualization  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context.workspace.add("banner", pd.DataFrame({"x": [1]}))
    arguments = {"chart_type": "bar"}

    with use_agent_context(loop.context):
        error = loop._current_task_scope_guard("create_chart", arguments)

    assert error == ""
    assert arguments["data"] == "banner"


@pytest.mark.parametrize("datasets", [[], ["banner", "iap"]])
def test_create_chart_auto_read_fails_closed_without_unique_scope_dataset(
    tmp_path,
    monkeypatch,
    datasets,
):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.tools import visualization  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=datasets)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    loop = AgentLoop(client=object(), session_id="s1")
    arguments = {"chart_type": "bar"}

    error = loop._current_task_scope_guard("create_chart", arguments)

    assert json.loads(error)["error_type"] == "dataset_scope_requires_unique_dataset"
    assert "data" not in arguments


def test_create_chart_cannot_fall_back_when_scoped_dataset_is_unavailable(
    tmp_path,
    monkeypatch,
):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.tools import visualization  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context.workspace.add("iap", pd.DataFrame({"x": [1]}))

    with use_agent_context(loop.context):
        error = loop._current_task_scope_guard(
            "create_chart",
            {"chart_type": "bar", "data": "banner"},
        )

    assert json.loads(error)["error_type"] == "current_task_dataset_unavailable"


def test_streaming_create_chart_cannot_auto_read_during_synthesis(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.tools import visualization  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, mode="synthesis")
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    executed = []
    monkeypatch.setattr(
        registry,
        "execute",
        lambda name, params: executed.append((name, params)) or ToolResult(summary="executed"),
    )
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context.analysis_state = None
    tc = ToolCall(id="tc_chart_synthesis", name="create_chart", arguments={"chart_type": "bar"})

    list(loop._process_tool_calls(Response(tool_calls=[tc]), round_num=1))

    assert executed == []
    payload = json.loads(loop.messages[-1]["content"])
    assert payload["error_type"] == "synthesis_cannot_read_raw_dataset"


def test_export_output_non_data_mode_is_not_treated_as_dataset_read(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.tools import data_io  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    executed = []
    monkeypatch.setattr(
        registry,
        "execute",
        lambda name, params: executed.append((name, params)) or ToolResult(summary="disabled"),
    )
    loop = AgentLoop(client=object(), session_id="s1")
    tc = ToolCall(
        id="tc_export_report",
        name="export_output",
        arguments={"output_type": "report_md", "name": "iap"},
    )

    loop._execute_single_tool(tc, [tc], 0)

    assert executed == [("export_output", tc.arguments)]
    assert loop.messages[-1]["content"] == "disabled"


def test_analysis_state_summary_injects_compact_current_task_scope(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    task = _scoped_task(manager, project_name="p1", datasets=["iap", "banner"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    state = AnalysisSessionState(session_id="s1", project_name="p1")

    summary = analysis_state_summary(state)

    assert (
        f"current_task_scope: task_id={task['id']}, step_id=step_banner, "
        "mode=single, datasets=banner,iap"
    ) in summary


def test_analysis_state_summary_survives_scope_lookup_failure(monkeypatch):
    import data_agent.agent.execution_scope as execution_scope

    monkeypatch.setattr(
        execution_scope,
        "current_execution_scope",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broken")),
    )

    summary = analysis_state_summary(AnalysisSessionState(session_id="s1"))

    assert "session_id: s1" in summary
    assert "current_task_scope" not in summary


def test_successful_tool_does_not_generically_complete_stage3c0b_task(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    task = _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    loop = AgentLoop(client=object(), session_id="s1")

    loop._auto_track_task_progress("describe_dataset", True)

    assert manager.get(task["id"])["status"] == "in_progress"


def test_generic_legacy_completion_does_not_cross_project_scope(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, project_name="p1")
    legacy = manager.create("Other project legacy", session_id="s1", project_name="p2")
    manager.update(legacy["id"], status="in_progress")
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    loop = AgentLoop(client=object(), session_id="s1", project_name="p1")

    loop._auto_track_task_progress("describe_dataset", True)

    assert manager.get(legacy["id"])["status"] == "in_progress"


def test_snapshot_tool_guard_is_pure_and_does_not_resolve_manager_or_workspace(monkeypatch):
    import data_agent.agent.execution_scope as execution_scope
    import data_agent.session.workspace as workspace_module

    snapshot = execution_scope.WorkspaceScopeSnapshot(
        phase="execution",
        session_id="s1",
        plan_id="plan_1",
        task_id=1,
        step_id="step_1",
        allowed_datasets=frozenset({"bound"}),
        dataset_contract_ids=frozenset({"contract_1"}),
    )
    monkeypatch.setattr(
        execution_scope,
        "resolve_workspace_scope",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("manager accessed")),
    )
    monkeypatch.setattr(
        workspace_module.workspace,
        "list_datasets",
        lambda: (_ for _ in ()).throw(AssertionError("workspace accessed")),
    )

    result = execution_scope.ensure_tool_allowed_for_scope(
        registry,
        snapshot,
        "create_chart",
        {"data": "bound"},
    )

    assert result.allowed is True


def test_substantive_tool_call_binds_to_plan_step_before_registry_execution(tmp_path, monkeypatch):
    """A substantive analytical tool call binds to its plan step, and the
    resulting computation ref carries the bound plan/step identity + claim
    key sourced ONLY from the binding (not from workspace scope)."""

    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.eda as eda  # noqa: F401  -- ensures correlation_analysis is registered

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan_record = manager.create_plan(
        session_id="s1",
        project_name="",
        goal="test binding",
        source="analysis_plan",
    )
    task = manager.create(
        "Correlate",
        session_id="s1",
        project_name="",
        plan_id=plan_record["id"],
        plan_version=plan_record["version"],
        analysis_plan_id="plan_bound_step",
        step_id="step_correlate",
        dataset_inputs=["factors"],
        dataset_contract_ids=["duc_factors_v1"],
        combination_mode="single",
    )
    manager.update(task["id"], status="in_progress")
    monkeypatch.setattr(task_manager_module, "task_manager", manager)

    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.dataset_contracts = [{"id": "duc_factors_v1", "dataset": "factors"}]
    envelope_plan = {
        "id": "plan_bound_step",
        "contract_version": "analysis_plan.v1",
        "review_status": "executable",
        "goal": "test binding",
        "analysis_requirements": {
            "step_correlate": [
                {"id": "req_step_correlate_correlation", "name": "correlation"}
            ]
        },
        "method_plan": [
            {
                "step_id": "step_correlate",
                "plan_id": "plan_bound_step",
                "goal": "correlate",
                "node_type": "analysis",
                "required_capability": "analysis.correlation",
                "expected_output": "correlation summary",
                "evidence_requirements": ["correlation"],
                "dataset_inputs": ["factors"],
                "combination_mode": "independent",
                "requirement_ids": ["req_step_correlate_correlation"],
            }
        ],
    }
    state.analysis_plan = envelope_plan
    ctx = AgentContext(session_id="s1", workspace=Workspace())
    ctx.workspace.add("factors", pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
    ctx.analysis_state = state
    monkeypatch.setattr(
        registry,
        "execute",
        lambda name, params: ToolResult(summary=json.dumps({"correlation": 0.9})),
    )
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context = ctx
    tc = ToolCall(id="tc_correlate", name="correlation_analysis", arguments={"name": "factors"})

    cap = registry.capability_for("correlation_analysis")
    assert cap and cap.get("capability_id") == "analysis.correlation"
    binding = loop._bind_tool_call(tc)

    assert binding is not None
    assert binding.ok is True
    assert binding.plan_id == "plan_bound_step"
    assert binding.step_id == "step_correlate"
    assert binding.claim_key
    assert "req_step_correlate_correlation" in binding.requirement_ids

    loop._execute_single_tool(tc, [tc], 0)

    ref = next(r for r in state.computation_refs if r.get("tool_call_id") == "tc_correlate")
    assert ref["plan_id"] == "plan_bound_step"
    assert ref["step_id"] == "step_correlate"
    assert ref["claim_key"] == binding.claim_key
    assert ref["requirement_ids"] == ["req_step_correlate_correlation"]
    assert ref["binding_error_type"] == ""
    tool_diag = next(
        item for item in state.turn_diagnostics
        if item.get("event") == "tool_binding" and item.get("tool_call_id") == "tc_correlate"
    )
    assert tool_diag["ok"] is True
    assert tool_diag["step_id"] == "step_correlate"


def test_unbound_substantive_call_persists_computation_ref_with_empty_identity(tmp_path, monkeypatch):
    """A substantive call that cannot be bound still persists a computation ref,
    but with EMPTY plan/step identity and the structured diagnostic."""

    import data_agent.session.task_manager as task_manager_module
    import data_agent.tools.eda as eda  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan_record = manager.create_plan(
        session_id="s1",
        project_name="",
        goal="no match",
        source="analysis_plan",
    )
    task = manager.create(
        "Orphan correlate",
        session_id="s1",
        project_name="",
        plan_id=plan_record["id"],
        plan_version=plan_record["version"],
        analysis_plan_id="plan_no_match",
        step_id="step_unrelated",
        dataset_inputs=["factors"],
        dataset_contract_ids=["duc_factors_v1"],
        combination_mode="single",
    )
    manager.update(task["id"], status="in_progress")
    monkeypatch.setattr(task_manager_module, "task_manager", manager)

    state = AnalysisSessionState(session_id="s1", data_state="data_loaded")
    state.analysis_plan = {
        "id": "plan_no_match",
        "contract_version": "analysis_plan.v1",
        "review_status": "executable",
        "goal": "no correlation step",
        "analysis_requirements": {},
        "method_plan": [
            {
                "step_id": "step_unrelated",
                "plan_id": "plan_no_match",
                "goal": "different analysis",
                "node_type": "analysis",
                "required_capability": "data.describe",
                "expected_output": "summary",
                "evidence_requirements": ["schema"],
                "dataset_inputs": ["factors"],
                "combination_mode": "independent",
                "requirement_ids": [],
            }
        ],
    }
    ctx = AgentContext(session_id="s1", workspace=Workspace())
    ctx.workspace.add("factors", pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
    ctx.analysis_state = state
    monkeypatch.setattr(
        registry,
        "execute",
        lambda name, params: ToolResult(summary="executed"),
    )
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context = ctx
    tc = ToolCall(id="tc_orphan", name="correlation_analysis", arguments={"name": "factors"})

    binding = loop._bind_tool_call(tc)
    assert binding is not None
    assert binding.ok is False
    assert binding.error_type == "analysis_step_not_found"

    loop._execute_single_tool(tc, [tc], 0)

    ref = next(r for r in state.computation_refs if r.get("tool_call_id") == "tc_orphan")
    assert ref["plan_id"] == ""
    assert ref["step_id"] == ""
    assert ref["claim_key"] == ""
    assert ref["requirement_ids"] == []
    assert ref["binding_error_type"] == "analysis_step_not_found"


def test_non_substantive_call_skips_binding(monkeypatch):
    """Capability-less tools (e.g. workflow helpers) never participate in binding."""

    state = AnalysisSessionState(session_id="s1")
    state.analysis_plan = {
        "id": "plan_anything",
        "method_plan": [{"step_id": "step_1", "required_capability": "data.list"}],
    }
    ctx = AgentContext(session_id="s1", workspace=Workspace())
    ctx.analysis_state = state
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context = ctx

    _install_tool(
        monkeypatch,
        "no_capability_helper",
        lambda: "ok",
        {"type": "object", "properties": {}},
        None,
    )
    tc = ToolCall(id="tc_helper", name="no_capability_helper", arguments={})

    binding = loop._bind_tool_call(tc)

    assert binding is None
