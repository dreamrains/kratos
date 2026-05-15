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
    cfg = get_config()
    parts = Path(filepath).parts
    if parts and parts[0] == "sessions":
        base_dir = cfg.sessions_resolved
        inner = str(Path(*parts[1:])) if len(parts) > 1 else ""
        resolved = (base_dir / inner).resolve()
    else:
        base_dir = cfg.project_resolved
        resolved = (base_dir / filepath).resolve()

    if not str(resolved).startswith(str(base_dir.resolve())):
        return jsonify({"error": "Access denied"}), 403

    if not resolved.exists():
        return jsonify({"error": "File not found"}), 404

    return send_from_directory(str(resolved.parent), resolved.name)
