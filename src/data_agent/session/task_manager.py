"""任务管理系统：文件级持久化；宿主管理可跨会话，公开工具按会话/项目范围访问。

参考 Claude Code 的 Task 系统设计：
一般 Task 保留模型工作项操作；分析 Task 的事实完成及依赖就绪由宿主已核交付投影决定。
"""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
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
    "analysis_plan_id": "",
    "step_id": "",
    "plan_sha256": "",
    "requirement_ids": [],
    "required_delivery_ids": [],
    "dataset_inputs": [],
    "dataset_contract_ids": [],
    "combination_mode": "",
    "required_evidence_step_ids": [],
    "required_data": [],
    "expected_output": "",
    "evidence_ids": [],
    "confirmation_ids": [],
    "result_summary": "",
    "limitations": "",
    "confidence": "",
    "required_capability": "",
    "evidence_requirements": [],
    "satisfied_evidence_requirements": [],
    "confirmation_policy": {},
}


PLAN_FIELDS = {
    "plan_id": "",
    "plan_version": 1,
    "plan_status": "",
    "task_kind": "plan_task",
    "source": "",
    "superseded_by": "",
    "archived_at": "",
    "completed_by": "",
    "completed_at": "",
}


class TaskManager:
    """基于文件的任务管理器。

    每个 task 的生命周期：pending → in_progress → completed
    支持 blocks/blockedBy 依赖关系（双向传播）。
    """

    def __init__(self, tasks_dir: Optional[Path] = None):
        self._dir = tasks_dir
        self._next_id_val = 0
        # Tool calls in one block execute in a ThreadPoolExecutor, so plan
        # authority mutations genuinely interleave. All check-then-act
        # transitions on the active plan must hold this reentrant lock.
        self._authority_lock = threading.RLock()

    @contextmanager
    def authority_guard(self, session_id: str = "", project_name: str = ""):
        """Serialize compound plan-authority transitions.

        The arguments are for readability at call sites; a single process-wide
        lock keeps the critical sections strictly ordered, which is the
        invariant the concurrent-supersede failure broke.
        """
        with self._authority_lock:
            yield

    @contextmanager
    def plan_transaction(self):
        """Roll back one compound plan projection under its authority lock."""
        with self._authority_lock:
            root=self.dir.resolve()
            before={p:p.read_bytes() for p in root.glob("*.json")}
            next_id=self._next_id_val
            try:
                yield
            except Exception:
                for path in root.glob("*.json"):
                    if path not in before and path.resolve().parent==root:path.unlink()
                for path,content in before.items():path.write_bytes(content)
                self._next_id_val=next_id
                raise

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
        for key, value in PLAN_FIELDS.items():
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
        for key in PLAN_FIELDS:
            if key in workflow_fields and workflow_fields[key] is not None:
                task[key] = workflow_fields[key]
        self._save(task)
        return task

    def get(self, tid: int) -> Optional[dict]:
        try:
            return self._load(tid)
        except ValueError:
            return None

    @staticmethod
    def _matches_scope(task: dict, session_id: str = "", project_name: str = "") -> bool:
        return (not session_id or task.get("session_id") == session_id) and (
            not project_name or task.get("project_name") == project_name
        )

    def get_for_scope(self, tid: int, session_id: str = "", project_name: str = "") -> Optional[dict]:
        """Resolve a public task reference with the same scope as task lists."""
        if type(tid) is not int or tid <= 0:
            return None
        task = self.get(tid)
        return task if task is not None and self._matches_scope(task, session_id, project_name) else None

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
            allowed = ("pending", "blocked", "in_progress", "completed", "failed", "superseded", "archived", "deleted")
            if status not in allowed:
                return None
            if status == "in_progress" and self._is_stage3c0b_scoped_task(task) and task.get("blockedBy"):
                return None
            if status == "completed" and self._is_stage3c0b_scoped_task(task):
                required=task.get("required_delivery_ids",[])
                projection=self._task_delivery_projection(task)
                if not required or any(d not in projection or projection[d]["gap"] is not None for d in required):
                    return None
            task["status"] = status

            if status == "completed":
                task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._clear_dependency(tid)

            if status == "failed":
                task["failed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if status == "archived":
                task["archived_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        for key in PLAN_FIELDS:
            if key in workflow_fields and workflow_fields[key] is not None:
                task[key] = workflow_fields[key]

        self._save(task)
        if (
            status in {"completed", "failed"}
            and self._is_stage3c0b_scoped_task(task)
            and task.get("plan_id")
            and task.get("plan_id") == self.get_active_plan_id(
                str(task.get("session_id") or ""), str(task.get("project_name") or "")
            )
        ):
            self.start_next_ready_stage3c0b_task(
                session_id=str(task.get("session_id") or ""),
                project_name=str(task.get("project_name") or ""),
                plan_id=str(task.get("plan_id") or ""),
            )
        return task

    def _is_stale(self, task: dict) -> bool:
        """Pending tasks older than 24 hours are considered stale."""
        if task.get("status") != "pending":
            return False
        created = task.get("created_at", "")
        if not created:
            return False
        from datetime import datetime, timedelta
        try:
            ct = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
            return datetime.now() - ct > timedelta(hours=24)
        except ValueError:
            return False

    def list_all(self, include_stale: bool = False) -> list[dict]:
        tasks = []
        for f in sorted(self.dir.glob("task_*.json")):
            try:
                tasks.append(self._normalize(json.loads(f.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, OSError):
                continue
        if not include_stale:
            tasks = [t for t in tasks if not self._is_stale(t)]
        return tasks

    def is_ready(self, task: dict) -> bool:
        task = self._normalize(dict(task))
        return task.get("status") == "pending" and not task.get("blockedBy")

    def start_next_ready_stage3c0b_task(
        self,
        *,
        session_id: str,
        project_name: str = "",
        plan_id: str = "",
    ) -> int | None:
        """Atomically establish the single current task for an active Stage 3C0B plan."""
        tasks = self.list_active_for_scope(
            session_id=session_id,
            project_name=project_name,
        )
        if plan_id:
            tasks = [task for task in tasks if task.get("plan_id") == plan_id]
        stage_tasks = [task for task in tasks if self._is_stage3c0b_scoped_task(task)]
        if any(task.get("status") == "in_progress" for task in stage_tasks):
            return None
        ready = sorted(
            (task for task in stage_tasks if self.is_ready(task)),
            key=lambda task: int(task.get("id") or 0),
        )
        if not ready:
            return None
        started = self.update(ready[0]["id"], status="in_progress")
        return int(started["id"]) if started is not None else None

    def _active_plans_path(self) -> Path:
        return self.dir / "active_plans.json"

    def _plan_key(self, session_id: str = "", project_name: str = "") -> str:
        return f"{session_id or ''}::{project_name or ''}"

    def _read_active_plans(self) -> dict:
        path = self._active_plans_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_active_plans(self, data: dict) -> None:
        path = self._active_plans_path()
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

    def get_active_plan_id(self, session_id: str = "", project_name: str = "") -> str:
        active = self._read_active_plans()
        value = active.get(self._plan_key(session_id, project_name), "")
        return str(value or "")

    def _get_active_plan_ids_for_scope(self, session_id: str = "", project_name: str = "") -> set[str]:
        active = self._read_active_plans()
        if session_id and not project_name:
            prefix = f"{session_id}::"
            return {str(plan_id) for key, plan_id in active.items() if key.startswith(prefix) and plan_id}
        if project_name and not session_id:
            suffix = f"::{project_name}"
            return {str(plan_id) for key, plan_id in active.items() if key.endswith(suffix) and plan_id}
        active_plan_id = active.get(self._plan_key(session_id, project_name), "")
        return {str(active_plan_id)} if active_plan_id else set()

    def _set_active_plan_id(self, plan_id: str, session_id: str = "", project_name: str = "") -> None:
        active = self._read_active_plans()
        active[self._plan_key(session_id, project_name)] = plan_id
        self._write_active_plans(active)

    def _session_project_tasks(
        self,
        session_id: str = "",
        project_name: str = "",
        include_stale: bool = False,
    ) -> list[dict]:
        return self._list_for_scope(
            session_id=session_id,
            project_name=project_name,
            include_global=False,
            include_stale=include_stale,
        )

    def _supersede_active_plan(self, session_id: str = "", project_name: str = "", superseded_by: str = "") -> None:
        active_plan_id = self.get_active_plan_id(session_id, project_name)
        if not active_plan_id:
            return
        for task in self._session_project_tasks(
            session_id=session_id,
            project_name=project_name,
            include_stale=True,
        ):
            if task.get("plan_id") != active_plan_id:
                continue
            if task.get("status") in ("pending", "blocked", "in_progress"):
                self.update(
                    task["id"],
                    status="superseded",
                    superseded_by=superseded_by,
                    plan_status="superseded",
                )

    def retire_active_plan_for_new_data(
        self,
        session_id: str = "",
        project_name: str = "",
        reason: str = "new_data_upload",
    ) -> dict:
        """Retire the exact active plan before a bound upload changes its data basis.

        A same-session upload is a data-scope transition, not another execution
        step in the old plan.  Keeping the old plan active makes the workspace
        resolver reject the newly derived analysis dataset and, worse, lets a
        later narrative reuse tasks whose dataset contract is no longer current.
        """
        with self._authority_lock:

            active_plan_id = self.get_active_plan_id(session_id, project_name)
            if not active_plan_id:
                return {
                    "retired": False,
                    "plan_id": "",
                    "reason": reason,
                    "session_id": session_id,
                    "project_name": project_name,
                    "tasks": [],
                }
            task_snapshots = [
                dict(task)
                for task in self._session_project_tasks(
                    session_id=session_id,
                    project_name=project_name,
                    include_stale=True,
                )
                if task.get("plan_id") == active_plan_id
                and task.get("status") in ("pending", "blocked", "in_progress")
            ]
            self._supersede_active_plan(
                session_id=session_id,
                project_name=project_name,
                superseded_by=reason,
            )
            active = self._read_active_plans()
            active.pop(self._plan_key(session_id, project_name), None)
            self._write_active_plans(active)
            return {
                "retired": True,
                "plan_id": active_plan_id,
                "reason": reason,
                "session_id": session_id,
                "project_name": project_name,
                "tasks": task_snapshots,
            }

    def restore_retired_plan(self, retirement: dict) -> dict:
        """Compensate a failed new-data transition without overwriting successors."""
        with self._authority_lock:

            if not isinstance(retirement, dict) or not retirement.get("retired"):
                return {"restored": False, "reason": "nothing_retired"}
            session_id = str(retirement.get("session_id") or "")
            project_name = str(retirement.get("project_name") or "")
            plan_id = str(retirement.get("plan_id") or "")
            reason = str(retirement.get("reason") or "new_data_upload")
            current_plan_id = self.get_active_plan_id(session_id, project_name)
            if current_plan_id == plan_id:
                return {"restored": False, "reason": "already_restored", "plan_id": plan_id}
            if current_plan_id:
                return {
                    "restored": False,
                    "reason": "successor_plan_active",
                    "plan_id": current_plan_id,
                }

            originals = [task for task in retirement.get("tasks") or [] if isinstance(task, dict)]
            current_tasks: list[tuple[dict, dict]] = []
            for original in originals:
                current = self.get(int(original.get("id") or 0))
                if (
                    current is None
                    or current.get("plan_id") != plan_id
                    or current.get("status") != "superseded"
                    or current.get("superseded_by") != reason
                ):
                    return {
                        "restored": False,
                        "reason": "retired_task_changed",
                        "plan_id": plan_id,
                    }
                current_tasks.append((current, original))

            for _current, original in current_tasks:
                self._save(dict(original))
            self._set_active_plan_id(plan_id, session_id, project_name)
            return {"restored": True, "reason": "ingestion_failed", "plan_id": plan_id}

    def active_plan_has_live_stage_tasks(self, session_id: str = "", project_name: str = "") -> bool:
        """True when the active plan still has non-terminal Stage3C0B tasks.

        An active structured plan is the single task authority: only the
        sanctioned retire path (new-data upload) or structured re-projection
        may replace it.  Silent supersede from manual/llm plan creation is
        what turned a transient scope refresh into a permanent error phase
        (R21 Codex M02 session death).
        """
        plan_id = self.get_active_plan_id(session_id, project_name)
        if not plan_id:
            return False
        for task in self._session_project_tasks(
            session_id=session_id, project_name=project_name, include_stale=True
        ):
            if task.get("plan_id") != plan_id:
                continue
            if task.get("status") in {"deleted", "archived", "superseded", "completed"}:
                continue
            if str(task.get("analysis_plan_id") or "") or str(task.get("step_id") or ""):
                return True
        return False

    def close_open_tasks_for_publication(
        self,
        session_id: str = "",
        project_name: str = "",
        reason: str = "superseded_by_publication",
    ) -> list[int]:
        """Close the active plan's open tasks when a final answer publishes.

        The task ledger is host bookkeeping: an honest published answer with
        declared boundaries must not leave tasks eternally pending (which the
        deterministic auditor would rightly flag).  Closing records an explicit
        terminal state with the closure reason instead of pretending the steps
        completed.
        """
        with self._authority_lock:
            plan_id = self.get_active_plan_id(session_id, project_name)
            if not plan_id:
                return []
            closed: list[int] = []
            for task in self._session_project_tasks(
                session_id=session_id, project_name=project_name, include_stale=True
            ):
                if task.get("plan_id") != plan_id:
                    continue
                if task.get("status") in {"pending", "blocked", "in_progress"}:
                    record = dict(task)
                    record["status"] = "closed_by_publication"
                    record["closure_reason"] = reason
                    self._save(record)
                    closed.append(int(record.get("id") or 0))
            # Keep the terminal structured plan as a read-only scope anchor.
            # A new explicit plan replaces it; dropping the pointer would make
            # the next turn attempt an unauthorized return to legacy raw access.
            tasks=self._session_project_tasks(session_id=session_id,project_name=project_name,include_stale=True)
            if not any(t.get("plan_id")==plan_id and self._is_stage3c0b_scoped_task(t) for t in tasks):
                active = self._read_active_plans()
                active.pop(self._plan_key(session_id, project_name), None)
                self._write_active_plans(active)
            return closed

    def create_plan(
        self,
        session_id: str = "",
        project_name: str = "",
        goal: str = "",
        source: str = "",
        analysis_spec_id: str = "",
        workflow_id: str = "",
    ) -> dict:
        with self._authority_lock:
            return self._create_plan_locked(session_id, project_name, goal, source, analysis_spec_id, workflow_id)

    def _create_plan_locked(
        self,
        session_id: str = "",
        project_name: str = "",
        goal: str = "",
        source: str = "",
        analysis_spec_id: str = "",
        workflow_id: str = "",
    ) -> dict:
        active_plan_id = self.get_active_plan_id(session_id, project_name)
        if (
            active_plan_id
            and source != "analysis_plan"
            and self.active_plan_has_live_stage_tasks(session_id, project_name)
        ):
            raise RuntimeError(
                "cannot supersede an active structured plan with live stage tasks "
                "from a non-structured plan; finish or explicitly retire it instead"
            )
        existing_versions = [
            int(t.get("plan_version") or 1)
            for t in self._session_project_tasks(
                session_id=session_id,
                project_name=project_name,
                include_stale=True,
            )
            if t.get("plan_id")
        ]
        version = max(existing_versions, default=0) + 1
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        self._supersede_active_plan(session_id=session_id, project_name=project_name, superseded_by=plan_id)
        self._set_active_plan_id(plan_id, session_id, project_name)
        return {
            "id": plan_id,
            "session_id": session_id,
            "project_name": project_name,
            "goal": goal,
            "version": version,
            "status": "active",
            "source": source,
            "previous_plan_id": active_plan_id,
            "analysis_spec_id": analysis_spec_id,
            "workflow_id": workflow_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def migrate_legacy_session_active_plan(self, session_id: str, project_name: str = "") -> dict:
        active_plan_id = self.get_active_plan_id(session_id, project_name)
        if active_plan_id:
            return {"active_plan_id": active_plan_id, "migrated": 0}
        scoped = self._list_for_scope(
            session_id=session_id,
            project_name=project_name,
            include_stale=True,
        )
        legacy = [t for t in scoped if not t.get("plan_id") and t.get("status") != "deleted"]
        completed = [t for t in legacy if t.get("status") == "completed"]
        if not completed:
            return {"active_plan_id": "", "migrated": 0}

        spec_id = completed[0].get("analysis_spec_id", "")
        plan = self.create_plan(
            session_id=session_id,
            project_name=project_name,
            goal="Migrated completed analysis plan",
            source="legacy_migration",
            analysis_spec_id=spec_id,
            workflow_id=completed[0].get("workflow_id", ""),
        )
        migrated = 0
        for task in legacy:
            if task.get("status") == "completed" and (not spec_id or task.get("analysis_spec_id") == spec_id):
                self.update(
                    task["id"],
                    plan_id=plan["id"],
                    plan_version=plan["version"],
                    plan_status="completed",
                    source=task.get("source") or "legacy_migration",
                )
                migrated += 1
            elif task.get("status") in ("pending", "blocked", "in_progress"):
                self.update(
                    task["id"],
                    status="superseded",
                    superseded_by=plan["id"],
                    source=task.get("source") or "legacy_migration",
                )
        return {"active_plan_id": plan["id"], "migrated": migrated}

    def _list_for_scope(
        self,
        session_id: str = "",
        project_name: str = "",
        include_global: bool = False,
        include_stale: bool = False,
    ) -> list[dict]:
        tasks = self.list_all(include_stale=include_stale)
        if not session_id and not project_name:
            return tasks

        scoped = [t for t in tasks if self._matches_scope(t, session_id, project_name)]
        if include_global:
            scoped.extend([
                t for t in tasks
                if not t.get("session_id") and not t.get("project_name")
            ])
        return scoped

    def list_for_scope(
        self,
        session_id: str = "",
        project_name: str = "",
        include_global: bool = False,
    ) -> list[dict]:
        return self._list_for_scope(
            session_id=session_id,
            project_name=project_name,
            include_global=include_global,
        )

    def list_active_for_scope(
        self,
        session_id: str = "",
        project_name: str = "",
        include_global: bool = False,
    ) -> list[dict]:
        active_plan_ids = self._get_active_plan_ids_for_scope(session_id, project_name)
        tasks = self._list_for_scope(
            session_id=session_id,
            project_name=project_name,
            include_global=include_global,
            include_stale=bool(active_plan_ids),
        )
        if active_plan_ids:
            return [
                t for t in tasks
                if t.get("plan_id") in active_plan_ids
                and t.get("task_kind") in ("plan_task", "confirmation", "evidence_gap")
                and t.get("status") not in ("deleted", "archived", "superseded")
            ]
        return [
            t for t in tasks
            if not t.get("plan_id")
            and t.get("status") not in ("deleted", "archived", "superseded")
        ]

    def find_duplicate_task(
        self,
        session_id: str,
        plan_id: str,
        subject: str,
        analysis_spec_id: str = "",
    ) -> dict | None:
        normalized_subject = (subject or "").strip()
        for task in self.list_for_scope(session_id=session_id):
            if task.get("plan_id") != plan_id:
                continue
            if analysis_spec_id and task.get("analysis_spec_id") != analysis_spec_id:
                continue
            if task.get("status") in ("deleted", "archived", "superseded"):
                continue
            if (task.get("subject") or "").strip() == normalized_subject:
                return task
        return None

    def _is_stage3c0b_scoped_task(self, task: dict) -> bool:
        return bool(task.get("analysis_plan_id") or task.get("step_id"))

    def _task_delivery_projection(self, task):
        """Rebuild the same native product projection used by publication."""
        from data_agent.agent.context import get_current_context
        from data_agent.agent.publication.runtime import collect_products
        from data_agent.agent.publication.deliveries import project_deliveries, OPEN_KINDS
        from data_agent.agent.publication.requirements import _source
        from data_agent.session.history import load_canonical_history
        ctx=get_current_context()
        if ctx is None or ctx.session_id!=task.get("session_id"): return {}
        state=ctx.analysis_state;plan=state.analysis_plan or {}
        if task.get("analysis_plan_id")!=plan.get("id") or task.get("plan_sha256")!=plan.get("plan_sha256"): return {}
        step=next((s for s in plan.get("method_plan",[]) if s["step_id"]==task.get("step_id")),None)
        if step is None or sorted(task.get("required_delivery_ids",[]))!=sorted(d["id"] for d in step["required_deliveries"] if d["kind"] not in OPEN_KINDS) or sorted(task.get("requirement_ids",[]))!=step["requirement_ids"]: return {}
        history=load_canonical_history(ctx.session_id)
        active=[r for r in state.answer_requirements if r.get("lifecycle_status")=="active"]
        for req in active:
            if req["id"] not in task.get("requirement_ids",[]): continue
            try:
                original=_source(history,req["source_message_ref"])
                if original[req["source_start"]:req["source_end"]]!=req["original_text"]: return {}
                if any(not ctx.workspace._receipt_identity_matches(n,i) for n,i in req.get("source_data_identities",{}).items()): return {}
            except (ValueError,OSError,KeyError,TypeError): return {}
        claims,artifacts,gaps,_,effects=collect_products(state,ctx.session_id)
        return project_deliveries(active,claims,artifacts,effects=effects,product_gaps=gaps)[1]

    def reconcile_deliveries(self, session_id):
        """Receipt arrival advances factual steps only after every delivery closes."""
        with self._authority_lock:
            completed=[]
            for task in self.list_active_for_scope(session_id=session_id):
                if task.get("status") not in {"pending","in_progress"} or not self._is_stage3c0b_scoped_task(task): continue
                required=task.get("required_delivery_ids",[])
                projection=self._task_delivery_projection(task)
                if required and all(d in projection and projection[d]["gap"] is None for d in required):
                    if self.update(task["id"],status="completed",completed_by="verified_deliveries"):
                        completed.append(task["id"])
            return completed

    def complete_matching_tasks_from_evidence(self, session_id, evidence, analysis_spec_id=""):
        # EvidenceRecord claims, confidence and labels are research annotations.
        # They cannot sign off a DAG step, including a legacy unscoped plan.
        return self.reconcile_deliveries(session_id)

    def list_history_for_scope(
        self,
        session_id: str = "",
        project_name: str = "",
        include_global: bool = False,
    ) -> list[dict]:
        active_plan_ids = self._get_active_plan_ids_for_scope(session_id, project_name)
        return [
            t for t in self._list_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
                include_stale=True,
            )
            if t.get("status") in ("completed", "archived", "superseded")
            and (not active_plan_ids or t.get("plan_id") not in active_plan_ids)
        ]

    def list_ready(
        self,
        session_id: str = "",
        project_name: str = "",
        include_global: bool = False,
    ) -> list[dict]:
        return [
            t for t in self.list_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
            if self.is_ready(t)
        ]

    def list_by_status(self, status: str) -> list[dict]:
        return [t for t in self.list_all() if t.get("status") == status]

    def list_all_raw(self) -> list[dict]:
        """Return all tasks including stale ones (for admin/management scenarios)."""
        return self.list_all(include_stale=True)

    def format_list(
        self,
        session_id: str = "",
        project_name: str = "",
        include_global: bool = False,
    ) -> str:
        """纯文本格式化任务列表。"""
        tasks = (
            self.list_active_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
            if (session_id or project_name)
            else self.list_all()
        )
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
        self._active_plans_path().unlink(missing_ok=True)
        self._next_id_val = 0


# 全局实例
task_manager = TaskManager()
