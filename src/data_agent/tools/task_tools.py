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


def _session_id() -> str:
    try:
        from data_agent.agent.context import get_current_context
        ctx = get_current_context()
        if ctx is not None:
            return ctx.session_id
    except Exception:
        pass
    return _current_session_id


@registry.register(
    name="task_create",
    description=(
        "创建分析任务。subject 为简短标题（祈使句如 '分析收入趋势'），"
        "description 为详细描述。"
        "复杂分析应先创建任务规划再逐步执行。"
        "支持批量创建：传入 tasks JSON 数组可一次性创建多个任务，减少轮次消耗。"
    ),
    schema_overrides={
        "tasks": {"description": '批量创建模式：JSON 数组 [{"subject": "...", "description": "..."}]'},
    },
)
def task_create(
    subject: str = "",
    description: str = "",
    tasks: str = "",
) -> str:
    """创建新任务。支持单个或批量创建。"""
    if tasks:
        # 批量创建模式
        try:
            task_list_data = json.loads(tasks)
        except json.JSONDecodeError:
            return json.dumps({"error": "tasks 必须是有效的 JSON 数组"}, ensure_ascii=False)
        if not isinstance(task_list_data, list):
            return json.dumps({"error": "tasks 必须是 JSON 数组"}, ensure_ascii=False)

        created = []
        for t in task_list_data:
            if not isinstance(t, dict):
                continue
            task = task_manager.create(
                subject=t.get("subject", ""),
                description=t.get("description", ""),
                session_id=_session_id(),
            )
            created.append(task)
        return json.dumps({"created": len(created), "tasks": created}, ensure_ascii=False, indent=2)

    # 单个创建模式
    if not subject:
        return json.dumps({"error": "subject 不能为空"}, ensure_ascii=False)
    task = task_manager.create(
        subject=subject,
        description=description,
        session_id=_session_id(),
    )
    return json.dumps(task, ensure_ascii=False, indent=2)


@registry.register(
    name="task_update",
    description=(
        "更新任务状态。status 可选：pending/in_progress/completed/deleted。"
        "开始执行时设为 in_progress，完成后设为 completed。"
        "支持批量更新：传入 updates JSON 数组可一次性更新多个任务，减少轮次消耗。"
        "addBlocks 指定此任务完成后才可执行的任务 ID 列表。"
        "addBlockedBy 指定必须先完成的任务 ID 列表。"
    ),
    schema_overrides={
        "updates": {"description": '批量更新模式：JSON 数组 [{"task_id": 1, "status": "completed"}, ...]'},
    },
)
def task_update(
    task_id: int = 0,
    status: str = "",
    owner: str = "",
    addBlocks: Optional[str] = None,
    addBlockedBy: Optional[str] = None,
    updates: str = "",
) -> str:
    """更新任务。支持单个或批量更新。"""
    if updates:
        # 批量更新模式
        try:
            update_list = json.loads(updates)
        except json.JSONDecodeError:
            return json.dumps({"error": "updates 必须是有效的 JSON 数组"}, ensure_ascii=False)
        if not isinstance(update_list, list):
            return json.dumps({"error": "updates 必须是 JSON 数组"}, ensure_ascii=False)

        results = []
        for u in update_list:
            if not isinstance(u, dict):
                continue
            tid = u.get("task_id")
            if not tid:
                continue
            blocks = u.get("addBlocks")
            blocked_by = u.get("addBlockedBy")
            task = task_manager.update(
                tid,
                status=u.get("status"),
                owner=u.get("owner"),
                addBlocks=blocks if isinstance(blocks, list) else (json.loads(blocks) if isinstance(blocks, str) else None),
                addBlockedBy=blocked_by if isinstance(blocked_by, list) else (json.loads(blocked_by) if isinstance(blocked_by, str) else None),
            )
            if task:
                results.append(task)
        return json.dumps({"updated": len(results), "tasks": results}, ensure_ascii=False, indent=2)

    # 单个更新模式
    if not task_id:
        return json.dumps({"error": "task_id 不能为空"}, ensure_ascii=False)
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
