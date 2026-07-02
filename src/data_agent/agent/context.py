"""Per-session agent context.

This module keeps mutable runtime state scoped to the active agent turn.  Tools
can continue to import the historical module-level facades, while those facades
resolve to the current context when one is active.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class AgentContext:
    session_id: str
    project_name: Optional[str] = None
    workspace: object | None = None
    active_tool_groups: set[str] = field(default_factory=lambda: {"core"})
    executed_tools: set[str] = field(default_factory=set)
    loaded_skills: list[str] = field(default_factory=list)
    mcp_visible: bool = True
    analysis_state: object | None = None
    turn_state: object | None = None
    user_proficiency: str = "auto"  # "auto" | "beginner" | "intermediate" | "advanced"
    user_quality_requirements: str = ""  # Extracted user quality/format requirements
    workspace_scope: object | None = None
    planning_preview_rows: int = 5

    @property
    def object_name(self) -> Optional[str]:
        """Backward-compatible alias for legacy object terminology."""
        return self.project_name

    @object_name.setter
    def object_name(self, value: Optional[str]) -> None:
        self.project_name = value

    def reset_turn_state(self) -> None:
        """Reset per-turn tool routing state."""
        self.active_tool_groups = {"core"}
        self.executed_tools.clear()
        self.turn_state = None

    def refresh_workspace_scope(self):
        """Atomically refresh this context's exact task-bound workspace scope."""
        from data_agent.agent.execution_scope import resolve_workspace_scope
        from data_agent.session.task_manager import task_manager

        self.workspace_scope = resolve_workspace_scope(
            task_manager,
            self.session_id,
            self.project_name or "",
        )
        return self.workspace_scope

    @contextmanager
    def bind_workspace_scope(self, snapshot):
        previous = self.workspace_scope
        self.workspace_scope = snapshot
        try:
            yield snapshot
        finally:
            self.workspace_scope = previous

    @contextmanager
    def planning_workspace_scope(
        self,
        datasets: Iterable[str],
        *,
        preview_rows: int = 5,
        plan_id: str = "",
    ):
        """Bind a planning-only scope which never grants unrestricted frames."""
        from data_agent.agent.execution_scope import planning_workspace_scope_snapshot

        snapshot = planning_workspace_scope_snapshot(
            self.session_id,
            self.project_name or "",
            allowed_datasets=list(datasets),
            plan_id=plan_id,
        )
        previous_rows = self.planning_preview_rows
        self.planning_preview_rows = max(0, min(int(preview_rows), 20))
        try:
            with self.bind_workspace_scope(snapshot):
                yield snapshot
        finally:
            self.planning_preview_rows = previous_rows


_current_context: ContextVar[AgentContext | None] = ContextVar(
    "data_agent_current_context",
    default=None,
)


def get_current_context() -> AgentContext | None:
    return _current_context.get()


def set_current_context(ctx: AgentContext):
    return _current_context.set(ctx)


def reset_current_context(token) -> None:
    _current_context.reset(token)


@contextmanager
def use_agent_context(ctx: AgentContext):
    token = _current_context.set(ctx)
    try:
        yield ctx
    finally:
        _current_context.reset(token)
