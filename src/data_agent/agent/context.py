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
import weakref


def _create_context_state_registry():
    """Keep raw ContextVars closure-local and expose only guarded operations."""

    class ScopeToken:
        __slots__ = ("__weakref__",)

    scope_vars = weakref.WeakKeyDictionary()
    preview_vars = weakref.WeakKeyDictionary()
    owners = weakref.WeakKeyDictionary()
    context_tokens = weakref.WeakKeyDictionary()
    workspace_tokens = weakref.WeakKeyDictionary()
    workspace_facades = weakref.WeakKeyDictionary()
    available_authorities = weakref.WeakKeyDictionary()
    claimed_authorities = weakref.WeakKeyDictionary()
    identity_ready_tokens = weakref.WeakSet()
    current_context = ContextVar("data_agent_current_context", default=None)

    class ResolverAuthority:
        pass

    def bind_owner(owner):
        token = ScopeToken()
        scope_vars[token] = ContextVar("data_agent_workspace_scope", default=None)
        preview_vars[token] = ContextVar("data_agent_planning_preview_rows", default=5)
        owners[token] = weakref.ref(owner)
        available_authorities[token] = ResolverAuthority()
        context_tokens[owner] = token

    def scope_token(owner):
        token = context_tokens.get(owner)
        if token is None:
            raise RuntimeError("Agent context scope binding is no longer available")
        return token

    def reject_escalation(message):
        raise PermissionError(f"workspace_scope_escalation: {message}")

    def validate_transition(current, target):
        from data_agent.agent.execution_scope import WorkspaceScopeSnapshot

        if not isinstance(target, WorkspaceScopeSnapshot):
            reject_escalation("scope bindings require an immutable snapshot")
        if current is None or current.phase == "legacy":
            return
        if target.phase == "legacy":
            reject_escalation("an active scoped phase cannot bind legacy access")

        identity_fields = ("session_id", "project_name", "plan_id", "task_id", "step_id")
        changed = [
            field_name
            for field_name in identity_fields
            if getattr(target, field_name) != getattr(current, field_name)
        ]
        if changed:
            reject_escalation(f"scope identity changed: {', '.join(changed)}")
        if not target.allowed_datasets.issubset(current.allowed_datasets):
            reject_escalation("allowed datasets expanded")
        if not target.dataset_contract_ids.issubset(current.dataset_contract_ids):
            reject_escalation("dataset contract identities expanded")

        access_rank = {
            "synthesis": 0,
            "error": 0,
            "planning": 1,
            "execution": 2,
        }
        if access_rank[target.phase] > access_rank[current.phase]:
            reject_escalation(f"unsafe phase transition: {current.phase} -> {target.phase}")

    def ensure_authoritative(owner, scope_var):
        current = scope_var.get()
        if current is None:
            current = resolve_authoritative(owner)
            scope_var.set(current)
        return current

    def operate_scope(owner, operation, *args):
        token = scope_token(owner)
        scope_var = scope_vars.get(token)
        preview_var = preview_vars.get(token)
        owner_ref = owners.get(token)
        registered_owner = owner_ref() if owner_ref is not None else None
        if scope_var is None or preview_var is None or registered_owner is not owner:
            raise RuntimeError("Agent context scope binding is no longer available")
        if operation == "identity_ready":
            return token in identity_ready_tokens
        if operation == "mark_identity_ready":
            identity_ready_tokens.add(token)
            return None
        if operation == "get":
            return scope_var.get()
        if operation == "ensure":
            return ensure_authoritative(owner, scope_var)
        if operation == "refresh":
            current = ensure_authoritative(owner, scope_var)
            snapshot = resolve_authoritative(owner)
            validate_transition(current, snapshot)
            scope_var.set(snapshot)
            return snapshot
        if operation == "refresh_authoritative":
            authority = claimed_authorities.get(token)
            if authority is None or not args or args[0] is not authority:
                raise PermissionError("workspace_scope_authority_required")
            snapshot = resolve_authoritative(owner)
            scope_var.set(snapshot)
            return snapshot
        if operation == "bind":
            snapshot = args[0]
            current = ensure_authoritative(owner, scope_var)
            validate_transition(current, snapshot)
            return scope_var.set(snapshot)
        if operation == "reset":
            scope_var.reset(args[0])
            return None
        if operation == "invalidate_legacy":
            current = scope_var.get()
            if current is not None and current.phase != "legacy":
                reject_escalation("only legacy scope can be invalidated after identity change")
            scope_var.set(None)
            return None
        if operation == "preview_get":
            return preview_var.get()
        if operation == "preview_bind":
            return preview_var.set(max(0, min(int(args[0]), 20)))
        if operation == "preview_reset":
            preview_var.reset(args[0])
            return None
        raise ValueError(f"Unsupported agent context scope operation: {operation}")

    def resolve_authoritative(owner):
        from data_agent.agent.execution_scope import resolve_workspace_scope
        from data_agent.session.task_manager import task_manager

        return resolve_workspace_scope(
            task_manager,
            owner.session_id,
            owner.project_name or "",
        )

    def claim_authoritative_controller(owner):
        token = scope_token(owner)
        authority = available_authorities.pop(token, None)
        if authority is None:
            raise RuntimeError("Authoritative workspace scope controller is unavailable")
        claimed_authorities[token] = authority

        def refresh_from_resolver():
            return operate_scope(owner, "refresh_authoritative", authority)

        return refresh_from_resolver

    def bind_workspace(owner, storage):
        from data_agent.session.workspace import WorkspaceProxy, _bind_workspace_store

        if workspace_tokens.get(owner) is not None and get_current() is owner:
            current = operate_scope(owner, "get")
            if current is None:
                current = operate_scope(owner, "ensure")
            if current.phase != "legacy":
                raise PermissionError(
                    "workspace_binding_mutation: cannot replace the active workspace "
                    f"while scope phase is {current.phase}"
                )
        workspace_tokens[owner] = _bind_workspace_store(owner, storage)
        workspace_facades[owner] = WorkspaceProxy(owner)

    def get_workspace(owner):
        facade = workspace_facades.get(owner)
        if facade is None:
            raise RuntimeError("Agent context workspace binding is no longer available")
        return facade

    def operate_workspace(owner, operation, *args):
        from data_agent.session.workspace import _workspace_operation

        token = workspace_tokens.get(owner)
        if token is None:
            raise RuntimeError("Agent context workspace binding is no longer available")
        return _workspace_operation(token, operation, *args)

    def is_workspace_token(owner, token):
        return workspace_tokens.get(owner) is token

    def has_scope(owner):
        return owner in context_tokens

    def get_current():
        return current_context.get()

    def bind_current(context):
        return current_context.set(context)

    def reset_current(token):
        current_context.reset(token)

    return (
        bind_owner,
        operate_scope,
        claim_authoritative_controller,
        bind_workspace,
        get_workspace,
        operate_workspace,
        is_workspace_token,
        has_scope,
        get_current,
        bind_current,
        reset_current,
    )


(
    _bind_context_scope,
    _context_scope_operation,
    _claim_authoritative_scope_controller,
    _bind_context_workspace,
    _get_context_workspace,
    _operate_context_workspace,
    _is_context_workspace_token,
    _context_has_scope,
    _get_current_context,
    _bind_current_context,
    _reset_current_context,
) = _create_context_state_registry()
del _create_context_state_registry


@dataclass(slots=True, weakref_slot=True, eq=False, init=False)
class AgentContext:
    session_id: str
    project_name: Optional[str] = None
    active_tool_groups: set[str] = field(default_factory=lambda: {"core"})
    executed_tools: set[str] = field(default_factory=set)
    loaded_skills: list[str] = field(default_factory=list)
    mcp_visible: bool = True
    analysis_state: object | None = None
    turn_state: object | None = None
    user_proficiency: str = "auto"  # "auto" | "beginner" | "intermediate" | "advanced"
    user_quality_requirements: str = ""  # Extracted user quality/format requirements
    turn_intent: object | None = None

    def __init__(
        self,
        session_id: str,
        project_name: Optional[str] = None,
        workspace: object | None = None,
        active_tool_groups: set[str] | None = None,
        executed_tools: set[str] | None = None,
        loaded_skills: list[str] | None = None,
        mcp_visible: bool = True,
        analysis_state: object | None = None,
        turn_state: object | None = None,
        user_proficiency: str = "auto",
        user_quality_requirements: str = "",
        turn_intent: object | None = None,
    ) -> None:
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "project_name", project_name)
        object.__setattr__(
            self,
            "active_tool_groups",
            {"core"} if active_tool_groups is None else active_tool_groups,
        )
        object.__setattr__(self, "executed_tools", set() if executed_tools is None else executed_tools)
        object.__setattr__(self, "loaded_skills", [] if loaded_skills is None else loaded_skills)
        object.__setattr__(self, "mcp_visible", mcp_visible)
        object.__setattr__(self, "analysis_state", analysis_state)
        object.__setattr__(self, "turn_state", turn_state)
        object.__setattr__(self, "turn_intent", turn_intent)
        object.__setattr__(self, "user_proficiency", user_proficiency)
        object.__setattr__(self, "user_quality_requirements", user_quality_requirements)
        _bind_context_scope(self)
        _context_scope_operation(self, "mark_identity_ready")
        _bind_context_workspace(self, workspace)

    def __setattr__(self, name, value) -> None:
        invalidate_legacy = False
        if (
            name in {"session_id", "project_name"}
            and _context_has_scope(self)
            and _context_scope_operation(self, "identity_ready")
        ):
            current_value = object.__getattribute__(self, name)
            if current_value != value:
                current_scope = _context_scope_operation(self, "get")
                if current_scope is None:
                    current_scope = _context_scope_operation(self, "ensure")
                if current_scope is not None and current_scope.phase != "legacy":
                    raise PermissionError(
                        f"workspace_identity_mutation: cannot change {name} "
                        f"while scope phase is {current_scope.phase}"
                    )
                invalidate_legacy = current_scope is not None
        object.__setattr__(self, name, value)
        if invalidate_legacy:
            _context_scope_operation(self, "invalidate_legacy")

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

    @property
    def workspace_scope(self):
        return _context_scope_operation(self, "get")

    @property
    def planning_preview_rows(self) -> int:
        return _context_scope_operation(self, "preview_get")

    def refresh_workspace_scope(self):
        """Atomically refresh this context's exact task-bound workspace scope."""
        return _context_scope_operation(self, "refresh")

    @contextmanager
    def bind_workspace_scope(self, snapshot):
        token = _context_scope_operation(self, "bind", snapshot)
        try:
            yield snapshot
        finally:
            _context_scope_operation(self, "reset", token)

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
        rows_token = _context_scope_operation(
            self,
            "preview_bind",
            preview_rows,
        )
        try:
            with self.bind_workspace_scope(snapshot):
                yield snapshot
        finally:
            _context_scope_operation(self, "preview_reset", rows_token)


def _get_scoped_workspace(ctx: AgentContext):
    return _get_context_workspace(ctx)


def _set_workspace_store(ctx: AgentContext, value: object | None) -> None:
    _bind_context_workspace(ctx, value)


# Keep the historical constructor/setter name while exposing only a scoped facade.
AgentContext.workspace = property(_get_scoped_workspace, _set_workspace_store)


def get_current_context() -> AgentContext | None:
    return _get_current_context()


def _ensure_context_workspace_scope(ctx: AgentContext):
    return _context_scope_operation(ctx, "ensure")


def set_current_context(ctx: AgentContext):
    return _bind_current_context(ctx)


def reset_current_context(token) -> None:
    _reset_current_context(token)


@contextmanager
def use_agent_context(ctx: AgentContext):
    token = _bind_current_context(ctx)
    try:
        yield ctx
    finally:
        _reset_current_context(token)
