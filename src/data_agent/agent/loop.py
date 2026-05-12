from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Optional

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
from data_agent.agent.context import (
    AgentContext,
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
            "question": suspension.question,
            "options": suspension.options,
            "context": suspension.context,
            "snapshot": suspension.snapshot,
            "confirmation_type": suspension.confirmation_type,
            "blocking_reason": suspension.blocking_reason,
            "state_updates": suspension.state_updates,
            "related_task_id": suspension.related_task_id,
            "related_spec_id": suspension.related_spec_id,
        }, default=str, ensure_ascii=False))
        return str(path)

    def load(self, suspension_id: str) -> SuspendedForConfirmation | None:
        path = self._dir / f"suspension_{suspension_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return SuspendedForConfirmation(
            suspension_id=data["suspension_id"],
            question=data["question"],
            options=data["options"],
            context=data["context"],
            snapshot=data["snapshot"],
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


class AgentLoop:
    """Agent 主循环，管理对话、工具调度和上下文。"""

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
        active_project = project_name or object_name
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
        self._interrupt_event = threading.Event()
        self._compact_state = CompactState()
        self._last_jsonl_idx: int = 0  # 上次 JSONL 推送的消息索引

        # 对象绑定
        if active_project:
            token = set_current_context(self.context)
            workspace.set_project(active_project)
            from data_agent.tools.knowledge_tools import set_active_object, set_active_session
            set_active_object(active_project)
            set_active_session(self.session_id)
            reset_current_context(token)

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

        obj_name = data.get("project_name") or data.get("object_name")
        if obj_name:
            self.context.project_name = obj_name
            with use_agent_context(self.context):
                workspace.set_project(obj_name)
            set_active_object(obj_name)
            logger.info("Object context restored", extra={"extra_data": {"object": obj_name}})

        self._prompt_cache_dirty = True

    def _ensure_mcp_initialized(self) -> None:
        """惰性初始化 MCP 连接。延迟到首次 _loop() 调用。"""
        global _mcp_manager, _mcp_bridge
        if self._mcp_initialized:
            return
        self._mcp_initialized = True

        cfg = get_config()
        if not cfg.mcp_enabled or not cfg.mcp_config_path.exists():
            return

        try:
            from data_agent.mcp.config import load_mcp_config
            from data_agent.mcp.client import MCPClientManager
            from data_agent.mcp.bridge import MCPToolBridge

            mcp_config = load_mcp_config(cfg.mcp_config_path)
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

    def _build_system_prompt(self) -> str:
        from data_agent.agent.prompts import build_system_prompt, _classify_task
        from data_agent.session.workspace import workspace
        from data_agent.tools.knowledge_tools import get_knowledge_instances

        tool_list = ", ".join(registry.tool_names)
        active_obj = workspace.active_project
        sid = self.session_id

        # 提取最近用户输入用于任务级别推断
        user_input = ""
        for msg in reversed(self.messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                user_input = content if isinstance(content, str) else str(content)
                break

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
        try:
            from data_agent.agent.analysis_state import analysis_state_summary
            analysis_ctx = analysis_state_summary(self.context.analysis_state)
            if analysis_ctx:
                session_ctx = (session_ctx + "\n\n" if session_ctx else "") + "<analysis_state>\n" + analysis_ctx + "\n</analysis_state>"
        except Exception:
            pass

        level = _classify_task(user_input, session_ctx) if user_input else "standard"

        # Chat 模式：不传工具列表
        if level == "chat":
            tool_list = ""

        project_rules, domain_knowledge, experience_log = get_knowledge_instances()
        rules_prompt = project_rules.get_rules_for_prompt(object_name=active_obj, session_id=sid)
        domain_prompt = domain_knowledge.get_for_prompt(object_name=active_obj, session_id=sid)
        experience_prompt = experience_log.get_for_prompt(object_name=active_obj, session_id=sid)

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
            )

        return build_system_prompt(
            tool_list=tool_list,
            project_rules=rules_prompt,
            domain_knowledge=domain_prompt,
            experience_log=experience_prompt,
            session_context=session_ctx,
            skill_instructions=skill_instructions,
            skill_descriptions=skill_descriptions,
            user_input=user_input,
        )

    def _get_system_prompt(self) -> str:
        """获取系统提示词（带缓存）。"""
        with use_agent_context(self.context):
            if self._prompt_cache_dirty or not self._prompt_cache:
                self._prompt_cache = self._build_system_prompt()
                self._prompt_cache_dirty = False
            hint = self._execution_prompt_hint()
            if hint:
                return self._prompt_cache + f"\n\n<execution_control>\n{hint}\n</execution_control>"
            return self._prompt_cache

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
        state = self.context.analysis_state if self.context.analysis_state is not None else controller.load_state()
        self.context.analysis_state = state
        controller.prepare_turn(state, intent, user_input=user_input, dataset_profile=session_ctx)
        profile = "deep" if intent.intent_type == "report" else ("interactive" if intent.intent_type in {"chat", "operation"} else "analysis")
        self.context.turn_state = TurnExecutionState(ToolExecutionBudget(profile=profile))
        return controller.activate_tool_groups(registry, intent, state, user_input)

    def _execution_prompt_hint(self) -> str:
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

    def run_turn(self, user_input: str) -> str:
        """处理一轮用户输入，返回回复文本。CLI 模式使用。"""
        logger.info("Turn started", extra={"extra_data": {"session": self.session_id}})
        self._interrupt_event.clear()
        # Inject interrupt context if previous turn was interrupted
        if self._was_last_turn_interrupted():
            context = self._build_interrupt_context(user_input)
            self.messages.append({"role": "user", "content": context})
        self.messages.append({"role": "user", "content": user_input})
        self._prompt_cache_dirty = True
        # 根据用户输入激活相关工具分组
        with use_agent_context(self.context):
            new_groups = self._prepare_analysis_turn(user_input)
        if new_groups:
            logger.info("Activated tool groups", extra={"extra_data": {"groups": list(new_groups)}})
        try:
            result = self._loop()
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
        self.messages.append({"role": "user", "content": user_input})
        self._prompt_cache_dirty = True
        with use_agent_context(self.context):
            self._prepare_analysis_turn(user_input)
        try:
            result = self._loop()
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
        with use_agent_context(self.context):
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
            "project_name": workspace.active_project,
            "object_name": workspace.active_project,
            "datasets": {
                name: {"rows": info["rows"], "columns": info["columns"]}
                for name, info in datasets.items()
            },
            "loaded_skills": loaded_skills,
            "message_count": len(self.messages),
        }

    def resume_turn(self, suspension_id: str, user_response: str) -> LoopResult:
        """Resume after user answers a suspended question. Web mode."""
        from pathlib import Path
        sessions_dir = get_config().sessions_resolved
        mgr = SuspensionManager(sessions_dir)
        susp = mgr.load(suspension_id)
        if not susp:
            return FinalResponse(content=f"Error: suspension {suspension_id} not found")
        self._resolve_confirmation(susp, user_response)

        self.messages.append({"role": "user", "content": (
            f"<confirmation_response suspension_id=\"{suspension_id}\">\n"
            f"Question: {susp.question}\n"
            f"User answered: {user_response}\n"
            f"</confirmation_response>"
        )})
        mgr.remove(suspension_id)
        result = self._loop()
        if isinstance(result, FinalResponse):
            self._maybe_archive("", result.content)
        return result

    def _handle_cli_suspension(self, susp: SuspendedForConfirmation) -> str:
        """Handle a suspension in CLI mode by prompting the user directly.

        Pauses CLI output before displaying the question so it's not overwritten.
        Loops to handle multiple consecutive suspensions.
        """
        from data_agent.tools.interaction import _ask_single

        while True:
            if self.cli_pauser:
                self.cli_pauser.pause()

            result = _ask_single(
                question_text=susp.question,
                options=susp.options,
                multi_select=False,
            )

            if self.cli_pauser:
                self.cli_pauser.resume()

            answer = result.get("answer", "cancelled")
            self._resolve_confirmation(susp, answer)

            self.messages.append({"role": "user", "content": (
                f"<confirmation_response suspension_id=\"{susp.suspension_id}\">\n"
                f"Question: {susp.question}\n"
                f"User answered: {answer}\n"
                f"</confirmation_response>"
            )})

            loop_result = self._loop()

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
        with use_agent_context(self.context):
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
        with use_agent_context(self.context):
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

    def _process_tool_calls(self, response, round_num: int):
        """Process tool calls from an LLM response. Yields SSE event dicts."""
        import time

        for tc in response.tool_calls:
            # Check interrupt between tool calls
            if self._interrupt_event.is_set():
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

            t0 = time.monotonic()
            try:
                tool_result = registry.execute(tc.name, tc.arguments)
            except UserConfirmationRequired as ucc:
                from pathlib import Path
                sessions_dir = get_config().sessions_resolved
                mgr = SuspensionManager(sessions_dir)
                susp = SuspendedForConfirmation(
                    suspension_id=uuid.uuid4().hex[:8],
                    question=ucc.question,
                    options=ucc.options,
                    context=ucc.context,
                    snapshot={"messages": self._serialize_messages()},
                    confirmation_type=ucc.confirmation_type,
                    blocking_reason=ucc.blocking_reason,
                    state_updates=ucc.state_updates,
                    related_task_id=ucc.related_task_id,
                    related_spec_id=ucc.related_spec_id,
                )
                self._register_confirmation(susp)
                mgr.save(susp)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Suspended for user confirmation. suspension_id={susp.suspension_id}",
                })
                yield {
                    "type": "suspended",
                    "suspension_id": susp.suspension_id,
                    "question": susp.question,
                    "options": susp.options,
                    "context": susp.context,
                    "confirmation_type": susp.confirmation_type,
                    "blocking_reason": susp.blocking_reason,
                }
                return  # stop processing further tool calls

            duration_ms = int((time.monotonic() - t0) * 1000)
            output = tool_result.to_cli()
            output = persist_large_output(self.session_id, tc.id, output)

            tool_msg_content = output
            if output.startswith('{"error":') or output.startswith('{"error": '):
                if turn_state is not None:
                    turn_state.record_tool_error(tc.name, tc.arguments, output)
                tool_msg_content = (
                    f"{output}\n"
                    "[系统提示] 工具执行失败。请按以下策略恢复：\n"
                    "1. 检查参数是否正确（列名是否存在、数据类型是否匹配）\n"
                    "2. 尝试使用替代工具或方法达到相同分析目标\n"
                    "3. 如果是数据质量问题，先用 detect_data_quality 评估数据状态\n"
                    "4. 如果无法自行恢复，通过 ask_user_question 请求用户提供更多上下文"
                )

            elif turn_state is not None:
                turn_state.record_tool_success()

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

    def stream_turn(self, user_input: str):
        """Generator variant of run_turn for SSE streaming. Yields event dicts."""
        import time
        set_current_context(self.context)

        logger.info("Stream turn started", extra={"extra_data": {"session": self.session_id}})
        self._interrupt_event.clear()
        # Inject interrupt context if previous turn was interrupted
        if self._was_last_turn_interrupted():
            context = self._build_interrupt_context(user_input)
            self.messages.append({"role": "user", "content": context})
        self.messages.append({"role": "user", "content": user_input})
        self._prompt_cache_dirty = True
        self._prepare_analysis_turn(user_input)

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

            response = None
            streamed_text = ""
            for ev in self._stream_llm_round(round_num):
                if ev["type"] == "_response":
                    response = ev["response"]
                    streamed_text = ev["streamed_text"]
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
                # Text was already streamed; just archive and save
                self._maybe_archive(user_input, final_text)
                self._auto_save()
                return

            # Process tool calls
            suspended = False
            for ev in self._process_tool_calls(response, round_num):
                yield ev
                if ev["type"] == "suspended":
                    suspended = True
            if suspended:
                return

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

    def resume_turn_streaming(self, suspension_id: str, user_response: str):
        """Generator variant of resume_turn for SSE streaming."""
        from pathlib import Path
        set_current_context(self.context)

        sessions_dir = get_config().sessions_resolved
        mgr = SuspensionManager(sessions_dir)
        susp = mgr.load(suspension_id)
        if not susp:
            yield {"type": "error", "message": f"Suspension {suspension_id} not found"}
            return

        self.messages.append({"role": "user", "content": (
            f"<confirmation_response suspension_id=\"{suspension_id}\">\n"
            f"Question: {susp.question}\n"
            f"User answered: {user_response}\n"
            f"</confirmation_response>"
        )})
        mgr.remove(suspension_id)

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

            response = None
            for ev in self._stream_llm_round(round_num):
                if ev["type"] == "_response":
                    response = ev["response"]
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
                self._maybe_archive("", final_text)
                self._auto_save()
                return

            suspended = False
            for ev in self._process_tool_calls(response, round_num):
                yield ev
                if ev["type"] == "suspended":
                    suspended = True
            if suspended:
                return

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

    def _loop(self) -> LoopResult:
        """Run the agent loop inside this session's AgentContext."""
        with use_agent_context(self.context):
            return self._loop_impl()

    def _loop_impl(self) -> LoopResult:
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
                return FinalResponse(content=final_text)

            # 执行工具，每条结果作为独立的 tool 消息
            for tc in response.tool_calls:
                if self._interrupt_event.is_set():
                    logger.info("Interrupted during tool execution")
                    return FinalResponse(content=(final_text or "分析已中断。") + "\n\n[已中断]")

                logger.info("Tool call", extra={"extra_data": {"tool": tc.name, "args_keys": list(tc.arguments.keys())}})

                # 根据调用的工具动态扩展工具分组
                registry.expand_from_tool_call(tc.name)
                turn_state = getattr(self.context, "turn_state", None)
                if self._is_tool_blocked_by_confirmation(tc.name):
                    blocked = self._blocked_tool_message(tc.name)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({"error": blocked, "error_type": "confirmation_required"}, ensure_ascii=False),
                    })
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
                        return FinalResponse(content=str(exc))
                    turn_state.record_tool_call(tc.name, tc.arguments)

                try:
                    tool_result = registry.execute(tc.name, tc.arguments)
                except UserConfirmationRequired as ucc:
                    # Web mode: suspension - save state and return
                    from pathlib import Path
                    sessions_dir = get_config().sessions_resolved
                    mgr = SuspensionManager(sessions_dir)
                    susp = SuspendedForConfirmation(
                        suspension_id=uuid.uuid4().hex[:8],
                        question=ucc.question,
                        options=ucc.options,
                        context=ucc.context,
                        snapshot={"messages": self._serialize_messages()},
                        confirmation_type=ucc.confirmation_type,
                        blocking_reason=ucc.blocking_reason,
                        state_updates=ucc.state_updates,
                        related_task_id=ucc.related_task_id,
                        related_spec_id=ucc.related_spec_id,
                    )
                    self._register_confirmation(susp)
                    mgr.save(susp)
                    # Tell LLM we're waiting
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Suspended for user confirmation. suspension_id={susp.suspension_id}",
                    })
                    return susp

                output = tool_result.to_cli()

                # 大输出持久化
                output = persist_large_output(self.session_id, tc.id, output)

                # 工具错误恢复：为 LLM 提供恢复提示
                tool_msg_content = output
                if output.startswith('{"error":') or output.startswith('{"error": '):
                    if turn_state is not None:
                        turn_state.record_tool_error(tc.name, tc.arguments, output)
                    tool_msg_content = (
                        f"{output}\n"
                        "[系统提示] 工具执行失败。请按以下策略恢复：\n"
                        "1. 检查参数是否正确（列名是否存在、数据类型是否匹配）\n"
                        "2. 尝试使用替代工具或方法达到相同分析目标\n"
                        "3. 如果是数据质量问题，先用 detect_data_quality 评估数据状态\n"
                        "4. 如果无法自行恢复，通过 ask_user_question 请求用户提供更多上下文"
                    )
                    logger.warning("Tool error", extra={"extra_data": {"tool": tc.name, "error": output[:200]}})
                elif turn_state is not None:
                    turn_state.record_tool_success()

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_msg_content,
                })

            # Safety valve: hard stop at 310 rounds
            if round_num >= 310:
                logger.warning("Safety valve triggered", extra={"extra_data": {
                    "session": self.session_id, "rounds": round_num,
                }})
                return FinalResponse(content=final_text or "分析已完成。（已达到安全轮次上限）")

    def _maybe_archive(self, user_input: str, reply: str) -> None:
        """当有实质性分析结果时自动归档。"""
        with use_agent_context(self.context):
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
