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
    identities = weakref.WeakKeyDictionary()
    authoritative_managers = weakref.WeakKeyDictionary()
    available_authorities = weakref.WeakKeyDictionary()
    claimed_authorities = weakref.WeakKeyDictionary()
    identity_ready_tokens = weakref.WeakSet()
    current_context = ContextVar("data_agent_current_context", default=None)
    workspace_binding = None
    authoritative_resolver = None
    authoritative_scope_guard = None
    workspace_scope_snapshot_type = None

    class ResolverAuthority:
        pass

    class ManagerCapabilities:
        """Immutable, closure-private view of the manager operations we trust."""

        __slots__ = ("_get_active_plan_id", "_list_all")

        def __init__(self, manager):
            object.__setattr__(self, "_get_active_plan_id", manager.get_active_plan_id)
            object.__setattr__(self, "_list_all", manager.list_all)

        def __setattr__(self, name, value):
            raise AttributeError("Manager capabilities are immutable")

        def get_active_plan_id(self, *args, **kwargs):
            return self._get_active_plan_id(*args, **kwargs)

        def list_all(self, *args, **kwargs):
            return self._list_all(*args, **kwargs)

    def bind_owner(owner):
        from data_agent.session.task_manager import task_manager

        token = ScopeToken()
        scope_vars[token] = ContextVar("data_agent_workspace_scope", default=None)
        preview_vars[token] = ContextVar("data_agent_planning_preview_rows", default=5)
        owners[token] = weakref.ref(owner)
        available_authorities[token] = ResolverAuthority()
        authoritative_managers[token] = ManagerCapabilities(task_manager)
        context_tokens[owner] = token

    def operate_identity(owner, operation, *args):
        if operation == "initialize":
            if owner in identities:
                raise RuntimeError("Agent context identity is already initialized")
            identities[owner] = (args[0], args[1])
            return None
        identity = identities.get(owner)
        if identity is None:
            raise RuntimeError("Agent context identity binding is no longer available")
        if operation == "get":
            return identity[0] if args[0] == "session_id" else identity[1]
        if operation == "set":
            name, value = args
            index = 0 if name == "session_id" else 1
            current_value = identity[index]
            if current_value == value:
                return None
            invalidate_legacy = False
            if owner in context_tokens and operate_scope(owner, "identity_ready"):
                current_scope = operate_scope(owner, "get")
                if current_scope is None:
                    current_scope = operate_scope(owner, "ensure")
                if current_scope is not None and current_scope.phase != "legacy":
                    raise PermissionError(
                        f"workspace_identity_mutation: cannot change {name} "
                        f"while scope phase is {current_scope.phase}"
                    )
                invalidate_legacy = current_scope is not None
            updated = list(identity)
            updated[index] = value
            identities[owner] = tuple(updated)
            if invalidate_legacy:
                operate_scope(owner, "invalidate_legacy")
            return None
        raise ValueError(f"Unsupported agent context identity operation: {operation}")

    def scope_token(owner):
        token = context_tokens.get(owner)
        if token is None:
            raise RuntimeError("Agent context scope binding is no longer available")
        return token

    def reject_escalation(message):
        raise PermissionError(f"workspace_scope_escalation: {message}")

    def validate_transition(current, target):
        if (
            workspace_scope_snapshot_type is None
            or not isinstance(target, workspace_scope_snapshot_type)
        ):
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

    def validate_authoritative_transition(current, target):
        if current is None or current.phase == "legacy" or target.phase != "legacy":
            return target
        return workspace_scope_snapshot_type(
            phase="error",
            session_id=current.session_id,
            project_name=current.project_name,
            plan_id=current.plan_id,
            task_id=current.task_id,
            step_id=current.step_id,
            error_type="workspace_scope_authoritative_downgrade",
            message="The authoritative workspace scope disappeared during an active scoped session.",
        )

    def authoritative_refresh_error(owner, current):
        basis = current
        return workspace_scope_snapshot_type(
            phase="error",
            session_id=(basis.session_id if basis is not None else owner.session_id),
            project_name=(
                basis.project_name if basis is not None else (owner.project_name or "")
            ),
            plan_id=(basis.plan_id if basis is not None else ""),
            task_id=(basis.task_id if basis is not None else 0),
            step_id=(basis.step_id if basis is not None else ""),
            error_type="workspace_scope_guard_error",
            message="Workspace scope guard failed.",
        )

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
            current = scope_var.get()
            try:
                snapshot = validate_authoritative_transition(
                    current,
                    resolve_authoritative(owner),
                )
            except Exception:
                snapshot = authoritative_refresh_error(owner, current)
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
        if authoritative_resolver is None:
            raise RuntimeError("Authoritative workspace scope resolver is not initialized")
        manager = authoritative_managers.get(scope_token(owner))
        if manager is None:
            raise RuntimeError("Authoritative task manager binding is no longer available")
        return authoritative_resolver(
            manager,
            owner.session_id,
            owner.project_name or "",
        )

    def install_authoritative_resolver(resolver, snapshot_type, scope_guard):
        nonlocal authoritative_resolver
        nonlocal authoritative_scope_guard
        nonlocal workspace_scope_snapshot_type
        if (
            not callable(resolver)
            or not isinstance(snapshot_type, type)
            or not callable(scope_guard)
        ):
            raise TypeError("Invalid authoritative workspace scope resolver binding")
        binding = (resolver, snapshot_type, scope_guard)
        current = (
            authoritative_resolver,
            workspace_scope_snapshot_type,
            authoritative_scope_guard,
        )
        if authoritative_resolver is not None:
            if current != binding:
                raise RuntimeError(
                    "Authoritative workspace scope resolver is already initialized"
                )
            return None
        (
            authoritative_resolver,
            workspace_scope_snapshot_type,
            authoritative_scope_guard,
        ) = binding

    def claim_authoritative_controller(owner):
        token = scope_token(owner)
        authority = available_authorities.pop(token, None)
        if authority is None:
            raise RuntimeError("Authoritative workspace scope controller is unavailable")
        claimed_authorities[token] = authority

        def refresh_from_resolver():
            return operate_scope(owner, "refresh_authoritative", authority)

        def guard_tool(tool_registry, tool_name, arguments):
            if authoritative_scope_guard is None:
                raise RuntimeError("Authoritative workspace scope guard is not initialized")
            current = operate_scope(owner, "get")
            snapshot = (
                current
                if current is not None and current.phase == "error"
                else operate_scope(owner, "refresh_authoritative", authority)
            )
            visible_datasets = operate_workspace(owner, "list")
            return authoritative_scope_guard(
                tool_registry,
                snapshot,
                tool_name,
                arguments,
                frozenset(visible_datasets),
            )

        def record_worker_refresh_error(snapshot):
            if (
                workspace_scope_snapshot_type is None
                or not isinstance(snapshot, workspace_scope_snapshot_type)
                or snapshot.phase != "error"
            ):
                raise TypeError("Only an immutable authoritative error snapshot can be recorded")
            scope_var = scope_vars.get(token)
            if scope_var is None:
                raise RuntimeError("Agent context scope binding is no longer available")
            scope_var.set(snapshot)

        return refresh_from_resolver, guard_tool, record_worker_refresh_error

    def bind_workspace(owner, storage):
        if workspace_binding is None:
            raise RuntimeError("Context workspace dispatch is not initialized")
        if workspace_tokens.get(owner) is not None and get_current() is owner:
            current = operate_scope(owner, "get")
            if current is None:
                current = operate_scope(owner, "ensure")
            if current.phase != "legacy":
                raise PermissionError(
                    "workspace_binding_mutation: cannot replace the active workspace "
                    f"while scope phase is {current.phase}"
                )
        bind_store, create_facade, _dispatch = workspace_binding
        workspace_tokens[owner] = bind_store(owner, storage)
        workspace_facades[owner] = create_facade(owner)

    def get_workspace(owner):
        facade = workspace_facades.get(owner)
        if facade is None:
            raise RuntimeError("Agent context workspace binding is no longer available")
        return facade

    def operate_workspace(owner, operation, *args):
        if workspace_binding is None:
            raise RuntimeError("Context workspace dispatch is not initialized")
        token = workspace_tokens.get(owner)
        if token is None:
            raise RuntimeError("Agent context workspace binding is no longer available")
        return workspace_binding[2](token, operation, *args)

    def install_workspace_binding(bind_store, create_facade, dispatch):
        nonlocal workspace_binding
        binding = (bind_store, create_facade, dispatch)
        if workspace_binding is not None:
            if workspace_binding != binding:
                raise RuntimeError("Context workspace dispatch is already initialized")
            return None
        workspace_binding = binding

    def is_workspace_token(owner, token):
        return workspace_tokens.get(owner) is token

    def has_scope(owner):
        return owner in context_tokens

    def get_current():
        return current_context.get()

    def bind_current(context):
        current = current_context.get()
        if current is not None and context is not current:
            current_scope = operate_scope(current, "get")
            if current_scope is None:
                current_scope = operate_scope(current, "ensure")
            if current_scope.phase != "legacy":
                raise PermissionError(
                    "workspace_context_mutation: cannot replace the active "
                    f"agent context while scope phase is {current_scope.phase}"
                )
        return current_context.set(context)

    def reset_current(token):
        current_context.reset(token)

    return (
        bind_owner,
        operate_identity,
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
        install_workspace_binding,
        install_authoritative_resolver,
    )


(
    _bind_context_scope,
    _context_identity_operation,
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
    _install_context_workspace_binding,
    _install_context_authoritative_resolver,
) = _create_context_state_registry()
del _create_context_state_registry

# Trigger the execution-scope side of the trusted one-shot resolver handshake.
# This remains safe whether context.py or execution_scope.py is imported first.
import data_agent.agent.execution_scope as _execution_scope_bootstrap
del _execution_scope_bootstrap


@dataclass(slots=True, weakref_slot=True, eq=False, init=False)
class AgentContext:
    active_tool_groups: set[str] = field(default_factory=lambda: {"core"})
    executed_tools: set[str] = field(default_factory=set)
    loaded_skills: list[str] = field(default_factory=list)
    mcp_visible: bool = True
    analysis_state: object | None = None
    turn_state: object | None = None
    user_proficiency: str = "auto"  # "auto" | "beginner" | "intermediate" | "advanced"
    user_quality_requirements: str = ""  # Extracted user quality/format requirements
    turn_intent: object | None = None

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

def _create_agent_context_type(
    cls,
    identity_operation,
    bind_scope,
    scope_operation,
    bind_workspace,
    get_workspace,
):
    """Install enforcement methods whose trusted callables are closure-captured."""

    def initialize(
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
        identity_operation(self, "initialize", session_id, project_name)
        object.__setattr__(self, "active_tool_groups", {"core"} if active_tool_groups is None else active_tool_groups)
        object.__setattr__(self, "executed_tools", set() if executed_tools is None else executed_tools)
        object.__setattr__(self, "loaded_skills", [] if loaded_skills is None else loaded_skills)
        object.__setattr__(self, "mcp_visible", mcp_visible)
        object.__setattr__(self, "analysis_state", analysis_state)
        object.__setattr__(self, "turn_state", turn_state)
        object.__setattr__(self, "turn_intent", turn_intent)
        object.__setattr__(self, "user_proficiency", user_proficiency)
        object.__setattr__(self, "user_quality_requirements", user_quality_requirements)
        bind_scope(self)
        scope_operation(self, "mark_identity_ready")
        bind_workspace(self, workspace)

    def get_session_id(self):
        return identity_operation(self, "get", "session_id")

    def set_session_id(self, value):
        identity_operation(self, "set", "session_id", value)

    def get_project_name(self):
        return identity_operation(self, "get", "project_name")

    def set_project_name(self, value):
        identity_operation(self, "set", "project_name", value)

    def get_workspace_scope(self):
        return scope_operation(self, "get")

    def get_planning_preview_rows(self):
        return scope_operation(self, "preview_get")

    def refresh_workspace_scope(self):
        return scope_operation(self, "refresh")

    @contextmanager
    def bind_workspace_scope(self, snapshot):
        token = scope_operation(self, "bind", snapshot)
        try:
            yield snapshot
        finally:
            scope_operation(self, "reset", token)

    @contextmanager
    def planning_workspace_scope(self, datasets, *, preview_rows=5, plan_id=""):
        from data_agent.agent.execution_scope import planning_workspace_scope_snapshot

        snapshot = planning_workspace_scope_snapshot(
            get_session_id(self),
            get_project_name(self) or "",
            allowed_datasets=list(datasets),
            plan_id=plan_id,
        )
        rows_token = scope_operation(self, "preview_bind", preview_rows)
        try:
            with bind_workspace_scope(self, snapshot):
                yield snapshot
        finally:
            scope_operation(self, "preview_reset", rows_token)

    def reject_copy(self):
        raise TypeError("AgentContext instances cannot be copied or pickled")

    def reject_deepcopy(self, memo):
        raise TypeError("AgentContext instances cannot be copied or pickled")

    def reject_pickle(self, protocol):
        raise TypeError("AgentContext instances cannot be copied or pickled")

    initialize.__name__ = "__init__"
    initialize.__qualname__ = f"{cls.__qualname__}.__init__"

    cls.__init__ = initialize
    cls.session_id = property(get_session_id, set_session_id)
    cls.project_name = property(get_project_name, set_project_name)
    cls.workspace_scope = property(get_workspace_scope)
    cls.planning_preview_rows = property(get_planning_preview_rows)
    cls.refresh_workspace_scope = refresh_workspace_scope
    cls.bind_workspace_scope = bind_workspace_scope
    cls.planning_workspace_scope = planning_workspace_scope
    cls.workspace = property(get_workspace, bind_workspace)
    cls.__copy__ = reject_copy
    cls.__deepcopy__ = reject_deepcopy
    cls.__reduce_ex__ = reject_pickle
    return cls


AgentContext = _create_agent_context_type(
    AgentContext,
    _context_identity_operation,
    _bind_context_scope,
    _context_scope_operation,
    _bind_context_workspace,
    _get_context_workspace,
)
del _create_agent_context_type


def _create_context_scope_ensure(scope_operation):
    def ensure(ctx: AgentContext):
        return scope_operation(ctx, "ensure")

    return ensure


_ensure_context_workspace_scope = _create_context_scope_ensure(_context_scope_operation)
del _create_context_scope_ensure


def _create_current_context_facades(getter, binder, resetter):
    """Capture guarded registry operations so module namespace shadows are inert."""

    def get_current_context() -> AgentContext | None:
        return getter()

    def set_current_context(ctx: AgentContext):
        return binder(ctx)

    def reset_current_context(token) -> None:
        resetter(token)

    @contextmanager
    def use_agent_context(ctx: AgentContext):
        token = binder(ctx)
        try:
            yield ctx
        finally:
            resetter(token)

    return (
        get_current_context,
        set_current_context,
        reset_current_context,
        use_agent_context,
    )


(
    get_current_context,
    set_current_context,
    reset_current_context,
    use_agent_context,
) = _create_current_context_facades(
    _get_current_context,
    _bind_current_context,
    _reset_current_context,
)
del _create_current_context_facades

# Complete the circular dispatch handshake during trusted module initialization.
# Importing ``context`` directly therefore initializes and hides the one-shot
# workspace installer before callers can construct their first AgentContext.
import data_agent.session.workspace as _workspace_module
del _workspace_module
