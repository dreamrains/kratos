"""Project management endpoints."""

from flask import Blueprint, jsonify, request

from data_agent.project_manager import get_project_manager

objects_bp = Blueprint("projects", __name__)


@objects_bp.get("/projects")
def list_projects():
    mgr = get_project_manager()
    return jsonify(mgr.list_projects())


@objects_bp.post("/projects")
def create_project():
    data = request.get_json(force=True)
    name = data.get("name", "")
    description = data.get("description", "")
    if not name:
        return jsonify({"error": "name is required"}), 400

    mgr = get_project_manager()
    try:
        project = mgr.create(name, description=description)
        return jsonify(project)
    except FileExistsError as e:
        return jsonify({"error": str(e)}), 409


@objects_bp.post("/projects/bind")
def bind_project():
    data = request.get_json(force=True)
    session_id = data.get("session_id", "")
    project_name = data.get("name", "")

    if not session_id or not project_name:
        return jsonify({"error": "session_id and name are required"}), 400

    from data_agent.session.history import bind_session_to_project

    result = bind_session_to_project(session_id, project_name)
    if result["success"]:
        return jsonify(result)
    return jsonify(result), 400


@objects_bp.post("/projects/<path:project_name>/rename")
def rename_project(project_name):
    data = request.get_json(force=True)
    new_name = data.get("new_name", "")
    if not new_name:
        return jsonify({"error": "new_name is required"}), 400

    mgr = get_project_manager()
    result = mgr.rename(project_name, new_name)
    if result is None:
        return jsonify({"error": "Project not found"}), 404
    if isinstance(result, str) and result.startswith("error:"):
        return jsonify({"error": result[6:].strip()}), 409
    return jsonify(result)


@objects_bp.delete("/projects/<path:project_name>")
def delete_project(project_name):
    mgr = get_project_manager()
    ok = mgr.delete(project_name)
    if ok:
        return jsonify({"deleted": project_name})
    return jsonify({"error": "Project not found"}), 404


@objects_bp.post("/projects/unbind")
def unbind_project():
    data = request.get_json(force=True)
    session_id = data.get("session_id", "")

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    from data_agent.session.history import unbind_session_from_project

    result = unbind_session_from_project(session_id)
    return jsonify(result)
