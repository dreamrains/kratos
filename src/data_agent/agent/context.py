"""Per-session agent context.

This module keeps mutable runtime state scoped to the active agent turn.  Tools
can continue to import the historical module-level facades, while those facades
resolve to the current context when one is active.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional


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
