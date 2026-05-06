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
        )

    def remove(self, suspension_id: str):
        path = self._dir / f"suspension_{suspension_id}.json"
        path.unlink(missing_ok=True)


class UserConfirmationRequired(Exception):
    """Raised by ask_user_question in non-CLI mode to trigger suspension."""
    def __init__(self, question: str, options: list[dict], context: str = ""):
        self.question = question
        self.options = options
        self.context = context
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
    ):
        global _skill_loader, _mcp_manager, _mcp_bridge

        cfg = get_config()
        self.client = client or LLMClient()
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.messages: list[dict] = []
        self.token_threshold = cfg.token_threshold
        self._last_data_file = ""
        self._prompt_cache: str = ""
        self._prompt_cache_dirty: bool = True
        self._interrupt_event = threading.Event()
        self._compact_state = CompactState()
        self._last_jsonl_idx: int = 0  # 上次 JSONL 推送的消息索引

        # 对象绑定
        if object_name:
            workspace.set_object(object_name)
            from data_agent.tools.knowledge_tools import set_active_object, set_active_session
            set_active_object(object_name)
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

        obj_name = data.get("object_name")
        if obj_name:
            workspace.set_object(obj_name)
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
        active_obj = workspace.active_object
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
        if self._prompt_cache_dirty or not self._prompt_cache:
            self._prompt_cache = self._build_system_prompt()
            self._prompt_cache_dirty = False
        return self._prompt_cache

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
        new_groups = registry.activate_groups_for_text(user_input)
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
            "object_name": workspace.active_object,
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
        sessions_dir = Path(get_config().project_resolved) / "sessions"
        mgr = SuspensionManager(sessions_dir)
        susp = mgr.load(suspension_id)
        if not susp:
            return FinalResponse(content=f"Error: suspension {suspension_id} not found")

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
                sessions_dir = Path(get_config().project_resolved) / "sessions"
                mgr = SuspensionManager(sessions_dir)
                susp = SuspendedForConfirmation(
                    suspension_id=uuid.uuid4().hex[:8],
                    question=ucc.question,
                    options=ucc.options,
                    context=ucc.context,
                    snapshot={"messages": self._serialize_messages()},
                )
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
                }
                return  # stop processing further tool calls

            duration_ms = int((time.monotonic() - t0) * 1000)
            output = tool_result.to_cli()
            output = persist_large_output(self.session_id, tc.id, output)

            tool_msg_content = output
            if output.startswith('{"error":') or output.startswith('{"error": '):
                tool_msg_content = (
                    f"{output}\n"
                    "[系统提示] 工具执行失败。请按以下策略恢复：\n"
                    "1. 检查参数是否正确（列名是否存在、数据类型是否匹配）\n"
                    "2. 尝试使用替代工具或方法达到相同分析目标\n"
                    "3. 如果是数据质量问题，先用 detect_data_quality 评估数据状态\n"
                    "4. 如果无法自行恢复，通过 ask_user_question 请求用户提供更多上下文"
                )

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

        logger.info("Stream turn started", extra={"extra_data": {"session": self.session_id}})
        self._interrupt_event.clear()
        # Inject interrupt context if previous turn was interrupted
        if self._was_last_turn_interrupted():
            context = self._build_interrupt_context(user_input)
            self.messages.append({"role": "user", "content": context})
        self.messages.append({"role": "user", "content": user_input})
        self._prompt_cache_dirty = True
        registry.activate_groups_for_text(user_input)

        max_rounds = 30
        final_text = ""
        self._ensure_mcp_initialized()

        for round_num in range(1, max_rounds + 1):
            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

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

        # Max rounds reached
        if not final_text:
            yield {"type": "text_delta", "text": "达到最大轮次限制。"}

    def resume_turn_streaming(self, suspension_id: str, user_response: str):
        """Generator variant of resume_turn for SSE streaming."""
        from pathlib import Path

        sessions_dir = Path(get_config().project_resolved) / "sessions"
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

        max_rounds = 30
        final_text = ""

        for round_num in range(1, max_rounds + 1):
            if self._interrupt_event.is_set():
                yield {"type": "error", "message": "Turn interrupted by user"}
                return

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

        if not final_text:
            yield {"type": "text_delta", "text": "达到最大轮次限制。"}

    def _loop(self) -> LoopResult:
        """循环调用 LLM 直到获得最终文本回复。"""
        max_rounds = 30
        final_text = ""

        # 惰性初始化 MCP
        self._ensure_mcp_initialized()

        for _ in range(max_rounds):
            # 协作式中断检查
            if self._interrupt_event.is_set():
                logger.info("Turn interrupted by user")
                return FinalResponse(content=(final_text or "分析已中断。") + "\n\n[已中断]")

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

                try:
                    tool_result = registry.execute(tc.name, tc.arguments)
                except UserConfirmationRequired as ucc:
                    # Web mode: suspension - save state and return
                    from pathlib import Path
                    sessions_dir = Path(get_config().project_resolved) / "sessions"
                    mgr = SuspensionManager(sessions_dir)
                    susp = SuspendedForConfirmation(
                        suspension_id=uuid.uuid4().hex[:8],
                        question=ucc.question,
                        options=ucc.options,
                        context=ucc.context,
                        snapshot={"messages": self._serialize_messages()},
                    )
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
                    tool_msg_content = (
                        f"{output}\n"
                        "[系统提示] 工具执行失败。请按以下策略恢复：\n"
                        "1. 检查参数是否正确（列名是否存在、数据类型是否匹配）\n"
                        "2. 尝试使用替代工具或方法达到相同分析目标\n"
                        "3. 如果是数据质量问题，先用 detect_data_quality 评估数据状态\n"
                        "4. 如果无法自行恢复，通过 ask_user_question 请求用户提供更多上下文"
                    )
                    logger.warning("Tool error", extra={"extra_data": {"tool": tc.name, "error": output[:200]}})

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_msg_content,
                })

        return FinalResponse(content=final_text or "达到最大轮次限制。")

    def _maybe_archive(self, user_input: str, reply: str) -> None:
        """当有实质性分析结果时自动归档。"""
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
