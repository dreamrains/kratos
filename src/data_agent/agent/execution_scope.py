"""Runtime dataset boundary for the current Stage 3C0B workflow task."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class ExecutionScope:
    active: bool
    task_id: int = 0
    step_id: str = ""
    combination_mode: str = ""
    allowed_datasets: set[str] = field(default_factory=set)
    dataset_contract_ids: set[str] = field(default_factory=set)
    error_type: str = ""
    message: str = ""


@dataclass(frozen=True)
class WorkspaceScopeSnapshot:
    """Immutable identity of the raw-data visibility boundary for one context."""

    phase: str = "legacy"
    session_id: str = ""
    project_name: str = ""
    plan_id: str = ""
    task_id: int = 0
    step_id: str = ""
    allowed_datasets: frozenset[str] = field(default_factory=frozenset)
    dataset_contract_ids: frozenset[str] = field(default_factory=frozenset)
    error_type: str = ""
    message: str = ""
    combination_mode: str = ""

    def __post_init__(self) -> None:
        if self.phase not in {"legacy", "planning", "execution", "synthesis", "error"}:
            raise ValueError(f"Unsupported workspace scope phase: {self.phase}")
        object.__setattr__(self, "session_id", _identity(self.session_id))
        object.__setattr__(self, "project_name", _identity(self.project_name))
        object.__setattr__(self, "plan_id", _identity(self.plan_id))
        object.__setattr__(self, "step_id", _text(self.step_id))
        object.__setattr__(self, "allowed_datasets", frozenset(_text_set(self.allowed_datasets)))
        object.__setattr__(self, "dataset_contract_ids", frozenset(_text_set(self.dataset_contract_ids)))
        object.__setattr__(self, "error_type", _text(self.error_type))
        object.__setattr__(self, "message", _text(self.message))
        object.__setattr__(self, "combination_mode", _text(self.combination_mode).casefold())

    @property
    def fingerprint(self) -> str:
        payload = {
            "phase": self.phase,
            "session_id": self.session_id,
            "project_name": self.project_name,
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "allowed_datasets": sorted(self.allowed_datasets),
            "dataset_contract_ids": sorted(self.dataset_contract_ids),
            "error_type": self.error_type,
            "message": self.message,
            "combination_mode": self.combination_mode,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def active(self) -> bool:
        return self.phase in {"execution", "synthesis"}


@dataclass(frozen=True)
class ScopeGuardResult:
    allowed: bool
    error_type: str = ""
    message: str = ""


_DATASET_ARGUMENT_NAMES = frozenset({
    "name",
    "dataset",
    "dataset_name",
    "left",
    "right",
    "left_name",
    "right_name",
    "left_dataset",
    "right_dataset",
    "datasets",
})

# Older native tools predate ToolCapability metadata. Keep their actual dataset
# inputs explicit so output names and unrelated ``name`` arguments are never
# mistaken for dataset reads.
_LEGACY_DATASET_ARGUMENTS: dict[str, frozenset[str]] = {
    "apply_type_conversion": frozenset({"name"}),
    "assess_readiness": frozenset({"name"}),
    "clean_data": frozenset({"name"}),
    "create_chart": frozenset({"data"}),
    "derive_features": frozenset({"name"}),
    "derive_field": frozenset({"name"}),
    "distribution_analysis": frozenset({"name"}),
    "export_data": frozenset({"name"}),
    "export_output": frozenset({"name"}),
    "interpret_dataset": frozenset({"name"}),
    "segmentation_analysis": frozenset({"name"}),
    "shap_analysis": frozenset({"name"}),
    "suggest_column_types": frozenset({"name"}),
    "transform_data": frozenset({"name", "other_name"}),
    "what_if_simulation": frozenset({"name"}),
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _identity(value: Any) -> str:
    """Preserve exact identity strings; only ``None`` denotes missing identity."""
    return "" if value is None else str(value)


def _text_set(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    return {text for item in value if (text := _text(item))}


def _is_stage3c0b_task(task: dict[str, Any]) -> bool:
    return bool(_text(task.get("analysis_plan_id")) or _text(task.get("step_id")))


def resolve_workspace_scope(manager, session_id: str, project_name: str = "") -> WorkspaceScopeSnapshot:
    """Resolve the exact active Stage 3C0B plan without wildcard scope semantics."""
    session = _identity(session_id)
    project = _identity(project_name)
    plan_id = _identity(manager.get_active_plan_id(session, project))
    if not plan_id:
        return WorkspaceScopeSnapshot(session_id=session, project_name=project)

    tasks = [
        task
        for task in manager.list_all(include_stale=True)
        if _identity(task.get("session_id")) == session
        and _identity(task.get("project_name")) == project
        and _identity(task.get("plan_id")) == plan_id
        and task.get("status") not in {"deleted", "archived", "superseded"}
    ]
    stage_tasks = [task for task in tasks if _is_stage3c0b_task(task)]
    if not stage_tasks and tasks:
        return WorkspaceScopeSnapshot(session_id=session, project_name=project)

    in_progress = [task for task in stage_tasks if task.get("status") == "in_progress"]
    if len(in_progress) != 1:
        error_type = (
            "multiple_in_progress_tasks"
            if len(in_progress) > 1
            else "stage3c0b_current_task_missing"
        )
        message = (
            "Stage 3C0B allows only one in-progress task per session and project."
            if len(in_progress) > 1
            else "The active Stage 3C0B plan has no unique in-progress task."
        )
        return WorkspaceScopeSnapshot(
            phase="error",
            session_id=session,
            project_name=project,
            plan_id=plan_id,
            error_type=error_type,
            message=message,
        )

    task = in_progress[0]
    mode = _text(task.get("combination_mode")).casefold()
    return WorkspaceScopeSnapshot(
        phase="synthesis" if mode == "synthesis" else "execution",
        session_id=session,
        project_name=project,
        plan_id=plan_id,
        task_id=int(task.get("id") or 0),
        step_id=_text(task.get("step_id")),
        allowed_datasets=frozenset(_text_set(task.get("dataset_inputs"))),
        dataset_contract_ids=frozenset(_text_set(task.get("dataset_contract_ids"))),
        combination_mode=mode,
    )


def planning_workspace_scope_snapshot(
    session_id: str,
    project_name: str = "",
    *,
    allowed_datasets: Any = (),
    plan_id: str = "",
) -> WorkspaceScopeSnapshot:
    """Create a schema/quality/preview-only scope for deterministic planning."""
    return WorkspaceScopeSnapshot(
        phase="planning",
        session_id=_identity(session_id),
        project_name=_identity(project_name),
        plan_id=_identity(plan_id),
        allowed_datasets=frozenset(_text_set(allowed_datasets)),
    )


def current_execution_scope(manager, session_id: str, project_name: str = "") -> ExecutionScope:
    """Return the unique in-progress Stage 3C0B task scope for this session/project."""
    snapshot = resolve_workspace_scope(manager, session_id, project_name)
    return ExecutionScope(
        active=snapshot.active,
        task_id=snapshot.task_id,
        step_id=snapshot.step_id,
        combination_mode=snapshot.combination_mode,
        allowed_datasets=set(snapshot.allowed_datasets),
        dataset_contract_ids=set(snapshot.dataset_contract_ids),
        error_type=snapshot.error_type,
        message=snapshot.message,
    )


def current_context_execution_scope() -> ExecutionScope:
    """Resolve execution scope from the context-local session and project."""
    from data_agent.agent.context import get_current_context

    context = get_current_context()
    if context is None:
        return ExecutionScope(active=False)

    from data_agent.session.task_manager import task_manager

    return current_execution_scope(
        task_manager,
        context.session_id,
        context.project_name or "",
    )


def ensure_dataset_allowed_in_current_context(dataset: str) -> ScopeGuardResult:
    """Guard a dataset read at a context-aware data-access boundary."""
    from data_agent.agent.context import get_current_context

    context = get_current_context()
    if context is None:
        return ScopeGuardResult(True)

    from data_agent.session.task_manager import task_manager

    return ensure_dataset_allowed_for_current_task(
        task_manager,
        context.session_id,
        context.project_name or "",
        dataset=dataset,
    )


def ensure_dataset_allowed_for_current_task(
    manager,
    session_id: str,
    project_name: str = "",
    *,
    dataset: str,
) -> ScopeGuardResult:
    """Check one raw dataset reference against the current execution scope."""
    scope = current_execution_scope(manager, session_id, project_name)
    if scope.error_type:
        return ScopeGuardResult(False, scope.error_type, scope.message)
    if not scope.active:
        return ScopeGuardResult(True)
    if scope.combination_mode == "synthesis":
        return ScopeGuardResult(
            False,
            "synthesis_cannot_read_raw_dataset",
            "Synthesis tasks consume verified evidence and cannot read raw datasets.",
        )

    normalized_dataset = _text(dataset)
    if normalized_dataset not in scope.allowed_datasets:
        return ScopeGuardResult(
            False,
            "dataset_outside_current_task_scope",
            f"Dataset '{normalized_dataset}' is outside the current task scope.",
        )
    return ScopeGuardResult(True)


def dataset_arguments_for_tool(registry, tool_name: str, arguments: dict[str, Any]) -> list[str]:
    """Extract dataset references only from metadata-classified dataset-read tools."""
    if tool_name == "export_output" and _text(arguments.get("output_type")).casefold() != "data":
        return []

    tool = registry.get(tool_name)
    capability = getattr(tool, "capability", None) if tool is not None else None
    capability_id = _text(getattr(capability, "capability_id", ""))
    explicit_arguments = _LEGACY_DATASET_ARGUMENTS.get(tool_name)
    if not explicit_arguments and not capability_id.startswith(("data.", "analysis.")):
        return []

    parameters = getattr(tool, "parameters", {}) or {}
    properties = parameters.get("properties") if isinstance(parameters, dict) else {}
    if not isinstance(properties, dict):
        return []

    datasets: list[str] = []
    dataset_argument_names = explicit_arguments or _DATASET_ARGUMENT_NAMES
    for argument_name in properties:
        if argument_name not in dataset_argument_names or argument_name not in arguments:
            continue
        value = arguments.get(argument_name)
        values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
        datasets.extend(text for item in values if (text := _text(item)))
    return datasets


def _prepare_create_chart_dataset(
    manager,
    session_id: str,
    project_name: str,
    arguments: dict[str, Any],
) -> ScopeGuardResult | None:
    """Replace create_chart's global auto-selection with a deterministic scoped dataset."""
    dataset = _text(arguments.get("data"))
    if not dataset and _text(arguments.get("data_json")):
        return None

    scope = current_execution_scope(manager, session_id, project_name)
    if scope.error_type:
        return ScopeGuardResult(False, scope.error_type, scope.message)
    if not scope.active:
        return None
    if scope.combination_mode == "synthesis":
        return ScopeGuardResult(
            False,
            "synthesis_cannot_read_raw_dataset",
            "Synthesis tasks consume verified evidence and cannot read raw datasets.",
        )

    if not dataset:
        if len(scope.allowed_datasets) != 1:
            return ScopeGuardResult(
                False,
                "dataset_scope_requires_unique_dataset",
                "create_chart requires one explicit dataset when the current task does not bind exactly one dataset.",
            )
        dataset = next(iter(scope.allowed_datasets))
        arguments["data"] = dataset

    if dataset in scope.allowed_datasets:
        from data_agent.session.workspace import workspace

        if dataset not in workspace.list_datasets():
            return ScopeGuardResult(
                False,
                "current_task_dataset_unavailable",
                f"Dataset '{dataset}' is bound to the current task but is not loaded.",
            )
    return None


def ensure_tool_allowed_for_current_task(
    registry,
    manager,
    session_id: str,
    project_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> ScopeGuardResult:
    """Validate every raw dataset referenced by a dataset-read tool call."""
    if tool_name == "create_chart":
        preparation_error = _prepare_create_chart_dataset(
            manager,
            session_id,
            project_name,
            arguments,
        )
        if preparation_error is not None:
            return preparation_error

    first_error: ScopeGuardResult | None = None
    for dataset in dataset_arguments_for_tool(registry, tool_name, arguments):
        result = ensure_dataset_allowed_for_current_task(
            manager,
            session_id,
            project_name,
            dataset=dataset,
        )
        if not result.allowed and first_error is None:
            first_error = result
    return first_error or ScopeGuardResult(True)


def _create_scope_enforcement_chain(
    normalize_text,
    normalize_identity,
    normalize_text_set,
    is_stage_task,
    snapshot_type,
    execution_type,
    guard_result_type,
    dataset_argument_names,
    legacy_dataset_arguments,
):
    """Capture every callable link used by authoritative scope enforcement."""

    def resolve_scope(manager, session_id: str, project_name: str = ""):
        session = normalize_identity(session_id)
        project = normalize_identity(project_name)
        plan_id = normalize_identity(manager.get_active_plan_id(session, project))
        if not plan_id:
            return snapshot_type(session_id=session, project_name=project)

        tasks = [
            task
            for task in manager.list_all(include_stale=True)
            if normalize_identity(task.get("session_id")) == session
            and normalize_identity(task.get("project_name")) == project
            and normalize_identity(task.get("plan_id")) == plan_id
            and task.get("status") not in {"deleted", "archived", "superseded"}
        ]
        stage_tasks = [task for task in tasks if is_stage_task(task)]
        if not stage_tasks and tasks:
            return snapshot_type(session_id=session, project_name=project)

        in_progress = [task for task in stage_tasks if task.get("status") == "in_progress"]
        if len(in_progress) != 1:
            multiple = len(in_progress) > 1
            return snapshot_type(
                phase="error",
                session_id=session,
                project_name=project,
                plan_id=plan_id,
                error_type=(
                    "multiple_in_progress_tasks"
                    if multiple
                    else "stage3c0b_current_task_missing"
                ),
                message=(
                    "Stage 3C0B allows only one in-progress task per session and project."
                    if multiple
                    else "The active Stage 3C0B plan has no unique in-progress task."
                ),
            )

        task = in_progress[0]
        mode = normalize_text(task.get("combination_mode")).casefold()
        return snapshot_type(
            phase="synthesis" if mode == "synthesis" else "execution",
            session_id=session,
            project_name=project,
            plan_id=plan_id,
            task_id=int(task.get("id") or 0),
            step_id=normalize_text(task.get("step_id")),
            allowed_datasets=frozenset(normalize_text_set(task.get("dataset_inputs"))),
            dataset_contract_ids=frozenset(
                normalize_text_set(task.get("dataset_contract_ids"))
            ),
            combination_mode=mode,
        )

    def current_scope(manager, session_id: str, project_name: str = ""):
        snapshot = resolve_scope(manager, session_id, project_name)
        return execution_type(
            active=snapshot.active,
            task_id=snapshot.task_id,
            step_id=snapshot.step_id,
            combination_mode=snapshot.combination_mode,
            allowed_datasets=set(snapshot.allowed_datasets),
            dataset_contract_ids=set(snapshot.dataset_contract_ids),
            error_type=snapshot.error_type,
            message=snapshot.message,
        )

    def ensure_dataset(manager, session_id: str, project_name: str = "", *, dataset: str):
        scope = current_scope(manager, session_id, project_name)
        if scope.error_type:
            return guard_result_type(False, scope.error_type, scope.message)
        if not scope.active:
            return guard_result_type(True)
        if scope.combination_mode == "synthesis":
            return guard_result_type(
                False,
                "synthesis_cannot_read_raw_dataset",
                "Synthesis tasks consume verified evidence and cannot read raw datasets.",
            )
        normalized_dataset = normalize_text(dataset)
        if normalized_dataset not in scope.allowed_datasets:
            return guard_result_type(
                False,
                "dataset_outside_current_task_scope",
                f"Dataset '{normalized_dataset}' is outside the current task scope.",
            )
        return guard_result_type(True)

    def dataset_arguments(registry, tool_name: str, arguments: dict[str, Any]):
        if (
            tool_name == "export_output"
            and normalize_text(arguments.get("output_type")).casefold() != "data"
        ):
            return []
        tool = registry.get(tool_name)
        capability = getattr(tool, "capability", None) if tool is not None else None
        capability_id = normalize_text(getattr(capability, "capability_id", ""))
        explicit_arguments = legacy_dataset_arguments.get(tool_name)
        if not explicit_arguments and not capability_id.startswith(("data.", "analysis.")):
            return []
        parameters = getattr(tool, "parameters", {}) or {}
        properties = parameters.get("properties") if isinstance(parameters, dict) else {}
        if not isinstance(properties, dict):
            return []
        datasets = []
        argument_names = explicit_arguments or dataset_argument_names
        for argument_name in properties:
            if argument_name not in argument_names or argument_name not in arguments:
                continue
            value = arguments.get(argument_name)
            values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
            datasets.extend(
                text for item in values if (text := normalize_text(item))
            )
        return datasets

    def prepare_chart(manager, session_id, project_name, arguments):
        dataset = normalize_text(arguments.get("data"))
        if not dataset and normalize_text(arguments.get("data_json")):
            return None
        scope = current_scope(manager, session_id, project_name)
        if scope.error_type:
            return guard_result_type(False, scope.error_type, scope.message)
        if not scope.active:
            return None
        if scope.combination_mode == "synthesis":
            return guard_result_type(
                False,
                "synthesis_cannot_read_raw_dataset",
                "Synthesis tasks consume verified evidence and cannot read raw datasets.",
            )
        if not dataset:
            if len(scope.allowed_datasets) != 1:
                return guard_result_type(
                    False,
                    "dataset_scope_requires_unique_dataset",
                    "create_chart requires one explicit dataset when the current task does not bind exactly one dataset.",
                )
            dataset = next(iter(scope.allowed_datasets))
            arguments["data"] = dataset
        if dataset in scope.allowed_datasets:
            from data_agent.session.workspace import workspace

            if dataset not in workspace.list_datasets():
                return guard_result_type(
                    False,
                    "current_task_dataset_unavailable",
                    f"Dataset '{dataset}' is bound to the current task but is not loaded.",
                )
        return None

    def ensure_tool(registry, manager, session_id, project_name, tool_name, arguments):
        if tool_name == "create_chart":
            preparation_error = prepare_chart(
                manager, session_id, project_name, arguments
            )
            if preparation_error is not None:
                return preparation_error
        first_error = None
        for dataset in dataset_arguments(registry, tool_name, arguments):
            result = ensure_dataset(
                manager, session_id, project_name, dataset=dataset
            )
            if not result.allowed and first_error is None:
                first_error = result
        return first_error or guard_result_type(True)

    return (
        resolve_scope,
        current_scope,
        ensure_dataset,
        dataset_arguments,
        prepare_chart,
        ensure_tool,
    )


(
    resolve_workspace_scope,
    current_execution_scope,
    ensure_dataset_allowed_for_current_task,
    dataset_arguments_for_tool,
    _prepare_create_chart_dataset,
    ensure_tool_allowed_for_current_task,
) = _create_scope_enforcement_chain(
    _text,
    _identity,
    _text_set,
    _is_stage3c0b_task,
    WorkspaceScopeSnapshot,
    ExecutionScope,
    ScopeGuardResult,
    _DATASET_ARGUMENT_NAMES,
    _LEGACY_DATASET_ARGUMENTS,
)
del _create_scope_enforcement_chain


# Capture the original resolver and snapshot type in context.py's closure-local
# registry during trusted module initialization.  Importing either module first
# completes this handshake before control returns to application or tool code.
import data_agent.agent.context as _context_module

_resolver_installer = getattr(
    _context_module,
    "_install_context_authoritative_resolver",
    None,
)
if _resolver_installer is not None:
    _resolver_installer(resolve_workspace_scope, WorkspaceScopeSnapshot)
    delattr(_context_module, "_install_context_authoritative_resolver")
del _resolver_installer, _context_module
