from __future__ import annotations

import os
import re
import sys
import threading
import uuid
from dataclasses import dataclass

if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from data_agent.agent.loop import AgentLoop
from data_agent.agent.runner import AgentRunner
from data_agent.config import get_config
from data_agent.session.history import (
    save_session,
    load_session,
    list_sessions,
    list_analyses,
    branch_session,
    list_branches,
)
from data_agent.session.task_manager import task_manager
from data_agent.tools.registry import ToolResult

console = Console()


@dataclass(frozen=True)
class DataCommandArgs:
    paths: list[str]
    context: str = ""

    @property
    def data_file(self) -> str:
        return "; ".join(self.paths)


def _parse_data_command_args(args: str) -> DataCommandArgs:
    """Parse `/data` arguments into file paths plus optional business context."""
    text = (args or "").strip()
    if not text:
        return DataCommandArgs(paths=[])

    matches = list(re.finditer(r'"([^"]+)"|\'([^\']+)\'', text))
    if matches:
        paths = [(m.group(1) or m.group(2) or "").strip() for m in matches]
        spans = [m.span() for m in matches]
        chunks = []
        cursor = 0
        for start, end in spans:
            chunks.append(text[cursor:start])
            cursor = end
        chunks.append(text[cursor:])
        context = re.sub(r"[ \t]+", " ", "".join(chunks)).strip()
        return DataCommandArgs(paths=[p for p in paths if p], context=context)

    lines = text.splitlines()
    first = lines[0].strip()
    paths = [p for p in first.split() if p]
    context = "\n".join(lines[1:]).strip()
    return DataCommandArgs(paths=paths, context=context)


def _format_data_command_prompt(parsed: DataCommandArgs) -> str:
    lines = ["请加载并预览以下数据文件："]
    for idx, path in enumerate(parsed.paths, 1):
        lines.append(f"{idx}. {path}")
    if parsed.context:
        lines.append("")
        lines.append("用户补充说明：")
        lines.append(parsed.context)
    return "\n".join(lines)


class _CLIPauser:
    """Coordinate pausing CLI output when the worker thread needs user input.

    Worker thread calls pause() before displaying a question, resume() after.
    Main thread calls check_plain() in its polling loop to handle the pause.
    """

    def __init__(self):
        self._pause_requested = threading.Event()
        self._pause_acknowledged = threading.Event()

    def pause(self):
        """Worker: request pause and wait for acknowledgement."""
        self._pause_acknowledged.clear()
        self._pause_requested.set()
        self._pause_acknowledged.wait(timeout=10)

    def resume(self):
        """Worker: signal that input is done."""
        self._pause_requested.clear()

    def check_plain(self):
        """Main thread: wait if worker needs to display a question."""
        if self._pause_requested.is_set():
            self._pause_acknowledged.set()
            self._pause_requested.wait(timeout=300)


def _repl_input(prompt_text: str = "data-agent >> ", *, allow_escape: bool = False) -> str:
    """使用 prompt_toolkit 获取 REPL 输入，确保文字可见。

    Enter 提交；Ctrl+Enter 换行。
    When allow_escape=True, pressing ESC raises KeyboardInterrupt.
    """
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.styles import Style

        style = Style.from_dict({
            "": "#00ffff bold",
            "prompt": "#00ffff bold",
        })

        kb = KeyBindings()

        # Ctrl+Enter 换行
        @kb.add("c-j")
        def _ctrl_enter(event):
            event.current_buffer.insert_text("\n")

        if allow_escape:
            @kb.add("escape")
            def _on_esc(event):
                event.app.exit(exception=KeyboardInterrupt())

        return pt_prompt(
            FormattedText([("class:prompt", prompt_text)]),
            style=style,
            multiline=False,
            key_bindings=kb,
        )
    except ImportError:
        return input(prompt_text)


# === Command Registry ===

class CommandRegistry:
    """Pluggable command registry.

    CLI triggers via ``/command [args]``; Web triggers via
    ``POST /api/command/<name>``.  Both share the same handler.
    """

    def __init__(self):
        self._commands: dict[str, dict] = {}

    def register(self, name: str, handler, description: str = "",
                 aliases: list[str] | None = None):
        entry = {"handler": handler, "description": description, "aliases": aliases or []}
        self._commands[name] = entry
        for alias in (aliases or []):
            self._commands[alias] = {**entry, "alias_of": name}

    def execute(self, name: str, args: str = ""):
        """Execute a command.

        Returns:
            None  — command handled, nothing to send to LLM
            str   — chat input to send to the LLM (e.g. /report, /data)
            ToolResult — display result (for unknown commands)
        """
        entry = self._commands.get(name)
        if not entry:
            return ToolResult(summary=f"Unknown command: /{name}. Type /help for available commands."
            )
        return entry["handler"](args)

    def list_commands(self) -> str:
        seen = set()
        lines = ["Available commands:"]
        for name, entry in self._commands.items():
            if "alias_of" in entry:
                continue
            seen.add(name)
            desc = entry.get("description", "")
            aliases = entry.get("aliases", [])
            alias_str = f" ({', '.join('/' + a for a in aliases)})" if aliases else ""
            lines.append(f"  /{name}{alias_str}  - {desc}")
        return "\n".join(lines)

def _print_help() -> None:
    help_text = """**可用命令：**

- `/help` - 显示帮助
- `/report` - 对当前数据生成完整分析报告
- `/export [markdown]` - 导出当前对话分析结果（默认 HTML）
- `/compact` - 手动压缩上下文
- `/clear` - 清空对话历史
- `/rewind` - 回退对话到之前的状态
- `/branch [name]` - 从当前会话创建分支
- `/branches` - 列出当前会话的所有分支
- `/data <path>` - 预加载数据文件
- `/bind <object>` - 绑定当前会话到对象（支持换绑）
- `/unbind` - 解除当前会话的对象绑定
- `/project create <name>` - 创建分析项目（`/object` 仍兼容）
- `/project list` - 列出所有项目
- `/project switch <name>` - 切换到项目（同 /bind）
- `/project info` - 显示当前项目信息
- `/project rename <old> <new>` - 重命名项目
- `/project archive <name>` - 归档项目
- `/inbox` - 切换到无归属模式（同 /unbind）
- `/migrate <filename>` - 将 inbox 文件迁移到当前对象
- `/tasks` - 列出项目任务（跨会话）
- `/skill` - 列出可用技能
- `/skill load <name>` - 加载技能
- `/skill unload <name>` - 卸载技能
- `/mcp` - 列出已连接的 MCP 服务器
- `/save [tag]` - 保存当前会话
- `/sessions` - 列出已保存的会话
- `/sessions switch <id>` - 切换到指定会话（保留当前状态）
- `/resume [id]` - 恢复会话（无参数显示列表选择）
- `/history` - 查看历史分析记录
- `/artifacts` - 查看当前会话的输出物清单
- `/artifacts delete <index>` - 删除指定索引的输出物
- `/exit` - 退出并自动保存

**快捷键：** ESC - 中断当前分析
"""
    console.print(Markdown(help_text))


def _print_sessions() -> None:
    sessions = list_sessions()
    if not sessions:
        console.print("[dim]没有已保存的会话[/dim]")
        return
    table = Table(title="Saved Sessions")
    table.add_column("ID", style="cyan", width=14)
    table.add_column("Saved At", width=20)
    table.add_column("Summary", width=30)
    table.add_column("Object", width=14)
    table.add_column("Data File", width=16)
    table.add_column("Tag", width=10)
    table.add_column("Msgs", width=5)
    for s in sessions[:20]:
        summary = s.get("summary", "")[:45]
        table.add_row(
            s["session_id"],
            s["saved_at"],
            summary,
            s.get("object_name") or "-",
            s.get("data_file", ""),
            s.get("tag", ""),
            str(s["message_count"]),
        )
    console.print(table)


def _print_history(session_id: str = "") -> None:
    analyses = list_analyses(session_id)
    if not analyses:
        console.print("[dim]没有历史分析记录[/dim]")
        return
    table = Table(title="Analysis History")
    table.add_column("ID", style="cyan", width=25)
    table.add_column("Time", width=20)
    table.add_column("Session", width=14)
    table.add_column("Data File", width=20)
    table.add_column("Summary", width=40)
    for a in analyses[:20]:
        table.add_row(
            a["archive_id"],
            a["timestamp"],
            a.get("session_id", ""),
            a.get("data_file", ""),
            (a.get("summary") or "")[:60],
        )
    console.print(table)


def _get_conversation_rounds(messages: list[dict]) -> list[list[dict]]:
    """Group messages into conversation rounds.

    Each round starts with a 'user' message and includes all subsequent
    non-user messages until the next 'user' message.
    """
    rounds: list[list[dict]] = []
    current: list[dict] = []
    for msg in messages:
        if msg.get("role") == "user" and current:
            rounds.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        rounds.append(current)
    return rounds


def _format_round_for_rewind(round_num: int, round_messages: list[dict]) -> str:
    """Format a conversation round for /rewind display."""
    user_text = ""
    assistant_summary = ""

    for msg in round_messages:
        role = msg.get("role", "")
        if role == "user":
            content = msg.get("content", "")
            user_text = content[:80] if isinstance(content, str) else "(非文本内容)"
        elif role == "assistant" and not assistant_summary:
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                names = [tc.get("function", {}).get("name", "") for tc in tool_calls]
                assistant_summary = ", ".join(n for n in names if n)
            elif isinstance(content, str) and content.strip():
                assistant_summary = content[:60]

    return (
        f"  [cyan]Round {round_num}[/cyan]  "
        f"[bold blue]>>>[/bold blue] {user_text}\n"
        f"{' ' * (len(f'Round {round_num}') + 4)}"
        f"[bold green]<<<[/bold green] {assistant_summary}"
    )


def _check_esc_key() -> bool:
    """检查是否按下了 ESC 键（仅 Windows）。"""
    if sys.platform == "win32":
        import msvcrt
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key == b'\x1b':
                return True
    return False


def _print_resumed_conversation(messages: list[dict]) -> None:
    """恢复会话后展示完整对话历史内容，不截断。"""
    if not messages:
        return

    console.print()
    console.print(Panel(
        f"[bold]已恢复的会话内容 ({len(messages)} 条消息)[/bold]",
        border_style="dim",
    ))

    for msg in messages:
        role = msg.get("role", "")

        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                console.print()
                console.print(f"[bold cyan]>>> {content}[/bold cyan]")

        elif role == "assistant":
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])

            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    args_str = fn.get("arguments", "")
                    # 显示完整工具名和参数
                    label = f"[tool call] {name}"
                    if args_str:
                        try:
                            import json as _json
                            args = _json.loads(args_str) if isinstance(args_str, str) else args_str
                            parts = []
                            for k, v in args.items():
                                parts.append(f"{k}={v}")
                            if parts:
                                label += f"({', '.join(parts)})"
                        except Exception:
                            label += f"({args_str})"
                    console.print(f"  [dim]{label}[/dim]")

            if isinstance(content, str) and content.strip():
                console.print()
                safe_content = content.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")
                console.print(Markdown(safe_content))

        elif role == "tool":
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                console.print()
                console.print(Panel(
                    content,
                    title="[tool result]",
                    border_style="dim",
                    expand=False,
                ))

    console.print()


def _format_recent_sessions(sessions: list[dict], max_show: int = 5) -> str:
    """格式化最近的会话列表用于启动提示。"""
    lines = []
    for i, s in enumerate(sessions[:max_show]):
        summary = s.get("summary", "")[:40] or "(无摘要)"
        obj = f" → {s['object_name']}" if s.get("object_name") else ""
        msgs = s.get("message_count", 0)
        saved = s.get("saved_at", "")[5:16]  # MM-DD HH:MM
        lines.append(f"  {i + 1}. [{saved}] {summary}{obj} ({msgs} msgs)")
    return "\n".join(lines)


def run_repl() -> None:
    """启动交互式 REPL。"""
    from data_agent.utils.logging import setup_logging

    cfg = get_config()

    # 初始化日志（如果 lifecycle 没有预先初始化）
    setup_logging(level=cfg.log_level, log_file=cfg.log_file_resolved)

    # ── 启动会话恢复 ──
    recent_sessions = []
    first_input = None
    try:
        recent_sessions = list_sessions()[:5]
    except Exception:
        recent_sessions = []

    if recent_sessions:
        console.print(Panel(
            f"[bold]Data Agent v0.1[/bold]\n"
            f"Model: {cfg.model_id}\n"
            f"Project: {cfg.project_resolved}\n\n"
            f"[bold]最近会话：[/bold]\n"
            f"{_format_recent_sessions(recent_sessions)}\n\n"
            f"输入编号恢复会话，或直接输入开始新会话。",
            title="Data Agent",
            border_style="blue",
        ))
        try:
            first_input = _repl_input("data-agent >> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]Goodbye![/dim]")
            return

        if first_input.isdigit():
            idx = int(first_input) - 1
            if 0 <= idx < len(recent_sessions):
                # 恢复选中会话
                selected = recent_sessions[idx]
                session_id = selected["session_id"]
                data = load_session(session_id)
                if data:
                    loop = AgentLoop(session_id=session_id)
                    loop.messages = data["messages"]
                    loop._last_jsonl_idx = len(data["messages"])
                    loop._last_data_file = data.get("data_file", "")
                    loop.restore_object_context()
                    from data_agent.tools.visualization import set_chart_session
                    set_chart_session(data["session_id"])
                    obj_info = f" → 对象: {data.get('object_name')}" if data.get("object_name") else ""
                    console.print(f"[green]已恢复会话: {session_id} ({data.get('message_count', 0)} msgs){obj_info}[/green]")
                    _print_resumed_conversation(data["messages"])
                    first_input = None  # 已处理，不作为首次输入
                else:
                    console.print(f"[red]无法加载会话: {session_id}，创建新会话[/red]")
                    session_id = uuid.uuid4().hex[:12]
                    loop = AgentLoop(session_id=session_id)
                    first_input = None
            else:
                console.print("[dim]无效编号，创建新会话[/dim]")
                session_id = uuid.uuid4().hex[:12]
                loop = AgentLoop(session_id=session_id)
                first_input = None
        else:
            # 用户直接输入了内容 → 创建新会话
            session_id = uuid.uuid4().hex[:12]
            loop = AgentLoop(session_id=session_id)
            # first_input 保留，后续作为第一条消息处理
    else:
        session_id = uuid.uuid4().hex[:12]
        loop = AgentLoop(session_id=session_id)
        console.print(
            Panel(
                f"[bold]Data Agent v0.1[/bold]\n"
                f"Model: {cfg.model_id}\n"
                f"Session: {session_id}\n"
                f"Project: {cfg.project_resolved}\n\n"
                f"输入问题开始分析，或输入 /help 查看帮助。",
                title="Data Agent",
                border_style="blue",
            )
        )

    # 确保会话目录存在
    from data_agent.session.history import _session_dir
    _session_dir(session_id)

    # ── Build command registry ──
    # Command handlers return None (handled) or a string (chat input to process).
    CMD = CommandRegistry()
    _ctx = {"running": True}  # mutable context for exit
    _sessions_cache: dict[str, AgentLoop] = {}  # multi-session cache (max 5)
    MAX_CONCURRENT_SESSIONS = 5

    def cmd_exit(args: str):
        if loop.messages:
            save_session(loop.messages, loop.session_id, data_file=loop._last_data_file)
            console.print(f"[dim]Session saved: {loop.session_id}[/dim]")
        console.print("[dim]Goodbye![/dim]")
        _ctx["running"] = False
        return None

    def cmd_help(args: str):
        _print_help()
        return None

    def cmd_report(args: str):
        parts = args.strip().split() if args else []
        report_type = parts[0].lower() if parts else "brief"
        fmt = parts[1].lower() if len(parts) > 1 else "html"
        if report_type not in ("brief", "formal"):
            fmt = report_type if report_type in ("html", "md", "markdown", "pdf") else fmt
            report_type = "brief"
        if fmt == "md":
            fmt = "markdown"
        if fmt not in ("html", "markdown", "pdf"):
            fmt = "html"
        tool_name = "generate_formal_report" if report_type == "formal" else "generate_analysis_brief"
        return f"请使用 {tool_name} 工具生成{report_type}报告，format={fmt}。报告只能消费已有 EvidenceRecord 和已验证图表；证据不足时返回缺口清单。"

    def cmd_export(args: str):
        fmt = args.strip().lower() if args else "html"
        if fmt not in ("html", "markdown", "md", "pdf"):
            fmt = "html"
        format_str = "markdown" if fmt in ("markdown", "md") else "html"
        if fmt == "pdf":
            format_str = "pdf"
        return f"请将当前对话中的分析结果导出为{format_str}格式文件，使用 export_conversation 工具。"

    def cmd_compact(args: str):
        if loop.messages:
            from data_agent.agent.compact import compact_history, CompactState
            focus = args.strip() if args else None
            loop.messages[:] = compact_history(
                loop.session_id, loop.client, loop.messages,
                loop._compact_state, focus=focus,
                token_threshold=loop.token_threshold,
            )
            console.print("[green]上下文已压缩并保存 transcript[/green]")
        else:
            console.print("[dim]当前没有对话内容可压缩[/dim]")
        return None

    def cmd_clear(args: str):
        loop.messages.clear()
        console.print("[green]对话历史已清空[/green]")
        return None

    def cmd_data(args: str):
        if not args:
            console.print("[yellow]Usage: /data <文件路径>[/yellow]")
            return None
        parsed = _parse_data_command_args(args)
        if not parsed.paths:
            console.print("[yellow]Usage: /data <文件路径>[/yellow]")
            return None
        loop._last_data_file = parsed.data_file
        return _format_data_command_prompt(parsed)

    def cmd_tasks(args: str):
        from data_agent.session.workspace import workspace
        console.print(task_manager.format_list(session_id=loop.session_id, project_name=workspace.active_project or ""))
        return None

    def cmd_analysis(args: str):
        from data_agent.agent.analysis_state import (
            analysis_state_summary,
            load_analysis_state,
            reset_analysis_state,
        )
        from data_agent.session.workspace import workspace

        action = (args or "status").strip().lower()
        if action == "reset":
            state = reset_analysis_state(loop.session_id, workspace.active_project)
            loop.context.analysis_state = state
            console.print("[green]Analysis state reset for current session.[/green]")
            return None

        state = load_analysis_state(loop.session_id, workspace.active_project)
        loop.context.analysis_state = state

        if action in ("", "status"):
            console.print(analysis_state_summary(state) or "No analysis state.")
        elif action == "requirements":
            console.print_json(data=state.data_requirements)
        elif action == "spec":
            console.print_json(data=state.analysis_spec or {})
        elif action == "evidence":
            console.print_json(data=state.evidence_records)
        else:
            console.print("[yellow]Usage: /analysis status|requirements|spec|evidence|reset[/yellow]")
        return None

    def cmd_save(args: str):
        tag = args.strip() if args else ""
        if not loop.messages:
            console.print("[yellow]当前没有对话内容可保存[/yellow]")
            return None
        save_session(loop.messages, loop.session_id, tag=tag, data_file=loop._last_data_file)
        console.print(f"[green]Session saved: {loop.session_id}" + (f" (tag: {tag})" if tag else "") + "[/green]")
        return None

    def cmd_sessions(args: str):
        _print_sessions()
        return None

    def cmd_sessions_switch(args: str):
        nonlocal loop
        target_id = args.strip()
        if not target_id:
            console.print("[yellow]Usage: /sessions switch <session_id>[/yellow]")
            return None

        # Prevent switching to the same session
        if target_id == loop.session_id:
            console.print(f"[dim]已经在会话 {target_id} 中[/dim]")
            return None

        # Save current loop to cache
        if loop.session_id not in _sessions_cache:
            # Evict oldest entry if at capacity
            if len(_sessions_cache) >= MAX_CONCURRENT_SESSIONS:
                oldest_key = next(iter(_sessions_cache))
                _sessions_cache.pop(oldest_key)
                console.print(f"[dim]缓存已满，释放会话: {oldest_key}[/dim]")
            _sessions_cache[loop.session_id] = loop

        # Try to load from cache first
        if target_id in _sessions_cache:
            loop = _sessions_cache.pop(target_id)
            console.print(f"[green]已切换到会话: {loop.session_id} (from cache)[/green]")
        else:
            # Load from disk
            data = load_session(target_id)
            if data is None:
                console.print(f"[red]会话未找到: {target_id}[/red]")
                return None
            new_loop = AgentLoop(session_id=data["session_id"])
            new_loop.messages = data["messages"]
            new_loop._last_jsonl_idx = len(data["messages"])
            new_loop._last_data_file = data.get("data_file", "")
            new_loop.restore_object_context()
            from data_agent.tools.visualization import set_chart_session
            set_chart_session(data["session_id"])
            loop = new_loop
            # Ensure session directory exists
            from data_agent.session.history import _session_dir
            _session_dir(data["session_id"])
            obj_info = f" → 对象: {data.get('object_name')}" if data.get("object_name") else ""
            console.print(f"[green]已切换到会话: {data['session_id']} ({data.get('message_count', 0)} msgs){obj_info}[/green]")
        return None

    def cmd_resume(args: str):
        session_id_arg = args.strip()

        if session_id_arg:
            data = load_session(session_id_arg)
            if data is None:
                console.print(f"[red]Session not found: {session_id_arg}[/red]")
                return None
            loop.messages = data["messages"]
            loop.session_id = data["session_id"]
            loop._last_data_file = data.get("data_file", "")
            from data_agent.tools.visualization import set_chart_session
            set_chart_session(data["session_id"])
            loop.restore_object_context()
            obj_info = f" → 对象: {data.get('object_name')}" if data.get("object_name") else ""
            console.print(f"[green]Session resumed: {data['session_id']} ({data.get('message_count', 0)} msgs){obj_info}[/green]")
            _print_resumed_conversation(data["messages"])
            return None

        sessions = list_sessions()
        if not sessions:
            console.print("[dim]没有已保存的会话[/dim]")
            return None

        table = Table(title="Saved Sessions")
        table.add_column("#", style="cyan", width=3)
        table.add_column("Session ID", style="cyan", width=14)
        table.add_column("Saved At", width=20)
        table.add_column("Summary", width=30)
        table.add_column("Object", width=14)
        table.add_column("Data File", width=16)
        table.add_column("Tag", width=10)
        table.add_column("Msgs", width=5)
        for i, s in enumerate(sessions[:20]):
            table.add_row(
                str(i + 1), s["session_id"], s["saved_at"],
                s.get("summary", "")[:45], s.get("object_name") or "-",
                s.get("data_file", ""),
                s.get("tag", ""), str(s["message_count"]),
            )
        console.print(table)

        try:
            choice = _repl_input("选择要恢复的会话编号 (Esc 取消) >> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]已取消[/dim]")
            return None

        if not choice or not choice.isdigit():
            console.print("[dim]已取消[/dim]")
            return None

        idx = int(choice) - 1
        if idx < 0 or idx >= len(sessions):
            console.print(f"[red]无效编号: {choice}[/red]")
            return None

        selected = sessions[idx]
        data = load_session(selected["session_id"])
        if data is None:
            console.print(f"[red]Session not found: {selected['session_id']}[/red]")
            return None

        loop.messages = data["messages"]
        loop.session_id = data["session_id"]
        loop._last_data_file = data.get("data_file", "")
        from data_agent.tools.visualization import set_chart_session
        set_chart_session(data["session_id"])
        loop.restore_object_context()
        obj_info = f" → 对象: {data.get('object_name')}" if data.get("object_name") else ""
        console.print(f"[green]Session resumed: {data['session_id']} ({data.get('message_count', 0)} msgs){obj_info}[/green]")
        _print_resumed_conversation(data["messages"])
        return None

    def cmd_history(args: str):
        _print_history(args.strip())
        return None

    def cmd_artifacts(args: str):
        from data_agent.session.history import list_artifacts, delete_artifact
        stripped = args.strip()
        if stripped.startswith("delete "):
            index_str = stripped[len("delete "):].strip()
            try:
                index = int(index_str)
            except ValueError:
                console.print("[red]无效的索引，请输入数字[/red]")
                return None
            artifacts = list_artifacts(loop.session_id)
            if index < 0 or index >= len(artifacts):
                console.print(f"[red]索引超出范围，当前共 {len(artifacts)} 个输出物 (0-{len(artifacts)-1})[/red]")
                return None
            if delete_artifact(loop.session_id, index):
                console.print(f"[green]已删除输出物 #{index}[/green]")
            else:
                console.print(f"[red]删除失败[/red]")
        else:
            artifacts = list_artifacts(loop.session_id)
            if not artifacts:
                console.print("[dim]当前会话没有生成输出物[/dim]")
            else:
                table = Table(title=f"Artifacts (Session: {loop.session_id})")
                table.add_column("#", style="cyan", width=4)
                table.add_column("Type", style="cyan", width=10)
                table.add_column("Path", width=55)
                table.add_column("Description", width=25)
                table.add_column("Time", width=20)
                for i, a in enumerate(artifacts):
                    table.add_row(str(i), a.get("type", ""), a.get("path", ""), a.get("description", ""), a.get("registered_at", ""))
                console.print(table)
        return None

    def cmd_skill(args: str):
        from data_agent.agent.loop import get_skill_loader
        loader = get_skill_loader()
        if loader is None:
            console.print("[yellow]Skill system not initialized[/yellow]")
            return None
        parts = args.split() if args else []
        if not parts:
            console.print(loader.format_list())
            return None
        action = parts[0]
        if action == "load" and len(parts) >= 2:
            console.print(f"[green]{loader.load(parts[1])}[/green]")
        elif action == "unload" and len(parts) >= 2:
            console.print(f"[green]{loader.unload(parts[1])}[/green]")
        elif action == "install" and len(parts) >= 3:
            scope = "global" if "--global" in args else "project"
            console.print(f"[green]{loader.install(parts[1], parts[2], scope)}[/green]")
        elif action == "uninstall" and len(parts) >= 2:
            scope = "global" if "--global" in args else "project"
            console.print(f"[green]{loader.uninstall(parts[1], scope)}[/green]")
        else:
            console.print("[yellow]Usage: /skill [load|unload|install|uninstall] <name>[/yellow]")
            console.print(loader.format_list())
        return None

    def cmd_mcp(args: str):
        parts = args.split() if args else []
        action = parts[0] if parts else "status"

        if action == "status":
            from data_agent.agent.loop import get_mcp_manager
            mcp_mgr = get_mcp_manager()
            if mcp_mgr is None:
                console.print("[dim]MCP not configured or not enabled[/dim]")
            else:
                status = mcp_mgr.health_check()
                if status:
                    table = Table(title="MCP Servers")
                    table.add_column("Server", style="cyan")
                    table.add_column("Status")
                    table.add_column("Tools", width=40)
                    for name, info in status.items():
                        table.add_row(name, info.get("status", "unknown"), info.get("tools", ""))
                    console.print(table)
                else:
                    console.print("[dim]No MCP servers connected[/dim]")
        else:
            console.print("[yellow]Usage: /mcp [status|add|remove|enable|disable] [options][/yellow]")
        return None

    def cmd_object(args: str):
        from data_agent.object_manager import get_object_manager
        from data_agent.session.workspace import workspace
        from data_agent.tools.knowledge_tools import set_active_object
        from data_agent.session.history import bind_session_to_object, unbind_session_from_object

        parts = args.split(maxsplit=1) if args else []
        if not parts:
            console.print("[yellow]Usage: /object create|list|switch|info|archive <name>[/yellow]")
            return None

        action = parts[0]
        name = parts[1] if len(parts) > 1 else ""
        mgr = get_object_manager()

        if action == "create":
            if not name:
                console.print("[yellow]Usage: /object create <name>[/yellow]")
                return None
            try:
                mgr.create(name)
                mgr.bind_session(name, loop.session_id)
                workspace.set_object(name)
                set_active_object(name)
                console.print(f"[green]对象 '{name}' 已创建并激活[/green]")
            except FileExistsError as e:
                console.print(f"[red]{e}[/red]")
        elif action == "list":
            objects = mgr.list_objects()
            if not objects:
                console.print("[dim]没有分析对象。使用 /object create <name> 创建。[/dim]")
            else:
                table = Table(title="Analysis Objects")
                table.add_column("Name", style="cyan", width=20)
                table.add_column("Status", width=10)
                table.add_column("Created", width=12)
                table.add_column("Sessions", width=5)
                table.add_column("Description", width=30)
                for obj in objects:
                    active_marker = " *" if obj["name"] == workspace.active_object else ""
                    table.add_row(obj["name"] + active_marker, obj.get("status", ""), obj.get("created", ""), str(len(obj.get("sessions", []))), obj.get("description", ""))
                console.print(table)
        elif action == "switch":
            # 使用统一的绑定接口
            result = bind_session_to_object(loop.session_id, name)
            if result["success"]:
                workspace.set_object(name)
                set_active_object(name)
                loop.invalidate_prompt_cache()
                console.print(f"[green]{result['message']}[/green]")
            else:
                console.print(f"[red]{result['message']}[/red]")
        elif action == "info":
            obj_name = workspace.active_object
            if not obj_name:
                console.print("[dim]当前处于 inbox 模式（无归属对象）[/dim]")
                return None
            meta = mgr.get(obj_name)
            if meta:
                # 显示该会话在对象中的知识贡献
                knowledge_info = mgr.extract_session_knowledge(obj_name, loop.session_id)
                knowledge_summary = (
                    f"本会话贡献: {knowledge_info['experience_entries']} 条经验"
                    + (" + 领域知识" if knowledge_info["has_domain"] else "")
                    + (" + 项目规则" if knowledge_info["has_rules"] else "")
                )
                console.print(Panel(
                    f"名称: {meta['name']}\n描述: {meta.get('description', '')}\n状态: {meta.get('status', '')}\n创建: {meta.get('created', '')}\n关联会话: {', '.join(meta.get('sessions', []))}\n标签: {', '.join(meta.get('tags', []))}\n{knowledge_summary}",
                    title=f"Object: {obj_name}", border_style="cyan",
                ))
        elif action == "archive":
            if not name:
                console.print("[yellow]Usage: /object archive <name>[/yellow]")
                return None
            result = mgr.archive(name)
            if result:
                if workspace.active_object == name:
                    unbind_session_from_object(loop.session_id)
                    workspace.clear_object()
                    set_active_object(None)
                    loop.invalidate_prompt_cache()
                console.print(f"[green]对象 '{name}' 已归档[/green]")
            else:
                console.print(f"[red]对象 '{name}' 不存在[/red]")
        elif action == "rename":
            parts2 = name.split(maxsplit=1) if name else []
            if len(parts2) < 2:
                console.print("[yellow]Usage: /object rename <old_name> <new_name>[/yellow]")
                return None
            old_n, new_n = parts2[0], parts2[1]
            result = mgr.rename(old_n, new_n)
            if result is None:
                console.print(f"[red]对象 '{old_n}' 不存在[/red]")
            elif isinstance(result, str):
                console.print(f"[red]{result}[/red]")
            else:
                if workspace.active_object == old_n:
                    from data_agent.session.history import bind_session_to_object
                    workspace.set_object(new_n)
                    set_active_object(new_n)
                    loop.invalidate_prompt_cache()
                console.print(f"[green]对象 '{old_n}' 已重命名为 '{new_n}'[/green]")
        else:
            console.print("[yellow]Unknown action. Use: create|list|switch|info|archive|rename[/yellow]")
        return None

    def cmd_bind(args: str):
        """绑定当前会话到对象。支持换绑（自动处理知识迁移）。"""
        from data_agent.session.workspace import workspace
        from data_agent.tools.knowledge_tools import set_active_object
        from data_agent.session.history import bind_session_to_object

        name = args.strip()
        if not name:
            console.print("[yellow]Usage: /bind <object_name>[/yellow]")
            return None

        result = bind_session_to_object(loop.session_id, name)
        if result["success"]:
            workspace.set_object(name)
            set_active_object(name)
            loop.invalidate_prompt_cache()
            console.print(f"[green]{result['message']}[/green]")
            if result.get("from_object"):
                console.print(f"[dim]知识已从 '{result['from_object']}' 迁移到 '{name}'[/dim]")
        else:
            console.print(f"[red]{result['message']}[/red]")
        return None

    def cmd_unbind(args: str):
        """解除当前会话的对象绑定。"""
        from data_agent.session.workspace import workspace
        from data_agent.tools.knowledge_tools import set_active_object
        from data_agent.session.history import unbind_session_from_object

        result = unbind_session_from_object(loop.session_id)
        if result["success"]:
            workspace.clear_object()
            set_active_object(None)
            loop.invalidate_prompt_cache()
            console.print(f"[green]{result['message']}[/green]")
        else:
            console.print(f"[red]{result['message']}[/red]")
        return None

    def cmd_inbox(args: str):
        from data_agent.session.workspace import workspace
        from data_agent.tools.knowledge_tools import set_active_object
        from data_agent.session.history import unbind_session_from_object

        result = unbind_session_from_object(loop.session_id)
        workspace.clear_object()
        set_active_object(None)
        loop.invalidate_prompt_cache()
        console.print("[green]已切回到 inbox 模式[/green]")
        return None

    def cmd_migrate(args: str):
        from data_agent.object_manager import get_object_manager
        from data_agent.session.workspace import workspace
        if not args:
            console.print("[yellow]Usage: /migrate <filename>[/yellow]")
            return None
        filename = args.strip("\"'")
        if not workspace.active_object:
            console.print("[yellow]请先切换到一个对象（/object switch <name>）再迁移文件[/yellow]")
            return None
        mgr = get_object_manager()
        try:
            mgr.migrate_from_inbox(workspace.active_object, filename)
            console.print(f"[green]文件 '{filename}' 已迁移到对象 '{workspace.active_object}'[/green]")
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
        return None

    def cmd_rewind(args: str):
        if args.strip() == "undo":
            # 恢复最近的 rewind 快照
            from pathlib import Path
            snapshots_dir = Path(get_config().sessions_resolved) / loop.session_id / "rewind_snapshots"
            if not snapshots_dir.exists():
                console.print("[dim]没有可恢复的快照[/dim]")
                return None
            snapshots = sorted(snapshots_dir.glob("rewind_*.json"), reverse=True)
            if not snapshots:
                console.print("[dim]没有可恢复的快照[/dim]")
                return None
            data = json.loads(snapshots[0].read_text(encoding="utf-8"))
            loop.messages = data["messages"]
            snapshots[0].unlink()
            console.print(f"[green]已恢复到快照 {snapshots[0].name}[/green]")
            return None

        if not loop.messages:
            console.print("[dim]当前没有对话历史[/dim]")
            return None

        rounds = _get_conversation_rounds(loop.messages)
        if not rounds:
            console.print("[dim]当前没有对话历史[/dim]")
            return None

        console.print("[bold]对话轮次：[/bold]")
        for i, r in enumerate(rounds):
            console.print(_format_round_for_rewind(i + 1, r))
        console.print()

        try:
            choice = _repl_input(
                f"选择要编辑重发的轮次 (1-{len(rounds)}, Esc 取消) >> ",
                allow_escape=True,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]已取消[/dim]")
            return None

        if not choice or not choice.isdigit():
            console.print("[dim]已取消[/dim]")
            return None

        round_num = int(choice)
        if round_num < 1 or round_num > len(rounds):
            console.print(f"[red]无效编号: {choice}，请输入 1-{len(rounds)}[/red]")
            return None

        # Extract user message from the target round for re-editing
        target_round = rounds[round_num - 1]
        user_msg_text = ""
        for msg in target_round:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                user_msg_text = content if isinstance(content, str) else ""
                break

        # Keep rounds before the selected one
        messages_to_keep = sum(len(r) for r in rounds[: round_num - 1])
        removed = len(loop.messages) - messages_to_keep

        try:
            if removed > 0:
                confirm = _repl_input(
                    f"删除 Round {round_num}-{len(rounds)} ({removed} 条消息) 并编辑重发？[y/N] ",
                    allow_escape=True,
                ).strip().lower()
            else:
                confirm = _repl_input(
                    f"删除 Round {round_num} 并编辑重发？[y/N] ",
                    allow_escape=True,
                ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]已取消[/dim]")
            return None

        if confirm != "y":
            console.print("[dim]已取消[/dim]")
            return None

        # 保存快照以便撤销
        import json as _json
        from pathlib import Path as _Path
        from datetime import datetime as _dt
        snapshots_dir = _Path(get_config().sessions_resolved) / loop.session_id / "rewind_snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = snapshots_dir / f"rewind_{ts}.json"
        snapshot_path.write_text(
            _json.dumps({"messages": loop.messages, "rewound_at": ts}, default=str, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        loop.messages = loop.messages[:messages_to_keep]

        console.print(
            f"[green]已回退到 Round {round_num} 之前，"
            f"删除了 {removed} 条消息[/green]"
        )
        console.print("[dim]快照已保存，可用 /rewind undo 恢复[/dim]")

        # Return the user message as chat input for re-editing
        if user_msg_text:
            console.print(f"\n[cyan]原始消息：[/cyan]{user_msg_text[:200]}")
            console.print("[dim]按 Enter 直接发送，或修改后发送[/dim]")
            try:
                edited = _repl_input("data-agent >> ").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if edited:
                return edited
        return None

    # Register all commands
    CMD.register("exit", cmd_exit, "退出并自动保存", aliases=["q"])
    CMD.register("help", cmd_help, "显示帮助信息", aliases=["h", "?"])
    CMD.register("report", cmd_report, "对当前数据生成完整分析报告")
    CMD.register("export", cmd_export, "导出当前对话分析结果 (html/markdown)")
    CMD.register("compact", cmd_compact, "手动压缩上下文")
    CMD.register("clear", cmd_clear, "清空对话历史")
    CMD.register("data", cmd_data, "预加载数据文件")
    CMD.register("bind", cmd_bind, "绑定当前会话到对象")
    CMD.register("unbind", cmd_unbind, "解除会话的对象绑定")
    CMD.register("tasks", cmd_tasks, "列出项目任务")
    CMD.register("analysis", cmd_analysis, "分析状态管理 (status/requirements/spec/evidence/reset)")
    CMD.register("save", cmd_save, "保存当前会话")
    CMD.register("sessions", cmd_sessions, "列出已保存的会话")
    CMD.register("sessions switch", cmd_sessions_switch, "切换到指定会话（保留当前会话状态）")
    CMD.register("resume", cmd_resume, "恢复会话")
    CMD.register("history", cmd_history, "查看历史分析记录")
    CMD.register("artifacts", cmd_artifacts, "列出或删除会话输出物")
    CMD.register("skill", cmd_skill, "技能管理 (load/unload/install/uninstall)")
    CMD.register("mcp", cmd_mcp, "MCP 服务器管理")
    CMD.register("object", cmd_object, "对象管理 (create/list/switch/info/archive)，兼容旧命令")
    CMD.register("project", cmd_object, "项目管理 (create/list/switch/info/archive)")
    CMD.register("inbox", cmd_inbox, "切回到 inbox 模式")
    CMD.register("migrate", cmd_migrate, "将 inbox 文件迁移到当前对象")
    CMD.register("rewind", cmd_rewind, "回退对话到之前的状态")

    def cmd_branch(args: str):
        result = branch_session(loop.session_id, args.strip())
        if result["success"]:
            console.print(f"[green]已创建分支: {result['session_id']}[/green]")
            console.print(f"[dim]使用 /resume {result['session_id']} 切换到该分支[/dim]")
        else:
            console.print(f"[red]{result['message']}[/red]")
        return None

    def cmd_branches(args: str):
        branches = list_branches(loop.session_id)
        if not branches:
            console.print("[dim]当前会话没有分支[/dim]")
        else:
            table = Table(title=f"Branches of {loop.session_id}")
            table.add_column("Session ID", style="cyan", width=14)
            table.add_column("Branch Name", width=20)
            table.add_column("Saved At", width=20)
            table.add_column("Messages", width=8)
            for b in branches:
                table.add_row(b["session_id"], b["branch_name"], b["saved_at"], str(b["message_count"]))
            console.print(table)
        return None

    CMD.register("branch", cmd_branch, "创建当前会话的分支 (fork)")
    CMD.register("branches", cmd_branches, "列出当前会话的所有分支")

    # ── 输入处理函数（首次输入和主循环共用） ──
    def _process_input(user_input: str) -> None:
        """处理一条用户输入：命令分发或对话。"""
        if not user_input:
            return

        # Direct exit (no / prefix)
        if user_input.lower() in ("q", "exit"):
            cmd_exit("")
            return

        # Command dispatch via registry
        if user_input.startswith("/"):
            parts = user_input[1:].split(None, 2)
            # Try two-word command first (e.g. "sessions switch")
            cmd_name = parts[0] if parts else ""
            cmd_args = " ".join(parts[1:]) if len(parts) > 1 else ""
            if len(parts) >= 2:
                two_word = f"{parts[0]} {parts[1]}"
                if CMD._commands.get(two_word):
                    cmd_name = two_word
                    cmd_args = parts[2] if len(parts) > 2 else ""
            result = CMD.execute(cmd_name, cmd_args)
            if not _ctx["running"]:
                return
            if result is None:
                return
            if isinstance(result, ToolResult):
                console.print(result.to_cli())
                return
            if isinstance(result, str):
                user_input = result
            else:
                return

        # ── Normal conversation (with ESC interrupt support + diff task display) ──

        from data_agent.session.task_display import TaskDisplay

        task_display = TaskDisplay(session_id=loop.session_id)
        done_event = threading.Event()
        result_holder: dict = {"result": None, "error": None}

        pauser = _CLIPauser()
        loop.cli_pauser = pauser

        def _run():
            try:
                result_holder["result"] = loop.run_turn(user_input)
            except Exception as e:
                result_holder["error"] = e
            finally:
                done_event.set()

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()

        # Diff-based task display: show spinner, print changes as they happen
        console.print(f"[dim]分析中... (按 ESC 中断)[/dim]")
        last_diff_len = 0
        while not done_event.is_set():
            pauser.check_plain()
            # Check for task status changes and print diffs
            diff = task_display.diff_lines()
            for line in diff:
                console.print(f"[dim]{line}[/dim]")
            if _check_esc_key():
                loop.request_interrupt()
                console.print("\n[yellow]正在中断...[/yellow]")
                break
            done_event.wait(0.3)
        # Final diff
        pauser.check_plain()
        diff = task_display.diff_lines()
        for line in diff:
            console.print(f"[dim]{line}[/dim]")

        loop.cli_pauser = None

        worker.join(timeout=10)

        if result_holder["error"] is not None:
            console.print(f"[bold red]Error:[/bold red] {result_holder['error']}")
        elif result_holder["result"] is not None:
            reply = result_holder["result"]
            if reply:
                safe_reply = reply.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")
                console.print()
                console.print(Markdown(safe_reply))
                console.print()
        else:
            console.print("[yellow][已中断] 分析已停止。你可以继续输入新问题。[/yellow]")

    # ── 处理启动时的首次输入（如有） ──
    if first_input:
        _process_input(first_input)

    # ── Main loop ──
    while _ctx["running"]:
        try:
            user_input = _repl_input("data-agent >> ").strip()
        except (EOFError, KeyboardInterrupt):
            if loop.messages:
                save_session(loop.messages, loop.session_id, data_file=loop._last_data_file)
                console.print(f"\n[dim]Session saved: {loop.session_id}[/dim]")
            console.print("[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        _process_input(user_input)
