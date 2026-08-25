from __future__ import annotations

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
}

_ANALYSIS_QUALITY_GUARD_MESSAGE = (
    "<analysis_quality_guard>\n"
    "The user requested analysis, but this turn has only loaded or profiled data. "
    "Continue by creating or applying an AnalysisSpec, running relevant analysis steps, "
    "and recording evidence before giving the final answer.\n"
    "</analysis_quality_guard>"
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
        """Restore workspace datasets from persisted metadata.

        Strategy A: reload from original file path.
        Strategy B: fall back to parquet backup in session directory.
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
        for name, info in meta.items():
            df = None

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

            # Strategy B: fall back to local dataset backup
            if df is None:
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
                workspace.add(name, df)
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
        self._turn_loaded_data = False
        self._turn_final_guard_injected = False
        self._turn_verification_injected = False
        self._turn_synthesis_policy_injected = False
        self._turn_synthesis_policy_instruction = ""

    def _tool_content_is_error(self, content: str) -> bool:
        stripped = (content or "").lstrip()
        lowered = stripped.lower()
        return (
            stripped.startswith('{"error":')
            or stripped.startswith('{"error": ')
            or lowered.startswith("error")
        )

    def _record_turn_tool_result(self, tool_name: str, tool_msg_content: str) -> None:
        if not hasattr(self, "_turn_tools_used"):
            self._reset_turn_tracking()
        self._turn_tools_used.append(tool_name)
        if tool_name == "load_data" and not self._tool_content_is_error(tool_msg_content):
            self._turn_loaded_data = True

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
        self._turn_synthesis_policy_instruction = build_synthesis_instruction(policy)
        self._turn_synthesis_policy_injected = True

    def _should_continue_for_analysis_quality(self, user_input: str, final_text: str) -> bool:
        return self._is_analysis_quality_guard_candidate()

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
        if not tools_used or not tools_used <= _PROFILING_TOOLS:
            return False
        return True

    def _inject_analysis_quality_guard(self) -> None:
        self._turn_final_guard_injected = True
        if self.messages:
            last_msg = self.messages[-1]
            if last_msg.get("role") == "assistant" and not last_msg.get("tool_calls"):
                self.messages.pop()
        self.messages.append({"role": "system", "content": _ANALYSIS_QUALITY_GUARD_MESSAGE})

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

        # Defensive: repair any broken tool_call sequences from prior turns
        self._repair_broken_tool_sequence()

        try:
            for ev in self.client.stream_chat_structured(
                messages=self.messages,
                tools=registry.active_definitions() or None,
                system=self._get_system_prompt(),
            ):
                # Check interrupt between streaming chunks
                if self._interrupt_event.is_set():
                    yield {"type": "_response", "response": response, "streamed_text": streamed_text}
                    return

                if isinstance(ev, StreamTextDelta):
                    streamed_text += ev.text
                    yield {"type": "text_delta", "text": ev.text, "turn_id": None}
                elif isinstance(ev, StreamComplete):
                    response = ev.response
        except Exception as e:
            logger.warning("Streaming LLM call failed, falling back to sync", extra={"extra_data": {"error": str(e)}})
            # Fallback to synchronous call on streaming failure
            try:
                response = self.client.chat(
                    messages=self.messages,
                    tools=registry.active_definitions() or None,
                    system=self._get_system_prompt(),
                )
                # Emit any text that wasn't streamed yet
                new_text = (response.text or "")[len(streamed_text):]
                if new_text:
                    yield {"type": "text_delta", "text": new_text, "turn_id": None}
                    streamed_text += new_text
            except Exception as fallback_err:
                yield {"type": "_response", "response": None, "streamed_text": streamed_text}
                return

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

            if post_scope.phase == "error":
                scope_error = json.dumps(
                    {"error": post_scope.message, "error_type": post_scope.error_type},
                    ensure_ascii=False,
                )
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

            duration_ms = int((time.monotonic() - t0) * 1000)
            tool_msg_content = self._compact_tool_output(tool_result, tc)

            if tool_msg_content.startswith('{"error":') or tool_msg_content.startswith('{"error": '):
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, tool_msg_content)
                tool_msg_content = registry.format_result(tc.name, tool_result)

            elif turn_state is not None:
                turn_state.record_tool_success()

            self._record_turn_tool_result(tc.name, tool_msg_content)
            self._auto_track_task_progress(tc.name, True)

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
                    self.session_id, self.client, self.messages,
                    self._compact_state, token_threshold=self.token_threshold,
                )

            blocked_confirmation = self._runtime_confirmation_checkpoint()
            if blocked_confirmation is not None:
                yield self._suspended_event(blocked_confirmation)
                return

            buffer_text_events = self._is_analysis_quality_guard_candidate()
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

            self.messages.append(assistant_msg)

            if not response.has_tool_calls:
                if self._should_continue_for_analysis_quality(user_input, final_text):
                    self._inject_analysis_quality_guard()
                    continue
                blocked_confirmation = self._runtime_confirmation_checkpoint()
                if blocked_confirmation is not None:
                    yield self._suspended_event(blocked_confirmation)
                    return
                if buffer_text_events:
                    for ev in pending_text_events:
                        yield ev
                # Text was already streamed; just archive and save
                self._maybe_archive(user_input, final_text)
                self._auto_save()
                return

            if buffer_text_events:
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
                if not final_text:
                    yield {"type": "text_delta", "text": "分析已完成。（已达到安全轮次上限）"}
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

            _microcompact(self.session_id, self.messages)
            if _estimate_tokens(self.messages) > self.token_threshold:
                self.messages[:] = compact_history(
                    self.session_id, self.client, self.messages,
                    self._compact_state, token_threshold=self.token_threshold,
                )

            buffer_text_events = self._is_analysis_quality_guard_candidate()
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

            self.messages.append(assistant_msg)

            if not response.has_tool_calls:
                if self._should_continue_for_analysis_quality(resumed_input, final_text):
                    self._inject_analysis_quality_guard()
                    continue
                if buffer_text_events:
                    for ev in pending_text_events:
                        yield ev
                self._maybe_archive(resumed_input, final_text)
                self._auto_save()
                return

            if buffer_text_events:
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
                if not final_text:
                    yield {"type": "text_delta", "text": "分析已完成。（已达到安全轮次上限）"}
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

        if post_scope.phase == "error":
            scope_error = json.dumps(
                {"error": post_scope.message, "error_type": post_scope.error_type},
                ensure_ascii=False,
            )
            if turn_state is not None:
                turn_state.record_tool_error(tc.name, tc.arguments, scope_error)
            self._record_turn_tool_result(tc.name, scope_error)
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

        self._record_turn_tool_result(tc.name, tool_msg_content)
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

        def _run_tool(tc):
            try:
                scope_error = guard_errors.get(tc.id, "")
                if scope_error:
                    return (tc, scope_error, None)
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
                    return (tc, scope_error, post_scope)
                duration_ms = int((time.monotonic() - t0) * 1000)
                tool_msg_content = self._compact_tool_output(tool_result, tc)

                if tool_msg_content.startswith('{"error":') or tool_msg_content.startswith('{"error": '):
                    if turn_state is not None:
                        turn_state.record_tool_error(tc.name, tc.arguments, tool_msg_content)
                    tool_msg_content = registry.format_result(tc.name, tool_result)
                elif turn_state is not None:
                    turn_state.record_tool_success()

                return (tc, tool_msg_content, None)
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
                    self.session_id, self.client, self.messages,
                    self._compact_state, token_threshold=self.token_threshold,
                )

            blocked_confirmation = self._runtime_confirmation_checkpoint()
            if blocked_confirmation is not None:
                return blocked_confirmation

            # Defensive: repair any broken tool_call sequences from prior turns
            self._repair_broken_tool_sequence()

            response = self.client.chat(
                messages=self.messages,
                tools=registry.active_definitions() or None,
                system=self._get_system_prompt(),
            )

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

            self.messages.append(assistant_msg)

            if not response.has_tool_calls:
                if self._should_continue_for_analysis_quality(user_input, final_text):
                    self._inject_analysis_quality_guard()
                    continue
                blocked_confirmation = self._runtime_confirmation_checkpoint()
                if blocked_confirmation is not None:
                    return blocked_confirmation
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
                    results = self._execute_tools_parallel(tool_calls)
                    for tc, tool_msg_content in results:
                        self._record_turn_tool_result(tc.name, tool_msg_content)
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

            # Track token usage for budget enforcement
            turn_state = getattr(self.context, "turn_state", None)
            if turn_state is not None:
                round_tokens = _estimate_tokens(self.messages[-3:])
                turn_state.record_token_usage(round_tokens)

            # Safety valve: hard stop at 310 rounds
            if round_num >= 310:
                logger.warning("Safety valve triggered", extra={"extra_data": {
                    "session": self.session_id, "rounds": round_num,
                }})
                return FinalResponse(content=final_text or "分析已完成。（已达到安全轮次上限）")

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
