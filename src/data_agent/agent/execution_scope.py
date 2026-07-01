"""Runtime dataset boundary for the current Stage 3C0B workflow task."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    "create_chart": frozenset({"name"}),
    "derive_features": frozenset({"name"}),
    "derive_field": frozenset({"name"}),
    "distribution_analysis": frozenset({"name"}),
    "export_data": frozenset({"name"}),
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


def _text_set(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    return {text for item in value if (text := _text(item))}


def _is_stage3c0b_task(task: dict[str, Any]) -> bool:
    return bool(_text(task.get("analysis_plan_id")) or _text(task.get("step_id")))


def current_execution_scope(manager, session_id: str, project_name: str = "") -> ExecutionScope:
    """Return the unique in-progress Stage 3C0B task scope for this session/project."""
    active_tasks = manager.list_active_for_scope(
        session_id=session_id,
        project_name=project_name,
    )
    in_progress = [
        task
        for task in active_tasks
        if task.get("status") == "in_progress" and _is_stage3c0b_task(task)
    ]
    if not in_progress:
        return ExecutionScope(active=False)
    if len(in_progress) > 1:
        return ExecutionScope(
            active=False,
            error_type="multiple_in_progress_tasks",
            message="Stage 3C0B allows only one in-progress task per session and project.",
        )

    task = in_progress[0]
    return ExecutionScope(
        active=True,
        task_id=int(task.get("id") or 0),
        step_id=_text(task.get("step_id")),
        combination_mode=_text(task.get("combination_mode")).casefold(),
        allowed_datasets=_text_set(task.get("dataset_inputs")),
        dataset_contract_ids=_text_set(task.get("dataset_contract_ids")),
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


def ensure_tool_allowed_for_current_task(
    registry,
    manager,
    session_id: str,
    project_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> ScopeGuardResult:
    """Validate every raw dataset referenced by a dataset-read tool call."""
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
