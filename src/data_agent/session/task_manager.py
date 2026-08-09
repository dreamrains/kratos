"""任务管理系统：文件级持久化，跨会话可见。

参考 Claude Code 的 Task 系统设计：
Task 是持久化工作项，LLM 完全控制生命周期，系统只做存取和展示。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from data_agent.config import get_config


WORKFLOW_FIELDS = {
    "workflow_id": "",
    "project_name": "",
    "stage": "",
    "node_type": "",
    "analysis_spec_id": "",
    "analysis_plan_id": "",
    "step_id": "",
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
    "satisfied_claim_keys": [],
    "analysis_requirement_ids": [],
    "satisfied_analysis_requirement_ids": [],
    "confirmation_policy": {},
}


def normalize_required_claim_keys(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("required_claim_keys must be a list of non-empty strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("required_claim_keys must be a list of non-empty strings")
        claim_key = " ".join(item.split())
        if not claim_key:
            raise ValueError("required_claim_keys must be a list of non-empty strings")
        if claim_key not in result:
            result.append(claim_key)
    return result


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
        if "required_claim_keys" in task:
            try:
                task["required_claim_keys"] = normalize_required_claim_keys(
                    task["required_claim_keys"]
                )
            except ValueError:
                # Malformed-present data stays on the canonical path and can
                # never opt into persisted legacy matching semantics.
                task["required_claim_keys"] = []
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
        required_claim_keys = normalize_required_claim_keys(
            workflow_fields.get("required_claim_keys", [])
        )
        task = {
            "id": self._alloc_id(),
            "subject": subject,
            "description": description,
            "status": "pending",
            "blockedBy": [],
            "blocks": [],
            "owner": "",
            "session_id": session_id,
            "required_claim_keys": required_claim_keys,
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
        if "required_claim_keys" in workflow_fields:
            workflow_fields["required_claim_keys"] = normalize_required_claim_keys(
                workflow_fields["required_claim_keys"]
            )
        try:
            task = self._load(tid)
        except ValueError:
            return None

        if "required_claim_keys" in workflow_fields:
            task["required_claim_keys"] = workflow_fields["required_claim_keys"]

        if status is not None:
            allowed = ("pending", "blocked", "in_progress", "completed", "failed", "superseded", "archived", "deleted")
            if status not in allowed:
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

    def activate_next_ready_plan_task(
        self,
        *,
        session_id: str,
        project_name: str = "",
        plan_id: str = "",
    ) -> int | None:
        """Activate exactly one ready canonical task when none is running.

        Canonical workflow bookkeeping is server-owned.  The model should
        choose and execute analytical tools, not maintain the transient
        ``pending -> in_progress`` invariant required by workspace scoping.
        Legacy/user-authored tasks remain untouched.
        """

        tasks = [
            task
            for task in self.list_active_for_scope(
                session_id=session_id,
                project_name=project_name,
            )
            if task.get("task_kind") == "plan_task"
            and (not plan_id or task.get("plan_id") == plan_id)
            and self._is_stage3c0b_scoped_task(task)
        ]
        current = [task for task in tasks if task.get("status") == "in_progress"]
        if current:
            return int(sorted(current, key=lambda task: int(task.get("id") or 0))[0]["id"])

        ready = sorted(
            (task for task in tasks if self.is_ready(task)),
            key=lambda task: int(task.get("id") or 0),
        )
        if not ready:
            return None
        activated = self.update(ready[0]["id"], status="in_progress")
        return int(activated["id"]) if activated else None

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
        self._active_plans_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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

    def create_plan(
        self,
        session_id: str = "",
        project_name: str = "",
        goal: str = "",
        source: str = "",
        analysis_spec_id: str = "",
        workflow_id: str = "",
    ) -> dict:
        active_plan_id = self.get_active_plan_id(session_id, project_name)
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

        if session_id and project_name:
            scoped = [
                t for t in tasks
                if t.get("session_id") == session_id
                and t.get("project_name") == project_name
            ]
        elif session_id:
            scoped = [t for t in tasks if t.get("session_id") == session_id]
        else:
            scoped = [t for t in tasks if t.get("project_name") == project_name]
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

    def _evidence_text(self, evidence: dict) -> str:
        parts = [
            evidence.get("claim", ""),
            evidence.get("result_summary", ""),
            evidence.get("method", ""),
            " ".join(str(x) for x in evidence.get("tool_calls", []) or []),
        ]
        metrics = evidence.get("metrics") or {}
        if isinstance(metrics, dict):
            parts.extend(str(k) for k in metrics.keys())
        return " ".join(str(p) for p in parts if p).lower()

    def _task_match_terms(self, task: dict) -> list[str]:
        terms = []
        for key in ("subject", "expected_output", "required_capability"):
            value = task.get(key)
            if value:
                terms.append(str(value))
        for item in task.get("evidence_requirements") or []:
            terms.append(str(item))
        return [t.lower() for t in terms if t]

    def _evidence_has_substantive_work(self, evidence: dict) -> bool:
        return bool(
            evidence.get("result_summary")
            or evidence.get("metrics")
            or evidence.get("tool_calls")
        )

    def _evidence_id(self, evidence: dict) -> str:
        evidence_id = str(evidence.get("id") or "")
        if evidence_id:
            return evidence_id
        try:
            from data_agent.agent.evidence_contracts import evidence_id_for

            if evidence.get("plan_id") and evidence.get("step_id") and evidence.get("claim_key"):
                return evidence_id_for(evidence.get("plan_id"), evidence.get("step_id"), evidence.get("claim_key"))
        except Exception:
            pass
        return ""

    def _is_stage3c0b_scoped_task(self, task: dict) -> bool:
        return bool(task.get("analysis_plan_id") or task.get("step_id"))

    def _stage3c0b_evidence_requirement(self, evidence: dict) -> str:
        return str(evidence.get("evidence_requirement") or "")

    def _uses_legacy_claim_key_compat(self, task: dict) -> bool:
        return "required_claim_keys" not in task

    def _stage3c0b_required_claim_keys(self, task: dict) -> list[str]:
        try:
            return normalize_required_claim_keys(task.get("required_claim_keys"))
        except ValueError:
            return []

    def _stage3c0b_analysis_requirement_ids(self, task: dict) -> list[str]:
        return [str(item) for item in task.get("analysis_requirement_ids") or [] if str(item)]

    def _stage3c0b_evidence_requirement_ids(self, evidence: dict) -> list[str]:
        value = evidence.get("requirement_ids")
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item)]

    def _stage3c0b_task_matches_evidence(self, task: dict, evidence: dict) -> bool:
        task_plan_id = str(task.get("analysis_plan_id") or "")
        if task_plan_id and str(evidence.get("plan_id") or "") != task_plan_id:
            return False

        task_step_id = str(task.get("step_id") or "")
        if task_step_id and str(evidence.get("step_id") or "") != task_step_id:
            return False

        task_contract_ids = [str(item) for item in task.get("dataset_contract_ids") or [] if str(item)]
        if task_contract_ids:
            evidence_contract_ids = []
            if evidence.get("dataset_contract_id"):
                evidence_contract_ids.append(str(evidence.get("dataset_contract_id")))
            evidence_contract_ids.extend(
                str(item) for item in evidence.get("dataset_contract_ids") or [] if str(item)
            )
            if not set(task_contract_ids).intersection(evidence_contract_ids):
                return False

        required_claim_keys = self._stage3c0b_required_claim_keys(task)
        if not self._uses_legacy_claim_key_compat(task):
            claim_key = str(evidence.get("claim_key") or "")
            if not required_claim_keys or claim_key not in required_claim_keys:
                return False
            analysis_requirement_ids = self._stage3c0b_analysis_requirement_ids(task)
            if analysis_requirement_ids:
                evidence_requirement_ids = self._stage3c0b_evidence_requirement_ids(evidence)
                if not set(analysis_requirement_ids).intersection(evidence_requirement_ids):
                    return False
        else:
            # Read-only compatibility for tasks persisted before required_claim_keys.
            task_requirements = [str(item) for item in task.get("evidence_requirements") or [] if str(item)]
            evidence_requirement = self._stage3c0b_evidence_requirement(evidence)
            if not task_requirements or not evidence_requirement or evidence_requirement not in task_requirements:
                return False

        return True

    def _complete_stage3c0b_task_from_evidence(self, task: dict, evidence: dict) -> int | None:
        if not self._stage3c0b_task_matches_evidence(task, evidence):
            return None

        evidence_id = self._evidence_id(evidence)
        evidence_ids = list(task.get("evidence_ids") or [])
        if evidence_id and evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)

        required_claim_keys = self._stage3c0b_required_claim_keys(task)
        if not self._uses_legacy_claim_key_compat(task):
            claim_key = str(evidence.get("claim_key") or "")
            satisfied_claim_keys = list(task.get("satisfied_claim_keys") or [])
            if claim_key and claim_key not in satisfied_claim_keys:
                satisfied_claim_keys.append(claim_key)
            analysis_requirement_ids = self._stage3c0b_analysis_requirement_ids(task)
            evidence_requirement_ids = self._stage3c0b_evidence_requirement_ids(evidence)
            satisfied_analysis_requirement_ids = list(
                task.get("satisfied_analysis_requirement_ids") or []
            )
            for requirement_id in analysis_requirement_ids:
                if (
                    requirement_id in evidence_requirement_ids
                    and requirement_id not in satisfied_analysis_requirement_ids
                ):
                    satisfied_analysis_requirement_ids.append(requirement_id)
            all_satisfied = (
                bool(required_claim_keys)
                and all(item in satisfied_claim_keys for item in required_claim_keys)
                and all(
                    item in satisfied_analysis_requirement_ids
                    for item in analysis_requirement_ids
                )
            )
            satisfaction_fields = {
                "satisfied_claim_keys": satisfied_claim_keys,
                "satisfied_analysis_requirement_ids": satisfied_analysis_requirement_ids,
            }
        else:
            evidence_requirement = self._stage3c0b_evidence_requirement(evidence)
            satisfied = list(task.get("satisfied_evidence_requirements") or [])
            if evidence_requirement and evidence_requirement not in satisfied:
                satisfied.append(evidence_requirement)
            required = [str(item) for item in task.get("evidence_requirements") or [] if str(item)]
            all_satisfied = bool(required) and all(item in satisfied for item in required)
            satisfaction_fields = {"satisfied_evidence_requirements": satisfied}
        was_completed = task.get("status") == "completed"

        update_fields = {
            "evidence_ids": evidence_ids,
            "result_summary": evidence.get("result_summary", "") or evidence.get("claim", ""),
            "confidence": evidence.get("confidence", ""),
            **satisfaction_fields,
        }
        if all_satisfied:
            self.update(
                task["id"],
                status="completed",
                completed_by="evidence",
                **update_fields,
            )
            if not was_completed:
                return task["id"]
        else:
            self.update(task["id"], **update_fields)
        return None

    def _complete_analysis_spec_plan_from_evidence(
        self,
        session_id: str,
        evidence: dict,
        analysis_spec_id: str = "",
    ) -> list[int]:
        if not self._evidence_has_substantive_work(evidence):
            return []

        active_tasks = self.list_active_for_scope(session_id=session_id)
        if any(t.get("analysis_plan_id") or t.get("step_id") for t in active_tasks):
            return []
        if any(t.get("source") == "llm_plan" for t in active_tasks):
            return []

        evidence_id = self._evidence_id(evidence)
        completed: list[int] = []
        for task in active_tasks:
            if task.get("status") not in ("pending", "in_progress"):
                continue
            if analysis_spec_id and task.get("analysis_spec_id") != analysis_spec_id:
                continue
            if task.get("task_kind") == "confirmation" or task.get("node_type") == "confirmation":
                self.update(
                    task["id"],
                    status="superseded",
                    completed_by="evidence",
                    result_summary=evidence.get("result_summary", "") or evidence.get("claim", ""),
                )
                continue
            if task.get("source") != "analysis_spec":
                continue

            evidence_ids = list(task.get("evidence_ids") or [])
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
            self.update(
                task["id"],
                status="completed",
                evidence_ids=evidence_ids,
                result_summary=evidence.get("result_summary", "") or evidence.get("claim", ""),
                confidence=evidence.get("confidence", ""),
                completed_by="evidence",
            )
            completed.append(task["id"])
        return completed

    def complete_matching_tasks_from_evidence(
        self,
        session_id: str,
        evidence: dict,
        analysis_spec_id: str = "",
    ) -> list[int]:
        active_tasks = self.list_active_for_scope(session_id=session_id)
        has_scoped_stage3c0b_tasks = any(self._is_stage3c0b_scoped_task(task) for task in active_tasks)
        evidence_id = self._evidence_id(evidence)
        completed: list[int] = []
        if has_scoped_stage3c0b_tasks:
            for task in active_tasks:
                if task.get("status") not in ("pending", "in_progress"):
                    continue
                if analysis_spec_id and task.get("analysis_spec_id") != analysis_spec_id:
                    continue
                if not self._is_stage3c0b_scoped_task(task):
                    continue
                completed_task_id = self._complete_stage3c0b_task_from_evidence(task, evidence)
                if completed_task_id is not None:
                    completed.append(completed_task_id)
            activated_scopes: set[tuple[str, str]] = set()
            for task in active_tasks:
                if task.get("id") not in completed:
                    continue
                scope_key = (
                    str(task.get("project_name") or ""),
                    str(task.get("plan_id") or ""),
                )
                if scope_key in activated_scopes:
                    continue
                activated_scopes.add(scope_key)
                self.activate_next_ready_plan_task(
                    session_id=session_id,
                    project_name=scope_key[0],
                    plan_id=scope_key[1],
                )
            return completed

        evidence_text = self._evidence_text(evidence)
        for task in active_tasks:
            if task.get("status") not in ("pending", "in_progress"):
                continue
            if analysis_spec_id and task.get("analysis_spec_id") != analysis_spec_id:
                continue
            terms = self._task_match_terms(task)
            if not any(term and term in evidence_text for term in terms):
                continue
            evidence_ids = list(task.get("evidence_ids") or [])
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
            self.update(
                task["id"],
                status="completed",
                evidence_ids=evidence_ids,
                result_summary=evidence.get("result_summary", "") or evidence.get("claim", ""),
                confidence=evidence.get("confidence", ""),
                completed_by="evidence",
            )
            completed.append(task["id"])
        if completed:
            return completed
        return self._complete_analysis_spec_plan_from_evidence(
            session_id=session_id,
            evidence=evidence,
            analysis_spec_id=analysis_spec_id,
        )

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
