"""Explicit commit semantics for results returned by registered tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolOutcomeState(StrEnum):
    COMMITTED = "committed"
    COMMITTED_WITH_WARNING = "committed_with_warning"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkflowWarning:
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    state: ToolOutcomeState
    result: Any
    artifact_ids: tuple[str, ...] = ()
    warning: WorkflowWarning | None = None


_ARTIFACT_ID_KEYS = frozenset(
    {
        "artifact_id",
        "computation_id",
        "evidence_id",
        "chart_id",
        "report_id",
        "output_id",
    }
)


def _json_payload(result: Any) -> Any:
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    if isinstance(result, dict):
        return result
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data
    summary = getattr(result, "summary", None)
    if isinstance(summary, str):
        return _json_payload(summary)
    return result


def _artifact_ids(value: Any) -> tuple[str, ...]:
    found: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in _ARTIFACT_ID_KEYS and str(child or "").strip():
                    identity = str(child).strip()
                    if identity not in found:
                        found.append(identity)
                else:
                    visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return tuple(found)


def committed_tool_outcome(result: Any, post_scope: Any) -> ToolOutcome:
    """Preserve an executed result; scope refresh can only add a warning."""

    warning = None
    if getattr(post_scope, "phase", "") == "error":
        warning = WorkflowWarning(
            error_type=str(getattr(post_scope, "error_type", "") or "workflow_refresh_error"),
            message=str(getattr(post_scope, "message", "") or "Workflow state refresh failed."),
        )
    return ToolOutcome(
        state=(
            ToolOutcomeState.COMMITTED_WITH_WARNING
            if warning is not None
            else ToolOutcomeState.COMMITTED
        ),
        result=result,
        artifact_ids=_artifact_ids(_json_payload(result)),
        warning=warning,
    )


def render_committed_tool_content(content: str, outcome: ToolOutcome) -> str:
    """Attach a bounded warning without hiding or nesting the committed result."""

    if outcome.warning is None:
        return content
    diagnostic = {
        "state": outcome.state.value,
        "artifact_ids": list(outcome.artifact_ids),
        "workflow_warning": {
            "error_type": outcome.warning.error_type,
            "message": outcome.warning.message,
        },
    }
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict):
        payload["_tool_outcome"] = diagnostic
        return json.dumps(payload, ensure_ascii=False)
    return json.dumps(
        {"result": content, "_tool_outcome": diagnostic},
        ensure_ascii=False,
    )


def with_workflow_warning(
    outcome: ToolOutcome,
    *,
    error_type: str,
    message: str,
) -> ToolOutcome:
    """Return a committed outcome carrying a bounded infrastructure warning."""

    return ToolOutcome(
        state=ToolOutcomeState.COMMITTED_WITH_WARNING,
        result=outcome.result,
        artifact_ids=outcome.artifact_ids,
        warning=WorkflowWarning(error_type=error_type, message=message),
    )
