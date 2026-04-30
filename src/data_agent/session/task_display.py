"""实时任务进度显示面板。

扁平列表 + 状态图标 + 依赖提示 + spinner，
对标 Claude Code 的 Task 状态面板。
"""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from data_agent.session.task_manager import task_manager

_SPINNER = "line"


class TaskDisplay:
    """Claude Code 风格的任务面板。

    - 扁平列表，无树状层级
    - in_progress 用 spinner
    - blocked 任务显示 (blocked)
    - 状态原地更新
    - 支持增量 diff 输出（CLI 用）
    """

    def __init__(self, session_id: str = ""):
        self._message = "分析中... (按 ESC 中断)"
        self._session_id = session_id
        # Snapshot current tasks at creation so diff_lines only shows changes during this turn
        self._prev_snapshot: dict[int, str] = {
            t["id"]: t.get("status", "pending")
            for t in task_manager.list_all()
            if t.get("status") not in ("deleted",)
        }

    def set_message(self, msg: str) -> None:
        self._message = msg

    def _current_tasks(self) -> list[dict]:
        tasks = task_manager.list_all()
        if self._session_id:
            # Show all tasks but prefer current session's tasks first
            session_tasks = [t for t in tasks if t.get("session_id") == self._session_id]
            other_tasks = [t for t in tasks if t.get("session_id") != self._session_id]
            return session_tasks + other_tasks
        return tasks

    def render(self) -> Panel:
        tasks = self._current_tasks()

        if not tasks:
            return Panel(
                Spinner(_SPINNER, text=f"[bold green]{self._message}[/bold green]"),
                border_style="green",
                padding=(0, 1),
            )

        rows: list = []
        for t in tasks:
            status = t.get("status", "pending")
            subject = t.get("subject", "")
            blocked_by = t.get("blockedBy", [])

            if status == "completed":
                line = Text()
                line.append("  ", style="green")
                line.append("√ ", style="bold green")
                line.append(f"#{t['id']}: ", style="cyan")
                line.append(subject, style="dim")
                rows.append(line)

            elif status == "in_progress":
                rows.append(Spinner(
                    _SPINNER,
                    text=Text.from_markup(f"  [yellow]●[/yellow] [cyan]#{t['id']}:[/cyan] {subject}"),
                ))

            elif status == "deleted":
                continue

            else:  # pending
                line = Text()
                line.append("  ", style="")
                line.append("○ ", style="dim")
                line.append(f"#{t['id']}: ", style="cyan")
                line.append(subject)
                if blocked_by:
                    line.append(" (blocked)", style="dim red")
                rows.append(line)

        done = sum(1 for t in tasks if t["status"] == "completed")
        total = len([t for t in tasks if t["status"] != "deleted"])
        rows.append(Text(f"{done}/{total} completed", style="dim"))

        return Panel(
            Group(*rows),
            title="[bold]Tasks[/bold]",
            border_style="blue",
            padding=(0, 1),
        )

    def diff_lines(self) -> list[str]:
        """Return changed task status lines since last call. Used by CLI for diff-based output."""
        tasks = self._current_tasks()
        current: dict[int, str] = {t["id"]: t.get("status", "pending") for t in tasks if t.get("status") != "deleted"}
        lines: list[str] = []
        for tid, status in current.items():
            prev = self._prev_snapshot.get(tid)
            if prev is None and status != "deleted":
                # New task appeared
                t = next((x for x in tasks if x["id"] == tid), None)
                if t:
                    marker = {"in_progress": "●", "pending": "○"}.get(status, "○")
                    lines.append(f"  {marker} #{tid}: {t.get('subject', '')}")
            elif prev != status:
                # Status changed
                t = next((x for x in tasks if x["id"] == tid), None)
                if t:
                    if status == "completed":
                        lines.append(f"  √ #{tid}: {t.get('subject', '')} [completed]")
                    elif status == "in_progress":
                        lines.append(f"  ● #{tid}: {t.get('subject', '')} [started]")
                    elif status == "deleted":
                        lines.append(f"  - #{tid}: {t.get('subject', '')} [deleted]")

        self._prev_snapshot = current
        return lines
