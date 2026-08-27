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
    return bool(workbench.get("verified_conclusions"))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""
