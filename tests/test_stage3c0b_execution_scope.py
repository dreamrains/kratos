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


def test_dataset_guard_blocks_unbound_dataset_and_allows_bound_dataset(tmp_path):
    from data_agent.agent.execution_scope import ensure_dataset_allowed_for_current_task

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)

    blocked = ensure_dataset_allowed_for_current_task(manager, "s1", dataset="iap")
    allowed = ensure_dataset_allowed_for_current_task(manager, "s1", dataset=" banner ")

    assert blocked.allowed is False
    assert blocked.error_type == "dataset_outside_current_task_scope"
    assert allowed.allowed is True


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
    monkeypatch.setattr(sandbox, "workspace", ws)
    ctx = AgentContext(session_id="s1", workspace=ws)

    with use_agent_context(ctx):
        payload = json.loads(sandbox.run_python("get_dataset('iap')['secret'].iloc[0]"))

    assert "dataset_outside_current_task_scope" in payload.get("result", "")
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

    assert "synthesis_cannot_read_raw_dataset" in payload.get("result", "")
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


def test_single_tool_guard_blocks_before_registry_execution(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
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

    assert result is None
    assert called == []
    payload = json.loads(loop.messages[-1]["content"])
    assert payload["error_type"] == "dataset_outside_current_task_scope"


def test_streaming_tool_guard_blocks_before_registry_execution(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
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

    assert called == []
    payload = json.loads(loop.messages[-1]["content"])
    assert payload["error_type"] == "dataset_outside_current_task_scope"


def test_parallel_guard_validates_every_dataset_argument(tmp_path, monkeypatch):
    import data_agent.session.task_manager as task_manager_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager, datasets=["banner"])
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
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

    assert called == [("banner", "banner")]
    assert json.loads(results[0][1])["error_type"] == "dataset_outside_current_task_scope"
    assert results[1][1] == "executed"


def test_tool_guard_checks_all_references_even_when_first_is_blocked(monkeypatch):
    import data_agent.agent.execution_scope as execution_scope

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
    checked = []

    def fake_guard(*args, dataset, **kwargs):
        checked.append(dataset)
        return execution_scope.ScopeGuardResult(
            dataset == "banner",
            "dataset_outside_current_task_scope",
            "blocked",
        )

    monkeypatch.setattr(execution_scope, "ensure_dataset_allowed_for_current_task", fake_guard)

    result = execution_scope.ensure_tool_allowed_for_current_task(
        registry,
        object(),
        "s1",
        "",
        "scope_test_all_references",
        {"left": "iap", "right": "banner"},
    )

    assert result.allowed is False
    assert checked == ["iap", "banner"]


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
def test_real_dataset_output_tools_block_unbound_datasets(
    tmp_path,
    monkeypatch,
    tool_name,
    arguments,
):
    import data_agent.session.task_manager as task_manager_module
    from data_agent.tools import data_io, visualization  # noqa: F401

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _scoped_task(manager)
    monkeypatch.setattr(task_manager_module, "task_manager", manager)
    executed = []
    monkeypatch.setattr(
        registry,
        "execute",
        lambda name, params: executed.append((name, params)) or ToolResult(summary="executed"),
    )
    loop = AgentLoop(client=object(), session_id="s1")
    tc = ToolCall(id=f"tc_{tool_name}", name=tool_name, arguments=arguments)

    loop._execute_single_tool(tc, [tc], 0)

    assert executed == []
    assert json.loads(loop.messages[-1]["content"])["error_type"] == (
        "dataset_outside_current_task_scope"
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
