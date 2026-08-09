from __future__ import annotations

import hashlib
import inspect
import json
import threading
import uuid
import weakref
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from data_agent.config import get_config
from data_agent.llm.client import LLMClient

from data_agent.skills.loader import SkillLoader
from data_agent.tools.registry import registry
from data_agent.utils.logging import get_logger
from data_agent.agent.compact import (
    CompactState,
    persist_large_output,
    micro_compact,
    compact_history,
    estimate_tokens,
)

from data_agent.tools._utils import persist_detail

TOOL_SUMMARY_THRESHOLD = 3000  # chars: auto-persist tool output exceeding this
from data_agent.agent.context import (
    AgentContext,
    _claim_authoritative_scope_controller,
    get_current_context,
    set_current_context,
    reset_current_context,
    use_agent_context,
)
from data_agent.agent.execution_control import (
    BudgetExceeded,
    ToolExecutionBudget,
    TurnExecutionState,
)
from data_agent.session.workspace import Workspace, workspace
from data_agent.agent.progress import build_analysis_progress
from data_agent.agent.tool_outcome import (
    committed_tool_outcome,
    render_committed_tool_content,
    with_workflow_warning,
)

logger = get_logger("loop")

_PROFILING_TOOLS = {
    "load_data",
    "list_data",
    "preview_data",
    "describe_dataset",
    "quick_profile",
    "detect_data_quality",
    "interpret_dataset",
}

_SUBSTANTIVE_TOOLS = {
    "record_analysis_spec",
    "record_analysis_plan",
    "record_evidence_record",
    "record_insight_record",
    "compare_periods",
    "analyze_time_series",
    "funnel_analysis",
    "correlation_analysis",
    "ab_test",
    "generate_report",
    "generate_analysis_brief",
    "generate_formal_report",
    "run_python",
}

# Tools that do not by themselves advance the analysis contract — only used to
# detect the "loaded/profiled but never planned or executed" pre-plan case.
_META_QUALITY_TOOLS = {
    "load_data",
    "list_data",
    "record_data_requirement",
    "record_insight_record",
    "task_create",
    "task_update",
    "task_list",
    "ask_user_question",
}

_ANALYSIS_QUALITY_GUARD_MESSAGE = (
    "<analysis_quality_guard>\n"
    "The user requested analysis, but this turn has only loaded or profiled data. "
    "Continue by creating or applying an AnalysisPlan, running relevant analysis steps, "
    "and recording evidence before giving the final answer.\n"
    "</analysis_quality_guard>"
)

_ANALYSIS_QUALITY_CONTINUATION_TEMPLATE = (
    "<analysis_quality_guard>\n"
    "Requirement-based completion evaluator: status={status}, reason={reason}.\n"
    "Missing requirements: {missing}.\n"
    "Allowed capability/fallback: {capability_hint}.\n"
    "Do ONE bounded round: you MUST call at least one listed structured analysis tool, "
    "using at most three distinct structured analysis tools in total. Do not return a "
    "final answer before that attempt; if the attempted tool fails, disclose that exact limitation. "
    "The server auto-projects eligible structured results; do not call task tools "
    "or record_evidence_record merely for bookkeeping. Do not strengthen the claim "
    "class. After this round, synthesize the final answer with explicit limitations "
    "even if a requirement remains unmet.\n"
    "</analysis_quality_guard>"
)

_COMPUTATION_REPAIR_REASON_CODES = {
    "computation_integrity_failure",
    "evidence_identity_not_found",
    "evidence_outside_current_plan",
    "missing_structured_measurement",
    "stale_dataset_evidence",
    "stale_plan_evidence",
    "unmet_block_claim_requirement",
    "unsupported_claim",
}

_MEASUREMENT_BOOKKEEPING_CODES = {
    "measurement_identity_missing",
    "measurement_marker_invalid",
    "measurement_not_found",
    "measurement_metric_mismatch",
    "measurement_claim_key_mismatch",
    "measurement_scope_mismatch",
    "measurement_dataset_version_mismatch",
    "measurement_ambiguous",
}

_SYNTHESIS_MEASUREMENT_REPAIR_CODES = {
    # ``verify_analysis_claims`` adds this generic companion to the actionable
    # missing-marker codes below.  Treating it as an independent hard blocker
    # accidentally skipped the one bounded synthesis-only repair.
    "evidence_check_failed",
    "measurement_identity_missing",
    "measurement_marker_invalid",
    # These failures describe a draft that did not faithfully copy a current
    # bounded-catalog measurement.  They are repairable by the same one-shot
    # synthesis rewrite: copy the exact alias label/value/marker, then let the
    # unchanged audit verify the revised claim.  They must not trigger another
    # computation round.
    "measurement_ambiguous",
    "measurement_metric_mismatch",
    "numeric_mismatch",
    "unit_mismatch",
}


def _capability_hint_for_unmet(decision, *, plan: dict[str, Any] | None = None) -> str:
    """Render a compact, requirement-aware capability hint for the guard.

    Looked up from the recoverable requirement ids in the decision; never
    invents a stronger capability than the supported claim class allows.
    """

    recoverable = list(getattr(decision, "recoverable_requirement_ids", ()) or ())
    if not recoverable:
        return "use the next planned analysis step or downgrade the claim"
    recoverable_set = {str(item) for item in recoverable}
    method_plan = plan.get("method_plan") if isinstance(plan, dict) else None
    structured_hints: list[str] = []
    known_tool_names = (
        "detect_data_quality",
        "distribution_analysis",
        "transform_data",
        "segmentation_analysis",
        "correlation_analysis",
        "factor_relationship_analysis",
        "regression_analysis",
        "compare_periods",
        "analyze_time_series",
        "top_n",
    )
    for step in method_plan if isinstance(method_plan, list) else []:
        if not isinstance(step, dict) or step.get("combination_mode") == "synthesis":
            continue
        requirement_ids = {
            str(item) for item in step.get("requirement_ids") or [] if str(item)
        }
        if not requirement_ids.intersection(recoverable_set):
            continue
        capability = str(step.get("required_capability") or "").strip()
        method = str(step.get("method") or "")
        tools = [name for name in known_tool_names if name in method]
        if capability:
            tools.extend(registry.tools_for_capability(capability))
        tools = list(dict.fromkeys(tools))
        if not tools:
            continue
        step_id = str(step.get("step_id") or "planned_step")
        structured_hints.append(
            f"{step_id}: use {', '.join(tools[:2])} ({capability or 'planned capability'})"
        )
        if len(structured_hints) >= 3:
            break
    if structured_hints:
        return "; ".join(structured_hints)

    head = recoverable[0]
    head_text = str(head)
    # The requirement id encodes the missing method input (e.g.
    # ``req_step_multivariable_method_attempted_multivariable_adjustment``);
    # surface the trailing segment so the model knows which structured
    # output to produce without re-stating the whole plan.
    tail = head_text.rsplit("_", 1)[-1] if "_" in head_text else head_text
    return f"produce the structured {tail} output for {head_text}"


# === LoopResult: Agent loop return types ===

@dataclass
class FinalResponse:
    """Agent completed its answer."""
    content: str


@dataclass
class SuspendedForConfirmation:
    """Agent paused at ask_user_question; awaiting user response."""
    suspension_id: str
    question: str
    options: list[dict]
    context: str
    snapshot: dict  # serialized messages
    confirmation_id: str = ""
    version: int = 1
    multi_select: bool = False
    allow_free_text: bool = True
    confirmation_type: str = ""
    blocking_reason: str = ""
    state_updates: str = ""
    related_task_id: int = 0
    related_spec_id: str = ""


LoopResult = FinalResponse | SuspendedForConfirmation


class SuspensionManager:
    """Persist and restore agent loop suspensions for Web API support."""

    def __init__(self, sessions_dir):
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, suspension: SuspendedForConfirmation) -> str:
        path = self._dir / f"suspension_{suspension.suspension_id}.json"
        path.write_text(json.dumps({
            "suspension_id": suspension.suspension_id,
            "confirmation_id": suspension.confirmation_id or suspension.suspension_id,
            "version": suspension.version,
            "question": suspension.question,
            "options": suspension.options,
            "context": suspension.context,
            "snapshot": suspension.snapshot,
            "multi_select": suspension.multi_select,
            "allow_free_text": suspension.allow_free_text,
            "confirmation_type": suspension.confirmation_type,
            "blocking_reason": suspension.blocking_reason,
            "state_updates": suspension.state_updates,
            "related_task_id": suspension.related_task_id,
            "related_spec_id": suspension.related_spec_id,
        }, default=str, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def load(self, suspension_id: str) -> SuspendedForConfirmation | None:
        path = self._dir / f"suspension_{suspension_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return SuspendedForConfirmation(
            suspension_id=data["suspension_id"],
            question=data["question"],
            options=data["options"],
            context=data["context"],
            snapshot=data["snapshot"],
            confirmation_id=data.get("confirmation_id", data["suspension_id"]),
            version=int(data.get("version") or 1),
            multi_select=bool(data.get("multi_select", False)),
            allow_free_text=bool(data.get("allow_free_text", True)),
            confirmation_type=data.get("confirmation_type", ""),
            blocking_reason=data.get("blocking_reason", ""),
            state_updates=data.get("state_updates", ""),
            related_task_id=int(data.get("related_task_id") or 0),
            related_spec_id=data.get("related_spec_id", ""),
        )

    def remove(self, suspension_id: str):
        path = self._dir / f"suspension_{suspension_id}.json"
        path.unlink(missing_ok=True)


class UserConfirmationRequired(Exception):
    """Raised by ask_user_question in non-CLI mode to trigger suspension."""
    def __init__(
        self,
        question: str,
        options: list[dict],
        context: str = "",
        multi_select: bool = False,
        confirmation_type: str = "",
        blocking_reason: str = "",
        state_updates: str = "",
        related_task_id: int = 0,
        related_spec_id: str = "",
    ):
        self.question = question
        self.options = options
        self.context = context
        self.multi_select = multi_select
        self.confirmation_type = confirmation_type
        self.blocking_reason = blocking_reason
        self.state_updates = state_updates
        self.related_task_id = related_task_id
        self.related_spec_id = related_spec_id
        super().__init__(question)


# Module-level interaction mode: "cli" (blocking) or "web" (suspension)
_interaction_mode: str = "cli"


def set_interaction_mode(mode: str):
    """Set interaction mode: 'cli' or 'web'."""
    global _interaction_mode
    _interaction_mode = mode


def get_interaction_mode() -> str:
    return _interaction_mode


def _estimate_tokens(messages: list[dict]) -> int:
    return estimate_tokens(messages)


def _microcompact(session_id: str, messages: list[dict]) -> None:
    """Module-level wrapper for micro_compact."""
    micro_compact(session_id, messages)


def _intent_to_budget_profile(intent_type: str) -> str:
    if intent_type in ("simple_response", "knowledge_qa", "analysis_consultation", "result_followup", "data_operation"):
        return "interactive"
    if intent_type in ("intent_negotiation", "data_requirement"):
        return "interactive"
    if intent_type == "comprehensive_report":
        return "deep"
    return "analysis"


def _token_budget_for_profile(profile: str, token_threshold: int) -> int:
    ratios = {"interactive": 0.3, "analysis": 0.7, "deep": 1.0}
    return int(token_threshold * ratios.get(profile, 0.7))


# 模块级 SkillLoader 实例（参考 s_full.py line 546: SKILLS = SkillLoader(SKILLS_DIR)）
_skill_loader: Optional[SkillLoader] = None

# 模块级 MCP 管理器实例
_mcp_manager = None
_mcp_bridge = None


def get_skill_loader() -> Optional[SkillLoader]:
    """供 skill_tools 等模块访问 SkillLoader。"""
    return _skill_loader


def get_mcp_manager():
    """供 mcp_tools 等模块访问 MCP 管理器。"""
    return _mcp_manager


def get_mcp_bridge():
    """供 repl 等模块访问 MCP 工具桥。"""
    return _mcp_bridge


def _create_loop_context_registry(
    current_context_getter,
    current_context_setter,
    context_binder,
    scope_controller_claimant,
):
    bindings = weakref.WeakKeyDictionary()

    def operate(loop, operation, *args):
        binding = bindings.get(loop)
        if operation == "get":
            if binding is None:
                raise RuntimeError("Agent loop context is not initialized")
            return binding[0]
        if operation == "refresh":
            if binding is None:
                raise RuntimeError("Agent loop context is not initialized")
            return binding[1]()
        if operation == "guard":
            if binding is None:
                raise RuntimeError("Agent loop context is not initialized")
            return binding[2](*args)
        if operation == "record_worker_refresh_error":
            if binding is None:
                raise RuntimeError("Agent loop context is not initialized")
            return binding[3](*args)
        if operation == "set":
            if binding is None:
                raise RuntimeError("Agent loop context is not initialized")
            return current_context_setter(binding[0])
        if operation == "use":
            if binding is None:
                raise RuntimeError("Agent loop context is not initialized")
            return context_binder(binding[0])
        if operation == "replace":
            replacement = args[0]
            if binding is not None:
                current = binding[0]
                if replacement is current:
                    return None
                if current_context_getter() is current:
                    scope = current.workspace_scope
                    if scope is None:
                        scope = current.refresh_workspace_scope()
                    if scope.phase != "legacy":
                        raise PermissionError(
                            "workspace_context_mutation: cannot replace the active "
                            f"agent context while scope phase is {scope.phase}"
                        )
            refresh, guard, record_worker_refresh_error = scope_controller_claimant(replacement)
            bindings[loop] = (replacement, refresh, guard, record_worker_refresh_error)
            return None
        raise ValueError(f"Unsupported agent loop context operation: {operation}")

    return operate


_loop_context_operation = _create_loop_context_registry(
    get_current_context,
    set_current_context,
    use_agent_context,
    _claim_authoritative_scope_controller,
)
del _create_loop_context_registry


def _create_loop_context_dispatch_descriptor(loop_context_operation):
    class LoopContextDispatch:
        __slots__ = ()

        def __get__(self, instance, owner=None):
            if instance is None:
                return loop_context_operation

            def dispatch(operation, *args):
                return loop_context_operation(instance, operation, *args)

            return dispatch

        def __set__(self, instance, value):
            raise AttributeError("Loop context dispatch is read-only")

    return LoopContextDispatch()


def _create_scope_guard_descriptor(loop_context_operation, tool_registry, json_dumps):
    def scope_guard(loop, tool_name, arguments):
        try:
            result = loop_context_operation(
                loop,
                "guard",
                tool_registry,
                tool_name,
                arguments,
            )
        except Exception:
            return json_dumps(
                {
                    "error": "Workspace scope guard failed.",
                    "error_type": "workspace_scope_guard_error",
                },
                ensure_ascii=False,
            )
        if result.allowed:
            return ""
        return json_dumps(
            {"error": result.message, "error_type": result.error_type},
            ensure_ascii=False,
        )

    class ScopeGuardDispatch:
        __slots__ = ()

        def __get__(self, instance, owner=None):
            if instance is None:
                return scope_guard

            def dispatch(tool_name, arguments):
                return scope_guard(instance, tool_name, arguments)

            return dispatch

        def __set__(self, instance, value):
            raise AttributeError("Scope guard dispatch is read-only")

    return scope_guard, ScopeGuardDispatch()


_protected_scope_guard, _scope_guard_dispatch = _create_scope_guard_descriptor(
    _loop_context_operation,
    registry,
    json.dumps,
)


def _redact_trust_dataset_names(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a prompt-safe projection while preserving opaque dataset identity."""

    redacted = dict(payload)
    datasets = payload.get("datasets")
    if isinstance(datasets, list):
        redacted["datasets"] = [
            {
                key: value
                for key, value in item.items()
                if key not in {"name", "dataset", "dataset_name"}
            }
            for item in datasets
            if isinstance(item, dict)
        ]
    return redacted


class AgentLoop:
    """Agent 主循环，管理对话、工具调度和上下文。"""

    __context_operation = _create_loop_context_dispatch_descriptor(_loop_context_operation)
    _current_task_scope_guard = _scope_guard_dispatch

    @property
    def context(self) -> AgentContext:
        return self.__context_operation("get")

    @context.setter
    def context(self, context: AgentContext) -> None:
        self.__context_operation("replace", context)

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        session_id: Optional[str] = None,
        object_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ):
        global _skill_loader, _mcp_manager, _mcp_bridge

        cfg = get_config()
        self.client = client or LLMClient()
        self.session_id = session_id or uuid.uuid4().hex[:12]
        active_project = project_name if project_name is not None else object_name
        self.context = AgentContext(
            session_id=self.session_id,
            project_name=active_project,
            workspace=Workspace(),
        )
        from data_agent.agent.analysis_state import load_analysis_state
        self.context.analysis_state = load_analysis_state(self.session_id, active_project)
        self.context.user_quality_requirements = (
            self.context.analysis_state.explicit_user_requirements
        )
        self.messages: list[dict] = []
        self.token_threshold = cfg.token_threshold
        self._last_data_file = ""
        self._prompt_cache: str = ""
        self._prompt_cache_dirty: bool = True
        self._prompt_cache_key: tuple[str, str, str] | None = None
        self._knowledge_retrieval_service = None
        self._interrupt_event = threading.Event()
        self._computation_ref_lock = threading.Lock()
        self._compact_state = CompactState()
        self._last_jsonl_idx: int = 0  # 上次 JSONL 推送的消息索引

        # 对象绑定
        if active_project:
            with self.__context_operation("use"):
                workspace.set_project(active_project)
                from data_agent.tools.knowledge_tools import set_active_object, set_active_session
                set_active_object(active_project)
                set_active_session(self.session_id)

        # 初始化 SkillLoader（支持全局 + 项目级目录）
        if _skill_loader is None:
            from data_agent.config_resolver import resolve_skills_dirs
            skills_dirs = resolve_skills_dirs()
            _skill_loader = SkillLoader(skills_dirs)
            if cfg.skill_auto_discover:
                _skill_loader.discover()
        self._skill_loader = _skill_loader

        # MCP 初始化延迟到首次 _loop() 调用时执行（_ensure_mcp_initialized）
        self._mcp_initialized = False

        # 注入 session_id 到 visualization/report/task_tools
        from data_agent.tools.visualization import set_chart_session
        set_chart_session(self.session_id)
        from data_agent.tools.task_tools import set_task_session
        set_task_session(self.session_id)

        # CLI pauser: set by repl.py to pause Live rendering during user input
        self.cli_pauser = None

    def invalidate_prompt_cache(self) -> None:
        """标记提示词缓存失效（数据集、技能等上下文变化时调用）。"""
        self._prompt_cache_dirty = True

    def restore_object_context(self) -> None:
        """恢复会话的对象绑定和知识上下文。

        从 meta.json 读取 object_name → 设置 workspace 和知识系统活跃对象。
        用于 /resume 恢复会话时重建完整上下文。
        """
        from data_agent.session.history import load_session
        from data_agent.session.workspace import workspace
        from data_agent.tools.knowledge_tools import set_active_object, set_active_session

        # 始终设置会话 ID
        set_active_session(self.session_id)

        data = load_session(self.session_id)
        if data is None:
            return

        has_project_name = "project_name" in data
        has_legacy_object_name = "object_name" in data
        obj_name = data["project_name"] if has_project_name else data.get("object_name")
        if has_project_name or has_legacy_object_name:
            with self.__context_operation("use"):
                if obj_name in (None, ""):
                    workspace.clear_project()
                else:
                    workspace.set_project(obj_name)
            self.context.project_name = obj_name
            set_active_object(obj_name)

            # Reload analysis_state to match restored project
            from data_agent.agent.analysis_state import load_analysis_state
            self.context.analysis_state = load_analysis_state(self.session_id, obj_name)
            self.context.analysis_state.project_name = obj_name

            logger.info("Object context restored", extra={"extra_data": {"object": obj_name}})

        self._prompt_cache_dirty = True

    def _restore_workspace(self) -> None:
        """Restore datasets while the loop-owned context is authoritative."""
        with self.__context_operation("use"):
            self._restore_workspace_in_context()

    def _restore_workspace_in_context(self) -> None:
        """Restore workspace datasets from persisted metadata.

        Strategy A: reload from original file path.
        Strategy B: fall back to parquet backup in session directory.
        """
        from data_agent.session.history import _session_dir

        workspace = self.context.workspace

        sdir = _session_dir(self.session_id)
        meta_path = sdir / "workspace_meta.json"
        if not meta_path.exists():
            return

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        if not meta:
            return

        restored = 0
        for name, info in meta.items():
            raw_df = None
            source_df = None
            persisted_raw = None
            active_backup = None
            migrated_from_legacy_backup = False
            source_changed_since_save = False
            raw_matches_saved = False

            def _read_backup(stem: str):
                parquet_path = sdir / "data" / f"{stem}.parquet"
                if parquet_path.exists():
                    try:
                        return pd.read_parquet(parquet_path)
                    except Exception:
                        pass
                pickle_path = sdir / "data" / f"{stem}.pkl"
                if pickle_path.exists():
                    try:
                        return pd.read_pickle(pickle_path)
                    except Exception:
                        pass
                return None

            # Strategy A: try original file path
            source_path = info.get("source_path", "")
            if source_path:
                from pathlib import Path as _Path
                sp = _Path(source_path)
                if sp.exists():
                    try:
                        fmt = info.get("source_fmt", "")
                        if fmt == "csv":
                            try:
                                source_df = pd.read_csv(sp, encoding="utf-8-sig")
                            except UnicodeDecodeError:
                                source_df = pd.read_csv(sp, encoding="gbk")
                        elif fmt == "excel":
                            source_df = pd.read_excel(sp)
                        elif fmt == "json":
                            source_df = pd.read_json(sp)
                    except Exception:
                        source_df = None

            # Always inspect the separately persisted immutable raw snapshot;
            # it is authoritative when the original source has drifted.
            persisted_raw = _read_backup(f"{name}__raw")

            # The active backup may contain confirmed material cleaning.  A
            # legacy session has only this file, so migrate it once as raw.
            active_backup = _read_backup(name)

            from data_agent.agent.data_lineage import frame_fingerprint

            saved_source_fingerprint = str(info.get("source_fingerprint") or "")
            source_fingerprint = (
                frame_fingerprint(source_df) if source_df is not None else ""
            )
            persisted_fingerprint = (
                frame_fingerprint(persisted_raw)
                if persisted_raw is not None
                else ""
            )
            if saved_source_fingerprint:
                if source_df is not None and source_fingerprint == saved_source_fingerprint:
                    raw_df = source_df
                    raw_matches_saved = True
                elif (
                    persisted_raw is not None
                    and persisted_fingerprint == saved_source_fingerprint
                ):
                    raw_df = persisted_raw
                    raw_matches_saved = True
                elif source_df is not None:
                    raw_df = source_df
                elif persisted_raw is not None:
                    raw_df = persisted_raw

                source_changed_since_save = bool(
                    (
                        source_df is not None
                        and source_fingerprint != saved_source_fingerprint
                    )
                    or (
                        source_df is None
                        and persisted_raw is not None
                        and persisted_fingerprint != saved_source_fingerprint
                    )
                )
            else:
                raw_df = source_df if source_df is not None else persisted_raw

            if raw_df is None and active_backup is not None:
                raw_df = active_backup.copy(deep=True)
                migrated_from_legacy_backup = True

            if raw_df is not None:
                from data_agent.tools.data_clean import prepare_analysis_copy

                source_fingerprint = frame_fingerprint(raw_df)
                raw_info = workspace.register_raw_snapshot(
                    name, raw_df, source_fingerprint
                )
                if not isinstance(raw_info, dict):
                    continue
                prepared, record, _, _ = prepare_analysis_copy(
                    raw_df,
                    logical_name=name,
                    raw_dataset_id=raw_info["dataset_id"],
                    source_fingerprint=source_fingerprint,
                )

                saved_versions = info.get("versions") or []
                saved_active = next(
                    (
                        item
                        for item in saved_versions
                        if item.get("dataset_id") == info.get("active_dataset_id")
                    ),
                    {},
                )
                active_matches_saved = False
                if active_backup is not None and saved_active and raw_matches_saved:
                    saved_fingerprint = saved_active.get("frame_fingerprint", "")
                    active_matches_saved = (
                        saved_fingerprint == frame_fingerprint(active_backup)
                    )

                active_info = None
                if active_matches_saved:
                    try:
                        active_info = workspace.restore_analysis_version(
                            name,
                            active_backup,
                            raw_info["dataset_id"],
                            saved_active,
                        )
                    except (KeyError, TypeError, ValueError, RuntimeError):
                        active_info = None
                if not isinstance(active_info, dict):
                    active_info = workspace.promote_analysis_copy(
                        name,
                        prepared,
                        raw_info["dataset_id"],
                        record,
                    )
                if not isinstance(active_info, dict):
                    continue
                if info.get("context"):
                    workspace.set_metadata(name, "context", info["context"])
                workspace.set_metadata(name, "_source_path", source_path)
                workspace.set_metadata(name, "_source_fmt", info.get("source_fmt", ""))
                if migrated_from_legacy_backup:
                    workspace.set_metadata(
                        name, "migrated_from_legacy_backup", True
                    )
                if source_changed_since_save:
                    workspace.set_metadata(
                        name, "source_changed_since_save", True
                    )
                restored += 1

        if restored:
            logger.info("Workspace restored", extra={"extra_data": {
                "session_id": self.session_id, "datasets_restored": restored
            }})
            self._prompt_cache_dirty = True

    def _ensure_mcp_initialized(self) -> None:
        """惰性初始化 MCP 连接。延迟到首次 _loop() 调用。"""
        global _mcp_manager, _mcp_bridge
        if self._mcp_initialized:
            return
        self._mcp_initialized = True

        cfg = get_config()
        if not cfg.mcp_enabled:
            return

        try:
            from data_agent.config_resolver import resolve_mcp_config
            from data_agent.mcp.client import MCPClientManager
            from data_agent.mcp.bridge import MCPToolBridge

            mcp_config = resolve_mcp_config()
            if mcp_config.servers:
                _mcp_manager = MCPClientManager(mcp_config)
                _mcp_bridge = MCPToolBridge(_mcp_manager, registry)
                _mcp_manager.start()
                registered = _mcp_bridge.register_all()
                logger.info("MCP tools registered", extra={"extra_data": {"tools": registered}})
        except Exception as e:
            logger.warning("MCP initialization failed", extra={"extra_data": {"error": str(e)}})
            _mcp_manager = None
            _mcp_bridge = None

    def request_interrupt(self) -> None:
        """请求中断当前正在执行的 turn。"""
        self._interrupt_event.set()

    def clear_interrupt(self) -> None:
        """清除中断信号（新 turn 开始时调用）。"""
        self._interrupt_event.clear()

    def _build_retrieval_query(self, messages: list[dict]) -> str:
        for message in reversed(messages[-6:]):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    return content[:500]
        return ""

    def _get_knowledge_retrieval_service(self):
        if self._knowledge_retrieval_service is None:
            from data_agent.knowledge.retrieval import KnowledgeRetrievalService

            self._knowledge_retrieval_service = KnowledgeRetrievalService()
        return self._knowledge_retrieval_service

    def _infer_retrieval_domain(self, user_input: str) -> str:
        text = f"{self.context.project_name or ''} {user_input}".lower()
        mappings = {
            "ecommerce": ("电商", "gmv", "订单", "退款", "转化"),
            "game": ("游戏", "留存", "付费率", "arpu", "dau"),
            "finance": ("金融", "授信", "逾期", "资产", "风控"),
        }
        for domain, markers in mappings.items():
            if any(marker in text for marker in markers):
                return domain
        return ""

    def _build_system_prompt(self) -> str:
        from data_agent.agent.prompts import build_system_prompt, _classify_task, detect_user_proficiency
        from data_agent.session.workspace import workspace
        from data_agent.tools.knowledge_tools import get_knowledge_instances

        tool_list = ", ".join(registry.tool_names)
        sid = self.session_id

        # 提取最近用户输入用于任务级别推断
        user_input = ""
        for msg in reversed(self.messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                user_input = content if isinstance(content, str) else str(content)
                break

        # Detect user proficiency level
        proficiency = self.context.user_proficiency
        if proficiency == "auto":
            proficiency = detect_user_proficiency(user_input, self.messages)
            self.context.user_proficiency = proficiency

        # 判断任务级别
        datasets = workspace.list_datasets()
        context_parts = []
        if datasets:
            for name, info in datasets.items():
                context_parts.append(
                    f"- {name}: {info['rows']} rows x {info['columns']} cols, "
                    f"columns: {', '.join(str(c) for c in info['column_names'][:10])}"
                )
        session_ctx = "\n".join(context_parts) if context_parts else ""

        # Structured data features: programmatic field classification for prompt
        if datasets:
            feature_lines = ["<data_features>"]
            for ds_name, ds_info in datasets.items():
                df = workspace.get(ds_name)
                if df is not None:
                    try:
                        from data_agent.tools.data_understand import _classify_columns
                        classified = _classify_columns(df)
                        has_time = bool(classified.get("time_columns"))
                        has_dims = bool(classified.get("dimensions"))
                        metrics = [m["column"] for m in classified.get("key_metrics", [])]
                        dims = [d["column"] for d in classified.get("dimensions", [])]
                        rates = [r["column"] for r in classified.get("rate_metrics", [])]

                        feature_lines.append(f"  {ds_name}:")
                        feature_lines.append(f"    has_time_columns: {has_time}")
                        feature_lines.append(f"    has_dimensions: {has_dims}")
                        feature_lines.append(f"    available_metrics: {metrics + rates}")
                        if dims:
                            feature_lines.append(f"    available_dimensions: {dims}")
                        else:
                            feature_lines.append(f"    available_dimensions: [] (无分组维度)")
                    except Exception:
                        pass
            feature_lines.append("</data_features>")
            session_ctx = (session_ctx + "\n" if session_ctx else "") + "\n".join(feature_lines)

        try:
            from data_agent.agent.analysis_state import (
                analysis_state_summary,
                build_trust_capsule,
                render_trust_capsule,
            )
            scope = self.context.workspace_scope or self.__context_operation("refresh")
            if scope.phase in {"synthesis", "error"}:
                state = self.context.analysis_state
                analysis_ctx = "\n".join([
                    f"- session_id: {getattr(state, 'session_id', self.session_id)}",
                    f"- evidence_records: {len(getattr(state, 'evidence_records', []) or [])}",
                    f"- verification_reports: {len(getattr(state, 'verification_reports', []) or [])}",
                    f"- pending_confirmations: {len(getattr(state, 'pending_confirmations', []) or [])}",
                ])
            else:
                analysis_ctx = analysis_state_summary(self.context.analysis_state)
            if analysis_ctx:
                session_ctx = (session_ctx + "\n\n" if session_ctx else "") + "<analysis_state>\n" + analysis_ctx + "\n</analysis_state>"
            capsule = build_trust_capsule(
                self.context.analysis_state,
                user_requirements=self.context.user_quality_requirements,
                active_confirmation=self._active_confirmation_identity(),
                active_datasets=self._active_dataset_capsule_inputs(),
            )
            redact_dataset_names = scope.phase in {"synthesis", "error"}
            prompt_capsule = (
                _redact_trust_dataset_names(capsule)
                if redact_dataset_names
                else capsule
            )
            capsule_json = render_trust_capsule(prompt_capsule)
            self._turn_trust_capsule = capsule
            self._turn_trust_capsule_text = capsule_json
            hydrated_trust_context = self._hydrate_overflow_trust_context(
                capsule,
                redact_dataset_names=redact_dataset_names,
            )
            self._turn_hydrated_trust_context_text = hydrated_trust_context
            session_context_without_capsule = session_ctx
            session_ctx = (
                (session_ctx + "\n\n" if session_ctx else "")
                + f'<trust_capsule digest="{capsule["digest"]}">\n'
                + capsule_json
                + "\n</trust_capsule>"
            )
            if hydrated_trust_context:
                session_ctx += (
                    "\n\n<hydrated_trust_context>\n"
                    + hydrated_trust_context
                    + "\n</hydrated_trust_context>"
                )
        except Exception:
            self._turn_trust_capsule = {}
            self._turn_trust_capsule_text = ""
            self._turn_hydrated_trust_context_text = ""
            session_context_without_capsule = session_ctx

        level = _classify_task(user_input, session_ctx) if user_input else "standard"

        # Chat 模式：不传工具列表
        if level == "chat":
            tool_list = ""

        project_rules, _, _ = get_knowledge_instances()
        rules_prompt = project_rules.get_rules_for_prompt(session_id=sid)
        retrieved_context = ""
        retrieval_query = self._build_retrieval_query(self.messages)
        if retrieval_query:
            try:
                service = self._get_knowledge_retrieval_service()
                context = service.retrieve(
                    retrieval_query,
                    domain=self._infer_retrieval_domain(user_input),
                    project_id=self.context.project_name or "",
                    include_evidence=False,
                )
                retrieved_context = service.compose_prompt_context(context)
            except Exception as exc:
                logger.warning(
                    "Knowledge retrieval failed",
                    extra={"extra_data": {"session_id": sid, "error": str(exc)}},
                )

        # Chat 模式：跳过技能信息
        skill_descriptions = ""
        skill_instructions = ""
        if level != "chat" and self._skill_loader and self._skill_loader.list_loaded():
            loaded = self._skill_loader.list_loaded()
            skill_descriptions = "\n已加载技能:\n" + "\n".join(
                f"  - {s.name}: {s.description}" for s in loaded
            )
            skill_instructions = self._skill_loader.get_prompt_injections()

        self._prompt_component_payloads = {
            "tool_list": tool_list,
            "project_rules": rules_prompt,
            "retrieved_context": retrieved_context if level != "chat" else "",
            "session_context": session_context_without_capsule,
            "skill_descriptions": skill_descriptions if level != "chat" else "",
            "skill_instructions": skill_instructions if level != "chat" else "",
            "user_input": user_input,
            "user_requirements": self.context.user_quality_requirements,
            "trust_capsule": getattr(self, "_turn_trust_capsule_text", ""),
            "hydrated_trust_context": getattr(
                self, "_turn_hydrated_trust_context_text", ""
            ),
        }

        # Chat 模式：只注入 rules（业务约束），跳过 domain/experience
        if level == "chat":
            return build_system_prompt(
                tool_list=tool_list,
                project_rules=rules_prompt,
                domain_knowledge="",
                experience_log="",
                session_context=session_ctx,
                skill_instructions="",
                skill_descriptions="",
                user_input=user_input,
                proficiency=proficiency,
                user_requirements=self.context.user_quality_requirements,
            )

        return build_system_prompt(
            tool_list=tool_list,
            project_rules=rules_prompt,
            domain_knowledge=retrieved_context,
            experience_log="",
            session_context=session_ctx,
            skill_instructions=skill_instructions,
            skill_descriptions=skill_descriptions,
            user_input=user_input,
            proficiency=proficiency,
            user_requirements=self.context.user_quality_requirements,
        )

    def _get_system_prompt(self) -> str:
        """获取系统提示词（带缓存）。"""
        with self.__context_operation("use"):
            scope = self.__context_operation("refresh")
            bundle_fingerprint = ""
            state = getattr(self.context, "analysis_state", None)
            from data_agent.agent.data_understanding import validate_data_understanding_bundle

            for bundle in reversed(getattr(state, "data_understanding_bundles", []) or []):
                validation = validate_data_understanding_bundle(bundle)
                if validation.ok:
                    bundle_fingerprint = str(validation.thaw_bundle().get("data_fingerprint") or "")
                    break
            cache_key = (
                scope.fingerprint,
                bundle_fingerprint,
                self._trust_state_cache_digest(),
            )
            if self._prompt_cache_dirty or not self._prompt_cache or cache_key != self._prompt_cache_key:
                self._prompt_cache = self._build_system_prompt()
                self._prompt_cache_dirty = False
                self._prompt_cache_key = cache_key
            prompt = self._prompt_cache
            synthesis_instruction = getattr(self, "_turn_synthesis_policy_instruction", "")
            if synthesis_instruction:
                prompt = prompt + "\n\n" + synthesis_instruction
            final_audit_instruction = getattr(self, "_turn_final_audit_instruction", "")
            if final_audit_instruction:
                prompt = prompt + "\n\n" + final_audit_instruction
            hint = self._execution_prompt_hint()
            if hint:
                prompt = prompt + f"\n\n<execution_control>\n{hint}\n</execution_control>"
            turn_state = getattr(self.context, "turn_state", None)
            if turn_state is not None:
                phase = self._current_prompt_phase()
                turn_state.ensure_phase_capacity(phase)
                components = dict(getattr(self, "_prompt_component_payloads", {}) or {})
                components.update({
                    "conversation_history": self.messages,
                    "synthesis_instruction": synthesis_instruction,
                    "final_audit_instruction": final_audit_instruction,
                    "execution_control": hint,
                })
                capsule = getattr(self, "_turn_trust_capsule", {})
                turn_state.record_prompt_assembly(
                    components,
                    assembled_payload={"system": prompt, "messages": self.messages},
                    trust_capsule_digest=(
                        str(capsule.get("digest") or "") if isinstance(capsule, dict) else ""
                    ),
                    phase=phase,
                )
                self._persist_budget_diagnostics(turn_state)
            return prompt

    def _current_prompt_phase(self) -> str:
        instruction = getattr(self, "_turn_final_audit_instruction", "")
        if 'mode="synthesis"' in instruction:
            return "revision"
        turn_state = getattr(self.context, "turn_state", None)
        if (
            getattr(self, "_turn_synthesis_policy_instruction", "")
            or (turn_state is not None and turn_state.exploration_budget_exhausted)
        ):
            return "synthesis"
        return "exploration"

    def _enter_synthesis_reserve_if_needed(self, user_input: str) -> None:
        """Switch to synthesis before a nearly empty exploration slice can draft the answer."""

        if getattr(self, "_turn_synthesis_policy_instruction", ""):
            return
        turn_state = getattr(self.context, "turn_state", None)
        state = getattr(self.context, "analysis_state", None)
        if turn_state is None or state is None or not getattr(state, "evidence_records", None):
            return
        synthesis_reserve = int(turn_state.budget.synthesis_reserve_tokens or 0)
        if synthesis_reserve <= 0 or not turn_state.can_run_phase("synthesis"):
            return
        if turn_state.remaining_phase_tokens("exploration") > synthesis_reserve:
            return
        self._maybe_inject_synthesis_policy(user_input)

    def _record_stream_delta_budget(self, text: str, *, phase: str) -> int:
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None or not text:
            return 0
        amount = max(1, _estimate_tokens([{"text": text}]))
        turn_state.record_token_usage(amount, phase=phase)
        self._persist_budget_diagnostics(turn_state)
        return amount

    def _record_llm_response_budget(
        self,
        response: Any,
        *,
        phase: str,
        pre_recorded_tokens: int = 0,
    ) -> None:
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None or response is None:
            return
        payload = {
            "text": getattr(response, "text", "") or "",
            "reasoning_content": getattr(response, "reasoning_content", "") or "",
            "tool_calls": [
                {
                    "name": getattr(call, "name", ""),
                    "arguments": getattr(call, "arguments", {}),
                }
                for call in (getattr(response, "tool_calls", None) or [])
            ],
        }
        estimated = max(1, _estimate_tokens([payload]))
        unreported = getattr(response, "unreported_output_tokens", None)
        if unreported is None:
            residual = max(0, estimated - max(0, int(pre_recorded_tokens or 0)))
        else:
            # Structured streaming reports hidden reasoning/tool output across
            # all retry attempts; visible text deltas were charged in real time.
            residual = max(0, int(unreported or 0))
        turn_state.record_llm_round()
        if residual:
            turn_state.record_token_usage(residual, phase=phase)
        self._persist_budget_diagnostics(turn_state)

    def _reclassify_synthesis_tool_round_budget(
        self,
        response: Any,
        *,
        phase: str,
        phase_usage_before: int,
    ) -> None:
        """Keep tool-bearing rounds out of the final synthesis reserve."""

        if (
            phase != "synthesis"
            or response is None
            or not getattr(response, "has_tool_calls", False)
            or self._synthesis_audit_revision_active()
        ):
            return
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return
        used_after = int(turn_state.phase_token_usage.get("synthesis", 0) or 0)
        moved = turn_state.reclassify_phase_usage(
            max(0, used_after - max(0, int(phase_usage_before or 0))),
            source_phase="synthesis",
            target_phase="exploration",
        )
        if moved:
            self._persist_budget_diagnostics(turn_state)

    def _llm_output_limit_kwargs(self, method: Any, *, phase: str) -> dict[str, int]:
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return {}
        configured_max = int(getattr(self.client, "max_tokens", get_config().max_tokens) or 1)
        limit = turn_state.output_limit_for_phase(phase, configured_max)
        try:
            parameters = inspect.signature(method).parameters.values()
            supports_limit = any(
                parameter.name == "max_tokens"
                or parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters
            )
        except (TypeError, ValueError):
            supports_limit = False
        return {"max_tokens": limit} if supports_limit else {}

    def _prepare_analysis_turn(self, user_input: str):
        from data_agent.agent.analysis_flow_controller import AnalysisFlowController
        from data_agent.agent.intent import plan_turn_intent
        from data_agent.session.workspace import workspace

        datasets = workspace.list_datasets()
        context_parts = []
        for name, info in datasets.items():
            context_parts.append(
                f"- {name}: {info['rows']} rows x {info['columns']} cols, "
                f"columns: {', '.join(str(c) for c in info['column_names'][:10])}"
            )
        session_ctx = "\n".join(context_parts)
        intent = plan_turn_intent(user_input, session_ctx)
        controller = AnalysisFlowController(self.session_id, self.context.project_name)
        self._flow_controller = controller
        state = self.context.analysis_state if self.context.analysis_state is not None else controller.load_state()
        self.context.analysis_state = state
        try:
            from data_agent.agent.trust_workflow_runtime import refine_turn_intent_with_state

            intent = refine_turn_intent_with_state(user_input, intent, state)
        except Exception as exc:
            logger.warning(
                "Trust workflow loop intent refinement skipped",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )
        self.context.turn_intent = intent
        self._last_turn_intent = intent
        self._turn_existing_pending_ids = {
            str(c.get("id") or c.get("suspension_id") or "")
            for c in getattr(state, "pending_confirmations", []) or []
            if self._is_actionable_pending_confirmation(c)
        }
        controller.prepare_turn(state, intent, user_input=user_input, dataset_profile=session_ctx)
        try:
            from data_agent.agent.question_need_detector import detect_question_need

            self._turn_question_need = detect_question_need(user_input, intent, state)
        except Exception as exc:
            self._turn_question_need = None
            logger.warning(
                "Question need detection skipped",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )
        profile = _intent_to_budget_profile(intent.intent_type)
        cfg = get_config()
        token_budget = _token_budget_for_profile(profile, cfg.token_threshold)
        # Extract user quality requirements on first analysis turn
        if not self.context.user_quality_requirements and user_input and len(user_input) > 100:
            self._extract_user_requirements(user_input)
        if self.context.user_quality_requirements:
            state.explicit_user_requirements = self.context.user_quality_requirements
            state.save()

        activated_groups = controller.activate_tool_groups(registry, intent, state, user_input)
        # Install the turn execution state AFTER activate_tool_groups so the
        # registry.reset_groups() call inside it (which clears per-turn state)
        # does not wipe the budget/recovery counters we just compiled.
        self.context.turn_state = TurnExecutionState(ToolExecutionBudget(
            profile=profile,
            token_budget=token_budget,
        ))
        return activated_groups

    def _maybe_auto_suspend_for_required_question(self) -> SuspendedForConfirmation | None:
        state = getattr(self.context, "analysis_state", None)
        pending = self._pending_confirmation_for_auto_suspend(state)
        if pending is False:
            return None
        question_need = getattr(self, "_turn_question_need", None)
        has_new_question = (
            isinstance(question_need, dict)
            and question_need.get("status") == "hard_question"
        )
        if not isinstance(pending, dict) and not has_new_question:
            return None

        pending_data = pending if isinstance(pending, dict) else {}
        question_data = question_need if isinstance(question_need, dict) else {}
        state_updates = pending_data.get("state_updates", question_data.get("state_updates"))
        if isinstance(state_updates, dict):
            state_updates_text = json.dumps(state_updates, ensure_ascii=False)
        elif isinstance(state_updates, str) and state_updates.strip():
            state_updates_text = state_updates
        else:
            state_updates_text = json.dumps({"stage": "scope"}, ensure_ascii=False)
        payload = {
            "question": str(pending_data.get("question") or question_data.get("question") or "Please confirm the key information before continuing."),
            "options": list(pending_data.get("options") or question_data.get("options") or []),
            "context": str(pending_data.get("context") or ""),
            "multi_select": False,
            "confirmation_type": str(pending_data.get("confirmation_type") or question_data.get("question_type") or "scope_confirmation"),
            "blocking_reason": str(pending_data.get("blocking_reason") or question_data.get("reason") or ""),
            "state_updates": state_updates_text,
            "related_task_id": int(pending_data.get("related_task_id") or 0),
            "related_spec_id": str(pending_data.get("related_spec_id") or ""),
        }
        susp = self._suspend_for_required_question_payload(
            payload,
            source="pending_confirmation" if isinstance(pending, dict) else "question_need_detector",
            operation=str(payload["confirmation_type"] or "auto_required_question"),
        )
        if isinstance(pending, dict):
            pending.setdefault("question", susp.question)
            pending.setdefault("options", susp.options)
            pending.setdefault("context", susp.context)
            pending.setdefault("confirmation_type", susp.confirmation_type)
            pending.setdefault("blocking_reason", susp.blocking_reason)
            if not pending.get("state_updates"):
                pending["state_updates"] = susp.state_updates
            if state is not None:
                state.save()
        return susp

    def _pending_confirmation_for_auto_suspend(self, state: Any) -> dict[str, Any] | bool | None:
        if state is None:
            return None
        pending_items = [
            c for c in getattr(state, "pending_confirmations", []) or []
            if self._is_actionable_pending_confirmation(c)
        ]
        if not pending_items:
            return None
        eligible_items = [
            item for item in pending_items
            if not item.get("suspension_id")
            and self._is_answerable_pending_confirmation(item)
        ]
        if not eligible_items:
            return False
        existing_ids = getattr(self, "_turn_existing_pending_ids", set()) or set()
        current_turn_items = [
            item
            for item in eligible_items
            if str(item.get("id") or "") not in existing_ids
        ]
        if current_turn_items:
            return current_turn_items[-1]
        return eligible_items[-1]

    @staticmethod
    def _is_answerable_pending_confirmation(item: dict[str, Any]) -> bool:
        return bool(
            item.get("question")
            and isinstance(item.get("options"), list)
            and item.get("options")
            and item.get("state_updates")
        )

    @staticmethod
    def _is_actionable_pending_confirmation(item: Any) -> bool:
        from data_agent.agent.confirmation_policy import is_actionable_pending_confirmation

        return is_actionable_pending_confirmation(item)

    def _extract_user_requirements(self, user_input: str) -> None:
        """Use LLM to extract quality/format requirements from user input (once per session)."""
        try:
            prompt = (
                "从以下用户消息中提取对分析输出格式、质量、详细程度的具体要求。\n"
                "只返回明确的要求（如'详细说明计算方式'、'需要包含置信度'等），忽略背景描述和问题描述。\n"
                "如果没有明确要求，返回空字符串。\n\n"
                f"用户消息：\n{user_input[:2000]}"
            )
            resp = self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                system="你是要求提取专家。只输出提取的要求，不要解释。如无要求输出空。",
            )
            requirements = resp.text.strip()
            if requirements and len(requirements) > 5:
                self.context.user_quality_requirements = requirements
                state = getattr(self.context, "analysis_state", None)
                if state is not None:
                    state.explicit_user_requirements = requirements
                    state.save()
                logger.info("User quality requirements extracted",
                            extra={"extra_data": {"requirements": requirements[:200]}})
        except Exception as e:
            logger.warning("Failed to extract user requirements", extra={"extra_data": {"error": str(e)}})

    def _maybe_inject_quality_reminder(self) -> None:
        """Inject user quality requirements as a reminder when execution budget is converging."""
        if getattr(self, '_quality_reminder_injected', False):
            return
        if not self.context.user_quality_requirements:
            return
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return
        if not turn_state.should_converge:
            return
        self._quality_reminder_injected = True
        self.messages.append({"role": "user", "content": (
            "<quality_reminder>\n"
            "输出前请确保满足以下用户要求：\n"
            f"{self.context.user_quality_requirements}\n"
            "</quality_reminder>"
        )})
        logger.info("Quality reminder injected", extra={"extra_data": {"session_id": self.session_id}})

    def _execution_prompt_hint(self) -> str:
        scope = self.context.workspace_scope or self.__context_operation("refresh")
        if scope.phase == "error":
            return f"{scope.error_type}: {scope.message}"
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return ""
        return turn_state.prompt_hint()

    def _compact_context_if_needed(self) -> None:
        """Compact low-priority history while reattaching deterministic trust state."""

        _microcompact(self.session_id, self.messages)
        turn_state = getattr(self.context, "turn_state", None)
        threshold = int(self.token_threshold)
        summary_max_chars = 6_000
        capsule_max_chars = 8_000
        if turn_state is not None:
            threshold = min(threshold, max(1, int(turn_state.exploration_token_budget)))
            summary_max_chars = min(
                summary_max_chars,
                max(400, int(turn_state.budget.synthesis_reserve_tokens or 0) * 4),
            )
            capsule_max_chars = min(
                capsule_max_chars,
                max(2_000, int(turn_state.budget.audit_reserve_tokens or 0) * 4),
            )
        if _estimate_tokens(self.messages) <= threshold:
            return
        from data_agent.agent.analysis_state import build_trust_capsule

        capsule = build_trust_capsule(
            getattr(self.context, "analysis_state", None),
            user_requirements=self.context.user_quality_requirements,
            active_confirmation=self._active_confirmation_identity(),
            active_datasets=self._active_dataset_capsule_inputs(),
            max_chars=capsule_max_chars,
        )
        if turn_state is not None:
            turn_state.trust_capsule_digest = str(capsule.get("digest") or "")
            self._persist_budget_diagnostics(turn_state)
        self.messages[:] = compact_history(
            self.session_id,
            self.client,
            self.messages,
            self._compact_state,
            token_threshold=threshold,
            trust_capsule=capsule,
            summary_max_chars=summary_max_chars,
            recent_max_chars=min(12_000, max(1_000, threshold * 2)),
        )
        self._prompt_cache_dirty = True

    def _persist_budget_diagnostics(self, turn_state: TurnExecutionState) -> None:
        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return
        diagnostics = turn_state.budget_diagnostics()
        previous = getattr(state, "budget_diagnostics", None)
        previous_digest = (
            str(previous.get("trust_capsule_digest") or "")
            if isinstance(previous, dict)
            else ""
        )
        state.budget_diagnostics = diagnostics
        current_digest = str(diagnostics.get("trust_capsule_digest") or "")
        if current_digest and current_digest != previous_digest:
            save = getattr(state, "save", None)
            if callable(save):
                save()

    def _active_confirmation_identity(self) -> dict[str, Any] | None:
        """Read the durable confirmation checkpoint for capsule/restart identity."""

        try:
            record = self._confirmation_runtime().checkpoint(self.session_id)
        except Exception:
            return None
        if record is None:
            return None
        params = getattr(record, "resolution_params", None)
        params = dict(params) if isinstance(params, dict) else {}
        return {
            "confirmation_id": str(getattr(record, "confirmation_id", "") or ""),
            "version": getattr(record, "version", None),
            "proposal_ref": {
                "proposal_id": str(params.get("proposal_id") or ""),
                "candidate_fingerprint": str(params.get("candidate_fingerprint") or ""),
                "data_version": str(
                    params.get("data_version") or getattr(record, "data_version", "") or ""
                ),
                "spec_version": str(
                    params.get("spec_version") or getattr(record, "spec_version", "") or ""
                ),
            },
        }

    def _active_dataset_capsule_inputs(self) -> list[dict[str, Any]]:
        try:
            datasets = self.context.workspace.list_datasets()
        except Exception:
            return []
        result: list[dict[str, Any]] = []
        for name, info in sorted((datasets or {}).items()):
            if not isinstance(info, dict):
                continue
            metadata = info.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            source_fingerprint = str(metadata.get("_source_fingerprint") or "")
            entry = {
                "dataset": str(name),
                "dataset_version_id": str(info.get("dataset_id") or ""),
                "raw_dataset_id": str(info.get("raw_dataset_id") or ""),
                "raw_fingerprint": source_fingerprint,
                "source_fingerprint": source_fingerprint,
            }
            if any(entry.values()):
                result.append(entry)
        return result

    def _hydrate_overflow_trust_context(
        self,
        capsule: dict[str, Any],
        *,
        redact_dataset_names: bool = False,
    ) -> str:
        if capsule.get("status") != "requires_hydration":
            return ""
        state = getattr(self.context, "analysis_state", None)
        plan = getattr(state, "analysis_plan", None)
        plan = plan if isinstance(plan, dict) else {}
        requirement_ids = [
            str(item.get("id") or "")
            for group in (plan.get("analysis_requirements") or {}).values()
            if isinstance(group, list)
            for item in group
            if isinstance(item, dict)
            and item.get("status") != "satisfied"
            and str(item.get("id") or "")
        ] if isinstance(plan.get("analysis_requirements"), dict) else []
        evidence_ids = [
            str(item.get("id") or "")
            for item in (getattr(state, "evidence_records", None) or [])
            if isinstance(item, dict) and str(item.get("id") or "")
        ]
        dataset_names = [
            str(item.get("dataset") or item.get("name") or "")
            for item in self._active_dataset_capsule_inputs()
            if str(item.get("dataset") or item.get("name") or "")
        ]
        requested = {
            "datasets": dataset_names,
            "unresolved_hard_requirements": requirement_ids,
            "evidence_bindings": evidence_ids,
        }
        try:
            from data_agent.agent.artifact_refs import hydrate_trust_capsule_manifest

            hydrated = hydrate_trust_capsule_manifest(
                capsule.get("trust_manifest") or {},
                expected_session_id=self.session_id,
                expected_plan_id=str(plan.get("id") or ""),
                expected_body_digest=str(
                    (capsule.get("trust_manifest") or {}).get("body_digest") or ""
                ),
                requested_ids=requested,
                per_component_limit=8,
                include_confirmation=True,
            )
        except Exception:
            hydrated = {}
        if not hydrated:
            return json.dumps({
                "status": "hydration_failed",
                "required_action": "downgrade_or_disclose",
                "manifest_digest": str(
                    (capsule.get("trust_manifest") or {}).get("body_digest") or ""
                ),
            }, ensure_ascii=False, sort_keys=True)
        confirmation = hydrated.get("active_confirmation")
        if isinstance(confirmation, dict):
            hydrated["active_confirmation"] = {
                key: (
                    confirmation.get(key)
                    if key == "version"
                    else (
                        str(confirmation.get(key) or "")
                        if len(str(confirmation.get(key) or "")) <= 320
                        else "sha256:" + hashlib.sha256(
                            str(confirmation.get(key) or "").encode("utf-8")
                        ).hexdigest()
                    )
                )
                for key in (
                    "id",
                    "version",
                    "proposal_id",
                    "candidate_fingerprint",
                    "data_version",
                    "spec_version",
                )
            }
        if redact_dataset_names:
            hydrated = _redact_trust_dataset_names(hydrated)
        hydrated["status"] = "hydrated_with_limits"
        hydrated["omitted_counts"] = {
            key: max(0, len(values) - 8)
            for key, values in requested.items()
        }
        hydrated["required_action"] = (
            "Use only hydrated identities. Downgrade or disclose any claim whose required identity is omitted."
        )
        text = json.dumps(hydrated, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(text) <= 4_000:
            return text
        return json.dumps({
            "status": "hydration_exceeded_prompt_limit",
            "required_action": "downgrade_or_disclose",
            "manifest_digest": str(
                (capsule.get("trust_manifest") or {}).get("body_digest") or ""
            ),
        }, ensure_ascii=False, sort_keys=True)

    def _trust_state_cache_digest(self) -> str:
        state = getattr(self.context, "analysis_state", None)
        payload = {
            "user_requirements": self.context.user_quality_requirements,
            "active_datasets": self._active_dataset_capsule_inputs(),
            "active_confirmation": self._active_confirmation_identity(),
        }
        if state is not None:
            for field_name in (
                "goal",
                "explicit_user_requirements",
                "analysis_plan",
                "data_pool",
                "dataset_contracts",
                "computation_refs",
                "evidence_records",
                "pending_confirmations",
                "verification_reports",
                "route_proposals",
                "cleaning_logs",
            ):
                payload[field_name] = getattr(state, field_name, None)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _is_tool_blocked_by_confirmation(self, tool_name: str) -> bool:
        from data_agent.agent.analysis_flow_controller import AnalysisFlowController

        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return False
        controller = AnalysisFlowController(self.session_id, self.context.project_name)
        return controller.is_tool_blocked_by_confirmation(state, tool_name)

    def _blocked_tool_message(self, tool_name: str) -> str:
        return (
            f"Tool '{tool_name}' requires structured confirmation before execution. "
            "I will keep the analysis at the planning stage until the user confirms the method, scope, or metric assumptions."
        )

    def _fill_remaining_tool_responses(self, tool_calls: list, start_index: int, reason: str) -> None:
        """Add error tool responses for unprocessed tool_call_ids to keep message history valid."""
        for tc in tool_calls[start_index:]:
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps({"error": reason, "error_type": "early_termination"}, ensure_ascii=False),
            })

    def _bind_tool_call(self, tc):
        """Bind a substantive tool call to its plan step before execution.

        Returns a ``StepBindingResult`` (successful or not) for tools with
        capability metadata; returns ``None`` for non-substantive tools that
        don't participate in plan/step identity (e.g. capability-less helpers
        or pure interaction tools). The caller passes the result into
        ``_compact_tool_output`` which is the single consumer.
        """

        try:
            from data_agent.agent.analysis_execution import bind_tool_call_to_plan_step

            state = getattr(self.context, "analysis_state", None)
            plan = getattr(state, "analysis_plan", None)
            if not isinstance(plan, dict) or not plan:
                return None
            capability = registry.capability_for(tc.name)
            if not capability:
                return None
            from data_agent.agent.execution_scope import dataset_arguments_for_tool

            dataset_names = dataset_arguments_for_tool(
                registry,
                tc.name,
                dict(tc.arguments or {}),
            )
            dataset_names = list(dict.fromkeys(dataset_names))
            scope = getattr(self.context, "workspace_scope", None)
            preferred_step_id = str(getattr(scope, "step_id", "") or "")
            return bind_tool_call_to_plan_step(
                plan=plan,
                tool_name=tc.name,
                capability=capability,
                dataset_names=dataset_names,
                preferred_step_id=preferred_step_id,
            )
        except Exception as exc:
            logger.warning(
                "Tool binding skipped: %s",
                exc,
                extra={"extra_data": {"tool": tc.name, "error": str(exc)}},
            )
            return None

    def _analysis_run_binding(self, step_binding):
        from data_agent.session.task_manager import task_manager

        resolver = getattr(task_manager, "get_analysis_run_tool_binding", None)
        if not callable(resolver):
            return None
        external_step_id = str(
            getattr(step_binding, "step_id", "")
            or getattr(self.context.workspace_scope, "step_id", "")
            or ""
        )
        try:
            return resolver(
                session_id=self.session_id,
                project_name=self.context.project_name or "",
                external_step_id=external_step_id,
            )
        except Exception:
            return None

    def _persist_analysis_run_outcome(self, tc, binding, outcome):
        if not binding:
            return outcome
        from data_agent.session.task_manager import task_manager

        try:
            task_manager.record_analysis_tool_outcome(
                session_id=self.session_id,
                binding=binding,
                tool_call_id=str(tc.id or ""),
                tool_name=tc.name,
                state=outcome.state.value,
                artifact_ids=outcome.artifact_ids,
                warning=(
                    {
                        "error_type": outcome.warning.error_type,
                        "message": outcome.warning.message,
                    }
                    if outcome.warning is not None
                    else None
                ),
            )
            return outcome
        except Exception:
            return with_workflow_warning(
                outcome,
                error_type="tool_outcome_persistence_failed",
                message="The tool result committed, but its workflow outcome could not be persisted.",
            )

    def _maybe_project_structured_evidence(
        self,
        *,
        ref: dict[str, Any],
        step_binding: Any,
        plan: dict[str, Any],
        capability: Any,
    ) -> None:
        """Auto-project a successful structured computation into v2 evidence.

        Reuses ``project_structured_computation_evidence``: on success it
        upserts the validated record and dirties the synthesis-policy
        cache so the next prompt rebuilds against the new evidence. On
        failure it appends a bounded projection diagnostic. The model is
        never asked to call ``record_evidence_record`` for this turn into
        a tool call; eligibility failures stay computation-only.
        """

        try:
            from data_agent.agent.evidence_contracts import (
                project_structured_computation_evidence,
            )
            from data_agent.config import get_config

            state = getattr(self.context, "analysis_state", None)
            if state is None:
                return
            if step_binding is None or not getattr(step_binding, "ok", False):
                return
            capability_payload: dict[str, Any] | None = None
            if capability is not None:
                if isinstance(capability, dict):
                    capability_payload = capability
                else:
                    to_dict = getattr(capability, "to_dict", None)
                    if callable(to_dict):
                        capability_payload = to_dict()
                    else:
                        capability_payload = {
                            "capability_id": str(getattr(capability, "capability_id", "") or ""),
                            "evidence_fields": list(getattr(capability, "evidence_fields", []) or []),
                            "risk_level": str(getattr(capability, "risk_level", "") or ""),
                        }
            dataset_contracts = list(getattr(state, "dataset_contracts", []) or [])
            turn_state = getattr(self.context, "turn_state", None)
            turn_id = str(getattr(turn_state, "turn_id", "") or "")
            result = project_structured_computation_evidence(
                computation_ref=ref,
                binding=step_binding,
                plan=plan,
                capability=capability_payload,
                dataset_contracts=dataset_contracts,
                current_session_id=self.session_id,
                current_turn_id=turn_id,
                sessions_root=get_config().sessions_resolved,
            )

            if result.projected:
                projected_records = tuple(result.records or (result.record,))
                # Automatic evidence must own canonical workflow progress as
                # well as persistence. Requiring the model to replay the same
                # record through ``record_evidence_record`` reintroduces a
                # bookkeeping ritual and can leave workspace scope with no
                # current task between analytical steps.
                from data_agent.session.task_manager import task_manager

                completed_task_ids: list[int] = []
                stored_records: list[dict[str, Any]] = []
                for record in projected_records:
                    projected_record = state.upsert_evidence_record(record)
                    stored_records.append(projected_record)
                    completed_task_ids.extend(
                        task_manager.complete_matching_tasks_from_evidence(
                            session_id=state.session_id,
                            evidence=projected_record,
                            analysis_spec_id="",
                        ) or []
                    )
                # Invalidate the synthesis-policy cache so the next prompt
                # rebuilds the bounded evidence catalog with this record.
                self._turn_synthesis_policy_injected = False
                self._turn_synthesis_policy_instruction = ""
                self._turn_synthesis_evidence_aliases = ()
                state.append_turn_diagnostic({
                    "event": "evidence_projected",
                    "tool_call_id": str(ref.get("tool_call_id") or ""),
                    "plan_id": str(ref.get("plan_id") or ""),
                    "step_id": str(ref.get("step_id") or ""),
                    "claim_keys": [
                        str(record.get("claim_key") or "")
                        for record in stored_records
                    ],
                    "evidence_ids": [
                        str(record.get("id") or "")
                        for record in stored_records
                    ],
                    "completed_task_ids": list(dict.fromkeys(completed_task_ids)),
                })
                return
            state.append_turn_diagnostic({
                "event": "evidence_projection_skipped",
                "tool_call_id": str(ref.get("tool_call_id") or ""),
                "reason": str(result.reason or ""),
                "diagnostics": list(result.diagnostics or []),
            })
        except Exception as exc:
            logger.warning(
                "Structured evidence projection skipped: %s",
                exc,
                extra={"extra_data": {"tool": str(ref.get("tool_name") or ""), "error": str(exc)}},
            )

    def _fallback_resolution_for_tool_call(self, tool_call: Any) -> str:
        """Return a server-persisted fallback resolution for this call.

        A successful ``run_python`` result is never promoted to structured
        evidence. Once its traceable computation reference has been stored,
        the server can deterministically resolve the control gate as a
        computation-only limitation instead of asking the model to perform a
        bookkeeping tool call.
        """

        if str(getattr(tool_call, "name", "") or "") != "run_python":
            return ""
        state = getattr(self.context, "analysis_state", None)
        refs = getattr(state, "computation_refs", None)
        if not isinstance(refs, list):
            return ""
        call_id = str(getattr(tool_call, "id", "") or "")
        for ref in reversed(refs):
            if not isinstance(ref, dict):
                continue
            if str(ref.get("tool_call_id") or "") != call_id:
                continue
            if not bool(ref.get("success")):
                return ""
            return str(ref.get("fallback_resolution") or "")
        return ""

    def _compact_tool_output(self, tool_result, tc, step_binding=None) -> str:
        """Compact tool output for LLM context. Persist data/details to disk, return concise summary.

        ``step_binding`` is the canonical ``StepBindingResult`` for this tool
        call. When supplied and successful, plan/step identity and the claim
        key/requirement IDs flow only from the binding. Unsuccessful or absent
        bindings persist an untrusted computation ref with empty identity and
        the structured diagnostic; we never invent identity later.
        """
        from data_agent.tools.registry import ToolResult

        summary = tool_result.to_cli()
        success = not self._tool_content_is_error(str(summary or ""))

        try:
            from data_agent.agent.evidence_contracts import persist_computation_output
            from data_agent.config import get_config

            state = getattr(self.context, "analysis_state", None)
            turn_state = getattr(self.context, "turn_state", None)
            plan = getattr(state, "analysis_plan", None)
            scope = getattr(self.context, "workspace_scope", None)
            from data_agent.agent.execution_scope import dataset_arguments_for_tool
            from data_agent.agent.evidence_contracts import (
                analysis_plan_semantic_digest,
                analysis_step_semantic_digest,
            )

            dataset_names = dataset_arguments_for_tool(
                registry,
                tc.name,
                dict(tc.arguments or {}),
            )
            try:
                summary_payload = json.loads(summary)
            except (TypeError, json.JSONDecodeError):
                summary_payload = None
            if tc.name == "run_python" and isinstance(summary_payload, dict):
                dataset_names.extend(
                    str(item)
                    for item in (summary_payload.get("dataset_reads") or [])
                    if str(item)
                )
            dataset_names = list(dict.fromkeys(dataset_names))
            binding_active = step_binding is not None and bool(getattr(step_binding, "ok", False))
            if binding_active:
                plan_id = str(getattr(step_binding, "plan_id", "") or "")
                step_id = str(getattr(step_binding, "step_id", "") or "")
                claim_key = str(getattr(step_binding, "claim_key", "") or "")
                claim_keys = [
                    str(item)
                    for item in (getattr(step_binding, "claim_keys", ()) or ())
                    if str(item)
                ] or ([claim_key] if claim_key else [])
                requirement_ids = [
                    str(item)
                    for item in (getattr(step_binding, "requirement_ids", ()) or ())
                    if str(item)
                ]
                binding_error_type = ""
                binding_candidate_step_ids: list[str] = []
            else:
                plan_id = ""
                step_id = ""
                claim_key = ""
                claim_keys = []
                requirement_ids = []
                if step_binding is not None:
                    binding_error_type = str(getattr(step_binding, "error_type", "") or "")
                    binding_candidate_step_ids = [
                        str(item)
                        for item in (getattr(step_binding, "candidate_step_ids", ()) or ())
                        if str(item)
                    ]
                else:
                    binding_error_type = "analysis_step_not_bound"
                    binding_candidate_step_ids = []
            dataset_versions = []
            for dataset_name in dataset_names:
                info = self.context.workspace.get_active_version_info(dataset_name)
                if isinstance(info, dict) and info.get("dataset_id"):
                    dataset_versions.append(str(info["dataset_id"]))
            definition = registry.get(tc.name)
            capability = getattr(definition, "capability", None)
            method_steps = [
                item
                for item in ((plan or {}).get("method_plan") or [])
                if isinstance(item, dict) and str(item.get("step_id") or "")
            ] if isinstance(plan, dict) else []
            current_step = next((
                item
                for item in method_steps
                if str(item.get("step_id") or "") == step_id
            ), {})
            with self._computation_ref_lock:
                ref = persist_computation_output(
                    sessions_root=get_config().sessions_resolved,
                    session_id=self.session_id,
                    turn_id=str(getattr(turn_state, "turn_id", "") or ""),
                    plan_id=plan_id,
                    step_id=step_id,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    arguments=dict(tc.arguments or {}),
                    output=tool_result.to_web(),
                    dataset_versions=dataset_versions,
                    success=success,
                    plan_digest=analysis_plan_semantic_digest(plan or {}),
                    step_digest=analysis_step_semantic_digest(current_step),
                    capability_id=str(getattr(capability, "capability_id", "") or ""),
                    evidence_fields=list(getattr(capability, "evidence_fields", []) or []),
                )
                ref["claim_key"] = claim_key
                ref["claim_keys"] = claim_keys
                ref["requirement_ids"] = requirement_ids
                ref["binding_error_type"] = binding_error_type
                if tc.name == "run_python" and success:
                    ref["fallback_resolution"] = "computation_only_limitation"
                    ref["limitations"] = [
                        "Free-form Python output is traceable computation only; "
                        "it is not automatically promoted to verified evidence."
                    ]
                if binding_candidate_step_ids:
                    ref["binding_candidate_step_ids"] = binding_candidate_step_ids
                if state is not None:
                    state.upsert_computation_ref(ref)
                    state.append_turn_diagnostic({
                        "event": "tool_binding",
                        "tool_call_id": tc.id,
                        "tool_name": tc.name,
                        "ok": binding_active,
                        "plan_id": plan_id,
                        "step_id": step_id,
                        "error_type": binding_error_type,
                    })
                    self._maybe_project_structured_evidence(
                        ref=ref,
                        step_binding=step_binding,
                        plan=plan or {},
                        capability=capability,
                    )
                    state.save()
        except Exception as exc:
            logger.warning(
                "Computation provenance persistence skipped: %s",
                exc,
                extra={"extra_data": {"tool": tc.name, "error": str(exc)}},
            )

        # If ToolResult has structured data, persist it
        if tool_result.data is not None:
            try:
                persist_detail(self.session_id, tc.id, tool_result.data)
                detail_ref = f" [detail: tool_outputs/{tc.id}_detail.json]"
            except Exception:
                detail_ref = ""
        else:
            detail_ref = ""

        # If summary is short enough, keep as-is
        if len(summary) <= TOOL_SUMMARY_THRESHOLD:
            return persist_large_output(self.session_id, tc.id, summary + detail_ref)

        # Long summary: persist full version, return truncated + reference
        try:
            persist_detail(self.session_id, tc.id, {"full_output": summary})
            truncated = summary[:TOOL_SUMMARY_THRESHOLD]
            # Try to break at a natural boundary
            last_newline = truncated.rfind("\n")
            if last_newline > TOOL_SUMMARY_THRESHOLD * 0.7:
                truncated = truncated[:last_newline]
            compact = (
                f"{truncated}\n\n"
                f"[Output truncated. Full result: tool_outputs/{tc.id}_detail.json]"
            )
            return persist_large_output(self.session_id, tc.id, compact)
        except Exception:
            return persist_large_output(self.session_id, tc.id, summary)

    def _auto_track_task_progress(self, tool_name: str, success: bool) -> None:
        """Auto-update in_progress tasks when tools execute successfully.

        If there are in_progress tasks for this session, mark the first one
        as completed when a tool succeeds. This provides basic progress tracking
        even when the LLM forgets to call task_update.
        """
        try:
            from data_agent.session.task_manager import task_manager
            tasks = task_manager.list_for_scope(
                session_id=self.session_id,
                project_name=self.context.project_name,
            )
            in_progress = [t for t in tasks if t["status"] == "in_progress"]
            legacy_in_progress = [
                task for task in in_progress
                if not (task.get("analysis_plan_id") or task.get("step_id"))
            ]
            if legacy_in_progress and success:
                task_manager.update(legacy_in_progress[0]["id"], status="completed")
        except Exception:
            pass

    def _repair_broken_tool_sequence(self) -> None:
        """Scan messages for assistant tool_calls missing corresponding tool responses and fill them in."""
        i = 0
        while i < len(self.messages):
            msg = self.messages[i]
            if msg.get("role") != "assistant" or "tool_calls" not in msg:
                i += 1
                continue
            # Collect expected tool_call_ids
            expected_ids = {tc["id"] for tc in msg["tool_calls"]}
            # Scan subsequent messages for tool responses
            j = i + 1
            while j < len(self.messages) and self.messages[j].get("role") == "tool":
                expected_ids.discard(self.messages[j].get("tool_call_id"))
                j += 1
            # Fill in any missing responses
            for missing_id in expected_ids:
                self.messages.insert(j, {
                    "role": "tool",
                    "tool_call_id": missing_id,
                    "content": json.dumps({"error": "Previous turn ended early", "error_type": "repaired"}, ensure_ascii=False),
                })
                j += 1
            i = j

    def _build_interrupt_context(self, user_input: str) -> str:
        """Build context hint when the previous turn was interrupted."""
        from data_agent.session.task_manager import task_manager
        # Find in-progress or pending tasks from the interrupted session
        active_tasks = [t for t in task_manager.list_all()
                        if t["status"] in ("in_progress", "pending")
                        and t.get("session_id") == self.session_id]
        task_hint = ""
        if active_tasks:
            task_lines = [f"  - #{t['id']}: {t['subject']} ({t['status']})" for t in active_tasks]
            task_hint = "\n之前未完成的任务：\n" + "\n".join(task_lines)

        return (
            "<system_context>\n"
            "⚠️ 之前的分析任务被用户中断。用户已提供新的指令，请根据最新指令重新评估任务计划：\n"
            "1. 如果新指令与之前任务完全不同，应删除之前的待处理任务并创建新任务\n"
            "2. 如果新指令是对之前任务的调整，应更新相关任务状态并据此调整计划\n"
            "3. 不要自动继续执行之前被中断的任务\n"
            f"{task_hint}\n"
            f"用户新指令：{user_input}\n"
            "</system_context>"
        )

    def _was_last_turn_interrupted(self) -> bool:
        """Check if the last assistant message indicates an interrupted turn."""
        for msg in reversed(self.messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                return "[已中断]" in content
        return False

    def _reset_turn_tracking(self) -> None:
        self._turn_tools_used = []
        self._turn_tool_outcomes = []
        self._turn_loaded_data = False
        self._turn_final_guard_injected = False
        self._turn_verification_injected = False
        self._turn_synthesis_policy_injected = False
        self._turn_synthesis_policy_instruction = ""
        self._turn_synthesis_evidence_aliases = ()
        self._turn_final_audit_revision_used = False
        self._turn_final_audit_analysis_retry_used = False
        self._turn_final_audit_instruction = ""
        self._turn_last_final_audit = None
        self._turn_provider_truncation_repair_used = False
        self._turn_resumed_from_confirmation = False
        self._turn_last_round_budget: dict[str, Any] | None = None
        self._turn_final_answer_candidates: list[dict[str, str]] = []

    # --- Safe live analysis progress narration -----------------------------
    # ``_progress_payload`` returns the wire dict for a closed-vocabulary
    # progress event (or ``None`` if the code/state was rejected). Streaming
    # callers yield the dict; sync callers pass it to
    # ``_record_progress_diagnostic`` so CLI/tests share the same provenance
    # trail without SSE. Progress payloads only carry identity/phase — no
    # values, p-values, rankings, claims, or reasoning.

    def _progress_payload(
        self,
        code: str,
        *,
        step_id: str = "",
        status: str = "running",
        phase: str = "",
    ) -> dict[str, str] | None:
        try:
            return build_analysis_progress(
                code=code,
                step_id=step_id,
                status=status,  # type: ignore[arg-type]
                phase=phase,
            ).to_dict()
        except Exception as exc:
            logger.warning(
                "analysis_progress event skipped",
                extra={"extra_data": {"code": code, "error": str(exc)}},
            )
            return None

    def _record_progress_diagnostic(self, payload: dict[str, str] | None) -> None:
        if not payload:
            return
        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return
        diagnostic = {"kind": "analysis_progress"}
        diagnostic.update(payload)
        # Strip the wire-only ``type`` key so the diagnostic is purely
        # observational and does not masquerade as a streamed event.
        diagnostic.pop("type", None)
        append = getattr(state, "append_turn_diagnostic", None)
        # Best-effort observability: progress diagnostics must never break
        # the main loop. Test stubs may use SimpleNamespace without the
        # method; just drop the diagnostic in that case.
        if callable(append):
            try:
                append(diagnostic)
            except Exception as exc:
                logger.warning(
                    "analysis_progress diagnostic dropped",
                    extra={"extra_data": {"error": str(exc)}},
                )

    def _emit_progress_stream(
        self,
        code: str,
        *,
        step_id: str = "",
        status: str = "running",
        phase: str = "",
    ):
        """Yield a progress event for SSE streaming (no-op on rejection)."""
        payload = self._progress_payload(code, step_id=step_id, status=status, phase=phase)
        if payload is not None:
            yield payload

    def _record_progress(
        self,
        code: str,
        *,
        step_id: str = "",
        status: str = "running",
        phase: str = "",
    ) -> None:
        """Record a progress event in turn diagnostics for sync execution."""
        self._record_progress_diagnostic(
            self._progress_payload(code, step_id=step_id, status=status, phase=phase)
        )

    # --- End progress narration -------------------------------------------

    def _tool_content_is_error(self, content: str) -> bool:
        stripped = (content or "").lstrip()
        payload_text = stripped.split(" [detail:", 1)[0]
        try:
            payload = json.loads(payload_text)
        except (TypeError, json.JSONDecodeError):
            payload = None
        return (
            isinstance(payload, dict) and "error" in payload
        ) or stripped.casefold().startswith("error")

    def _record_turn_tool_result(self, tool_name: str, tool_msg_content: str) -> None:
        if not hasattr(self, "_turn_tools_used"):
            self._reset_turn_tracking()
        self._turn_tools_used.append(tool_name)
        is_error = self._tool_content_is_error(tool_msg_content)
        if not hasattr(self, "_turn_tool_outcomes"):
            self._turn_tool_outcomes = []
        # Keep the most recent outcome per tool_call_id-ish key (tool_name + index).
        self._turn_tool_outcomes.append({
            "tool_name": tool_name,
            "tool_call_id": f"{tool_name}_{len(self._turn_tool_outcomes)}",
            "success": not is_error,
            "error_category": (
                self._categorize_tool_error(tool_msg_content) if is_error else ""
            ),
        })
        if tool_name == "load_data" and not is_error:
            self._turn_loaded_data = True

    @staticmethod
    def _categorize_tool_error(content: str) -> str:
        text = (content or "").lower()
        if "not found" in text or "不存在" in text or "missing" in text or "找不到" in text:
            return "missing_column_or_data"
        if "too few" in text or "数据点太少" in text or "insufficient" in text:
            return "insufficient_data"
        if "安全" in text or "sandbox" in text or "not allowed" in text:
            return "sandbox_violation"
        return "tool_error"

    def _maybe_replan_after_data_load(self, user_input: str) -> None:
        if not getattr(self, "_turn_loaded_data", False):
            return
        self._turn_loaded_data = False
        if not user_input:
            return
        self._prompt_cache_dirty = True
        with self.__context_operation("use"):
            self._prepare_analysis_turn(user_input)

    def _turn_tool_error_count(self) -> int:
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return 0
        return len(getattr(turn_state, "tool_errors", []) or [])

    def _current_dataset_profile(self) -> str:
        from data_agent.session.workspace import workspace as workspace_obj

        try:
            datasets = workspace_obj.list_datasets()
        except Exception:
            return ""
        profile_lines = []
        for name, info in (datasets or {}).items():
            if isinstance(info, dict):
                rows = info.get("rows", "?")
                cols = info.get("columns", "?")
                columns = info.get("column_names") or []
                column_text = ", ".join(str(col) for col in columns[:10])
                profile_lines.append(f"- {name}: {rows} rows x {cols} cols; columns: {column_text}")
            else:
                profile_lines.append(f"- {name}: {info}")
        return "\n".join(profile_lines)

    def _maybe_inject_synthesis_policy(self, user_input: str) -> None:
        intent = getattr(self, "_last_turn_intent", None)
        if intent is None or intent.intent_type not in ("directed_analysis", "comprehensive_report"):
            return
        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return
        evidence = getattr(state, "evidence_records", []) or []
        if not evidence:
            return

        try:
            from data_agent.agent.trust_workflow_runtime import maybe_verify_turn_claims

            self._turn_verification_injected = True
            maybe_verify_turn_claims(user_input, state)
        except Exception as exc:
            logger.warning(
                "Trust workflow loop verification skipped",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )

        try:
            from data_agent.agent.trust_workflow_runtime import maybe_create_hypothesis_set

            maybe_create_hypothesis_set(user_input, intent, state)
        except Exception as exc:
            logger.warning(
                "Trust workflow loop hypothesis creation skipped",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )

        from data_agent.agent.synthesis_policy import (
            build_synthesis_instruction,
            derive_synthesis_policy,
        )

        policy = derive_synthesis_policy(
            intent=intent,
            state=state,
            user_input=user_input,
            data_profile=self._current_dataset_profile(),
            tool_error_count=self._turn_tool_error_count(),
            user_requirements=self.context.user_quality_requirements,
            proficiency=self.context.user_proficiency,
        )
        self._turn_synthesis_policy_instruction = build_synthesis_instruction(policy)
        self._turn_synthesis_evidence_aliases = tuple(policy.evidence_aliases)
        self._turn_synthesis_policy_injected = True

    def _is_final_answer_audit_candidate(self) -> bool:
        intent = getattr(self, "_last_turn_intent", None)
        if intent is not None and getattr(intent, "intent_type", "") in {
            "directed_analysis", "comprehensive_report", "result_followup",
        }:
            return True
        if not getattr(self, "_turn_resumed_from_confirmation", False):
            return False
        state = getattr(self.context, "analysis_state", None)
        return state is not None and bool(
            getattr(state, "analysis_plan", None)
            or getattr(state, "evidence_records", None)
        )

    def _should_buffer_final_answer_text(self) -> bool:
        return self._is_final_answer_audit_candidate()

    def _analysis_retry_budget_available(self) -> bool:
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return False
        budget = getattr(turn_state, "budget", None)
        if budget is None:
            return False
        if turn_state.tool_calls >= int(getattr(budget, "max_tool_calls", 0) or 0):
            return False
        if getattr(turn_state, "exploration_budget_exhausted", False):
            return False
        max_elapsed = getattr(budget, "max_elapsed_seconds", None)
        if max_elapsed is not None and turn_state.elapsed_seconds >= max_elapsed:
            return False
        return True

    def _discard_last_answer_candidate(self) -> None:
        if not self.messages:
            return
        last = self.messages[-1]
        if last.get("role") == "assistant" and not last.get("tool_calls"):
            self.messages.pop()

    def _replace_last_answer_candidate(self, public_text: str) -> None:
        for message in reversed(self.messages):
            if message.get("role") == "assistant" and not message.get("tool_calls"):
                message["content"] = public_text
                return
        self.messages.append({"role": "assistant", "content": public_text})

    def _public_intermediate_text(self, text: str) -> str:
        from data_agent.agent.answer_quality import strip_internal_evidence_markers

        return strip_internal_evidence_markers(text)

    def _interrupted_response_text(self, partial_text: str) -> str:
        if self._is_final_answer_audit_candidate():
            return "分析在最终审计前被中断；未发布未经审计的分析结论。\n\n[已中断]"
        return (partial_text or "分析已中断。") + "\n\n[已中断]"

    def _inject_final_answer_audit_repair(
        self,
        *,
        mode: str,
        reason_codes: list[str],
    ) -> None:
        self._discard_last_answer_candidate()
        if mode == "synthesis":
            if "provider_output_truncated" in reason_codes:
                instruction = (
                    "The provider stopped the previous final draft at its output limit. Rewrite it as one "
                    "complete self-contained answer; do not continue from the cutoff and do not call tools. "
                    "Keep the visible answer within 2400 Chinese characters and prioritize the answer over "
                    "process narration. It must contain explicit findings, actionable recommendations, and "
                    "limitations. Copy only exact current short measurement aliases from "
                    "bounded_evidence_catalog using [[evidence:aeNN#amNN]] markers and copy the exact metric_label "
                    "and value from the same entry without translating or rounding those identity tokens; "
                    "when required_verified_core_copy= is present, begin the revised answer by copying only its "
                    "value verbatim, including the marker; "
                    "include at least one standalone verified-core sentence with exactly one catalog measurement; "
                    "downgrade unsupported claims, and keep "
                    "the internal evidence markers for re-audit. This is the only truncation repair attempt."
                )
            else:
                instruction = (
                    "Revise the synthesis only. Do not call tools. Copy the exact current short measurement "
                    "aliases shown in bounded_evidence_catalog, using [[evidence:aeNN#amNN]] markers; "
                    "for each cited measurement copy the exact metric_label and value from the same entry. "
                    "Do not translate or round those identity tokens; add Chinese explanation around them. "
                    "When required_verified_core_copy= is present, Begin the revised answer by copying only its "
                    "value verbatim, including the marker. "
                    "Include at least one standalone verified-core sentence using exactly one catalog measurement, "
                    "its exact metric_label/value, and its marker, with no unrelated quantity in that sentence. "
                    "remove or downgrade unsupported claims, add required limitations/exploratory labels, and keep "
                    "the internal evidence markers for re-audit. Return a complete answer, not process narration; "
                    "for a comprehensive report include findings, recommendations, and limitations with enough "
                    "supporting context to stand alone. This is the only synthesis revision attempt."
                )
        else:
            instruction = (
                "Do not merely rephrase the blocked draft. Continue the required analysis with available tools, "
                "record current computation evidence, then synthesize only supported findings. If evidence cannot "
                "be produced within the remaining budget, return only diagnostic evidence gaps."
            )
        codes = ",".join(sorted(set(reason_codes)))
        self._turn_final_audit_instruction = (
            f'<final_answer_audit_repair mode="{mode}" reason_codes="{codes}">'
            f"{instruction}</final_answer_audit_repair>"
        )
        self._prompt_cache_dirty = True

    def _maybe_repair_truncated_analysis_response(self, response: Any) -> bool:
        """Use one revision-reserve round for a provider-truncated final draft."""

        finish_reason = str(getattr(response, "finish_reason", "") or "").casefold()
        if finish_reason not in {"length", "max_tokens", "max_output_tokens"}:
            return False
        if getattr(response, "has_tool_calls", False):
            return False
        if not self._is_final_answer_audit_candidate():
            return False
        if getattr(self, "_turn_provider_truncation_repair_used", False):
            return False
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is not None and not turn_state.claim_revision_attempt():
            return False
        self._remember_final_answer_candidate(
            str(getattr(response, "text", "") or ""),
            reason="provider_output_truncated",
        )
        self._turn_provider_truncation_repair_used = True
        # The final-audit revision flag shares the same single revision
        # reserve.  A truncation rewrite must not be followed by another
        # stylistic rewrite that silently exceeds the agreed budget.
        self._turn_final_audit_revision_used = True
        self._inject_final_answer_audit_repair(
            mode="synthesis",
            reason_codes=["provider_output_truncated"],
        )
        state = getattr(self.context, "analysis_state", None)
        if state is not None:
            try:
                state.append_turn_diagnostic({
                    "event": "provider_output_truncation",
                    "finish_reason": finish_reason,
                    "action": "bounded_synthesis_revision",
                })
            except Exception:
                pass
        return True

    def _remember_round_budget(self, *, phase: str, usage_before: int) -> None:
        """Remember the accepted phase usage of the just-finished LLM round."""

        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            self._turn_last_round_budget = None
            return
        usage_after = int(turn_state.phase_token_usage.get(phase, 0) or 0)
        self._turn_last_round_budget = {
            "phase": str(phase or ""),
            "tokens": max(0, usage_after - max(0, int(usage_before or 0))),
        }

    def _reclassify_discarded_candidate_budget(self, *, reason: str) -> int:
        """Free final-synthesis reserve when a candidate is discarded for more analysis.

        The provider usage remains in ``approximate_runtime_tokens_used``. Only
        phase ownership moves to exploration, so assurance diagnostics remain
        truthful while the final synthesis reserve is not consumed by text the
        runtime deliberately removed from the conversation.
        """

        budget = getattr(self, "_turn_last_round_budget", None)
        turn_state = getattr(self.context, "turn_state", None)
        if not isinstance(budget, dict) or turn_state is None:
            return 0
        phase = str(budget.get("phase") or "")
        tokens = max(0, int(budget.get("tokens") or 0))
        if phase != "synthesis" or tokens <= 0:
            return 0
        moved = turn_state.reclassify_phase_usage(
            tokens,
            source_phase="synthesis",
            target_phase="exploration",
        )
        budget["tokens"] = max(0, tokens - moved)
        if moved:
            self._persist_budget_diagnostics(turn_state)
            state = getattr(self.context, "analysis_state", None)
            append = getattr(state, "append_turn_diagnostic", None)
            if callable(append):
                append({
                    "event": "discarded_candidate_budget_reclassified",
                    "reason": str(reason or ""),
                    "source_phase": "synthesis",
                    "target_phase": "exploration",
                    "tokens": moved,
                })
        return moved

    def _remember_final_answer_candidate(self, text: str, *, reason: str) -> None:
        candidate = str(text or "")
        if not candidate.strip():
            return
        candidates = list(getattr(self, "_turn_final_answer_candidates", []) or [])
        candidates.append({"text": candidate, "reason": str(reason or "")})
        self._turn_final_answer_candidates = candidates[-3:]

    def _final_answer_candidate_score(self, text: str) -> tuple[int, int, int, int]:
        """Return a deterministic structural score; it never judges truth."""

        value = str(text or "")
        compact = "".join(value.split())
        section_groups = (
            ("发现", "结论", "结果"),
            ("建议", "行动", "下一步"),
            ("局限", "限制"),
        )
        section_count = sum(
            any(marker in value for marker in group)
            for group in section_groups
        )
        evidence_markers = value.count("[[evidence:")
        incomplete = bool(self._analysis_answer_incomplete_reasons(value))
        return (
            0 if incomplete else 1,
            section_count,
            evidence_markers,
            min(len(compact), 4_000),
        )

    def _select_best_final_answer_candidate(self, current_text: str) -> str:
        """Keep a prior truncated draft when the single revision is worse."""

        current = str(current_text or "")
        candidates = list(getattr(self, "_turn_final_answer_candidates", []) or [])
        if not candidates or not self._analysis_answer_incomplete_reasons(current):
            return current
        best = max(
            candidates,
            key=lambda item: self._final_answer_candidate_score(str(item.get("text") or "")),
        )
        selected = str(best.get("text") or "")
        if self._final_answer_candidate_score(selected) <= self._final_answer_candidate_score(current):
            return current
        state = getattr(self.context, "analysis_state", None)
        append = getattr(state, "append_turn_diagnostic", None)
        if callable(append):
            append({
                "event": "final_answer_candidate_fallback",
                "selected_reason": str(best.get("reason") or ""),
                "rejected_length": len("".join(current.split())),
                "selected_length": len("".join(selected.split())),
            })
        self._replace_last_answer_candidate(selected)
        return selected

    def _publication_mode(self) -> str:
        from data_agent.config import get_config

        try:
            return str(getattr(get_config(), "assurance_publication_mode", "tiered") or "tiered")
        except Exception:
            return "tiered"

    def _publication_feature_flags(self) -> dict[str, bool]:
        from data_agent.config import get_config

        try:
            cfg = get_config()
        except Exception:
            return {
                "auto_evidence_projection_enabled": True,
                "analysis_live_progress_enabled": True,
            }
        return {
            "auto_evidence_projection_enabled": bool(
                getattr(cfg, "auto_evidence_projection_enabled", True)
            ),
            "analysis_live_progress_enabled": bool(
                getattr(cfg, "analysis_live_progress_enabled", True)
            ),
        }

    def _record_publication_diagnostic(self, publication: Any) -> None:
        state = getattr(self.context, "analysis_state", None)
        if state is None or publication is None:
            return
        try:
            state.append_turn_diagnostic({
                "event": "claim_tier_publication",
                "mode": self._publication_mode(),
                "feature_flags": self._publication_feature_flags(),
                "actions": dict(getattr(publication, "actions", {}) or {}),
            })
        except Exception:
            pass

    def _record_pass_publication_diagnostic(self, audit: dict[str, Any]) -> None:
        """Record a ``claim_tier_publication`` diagnostic on the pass path.

        The pass path publishes ``audit.public_text`` directly without going
        through ``_render_audited_publication`` (every claim passed, so there
        is nothing to downgrade or replace). The publication still happened,
        so we record the per-claim action map (all ``verified``) for
        observability consistency with the fallback and revise paths.
        """

        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return
        actions = {
            str(check.get("claim_id") or ""): "verified"
            for check in audit.get("claim_checks") or []
            if isinstance(check, dict) and check.get("status") == "passed"
        }
        try:
            state.append_turn_diagnostic({
                "event": "claim_tier_publication",
                "mode": self._publication_mode(),
                "feature_flags": self._publication_feature_flags(),
                "actions": actions,
            })
        except Exception:
            pass

    def _render_audited_publication(
        self,
        draft: str,
        audit: dict[str, Any] | None,
    ) -> str:
        """Render a draft answer under claim-tier publication rules.

        Always publishes deterministically — never triggers another analysis
        tool call. When ``audit`` is missing or invalid (audit infrastructure
        failure), every material claim is replaced with a deterministic
        diagnostic; an exploratory disclaimer cannot authorize unaudited
        analytical assertions.
        """

        from data_agent.agent.answer_quality import (
            PublicationResult,
            render_audited_analysis_answer,
        )

        completion = self._evaluate_turn_completion()
        rendered: PublicationResult = render_audited_analysis_answer(
            draft=draft,
            audit=audit if isinstance(audit, dict) else None,
            completion=completion,
            mode=self._publication_mode(),
        )
        self._record_publication_diagnostic(rendered)
        return rendered.text

    def _synthesis_audit_revision_active(self) -> bool:
        return 'mode="synthesis"' in getattr(self, "_turn_final_audit_instruction", "")

    def _reject_synthesis_revision_tool_calls(self, user_input: str = "") -> str:
        draft_text = ""
        if self.messages and self.messages[-1].get("role") == "assistant":
            draft_text = str(self.messages[-1].get("content") or "")
            self.messages.pop()
        audit = getattr(self, "_turn_last_final_audit", None)
        if not isinstance(audit, dict) and getattr(
            self, "_turn_final_answer_candidates", None
        ):
            selected = self._select_best_final_answer_candidate(draft_text)
            gate = self._gate_final_analysis_answer(
                user_input,
                selected,
                allow_repair=False,
            )
            self._turn_final_audit_instruction = ""
            return gate["text"]
        rendered = self._render_audited_publication(
            draft_text, audit if isinstance(audit, dict) else None,
        )
        self._replace_last_answer_candidate(rendered)
        self._turn_final_audit_instruction = ""
        return rendered

    def _gate_final_analysis_answer(
        self,
        user_input: str,
        final_text: str,
        *,
        allow_repair: bool = True,
    ) -> dict[str, str]:
        if not self._is_final_answer_audit_candidate():
            return {"action": "publish", "text": final_text}

        final_text = self._select_best_final_answer_candidate(final_text)
        incomplete_codes = self._analysis_answer_incomplete_reasons(final_text)
        turn_state = getattr(self.context, "turn_state", None)
        if (
            incomplete_codes
            and allow_repair
            and not self._turn_final_audit_revision_used
            and (turn_state is None or turn_state.claim_revision_attempt())
        ):
            self._turn_final_audit_revision_used = True
            self._inject_final_answer_audit_repair(
                mode="synthesis",
                reason_codes=incomplete_codes,
            )
            return {"action": "continue", "mode": "synthesis"}

        from data_agent.agent.trust_workflow_runtime import (
            audit_final_answer_draft,
            hydrate_final_answer_audit_ref,
        )

        state = getattr(self.context, "analysis_state", None)
        if state is None:
            rendered = self._render_audited_publication(final_text, None)
            self._replace_last_answer_candidate(rendered)
            self._turn_final_audit_instruction = ""
            return {"action": "fallback", "text": rendered}

        try:
            ref = audit_final_answer_draft(
                final_text,
                state,
                evidence_aliases=tuple(
                    getattr(self, "_turn_synthesis_evidence_aliases", ()) or ()
                ),
            )
            audit = hydrate_final_answer_audit_ref(ref)
            turn_state = getattr(self.context, "turn_state", None)
            if turn_state is not None:
                turn_state.record_token_usage(1, phase="audit")
                self._persist_budget_diagnostics(turn_state)
        except Exception as exc:
            logger.error(
                "Final answer audit failed closed",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )
            append = getattr(state, "append_turn_diagnostic", None)
            if callable(append):
                append({
                    "event": "final_answer_audit_runtime_failure",
                    "exception_type": type(exc).__name__,
                })
            audit = None
        if not isinstance(audit, dict):
            # Audit failed closed. Publish deterministically via the renderer
            # with a missing audit so every material claim is replaced by a
            # diagnostic. Never trigger another analysis tool call from this
            # path — the renderer is read-only.
            rendered = self._render_audited_publication(final_text, None)
            self._replace_last_answer_candidate(rendered)
            self._turn_final_audit_instruction = ""
            return {"action": "fallback", "text": rendered}

        self._turn_last_final_audit = audit

        status = str(audit.get("status") or "blocked")
        if status == "pass":
            public_text = str(audit.get("public_text") or "")
            incomplete_codes = self._analysis_answer_incomplete_reasons(public_text)
            turn_state = getattr(self.context, "turn_state", None)
            if (
                incomplete_codes
                and allow_repair
                and not self._turn_final_audit_revision_used
                and (turn_state is None or turn_state.claim_revision_attempt())
            ):
                self._turn_final_audit_revision_used = True
                self._inject_final_answer_audit_repair(
                    mode="synthesis",
                    reason_codes=incomplete_codes,
                )
                return {"action": "continue", "mode": "synthesis"}
            # Record the publication diagnostic on the pass path too — the
            # publication still happened, so observability must be consistent
            # with the fallback and revise paths. The published text is the
            # audit's public_text verbatim (every claim passed).
            self._record_pass_publication_diagnostic(audit)
            self._replace_last_answer_candidate(public_text)
            self._turn_final_audit_instruction = ""
            return {"action": "publish", "text": public_text}

        failed_codes = list(dict.fromkeys(
            str(code)
            for check in audit.get("claim_checks") or []
            if isinstance(check, dict) and check.get("status") == "failed"
            for code in check.get("reason_codes") or []
            if str(code)
        ))
        all_codes = list(dict.fromkeys(
            str(code)
            for check in audit.get("claim_checks") or []
            if isinstance(check, dict)
            for code in check.get("reason_codes") or []
            if str(code)
        ))
        evidence_available = bool(getattr(state, "evidence_records", None))
        evidence_aliases_available = bool(
            getattr(self, "_turn_synthesis_evidence_aliases", ()) or ()
        )
        synthesis_repairable = status == "revise" or (
            status == "blocked"
            and evidence_available
            and evidence_aliases_available
            and bool(failed_codes)
            and set(failed_codes) <= {
                "missing_evidence_identity",
                *_SYNTHESIS_MEASUREMENT_REPAIR_CODES,
            }
        )
        if (
            allow_repair
            and synthesis_repairable
            and not self._turn_final_audit_revision_used
            and (
                getattr(self.context, "turn_state", None) is None
                or self.context.turn_state.claim_revision_attempt()
            )
        ):
            self._turn_final_audit_revision_used = True
            self._inject_final_answer_audit_repair(
                mode="synthesis",
                reason_codes=all_codes,
            )
            return {"action": "continue", "mode": "synthesis"}

        failed_code_set = set(failed_codes)
        all_code_set = set(all_codes)
        has_measurement_bookkeeping = bool(
            all_code_set & _MEASUREMENT_BOOKKEEPING_CODES
        )
        needs_computation = (
            not has_measurement_bookkeeping
            and bool(failed_code_set & _COMPUTATION_REPAIR_REASON_CODES)
        )
        if (
            allow_repair
            and needs_computation
            and not self._turn_final_audit_analysis_retry_used
            and self._analysis_retry_budget_available()
        ):
            self._turn_final_audit_analysis_retry_used = True
            self._inject_final_answer_audit_repair(
                mode="analysis",
                reason_codes=failed_codes,
            )
            return {"action": "continue", "mode": "analysis"}

        # One bounded wording revision is already exhausted (or not allowed).
        # Publish deterministically by claim tier: verified findings stay,
        # downgraded claims get the exploratory suffix, fabricated/stale/
        # cross-scope/contradictory/causal-invalid claims are replaced in
        # place with Chinese diagnostics. The whole-answer English fallback
        # must not appear.
        rendered = self._render_audited_publication(final_text, audit)
        self._replace_last_answer_candidate(rendered)
        self._turn_final_audit_instruction = ""
        return {"action": "fallback", "text": rendered}

    def _analysis_answer_incomplete_reasons(self, text: str) -> list[str]:
        """Detect an unfinished analysis response without judging its claims.

        Claim audit answers "is this statement supported?"; it cannot decide
        whether a comprehensive answer exists at all.  This bounded check is
        intentionally structural and intent-aware so a concise directed
        answer is not forced into a long report.
        """

        intent = getattr(self, "_last_turn_intent", None)
        intent_type = str(getattr(intent, "intent_type", "") or "")
        compact = "".join(str(text or "").split())
        process_markers = (
            "现在继续执行",
            "接下来执行",
            "将继续分析",
            "正在继续分析",
            "现在做最后一步",
            "接下来做最后一步",
            "复核完成",
            "图表已生成",
            "continue the analysis",
        )
        section_groups = (
            ("发现", "结论", "结果"),
            ("建议", "行动", "下一步"),
            ("局限", "限制"),
        )
        has_all_sections = all(
            any(marker in text for marker in group)
            for group in section_groups
        )
        reasons: list[str] = []
        if any(marker.casefold() in compact.casefold() for marker in process_markers) and not has_all_sections:
            reasons.append("analysis_answer_incomplete")
        if intent_type == "comprehensive_report":
            if len(compact) < 600:
                reasons.append("analysis_answer_too_short")
            if not has_all_sections:
                reasons.append("analysis_answer_sections_missing")
        return list(dict.fromkeys(reasons))

    def _should_continue_for_analysis_quality(self, user_input: str, final_text: str) -> bool:
        return self._maybe_continue_for_analysis_quality(user_input, final_text) is not None

    def _is_analysis_quality_guard_candidate(self) -> bool:
        """Streaming-round buffer gate.

        Text is buffered only when this turn is still eligible for one
        analysis-quality continuation: the intent is analysis-bearing, the
        guard has not yet been injected, and the per-turn continuation
        budget still has room. The substantive-tool shortcut is gone — a
        missing requirement can still force a recovery round even after a
        successful substantive tool.
        """

        return self._is_analysis_continuation_candidate()

    def _is_analysis_continuation_candidate(self) -> bool:
        if getattr(self, "_turn_final_guard_injected", False):
            return False
        intent = getattr(self, "_last_turn_intent", None)
        if intent is None or intent.intent_type not in ("directed_analysis", "comprehensive_report"):
            return False
        if getattr(intent, "execution_readiness", "") not in ("ready", "pending_load"):
            return False
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return False
        return int(getattr(turn_state, "analysis_continuations_used", 0) or 0) < 1

    def _evaluate_turn_completion(self):
        """Build and run the requirement-based completion evaluator."""

        from data_agent.agent.execution_control import evaluate_analysis_completion

        state = getattr(self.context, "analysis_state", None)
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return None
        plan = getattr(state, "analysis_plan", None) if state is not None else None
        requirements: list[dict[str, Any]] = []
        if state is not None and isinstance(plan, dict) and plan.get("method_plan"):
            try:
                from data_agent.agent.analysis_requirements import compile_analysis_requirements

                requirements = compile_analysis_requirements(
                    plan=plan,
                    **state.analysis_requirement_inputs(plan),
                )
            except Exception as exc:
                logger.warning(
                    "Requirement compilation failed for completion evaluation: %s",
                    exc,
                    extra={"extra_data": {"session_id": self.session_id}},
                )
                requirements = []
        computation_refs = list(getattr(state, "computation_refs", []) or []) if state is not None else []
        evidence_records = list(getattr(state, "evidence_records", []) or []) if state is not None else []
        tool_outcomes = list(getattr(self, "_turn_tool_outcomes", []) or [])
        budget_exhausted = (
            turn_state.tool_calls >= int(turn_state.budget.max_tool_calls or 0)
            or getattr(turn_state, "exploration_budget_exhausted", False)
        )
        try:
            return evaluate_analysis_completion(
                plan=plan if isinstance(plan, dict) else None,
                requirements=requirements,
                computation_refs=computation_refs,
                evidence_records=evidence_records,
                tool_outcomes=tool_outcomes,
                turn_state=turn_state,
                budget_exhausted=budget_exhausted,
            )
        except Exception as exc:
            logger.warning(
                "Completion evaluation failed: %s",
                exc,
                extra={"extra_data": {"session_id": self.session_id}},
            )
            return None

    def _maybe_continue_for_analysis_quality(
        self,
        user_input: str,
        final_text: str,
    ):
        """Return the system message to inject when continuation is allowed.

        Returns ``None`` when the turn should proceed to synthesis.
        Handles two paths:

        1. ``plan_not_started`` — analysis intent, plan not materialized,
           only profiling/meta tools used. Allow one continuation so the
           agent can produce a plan and execute.
        2. ``requirement_based`` — plan exists; the evaluator reports
           ``allow_analysis_continuation=True`` for a recoverable
           requirement. Inject a targeted instruction naming the
           requirement and the allowed capability/fallback.
        """

        if not self._is_analysis_continuation_candidate():
            return None
        turn_state = getattr(self.context, "turn_state", None)
        if turn_state is None:
            return None
        if not turn_state.can_run_phase("synthesis") or not turn_state.can_run_phase("audit"):
            return None

        state = getattr(self.context, "analysis_state", None)
        plan = getattr(state, "analysis_plan", None) if state is not None else None
        tools_used = set(getattr(self, "_turn_tools_used", []))
        if (
            not isinstance(plan, dict) or not plan.get("method_plan")
        ) and tools_used and tools_used <= (_PROFILING_TOOLS | _META_QUALITY_TOOLS):
            if not turn_state.consume_quality_continuation(reason="plan_not_started"):
                return None
            message = _ANALYSIS_QUALITY_GUARD_MESSAGE
            self._record_completion_diagnostic(
                status="complete_with_limits",
                reason_code="plan_not_started",
                unmet_requirement_ids=(),
                recoverable_requirement_ids=(),
                supported_claim_class="exploratory_association",
            )
            self._inject_analysis_quality_guard(message)
            return message

        decision = self._evaluate_turn_completion()
        if decision is None or not decision.allow_analysis_continuation:
            if decision is not None:
                self._record_completion_diagnostic(
                    status=decision.status,
                    reason_code=decision.reason_code,
                    unmet_requirement_ids=decision.unmet_requirement_ids,
                    recoverable_requirement_ids=decision.recoverable_requirement_ids,
                    supported_claim_class=decision.supported_claim_class,
                )
            return None
        if not turn_state.consume_quality_continuation(reason=decision.reason_code):
            self._record_completion_diagnostic(
                status=decision.status,
                reason_code=decision.reason_code,
                unmet_requirement_ids=decision.unmet_requirement_ids,
                recoverable_requirement_ids=decision.recoverable_requirement_ids,
                supported_claim_class=decision.supported_claim_class,
            )
            return None
        missing = ", ".join(decision.recoverable_requirement_ids) or "current_missing_requirement"
        message = _ANALYSIS_QUALITY_CONTINUATION_TEMPLATE.format(
            status=decision.status,
            reason=decision.reason_code,
            missing=missing,
            capability_hint=_capability_hint_for_unmet(decision, plan=plan),
        )
        self._record_completion_diagnostic(
            status=decision.status,
            reason_code=decision.reason_code,
            unmet_requirement_ids=decision.unmet_requirement_ids,
            recoverable_requirement_ids=decision.recoverable_requirement_ids,
            supported_claim_class=decision.supported_claim_class,
        )
        self._inject_analysis_quality_guard(message)
        return message

    def _record_completion_diagnostic(
        self,
        *,
        status: str,
        reason_code: str,
        unmet_requirement_ids,
        recoverable_requirement_ids,
        supported_claim_class: str,
    ) -> None:
        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return
        try:
            state.append_turn_diagnostic({
                "event": "completion_decision",
                "status": str(status or ""),
                "reason_code": str(reason_code or ""),
                "unmet_requirement_ids": [str(item) for item in (unmet_requirement_ids or ())],
                "recoverable_requirement_ids": [
                    str(item) for item in (recoverable_requirement_ids or ())
                ],
                "supported_claim_class": str(supported_claim_class or ""),
            })
        except Exception:
            pass

    def _inject_analysis_quality_guard(self, message: str | None = None) -> None:
        self._turn_final_guard_injected = True
        if self.messages:
            last_msg = self.messages[-1]
            if last_msg.get("role") == "assistant" and not last_msg.get("tool_calls"):
                self.messages.pop()
        self.messages.append({
            "role": "system",
            "content": message or _ANALYSIS_QUALITY_GUARD_MESSAGE,
        })

    def _last_external_user_message(self) -> str:
        for msg in reversed(self.messages):
            if msg.get("role") != "user":
                continue
            content = str(msg.get("content") or "")
            stripped = content.lstrip()
            if stripped.startswith("<confirmation_response") or stripped.startswith("<analysis_quality_guard"):
                continue
            return content
        return ""

    def _build_resume_user_input(self, susp: SuspendedForConfirmation, answer: str) -> str:
        original = self._last_external_user_message()
        confirmation = (
            f"Question: {susp.question}\n"
            f"User answered: {answer}"
        )
        if original:
            return f"{original}\n\n{confirmation}"
        return confirmation

    def _confirmation_runtime(self):
        from data_agent.agent.confirmation.runtime import build_action_registry
        from data_agent.agent.confirmation.service import ConfirmationService

        sessions_root = get_config().sessions_resolved
        cached = getattr(self, "_confirmation_service", None)
        cached_root = getattr(self, "_confirmation_service_root", None)
        if cached is None or cached_root != sessions_root:
            cached = ConfirmationService(
                sessions_root,
                action_registry=build_action_registry(),
            )
            self._confirmation_service = cached
            self._confirmation_service_root = sessions_root
        return cached

    def _suspend_for_confirmation_request(
        self,
        request: UserConfirmationRequired,
        *,
        turn_id: str,
    ) -> SuspendedForConfirmation:
        from data_agent.agent.confirmation.models import ConfirmationStatus
        from data_agent.agent.confirmation.runtime import (
            build_direct_question_candidate,
            confirmation_record_to_loop_result,
        )

        service = self._confirmation_runtime()
        candidate = build_direct_question_candidate(
            session_id=self.session_id,
            turn_id=turn_id,
            message_version=len(self.messages),
            request=request,
        )
        request_result = service.request(candidate)
        record = request_result.record
        if record is None and request_result.reused_confirmation_id:
            record = service.get(self.session_id, request_result.reused_confirmation_id)
        if record is None:
            raise RuntimeError(
                f"confirmation request was not created: {request_result.reason}"
            )

        checkpoint = service.checkpoint(self.session_id)
        if checkpoint is not None and checkpoint.confirmation_id == record.confirmation_id:
            record = checkpoint
        elif record.status == ConfirmationStatus.PENDING:
            record = service.get(self.session_id, record.confirmation_id)
            if record.status == ConfirmationStatus.PENDING:
                raise RuntimeError(
                    f"confirmation {record.confirmation_id} was not suspended"
                )

        return confirmation_record_to_loop_result(
            record,
            {"messages": self._serialize_messages()},
        )

    def _suspend_for_required_question_payload(
        self,
        payload: dict[str, Any],
        *,
        source: str,
        operation: str,
    ) -> SuspendedForConfirmation:
        from data_agent.agent.confirmation.models import ConfirmationStatus
        from data_agent.agent.confirmation.runtime import (
            build_required_question_candidate,
            confirmation_record_to_loop_result,
        )

        service = self._confirmation_runtime()
        candidate = build_required_question_candidate(
            session_id=self.session_id,
            turn_id=str(payload.get("confirmation_type") or operation or "auto_required_question"),
            message_version=len(self.messages),
            request=payload,
            source=source,
            operation=operation or "auto_required_question",
        )
        request_result = service.request(candidate)
        record = request_result.record
        if record is None and request_result.reused_confirmation_id:
            record = service.get(self.session_id, request_result.reused_confirmation_id)
        if record is None:
            raise RuntimeError(
                f"confirmation request was not created: {request_result.reason}"
            )

        checkpoint = service.checkpoint(self.session_id)
        if checkpoint is not None and checkpoint.confirmation_id == record.confirmation_id:
            record = checkpoint
        elif record.status == ConfirmationStatus.PENDING:
            record = service.get(self.session_id, record.confirmation_id)
            if record.status == ConfirmationStatus.PENDING:
                raise RuntimeError(
                    f"confirmation {record.confirmation_id} was not suspended"
                )

        return confirmation_record_to_loop_result(
            record,
            {"messages": self._serialize_messages()},
        )

    def _runtime_confirmation_checkpoint(self) -> SuspendedForConfirmation | None:
        from data_agent.agent.confirmation.runtime import confirmation_record_to_loop_result

        record = self._confirmation_runtime().checkpoint(self.session_id)
        if record is None:
            return None
        return confirmation_record_to_loop_result(
            record,
            {"messages": self._serialize_messages()},
        )

    def _suspended_event(self, susp: SuspendedForConfirmation) -> dict[str, Any]:
        confirmation_id = susp.confirmation_id or susp.suspension_id
        return {
            "type": "suspended",
            "confirmation_id": confirmation_id,
            "suspension_id": confirmation_id,
            "version": susp.version,
            "question": susp.question,
            "options": susp.options,
            "context": susp.context,
            "multi_select": susp.multi_select,
            "allow_free_text": susp.allow_free_text,
            "confirmation_type": susp.confirmation_type,
            "blocking_reason": susp.blocking_reason,
            "related_task_id": susp.related_task_id,
            "related_spec_id": susp.related_spec_id,
        }

    def _runtime_suspension_for_resume(
        self,
        confirmation_id: str,
    ) -> SuspendedForConfirmation | None:
        from data_agent.agent.confirmation.runtime import confirmation_record_to_loop_result
        from data_agent.agent.confirmation_policy import is_obsolete_confirmation_record

        try:
            record = self._confirmation_runtime().get(self.session_id, confirmation_id)
        except KeyError:
            return None
        if is_obsolete_confirmation_record(record):
            return None
        return confirmation_record_to_loop_result(
            record,
            {"messages": self._serialize_messages()},
        )

    def _load_confirmation_for_resume(
        self,
        confirmation_id: str,
    ) -> SuspendedForConfirmation | None:
        return self._runtime_suspension_for_resume(confirmation_id)

    def _resolve_runtime_confirmation(
        self,
        susp: SuspendedForConfirmation,
        user_response: str,
        *,
        expected_version: int | None = None,
        idempotency_key: str = "",
    ) -> SuspendedForConfirmation:
        from data_agent.agent.confirmation.runtime import confirmation_record_to_loop_result

        confirmation_id = susp.confirmation_id or susp.suspension_id
        service = self._confirmation_runtime()
        record = service.get(self.session_id, confirmation_id)
        version = int(expected_version or record.version)
        idempotency_key = str(idempotency_key or "").strip()
        response_text = str(user_response or "").strip()
        lowered = response_text.lower()

        if lowered == "skipped":
            operation = "skip"
            answer: Any = "skipped"
            resolved = service.skip(
                self.session_id,
                confirmation_id,
                version,
                idempotency_key,
            )
        elif lowered == "cancelled":
            operation = "cancel"
            answer = "cancelled"
            resolved = service.cancel(
                self.session_id,
                confirmation_id,
                version,
                idempotency_key,
            )
        else:
            operation = "answer"
            answer = self._normalise_runtime_answer(record, user_response)
            resolved = service.respond(
                self.session_id,
                confirmation_id,
                answer,
                version,
                idempotency_key,
            )

        if (
            resolved.resolution_action == "approve_dataset_transformation"
            and resolved.response == "approve"
        ):
            from data_agent.tools.data_clean import apply_confirmed_transformation

            apply_confirmed_transformation(
                resolved.confirmation_id,
                session_id=self.session_id,
            )
            self._prompt_cache_dirty = True

        return confirmation_record_to_loop_result(
            resolved,
            {"messages": self._serialize_messages()},
        )

    @staticmethod
    def _normalise_runtime_answer(record: Any, user_response: Any) -> Any:
        from data_agent.agent.confirmation.models import AnswerMode

        if record.answer_mode == AnswerMode.MULTI_SELECT:
            if isinstance(user_response, (list, tuple)):
                return [str(value).strip() for value in user_response if str(value).strip()]
            return [
                part.strip()
                for part in str(user_response or "").split(",")
                if part.strip()
            ]
        return str(user_response or "").strip()

    @staticmethod
    def _confirmation_response_key(
        confirmation_id: str,
        operation: str,
        answer: Any,
    ) -> str:
        import hashlib

        payload = json.dumps(
            {
                "confirmation_id": confirmation_id,
                "operation": operation,
                "answer": answer,
            },
            default=str,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"loop_resume:{hashlib.sha256(payload).hexdigest()}"

    def run_turn(self, user_input: str) -> str:
        """处理一轮用户输入，返回回复文本。CLI 模式使用。"""
        logger.info("Turn started", extra={"extra_data": {"session": self.session_id}})
        self._interrupt_event.clear()
        self._quality_reminder_injected = False
        self._reset_turn_tracking()
        # Inject interrupt context if previous turn was interrupted
        if self._was_last_turn_interrupted():
            context = self._build_interrupt_context(user_input)
            self.messages.append({"role": "user", "content": context})
        self.messages.append({"role": "user", "content": user_input})
        self._prompt_cache_dirty = True
        # 根据用户输入激活相关工具分组
        with self.__context_operation("use"):
            new_groups = self._prepare_analysis_turn(user_input)
            required_question = self._maybe_auto_suspend_for_required_question()
        if new_groups:
            logger.info("Activated tool groups", extra={"extra_data": {"groups": list(new_groups)}})
        if required_question is not None:
            reply = self._handle_cli_suspension(required_question)
            self._maybe_archive(user_input, reply)
            self._auto_save()
            logger.info("Turn completed (with auto confirmation)", extra={"extra_data": {"session": self.session_id}})
            return reply
        try:
            result = self._loop(user_input)
        except Exception as e:
            # 原子性保证：即使失败也写入 assistant 消息，避免连续 user 消息
            import traceback
            tb = traceback.format_exc()
            error_msg = f"⚠ 分析中断：{type(e).__name__}: {e}"
            self.messages.append({"role": "assistant", "content": error_msg})
            self._auto_save()
            logger.error("Turn failed", extra={"extra_data": {"error": str(e), "traceback": tb}})
            return error_msg
        if result is None:
            # _loop 耗尽最大轮次返回 None
            fallback = "达到最大轮次限制。"
            self.messages.append({"role": "assistant", "content": fallback})
            self._auto_save()
            return fallback
        if isinstance(result, SuspendedForConfirmation):
            # CLI mode: handle suspension inline by prompting user
            reply = self._handle_cli_suspension(result)
            self._maybe_archive(user_input, reply)
            self._auto_save()
            logger.info("Turn completed (with confirmation)", extra={"extra_data": {"session": self.session_id}})
            return reply
        reply = result.content
        self._maybe_archive(user_input, reply)
        self._auto_save()
        logger.info("Turn completed", extra={"extra_data": {"session": self.session_id}})
        return reply

    def run_turn_structured(self, user_input: str) -> LoopResult:
        """处理一轮用户输入，返回 LoopResult。Web 模式使用。"""
        logger.info("Turn started (structured)", extra={"extra_data": {"session": self.session_id}})
        self._interrupt_event.clear()
        self._quality_reminder_injected = False
        self._reset_turn_tracking()
        self.messages.append({"role": "user", "content": user_input})
        self._prompt_cache_dirty = True
        with self.__context_operation("use"):
            self._prepare_analysis_turn(user_input)
            required_question = self._maybe_auto_suspend_for_required_question()
        if required_question is not None:
            return required_question
        try:
            result = self._loop(user_input)
        except Exception as e:
            error_msg = f"⚠ 分析中断：{type(e).__name__}: {e}"
            self.messages.append({"role": "assistant", "content": error_msg})
            self._auto_save()
            return FinalResponse(content=error_msg)
        if result is None:
            fallback = "达到最大轮次限制。"
            self.messages.append({"role": "assistant", "content": fallback})
            self._auto_save()
            return FinalResponse(content=fallback)
        if isinstance(result, FinalResponse):
            self._maybe_archive(user_input, result.content)
            self._auto_save()
            logger.info("Turn completed (structured)", extra={"extra_data": {"session": self.session_id}})
        return result

    def _auto_save(self) -> None:
        """自动保存会话状态。增量推送新消息到 JSONL + 全量保存。"""
        with self.__context_operation("use"):
            if self.context.analysis_state is not None:
                try:
                    self.context.analysis_state.save()
                except Exception:
                    pass
            from data_agent.session.history import save_session, push_messages
            # 增量推送上次保存后新增的消息
            new_msgs = self.messages[self._last_jsonl_idx:]
            if new_msgs:
                push_messages(self.session_id, new_msgs)
                self._last_jsonl_idx = len(self.messages)
            # 全量保存（会合并 JSONL 并清空）
            save_session(
                self.messages,
                self.session_id,
                data_file=self._last_data_file,
                extra_meta=self._build_session_meta(),
            )

    def _stream_checkpoint(self) -> None:
        """Persist newly appended messages while a Web turn is still running."""

        with self.__context_operation("use"):
            from data_agent.session.history import checkpoint_session

            checkpoint_session(
                self.messages,
                self.session_id,
                start_index=self._last_jsonl_idx,
                data_file=self._last_data_file,
                extra_meta=self._build_session_meta(),
            )
            self._last_jsonl_idx = len(self.messages)

    def _build_session_meta(self) -> dict:
        """构建丰富的 session 元数据。"""
        from data_agent.session.workspace import workspace

        datasets = workspace.list_datasets()
        loaded_skills = []
        if self._skill_loader and self._skill_loader.list_loaded():
            loaded_skills = [s.name for s in self._skill_loader.list_loaded()]

        return {
            "project_name": self.context.project_name,
            "datasets": {
                name: {"rows": info["rows"], "columns": info["columns"]}
                for name, info in datasets.items()
            },
            "loaded_skills": loaded_skills,
            "message_count": len(self.messages),
        }

    def resume_turn(
        self,
        suspension_id: str,
        user_response: str,
        *,
        expected_version: int | None = None,
        idempotency_key: str = "",
    ) -> LoopResult:
        """Resume after user answers a suspended question. Web mode."""
        susp = self._load_confirmation_for_resume(suspension_id)
        if not susp:
            return FinalResponse(content=f"Error: runtime confirmation {suspension_id} not found")
        try:
            susp = self._resolve_runtime_confirmation(
                susp,
                user_response,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            return FinalResponse(content=f"Error: {exc}")
        resumed_input = self._build_resume_user_input(susp, user_response)
        confirmation_id = susp.confirmation_id or susp.suspension_id
        self._turn_resumed_from_confirmation = True

        self.messages.append({"role": "user", "content": (
            f"<confirmation_response confirmation_id=\"{confirmation_id}\" suspension_id=\"{confirmation_id}\" version=\"{susp.version}\">\n"
            f"Question: {susp.question}\n"
            f"User answered: {user_response}\n"
            f"</confirmation_response>"
        )})
        result = self._loop(resumed_input)
        if isinstance(result, FinalResponse):
            self._maybe_archive("", result.content)
        return result

    def _handle_cli_suspension(self, susp: SuspendedForConfirmation) -> str:
        """Handle a suspension in CLI mode by prompting the user directly.

        Pauses CLI output before displaying the question so it's not overwritten.
        Loops to handle multiple consecutive suspensions.
        """
        from data_agent.tools.interaction import _ask_multiple, _ask_single

        while True:
            if self.cli_pauser:
                self.cli_pauser.pause()

            parsed_questions = []
            if susp.context:
                try:
                    parsed = json.loads(susp.context)
                    if isinstance(parsed, list) and parsed and all(isinstance(q, dict) for q in parsed):
                        parsed_questions = parsed
                except json.JSONDecodeError:
                    parsed_questions = []

            if parsed_questions:
                result = _ask_multiple(parsed_questions)
            else:
                result = _ask_single(
                    question_text=susp.question,
                    options=susp.options,
                    multi_select=susp.multi_select,
                )

            if self.cli_pauser:
                self.cli_pauser.resume()

            if parsed_questions:
                answers = result.get("answers", [])
                answer = "; ".join(
                    f"Q{i + 1}: {item.get('question', '')} => {item.get('answer', 'skipped')}"
                    for i, item in enumerate(answers)
                ) or "skipped"
            else:
                answer = result.get("answer", "cancelled")
            self._resolve_confirmation(susp, answer)
            resumed_input = self._build_resume_user_input(susp, answer)
            self._turn_resumed_from_confirmation = True

            self.messages.append({"role": "user", "content": (
                f"<confirmation_response suspension_id=\"{susp.suspension_id}\">\n"
                f"Question: {susp.question}\n"
                f"User answered: {answer}\n"
                f"</confirmation_response>"
            )})

            loop_result = self._loop(resumed_input)

            if isinstance(loop_result, FinalResponse):
                return loop_result.content
            elif isinstance(loop_result, SuspendedForConfirmation):
                # Another suspension — loop again
                susp = loop_result
                continue
            else:
                # None (max rounds) or unexpected
                return loop_result.content if hasattr(loop_result, "content") else "达到最大轮次限制。"

    def _register_confirmation(self, susp: SuspendedForConfirmation) -> None:
        with self.__context_operation("use"):
            try:
                from data_agent.agent.analysis_state import current_analysis_state
                state = current_analysis_state()
                if state is None:
                    return
                state.add_confirmation({
                    "id": susp.suspension_id,
                    "suspension_id": susp.suspension_id,
                    "question": susp.question,
                    "options": susp.options,
                    "context": susp.context,
                    "confirmation_type": susp.confirmation_type,
                    "blocking_reason": susp.blocking_reason,
                    "state_updates": susp.state_updates,
                    "related_task_id": susp.related_task_id,
                    "related_spec_id": susp.related_spec_id,
                })
                state.save()
            except Exception as e:
                logger.warning("Failed to register confirmation", extra={"extra_data": {"error": str(e)}})

    def _resolve_confirmation(self, susp: SuspendedForConfirmation, answer: str) -> None:
        with self.__context_operation("use"):
            try:
                from data_agent.agent.analysis_state import current_analysis_state
                state = current_analysis_state()
                if state is not None:
                    state.resolve_confirmation(susp.suspension_id, answer)
                    state.save()
                if susp.related_task_id:
                    from data_agent.session.task_manager import task_manager
                    task_manager.update(
                        susp.related_task_id,
                        confirmation_ids=[susp.suspension_id],
                        result_summary=f"用户确认: {answer}",
                    )
            except Exception as e:
                logger.warning("Failed to resolve confirmation", extra={"extra_data": {"error": str(e)}})

    def _stream_llm_round(self, round_num: int):
        """Execute one LLM round using streaming. Yields SSE event dicts.

        Text deltas are yielded in real-time. When the round completes, the
        final Response is returned via a ``{"type": "_response", ...}`` event
        so the caller can decide what to do next.
        """
        from data_agent.llm.client import StreamTextDelta, StreamComplete

        yield {"type": "llm_call_start", "round": round_num}

        response = None
        streamed_text = ""
        streamed_tokens = 0
        used_sync_fallback = False
        stream_requested_limit = 0
        phase = self._current_prompt_phase()
        turn_state = getattr(self.context, "turn_state", None)
        phase_usage_before = (
            int(turn_state.phase_token_usage.get(phase, 0) or 0)
            if turn_state is not None
            else 0
        )

        # Defensive: repair any broken tool_call sequences from prior turns
        self._repair_broken_tool_sequence()

        try:
            system_prompt = self._get_system_prompt()
            output_limit = self._llm_output_limit_kwargs(
                self.client.stream_chat_structured,
                phase=phase,
            )
            turn_state = getattr(self.context, "turn_state", None)
            if turn_state is not None:
                stream_requested_limit = int(
                    turn_state.requested_max_output_tokens.get(phase, 0) or 0
                )
            for ev in self.client.stream_chat_structured(
                messages=self.messages,
                tools=registry.active_definitions() or None,
                system=system_prompt,
                **output_limit,
            ):
                # Check interrupt between streaming chunks
                if self._interrupt_event.is_set():
                    yield {"type": "_response", "response": response, "streamed_text": streamed_text}
                    return

                if isinstance(ev, StreamTextDelta):
                    streamed_text += ev.text
                    streamed_tokens += self._record_stream_delta_budget(
                        ev.text,
                        phase=phase,
                    )
                    yield {"type": "text_delta", "text": ev.text, "turn_id": None}
                elif isinstance(ev, StreamComplete):
                    response = ev.response
        except Exception as e:
            unreported = getattr(e, "unreported_output_tokens", None)
            if unreported is None:
                unreported = max(0, stream_requested_limit - streamed_tokens)
            turn_state = getattr(self.context, "turn_state", None)
            if turn_state is not None and int(unreported or 0) > 0:
                turn_state.record_token_usage(int(unreported), phase=phase)
                self._persist_budget_diagnostics(turn_state)
            logger.warning("Streaming LLM call failed, falling back to sync", extra={"extra_data": {"error": str(e)}})
            # Fallback to synchronous call on streaming failure
            try:
                system_prompt = self._get_system_prompt()
                output_limit = self._llm_output_limit_kwargs(
                    self.client.chat,
                    phase=phase,
                )
                response = self.client.chat(
                    messages=self.messages,
                    tools=registry.active_definitions() or None,
                    system=system_prompt,
                    **output_limit,
                )
                used_sync_fallback = True
                # Emit any text that wasn't streamed yet
                new_text = (response.text or "")[len(streamed_text):]
                if new_text:
                    yield {"type": "text_delta", "text": new_text, "turn_id": None}
                    streamed_text += new_text
            except Exception as fallback_err:
                yield {"type": "_response", "response": None, "streamed_text": streamed_text}
                return

        # Internal event — caller uses this to continue the loop
        self._record_llm_response_budget(
            response,
            phase=phase,
            pre_recorded_tokens=(0 if used_sync_fallback else streamed_tokens),
        )
        self._reclassify_synthesis_tool_round_budget(
            response,
            phase=phase,
            phase_usage_before=phase_usage_before,
        )
        self._remember_round_budget(
            phase=phase,
            usage_before=phase_usage_before,
        )
        yield {"type": "_response", "response": response, "streamed_text": streamed_text}

    def _process_tool_calls(
        self,
        response,
        round_num: int,
        _scope_guard=_protected_scope_guard,
    ):
        """Process tool calls from an LLM response. Yields SSE event dicts."""
        import time

        for i, tc in enumerate(response.tool_calls):
            self.__context_operation("refresh")
            # Check interrupt between tool calls
            if self._interrupt_event.is_set():
                self._fill_remaining_tool_responses(response.tool_calls, i, "Turn interrupted by user")
                return
            logger.info("Stream tool call", extra={"extra_data": {"tool": tc.name}})
            registry.expand_from_tool_call(tc.name)
            turn_state = getattr(self.context, "turn_state", None)
            if self._is_tool_blocked_by_confirmation(tc.name):
                blocked = self._blocked_tool_message(tc.name)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": blocked, "error_type": "confirmation_required"}, ensure_ascii=False),
                })
                self._fill_remaining_tool_responses(response.tool_calls, i + 1, "Turn blocked by confirmation")
                yield {"type": "error", "message": blocked}
                return
            if turn_state is not None:
                try:
                    turn_state.ensure_can_call(tc.name, tc.arguments)
                except BudgetExceeded as exc:
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({"error": str(exc), "error_type": "budget_exceeded"}, ensure_ascii=False),
                    })
                    self._fill_remaining_tool_responses(response.tool_calls, i + 1, str(exc))
                    yield {"type": "error", "message": str(exc)}
                    return
                turn_state.record_tool_call(tc.name, tc.arguments)
            yield {
                "type": "tool_call",
                "tool_call_id": tc.id,
                "name": tc.name,
                "arguments": tc.arguments,
                "round": round_num,
            }
            # Bind the call to its plan step BEFORE execution so a
            # substantive analytical tool can narrate its step-specific
            # method (e.g. ``正在评估变量关系``) ahead of the generic
            # ``正在运行分析工具``. Compute once and reuse for compaction.
            step_binding = self._bind_tool_call(tc)
            analysis_run_binding = self._analysis_run_binding(step_binding)
            if step_binding is not None and step_binding.ok and step_binding.step_id:
                yield from self._emit_progress_stream(
                    "analysis_step_started", step_id=step_binding.step_id
                )
            # Server-authored "tool starting" progress event. Closed
            # vocabulary — the tool name is NOT in the payload, only the
            # generic narration label.
            yield from self._emit_progress_stream("tool_started")

            scope_error = _scope_guard(self, tc.name, tc.arguments)
            if scope_error:
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
                self._record_turn_tool_result(tc.name, scope_error)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": scope_error,
                })
                yield {"type": "error", "message": scope_error}
                continue

            t0 = time.monotonic()
            try:
                with self.__context_operation("use"):
                    tool_result = registry.execute(tc.name, tc.arguments)
                post_scope = self.__context_operation("refresh")
                committed_outcome = committed_tool_outcome(tool_result, post_scope)
            except UserConfirmationRequired as ucc:
                susp = self._suspend_for_confirmation_request(
                    ucc,
                    turn_id=str(getattr(tc, "id", "") or "direct_user_question"),
                )
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Suspended for user confirmation. confirmation_id={susp.confirmation_id or susp.suspension_id}",
                })
                self._fill_remaining_tool_responses(response.tool_calls, i + 1, "Suspended for user confirmation")
                yield self._suspended_event(susp)
                return  # stop processing further tool calls

            duration_ms = int((time.monotonic() - t0) * 1000)
            tool_msg_content = self._compact_tool_output(tool_result, tc, step_binding)
            tool_failed = self._tool_content_is_error(tool_msg_content)

            if tool_failed:
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, tool_msg_content)
                tool_msg_content = registry.format_result(tc.name, tool_result)

            else:
                committed_outcome = self._persist_analysis_run_outcome(
                    tc, analysis_run_binding, committed_outcome
                )
                tool_msg_content = render_committed_tool_content(
                    tool_msg_content, committed_outcome
                )
                if turn_state is not None:
                    turn_state.record_tool_success(
                        tc.name,
                        fallback_resolution=self._fallback_resolution_for_tool_call(tc),
                    )

            self._record_turn_tool_result(tc.name, tool_msg_content)
            self._auto_track_task_progress(tc.name, not tool_failed)

            # Phase 3: check for stage regression after tool execution
            if self.context.analysis_state is not None:
                fc = getattr(self, '_flow_controller', None)
                if fc is not None:
                    regression_msg = fc.check_tool_regression(
                        self.context.analysis_state, tc.name, tool_msg_content,
                    )
                if regression_msg:
                    self.messages.append({
                        "role": "system",
                        "content": f"[分析流程回退] {regression_msg}",
                    })

            self.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_msg_content,
            })

            yield {
                "type": "tool_result",
                "tool_call_id": tc.id,
                "name": tc.name,
                "web": tool_result.to_web(),
                "duration_ms": duration_ms,
            }
            # Server-authored "tool finished" progress event fires only on a
            # successful tool execution; errors already surface via the
            # ``error`` SSE event and must not be repackaged as progress.
            if not tool_failed:
                yield from self._emit_progress_stream("tool_succeeded", status="completed")

    def _stream_turn_impl(self, user_input: str):
        """Generator variant of run_turn for SSE streaming. Yields event dicts."""
        import time

        logger.info("Stream turn started", extra={"extra_data": {"session": self.session_id}})
        self._interrupt_event.clear()
        self._quality_reminder_injected = False
        self._reset_turn_tracking()
        # Inject interrupt context if previous turn was interrupted
        if self._was_last_turn_interrupted():
            context = self._build_interrupt_context(user_input)
            self.messages.append({"role": "user", "content": context})
        self.messages.append({"role": "user", "content": user_input})
        self._prompt_cache_dirty = True
        self._prepare_analysis_turn(user_input)
        required_question = self._maybe_auto_suspend_for_required_question()
        if required_question is not None:
            yield {
                "type": "suspended",
                "suspension_id": required_question.suspension_id,
                "confirmation_id": required_question.confirmation_id or required_question.suspension_id,
                "version": required_question.version,
                "question": required_question.question,
                "options": required_question.options,
                "context": required_question.context,
                "multi_select": required_question.multi_select,
                "allow_free_text": required_question.allow_free_text,
                "confirmation_type": required_question.confirmation_type,
                "blocking_reason": required_question.blocking_reason,
                "related_task_id": required_question.related_task_id,
                "related_spec_id": required_question.related_spec_id,
            }
            return

        # Envelope ready: emit a single server-authored plan-ready progress
        # event before any LLM round fires. This is the earliest progress
        # signal the user sees and is guaranteed to precede any streamed or
        # buffered final-answer text.
        yield from self._emit_progress_stream("analysis_plan_ready", status="completed")

        final_text = ""
        round_num = 0
        self._ensure_mcp_initialized()

        while True:
            round_num += 1

            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

            # Safety valve: force summary at high round count
            if round_num == 300:
                self.messages.append({"role": "user", "content": (
                    "分析已进行超过 300 轮工具调用。请立即停止调用工具，"
                    "基于已获得的所有数据和分析结果输出总结报告。"
                )})

            self._compact_context_if_needed()

            blocked_confirmation = self._runtime_confirmation_checkpoint()
            if blocked_confirmation is not None:
                yield self._suspended_event(blocked_confirmation)
                return

            self._enter_synthesis_reserve_if_needed(user_input)

            buffer_text_events = (
                self._is_analysis_quality_guard_candidate()
                or self._should_buffer_final_answer_text()
            )
            pending_text_events = []

            # Inject paragraph separator between streaming rounds
            if round_num > 1:
                separator_event = {"type": "text_delta", "text": "\n\n"}
                if buffer_text_events:
                    pending_text_events.append(separator_event)
                else:
                    yield separator_event

            response = None
            streamed_text = ""
            for ev in self._stream_llm_round(round_num):
                if ev["type"] == "_response":
                    response = ev["response"]
                    streamed_text = ev["streamed_text"]
                elif ev["type"] == "text_delta":
                    if buffer_text_events:
                        pending_text_events.append(ev)
                    else:
                        yield ev
                else:
                    yield ev

            # Check interrupt after streaming round
            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

            if response is None:
                yield {"type": "error", "message": "LLM 返回为空"}
                return

            response_text = response.text or ""
            if response.has_tool_calls and self._is_final_answer_audit_candidate():
                response_text = self._public_intermediate_text(response_text)
            assistant_msg: dict = {"role": "assistant", "content": response_text}
            if response.reasoning_content:
                assistant_msg["reasoning_content"] = response.reasoning_content
            if response_text:
                final_text = response_text

            if response.has_tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]

            self.messages.append(assistant_msg)

            if response.has_tool_calls and self._synthesis_audit_revision_active():
                final_text = self._reject_synthesis_revision_tool_calls(user_input)
                if final_text:
                    yield {"type": "text_delta", "text": final_text, "turn_id": None}
                self._maybe_archive(user_input, final_text)
                self._auto_save()
                return

            if not response.has_tool_calls:
                self._maybe_inject_synthesis_policy(user_input)
                if self._should_continue_for_analysis_quality(user_input, final_text):
                    self._reclassify_discarded_candidate_budget(
                        reason="analysis_quality_continuation",
                    )
                    continue
                if self._maybe_repair_truncated_analysis_response(response):
                    yield from self._emit_progress_stream("tool_recovery")
                    continue
                # The requirement-based completion evaluator ran inside
                # ``_should_continue_for_analysis_quality``; emit the
                # resulting progress signal before any final-answer gate so
                # the user sees "整理可支持的结论" before audit/publication.
                yield from self._emit_progress_stream("completion_evaluated")
                blocked_confirmation = self._runtime_confirmation_checkpoint()
                if blocked_confirmation is not None:
                    yield self._suspended_event(blocked_confirmation)
                    return
                if self._is_final_answer_audit_candidate():
                    yield from self._emit_progress_stream("audit_started")
                    gate = self._gate_final_analysis_answer(user_input, final_text)
                    if gate["action"] == "continue":
                        # Audit-driven bounded recovery (synthesis or analysis
                        # revision). Emit the recovery signal before the next
                        # round so the user knows the agent is retrying within
                        # the agreed bounds — never leaking the rejected draft.
                        yield from self._emit_progress_stream("tool_recovery")
                        continue
                    final_text = gate["text"]
                    if final_text:
                        yield {"type": "text_delta", "text": final_text, "turn_id": None}
                elif buffer_text_events:
                    for ev in pending_text_events:
                        yield ev
                self._maybe_archive(user_input, final_text)
                self._auto_save()
                return

            if buffer_text_events:
                if not self._is_final_answer_audit_candidate():
                    for ev in pending_text_events:
                        yield ev

            # Budget-based quality reminder injection
            self._maybe_inject_quality_reminder()

            # Process tool calls
            suspended = False
            for ev in self._process_tool_calls(response, round_num):
                yield ev
                if ev["type"] == "suspended":
                    suspended = True
            if suspended:
                return

            self._maybe_replan_after_data_load(user_input)
            self._maybe_inject_synthesis_policy(user_input)

            # Check interrupt after tool calls
            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

            # Safety valve: hard stop at 310 rounds
            if round_num >= 310:
                logger.warning("Safety valve triggered", extra={"extra_data": {
                    "session": self.session_id, "rounds": round_num,
                }})
                bounded_text = final_text or "分析已完成。（已达到安全轮次上限）"
                yield from self._emit_progress_stream("completion_evaluated")
                yield from self._emit_progress_stream("audit_started")
                gate = self._gate_final_analysis_answer(
                    user_input,
                    bounded_text,
                    allow_repair=False,
                )
                final_text = gate["text"]
                if final_text:
                    yield {"type": "text_delta", "text": final_text, "turn_id": None}
                self._maybe_archive(user_input, final_text)
                self._auto_save()
                return

    def _resume_turn_streaming_impl(
        self,
        suspension_id: str,
        user_response: str,
        *,
        expected_version: int | None = None,
        idempotency_key: str = "",
    ):
        """Generator variant of resume_turn for SSE streaming."""
        susp = self._load_confirmation_for_resume(suspension_id)
        if not susp:
            yield {"type": "error", "message": f"runtime confirmation {suspension_id} not found"}
            return
        try:
            susp = self._resolve_runtime_confirmation(
                susp,
                user_response,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
            return
        resumed_input = self._build_resume_user_input(susp, user_response)
        confirmation_id = susp.confirmation_id or susp.suspension_id
        self._turn_resumed_from_confirmation = True

        self.messages.append({"role": "user", "content": (
            f"<confirmation_response confirmation_id=\"{confirmation_id}\" suspension_id=\"{confirmation_id}\" version=\"{susp.version}\">\n"
            f"Question: {susp.question}\n"
            f"User answered: {user_response}\n"
            f"</confirmation_response>"
        )})

        final_text = ""
        round_num = 0

        while True:
            round_num += 1

            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

            # Safety valve: force summary at high round count
            if round_num == 300:
                self.messages.append({"role": "user", "content": (
                    "分析已进行超过 300 轮工具调用。请立即停止调用工具，"
                    "基于已获得的所有数据和分析结果输出总结报告。"
                )})

            self._compact_context_if_needed()

            blocked_confirmation = self._runtime_confirmation_checkpoint()
            if blocked_confirmation is not None:
                yield self._suspended_event(blocked_confirmation)
                return

            self._enter_synthesis_reserve_if_needed(resumed_input)

            buffer_text_events = (
                self._is_analysis_quality_guard_candidate()
                or self._should_buffer_final_answer_text()
            )
            pending_text_events = []

            # Inject paragraph separator between streaming rounds
            if round_num > 1:
                separator_event = {"type": "text_delta", "text": "\n\n"}
                if buffer_text_events:
                    pending_text_events.append(separator_event)
                else:
                    yield separator_event

            response = None
            for ev in self._stream_llm_round(round_num):
                if ev["type"] == "_response":
                    response = ev["response"]
                elif ev["type"] == "text_delta":
                    if buffer_text_events:
                        pending_text_events.append(ev)
                    else:
                        yield ev
                else:
                    yield ev

            # Check interrupt after streaming round
            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

            if response is None:
                yield {"type": "error", "message": "LLM 返回为空"}
                return

            response_text = response.text or ""
            if response.has_tool_calls and self._is_final_answer_audit_candidate():
                response_text = self._public_intermediate_text(response_text)
            assistant_msg: dict = {"role": "assistant", "content": response_text}
            if response.reasoning_content:
                assistant_msg["reasoning_content"] = response.reasoning_content
            if response_text:
                final_text = response_text

            if response.has_tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]

            self.messages.append(assistant_msg)

            if response.has_tool_calls and self._synthesis_audit_revision_active():
                final_text = self._reject_synthesis_revision_tool_calls(resumed_input)
                if final_text:
                    yield {"type": "text_delta", "text": final_text, "turn_id": None}
                self._maybe_archive(resumed_input, final_text)
                self._auto_save()
                return

            if not response.has_tool_calls:
                self._maybe_inject_synthesis_policy(resumed_input)
                if self._should_continue_for_analysis_quality(resumed_input, final_text):
                    self._reclassify_discarded_candidate_budget(
                        reason="analysis_quality_continuation",
                    )
                    continue
                if self._maybe_repair_truncated_analysis_response(response):
                    yield from self._emit_progress_stream("tool_recovery")
                    continue
                blocked_confirmation = self._runtime_confirmation_checkpoint()
                if blocked_confirmation is not None:
                    yield self._suspended_event(blocked_confirmation)
                    return
                if self._is_final_answer_audit_candidate():
                    gate = self._gate_final_analysis_answer(resumed_input, final_text)
                    if gate["action"] == "continue":
                        continue
                    final_text = gate["text"]
                    if final_text:
                        yield {"type": "text_delta", "text": final_text, "turn_id": None}
                elif buffer_text_events:
                    for ev in pending_text_events:
                        yield ev
                self._maybe_archive(resumed_input, final_text)
                self._auto_save()
                return

            if buffer_text_events:
                if not self._is_final_answer_audit_candidate():
                    for ev in pending_text_events:
                        yield ev

            # Budget-based quality reminder injection
            self._maybe_inject_quality_reminder()

            suspended = False
            for ev in self._process_tool_calls(response, round_num):
                yield ev
                if ev["type"] == "suspended":
                    suspended = True
            if suspended:
                return

            self._maybe_replan_after_data_load(resumed_input)
            self._maybe_inject_synthesis_policy(resumed_input)

            # Check interrupt after tool calls
            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

            # Safety valve: hard stop at 310 rounds
            if round_num >= 310:
                logger.warning("Safety valve triggered", extra={"extra_data": {
                    "session": self.session_id, "rounds": round_num,
                }})
                bounded_text = final_text or "分析已完成。（已达到安全轮次上限）"
                gate = self._gate_final_analysis_answer(
                    resumed_input,
                    bounded_text,
                    allow_repair=False,
                )
                final_text = gate["text"]
                if final_text:
                    yield {"type": "text_delta", "text": final_text, "turn_id": None}
                self._maybe_archive("", final_text)
                self._auto_save()
                return

    def _loop(self, user_input: str = "") -> LoopResult:
        """Run the agent loop inside this session's AgentContext."""
        with self.__context_operation("use"):
            return self._loop_impl(user_input)

    def _execute_tools_sequential(self, tool_calls, final_text: str) -> LoopResult | None:
        """Execute tool calls sequentially. Returns LoopResult if the loop should exit, None to continue."""
        for i, tc in enumerate(tool_calls):
            if self._interrupt_event.is_set():
                logger.info("Interrupted during tool execution")
                self._fill_remaining_tool_responses(tool_calls, i, "Turn interrupted by user")
                return FinalResponse(content=self._interrupted_response_text(final_text))

            logger.info("Tool call", extra={"extra_data": {"tool": tc.name, "args_keys": list(tc.arguments.keys())}})

            registry.expand_from_tool_call(tc.name)
            turn_state = getattr(self.context, "turn_state", None)
            if self._is_tool_blocked_by_confirmation(tc.name):
                blocked = self._blocked_tool_message(tc.name)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": blocked, "error_type": "confirmation_required"}, ensure_ascii=False),
                })
                self._fill_remaining_tool_responses(tool_calls, i + 1, "Turn blocked by confirmation")
                return FinalResponse(content=blocked)
            if turn_state is not None:
                try:
                    turn_state.ensure_can_call(tc.name, tc.arguments)
                except BudgetExceeded as exc:
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({"error": str(exc), "error_type": "budget_exceeded"}, ensure_ascii=False),
                    })
                    self._fill_remaining_tool_responses(tool_calls, i + 1, str(exc))
                    return FinalResponse(content=str(exc))
                turn_state.record_tool_call(tc.name, tc.arguments)

            result = self._execute_single_tool(tc, tool_calls, i)
            if result is not None:
                return result
        return None

    def _execute_single_tool(
        self,
        tc,
        tool_calls,
        index: int,
        _scope_guard=_protected_scope_guard,
    ) -> LoopResult | None:
        """Execute a single tool call and append result message.

        Returns LoopResult if the loop should exit (suspension), None to continue.
        """
        import time

        self.__context_operation("refresh")
        turn_state = getattr(self.context, "turn_state", None)

        # Bind once and reuse for both progress narration and compaction.
        # A substantive tool that binds to a canonical step narrates the
        # step-specific method before the generic ``tool_started`` breadcrumb.
        step_binding = self._bind_tool_call(tc)
        analysis_run_binding = self._analysis_run_binding(step_binding)
        if step_binding is not None and step_binding.ok and step_binding.step_id:
            self._record_progress(
                "analysis_step_started", step_id=step_binding.step_id
            )
        # Sync mirror of the streaming ``tool_started`` progress event. Emit
        # before scope/budget guards return early so a turn that suspends or
        # errors still leaves a "正在运行分析工具" diagnostic breadcrumb.
        self._record_progress("tool_started")

        scope_error = _scope_guard(self, tc.name, tc.arguments)
        if scope_error:
            if turn_state is not None:
                turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
            self._record_turn_tool_result(tc.name, scope_error)
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": scope_error,
            })
            return None

        try:
            with self.__context_operation("use"):
                tool_result = registry.execute(tc.name, tc.arguments)
            post_scope = self.__context_operation("refresh")
            committed_outcome = committed_tool_outcome(tool_result, post_scope)
        except UserConfirmationRequired as ucc:
            susp = self._suspend_for_confirmation_request(
                ucc,
                turn_id=str(getattr(tc, "id", "") or "direct_user_question"),
            )
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": f"Suspended for user confirmation. confirmation_id={susp.confirmation_id or susp.suspension_id}",
            })
            self._fill_remaining_tool_responses(tool_calls, index + 1, "Suspended for user confirmation")
            return susp

        tool_msg_content = self._compact_tool_output(tool_result, tc, step_binding)
        tool_failed = self._tool_content_is_error(tool_msg_content)

        if tool_failed:
            if turn_state is not None:
                turn_state.record_tool_error(tc.name, tc.arguments, tool_msg_content)
            tool_msg_content = registry.format_result(tc.name, tool_result)
            logger.warning("Tool error", extra={"extra_data": {"tool": tc.name, "error": tool_msg_content[:200]}})
        else:
            committed_outcome = self._persist_analysis_run_outcome(
                tc, analysis_run_binding, committed_outcome
            )
            tool_msg_content = render_committed_tool_content(
                tool_msg_content, committed_outcome
            )
            if turn_state is not None:
                turn_state.record_tool_success(
                    tc.name,
                    fallback_resolution=self._fallback_resolution_for_tool_call(tc),
                )

        self._record_turn_tool_result(tc.name, tool_msg_content)
        self._auto_track_task_progress(tc.name, not tool_failed)
        if not tool_failed:
            # Sync mirror of the streaming ``tool_succeeded`` event; only
            # fires on a successful execution, never on errors.
            self._record_progress("tool_succeeded", status="completed")

        # Check for stage regression after tool execution
        if self.context.analysis_state is not None:
            fc = getattr(self, '_flow_controller', None)
            if fc is not None:
                regression_msg = fc.check_tool_regression(
                    self.context.analysis_state, tc.name, tool_msg_content,
                )
                if regression_msg:
                    self.messages.append({
                        "role": "system",
                        "content": f"[分析流程回退] {regression_msg}",
                    })

        self.messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": tool_msg_content,
        })
        return None

    def _execute_tools_parallel(
        self,
        tool_calls,
        _scope_guard=_protected_scope_guard,
    ) -> list[tuple]:
        """Execute read-only tool calls in parallel. Returns [(tc, tool_msg_content), ...]."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from contextvars import copy_context

        turn_state = getattr(self.context, "turn_state", None)
        guarded_contexts = {}
        guard_errors = {}

        # Record all tool calls for budget tracking
        for tc in tool_calls:
            if turn_state is not None:
                turn_state.record_tool_call(tc.name, tc.arguments)
            self.__context_operation("refresh")
            scope_error = _scope_guard(self, tc.name, tc.arguments)
            if scope_error:
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
                guard_errors[tc.id] = scope_error
            guarded_contexts[tc.id] = copy_context()

        # Pre-compute deterministic bindings so the parallel workers can pass
        # the canonical ``StepBindingResult`` into compaction without each
        # worker touching ``state.analysis_plan`` concurrently.
        bindings = {tc.id: self._bind_tool_call(tc) for tc in tool_calls}
        analysis_run_bindings = {
            tc.id: self._analysis_run_binding(bindings.get(tc.id))
            for tc in tool_calls
        }

        def _run_tool(tc):
            try:
                scope_error = guard_errors.get(tc.id, "")
                if scope_error:
                    return (tc, scope_error, None)
                t0 = time.monotonic()
                with self.__context_operation("use"):
                    tool_result = registry.execute(tc.name, tc.arguments)
                post_scope = self.__context_operation("refresh")
                committed_outcome = committed_tool_outcome(tool_result, post_scope)
                duration_ms = int((time.monotonic() - t0) * 1000)
                tool_msg_content = self._compact_tool_output(
                    tool_result, tc, bindings.get(tc.id)
                )
                tool_failed = self._tool_content_is_error(tool_msg_content)

                if tool_failed:
                    if turn_state is not None:
                        turn_state.record_tool_error(tc.name, tc.arguments, tool_msg_content)
                    tool_msg_content = registry.format_result(tc.name, tool_result)
                else:
                    committed_outcome = self._persist_analysis_run_outcome(
                        tc,
                        analysis_run_bindings.get(tc.id),
                        committed_outcome,
                    )
                    tool_msg_content = render_committed_tool_content(
                        tool_msg_content, committed_outcome
                    )
                    if turn_state is not None:
                        turn_state.record_tool_success(
                            tc.name,
                            fallback_resolution=self._fallback_resolution_for_tool_call(tc),
                        )

                return (
                    tc,
                    tool_msg_content,
                    post_scope if committed_outcome.warning is not None else None,
                )
            except Exception as e:
                error_content = json.dumps({"error": str(e)}, ensure_ascii=False)
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, error_content)
                return (tc, error_content, None)

        import time

        results = {}
        max_workers = min(len(tool_calls), 3)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for tc in tool_calls:
                ctx = guarded_contexts[tc.id]
                future = pool.submit(lambda t=tc: ctx.run(_run_tool, t))
                futures[future] = tc.id

            for future in as_completed(futures):
                tc_obj, content, refresh_error = future.result()
                if refresh_error is not None:
                    self.__context_operation("record_worker_refresh_error", refresh_error)
                results[tc_obj.id] = (tc_obj, content)

        # Return in original order
        return [results[tc.id] for tc in tool_calls if tc.id in results]

    def _loop_impl(self, user_input: str = "") -> LoopResult:
        """循环调用 LLM 直到获得最终文本回复。"""
        final_text = ""
        round_num = 0

        # 惰性初始化 MCP
        self._ensure_mcp_initialized()

        # Sync mirror of the streaming plan-ready progress event so CLI/tests
        # share state without SSE. Fires once per turn, before any round.
        self._record_progress("analysis_plan_ready", status="completed")

        while True:
            round_num += 1
            # 协作式中断检查
            if self._interrupt_event.is_set():
                logger.info("Turn interrupted by user")
                return FinalResponse(content=self._interrupted_response_text(final_text))

            # Safety valve: force summary at high round count
            if round_num == 300:
                self.messages.append({"role": "user", "content": (
                    "分析已进行超过 300 轮工具调用。请立即停止调用工具，"
                    "基于已获得的所有数据和分析结果输出总结报告。"
                )})

            self._compact_context_if_needed()

            blocked_confirmation = self._runtime_confirmation_checkpoint()
            if blocked_confirmation is not None:
                return blocked_confirmation

            self._enter_synthesis_reserve_if_needed(user_input)

            # Defensive: repair any broken tool_call sequences from prior turns
            self._repair_broken_tool_sequence()

            phase = self._current_prompt_phase()
            turn_state = getattr(self.context, "turn_state", None)
            phase_usage_before = (
                int(turn_state.phase_token_usage.get(phase, 0) or 0)
                if turn_state is not None
                else 0
            )
            system_prompt = self._get_system_prompt()
            output_limit = self._llm_output_limit_kwargs(
                self.client.chat,
                phase=phase,
            )
            response = self.client.chat(
                messages=self.messages,
                tools=registry.active_definitions() or None,
                system=system_prompt,
                **output_limit,
            )
            self._record_llm_response_budget(
                response,
                phase=phase,
            )
            self._reclassify_synthesis_tool_round_budget(
                response,
                phase=phase,
                phase_usage_before=phase_usage_before,
            )
            self._remember_round_budget(
                phase=phase,
                usage_before=phase_usage_before,
            )

            response_text = response.text or ""
            if response.has_tool_calls and self._is_final_answer_audit_candidate():
                response_text = self._public_intermediate_text(response_text)
            assistant_msg: dict = {"role": "assistant", "content": response_text}
            if response.reasoning_content:
                assistant_msg["reasoning_content"] = response.reasoning_content
            if response_text:
                final_text = response_text

            if response.has_tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]

            self.messages.append(assistant_msg)

            if response.has_tool_calls and self._synthesis_audit_revision_active():
                fallback = self._reject_synthesis_revision_tool_calls(user_input)
                return FinalResponse(content=fallback)

            if not response.has_tool_calls:
                self._maybe_inject_synthesis_policy(user_input)
                if self._should_continue_for_analysis_quality(user_input, final_text):
                    self._reclassify_discarded_candidate_budget(
                        reason="analysis_quality_continuation",
                    )
                    continue
                if self._maybe_repair_truncated_analysis_response(response):
                    self._record_progress("tool_recovery")
                    continue
                # Sync mirror of completion/audit/recovery progress signals.
                self._record_progress("completion_evaluated")
                blocked_confirmation = self._runtime_confirmation_checkpoint()
                if blocked_confirmation is not None:
                    return blocked_confirmation
                self._record_progress("audit_started")
                gate = self._gate_final_analysis_answer(user_input, final_text)
                if gate["action"] == "continue":
                    self._record_progress("tool_recovery")
                    continue
                final_text = gate["text"]
                return FinalResponse(content=final_text)

            # Budget-based quality reminder injection
            self._maybe_inject_quality_reminder()

            # 执行工具，每条结果作为独立的 tool 消息
            tool_calls = response.tool_calls

            # Check if all tool calls are read-only → parallel execution
            from data_agent.tools.registry import get_read_only_tools
            read_only = get_read_only_tools(registry)
            all_read_only = len(tool_calls) > 1 and all(
                tc.name in read_only for tc in tool_calls
            )

            if all_read_only:
                # Pre-check all tools (group expansion, confirmation, budget)
                can_parallelize = True
                for tc in tool_calls:
                    registry.expand_from_tool_call(tc.name)
                    if self._is_tool_blocked_by_confirmation(tc.name):
                        can_parallelize = False
                        break
                    turn_state = getattr(self.context, "turn_state", None)
                    if turn_state is not None:
                        try:
                            turn_state.ensure_can_call(tc.name, tc.arguments)
                        except BudgetExceeded:
                            can_parallelize = False
                            break

                if can_parallelize:
                    # Sync mirror of the streaming ``tool_started`` event for
                    # each parallelized read-only tool. Per-tool signal so the
                    # diagnostic trail matches the sequential path even when
                    # execution is concurrent.
                    for tc in tool_calls:
                        self._record_progress("tool_started")
                    results = self._execute_tools_parallel(tool_calls)
                    for tc, tool_msg_content in results:
                        self._record_turn_tool_result(tc.name, tool_msg_content)
                        succeeded = not self._tool_content_is_error(tool_msg_content)
                        self._auto_track_task_progress(tc.name, succeeded)
                        if succeeded:
                            self._record_progress("tool_succeeded", status="completed")
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_msg_content,
                        })
                else:
                    seq_result = self._execute_tools_sequential(tool_calls, final_text)
                    if seq_result is not None:
                        return seq_result
            else:
                seq_result = self._execute_tools_sequential(tool_calls, final_text)
                if seq_result is not None:
                    return seq_result

            self._maybe_replan_after_data_load(user_input)
            self._maybe_inject_synthesis_policy(user_input)

            # Safety valve: hard stop at 310 rounds
            if round_num >= 310:
                logger.warning("Safety valve triggered", extra={"extra_data": {
                    "session": self.session_id, "rounds": round_num,
                }})
                bounded_text = final_text or "分析已完成。（已达到安全轮次上限）"
                self._record_progress("completion_evaluated")
                self._record_progress("audit_started")
                gate = self._gate_final_analysis_answer(
                    user_input,
                    bounded_text,
                    allow_repair=False,
                )
                return FinalResponse(content=gate["text"])

    def _maybe_archive(self, user_input: str, reply: str) -> None:
        """当有实质性分析结果时自动归档。"""
        with self.__context_operation("use"):
            return self._maybe_archive_impl(user_input, reply)

    def _maybe_archive_impl(self, user_input: str, reply: str) -> None:
        from data_agent.session.workspace import workspace
        from data_agent.session.history import archive_analysis

        datasets = workspace.list_datasets()
        if not datasets or not reply:
            return

        tools_used = []
        for msg in self.messages[-20:]:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    name = tc.get("function", {}).get("name", "")
                    if name and name not in ("load_data", "list_data", "preview_data"):
                        tools_used.append(name)

        if not tools_used:
            return

        data_file = self._last_data_file or list(datasets.keys())[0]
        summary = reply[:500] if reply else ""

        archive_analysis(
            session_id=self.session_id,
            data_file=data_file,
            summary=summary,
            insights=[],
            tools_used=tools_used,
        )

    def _serialize_messages(self) -> list:
        """Serialize messages for suspension storage."""
        serialized = []
        for msg in self.messages:
            m = {"role": msg["role"]}
            content = msg.get("content")
            if isinstance(content, str):
                m["content"] = content[:5000]
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        parts.append(str(part)[:500])
                    else:
                        parts.append(str(part)[:500])
                m["content"] = parts
            else:
                m["content"] = str(content)[:5000]
            serialized.append(m)
        return serialized


def _create_streaming_context_methods(loop_context_operation, stream_impl, resume_impl):
    """Bind a loop context for exactly the lifetime of each streaming generator."""

    def stream_turn(self, user_input: str):
        with loop_context_operation(self, "use"):
            yield from stream_impl(self, user_input)

    def resume_turn_streaming(
        self,
        suspension_id: str,
        user_response: str,
        *,
        expected_version: int | None = None,
        idempotency_key: str = "",
    ):
        with loop_context_operation(self, "use"):
            yield from resume_impl(
                self,
                suspension_id,
                user_response,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )

    return stream_turn, resume_turn_streaming


AgentLoop.stream_turn, AgentLoop.resume_turn_streaming = _create_streaming_context_methods(
    _loop_context_operation,
    AgentLoop._stream_turn_impl,
    AgentLoop._resume_turn_streaming_impl,
)
del _create_scope_guard_descriptor
del _protected_scope_guard, _scope_guard_dispatch
del _create_loop_context_dispatch_descriptor, _create_streaming_context_methods
