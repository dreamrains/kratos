"""Server-owned coordination between canonical runs and legacy task views."""

from __future__ import annotations

import hashlib
from typing import Any, Sequence

from data_agent.session.analysis_run_models import AnalysisRun, StepSpec, StepStatus
from data_agent.session.analysis_run_store import AnalysisRunStore


class AnalysisRunCoordinator:
    def __init__(self, store: AnalysisRunStore):
        self.store = store

    def materialize_plan(
        self,
        *,
        session_id: str,
        project_name: str,
        plan_id: str,
        tasks: Sequence[dict[str, Any]],
    ) -> AnalysisRun:
        ordered = self._topological_tasks(tasks)
        task_identity = ",".join(str(int(task.get("id") or 0)) for task in ordered)
        projection_digest = hashlib.sha256(task_identity.encode("utf-8")).hexdigest()[:16]
        active = self.store.get_active_run(session_id)
        if active is not None:
            active_plan = str(active.steps[0].payload.get("plan_id") or "")
            active_task_ids = {
                int(step.payload.get("legacy_task_id") or 0) for step in active.steps
            }
            projected_task_ids = {int(task.get("id") or 0) for task in ordered}
            if active_plan == plan_id and active_task_ids == projected_task_ids:
                return active
            self.store.terminate_active_run(
                session_id=session_id,
                idempotency_key=(
                    f"supersede:{active.run_id}:{plan_id}:{projection_digest}"
                ),
            )
        specs = [
            StepSpec(
                subject=str(task.get("subject") or "Analysis step"),
                capability=str(task.get("required_capability") or ""),
                payload={
                    "legacy_task_id": int(task.get("id") or 0),
                    "plan_id": plan_id,
                    "project_name": project_name,
                    "analysis_plan_id": str(task.get("analysis_plan_id") or ""),
                    "external_step_id": str(task.get("step_id") or ""),
                    "dataset_inputs": list(task.get("dataset_inputs") or []),
                    "dataset_contract_ids": list(
                        task.get("dataset_contract_ids") or []
                    ),
                    "combination_mode": str(task.get("combination_mode") or ""),
                },
                idempotency_key=f"plan:{plan_id}:task:{int(task.get('id') or 0)}",
            )
            for task in ordered
        ]
        return self.store.create_run(
            session_id=session_id,
            idempotency_key=f"plan:{plan_id}:{projection_digest}",
            steps=specs,
        )

    @staticmethod
    def _topological_tasks(tasks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return a stable dependency-first order for the legacy projection."""

        remaining = {
            int(task.get("id") or 0): task
            for task in tasks
            if int(task.get("id") or 0)
        }
        ordered: list[dict[str, Any]] = []
        emitted: set[int] = set()
        while remaining:
            ready = [
                task
                for task_id, task in remaining.items()
                if {
                    int(blocker)
                    for blocker in task.get("blockedBy") or []
                    if int(blocker) in remaining or int(blocker) in emitted
                }.issubset(emitted)
            ]
            if not ready:
                ready = [remaining[min(remaining)]]
            for task in sorted(ready, key=lambda item: int(item.get("id") or 0)):
                task_id = int(task.get("id") or 0)
                ordered.append(task)
                emitted.add(task_id)
                remaining.pop(task_id, None)
        return ordered

    def current_scope(
        self,
        *,
        session_id: str,
        project_name: str,
    ) -> dict[str, Any] | None:
        run = self.store.get_active_run(session_id)
        if run is None:
            latest = self.store.get_latest_run(session_id)
            if latest is None or latest.status.value not in {
                "completed",
                "failed",
                "terminated",
            }:
                return None
            project = (
                str(latest.steps[0].payload.get("project_name") or "")
                if latest.steps
                else ""
            )
            if project != project_name:
                return None
            return {
                "run_id": latest.run_id,
                "plan_id": (
                    str(latest.steps[0].payload.get("plan_id") or "")
                    if latest.steps
                    else ""
                ),
                "task_id": 0,
                "step_id": "",
                "phase": "terminal",
                "combination_mode": "terminal",
                "allowed_datasets": [],
                "dataset_contract_ids": [],
            }
        if run.current_step is None:
            run = self.store.recover_current_step(
                run_id=run.run_id,
                session_id=session_id,
                idempotency_key=f"recover:{run.run_id}:{run.version}",
            )
        step = run.current_step
        if step is None:
            return None
        payload = step.payload
        if str(payload.get("project_name") or "") != project_name:
            return None
        mode = str(payload.get("combination_mode") or "").casefold()
        return {
            "run_id": run.run_id,
            "plan_id": str(payload.get("plan_id") or ""),
            "task_id": int(payload.get("legacy_task_id") or 0),
            "step_id": str(payload.get("external_step_id") or ""),
            "phase": "synthesis" if mode == "synthesis" else "execution",
            "combination_mode": mode,
            "allowed_datasets": list(payload.get("dataset_inputs") or []),
            "dataset_contract_ids": list(payload.get("dataset_contract_ids") or []),
        }

    def advance_completed_tasks(
        self,
        *,
        session_id: str,
        completed_task_ids: Sequence[int],
        idempotency_key: str,
    ) -> AnalysisRun | None:
        run = self.store.get_active_run(session_id)
        if run is None:
            return None
        completed = {int(task_id) for task_id in completed_task_ids}
        transition = 0
        while run.current_step is not None:
            legacy_task_id = int(run.current_step.payload.get("legacy_task_id") or 0)
            if legacy_task_id not in completed:
                break
            run = self.store.complete_and_activate_next(
                run_id=run.run_id,
                step_id=run.current_step.step_id,
                session_id=session_id,
                idempotency_key=f"{idempotency_key}:{transition}:{legacy_task_id}",
            )
            transition += 1
        return run

    def commit_computation_projection(
        self,
        **transaction,
    ) -> dict:
        """Commit one server-owned computation/evidence workflow transaction."""

        return self.store.commit_computation_projection(**transaction)

    def reconcile_computation_projection(
        self,
        **transaction,
    ) -> dict:
        """Replay a previously unbound computation into its recovered step."""

        return self.store.reconcile_computation_projection(**transaction)

    def advance_terminal_task(
        self,
        *,
        session_id: str,
        legacy_task_id: int,
        final_status: str,
        idempotency_key: str,
    ) -> AnalysisRun | None:
        run = self.store.get_active_run(session_id)
        if run is None or run.current_step is None:
            return run
        current_task_id = int(
            run.current_step.payload.get("legacy_task_id") or 0
        )
        if current_task_id != int(legacy_task_id):
            return run
        return self.store.finish_and_activate_next(
            run_id=run.run_id,
            step_id=run.current_step.step_id,
            session_id=session_id,
            final_status=final_status,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def legacy_projection(run: AnalysisRun) -> dict[int, str]:
        projection: dict[int, str] = {}
        for step in run.steps:
            legacy_task_id = int(step.payload.get("legacy_task_id") or 0)
            if not legacy_task_id:
                continue
            projection[legacy_task_id] = {
                StepStatus.PENDING: "pending",
                StepStatus.IN_PROGRESS: "in_progress",
                StepStatus.COMPLETED: "completed",
                StepStatus.FAILED: "failed",
                StepStatus.SKIPPED: "archived",
            }[step.status]
        return projection
