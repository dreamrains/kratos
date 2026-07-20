from __future__ import annotations

import uuid
from typing import Any

from data_agent.agent.analysis_plan_contracts import (
    ANALYSIS_PLAN_CONTRACT_VERSION,
    analysis_plan_id_from_mapping,
    validate_analysis_plan_contract,
)
from data_agent.session.task_manager import TaskManager


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _step_subject(step: dict[str, Any], index: int) -> str:
    return (
        _text(step.get("task"))
        or _text(step.get("subject"))
        or _text(step.get("title"))
        or _text(step.get("goal"))
        or f"Analysis step {index}"
    )


def _matches_existing_projection(task: dict[str, Any], *, analysis_plan_id: str, workflow_id: str) -> bool:
    if analysis_plan_id and analysis_plan_id_from_mapping(task) == analysis_plan_id:
        return True
    if workflow_id and task.get("workflow_id") == workflow_id:
        return True
    return False


def _find_step_duplicate(
    manager: TaskManager,
    *,
    session_id: str,
    project_name: str,
    task_plan_id: str,
    analysis_plan_id: str,
    step_id: str,
) -> dict[str, Any] | None:
    for task in manager.list_for_scope(session_id=session_id, project_name=project_name):
        if task.get("plan_id") != task_plan_id:
            continue
        if task.get("analysis_plan_id") != analysis_plan_id:
            continue
        if task.get("step_id") != step_id:
            continue
        if task.get("status") in ("deleted", "archived", "superseded"):
            continue
        return task
    return None


def _analysis_requirement_ids_for_step(plan: dict[str, Any], step_id: str) -> list[str]:
    grouped = plan.get("analysis_requirements")
    if not isinstance(grouped, dict):
        return []
    group = grouped.get(step_id)
    if not isinstance(group, list):
        return []
    return [
        _text(requirement.get("id"))
        for requirement in group
        if isinstance(requirement, dict) and _text(requirement.get("id"))
    ]


def project_plan_to_workflow_tasks(
    manager: TaskManager,
    plan: dict[str, Any],
    *,
    session_id: str,
    project_name: str = "",
    source: str = "analysis_plan",
) -> dict[str, Any]:
    if plan.get("contract_version") != ANALYSIS_PLAN_CONTRACT_VERSION:
        return {
            "created": 0,
            "reused": 0,
            "task_ids": [],
            "error": "unsupported_contract_version",
        }
    validation = validate_analysis_plan_contract(plan)
    if not validation.ok:
        return {
            "created": 0,
            "reused": 0,
            "task_ids": [],
            "error": validation.error_type,
        }

    method_plan = plan.get("method_plan")
    if not isinstance(method_plan, list) or not method_plan:
        return {
            "created": 0,
            "reused": 0,
            "task_ids": [],
            "error": "missing_method_plan",
        }
    if any(not isinstance(step, dict) for step in method_plan):
        return {
            "created": 0,
            "reused": 0,
            "task_ids": [],
            "error": "invalid_method_plan_step",
        }

    plan_id = _text(plan.get("id")) or f"plan_{uuid.uuid4().hex[:10]}"
    workflow_id = _text(plan.get("workflow_id")) or f"wf_{uuid.uuid4().hex[:8]}"

    active_tasks = manager.list_active_for_scope(
        session_id=session_id,
        project_name=project_name,
    )
    matching_active = [
        task for task in active_tasks
        if task.get("plan_id")
        and task.get("task_kind") == "plan_task"
        if _matches_existing_projection(
            task,
            analysis_plan_id=plan_id,
            workflow_id=_text(plan.get("workflow_id")),
        )
    ]
    if matching_active:
        existing_workflow_id = _text(matching_active[0].get("workflow_id"))
        if existing_workflow_id:
            workflow_id = existing_workflow_id
        plan_record = {
            "id": matching_active[0].get("plan_id", ""),
            "version": matching_active[0].get("plan_version", 1),
        }
    else:
        plan_record = manager.create_plan(
            session_id=session_id,
            project_name=project_name,
            goal=_text(plan.get("goal")),
            source=source,
            analysis_spec_id=plan_id,
            workflow_id=workflow_id,
        )

    created: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    by_step_id: dict[str, dict[str, Any]] = {}

    for index, step in enumerate(method_plan, 1):
        if not isinstance(step, dict):
            continue
        explicit_step_id = _text(step.get("step_id"))
        step_id = explicit_step_id or f"step_{index}"
        if explicit_step_id:
            duplicate = _find_step_duplicate(
                manager,
                session_id=session_id,
                project_name=project_name,
                task_plan_id=plan_record["id"],
                analysis_plan_id=plan_id,
                step_id=step_id,
            )
        else:
            duplicate = manager.find_duplicate_task(
                session_id=session_id,
                plan_id=plan_record["id"],
                subject=_step_subject(step, index),
                analysis_spec_id=plan_id,
            )
        if duplicate:
            updated = manager.update(
                duplicate["id"],
                description=_text(step.get("expected_output")),
                workflow_id=workflow_id,
                project_name=project_name,
                stage="execute",
                node_type=_text(step.get("node_type")) or "analysis",
                analysis_spec_id=plan_id,
                analysis_plan_id=plan_id,
                step_id=step_id,
                dataset_inputs=list(step.get("dataset_inputs") or []),
                dataset_contract_ids=list(step.get("dataset_contract_ids") or []),
                combination_mode=_text(step.get("combination_mode")),
                required_evidence_step_ids=list(step.get("required_evidence_step_ids") or []),
                required_data=list(step.get("dataset_inputs") or []),
                expected_output=_text(step.get("expected_output")),
                required_capability=_text(step.get("required_capability")),
                evidence_requirements=list(step.get("evidence_requirements") or []),
                required_claim_keys=list(step.get("required_claim_keys") or []),
                analysis_requirement_ids=_analysis_requirement_ids_for_step(validation.plan, step_id),
                confirmation_policy=step.get("confirmation_policy") or {},
            )
            duplicate = updated or duplicate
            reused.append(duplicate)
            by_step_id[step_id] = duplicate
            continue
        task = manager.create(
            subject=_step_subject(step, index)[:120],
            description=_text(step.get("expected_output")),
            session_id=session_id,
            workflow_id=workflow_id,
            project_name=project_name,
            stage="execute",
            node_type=_text(step.get("node_type")) or "analysis",
            analysis_spec_id=plan_id,
            analysis_plan_id=plan_id,
            step_id=step_id,
            dataset_inputs=list(step.get("dataset_inputs") or []),
            dataset_contract_ids=list(step.get("dataset_contract_ids") or []),
            combination_mode=_text(step.get("combination_mode")),
            required_evidence_step_ids=list(step.get("required_evidence_step_ids") or []),
            required_data=list(step.get("dataset_inputs") or []),
            expected_output=_text(step.get("expected_output")),
            required_capability=_text(step.get("required_capability")),
            evidence_requirements=list(step.get("evidence_requirements") or []),
            required_claim_keys=list(step.get("required_claim_keys") or []),
            analysis_requirement_ids=_analysis_requirement_ids_for_step(validation.plan, step_id),
            confirmation_policy=step.get("confirmation_policy") or {},
            plan_id=plan_record["id"],
            plan_version=plan_record.get("version", 1),
            plan_status="active",
            task_kind="plan_task",
            source=source,
        )
        created.append(task)
        by_step_id[step_id] = task

    for task in created + reused:
        required_steps = list(task.get("required_evidence_step_ids") or [])
        dependency_ids = [
            by_step_id[step_id]["id"]
            for step_id in required_steps
            if step_id in by_step_id
        ]
        if dependency_ids:
            manager.update(task["id"], addBlockedBy=dependency_ids)
            for dependency_id in dependency_ids:
                manager.update(dependency_id, addBlocks=[task["id"]])

    return {
        "workflow_id": workflow_id,
        "plan_id": plan_record["id"],
        "analysis_plan_id": plan_id,
        "created": len(created),
        "reused": len(reused),
        "task_ids": [task["id"] for task in created + reused],
    }
