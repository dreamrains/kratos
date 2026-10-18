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


# Same tools can inspect before planning; those receipts have no delivery authority.
EXPLORATION_TOOLS = frozenset({"load_data","reload_data","load_sql","list_data", "describe_dataset",
    "preview_data","quick_profile","detect_data_quality","assess_readiness","interpret_dataset","suggest_column_types"})


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



def _derived_visible(name):
    from data_agent.session.workspace import workspace
    return workspace.exists(name)









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

        active_stage_tasks = [
            task for task in stage_tasks
            if task.get("status") in {"pending", "blocked", "in_progress"}
        ]
        if stage_tasks and not active_stage_tasks:
            last = max(stage_tasks, key=lambda item: int(item.get("id") or 0))
            if all(task.get("status") in {"completed", "failed", "closed_by_publication"} for task in stage_tasks):
                shared_datasets = set.intersection(*(
                    normalize_text_set(task.get("dataset_inputs")) for task in stage_tasks
                ))
                shared_contracts = set.intersection(*(
                    normalize_text_set(task.get("dataset_contract_ids")) for task in stage_tasks
                ))
                return snapshot_type(
                    phase="synthesis", session_id=session, project_name=project,
                    plan_id=plan_id, task_id=int(last.get("id") or 0),
                    step_id=normalize_text(last.get("step_id")),
                    allowed_datasets=frozenset(shared_datasets),
                    dataset_contract_ids=frozenset(shared_contracts),
                    combination_mode=normalize_text(last.get("combination_mode")).casefold(),
                )
            return snapshot_type(session_id=session, project_name=project)

        in_progress = [
            task for task in active_stage_tasks if task.get("status") == "in_progress"
        ]
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
        if normalized_dataset not in scope.allowed_datasets and not _derived_visible(normalized_dataset):
            return guard_result_type(
                False,
                "dataset_outside_current_task_scope",
                f"Dataset '{normalized_dataset}' is outside the current task scope.",
            )
        return guard_result_type(True)

    def ensure_dataset_for_snapshot(scope, dataset: str):
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
        if normalized_dataset not in scope.allowed_datasets and not _derived_visible(normalized_dataset):
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
        if tool_name=="transform_data":
            from data_agent.tools.data_transform import _transform_sources
            try:return _transform_sources(arguments)
            except (ValueError,KeyError,TypeError):return []
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
            separator = (getattr(capability, "input_contract", {}) or {}).get("dataset_argument_separators", {}).get(argument_name)
            # A declared native wire format is not inferred from prose.
            values = (value.split(separator) if isinstance(value, str) and separator
                      else value if isinstance(value, (list, tuple, set, frozenset)) else [value])
            datasets.extend(
                text for item in values if (text := normalize_text(item))
            )
        return datasets

    def bind_chart_source(arguments):
        if arguments.get("data_json") and (arguments.get("data") or arguments.get("result_ref")):
            return guard_result_type(False, "chart_source_conflict", "data_json cannot be combined with data or result_ref")
        if arguments.get("result_ref"):
            from data_agent.tools.result_reference import load_chart_result_reference
            try:
                _, _, name = load_chart_result_reference(arguments["result_ref"], dataset=arguments.get("data", ""))
            except (ValueError, KeyError, OSError) as exc:
                return guard_result_type(False, "chart_result_source_invalid", str(exc))
            arguments["data"] = name
        return None

    def prepare_chart(manager, session_id, project_name, arguments):
        source_error = bind_chart_source(arguments)
        if source_error is not None:
            return source_error
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

    def prepare_chart_for_snapshot(scope, arguments):
        source_error = bind_chart_source(arguments)
        if source_error is not None:
            return source_error
        dataset = normalize_text(arguments.get("data"))
        if not dataset and normalize_text(arguments.get("data_json")):
            return None
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
            arguments["data"] = next(iter(scope.allowed_datasets))
        return None

    def ensure_tool_for_snapshot(
        registry,
        scope,
        tool_name,
        arguments,
        available_datasets=None,
    ):
        """Validate a tool call against one supplied immutable scope snapshot."""
        if tool_name == "create_chart":
            preparation_error = prepare_chart_for_snapshot(scope, arguments)
            if preparation_error is not None:
                return preparation_error
        first_error = None
        for dataset in dataset_arguments(registry, tool_name, arguments):
            result = ensure_dataset_for_snapshot(scope, dataset)
            if not result.allowed and first_error is None:
                first_error = result
        if first_error is not None:
            return first_error
        if tool_name == "create_chart":
            dataset = normalize_text(arguments.get("data"))
            tool = registry.get(tool_name)
            parameters = getattr(tool, "parameters", {}) or {}
            properties = parameters.get("properties") if isinstance(parameters, dict) else {}
            if (
                dataset
                and scope.active
                and (
                    (available_datasets is not None and dataset not in available_datasets)
                    or not isinstance(properties, dict)
                    or "data" not in properties
                )
            ):
                return guard_result_type(
                    False,
                    "current_task_dataset_unavailable",
                    f"Dataset '{dataset}' is bound to the current task but is not loaded.",
                )
        return guard_result_type(True)

    def ensure_tool(registry, manager, session_id, project_name, tool_name, arguments):
        scope = resolve_scope(manager, session_id, project_name)
        result = ensure_tool_for_snapshot(registry, scope, tool_name, arguments)
        if not result.allowed or tool_name != "create_chart":
            return result
        dataset = normalize_text(arguments.get("data"))
        if dataset in scope.allowed_datasets:
            from data_agent.session.workspace import workspace

            if dataset not in workspace.list_datasets():
                return guard_result_type(
                    False,
                    "current_task_dataset_unavailable",
                    f"Dataset '{dataset}' is bound to the current task but is not loaded.",
                )
        return result

    return (
        resolve_scope,
        current_scope,
        ensure_dataset,
        dataset_arguments,
        prepare_chart,
        ensure_tool,
        ensure_tool_for_snapshot,
    )


(
    resolve_workspace_scope,
    current_execution_scope,
    ensure_dataset_allowed_for_current_task,
    dataset_arguments_for_tool,
    _prepare_create_chart_dataset,
    ensure_tool_allowed_for_current_task,
    ensure_tool_allowed_for_scope,
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


# Capture the original resolver, snapshot type, and scope guard in context.py's
# closure-local registry during trusted module initialization. Importing either
# module first completes this handshake before control returns to tool code.
import data_agent.agent.context as _context_module

_resolver_installer = getattr(
    _context_module,
    "_install_context_authoritative_resolver",
    None,
)
if _resolver_installer is not None:
    _resolver_installer(
        resolve_workspace_scope,
        WorkspaceScopeSnapshot,
        ensure_tool_allowed_for_scope,
    )
    delattr(_context_module, "_install_context_authoritative_resolver")
del _resolver_installer, _context_module
