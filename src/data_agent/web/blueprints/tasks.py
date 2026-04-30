"""Task management API endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

tasks_bp = Blueprint("tasks", __name__)


def _get_manager():
    from data_agent.session.task_manager import task_manager
    return task_manager


@tasks_bp.get("/tasks")
def list_tasks():
    mgr = _get_manager()
    return jsonify(mgr.list_all())


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
