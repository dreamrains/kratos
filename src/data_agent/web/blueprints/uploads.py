"""File upload handling."""

from pathlib import Path

from flask import Blueprint, jsonify, request

from data_agent.config import get_config

uploads_bp = Blueprint("uploads", __name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".tsv", ".parquet"}


@uploads_bp.post("/upload")
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    inbox = get_config().inbox_dir
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / f.filename
    f.save(str(dest))

    return jsonify({
        "filename": f.filename,
        "path": str(dest),
        "size": dest.stat().st_size,
    })
