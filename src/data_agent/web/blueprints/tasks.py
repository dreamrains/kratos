"""Task management API endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

tasks_bp = Blueprint("tasks", __name__)


def _get_manager():
    from data_agent.session.task_manager import task_manager
    return task_manager


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


@tasks_bp.get("/tasks")
def list_tasks():
    mgr = _get_manager()
    session_id = request.args.get("session_id", "")
    project_name = request.args.get("project_name", "")
    include_global = _truthy(request.args.get("include_global"))
    ready_only = _truthy(request.args.get("ready_only"))
    active_only = _truthy(request.args.get("active_only"))
    scope = (request.args.get("scope") or "active").lower()

    if ready_only:
        base_tasks = mgr.list_ready(
            session_id=session_id,
            project_name=project_name,
            include_global=include_global,
        )
    elif session_id or project_name:
        if scope == "all":
            base_tasks = mgr.list_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
        elif scope == "history":
            base_tasks = mgr.list_history_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
        else:
            base_tasks = mgr.list_active_for_scope(
                session_id=session_id,
                project_name=project_name,
                include_global=include_global,
            )
    else:
        base_tasks = mgr.list_all()

    tasks = base_tasks

    if active_only:
        tasks = [t for t in tasks if t.get("status") in ("pending", "in_progress")]

    return jsonify(tasks)


@tasks_bp.get("/tasks/<int:task_id>")
def get_task(task_id: int):
    mgr = _get_manager()
    task = mgr.get(task_id)
    if not task:
        return jsonify({"error": f"Task {task_id} not found"}), 404
    return jsonify(task)


@tasks_bp.post("/tasks")
def create_task():
    data = request.get_json(force=True)
    subject = data.get("subject", "").strip()
    if not subject:
        return jsonify({"error": "subject is required"}), 400
    mgr = _get_manager()
    task = mgr.create(
        subject=subject,
        description=data.get("description", ""),
        session_id=data.get("session_id", ""),
        workflow_id=data.get("workflow_id", ""),
        project_name=data.get("project_name", ""),
        stage=data.get("stage", ""),
        node_type=data.get("node_type", ""),
        analysis_spec_id=data.get("analysis_spec_id", ""),
        analysis_plan_id=data.get("analysis_plan_id", ""),
        step_id=data.get("step_id", ""),
        dataset_inputs=data.get("dataset_inputs", []),
        dataset_contract_ids=data.get("dataset_contract_ids", []),
        combination_mode=data.get("combination_mode", ""),
        required_evidence_step_ids=data.get("required_evidence_step_ids", []),
        required_data=data.get("required_data", []),
        expected_output=data.get("expected_output", ""),
        evidence_ids=data.get("evidence_ids", []),
        confirmation_ids=data.get("confirmation_ids", []),
        required_capability=data.get("required_capability", ""),
        evidence_requirements=data.get("evidence_requirements", []),
        confirmation_policy=data.get("confirmation_policy", {}),
    )
    return jsonify(task), 201


@tasks_bp.patch("/tasks/<int:task_id>")
def update_task(task_id: int):
    data = request.get_json(force=True)
    mgr = _get_manager()
    task = mgr.update(
        task_id,
        status=data.get("status"),
        owner=data.get("owner"),
        addBlocks=data.get("addBlocks"),
        addBlockedBy=data.get("addBlockedBy"),
        stage=data.get("stage"),
        node_type=data.get("node_type"),
        analysis_plan_id=data.get("analysis_plan_id"),
        step_id=data.get("step_id"),
        dataset_inputs=data.get("dataset_inputs"),
        dataset_contract_ids=data.get("dataset_contract_ids"),
        combination_mode=data.get("combination_mode"),
        required_evidence_step_ids=data.get("required_evidence_step_ids"),
        result_summary=data.get("result_summary"),
        evidence_ids=data.get("evidence_ids"),
        confirmation_ids=data.get("confirmation_ids"),
        limitations=data.get("limitations"),
        confidence=data.get("confidence"),
        expected_output=data.get("expected_output"),
        required_capability=data.get("required_capability"),
        evidence_requirements=data.get("evidence_requirements"),
        confirmation_policy=data.get("confirmation_policy"),
    )
    if not task:
        return jsonify({"error": f"Task {task_id} not found"}), 404
    return jsonify(task)


@tasks_bp.delete("/tasks/<int:task_id>")
def delete_task(task_id: int):
    mgr = _get_manager()
    task = mgr.update(task_id, status="deleted")
    if not task:
        return jsonify({"error": f"Task {task_id} not found"}), 404
    return jsonify({"deleted": True})
