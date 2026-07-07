"""Bounded, user-facing Workbench view model."""

from __future__ import annotations

from typing import Any

from data_agent.agent.workbench_view import build_workbench_view


def build_trust_view(state: Any, session_id: str | None = None) -> dict[str, Any]:
    """Return the current Workbench without legacy Trust Inspector projections."""
    workbench = build_workbench_view(state)
    if state is None:
        return _view(
            status="empty",
            session_id=session_id or "",
            updated_at="",
            workbench=workbench,
        )

    status = "ready" if _has_workbench_content(state, workbench) else "empty"
    return _view(
        status=status,
        session_id=session_id or _text(getattr(state, "session_id", "")),
        updated_at=_text(getattr(state, "updated_at", "")),
        workbench=workbench,
    )


def _view(
    *,
    status: str,
    session_id: str,
    updated_at: str,
    workbench: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "session_id": session_id,
        "updated_at": updated_at,
        "workbench": workbench,
    }


def _has_workbench_content(state: Any, workbench: dict[str, Any]) -> bool:
    if _text(getattr(state, "data_state", "")) == "data_loaded":
        return True
    primary = workbench["multifile_analysis"]
    understanding = primary["data_understanding"]
    coverage = primary["answer_coverage"]
    details = workbench["details"]
    return bool(
        understanding.get("datasets")
        or understanding.get("quality_findings")
        or primary.get("relationships")
        or primary.get("analysis_directions")
        or coverage.get("evidence_count")
        or details["scope"].get("files")
        or details["confirmation"].get("status") == "needs_confirmation"
        or details["verification"].get("status") != "not_run"
    )


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""
