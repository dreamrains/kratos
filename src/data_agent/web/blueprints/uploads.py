"""File upload staging, session binding, and deterministic ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import threading
import uuid

from flask import Blueprint, jsonify, request

from data_agent.config import get_config
from data_agent.file_formats import SUPPORTED_DATA_EXTENSIONS

uploads_bp = Blueprint("uploads", __name__)

ALLOWED_EXTENSIONS = SUPPORTED_DATA_EXTENSIONS
_UPLOAD_ID_RE = re.compile(r"[0-9a-f]{32}")
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
_UPLOAD_BIND_LOCK = threading.RLock()


class UploadBindingError(ValueError):
    """A structured upload reference is invalid or no longer claimable."""


class UploadIngestionError(ValueError):
    """A claimed upload could not be loaded into its owning session."""


@dataclass(frozen=True)
class BoundUpload:
    upload_id: str
    session_id: str
    filename: str
    path: Path
    size: int
    sha256: str
    record_path: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pending_uploads_dir() -> Path:
    root = get_config().sessions_resolved / ".pending_uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalise_filename(value: str) -> str:
    raw = str(value or "").strip()
    portable = raw.replace("\\", "/")
    name = PurePosixPath(portable).name
    if not name or name in {".", ".."} or name != portable:
        raise UploadBindingError("Invalid upload filename")
    if any(ord(char) < 32 for char in name):
        raise UploadBindingError("Invalid upload filename")
    return name


def _validate_upload_id(value: object) -> str:
    upload_id = str(value or "").strip().lower()
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        raise UploadBindingError("Invalid upload_id")
    return upload_id


def _validate_session_id(value: object) -> str:
    session_id = str(value or "").strip()
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise UploadBindingError("Invalid session_id for upload binding")
    return session_id


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_upload_record(directory: Path, upload_id: str) -> dict:
    record_path = directory / "upload.json"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UploadBindingError(f"Upload {upload_id} is not available") from exc
    if record.get("upload_id") != upload_id:
        raise UploadBindingError(f"Upload {upload_id} has invalid metadata")
    filename = _normalise_filename(record.get("filename", ""))
    file_path = directory / filename
    if not file_path.is_file():
        raise UploadBindingError(f"Upload {upload_id} is not available")
    return record


def _bound_upload(directory: Path, session_id: str, record: dict) -> BoundUpload:
    filename = _normalise_filename(record.get("filename", ""))
    return BoundUpload(
        upload_id=str(record["upload_id"]),
        session_id=session_id,
        filename=filename,
        path=directory / filename,
        size=int(record.get("size") or 0),
        sha256=str(record.get("sha256") or ""),
        record_path=directory / "upload.json",
    )


def _verify_upload_payload(directory: Path, record: dict) -> None:
    filename = _normalise_filename(record.get("filename", ""))
    path = directory / filename
    expected_size = int(record.get("size") or -1)
    expected_hash = str(record.get("sha256") or "")
    try:
        actual_size = path.stat().st_size
        actual_hash = _sha256_file(path)
    except OSError as exc:
        raise UploadBindingError(f"Upload {record.get('upload_id')} is not available") from exc
    if actual_size != expected_size or actual_hash != expected_hash:
        raise UploadBindingError(f"Upload {record.get('upload_id')} failed integrity verification")


def bind_uploads_to_session(session_id: str, references: object) -> list[BoundUpload]:
    """Atomically claim opaque upload tickets for exactly one session."""

    if references in (None, []):
        return []
    if not isinstance(references, list) or len(references) > 20:
        raise UploadBindingError("uploads must be a list containing at most 20 items")
    safe_session_id = _validate_session_id(session_id)

    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    for reference in references:
        if not isinstance(reference, dict):
            raise UploadBindingError("Each upload reference must be an object")
        upload_id = _validate_upload_id(reference.get("upload_id"))
        filename = _normalise_filename(reference.get("filename", ""))
        if upload_id in seen:
            raise UploadBindingError(f"Duplicate upload_id: {upload_id}")
        seen.add(upload_id)
        parsed.append((upload_id, filename))

    pending_root = _pending_uploads_dir()
    session_uploads = get_config().sessions_resolved / safe_session_id / "uploads"

    with _UPLOAD_BIND_LOCK:
        prepared: list[tuple[str, str, Path, dict, bool]] = []
        for upload_id, expected_filename in parsed:
            pending_dir = pending_root / upload_id
            bound_dir = session_uploads / upload_id
            if bound_dir.is_dir():
                record = _read_upload_record(bound_dir, upload_id)
                if record.get("session_id") != safe_session_id:
                    raise UploadBindingError(f"Upload {upload_id} is not available")
                from_pending = False
            elif pending_dir.is_dir():
                record = _read_upload_record(pending_dir, upload_id)
                from_pending = True
            else:
                raise UploadBindingError(f"Upload {upload_id} is not available")
            if record.get("filename") != expected_filename:
                raise UploadBindingError(f"Upload {upload_id} filename does not match its ticket")
            _verify_upload_payload(bound_dir if not from_pending else pending_dir, record)
            prepared.append((upload_id, expected_filename, bound_dir, record, from_pending))

        session_uploads.mkdir(parents=True, exist_ok=True)
        bound: list[BoundUpload] = []
        for upload_id, _filename, bound_dir, record, from_pending in prepared:
            if from_pending:
                (pending_root / upload_id).replace(bound_dir)
            record.update({
                "status": record.get("status") if record.get("status") == "loaded" else "claimed",
                "session_id": safe_session_id,
                "claimed_at": record.get("claimed_at") or _now(),
            })
            _write_json_atomic(bound_dir / "upload.json", record)
            bound.append(_bound_upload(bound_dir, safe_session_id, record))
        return bound


def _dataset_name_for_upload(filename: str, existing: set[str]) -> str:
    stem = Path(filename).stem.strip() or "data"
    candidate = stem
    index = 2
    while candidate in existing or f"{candidate}__raw" in existing:
        candidate = f"{stem}_{index}"
        index += 1
    return candidate


def _update_ingestion_record(upload: BoundUpload, **updates) -> dict:
    record = _read_upload_record(upload.record_path.parent, upload.upload_id)
    record.update(updates)
    record["updated_at"] = _now()
    _write_json_atomic(upload.record_path, record)
    return record


def ingest_bound_uploads(agent_loop, uploads: list[BoundUpload]) -> str:
    """Load claimed files before analysis planning and return trusted turn context."""

    if not uploads:
        return ""

    from data_agent.agent.context import use_agent_context
    from data_agent.session.workspace import workspace
    from data_agent.tools.data_io import load_data

    loaded: list[tuple[BoundUpload, str, str]] = []
    with use_agent_context(agent_loop.context):
        existing = set(workspace.list_datasets())
        for upload in uploads:
            record = _read_upload_record(upload.record_path.parent, upload.upload_id)
            _verify_upload_payload(upload.record_path.parent, record)
            recorded_dataset = str(record.get("dataset_name") or "")
            if record.get("status") == "loaded" and recorded_dataset in existing:
                loaded.append((upload, recorded_dataset, "already loaded from an earlier retry"))
                continue

            dataset_name = _dataset_name_for_upload(upload.filename, existing)
            result = str(load_data(str(upload.path), name=dataset_name))
            if result.lstrip().startswith("Error"):
                _update_ingestion_record(upload, status="failed", error=result[:2000])
                raise UploadIngestionError(
                    f"Uploaded file {upload.filename} could not be loaded: {result}"
                )

            existing = set(workspace.list_datasets())
            for name, info in workspace.list_datasets().items():
                metadata = info.get("metadata") if isinstance(info, dict) else {}
                if str((metadata or {}).get("_source_path") or "") == str(upload.path):
                    workspace.set_metadata(name, "_upload_id", upload.upload_id)
                    workspace.set_metadata(name, "_original_filename", upload.filename)
                    workspace.set_metadata(name, "_source_sha256", upload.sha256)
            workspace.save_meta(upload.session_id)
            _update_ingestion_record(
                upload,
                status="loaded",
                dataset_name=dataset_name,
                loaded_at=_now(),
                error="",
            )
            loaded.append((upload, dataset_name, result))

    invalidate = getattr(agent_loop, "invalidate_prompt_cache", None)
    if callable(invalidate):
        invalidate()

    lines = [
        "<uploaded_data_context>",
        "The server verified these attachment tickets and they are already loaded into this session before analysis planning.",
        "Use the listed dataset names directly. Do not ask the user for file paths and do not reload the same attachments.",
    ]
    for upload, dataset_name, result in loaded:
        compact_result = result[:3500]
        lines.append(
            f"- {upload.filename} -> dataset `{dataset_name}` "
            f"(upload_id={upload.upload_id}, sha256={upload.sha256})\n{compact_result}"
        )
    lines.append("</uploaded_data_context>")
    return "\n".join(lines)


@uploads_bp.post("/upload")
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file_storage = request.files["file"]
    if not file_storage.filename:
        return jsonify({"error": "Empty filename"}), 400

    try:
        filename = _normalise_filename(file_storage.filename)
    except UploadBindingError as exc:
        return jsonify({"error": str(exc)}), 400

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    upload_id = uuid.uuid4().hex
    root = _pending_uploads_dir()
    temporary_dir = root / f".{upload_id}.tmp"
    ticket_dir = root / upload_id
    temporary_dir.mkdir(parents=False, exist_ok=False)
    try:
        destination = temporary_dir / filename
        file_storage.save(str(destination))
        record = {
            "schema_version": 1,
            "upload_id": upload_id,
            "filename": filename,
            "size": destination.stat().st_size,
            "sha256": _sha256_file(destination),
            "status": "pending",
            "session_id": "",
            "created_at": _now(),
        }
        _write_json_atomic(temporary_dir / "upload.json", record)
        temporary_dir.replace(ticket_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise

    return jsonify({
        "upload_id": upload_id,
        "filename": filename,
        "size": record["size"],
        "sha256": record["sha256"],
    })


@uploads_bp.delete("/upload/<upload_id>")
def cancel_upload(upload_id: str):
    """Discard an unclaimed upload ticket when the user removes an attachment."""

    try:
        safe_upload_id = _validate_upload_id(upload_id)
    except UploadBindingError as exc:
        return jsonify({"error": str(exc)}), 400

    with _UPLOAD_BIND_LOCK:
        pending_dir = _pending_uploads_dir() / safe_upload_id
        if pending_dir.is_dir():
            shutil.rmtree(pending_dir)

    # Cancellation is intentionally idempotent. A ticket that has already
    # been claimed is session-owned and is never removed by this endpoint.
    return jsonify({"upload_id": safe_upload_id, "status": "cancelled"})
