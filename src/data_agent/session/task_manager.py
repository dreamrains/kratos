"""任务管理系统：文件级持久化，跨会话可见。

参考 Claude Code 的 Task 系统设计：
Task 是持久化工作项，LLM 完全控制生命周期，系统只做存取和展示。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from data_agent.config import get_config


WORKFLOW_FIELDS = {
    "workflow_id": "",
    "project_name": "",
    "stage": "",
    "node_type": "",
    "analysis_spec_id": "",
    "required_data": [],
    "expected_output": "",
    "evidence_ids": [],
    "confirmation_ids": [],
    "result_summary": "",
    "limitations": "",
    "confidence": "",
    "required_capability": "",
    "evidence_requirements": [],
    "confirmation_policy": {},
}


class TaskManager:
    """基于文件的任务管理器。

    每个 task 的生命周期：pending → in_progress → completed
    支持 blocks/blockedBy 依赖关系（双向传播）。
    """

    def __init__(self, tasks_dir: Optional[Path] = None):
        self._dir = tasks_dir
        self._next_id_val = 0

    @property
    def dir(self) -> Path:
        if self._dir is None:
            cfg = get_config()
            self._dir = cfg.project_resolved / "tasks"
        self._dir.mkdir(parents=True, exist_ok=True)
        return self._dir

    def _init_next_id(self) -> None:
        if self._next_id_val == 0:
            ids = [int(f.stem.split("_")[1]) for f in self.dir.glob("task_*.json")]
            self._next_id_val = max(ids, default=0) + 1

    def _alloc_id(self) -> int:
        self._init_next_id()
        tid = self._next_id_val
        self._next_id_val += 1
        return tid

    def _path(self, tid: int) -> Path:
        return self.dir / f"task_{tid}.json"

    def _load(self, tid: int) -> dict:
        p = self._path(tid)
        if not p.exists():
            raise ValueError(f"Task {tid} not found")
        return self._normalize(json.loads(p.read_text(encoding="utf-8")))

    def _save(self, task: dict) -> None:
        task = self._normalize(task)
        self._path(task["id"]).write_text(
            json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _normalize(self, task: dict) -> dict:
        for key, value in WORKFLOW_FIELDS.items():
            if key not in task:
                task[key] = list(value) if isinstance(value, list) else value
        task.setdefault("session_id", "")
        task.setdefault("owner", "")
        task.setdefault("blockedBy", [])
        task.setdefault("blocks", [])
        return task

    def _clear_dependency(self, completed_id: int) -> None:
        """完成时从所有其他任务的 blockedBy 中移除 completed_id。"""
        for f in self.dir.glob("task_*.json"):
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
                if completed_id in t.get("blockedBy", []):
                    t["blockedBy"].remove(completed_id)
                    self._save(t)
            except (json.JSONDecodeError, OSError):
                continue

    def create(
        self,
        subject: str,
        description: str = "",
        session_id: str = "",
        **workflow_fields,
    ) -> dict:
        """创建新任务。"""
        task = {
            "id": self._alloc_id(),
            "subject": subject,
            "description": description,
            "status": "pending",
            "blockedBy": [],
            "blocks": [],
            "owner": "",
            "session_id": session_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        for key in WORKFLOW_FIELDS:
            if key in workflow_fields and workflow_fields[key] is not None:
                task[key] = workflow_fields[key]
        self._save(task)
        return task

    def get(self, tid: int) -> Optional[dict]:
        try:
            return self._load(tid)
        except ValueError:
            return None

    def update(
        self,
        tid: int,
        status: Optional[str] = None,
        owner: Optional[str] = None,
        addBlocks: Optional[list[int]] = None,
        addBlockedBy: Optional[list[int]] = None,
        **workflow_fields,
    ) -> Optional[dict]:
        """更新任务。status 可选值：pending / in_progress / completed / deleted。"""
        try:
            task = self._load(tid)
        except ValueError:
            return None

        if status is not None:
            if status not in ("pending", "in_progress", "completed", "deleted"):
                return None
            task["status"] = status

            if status == "completed":
                self._clear_dependency(tid)

            if status == "deleted":
                self._path(tid).unlink(missing_ok=True)
                return {"id": tid, "status": "deleted"}

        if owner is not None:
            task["owner"] = owner

        if addBlocks is not None:
            task["blocks"] = list(set(task.get("blocks", []) + addBlocks))
            for blocked_id in addBlocks:
                try:
                    blocked = self._load(blocked_id)
                    if tid not in blocked["blockedBy"]:
                        blocked["blockedBy"].append(tid)
                        self._save(blocked)
                except ValueError:
                    pass

        if addBlockedBy is not None:
            task["blockedBy"] = list(set(task.get("blockedBy", []) + addBlockedBy))

        for key in WORKFLOW_FIELDS:
            if key in workflow_fields and workflow_fields[key] is not None:
                task[key] = workflow_fields[key]

        self._save(task)
        return task

    def list_all(self) -> list[dict]:
        tasks = []
        for f in sorted(self.dir.glob("task_*.json")):
            try:
                tasks.append(self._normalize(json.loads(f.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, OSError):
                continue
        return tasks

    def list_for_scope(self, session_id: str = "", project_name: str = "") -> list[dict]:
        tasks = self.list_all()
        scoped = [
            t for t in tasks
            if (session_id and t.get("session_id") == session_id)
            or (project_name and t.get("project_name") == project_name)
        ]
        others = [t for t in tasks if t not in scoped]
        return scoped + others

    def list_by_status(self, status: str) -> list[dict]:
        return [t for t in self.list_all() if t.get("status") == status]

    def format_list(self, session_id: str = "", project_name: str = "") -> str:
        """纯文本格式化任务列表。"""
        tasks = self.list_for_scope(session_id=session_id, project_name=project_name) if (session_id or project_name) else self.list_all()
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            status = t.get("status", "pending")
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]", "deleted": "[-]"}.get(status, "[?]")
            blocked = f" (blocked by: {t.get('blockedBy', [])})" if t.get("blockedBy") else ""
            workflow = f" [{t.get('stage')}/{t.get('node_type')}]" if t.get("stage") or t.get("node_type") else ""
            capability = f" capability={t.get('required_capability')}" if t.get("required_capability") else ""
            evidence = f" evidence={len(t.get('evidence_ids') or [])}" if t.get("evidence_ids") else ""
            scope = " *" if (session_id and t.get("session_id") == session_id) or (project_name and t.get("project_name") == project_name) else ""
            lines.append(f"{marker} #{t['id']}: {t['subject']}{workflow}{capability}{evidence}{blocked}{scope}")
        done = sum(1 for t in tasks if t["status"] == "completed")
        lines.append(f"\n({done}/{len(tasks)} completed)")
        return "\n".join(lines)

    def reset_for_testing(self) -> None:
        for f in self.dir.glob("task_*.json"):
            f.unlink(missing_ok=True)
        self._next_id_val = 0


# 全局实例
task_manager = TaskManager()
