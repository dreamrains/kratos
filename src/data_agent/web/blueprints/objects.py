"""Object management endpoints."""

from flask import Blueprint, current_app, jsonify, request

from data_agent.object_manager import get_object_manager

objects_bp = Blueprint("objects", __name__)


@objects_bp.get("/objects")
def list_objects():
    mgr = get_object_manager()
    return jsonify(mgr.list_objects())


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
