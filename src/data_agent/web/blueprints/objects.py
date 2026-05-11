"""Project management endpoints.

The /objects routes remain as backward-compatible aliases.
"""

from flask import Blueprint, current_app, jsonify, request

from data_agent.object_manager import get_object_manager

objects_bp = Blueprint("objects", __name__)


@objects_bp.get("/objects")
def list_objects():
    mgr = get_object_manager()
    return jsonify(mgr.list_objects())


@objects_bp.get("/projects")
def list_projects():
    mgr = get_object_manager()
    return jsonify(mgr.list_projects())


@objects_bp.post("/objects")
def create_object():
    data = request.get_json(force=True)
    name = data.get("name", "")
    description = data.get("description", "")
    if not name:
        return jsonify({"error": "name is required"}), 400

    mgr = get_object_manager()
    try:
        obj = mgr.create(name, description=description)
        return jsonify(obj)
    except FileExistsError as e:
        return jsonify({"error": str(e)}), 409


@objects_bp.post("/projects")
def create_project():
    data = request.get_json(force=True)
    name = data.get("name", "")
    description = data.get("description", "")
    if not name:
        return jsonify({"error": "name is required"}), 400

    mgr = get_object_manager()
    try:
        project = mgr.create_project(name, description=description)
        return jsonify(project)
    except FileExistsError as e:
        return jsonify({"error": str(e)}), 409


@objects_bp.post("/objects/bind")
def bind_object():
    """Bind current session to an object."""
    data = request.get_json(force=True)
    session_id = data.get("session_id", "")
    object_name = data.get("name", "")

    if not session_id or not object_name:
        return jsonify({"error": "session_id and name are required"}), 400

    from data_agent.session.history import bind_session_to_object
    result = bind_session_to_object(session_id, object_name)
    if result["success"]:
        return jsonify(result)
    return jsonify(result), 400


@objects_bp.post("/projects/bind")
def bind_project():
    """Bind current session to a project."""
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


@objects_bp.post("/objects/<path:object_name>/rename")
def rename_object(object_name):
    """Rename an object."""
    data = request.get_json(force=True)
    new_name = data.get("new_name", "")
    if not new_name:
        return jsonify({"error": "new_name is required"}), 400

    mgr = get_object_manager()
    result = mgr.rename(object_name, new_name)
    if result is None:
        return jsonify({"error": "Object not found"}), 404
    if isinstance(result, str) and result.startswith("error:"):
        return jsonify({"error": result[6:].strip()}), 409
    return jsonify(result)


@objects_bp.post("/projects/<path:project_name>/rename")
def rename_project(project_name):
    """Rename a project."""
    data = request.get_json(force=True)
    new_name = data.get("new_name", "")
    if not new_name:
        return jsonify({"error": "new_name is required"}), 400

    mgr = get_object_manager()
    result = mgr.rename_project(project_name, new_name)
    if result is None:
        return jsonify({"error": "Project not found"}), 404
    if isinstance(result, str) and result.startswith("error:"):
        return jsonify({"error": result[6:].strip()}), 409
    return jsonify(result)


@objects_bp.delete("/objects/<path:object_name>")
def delete_object(object_name):
    mgr = get_object_manager()
    ok = mgr.delete(object_name)
    if ok:
        return jsonify({"deleted": object_name})
    return jsonify({"error": "Object not found"}), 404


@objects_bp.delete("/projects/<path:project_name>")
def delete_project(project_name):
    mgr = get_object_manager()
    ok = mgr.delete_project(project_name)
    if ok:
        return jsonify({"deleted": project_name})
    return jsonify({"error": "Project not found"}), 404


@objects_bp.post("/objects/unbind")
def unbind_object():
    """Unbind current session from its object."""
    data = request.get_json(force=True)
    session_id = data.get("session_id", "")

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    from data_agent.session.history import unbind_session_from_object
    result = unbind_session_from_object(session_id)
    return jsonify(result)


@objects_bp.post("/projects/unbind")
def unbind_project():
    """Unbind current session from its project."""
    data = request.get_json(force=True)
    session_id = data.get("session_id", "")

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    from data_agent.session.history import unbind_session_from_project
    result = unbind_session_from_project(session_id)
    return jsonify(result)
