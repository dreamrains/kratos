from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from data_agent.agent.context import AgentContext, get_current_context, use_agent_context
from data_agent.session.task_manager import TaskManager
from data_agent.session.workspace import Workspace, workspace
from data_agent.agent.loop import AgentLoop
from data_agent.llm.client import Response, ToolCall
from data_agent.tools.registry import ToolDefinition, registry


def _stage3c0b_task(
    manager: TaskManager,
    *,
    session_id: str = "s1",
    project_name: str = "",
    datasets: list[str] | None = None,
    mode: str = "single",
    status: str = "in_progress",
) -> dict:
    plan = manager.create_plan(session_id=session_id, project_name=project_name, source="analysis_plan")
    task = manager.create(
        "analyze",
        session_id=session_id,
        project_name=project_name,
        plan_id=plan["id"],
        analysis_plan_id="analysis_plan_1",
        step_id="step_1",
        dataset_inputs=datasets or ["bound"],
        dataset_contract_ids=["contract_1"],
        combination_mode=mode,
    )
    manager.update(task["id"], status=status)
    return task


def _bind_manager(monkeypatch, manager: TaskManager) -> None:
    import data_agent.session.task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "task_manager", manager)


def _install_unclassified_reader(monkeypatch, name: str) -> None:
    monkeypatch.setitem(
        registry._tools,
        name,
        ToolDefinition(
            name=name,
            description="unclassified reader",
            func=lambda: str(workspace.get("secret")),
            parameters={"type": "object", "properties": {}},
            capability=None,
        ),
    )


def test_workspace_scope_snapshot_is_immutable_and_stably_fingerprinted():
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

    first = WorkspaceScopeSnapshot(
        phase="execution",
        session_id="s1",
        project_name="p1",
        plan_id="plan_1",
        task_id=7,
        step_id="step_1",
        allowed_datasets=frozenset({"b", "a"}),
        dataset_contract_ids=frozenset({"contract_1"}),
    )
    reordered = WorkspaceScopeSnapshot(
        phase="execution",
        session_id="s1",
        project_name="p1",
        plan_id="plan_1",
        task_id=7,
        step_id="step_1",
        allowed_datasets=frozenset({"a", "b"}),
        dataset_contract_ids=frozenset({"contract_1"}),
    )

    assert first.fingerprint == reordered.fingerprint
    assert first.fingerprint.startswith("sha256:")
    with pytest.raises(FrozenInstanceError):
        first.phase = "legacy"


def test_resolver_uses_exact_blank_inbox_scope_and_active_plan(tmp_path):
    from data_agent.agent.execution_scope import resolve_workspace_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    inbox = _stage3c0b_task(manager, datasets=["inbox"])
    _stage3c0b_task(manager, project_name="p1", datasets=["project"])

    scope = resolve_workspace_scope(manager, "s1", "")

    assert scope.task_id == inbox["id"]
    assert scope.project_name == ""
    assert scope.allowed_datasets == frozenset({"inbox"})


def test_resolver_preserves_exact_nonblank_session_and_project_identity(tmp_path):
    from data_agent.agent.execution_scope import resolve_workspace_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    task = _stage3c0b_task(
        manager,
        session_id=" session  one ",
        project_name="Project  Alpha",
        datasets=["bound"],
    )

    scope = resolve_workspace_scope(manager, " session  one ", "Project  Alpha")

    assert scope.session_id == " session  one "
    assert scope.project_name == "Project  Alpha"
    assert scope.task_id == task["id"]


def test_active_stage3c0b_plan_without_current_task_fails_closed(tmp_path):
    from data_agent.agent.execution_scope import resolve_workspace_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    task = _stage3c0b_task(manager, status="pending")

    scope = resolve_workspace_scope(manager, "s1", "")

    assert scope.plan_id == manager.get_active_plan_id("s1", "")
    assert scope.phase == "error"
    assert scope.task_id == 0
    assert scope.error_type == "stage3c0b_current_task_missing"
    assert task["id"]


def test_active_analysis_plan_without_task_records_fails_closed(tmp_path):
    from data_agent.agent.execution_scope import resolve_workspace_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = manager.create_plan(session_id="s1", source="analysis_plan")

    scope = resolve_workspace_scope(manager, "s1", "")

    assert scope.plan_id == plan["id"]
    assert scope.phase == "error"
    assert scope.error_type == "stage3c0b_current_task_missing"


def test_active_plan_without_task_records_fails_closed_conservatively(tmp_path):
    from data_agent.agent.execution_scope import resolve_workspace_scope

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    manager.create_plan(session_id="s1", source="user_replan")

    scope = resolve_workspace_scope(manager, "s1", "")

    assert scope.phase == "error"
    assert scope.error_type == "stage3c0b_current_task_missing"


def test_task_manager_does_not_introduce_active_plan_provenance_sidecar(tmp_path):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")

    manager.create_plan(session_id="s1", source="analysis_plan")

    assert not (tmp_path / "tasks" / "active_plan_sources.json").exists()
    assert not hasattr(manager, "get_active_plan_source")


def test_scoped_proxy_hides_unbound_dataset_and_returns_read_copies(tmp_path, monkeypatch):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["bound"])
    _bind_manager(monkeypatch, manager)
    store = Workspace()
    store.add("bound", pd.DataFrame({"value": [1]}))
    store.add("secret", pd.DataFrame({"token": [9876]}))
    ctx = AgentContext(session_id="s1", workspace=store)

    with use_agent_context(ctx):
        ctx.refresh_workspace_scope()
        assert set(workspace.list_datasets()) == {"bound"}
        assert workspace.exists("bound") is True
        assert workspace.exists("secret") is False
        assert workspace.get("secret") is None
        assert workspace.get_metadata("secret") == {}
        assert set(workspace._datasets) == {"bound"}
        frame = workspace.get("bound")
        frame.loc[0, "value"] = 100
        assert workspace.get("bound").loc[0, "value"] == 1


def test_synthesis_hides_all_raw_details_and_blocks_writes(tmp_path, monkeypatch):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["bound"], mode="synthesis")
    _bind_manager(monkeypatch, manager)
    store = Workspace()
    store.add("bound", pd.DataFrame({"secret_column": [9876]}))

    with use_agent_context(AgentContext(session_id="s1", workspace=store)) as ctx:
        ctx.refresh_workspace_scope()
        assert workspace.list_datasets() == {}
        assert workspace.get("bound") is None
        assert workspace.get_metadata("bound") == {}
        assert workspace.get_transform_log() == []
        assert workspace.add("new", pd.DataFrame({"x": [1]})) == "Error: synthesis_cannot_mutate_raw_data"
        assert store.get("new") is None


@pytest.mark.parametrize(
    ("mode", "status", "write_error"),
    [
        ("synthesis", "in_progress", "Error: synthesis_cannot_mutate_raw_data"),
        ("single", "pending", "Error: error_cannot_mutate_raw_data"),
    ],
)
def test_public_context_workspace_cannot_bypass_synthesis_or_error_scope(
    tmp_path,
    monkeypatch,
    mode,
    status,
    write_error,
):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["secret"], mode=mode, status=status)
    _bind_manager(monkeypatch, manager)
    store = Workspace()
    store.add("secret", pd.DataFrame({"secret_column": [9876]}))
    store.set_metadata("secret", "context", "private context")

    with use_agent_context(AgentContext(session_id="s1", workspace=store)) as ctx:
        ctx.refresh_workspace_scope()
        public_workspace = get_current_context().workspace
        assert not isinstance(public_workspace, Workspace)
        assert public_workspace.get("secret") is None
        assert public_workspace.list_datasets() == {}
        assert public_workspace._datasets == {}
        assert public_workspace._metadata == {}
        assert public_workspace.add("new", pd.DataFrame({"x": [1]})) == write_error
        assert public_workspace.set_metadata("secret", "context", "changed") == write_error

    assert store.get("new") is None
    assert store.get_metadata("secret", "context") == "private context"


@pytest.mark.parametrize(
    ("mode", "status"),
    [("synthesis", "in_progress"), ("single", "pending")],
)
def test_reflection_does_not_expose_raw_workspace_from_context_or_proxy(
    tmp_path,
    monkeypatch,
    mode,
    status,
):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["secret"], mode=mode, status=status)
    _bind_manager(monkeypatch, manager)
    store = Workspace()
    store.add("secret", pd.DataFrame({"secret_column": [9876]}))

    with use_agent_context(AgentContext(session_id="s1", workspace=store)) as ctx:
        ctx.refresh_workspace_scope()
        public_workspace = ctx.workspace
        inspected = [ctx, public_workspace, workspace]
        exposed = []
        for owner in inspected:
            for name, value in vars(owner).items():
                if isinstance(value, Workspace):
                    exposed.append((type(owner).__name__, name))
            for name in dir(owner):
                try:
                    value = getattr(owner, name)
                except Exception:
                    continue
                if isinstance(value, Workspace):
                    exposed.append((type(owner).__name__, name))

        import data_agent.session.workspace as workspace_module

        exposed.extend(
            ("workspace_module", name)
            for name, value in vars(workspace_module).items()
            if isinstance(value, Workspace)
        )

    assert exposed == []


@pytest.mark.parametrize(
    ("mode", "status", "write_error"),
    [
        ("synthesis", "in_progress", "Error: synthesis_cannot_mutate_raw_data"),
        ("single", "pending", "Error: error_cannot_mutate_raw_data"),
    ],
)
def test_opaque_workspace_capability_operations_still_enforce_scope(
    tmp_path,
    monkeypatch,
    mode,
    status,
    write_error,
):
    import data_agent.session.workspace as workspace_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["secret"], mode=mode, status=status)
    _bind_manager(monkeypatch, manager)
    store = Workspace()
    store.add("secret", pd.DataFrame({"secret_column": [9876]}))

    with use_agent_context(AgentContext(session_id="s1", workspace=store)) as ctx:
        ctx.refresh_workspace_scope()
        token = next(
            (value for name, value in vars(ctx).items() if "workspace_token" in name),
            None,
        )
        get_operation = getattr(workspace_module, "_workspace_get_operation", None)
        add_operation = getattr(workspace_module, "_workspace_add_operation", None)
        generic_operation = getattr(workspace_module, "_workspace_operation", None)
        assert token is not None
        assert callable(get_operation)
        assert callable(add_operation)
        assert callable(generic_operation)
        assert get_operation(token, "secret") is None
        assert add_operation(token, "new", pd.DataFrame({"x": [1]})) == write_error
        assert generic_operation(token, "get", "secret") is None
        assert generic_operation(token, "add", "generic_new", pd.DataFrame({"x": [1]})) == write_error

    assert store.get("new") is None
    assert store.get("generic_new") is None


def test_planning_exposes_schema_quality_and_bounded_preview_only(monkeypatch):
    store = Workspace()
    store.add("orders", pd.DataFrame({"order_id": [1, 2, 3], "amount": [10, 20, 30]}))
    store.set_metadata("orders", "quality", {"missing": 0})
    ctx = AgentContext(session_id="s1", workspace=store)

    with use_agent_context(ctx):
        with ctx.planning_workspace_scope(["orders"], preview_rows=2):
            assert workspace.get("orders") is None
            assert workspace.planning_schema("orders") == ["order_id", "amount"]
            assert workspace.planning_quality("orders") == {"missing": 0}
            preview = workspace.planning_preview("orders", rows=100)
            assert list(preview) == [
                {"order_id": 1, "amount": 10},
                {"order_id": 2, "amount": 20},
            ]


@pytest.mark.parametrize("surface", ["public", "opaque"])
@pytest.mark.parametrize("phase", ["planning", "synthesis", "error"])
def test_restricted_scope_blocks_every_workspace_mutator_and_persistence(
    tmp_path,
    monkeypatch,
    surface,
    phase,
):
    import data_agent.session.history as history
    import data_agent.session.workspace as workspace_module
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

    monkeypatch.setattr(history, "_session_dir", lambda session_id: tmp_path)
    store = Workspace()
    original = pd.DataFrame({"order_id": [1], "amount": [10]})
    store.add("orders", original)
    store.set_metadata("orders", "quality", {"missing": 0})
    store._active_project = "original-project"
    ctx = AgentContext(session_id="s1", workspace=store)

    with use_agent_context(ctx):
        scope = (
            ctx.planning_workspace_scope(["orders"])
            if phase == "planning"
            else ctx.bind_workspace_scope(WorkspaceScopeSnapshot(
                phase=phase,
                allowed_datasets=frozenset({"orders"}),
                error_type="scope_error" if phase == "error" else "",
            ))
        )
        with scope:
            if surface == "public":
                calls = [
                    lambda: workspace.add("new", pd.DataFrame({"x": [1]})),
                    lambda: workspace.derive("orders", "derived", original, "copy"),
                    lambda: workspace.set_metadata("orders", "quality", {"missing": 1}),
                    lambda: workspace.log_transform("orders", "filter", "orders", "x > 0"),
                    lambda: workspace.save_meta("s1"),
                    lambda: workspace.persist_dataset("s1", "orders"),
                    lambda: workspace.set_project("other-project"),
                    lambda: workspace.clear_project(),
                    lambda: workspace.remove("orders"),
                ]
            else:
                token = next(
                    value for name, value in vars(ctx).items() if "workspace_token" in name
                )
                operate = workspace_module._workspace_operation
                calls = [
                    lambda: operate(token, "add", "new", pd.DataFrame({"x": [1]})),
                    lambda: operate(token, "derive", "orders", "derived", original, "copy"),
                    lambda: operate(token, "set_metadata", "orders", "quality", {"missing": 1}),
                    lambda: operate(token, "log_transform", "orders", "filter", "orders", "x > 0"),
                    lambda: operate(token, "save_meta", "s1"),
                    lambda: operate(token, "persist", "s1", "orders"),
                    lambda: operate(token, "set_project", "other-project"),
                    lambda: operate(token, "clear_project"),
                    lambda: operate(token, "remove", "orders"),
                ]

            results = [call() for call in calls]

    assert results == [f"Error: {phase}_cannot_mutate_raw_data"] * len(calls)
    pd.testing.assert_frame_equal(store.get("orders"), original)
    assert store.get("new") is None
    assert store.get("derived") is None
    assert store._derived_lineage == {}
    assert store.get_metadata("orders") == {"quality": {"missing": 0}}
    assert store.get_transform_log() == []
    assert store.active_project == "original-project"
    assert not (tmp_path / "workspace_meta.json").exists()
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("surface", ["public", "opaque"])
@pytest.mark.parametrize("operation", ["set_project", "clear_project"])
def test_execution_scope_blocks_project_identity_mutations(
    tmp_path,
    monkeypatch,
    surface,
    operation,
):
    import data_agent.object_manager as object_manager_module
    import data_agent.session.workspace as workspace_module

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["bound"])
    _bind_manager(monkeypatch, manager)
    monkeypatch.setattr(
        object_manager_module,
        "get_object_manager",
        lambda: SimpleNamespace(get=lambda name: {"name": name}),
    )
    store = Workspace()
    store.add("bound", pd.DataFrame({"visible": [1]}))
    store.add("secret", pd.DataFrame({"token": [9876]}))

    with use_agent_context(AgentContext(session_id="s1", project_name="", workspace=store)) as ctx:
        ctx.refresh_workspace_scope()
        if surface == "public":
            result = (
                workspace.set_project("other-project")
                if operation == "set_project"
                else workspace.clear_project()
            )
        else:
            token = next(
                value for name, value in vars(ctx).items() if "workspace_token" in name
            )
            result = workspace_module._workspace_operation(
                token,
                operation,
                *(["other-project"] if operation == "set_project" else []),
            )

        assert result == "Error: execution_cannot_change_project_identity"
        assert ctx.workspace_scope.phase == "execution"
        assert workspace.get("secret") is None

    assert store.active_project is None


def test_scope_binding_rejects_legacy_expansion_identity_change_and_phase_relaxation():
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

    ctx = AgentContext(session_id="s1", project_name="p1", workspace=Workspace())
    execution = WorkspaceScopeSnapshot(
        phase="execution",
        session_id="s1",
        project_name="p1",
        plan_id="plan_1",
        task_id=7,
        step_id="step_1",
        allowed_datasets=frozenset({"bound"}),
        dataset_contract_ids=frozenset({"contract_1"}),
    )
    unsafe = [
        WorkspaceScopeSnapshot(),
        WorkspaceScopeSnapshot(
            phase="execution",
            session_id="s1",
            project_name="p1",
            plan_id="plan_1",
            task_id=7,
            step_id="step_1",
            allowed_datasets=frozenset({"bound", "secret"}),
            dataset_contract_ids=frozenset({"contract_1"}),
        ),
        WorkspaceScopeSnapshot(
            phase="execution",
            session_id="other-session",
            project_name="p1",
            plan_id="plan_1",
            task_id=7,
            step_id="step_1",
            allowed_datasets=frozenset({"bound"}),
            dataset_contract_ids=frozenset({"contract_1"}),
        ),
    ]

    with ctx.bind_workspace_scope(execution):
        for forged in unsafe:
            with pytest.raises(PermissionError, match="workspace_scope_escalation"):
                with ctx.bind_workspace_scope(forged):
                    pass

    planning = WorkspaceScopeSnapshot(
        phase="planning",
        session_id="s1",
        project_name="p1",
        plan_id="plan_1",
        allowed_datasets=frozenset({"bound"}),
    )
    with ctx.bind_workspace_scope(planning):
        with pytest.raises(PermissionError, match="workspace_scope_escalation"):
            with ctx.bind_workspace_scope(WorkspaceScopeSnapshot(
                phase="execution",
                session_id="s1",
                project_name="p1",
                plan_id="plan_1",
                allowed_datasets=frozenset({"bound"}),
            )):
                pass


def test_workspace_scope_contextvars_are_not_discoverable_on_context_or_module():
    from contextvars import ContextVar
    import data_agent.agent.context as context_module

    ctx = AgentContext(session_id="s1", workspace=Workspace())

    assert not any(isinstance(value, ContextVar) for value in vars(ctx).values())
    assert not any(isinstance(value, ContextVar) for value in vars(context_module).values())


def test_planning_metadata_and_raw_views_expose_only_explicit_allowlist():
    store = Workspace()
    store.add("orders", pd.DataFrame({"order_id": [1], "amount": [10]}))
    store.set_metadata("orders", "schema", {"grain": "one row per order"})
    store.set_metadata("orders", "quality", {"missing": 0})
    store.set_metadata("orders", "context", "private planning context")
    store.set_metadata("orders", "secret", {"token": 9876})
    store.set_metadata("orders", "raw_notes", "do not disclose")

    with use_agent_context(AgentContext(session_id="s1", workspace=store)) as ctx:
        with ctx.planning_workspace_scope(["orders"]):
            metadata = workspace.get_metadata("orders")
            metadata_view = workspace._metadata
            datasets_view = workspace._datasets

    assert metadata == {
        "schema": {"grain": "one row per order"},
        "quality": {"missing": 0},
    }
    assert metadata_view == {"orders": metadata}
    assert datasets_view == {"orders": None}
    exposed = repr((metadata, metadata_view, datasets_view))
    assert "private planning context" not in exposed
    assert "9876" not in exposed
    assert "do not disclose" not in exposed


def test_planning_list_datasets_exposes_only_approved_summary_fields():
    store = Workspace()
    store.add("orders", pd.DataFrame({"order_id": [1], "amount": [10]}))
    store.set_metadata("orders", "quality", {"missing": 0})
    store.set_metadata("orders", "secret", {"token": 9876})
    store.set_metadata("orders", "context", "private planning notes")

    with use_agent_context(AgentContext(session_id="s1", workspace=store)) as ctx:
        with ctx.planning_workspace_scope(["orders"]):
            info = workspace.list_datasets()["orders"]

    assert set(info) == {"rows", "columns", "column_names", "derived_from"}
    assert "9876" not in repr(info)
    assert "private planning notes" not in repr(info)


def test_contextvar_scope_is_isolated_and_propagates_to_worker(tmp_path, monkeypatch):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, session_id="s1", datasets=["one"])
    _stage3c0b_task(manager, session_id="s2", datasets=["two"])
    _bind_manager(monkeypatch, manager)
    one = AgentContext(session_id="s1", workspace=Workspace())
    two = AgentContext(session_id="s2", workspace=Workspace())
    one.workspace.add("one", pd.DataFrame({"x": [1]}))
    one.workspace.add("two", pd.DataFrame({"x": [2]}))
    two.workspace.add("one", pd.DataFrame({"x": [1]}))
    two.workspace.add("two", pd.DataFrame({"x": [2]}))

    with use_agent_context(one):
        one.refresh_workspace_scope()
        copied = copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            worker_names = pool.submit(copied.run, lambda: set(workspace.list_datasets())).result()
    with use_agent_context(two):
        two.refresh_workspace_scope()
        main_names = set(workspace.list_datasets())

    assert worker_names == {"one"}
    assert main_names == {"two"}


def test_explicit_blank_project_name_does_not_fall_back_to_object_name():
    loop = AgentLoop(
        client=object(),
        session_id="s1",
        object_name="legacy-project",
        project_name="",
    )

    assert loop.context.project_name == ""


@pytest.mark.parametrize(
    ("session_data", "expected_project", "expected_workspace_action"),
    [
        ({"project_name": "", "object_name": "legacy-project"}, "", ("clear", None)),
        ({"object_name": "legacy-project"}, "legacy-project", ("set", "legacy-project")),
        (
            {"project_name": "  exact project  ", "object_name": "legacy-project"},
            "  exact project  ",
            ("set", "  exact project  "),
        ),
    ],
)
def test_restore_object_context_uses_project_key_presence_and_exact_identity(
    monkeypatch,
    session_data,
    expected_project,
    expected_workspace_action,
):
    import data_agent.agent.analysis_state as analysis_state_module
    import data_agent.session.history as history
    import data_agent.tools.knowledge_tools as knowledge_tools

    loop = AgentLoop(client=object(), session_id="s1", project_name="initial-project")
    workspace_actions = []
    active_objects = []
    monkeypatch.setattr(history, "load_session", lambda session_id: dict(session_data))
    monkeypatch.setattr(
        workspace,
        "set_project",
        lambda name: workspace_actions.append(("set", name)) or "ok",
    )
    monkeypatch.setattr(
        workspace,
        "clear_project",
        lambda: workspace_actions.append(("clear", None)) or "ok",
    )
    monkeypatch.setattr(knowledge_tools, "set_active_session", lambda session_id: None)
    monkeypatch.setattr(knowledge_tools, "set_active_object", active_objects.append)
    monkeypatch.setattr(
        analysis_state_module,
        "load_analysis_state",
        lambda session_id, project_name: SimpleNamespace(project_name=project_name),
    )

    loop.restore_object_context()

    assert loop.context.project_name == expected_project
    assert loop.context.analysis_state.project_name == expected_project
    assert workspace_actions == [expected_workspace_action]
    assert active_objects == [expected_project]


def test_copied_context_keeps_scope_snapshot_when_original_context_is_rebound():
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

    ctx = AgentContext(session_id="s1", workspace=Workspace())
    first = WorkspaceScopeSnapshot(
        phase="execution",
        allowed_datasets=frozenset({"one", "two"}),
    )
    second = WorkspaceScopeSnapshot(
        phase="synthesis",
        allowed_datasets=frozenset({"two"}),
    )

    with use_agent_context(ctx):
        with ctx.bind_workspace_scope(first):
            copied = copy_context()
            with ctx.bind_workspace_scope(second):
                assert ctx.workspace_scope == second
                assert copied.run(lambda: ctx.workspace_scope) == first


def test_workspace_module_does_not_expose_raw_storage_resolver():
    import data_agent.session.workspace as workspace_module

    assert not hasattr(workspace_module, "_resolve_internal_workspace")
    assert not any(
        "storage" in name and callable(getattr(workspace, name))
        for name in dir(workspace)
    )


def test_execution_save_meta_serializes_only_scope_approved_dataset_details(
    tmp_path,
    monkeypatch,
):
    import data_agent.session.history as history
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

    monkeypatch.setattr(history, "_session_dir", lambda session_id: tmp_path)
    store = Workspace()
    store.add("bound", pd.DataFrame({"visible_column": [1]}))
    store.add("secret", pd.DataFrame({"secret_column": [9876]}))
    store.set_metadata("secret", "_source_path", "secret/source.csv")
    store.set_metadata("secret", "context", "private context")
    snapshot = WorkspaceScopeSnapshot(
        phase="execution",
        allowed_datasets=frozenset({"bound"}),
    )

    with use_agent_context(AgentContext(session_id="s1", workspace=store)) as ctx:
        with ctx.bind_workspace_scope(snapshot):
            workspace.save_meta("s1")

    payload = json.loads((tmp_path / "workspace_meta.json").read_text(encoding="utf-8"))
    assert set(payload) == {"bound"}
    serialized = json.dumps(payload)
    assert "secret" not in serialized
    assert "secret_column" not in serialized
    assert "secret/source.csv" not in serialized
    assert "private context" not in serialized


def test_loop_profile_and_session_meta_use_scoped_facade(tmp_path, monkeypatch):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["bound"])
    _bind_manager(monkeypatch, manager)
    loop = AgentLoop(client=object(), session_id="s1")
    monkeypatch.setattr(loop, "_build_retrieval_query", lambda messages: "")
    loop.context.workspace.add("bound", pd.DataFrame({"visible": [1]}))
    loop.context.workspace.add("secret", pd.DataFrame({"hidden_column": [9876]}))

    with use_agent_context(loop.context):
        loop.context.refresh_workspace_scope()
        profile = loop._current_dataset_profile()
        meta = loop._build_session_meta()

    assert "bound" in profile and "visible" in profile
    assert "secret" not in profile and "hidden_column" not in profile
    assert set(meta["datasets"]) == {"bound"}


def test_prompt_cache_invalidates_on_scope_and_bundle_fingerprint(tmp_path, monkeypatch):
    from data_agent.agent.data_understanding import build_data_understanding_bundle

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    first = _stage3c0b_task(manager, datasets=["bound"])
    _bind_manager(monkeypatch, manager)
    loop = AgentLoop(client=object(), session_id="s1")
    first_bundle = build_data_understanding_bundle(
        datasets=[{
            "dataset": "bound",
            "dataset_contract_id": "contract_1",
            "grain": "one row",
            "rows": 1,
            "columns": [{"name": "value", "type": "number"}],
        }],
        quality_findings=[{"finding": "first"}],
        relationship_candidates=[],
    )
    second_bundle = build_data_understanding_bundle(
        datasets=[{
            "dataset": "bound",
            "dataset_contract_id": "contract_1",
            "grain": "one row",
            "rows": 1,
            "columns": [{"name": "value", "type": "number"}],
        }],
        quality_findings=[{"finding": "second"}],
        relationship_candidates=[],
    )
    loop.context.analysis_state.data_understanding_bundles = [first_bundle]
    builds: list[str] = []
    monkeypatch.setattr(loop, "_build_system_prompt", lambda: builds.append("build") or f"prompt-{len(builds)}")

    assert loop._get_system_prompt() == "prompt-1"
    assert loop._get_system_prompt() == "prompt-1"
    loop.context.analysis_state.data_understanding_bundles.append({"data_fingerprint": "sha256:not-valid"})
    assert loop._get_system_prompt() == "prompt-1"
    loop.context.analysis_state.data_understanding_bundles.append(second_bundle)
    assert loop._get_system_prompt() == "prompt-2"

    manager.update(first["id"], status="completed")
    second = manager.create(
        "synthesis",
        session_id="s1",
        plan_id=manager.get_active_plan_id("s1", ""),
        analysis_plan_id="analysis_plan_1",
        step_id="synthesis",
        combination_mode="synthesis",
    )
    manager.update(second["id"], status="in_progress")
    assert loop._get_system_prompt() == "prompt-3"
    assert len(builds) == 3


def test_single_parallel_and_streaming_unclassified_tools_cannot_bypass_scope(tmp_path, monkeypatch):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["bound"])
    _bind_manager(monkeypatch, manager)
    store = Workspace()
    store.add("bound", pd.DataFrame({"visible": [1]}))
    store.add("secret", pd.DataFrame({"token": [9876]}))
    loop = AgentLoop(client=object(), session_id="s1")
    loop.context.analysis_state = None
    loop.context.workspace = store
    for name in ("unknown_single", "unknown_parallel", "unknown_stream"):
        _install_unclassified_reader(monkeypatch, name)

    single = ToolCall(id="single", name="unknown_single", arguments={})
    loop._execute_single_tool(single, [single], 0)
    parallel = loop._execute_tools_parallel([
        ToolCall(id="parallel", name="unknown_parallel", arguments={})
    ])
    list(loop._process_tool_calls(
        Response(tool_calls=[ToolCall(id="stream", name="unknown_stream", arguments={})]),
        round_num=1,
    ))

    outputs = [loop.messages[-2]["content"], parallel[0][1], loop.messages[-1]["content"]]
    assert all("9876" not in output for output in outputs)
    assert all("None" in output for output in outputs)


def test_unclassified_tool_cannot_downgrade_scope_then_read_secret(tmp_path, monkeypatch):
    from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, project_name="project-one", datasets=["bound"])
    _bind_manager(monkeypatch, manager)
    store = Workspace()
    store.add("bound", pd.DataFrame({"visible": [1]}))
    store.add("secret", pd.DataFrame({"token": [9876]}))
    loop = AgentLoop(client=object(), session_id="s1", project_name="project-one")
    loop.context.analysis_state = None
    loop.context.workspace = store

    def privilege_downgrade_reader():
        ctx = get_current_context()
        workspace.clear_project()
        with ctx.bind_workspace_scope(WorkspaceScopeSnapshot()):
            return str(workspace.get("secret"))

    monkeypatch.setitem(
        registry._tools,
        "privilege_downgrade_reader",
        ToolDefinition(
            name="privilege_downgrade_reader",
            description="attempt a scope downgrade before reading",
            func=privilege_downgrade_reader,
            parameters={"type": "object", "properties": {}},
            capability=None,
        ),
    )

    call = ToolCall(id="downgrade", name="privilege_downgrade_reader", arguments={})
    loop._execute_single_tool(call, [call], 0)

    output = loop.messages[-1]["content"]
    assert "9876" not in output
    assert loop.context.workspace_scope.phase == "execution"
    assert loop.context.workspace.get("secret") is None


def test_synthesis_system_prompt_omits_dataset_names_and_schema(tmp_path, monkeypatch):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["secret_dataset"], mode="synthesis")
    _bind_manager(monkeypatch, manager)
    loop = AgentLoop(client=object(), session_id="s1")
    monkeypatch.setattr(loop, "_build_retrieval_query", lambda messages: "")
    loop.messages.append({"role": "user", "content": "summarize verified evidence"})
    loop.context.workspace.add("secret_dataset", pd.DataFrame({"secret_column": [9876]}))
    loop.context.analysis_state.dataset_contracts = [
        {"id": "contract_1", "dataset": "secret_dataset", "quality_status": "valid"}
    ]

    prompt = loop._get_system_prompt()

    assert "secret_dataset" not in prompt
    assert "secret_column" not in prompt


def test_error_scope_prompt_exposes_control_error_without_workspace_details(tmp_path, monkeypatch):
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    _stage3c0b_task(manager, datasets=["secret_dataset"], status="pending")
    _bind_manager(monkeypatch, manager)
    loop = AgentLoop(client=object(), session_id="s1")
    monkeypatch.setattr(loop, "_build_retrieval_query", lambda messages: "")
    loop.context.workspace.add("secret_dataset", pd.DataFrame({"secret_column": [9876]}))

    prompt = loop._get_system_prompt()

    assert "stage3c0b_current_task_missing" in prompt
    assert "secret_dataset" not in prompt
    assert "secret_column" not in prompt
