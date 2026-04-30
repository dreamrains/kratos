"""任务管理工具，参考 Claude Code 的 TaskCreate/TaskUpdate 设计。

复杂分析时，LLM 先用 task_create 规划步骤，再逐步 task_update 跟踪进度。
每个 task 是一个具体目标，不是流程阶段。
"""

from __future__ import annotations

import json
from typing import Optional

from data_agent.session.task_manager import task_manager
from data_agent.tools.registry import registry

# 当前会话 ID（由 AgentLoop 设置）
_current_session_id: str = ""


def set_task_session(session_id: str):
    global _current_session_id
    _current_session_id = session_id


@registry.register(
    name="task_create",
    description=(
        "创建分析任务。subject 为简短标题（祈使句如 '分析收入趋势'），"
        "description 为详细描述。"
        "复杂分析应先创建任务规划再逐步执行。"
    ),
)
def task_create(
    subject: str,
    description: str = "",
) -> str:
    """创建新任务。"""
    task = task_manager.create(
        subject=subject,
        description=description,
        session_id=_current_session_id,
    )
    return json.dumps(task, ensure_ascii=False, indent=2)


@registry.register(
    name="task_update",
    description=(
        "更新任务状态。status 可选：pending/in_progress/completed/deleted。"
        "开始执行时设为 in_progress，完成后设为 completed。"
        "addBlocks 指定此任务完成后才可执行的任务 ID 列表。"
        "addBlockedBy 指定必须先完成的任务 ID 列表。"
    ),
)
def task_update(
    task_id: int,
    status: str = "",
    owner: str = "",
    addBlocks: Optional[str] = None,
    addBlockedBy: Optional[str] = None,
) -> str:
    """更新任务。"""
    blocks = json.loads(addBlocks) if addBlocks else None
    blocked_by = json.loads(addBlockedBy) if addBlockedBy else None

    task = task_manager.update(
        task_id,
        status=status or None,
        owner=owner or None,
        addBlocks=blocks,
        addBlockedBy=blocked_by,
    )
    if task is None:
        return json.dumps({"error": f"Task {task_id} not found"}, ensure_ascii=False)
    return json.dumps(task, ensure_ascii=False, indent=2)


@registry.register(
    name="task_get",
    description="获取指定任务的详情。",
)
def task_get(task_id: int) -> str:
    task = task_manager.get(task_id)
    if task is None:
        return json.dumps({"error": f"Task {task_id} not found"}, ensure_ascii=False)
    return json.dumps(task, ensure_ascii=False, indent=2)


@registry.register(
    name="task_list",
    description="列出所有分析任务及状态。",
)
def task_list() -> str:
    return task_manager.format_list()
