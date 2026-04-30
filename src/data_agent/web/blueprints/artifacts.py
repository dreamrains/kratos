"""Artifact listing and file serving."""

from pathlib import Path

from flask import Blueprint, jsonify, send_from_directory

from data_agent.config import get_config
from data_agent.session.history import list_artifacts

artifacts_bp = Blueprint("artifacts", __name__)


@artifacts_bp.get("/artifacts/<session_id>")
def get_artifacts(session_id: str):
    return jsonify(list_artifacts(session_id))


@artifacts_bp.get("/files/<path:filepath>")
def serve_file(filepath: str):
    project_dir = get_config().project_resolved
    resolved = (project_dir / filepath).resolve()

    if not str(resolved).startswith(str(project_dir.resolve())):
        return jsonify({"error": "Access denied"}), 403

    if not resolved.exists():
        return jsonify({"error": "File not found"}), 404

    return send_from_directory(str(resolved.parent), resolved.name)
