from __future__ import annotations

import copy
import hashlib
import json
import re
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


def _structured_detail_identity(tool_call_id: str, data: Any) -> tuple[str, str]:
    """Return a bounded content address and the canonical payload digest."""
    payload_digest = hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    call_digest = hashlib.sha256(str(tool_call_id).encode("utf-8")).hexdigest()
    return f"result-{call_digest[:12]}-{payload_digest[:12]}", f"sha256:{payload_digest}"


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
    "compare_periods",
    "analyze_time_series",
    "funnel_analysis",
    "correlation_analysis",
    "ab_test",
    "run_python",
    "curve_fitting",
    "contribute_decomposition",
    "distribution_analysis",
    "segmentation_analysis",
    "cohort_analysis",
    "causal_analysis",
    "shap_analysis",
    "forecast",
    "classification",
    "regression_analysis",
    "attribution_analysis",
    "what_if_simulation",
}

# Profiling receipts are sufficient evidence for a bounded factual summary,
# even though they do not satisfy the analysis-quality requirement for a new
# substantive analysis. Keeping these concepts separate prevents presentation
# follow-ups from losing their source/unit/version guardrails.
_PUBLICATION_EVIDENCE_TOOLS = _SUBSTANTIVE_TOOLS | {
    "preview_data",
    "describe_dataset",
    "quick_profile",
    "detect_data_quality",
    "interpret_dataset",
}

_ANALYSIS_QUALITY_GUARD_MESSAGE = (
    "<analysis_quality_guard>\n"
    "The user requested analysis, but this turn has only loaded or profiled data. "
    "Continue by creating or applying an AnalysisSpec, running relevant analysis steps, "
    "and recording evidence before giving the final answer.\n"
    "</analysis_quality_guard>"
)

_HYPOTHESIS_QUALITY_GUARD_MESSAGE = (
    "<competing_hypothesis_quality_guard>\n"
    "The user explicitly requested competing hypotheses, but the structured audit trail is incomplete: {gaps}. "
    "Continue with tools before answering. Record an analysis plan, keep at least two stable hypotheses, "
    "and attach receipt-backed support/refute proposals through record_evidence_record.competing_hypotheses "
    "using the hypothesis IDs already shown in <competing_hypotheses>. The host will validate each relation. "
    "Report unsupported, refuted, supported, contested, inconclusive, or stale exactly as the resulting state shows; "
    "do not ask the user to choose an analysis method and do not invent a verdict.\n"
    "</competing_hypothesis_quality_guard>"
)

_WRAP_UP_GUARD_MESSAGE = (
    "<analysis_wrap_up_guard>\n"
    "The analysis has already run for many rounds. Conclude now with the evidence "
    "already computed: state the verified findings with their numbers, the boundaries "
    "and limitations, and the next action. Start new exploratory tool calls only if "
    "strictly required to close the answer.\n"
    "</analysis_wrap_up_guard>"
)

_FINALIZATION_GUARD_MESSAGE = (
    "<analysis_finalization_mode>\n"
    "The turn has already completed substantive analysis. Tool use is now closed for "
    "this turn. Continue reasoning over the verified results already in the conversation, "
    "then provide the final answer with numbers, boundaries, limitations, and next action. "
    "Do not emit tool tags, tool_calls, or requests for more tools, and do not claim facts "
    "that the available evidence does not support.\n"
    "</analysis_finalization_mode>"
)

_FINALIZATION_RECOVERY_MESSAGE = (
    "<analysis_finalization_recovery>\n"
    "Your previous response attempted tool-invocation markup after tools were intentionally "
    "closed. That markup was not executed and will not be shown to the user. Do not emit "
    "tool tags, tool_calls, or requests for more tools. Continue reasoning from the verified "
    "results already available, then answer directly with numbers, boundaries, limitations, "
    "and next action.\n"
    "</analysis_finalization_recovery>"
)

_PUBLICATION_RECOVERY_MESSAGE = (
    "<publication_narrative_recovery>\n"
    "Your previous final answer was rejected by the deterministic publication contract and will not be shown to the user. "
    "Rewrite the answer once using only the already computed evidence. Preserve supported numeric findings, explicitly state unknowns and limitations, "
    "and remove the unsupported interpretation described below. Do not call tools.\n"
    "Rejection: {error}\n"
    "</publication_narrative_recovery>"
)

_FALLBACK_RESOLUTION_GUIDANCE = (
    "<fallback_resolution_guidance>\n"
    "已执行的 Python 计算结果尚未沉淀。两条合法的继续路径：\n"
    "1. 调用 record_evidence_record 把结果记录为证据（含口径、样本与限制）；\n"
    "2. 直接给出最终答复——发布已观测范围内的描述性结论，并对无法支持的部分明确边界"
    "（例如“无法预测 D30：仅观测到 D7，缺少 D8—D30 观测与验证窗口”）。\n"
    "带证据边界的拒答是有效完成状态；不要继续探索性工具调用，也不要为未观测数值编造估计。\n"
    "</fallback_resolution_guidance>"
)


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
        decision_context: dict | None = None,
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
        # IC1：直接询问携带结构化决策上下文（decision_kind/missing_value/
        # affected_operations/scope_data_version），模型自报字段仍经宿主校验。
        self.decision_context = dict(decision_context or {})
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
        if operation == "reset_for_new_data":
            if binding is None:
                raise RuntimeError("Agent loop context is not initialized")
            return binding[4]()
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
            refresh, guard, record_worker_refresh_error, reset_for_new_data = scope_controller_claimant(replacement)
            bindings[loop] = (
                replacement,
                refresh,
                guard,
                record_worker_refresh_error,
                reset_for_new_data,
            )
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


def record_is_none(request_result) -> bool:
    """True when a confirmation request produced no record to suspend on."""
    return request_result.record is None


def _provider_failure_detail(exc: BaseException, limit: int = 300) -> str:
    """将异常压缩成单行摘要，供日志与用户可见错误使用。

    litellm 异常常内嵌完整 provider 响应（多行、超长），不能原样进入
    UI 或 notice；只保留类名 + 首段消息并截断。
    """
    text = " ".join(str(exc).split())
    try:
        configured_key = str(get_config().api_key or "")
    except Exception:
        configured_key = ""
    if configured_key:
        text = text.replace(configured_key, "[REDACTED]")
    text = re.sub(
        r"(?i)((?:authorization|api[_-]?key|access[_-]?token|secret|password)"
        r"\s*[:=]\s*[\"']?(?:bearer\s+)?)[^\s,;\"'}]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
    text = text[:limit]
    name = type(exc).__name__
    return f"{name}: {text}" if text else name


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
        auxiliary_llm_client=None,
    ):
        global _skill_loader, _mcp_manager, _mcp_bridge

        cfg = get_config()
        self.client = client or LLMClient()
        self.auxiliary_llm_client = auxiliary_llm_client
        if self.auxiliary_llm_client is None and isinstance(self.client, LLMClient):
            # Intent/playbook calls share the injected transport and own an
            # eight-second transport deadline; no detached timeout thread.
            self.auxiliary_llm_client = self.client.for_purpose(max_tokens=300, timeout=8)
        self.session_id = session_id or uuid.uuid4().hex[:12]
        active_project = project_name if project_name is not None else object_name
        self.context = AgentContext(
            session_id=self.session_id,
            project_name=active_project,
            workspace=Workspace(),
        )
        from data_agent.agent.analysis_state import load_analysis_state
        self.context.analysis_state = load_analysis_state(self.session_id, active_project)
        self.messages: list[dict] = []
        self.token_threshold = cfg.token_threshold
        self._last_data_file = ""
        self._prompt_cache: str = ""
        self._prompt_cache_dirty: bool = True
        self._prompt_cache_key: tuple[str, str] | None = None
        self._knowledge_retrieval_service = None
        self._interrupt_event = threading.Event()
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

    def prepare_for_bound_upload(self) -> dict:
        """Retire an obsolete plan and reopen the exact session for new data."""

        from data_agent.session.task_manager import task_manager

        retired = task_manager.retire_active_plan_for_new_data(
            session_id=self.session_id,
            project_name=self.context.project_name or "",
        )
        try:
            scope = self.__context_operation("reset_for_new_data")
            if scope.phase != "legacy":
                raise RuntimeError("bound upload did not obtain a legacy workspace scope")
        except Exception:
            task_manager.restore_retired_plan(retired)
            self.__context_operation("refresh")
            raise
        self.invalidate_prompt_cache()
        return retired

    def rollback_bound_upload(self, retirement: dict) -> dict:
        """Restore the prior execution scope after ingestion fails."""

        from data_agent.session.task_manager import task_manager

        restored = task_manager.restore_retired_plan(retirement)
        if restored.get("restored") or restored.get("reason") in {
            "nothing_retired",
            "already_restored",
        }:
            self.__context_operation("refresh")
        self.invalidate_prompt_cache()
        return restored

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
        with self.__context_operation("use"):
            self._restore_workspace_scoped()

    def _restore_workspace_scoped(self) -> None:
        """Restore workspace datasets from persisted metadata.

        Identity-bearing metadata requires the exact persisted snapshot.
        Legacy metadata may reload its original file or use a backup.
        """
        from data_agent.session.history import _session_dir
        from data_agent.session.workspace import workspace

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
        from data_agent.migration import read_session_migration_status
        migration_status = read_session_migration_status(self.session_id)
        is_read_only_missing_original = migration_status.get("mode") == "read_only_missing_original"
        for name, info in meta.items():
            df = None
            identity = info.get("data_identity") or {}

            # Strategy A: try original file path
            source_path = info.get("source_path", "")
            if source_path and not identity:
                from pathlib import Path as _Path
                sp = _Path(source_path)
                if sp.exists():
                    try:
                        fmt = info.get("source_fmt", "")
                        if fmt == "csv":
                            try:
                                df = pd.read_csv(sp, encoding="utf-8-sig")
                            except UnicodeDecodeError:
                                df = pd.read_csv(sp, encoding="gbk")
                        elif fmt == "excel":
                            df = pd.read_excel(sp)
                        elif fmt == "json":
                            df = pd.read_json(sp)
                        if df is not None:
                            from data_agent.tools.data_clean import auto_clean
                            df, _, _ = auto_clean(df)
                    except Exception:
                        df = None

            # A migrated session whose original input is gone is intentionally
            # read-only. Do not present its backup as a re-uploaded source.
            if df is None and not is_read_only_missing_original:
                parquet_path = sdir / "data" / f"{name}.parquet"
                if parquet_path.exists():
                    try:
                        df = pd.read_parquet(parquet_path)
                    except Exception:
                        pass
                if df is None:
                    pickle_path = sdir / "data" / f"{name}.pkl"
                    if pickle_path.exists():
                        try:
                            df = pd.read_pickle(pickle_path)
                        except Exception:
                            pass

            if df is not None:
                if identity:
                    from data_agent.session.workspace import Workspace
                    if Workspace._frame_fingerprint(df) != identity.get("fingerprint"):
                        logger.warning("Stored dataset identity mismatch; restore refused", extra={"extra_data": {"dataset": name}})
                        continue
                added = workspace.add(name, df)
                if added.startswith("Error:"):
                    logger.warning("Dataset restore denied by current scope", extra={"extra_data": {"dataset": name}})
                    continue
                if identity:
                    workspace.set_metadata(name, "data_identity", identity)
                if info.get("context"):
                    workspace.set_metadata(name, "context", info["context"])
                workspace.set_metadata(name, "_source_path", source_path)
                workspace.set_metadata(name, "_source_fmt", info.get("source_fmt", ""))
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
        for client in (self.client, self.auxiliary_llm_client):
            if isinstance(client, LLMClient):
                client.cancel()

    def clear_interrupt(self) -> None:
        """清除中断信号（新 turn 开始时调用）。"""
        self._interrupt_event.clear()
        for client in (self.client, self.auxiliary_llm_client):
            if isinstance(client, LLMClient):
                client.reset_cancellation()

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
        from data_agent.agent.prompts import (
            _classify_task,
            build_system_prompt,
            detect_audience,
            resolve_proficiency,
        )
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

        # Proficiency: "auto" re-detects every turn without being written
        # back, so a later plain-language request is honored (P6/D07).
        proficiency = resolve_proficiency(
            self.context.user_proficiency, user_input, self.messages,
        )
        if self.context.user_proficiency == "auto":
            self.context.detected_proficiency = proficiency
        # Audience is per-turn from explicit self-identification; it never
        # changes facts, evidence thresholds, or permissions.
        audience = detect_audience(user_input)
        self.context.audience = audience

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
            from data_agent.agent.analysis_state import analysis_state_summary
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
        except Exception:
            pass

        level = _classify_task(user_input, session_ctx) if user_input else "standard"

        # P08-05：无数据时的最短可行动恢复——说明缺少数据＋一个明确入口，
        # 不列未来路线菜单、不追问无关业务背景。
        no_data_recovery = ""
        if not datasets:
            no_data_recovery = (
                "<no_data_recovery>\n"
                "当前没有可分析的数据。回复保持最短：说明缺少数据，并给出一个明确的上传或选择数据集入口；"
                "收到数据后可直接执行用户已描述的任务。"
                "不要列举未来分析路线菜单，不要追问与当前请求无关的业务背景，也不要推测业务答案。\n"
                "</no_data_recovery>"
            )

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

        # Chat 模式：只注入 rules（业务约束），跳过 domain/experience
        if level == "chat":
            return build_system_prompt(
                tool_list=tool_list,
                project_rules=(no_data_recovery + "\n\n" + rules_prompt).strip(),
                domain_knowledge="",
                experience_log="",
                session_context=session_ctx,
                skill_instructions="",
                skill_descriptions="",
                user_input=user_input,
                proficiency=proficiency,
                user_requirements=self.context.user_quality_requirements,
                audience=audience,
            )

        return build_system_prompt(
            tool_list=tool_list,
            project_rules=(no_data_recovery + "\n\n" + rules_prompt).strip(),
            domain_knowledge=retrieved_context,
            experience_log="",
            session_context=session_ctx,
            skill_instructions=skill_instructions,
            skill_descriptions=skill_descriptions,
            user_input=user_input,
            proficiency=proficiency,
            user_requirements=self.context.user_quality_requirements,
            audience=audience,
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
            cache_key = (scope.fingerprint, bundle_fingerprint)
            if self._prompt_cache_dirty or not self._prompt_cache or cache_key != self._prompt_cache_key:
                self._prompt_cache = self._build_system_prompt()
                self._prompt_cache_dirty = False
                self._prompt_cache_key = cache_key
            prompt = self._prompt_cache
            synthesis_instruction = getattr(self, "_turn_synthesis_policy_instruction", "")
            if synthesis_instruction:
                prompt = prompt + "\n\n" + synthesis_instruction
            hint = self._execution_prompt_hint()
            if hint:
                return prompt + f"\n\n<execution_control>\n{hint}\n</execution_control>"
            return prompt

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
        if self.auxiliary_llm_client is None:
            intent = plan_turn_intent(user_input, session_ctx)
        else:
            intent = plan_turn_intent(
                user_input,
                session_ctx,
                llm_client=self.auxiliary_llm_client,
            )
        controller = AnalysisFlowController(self.session_id, self.context.project_name)
        self._flow_controller = controller
        state = self.context.analysis_state if self.context.analysis_state is not None else controller.load_state()
        self.context.analysis_state = state
        try:
            import hashlib
            from data_agent.agent.publication_synthesis import update_requirement_lifecycle

            source_ref = "msg_" + hashlib.sha256(user_input.encode("utf-8")).hexdigest()[:12]
            requirement_ids = update_requirement_lifecycle(
                state,
                user_input,
                source_message_ref=source_ref,
            )
            self.context.turn_requirement_ids = requirement_ids
            self.context.requirement_revision = int(getattr(state, "requirement_revision", 0) or 0)
        except Exception as exc:
            logger.warning(
                "Answer requirement lifecycle update skipped",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )
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
        if self.auxiliary_llm_client is None:
            controller.prepare_turn(
                state,
                intent,
                user_input=user_input,
                dataset_profile=session_ctx,
            )
        else:
            controller.prepare_turn(
                state,
                intent,
                user_input=user_input,
                dataset_profile=session_ctx,
                llm_client=self.auxiliary_llm_client,
            )
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
        self.context.turn_state = TurnExecutionState(ToolExecutionBudget(
            profile=profile,
            token_budget=_token_budget_for_profile(profile, cfg.token_threshold),
        ))

        # Extract user quality requirements on first analysis turn
        if not self.context.user_quality_requirements and user_input and len(user_input) > 100:
            self._extract_user_requirements(user_input)

        return controller.activate_tool_groups(registry, intent, state, user_input)

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
        if susp is None and isinstance(pending, dict) and has_new_question:
            # IC2：旧 pending 被策略降级（如通用方法审批）时，让位给本轮
            # 新检测到的真实语义问题，而不是吞掉整个悬挂路径。
            pending = False
            pending_data = {}
            question_data = self._turn_question_need if isinstance(self._turn_question_need, dict) else {}
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
                source="question_need_detector",
                operation=str(payload["confirmation_type"] or "auto_required_question"),
            )
        if susp is None:
            return None
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
            client = self.auxiliary_llm_client or self.client
            resp = client.chat(
                messages=[{"role": "user", "content": prompt}],
                system="你是要求提取专家。只输出提取的要求，不要解释。如无要求输出空。",
            )
            requirements = resp.text.strip()
            if requirements and len(requirements) > 5:
                self.context.user_quality_requirements = requirements
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

    def _compact_tool_output(self, tool_result, tc) -> str:
        """Compact tool output for LLM context. Persist data/details to disk, return concise summary."""
        from data_agent.tools.registry import ToolResult

        summary = tool_result.to_cli()

        # If ToolResult has structured data, persist it
        if tool_result.data is not None:
            try:
                detail_key, _ = _structured_detail_identity(tc.id, tool_result.data)
                detail_path = persist_detail(self.session_id, detail_key, tool_result.data)
                detail_ref = f" [detail: tool_outputs/{detail_path.name}]"
            except Exception:
                detail_ref = ""
        else:
            detail_ref = ""

        # Persist the receipt, but deliver the bounded page itself unchanged.
        # A summary of this page would recursively replace the requested bytes.
        if getattr(tc, "name", "") == "read_file" and isinstance(tool_result.data, dict) and tool_result.data.get("schema_version") == "file_page.v1":
            return summary

        # If summary is short enough, keep as-is
        if len(summary) <= TOOL_SUMMARY_THRESHOLD:
            return persist_large_output(self.session_id, tc.id, summary + detail_ref)

        # Long summary: persist full version, return truncated + reference
        try:
            summary_path = persist_detail(self.session_id, tc.id + "_summary", {"full_output": summary})
            truncated = summary[:TOOL_SUMMARY_THRESHOLD]
            # Try to break at a natural boundary
            last_newline = truncated.rfind("\n")
            if last_newline > TOOL_SUMMARY_THRESHOLD * 0.7:
                truncated = truncated[:last_newline]
            compact = (
                f"{truncated}\n\n"
                f"[Output truncated. Full summary: tool_outputs/{summary_path.name}]{detail_ref}"
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
                # Task/evidence completion is not implied by one successful tool.
                return
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
        self._turn_successful_substantive_tools = set()
        self._turn_successful_publication_tools = set()
        self._turn_loaded_data = False
        self._turn_final_guard_injected = False
        self._turn_analysis_quality_gaps = []
        self._turn_verification_injected = False
        self._turn_wrap_up_injected = False
        self._turn_finalization_mode = False
        self._turn_finalization_recovery_used = False
        self._turn_publication_recovery_used = False
        self._turn_origin_revision_issued = False
        self._turn_synthesis_policy_injected = False
        self._turn_synthesis_policy_instruction = ""
        self._turn_publication_packet = None
        self.context.turn_receipt_ids = []
        self.context.turn_requirement_ids = []

    def _has_substantive_turn_evidence(self) -> bool:
        """Whether this turn has executed a computation suitable for synthesis."""
        return bool(getattr(self, "_turn_successful_substantive_tools", set()))

    def _has_publishable_turn_evidence(self) -> bool:
        """Whether this turn produced a receipt suitable for factual publication."""
        return bool(getattr(self, "_turn_successful_publication_tools", set()))

    def _latest_publication_packet_for_presentation(self, user_input: str) -> dict | None:
        """Reuse the last accepted snapshot for a no-evidence follow-up turn.

        P1-6 item 3 (real R15 M05 "120 块" leak): reuse is gated by closed-class
        identity only (ready + answer_sha256 + every bound dataset fingerprint
        unchanged), never by matching presentation phrasing - a wording outside
        the retired regex list used to skip reuse and thereby skip the whole
        narrative validation for the turn's final answer.
        """
        state = getattr(self.context, "analysis_state", None)
        packets = list(getattr(state, "publication_packets", []) or []) if state is not None else []
        for packet in reversed(packets):
            if not isinstance(packet, dict) or packet.get("status") != "ready":
                continue
            if not packet.get("answer_sha256") or not packet.get("sources"):
                continue
            identity_count = 0
            stale = False
            for source in packet.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                for dataset, identity in (source.get("data_identities") or {}).items():
                    if not isinstance(identity, dict):
                        stale = True
                        break
                    current = self.context.workspace.get_data_identity(str(dataset))
                    expected = str(identity.get("fingerprint") or identity.get("version_id") or "")
                    actual = str((current or {}).get("fingerprint") or (current or {}).get("version_id") or "")
                    identity_count += 1
                    if not expected or expected != actual:
                        stale = True
                        break
                if stale:
                    break
            if identity_count and not stale:
                return copy.deepcopy(packet)
        return None

    def _tools_for_current_round(self):
        """Offer tools until a sufficiently evidenced turn enters finalization.

        Finalization still leaves the model free to reason and write its own
        answer. It only closes further tool exploration after substantive
        analysis, preventing a soft wrap-up reminder from being ignored until
        an external journey budget is exhausted.
        """
        if getattr(self, "_turn_finalization_mode", False):
            return None
        return registry.active_definitions() or None

    @staticmethod
    def _contains_unexecuted_tool_markup(text: str) -> bool:
        """Recognize tool syntax emitted as ordinary final-answer text.

        Some reasoning models emit DSML/OpenAI-style tool tags even when no
        tool schema is offered. Those bytes are not executable tool calls and
        must not be mistaken for a publishable analytical answer.
        """
        normalized = str(text or "").lower()
        markers = (
            "<｜｜dsml｜｜",
            "<|dsml|>",
            "<tool_calls>",
            "<tool_call>",
            "\"tool_calls\"",
        )
        return any(marker in normalized for marker in markers)

    def _recover_finalization_tool_markup(self) -> bool:
        """Request one no-tools correction after an unexecuted tool attempt."""
        if getattr(self, "_turn_finalization_recovery_used", False):
            return False
        self._turn_finalization_recovery_used = True
        self.messages.append({
            "role": "assistant",
            "content": "[未执行的最终化工具标记已省略；请基于现有证据直接作答。]",
        })
        self.messages.append({"role": "system", "content": _FINALIZATION_RECOVERY_MESSAGE})
        return True

    def _persist_rejected_publication(self, assistant_msg: dict, error: str) -> None:
        """Persist every rejected publication candidate for audit (P2-1).

        Real r2 M02 trajectory: from the second rejection on, the candidate's
        full text existed only inside the failure notification quote - the
        audit trail could not reach it. The dump is host bookkeeping; a write
        failure must never block the already-failing publication path.
        """
        try:
            from datetime import datetime

            out_dir = get_config().sessions_resolved / self.session_id / "publication_rejected"
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            body = (
                f"# 被拒发布候选 {stamp}\n\n"
                f"## 校验错误\n\n{error or 'publication contract violation'}\n\n"
                f"## 候选全文\n\n{assistant_msg.get('content') or ''}\n"
            )
            (out_dir / f"candidate_{stamp}.md").write_text(body, encoding="utf-8")
        except Exception as exc:
            logger.warning(
                "Rejected publication candidate dump failed",
                extra={"extra_data": {"session_id": self.session_id, "error": str(exc)}},
            )

    def _recover_publication_narrative(self, assistant_msg: dict, error: str) -> bool:
        """Keep one rejected answer internal and request one bounded rewrite."""
        if getattr(self, "_turn_publication_recovery_used", False):
            # P2-1：恢复额度用尽的拒绝同样落盘，候选全文不得只存在于
            # 失败通知的引文里。
            self._persist_rejected_publication(assistant_msg, error)
            return False
        self._turn_publication_recovery_used = True
        if "unsupported_data_origin_inference" in str(error or ""):
            # Revision-only finding: after this one rewrite request the
            # origin lexicon stops blocking; the host annotates instead.
            self._turn_origin_revision_issued = True
        self._persist_rejected_publication(assistant_msg, error)
        rejected = dict(assistant_msg)
        rejected["publication_rejected"] = True
        self.messages.append(rejected)
        self.messages.append({
            "role": "system",
            "content": _PUBLICATION_RECOVERY_MESSAGE.format(error=str(error or "publication contract violation")),
        })
        return True

    def _maybe_inject_wrap_up(self, round_num: int, user_input: str = "") -> None:
        """Nudge convergence without confusing round count with completion."""
        if getattr(self, "_turn_wrap_up_injected", False):
            return
        threshold = get_config().wrap_up_round
        if not threshold or round_num < threshold:
            return
        self._turn_wrap_up_injected = True
        packet = (
            self._prepare_publication_packet(user_input, phase="preview", persist=False)
            if self._has_substantive_turn_evidence()
            else None
        )
        if packet and packet.get("status") == "ready" and packet.get("evidence"):
            # Round count is advisory, not evidence of analysis completion.
            self.messages.append({"role": "system", "content": _WRAP_UP_GUARD_MESSAGE})
            if packet and packet.get("status") == "ready":
                from data_agent.agent.publication_synthesis import publication_packet_prompt

                self.messages.append({"role": "system", "content": publication_packet_prompt(packet)})
        else:
            self.messages.append({"role": "system", "content": _WRAP_UP_GUARD_MESSAGE})

    def _tool_content_is_error(self, content: str) -> bool:
        stripped = (content or "").lstrip()
        lowered = stripped.lower()
        return (
            stripped.startswith('{"error":')
            or stripped.startswith('{"error": ')
            or lowered.startswith("error")
        )

    def _record_turn_tool_result(
        self,
        tool_name: str,
        tool_msg_content: str,
        tool_args: dict | None = None,
        tool_call_id: str = "",
        structured_data: dict | None = None,
    ) -> str:
        if not hasattr(self, "_turn_tools_used"):
            self._reset_turn_tracking()
        self._turn_tools_used.append(tool_name)
        if tool_name in _SUBSTANTIVE_TOOLS and not self._tool_content_is_error(tool_msg_content):
            self._turn_successful_substantive_tools.add(tool_name)
        if tool_name in _PUBLICATION_EVIDENCE_TOOLS and not self._tool_content_is_error(tool_msg_content):
            self._turn_successful_publication_tools.add(tool_name)
        if tool_name == "load_data" and not self._tool_content_is_error(tool_msg_content):
            self._turn_loaded_data = True
        if self._tool_content_is_error(tool_msg_content):
            return ""

        state = getattr(self.context, "analysis_state", None)
        add_receipt = getattr(state, "add_tool_receipt", None)
        if not callable(add_receipt):
            return ""
        try:
            from data_agent.agent.publication_synthesis import publication_contract

            args = dict(tool_args or {})
            dataset_refs = [
                str(args[key])
                for key in ("name", "data", "source", "other_name", "save_as")
                if isinstance(args.get(key), str) and args[key].strip()
            ]
            if isinstance(args.get("datasets"), str):
                dataset_refs.extend(name.strip() for name in args["datasets"].split(",") if name.strip())
            if tool_name == "run_python" and isinstance(args.get("code"), str):
                import ast
                for node in ast.walk(ast.parse(args["code"])):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == "get_dataset" and node.args
                            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                        dataset_refs.append(node.args[0].value)
            if isinstance(structured_data, dict):
                for key in ("dataset", "derived_dataset"):
                    if isinstance(structured_data.get(key), str):
                        dataset_refs.append(structured_data[key])
            dataset_refs = list(dict.fromkeys(dataset_refs))
            detail_ref: dict[str, str] = {}
            structured_result_sha256 = ""
            if structured_data is not None:
                try:
                    from data_agent.tools._utils import persist_detail

                    # Provider call IDs are unbounded and may be reused across
                    # rounds. A fixed-length call hash plus the payload digest
                    # keeps the path stable, bounded, and immutable. The same
                    # helper is used for the reference shown to the model.
                    detail_key, structured_result_sha256 = _structured_detail_identity(
                        str(tool_call_id or tool_name), structured_data
                    )
                    detail_path = persist_detail(self.session_id, detail_key, structured_data)
                    detail_ref = {
                        "path": f"tool_outputs/{detail_path.name}",
                        "sha256": "sha256:" + hashlib.sha256(detail_path.read_bytes()).hexdigest(),
                    }
                except Exception as exc:
                    logger.warning(
                        "Structured result detail persistence failed",
                        extra={"extra_data": {"tool": tool_name, "error": str(exc)}},
                    )
            publication_groups = self._publication_groups_for_tool(
                structured_data,
                receipt_id=str(tool_call_id or ""),
                detail_ref=detail_ref,
            )
            receipt = add_receipt({
                "tool_name": tool_name,
                "tool_call_id": str(tool_call_id or ""),
                "arguments": args,
                "dataset_refs": dataset_refs,
                "data_identities": {
                    name: self.context.workspace.get_data_identity(name) for name in dataset_refs
                    if self.context.workspace.get_data_identity(name)
                },
                "structured_result_sha256": structured_result_sha256,
                "result_sha256": "sha256:" + hashlib.sha256(
                    (tool_msg_content or "").encode("utf-8")
                ).hexdigest(),
                "result_preview": (tool_msg_content or "")[:2000],
                "publication_facts": self._publication_facts_for_tool(structured_data),
                "publication_fact_groups": publication_groups.get("groups", []),
                "publication_scan": publication_groups.get("scan", {}),
                "detail_ref": detail_ref,
                "publication_contract": publication_contract(tool_name, structured_data, args=args),
            })
            receipt_id = str(receipt.get("id") or "")
            for group in receipt.get("publication_fact_groups") or []:
                if isinstance(group, dict):
                    group["receipt_id"] = receipt_id
                    group["scope_ref"] = receipt_id
            if receipt_id:
                self.context.turn_receipt_ids.append(receipt_id)
            turn_state = getattr(self.context, "turn_state", None)
            receipt_ids = getattr(turn_state, "tool_receipt_ids", None)
            if receipt_id and isinstance(receipt_ids, list):
                receipt_ids.append(receipt_id)
            return receipt_id
        except Exception as exc:
            logger.warning(
                "Tool receipt recording skipped",
                extra={"extra_data": {"tool": tool_name, "error": str(exc)}},
            )
            return ""

    @staticmethod
    def _publication_facts_for_tool(structured_data: dict | None) -> list[dict[str, str]]:
        if not isinstance(structured_data, dict):
            return []
        try:
            from data_agent.agent.publication_synthesis import extract_publication_facts

            # Receipts are the durable lossless-enough boundary.  The final
            # packet applies its own display budget after it knows the user's
            # complete request, so do not discard later business groups here.
            return extract_publication_facts(structured_data, max_facts=500)
        except Exception:
            return []

    @staticmethod
    def _publication_groups_for_tool(
        structured_data: dict | None,
        *,
        receipt_id: str = "",
        detail_ref: dict | None = None,
    ) -> dict:
        if not isinstance(structured_data, dict):
            return {"groups": [], "scan": {"scan_incomplete": False, "omitted_count": 0}}
        try:
            from data_agent.agent.publication_synthesis import extract_publication_fact_groups

            return extract_publication_fact_groups(
                structured_data,
                receipt_id=receipt_id,
                detail_ref=detail_ref,
            )
        except Exception:
            return {"groups": [], "scan": {"scan_incomplete": True, "unknown_count": True}}

    def _prepare_publication_packet(
        self,
        user_input: str,
        *,
        phase: str = "final",
        persist: bool = True,
    ) -> dict | None:
        """Build a receipt-backed hand-off for preview or final publication."""
        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return None
        try:
            from data_agent.agent.publication_synthesis import build_publication_packet

            receipt_ids = list(self.context.turn_receipt_ids)
            if not receipt_ids:
                prior_packet = getattr(self, "_turn_publication_packet", None)
                if isinstance(prior_packet, dict):
                    receipt_ids = [
                        str(source.get("receipt_id") or "")
                        for source in prior_packet.get("sources", [])
                        if isinstance(source, dict) and source.get("receipt_id")
                    ]
            packet = build_publication_packet(
                state,
                user_input=user_input,
                substantive_tools=(
                    _SUBSTANTIVE_TOOLS
                    if self._has_substantive_turn_evidence()
                    else _PUBLICATION_EVIDENCE_TOOLS
                ),
                receipt_ids=receipt_ids,
                requirement_ids=list(getattr(self.context, "turn_requirement_ids", []) or []),
                phase=phase,
            )
            self._turn_publication_packet = packet
            if packet.get("status") == "ready" and persist:
                self._commit_publication_packet(packet)
            return packet
        except Exception as exc:
            logger.warning(
                "Publication synthesis packet skipped",
                extra={"extra_data": {"session_id": self.session_id, "error": str(exc)}},
            )
            return None

    def _commit_publication_packet(self, packet: dict, final_text: str = "") -> dict:
        """Persist only the packet that crossed the terminal publication gate."""
        import hashlib

        committed = dict(packet)
        committed["phase"] = "final"
        if final_text:
            committed["answer_sha256"] = "sha256:" + hashlib.sha256(
                final_text.encode("utf-8")
            ).hexdigest()
            binding_seed = f"{committed.get('snapshot_digest', '')}|{committed['answer_sha256']}"
            committed["snapshot_packet_id"] = str(packet.get("id") or "")
            committed["id"] = "pub_" + hashlib.sha256(binding_seed.encode("utf-8")).hexdigest()[:12]
            state = getattr(self.context, "analysis_state", None)
            same_snapshot = [
                item for item in (getattr(state, "publication_packets", []) or [])
                if isinstance(item, dict) and item.get("snapshot_digest") == committed.get("snapshot_digest")
                and item.get("answer_sha256")
            ]
            same_answer = next((item for item in same_snapshot if item.get("answer_sha256") == committed["answer_sha256"]), None)
            if same_answer:
                committed["content_revision"] = int(same_answer.get("content_revision") or 1)
            else:
                committed["content_revision"] = 1 + max(
                    [int(item.get("content_revision") or 0) for item in same_snapshot] or [0]
                )
                if same_snapshot:
                    committed["supersedes_packet_id"] = str(same_snapshot[-1].get("id") or "")
        self._turn_publication_packet = committed
        state = getattr(self.context, "analysis_state", None)
        if state is not None:
            # The receipt artifact is part of the publication contract.  Write
            # it before adding the packet to live state so a failed write
            # cannot be mistaken for a complete, exportable publication.
            self._register_publication_receipt_artifact(committed, state)
            add_packet = getattr(state, "add_publication_packet", None)
            if callable(add_packet):
                add_packet(committed)
        return committed

    def _close_ledger_for_published_turn(self) -> None:
        """Host-owned bookkeeping at successful publication.

        The task ledger must not outlive the answer it served: open tasks of
        the active plan are closed with an explicit reason so the audit trail
        stays honest (R21: both M04 runs left eternally-pending tasks and the
        deterministic auditor rightly flags that residue).
        """
        try:
            from data_agent.session.task_manager import task_manager

            task_manager.close_open_tasks_for_publication(
                session_id=self.session_id,
                project_name=self.context.project_name or "",
                reason="superseded_by_publication",
            )
        except Exception:
            # Bookkeeping must never block the published answer; residue (if
            # any) is surfaced by the deterministic scenario auditor instead.
            return

    def _persist_accepted_answer(self, assistant_msg: dict, final_text: str) -> str | None:
        """Bind and persist one accepted terminal answer before exposure."""
        packet = getattr(self, "_turn_publication_packet", None)
        state = getattr(self.context, "analysis_state", None)
        prior_packets = list(getattr(state, "publication_packets", []) or []) if state is not None else []
        try:
            if isinstance(packet, dict) and packet.get("status") == "ready":
                committed = self._commit_publication_packet(packet, final_text)
                assistant_msg["publication_packet_id"] = str(committed.get("id") or "")
                assistant_msg["publication_snapshot_digest"] = str(committed.get("snapshot_digest") or "")
                assistant_msg["answer_sha256"] = str(committed.get("answer_sha256") or "")
                assistant_msg["publication_artifact_path"] = str(committed.get("publication_artifact_path") or "")
            assistant_msg["content"] = final_text
            self.messages.append(assistant_msg)
            self._auto_save()
            return None
        except Exception as exc:
            if self.messages and self.messages[-1] is assistant_msg:
                self.messages.pop()
            if state is not None:
                state.publication_packets[:] = prior_packets
            logger.error(
                "Accepted answer persistence failed",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )
            return (
                "最终回答已生成，但正文与来源绑定未能可靠保存，因此本轮未发布完整成功结果。"
                f"可恢复失败：{type(exc).__name__}: {exc}"
            )

    def _register_publication_receipt_artifact(self, packet: dict, state: Any) -> None:
        """Persist an openable receipt artifact for the published packet (B03).

        The browser artifacts panel and exports must show which sources,
        receipts, and omissions back the published answer. One artifact per
        packet id; re-preparing the same packet does not duplicate it.
        """
        receipted = getattr(self, "_publication_receipt_packet_ids", None)
        if receipted is None:
            receipted = set()
            self._publication_receipt_packet_ids = receipted
        packet_id = str(packet.get("id") or "")
        if not packet_id or packet_id in receipted:
            return
        from data_agent.agent.publication_synthesis import render_publication_receipt_markdown
        from data_agent.agent.workbench_view import build_workbench_view
        from data_agent.tools.report import _write_report_artifact

        workbench = build_workbench_view(state)
        content = render_publication_receipt_markdown(
            packet,
            pending_findings=workbench.get("pending_findings"),
            verified_total=workbench.get("verified_total"),
        )
        artifact_path = _write_report_artifact(
            self.session_id,
            f"计算来源说明 {packet_id}",
            content,
            "md",
            "publication_receipt",
            "publication",
        )
        packet["publication_artifact_path"] = artifact_path
        receipted.add(packet_id)

    def _render_finalized_publication(self, final_text: str) -> tuple[str | None, str | None]:
        """Validate the answer against persisted evidence without leaking audit records."""
        packet = getattr(self, "_turn_publication_packet", None)
        if not isinstance(packet, dict) or packet.get("status") != "ready":
            return final_text, None
        try:
            from data_agent.agent.publication_synthesis import (
                apply_answer_binding_coverage,
                parse_answer_bindings,
                render_bound_claims,
                validate_final_narrative,
            )

            visible_text, bindings, binding_issues = parse_answer_bindings(final_text, packet)
            if bindings is not None:
                packet["answer_bindings"] = bindings
                apply_answer_binding_coverage(packet, bindings)
            error = validate_final_narrative(visible_text, packet)
            if error and getattr(self, "_turn_origin_revision_issued", False):
                # Second pass after the origin revision: origin-class findings
                # no longer block; the host annotates the appendix instead.
                from data_agent.agent.publication_synthesis import (
                    drop_revision_only_issues,
                    validate_final_narrative_issues,
                )

                blocking, _revision_only = drop_revision_only_issues(
                    validate_final_narrative_issues(visible_text, packet)
                )
                if not blocking:
                    packet["provenance_unverified"] = True
                    error = None
            if binding_issues:
                binding_error = "\n".join(
                    f"[{issue['code']}] {issue['reason']}（位置：{issue['span']}）"
                    for issue in binding_issues
                )
                error = "\n".join(filter(None, [error, binding_error]))
            if error:
                return None, error
            # The free prose has passed its existing checks. A typed claim's
            # placeholder is now replaced at its own position by receipt-only
            # content; this is not a post-hoc disclaimer for incorrect prose.
            try:
                visible_text = render_bound_claims(visible_text, packet, bindings)
            except Exception as exc:
                return None, f"[invalid_scenario_binding] 宿主无法复算或渲染绑定情景：{exc}"
            # P08-02：通过发布检查的最终答复是合法的解析结果——带证据边界的
            # 拒答（如“无法预测 D30”）完成本轮，待解析状态随之满足。
            turn_state = getattr(self.context, "turn_state", None)
            if turn_state is not None and getattr(turn_state, "pending_fallback_resolution", False):
                turn_state.pending_fallback_resolution = False
            return visible_text.rstrip(), None
        except Exception as exc:
            logger.warning(
                "Publication synthesis rendering skipped",
                extra={"extra_data": {"session_id": self.session_id, "error": str(exc)}},
            )
            if "```answer-bindings" in final_text.lower() or "[[claim:" in final_text:
                return None, "[publication_render_error] 结构化答案绑定未能安全验证，未发布原始候选。"
            return final_text, None

    def _render_terminal_publication(
        self,
        user_input: str,
        final_text: str,
        *,
        persist: bool = True,
    ) -> tuple[str | None, str | None]:
        """Publish a receipt-backed appendix for every evidenced terminal answer.

        A model can choose to answer before the soft wrap-up threshold.  Its
        final response still crosses the same product publication boundary,
        so collecting the receipt packet only in forced finalization would
        leave normal short analyses ungrounded.
        """
        packet = None
        prior_packet = getattr(self, "_turn_publication_packet", None)
        if self._has_publishable_turn_evidence() or (
            isinstance(prior_packet, dict) and prior_packet.get("status") == "ready"
        ):
            # Always rebuild here.  A ready preview packet may predate late
            # receipts, EvidenceRecords, or the final verification report.
            packet = self._prepare_publication_packet(
                user_input,
                phase="final",
                persist=False,
            )
        elif prior_packet is None:
            packet = self._latest_publication_packet_for_presentation(user_input)
            if packet is not None:
                self._turn_publication_packet = packet
        if isinstance(packet, dict) and packet.get("status") == "ready":
            published_text, error = self._render_finalized_publication(final_text)
            if not error and published_text is not None and persist:
                self._commit_publication_packet(packet, published_text)
            return published_text, error
        return final_text, None

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
        if getattr(self, "_turn_synthesis_policy_injected", False):
            return
        intent = getattr(self, "_last_turn_intent", None)
        if intent is None or intent.intent_type not in ("directed_analysis", "comprehensive_report"):
            return
        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return
        evidence = getattr(state, "evidence_records", []) or []
        if not evidence:
            # An explicit competing-hypothesis task needs stable hypothesis
            # IDs before the model can attach receipt-backed support/refute
            # relations.  Create and expose only that deterministic brief;
            # ordinary analyses keep the existing no-evidence fast path.
            try:
                from data_agent.agent.question_need_detector import explicit_task_reason
                from data_agent.agent.trust_workflow_runtime import maybe_create_hypothesis_set
                from data_agent.agent.hypotheses import hydrate_hypothesis_refs, hypotheses_prompt_brief

                if explicit_task_reason(user_input) in {"hypothesis_task", "competing_hypotheses", "evidence_reassessment"}:
                    maybe_create_hypothesis_set(user_input, intent, state)
                    hydrated = hydrate_hypothesis_refs(list(getattr(state, "hypothesis_sets", []) or []))
                    brief = hypotheses_prompt_brief(state, hydrated=hydrated)
                    if brief:
                        self._turn_synthesis_policy_instruction = brief
            except Exception as exc:
                logger.warning(
                    "Pre-evidence hypothesis brief skipped",
                    extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
                )
            return

        if not getattr(self, "_turn_verification_injected", False):
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
        instruction = build_synthesis_instruction(policy)
        try:
            from data_agent.agent.hypotheses import hydrate_hypothesis_refs, hypotheses_prompt_brief

            hydrated = hydrate_hypothesis_refs(list(getattr(state, "hypothesis_sets", []) or []))
            brief = hypotheses_prompt_brief(state, hydrated=hydrated)
            if brief:
                instruction = f"{instruction}\n{brief}"
        except Exception as exc:
            logger.warning(
                "Hypothesis brief injection skipped",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )
        self._turn_synthesis_policy_instruction = instruction
        self._turn_synthesis_policy_injected = True

    def _verify_before_publication(self, user_input: str) -> None:
        """Refresh deterministic claim verification at the publication boundary.

        Tool rounds may create an EvidenceRecord after the earlier synthesis
        hook ran.  A final answer must not be published with that fresh record
        still labelled unverified in the Workbench.
        """
        state = getattr(self.context, "analysis_state", None)
        if state is None or not getattr(state, "evidence_records", None):
            return
        try:
            from data_agent.agent.trust_workflow_runtime import maybe_verify_turn_claims

            maybe_verify_turn_claims(user_input, state)
        except Exception as exc:
            logger.warning(
                "Publication-boundary verification skipped",
                extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
            )
        # Hypothesis states are refreshed on the same evidence snapshot as
        # verification, so a final answer never ships with stale verdicts.
        intent = getattr(self, "_last_turn_intent", None)
        if intent is not None:
            try:
                from data_agent.agent.trust_workflow_runtime import maybe_create_hypothesis_set

                maybe_create_hypothesis_set(user_input, intent, state)
            except Exception as exc:
                logger.warning(
                    "Publication-boundary hypothesis refresh skipped",
                    extra={"extra_data": {"error": str(exc), "session_id": self.session_id}},
                )

    @staticmethod
    def _budget_truncation_message(response) -> str | None:
        """Explicit guidance when reasoning exhausted the output budget.

        The client already attempted its bounded budget escalations before the
        response surfaced here; remaining truncation needs user action, not a
        silent empty answer.
        """
        if response is None or getattr(response, "finish_reason", None) != "length":
            return None
        if (getattr(response, "text", "") or "").strip():
            return None
        return (
            "模型推理耗尽了输出预算（已自动提升预算重试仍被截断）。"
            "请在设置中提高 MAX_TOKENS 或更换模型后重试。"
        )

    def _should_continue_for_analysis_quality(self, user_input: str, final_text: str) -> bool:
        hypothesis_gaps = self._competing_hypothesis_quality_gaps(user_input)
        self._turn_analysis_quality_gaps = hypothesis_gaps
        if hypothesis_gaps:
            return not getattr(self, "_turn_final_guard_injected", False)
        return self._is_analysis_quality_guard_candidate()

    def _competing_hypothesis_quality_gaps(self, user_input: str) -> list[str]:
        """Return missing audit structures for an explicit hypothesis task.

        The gate is deliberately host-owned: a plan-shaped object and one
        relation-shaped record are not completion evidence.  Per the
        2026-09-21 goal realignment the task ledger is host bookkeeping:
        unfinished projected tasks no longer block publication (both R21 M04
        runs died on that), and the host closes open tasks with an explicit
        reason once the final answer publishes.  What still blocks is the
        absence of the structured artifacts themselves.
        """
        try:
            from data_agent.agent.question_need_detector import explicit_task_reason

            reason = explicit_task_reason(user_input)
        except Exception:
            return []
        if reason not in {"hypothesis_task", "competing_hypotheses", "evidence_reassessment"}:
            return []
        state = getattr(self.context, "analysis_state", None)
        if state is None:
            return ["analysis state is missing"]
        gaps: list[str] = []
        plan = getattr(state, "analysis_plan", None)
        if not isinstance(plan, dict) or not str(plan.get("id") or "").strip():
            gaps.append("record_analysis_plan has not produced a current plan")
        hypothesis_sets = getattr(state, "hypothesis_sets", None)
        if not isinstance(hypothesis_sets, list) or not hypothesis_sets:
            gaps.append("no persisted competing-hypothesis set exists")
        evidence_records = getattr(state, "evidence_records", None)
        has_relation_proposal = any(
            isinstance(record, dict)
            and isinstance(record.get("competing_hypotheses"), list)
            and bool(record.get("competing_hypotheses"))
            for record in (evidence_records or [])
        )
        if not has_relation_proposal:
            gaps.append("no evidence record contains structured hypothesis relations")
        return gaps

    def _analysis_quality_failure_after_guard(self) -> str | None:
        gaps = list(getattr(self, "_turn_analysis_quality_gaps", []) or [])
        if not getattr(self, "_turn_final_guard_injected", False) or not gaps:
            return None
        return "[analysis_audit_incomplete] 竞争假设审计结构仍不完整：" + "; ".join(gaps)

    def _is_analysis_quality_guard_candidate(self) -> bool:
        if getattr(self, "_turn_final_guard_injected", False):
            return False
        intent = getattr(self, "_last_turn_intent", None)
        if intent is None or intent.intent_type not in ("directed_analysis", "comprehensive_report"):
            return False
        if getattr(intent, "execution_readiness", "") not in ("ready", "pending_load"):
            return False
        tools_used = set(getattr(self, "_turn_tools_used", []))
        if tools_used & _SUBSTANTIVE_TOOLS:
            return False
        # Any tool use without a substantive analysis tool (including browsing
        # helpers like list_files that fall outside the profiling set) still
        # means the turn only profiled data and must not answer yet.
        if not tools_used:
            return False
        return True

    def _inject_analysis_quality_guard(self) -> None:
        self._turn_final_guard_injected = True
        if self.messages:
            last_msg = self.messages[-1]
            if last_msg.get("role") == "assistant" and not last_msg.get("tool_calls"):
                self.messages.pop()
        gaps = list(getattr(self, "_turn_analysis_quality_gaps", []) or [])
        content = (
            _HYPOTHESIS_QUALITY_GUARD_MESSAGE.format(gaps="; ".join(gaps))
            if gaps else _ANALYSIS_QUALITY_GUARD_MESSAGE
        )
        self.messages.append({"role": "system", "content": content})

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
        from data_agent.agent.confirmation.policy import RequestDisposition
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
        # IC2/设计§5：REUSED 恢复既有答案，不对旧 resolved record 再悬挂；
        # advisory/rejected 同样以一次正常工具响应继续本轮。
        if (
            request_result.disposition == RequestDisposition.REUSED
            or record_is_none(request_result)
        ):
            return self._nonblocking_confirmation_response(request_result)

        record = request_result.record
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

    def _nonblocking_confirmation_response(self, request_result) -> str:
        """Tool-response text for advisory/reused/rejected confirmation results."""
        from data_agent.agent.confirmation.policy import RequestDisposition

        if (
            request_result.disposition == RequestDisposition.REUSED
            and request_result.reused_confirmation_id
        ):
            try:
                service = self._confirmation_runtime()
                reused = service.get(self.session_id, request_result.reused_confirmation_id)
                answer = reused.response if reused is not None else None
            except Exception:
                answer = None
            if answer not in (None, "", [], {}):
                return (
                    f"此前的回答仍然适用：{json.dumps(answer, ensure_ascii=False, default=str)}。"
                    "如业务口径已变化，请说明新的具体口径。"
                )
        return (
            f"该问题无需用户确认：{request_result.reason}。"
            "请直接继续当前任务；只有当具体业务口径（分母/时间窗/人群/成本范围等）"
            "确实缺失且会改变结论时才询问用户。"
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
            # IC2/设计§5：自动门的 advisory/rejected 不悬挂不抛异常——记日志后
            # 让本轮继续（该缺口已按策略判定无需用户决策）。
            logger.info(
                "Auto confirmation downgraded to non-blocking",
                extra={"extra_data": {
                    "session_id": self.session_id,
                    "reason": request_result.reason,
                }},
            )
            return None

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
        self.clear_interrupt()
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
        self.clear_interrupt()
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
            # Persist the datasets readable in this execution scope before
            # publishing the terminal. No broader storage access is granted.
            from data_agent.session.workspace import workspace
            scope = self.context.workspace_scope
            if scope is not None and scope.phase in {"legacy", "execution"}:
                names = list(workspace.list_datasets())
                for name in names:
                    workspace.persist_dataset(self.session_id, name)
                if names:
                    workspace.save_meta(self.session_id)
            if self.context.analysis_state is not None:
                self.context.analysis_state.save()
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
        self._resolve_confirmation(susp, user_response)
        resumed_input = self._build_resume_user_input(susp, user_response)
        confirmation_id = susp.confirmation_id or susp.suspension_id

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
                from data_agent.session.task_manager import task_manager

                state = current_analysis_state()
                if state is not None:
                    normalized = str(answer or "").strip().lower()
                    should_apply = normalized not in {"skipped", "cancelled"}
                    resolved = state.resolve_confirmation(susp.suspension_id, answer)
                    task = task_manager.get(susp.related_task_id) if susp.related_task_id else None
                    if resolved is None and task is not None:
                        for confirmation_id in task.get("confirmation_ids") or []:
                            resolved = state.resolve_confirmation(str(confirmation_id), answer)
                            if resolved is not None:
                                break
                    if resolved is None and susp.related_spec_id:
                        candidates = [
                            item for item in state.pending_confirmations
                            if item.get("status", "pending") == "pending"
                            and item.get("related_spec_id") == susp.related_spec_id
                            and (
                                not susp.confirmation_type
                                or item.get("confirmation_type") == susp.confirmation_type
                            )
                        ]
                        if len(candidates) == 1:
                            candidate = candidates[0]
                            resolved = state.resolve_confirmation(str(candidate.get("id") or ""), answer)
                    if should_apply:
                        state.apply_state_updates(susp.state_updates, answer=answer)
                    elif resolved is not None:
                        resolved["status"] = normalized
                    state.save()
                if susp.related_task_id:
                    current_task = task_manager.get(susp.related_task_id) or {}
                    confirmation_ids = list(current_task.get("confirmation_ids") or [])
                    if susp.suspension_id and susp.suspension_id not in confirmation_ids:
                        confirmation_ids.append(susp.suspension_id)
                    task_manager.update(
                        susp.related_task_id,
                        status=(
                            "superseded"
                            if str(answer or "").strip().lower() in {"skipped", "cancelled"}
                            else "completed"
                        ),
                        confirmation_ids=confirmation_ids,
                        result_summary=f"用户确认: {answer}",
                        completed_by="confirmation",
                    )
            except Exception as e:
                logger.warning("Failed to resolve confirmation", extra={"extra_data": {"error": str(e)}})

    def _stream_llm_round(self, round_num: int):
        """Execute one LLM round using streaming. Yields SSE event dicts.

        The caller buffers text until the round is durably persisted, then
        decides whether it is safe to publish it.  When the round completes,
        the final Response is returned via a ``{"type": "_response", ...}``
        event so the caller can decide what to do next.
        """
        from data_agent.llm.client import StreamTextDelta, StreamComplete

        yield {"type": "llm_call_start", "round": round_num}

        response = None
        streamed_text = ""

        # Defensive: repair any broken tool_call sequences from prior turns
        self._repair_broken_tool_sequence()

        from data_agent.llm.request_policy import close_stream
        provider_messages = self._provider_messages()
        if provider_messages is None:
            yield {
                "type": "_round_failure",
                "code": "invalid_tool_message_sequence",
                "detail": "会话工具消息存在不可配对条目，已阻止本次 Provider 投递；请回退或重开该轮。",
            }
            return
        stream = self.client.stream_chat_structured(
            messages=provider_messages, tools=self._tools_for_current_round(), system=self._get_system_prompt(),
        )
        try:
            for ev in stream:
                if self._interrupt_event.is_set():
                    return
                if isinstance(ev, StreamTextDelta):
                    streamed_text += ev.text
                    yield {"type": "text_delta", "text": ev.text, "turn_id": None}
                elif isinstance(ev, StreamComplete):
                    response = ev.response
        except Exception as exc:
            if getattr(exc, "error_domain", "") == "acceptance":
                code = "acceptance_stopped"
            else:
                code = str(exc) if type(exc).__name__ == "JourneyStructureError" else "provider_request_failed"
            detail = _provider_failure_detail(exc)
            logger.warning("Streaming request failed", extra={"extra_data": {
                "error": type(exc).__name__, "code": code, "detail": detail,
            }})
            yield {"type": "_round_failure", "code": code, "detail": detail}
            return
        finally:
            close_stream(stream)

        # Internal event — caller uses this to continue the loop
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
                    error_payload = {"error": str(exc), "error_type": "budget_exceeded"}
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(error_payload, ensure_ascii=False),
                    })
                    self._fill_remaining_tool_responses(response.tool_calls, i + 1, str(exc))
                    if "Fallback Python result" in str(exc):
                        # P08-02: 指明两条合法继续路径，而不是让错误像终态。
                        self.messages.append({
                            "role": "system",
                            "content": _FALLBACK_RESOLUTION_GUIDANCE,
                        })
                        # This is a recoverable policy rejection, not a failed
                        # turn. Emit paired attempted-call/result events so the
                        # browser and durable message history observe the same
                        # lifecycle while the next LLM round can finalize.
                        for offset, blocked_tc in enumerate(response.tool_calls[i:]):
                            blocked_payload = error_payload if offset == 0 else {
                                "error": str(exc),
                                "error_type": "early_termination",
                            }
                            yield {
                                "type": "tool_call",
                                "tool_call_id": blocked_tc.id,
                                "name": blocked_tc.name,
                                "arguments": blocked_tc.arguments,
                                "round": round_num,
                            }
                            yield {
                                "type": "tool_result",
                                "tool_call_id": blocked_tc.id,
                                "name": blocked_tc.name,
                                "web": blocked_payload,
                                "duration_ms": 0,
                            }
                        return
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

            scope_error = _scope_guard(self, tc.name, tc.arguments)
            if scope_error:
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
                self._record_turn_tool_result(tc.name, scope_error, tc.arguments, tc.id)
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
            except UserConfirmationRequired as ucc:
                susp = self._suspend_for_confirmation_request(
                    ucc,
                    turn_id=str(getattr(tc, "id", "") or "direct_user_question"),
                )
                if isinstance(susp, str):
                    # IC2：advisory/reused 的直接询问得到一次正常工具响应并继续
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": susp,
                    })
                    yield {"type": "tool_result", "tool_call_id": tc.id, "name": tc.name, "web": None, "duration_ms": 0}
                    continue
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Suspended for user confirmation. confirmation_id={susp.confirmation_id or susp.suspension_id}",
                })
                self._fill_remaining_tool_responses(response.tool_calls, i + 1, "Suspended for user confirmation")
                yield self._suspended_event(susp)
                return  # stop processing further tool calls

            if post_scope.phase == "error":
                scope_error = json.dumps(
                    {"error": post_scope.message, "error_type": post_scope.error_type},
                    ensure_ascii=False,
                )
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
                self._record_turn_tool_result(tc.name, scope_error, tc.arguments, tc.id)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": scope_error,
                })
                yield {"type": "error", "message": scope_error}
                continue

            duration_ms = int((time.monotonic() - t0) * 1000)
            tool_msg_content = self._compact_tool_output(tool_result, tc)

            if tool_msg_content.startswith('{"error":') or tool_msg_content.startswith('{"error": '):
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, tool_msg_content)
                tool_msg_content = registry.format_result(tc.name, tool_result)

            elif turn_state is not None:
                turn_state.record_tool_success()

            self._record_turn_tool_result(
                tc.name,
                tool_msg_content,
                tc.arguments,
                tc.id,
                getattr(tool_result, "data", None),
            )
            self._auto_track_task_progress(tc.name, True)

            # Phase 3: check for stage regression after tool execution
            regression_msg = None
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

    def _stream_turn_impl(self, user_input: str, turn_context: str = ""):
        """Generator variant of run_turn for SSE streaming. Yields event dicts."""
        import time

        logger.info("Stream turn started", extra={"extra_data": {"session": self.session_id}})
        if not getattr(self, "_web_interrupt_prepared", False):
            self.clear_interrupt()
        self._web_interrupt_prepared = False
        self._quality_reminder_injected = False
        self._reset_turn_tracking()
        # Inject interrupt context if previous turn was interrupted
        if self._was_last_turn_interrupted():
            context = self._build_interrupt_context(user_input)
            self.messages.append({"role": "user", "content": context})
        self.messages.append({"role": "user", "content": user_input})
        if turn_context:
            self.messages.append({"role": "system", "content": turn_context})
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

        yield from self._stream_analysis_loop(user_input)

    def _stream_analysis_loop(self, user_input: str):
        """Shared normal/resumed execution and durable publication lifecycle."""
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

            _microcompact(self.session_id, self.messages)
            if _estimate_tokens(self.messages) > self.token_threshold:
                self.messages[:] = compact_history(
                    self.session_id, self.auxiliary_llm_client or self.client, self.messages,
                    self._compact_state, token_threshold=self.token_threshold,
                )

            blocked_confirmation = self._runtime_confirmation_checkpoint()
            if blocked_confirmation is not None:
                yield self._suspended_event(blocked_confirmation)
                return

            # A completed final answer must be persisted before any of its
            # text reaches the browser.  Buffering one LLM round also lets us
            # discard a premature final response when the quality guard needs
            # another substantive-tool round.
            buffer_text_events = True
            pending_text_events = []
            separator_event = None

            # Inject paragraph separator between streaming rounds
            if round_num > 1:
                separator_event = {"type": "text_delta", "text": "\n\n"}
                if buffer_text_events:
                    pending_text_events.append(separator_event)
                else:
                    yield separator_event

            response = None
            streamed_text = ""
            round_failure = ""
            round_failure_detail = ""
            for ev in self._stream_llm_round(round_num):
                if ev["type"] == "_response":
                    response = ev["response"]
                    streamed_text = ev["streamed_text"]
                elif ev["type"] == "_round_failure":
                    round_failure = str(ev.get("code") or "")
                    round_failure_detail = str(ev.get("detail") or "")
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

            if round_failure:
                if round_failure == "round_cap_exceeded":
                    message = f"LLM 轮次已达到上限（{round_failure}）"
                else:
                    message = f"LLM 请求失败（{round_failure}）"
                    if round_failure_detail:
                        message += f"：{round_failure_detail}"
                yield {"type": "error", "message": message}
                return

            if response is None:
                yield {"type": "error", "message": "LLM 返回为空"}
                return

            budget_truncation = self._budget_truncation_message(response)
            if budget_truncation:
                yield {"type": "error", "message": budget_truncation}
                return

            if (
                getattr(self, "_turn_finalization_mode", False)
                and not response.has_tool_calls
                and self._contains_unexecuted_tool_markup(response.text)
            ):
                if self._recover_finalization_tool_markup():
                    continue
                yield {"type": "error", "message": "最终化轮未生成可发布回答（检测到未执行工具标记）"}
                return

            assistant_msg: dict = {"role": "assistant", "content": response.text or ""}
            if response.reasoning_content:
                assistant_msg["reasoning_content"] = response.reasoning_content
            if response.text:
                final_text = response.text

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

            if not response.has_tool_calls:
                self._verify_before_publication(user_input)
                published_text, publication_error = self._render_terminal_publication(
                    user_input, final_text, persist=False
                )
                if publication_error:
                    if self._recover_publication_narrative(assistant_msg, publication_error):
                        continue
                    yield {"type": "error", "message": publication_error}
                    return
                final_text = published_text or final_text
                assistant_msg["content"] = final_text
                pending_text_events = ([separator_event] if separator_event else []) + [{"type": "text_delta", "text": final_text, "turn_id": None}]
                if self._should_continue_for_analysis_quality(user_input, final_text):
                    rejected = dict(assistant_msg)
                    rejected["publication_rejected"] = True
                    self.messages.append(rejected)
                    self._inject_analysis_quality_guard()
                    continue
                analysis_quality_failure = self._analysis_quality_failure_after_guard()
                if analysis_quality_failure:
                    yield {"type": "error", "message": analysis_quality_failure}
                    return
                blocked_confirmation = self._runtime_confirmation_checkpoint()
                if blocked_confirmation is not None:
                    rejected = dict(assistant_msg)
                    rejected["publication_rejected"] = True
                    rejected["publication_pending_confirmation"] = True
                    self.messages.append(rejected)
                    yield self._suspended_event(blocked_confirmation)
                    return
                self._maybe_archive(user_input, final_text)
                persistence_error = self._persist_accepted_answer(assistant_msg, final_text)
                if persistence_error:
                    yield {"type": "error", "message": persistence_error}
                    return
                self._close_ledger_for_published_turn()
                for ev in pending_text_events:
                    yield ev
                return

            self.messages.append(assistant_msg)

            if buffer_text_events:
                # This is an intermediate tool-call round rather than the
                # final answer, but it is still browser-visible text.  Persist
                # the assistant message before publishing it so refresh/replay
                # cannot lose text that the user already saw.
                self._auto_save()
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
            self._maybe_inject_wrap_up(round_num, user_input)

            # Check interrupt after tool calls
            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

            # Safety valve: hard stop at 310 rounds
            if round_num >= 310:
                logger.warning("Safety valve triggered", extra={"extra_data": {
                    "session": self.session_id, "rounds": round_num,
                }})
                yield {"type": "error", "message": "分析未完成：已达到安全轮次上限。"}
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
        self._resolve_confirmation(susp, user_response)
        resumed_input = self._build_resume_user_input(susp, user_response)
        confirmation_id = susp.confirmation_id or susp.suspension_id

        self.messages.append({"role": "user", "content": (
            f"<confirmation_response confirmation_id=\"{confirmation_id}\" suspension_id=\"{confirmation_id}\" version=\"{susp.version}\">\n"
            f"Question: {susp.question}\n"
            f"User answered: {user_response}\n"
            f"</confirmation_response>"
        )})

        yield from self._stream_analysis_loop(resumed_input)

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
                return FinalResponse(content=(final_text or "分析已中断。") + "\n\n[已中断]")

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
                    if "Fallback Python result" in str(exc):
                        self.messages.append({
                            "role": "system",
                            "content": _FALLBACK_RESOLUTION_GUIDANCE,
                        })
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

        scope_error = _scope_guard(self, tc.name, tc.arguments)
        if scope_error:
            if turn_state is not None:
                turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
            self._record_turn_tool_result(tc.name, scope_error, tc.arguments, tc.id)
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
        except UserConfirmationRequired as ucc:
            susp = self._suspend_for_confirmation_request(
                ucc,
                turn_id=str(getattr(tc, "id", "") or "direct_user_question"),
            )
            if isinstance(susp, str):
                # IC2：advisory/reused 的直接询问得到一次正常工具响应并继续
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": susp,
                })
                return None
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": f"Suspended for user confirmation. confirmation_id={susp.confirmation_id or susp.suspension_id}",
            })
            self._fill_remaining_tool_responses(tool_calls, index + 1, "Suspended for user confirmation")
            return susp

        if post_scope.phase == "error":
            scope_error = json.dumps(
                {"error": post_scope.message, "error_type": post_scope.error_type},
                ensure_ascii=False,
            )
            if turn_state is not None:
                turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
            self._record_turn_tool_result(tc.name, scope_error, tc.arguments, tc.id)
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": scope_error,
            })
            return None

        tool_msg_content = self._compact_tool_output(tool_result, tc)

        if tool_msg_content.startswith('{"error":') or tool_msg_content.startswith('{"error": '):
            if turn_state is not None:
                turn_state.record_tool_error(tc.name, tc.arguments, tool_msg_content)
            tool_msg_content = registry.format_result(tc.name, tool_result)
            logger.warning("Tool error", extra={"extra_data": {"tool": tc.name, "error": tool_msg_content[:200]}})
        elif turn_state is not None:
            turn_state.record_tool_success()

        self._record_turn_tool_result(
            tc.name,
            tool_msg_content,
            tc.arguments,
            tc.id,
            getattr(tool_result, "data", None),
        )
        self._auto_track_task_progress(tc.name, tool_msg_content and not tool_msg_content.startswith('{"error":'))

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
        """Execute read-only tool calls in parallel with structured result facts."""
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

        def _run_tool(tc):
            try:
                scope_error = guard_errors.get(tc.id, "")
                if scope_error:
                    return (tc, scope_error, None, None)
                t0 = time.monotonic()
                with self.__context_operation("use"):
                    tool_result = registry.execute(tc.name, tc.arguments)
                post_scope = self.__context_operation("refresh")
                if post_scope.phase == "error":
                    scope_error = json.dumps(
                        {"error": post_scope.message, "error_type": post_scope.error_type},
                        ensure_ascii=False,
                    )
                    if turn_state is not None:
                        turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
                    return (tc, scope_error, post_scope, None)
                duration_ms = int((time.monotonic() - t0) * 1000)
                tool_msg_content = self._compact_tool_output(tool_result, tc)

                if tool_msg_content.startswith('{"error":') or tool_msg_content.startswith('{"error": '):
                    if turn_state is not None:
                        turn_state.record_tool_error(tc.name, tc.arguments, tool_msg_content)
                    tool_msg_content = registry.format_result(tc.name, tool_result)
                elif turn_state is not None:
                    turn_state.record_tool_success()

                return (tc, tool_msg_content, None, getattr(tool_result, "data", None))
            except Exception as e:
                error_content = json.dumps({"error": str(e)}, ensure_ascii=False)
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, error_content)
                return (tc, error_content, None, None)

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
                tc_obj, content, refresh_error, structured_data = future.result()
                if refresh_error is not None:
                    self.__context_operation("record_worker_refresh_error", refresh_error)
                results[tc_obj.id] = (tc_obj, content, structured_data)

        # Return in original order
        return [results[tc.id] for tc in tool_calls if tc.id in results]

    def _loop_impl(self, user_input: str = "") -> LoopResult:
        """循环调用 LLM 直到获得最终文本回复。"""
        final_text = ""
        round_num = 0

        # 惰性初始化 MCP
        self._ensure_mcp_initialized()

        while True:
            round_num += 1
            # 协作式中断检查
            if self._interrupt_event.is_set():
                logger.info("Turn interrupted by user")
                return FinalResponse(content=(final_text or "分析已中断。") + "\n\n[已中断]")

            # Safety valve: force summary at high round count
            if round_num == 300:
                self.messages.append({"role": "user", "content": (
                    "分析已进行超过 300 轮工具调用。请立即停止调用工具，"
                    "基于已获得的所有数据和分析结果输出总结报告。"
                )})

            _microcompact(self.session_id, self.messages)
            if _estimate_tokens(self.messages) > self.token_threshold:
                self.messages[:] = compact_history(
                    self.session_id, self.auxiliary_llm_client or self.client, self.messages,
                    self._compact_state, token_threshold=self.token_threshold,
                )

            blocked_confirmation = self._runtime_confirmation_checkpoint()
            if blocked_confirmation is not None:
                return blocked_confirmation

            # Defensive: repair any broken tool_call sequences from prior turns
            self._repair_broken_tool_sequence()

            provider_messages = self._provider_messages()
            if provider_messages is None:
                return FinalResponse(content=(
                    "会话工具消息存在不可配对条目，已阻止本次请求；"
                    "请回退到上一完整轮次或重开该轮后再继续。"
                ))
            response = self.client.chat(
                messages=provider_messages,
                tools=self._tools_for_current_round(),
                system=self._get_system_prompt(),
            )

            if (
                getattr(self, "_turn_finalization_mode", False)
                and not response.has_tool_calls
                and self._contains_unexecuted_tool_markup(response.text)
            ):
                if self._recover_finalization_tool_markup():
                    continue
                return FinalResponse(content="最终化轮未生成可发布回答（检测到未执行工具标记）。")

            assistant_msg: dict = {"role": "assistant", "content": response.text or ""}
            if response.reasoning_content:
                assistant_msg["reasoning_content"] = response.reasoning_content
            if response.text:
                final_text = response.text

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

            if not response.has_tool_calls:
                self._verify_before_publication(user_input)
                published_text, publication_error = self._render_terminal_publication(
                    user_input, final_text, persist=False
                )
                if publication_error:
                    if self._recover_publication_narrative(assistant_msg, publication_error):
                        continue
                    return FinalResponse(content=publication_error)
                final_text = published_text or final_text
                assistant_msg["content"] = final_text
                if self._should_continue_for_analysis_quality(user_input, final_text):
                    rejected = dict(assistant_msg)
                    rejected["publication_rejected"] = True
                    self.messages.append(rejected)
                    self._inject_analysis_quality_guard()
                    continue
                analysis_quality_failure = self._analysis_quality_failure_after_guard()
                if analysis_quality_failure:
                    return FinalResponse(content=analysis_quality_failure)
                blocked_confirmation = self._runtime_confirmation_checkpoint()
                if blocked_confirmation is not None:
                    rejected = dict(assistant_msg)
                    rejected["publication_rejected"] = True
                    rejected["publication_pending_confirmation"] = True
                    self.messages.append(rejected)
                    return blocked_confirmation
                persistence_error = self._persist_accepted_answer(assistant_msg, final_text)
                if persistence_error:
                    return FinalResponse(content=persistence_error)
                self._close_ledger_for_published_turn()
                return FinalResponse(content=final_text)

            self.messages.append(assistant_msg)

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
                    results = self._execute_tools_parallel(tool_calls)
                    for tc, tool_msg_content, structured_data in results:
                        self._record_turn_tool_result(
                            tc.name,
                            tool_msg_content,
                            tc.arguments,
                            tc.id,
                            structured_data,
                        )
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
            self._maybe_inject_wrap_up(round_num, user_input)

            # Safety valve: hard stop at 310 rounds
            if round_num >= 310:
                logger.warning("Safety valve triggered", extra={"extra_data": {
                    "session": self.session_id, "rounds": round_num,
                }})
                return FinalResponse(content=final_text + "\n\n分析未完成：已达到安全轮次上限。")

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
        """Serialize messages for suspension storage.

        P08-04: assistant.tool_calls 与 tool.tool_call_id 的配对字段必须
        保留——只写 role/content 会在恢复后制造孤立的 tool 消息，触发
        Provider 400。参数字符串截断到 2000 字符控制快照体积。
        """
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
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                preserved_calls = []
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") if isinstance(call.get("function"), dict) else {}
                    preserved_calls.append({
                        "id": str(call.get("id") or ""),
                        "type": str(call.get("type") or "function"),
                        "function": {
                            "name": str(function.get("name") or ""),
                            "arguments": str(function.get("arguments") or "")[:2000],
                        },
                    })
                if preserved_calls:
                    m["tool_calls"] = preserved_calls
            tool_call_id = msg.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                m["tool_call_id"] = tool_call_id
            serialized.append(m)
        return serialized

    def _provider_messages(self) -> list[dict] | None:
        """P08-04: 构造投递前副本——剔除孤立 tool 消息并校验成对完整性。

        原始历史不被修改（审计保留）。剔除记录警告；校验仍有违规时返回
        None，调用方走可恢复的本地诊断而不是把非法序列发给 Provider。
        """
        from data_agent.agent.compact import (
            drop_orphan_tool_messages,
            validate_tool_message_sequence,
        )

        provider_copy, dropped = drop_orphan_tool_messages(self.messages)
        if dropped:
            logger.warning(
                "Dropped orphan tool messages from provider copy",
                extra={"extra_data": {"dropped": dropped[:10], "session_id": self.session_id}},
            )
        violations = validate_tool_message_sequence(provider_copy)
        if violations:
            logger.warning(
                "Tool message sequence invalid before provider delivery",
                extra={"extra_data": {"violations": violations[:10], "session_id": self.session_id}},
            )
            return None
        return provider_copy


def _create_streaming_context_methods(loop_context_operation, stream_impl, resume_impl):
    """Bind a loop context for exactly the lifetime of each streaming generator."""

    def stream_turn(self, user_input: str, turn_context: str = ""):
        with loop_context_operation(self, "use"):
            yield from stream_impl(self, user_input, turn_context)

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
