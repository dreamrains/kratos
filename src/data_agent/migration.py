"""One-time, inspectable migration support for Route A session data.

The migration is deliberately split into a read-only audit and an explicit
apply operation. It never reconstructs an unavailable original upload from a
backup, and it never introduces a dual-write compatibility path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from data_agent.config import get_config


MIGRATION_SCHEMA = "route_a_identity_artifacts_v1"
_IDENTITY_KEYS = {"version_id", "role", "fingerprint", "source_fingerprint", "parent_version_ids", "expression"}


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, (dict, list)) else None


def _content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _identity_from_source(source_hash: str) -> dict[str, Any]:
    version_digest = hashlib.sha256(json.dumps({"fingerprint": source_hash, "role": "raw", "parents": [], "expression": ""}, sort_keys=True).encode("utf-8")).hexdigest()
    return {"version_id": f"dv_{version_digest[:16]}", "role": "raw", "fingerprint": source_hash, "source_fingerprint": source_hash, "parent_version_ids": [], "expression": ""}


def _has_current_identity(value: Any) -> bool:
    return isinstance(value, dict) and _IDENTITY_KEYS <= set(value)


def _source_path(value: Any) -> Path | None:
    return Path(value).expanduser() if isinstance(value, str) and value.strip() else None


def _artifact_path(value: str, session_id: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    cfg = get_config()
    return cfg.sessions_resolved.parent.joinpath(*path.parts) if len(path.parts) >= 2 and path.parts[0] == "sessions" else cfg.sessions_resolved / session_id / path


def _artifact_references(value: Any, session_id: str, prefix: str = "") -> list[dict[str, str]]:
    """Find persisted artifact references without treating source files as artifacts."""
    result: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, str) and (key == "artifact_path" or key == "path"):
                result.append({"field": location, "path": item})
            else:
                result.extend(_artifact_references(item, session_id, location))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(_artifact_references(item, session_id, f"{prefix}[{index}]"))
    return result


def _session_record(session_dir: Path) -> dict[str, Any]:
    session_id = session_dir.name
    meta_path, workspace_path, analysis_path = (session_dir / "meta.json", session_dir / "workspace_meta.json", session_dir / "analysis_state.json")
    meta, workspace_meta, analysis_state = _read_json(meta_path), _read_json(workspace_path), _read_json(analysis_path)
    invalid_json = [name for name, path, payload in (("meta", meta_path, meta), ("workspace_meta", workspace_path, workspace_meta), ("analysis_state", analysis_path, analysis_state)) if path.exists() and payload is None]
    workspace = workspace_meta if isinstance(workspace_meta, dict) else {}
    datasets, hashes = [], {}
    for name, info in sorted(workspace.items()):
        if not isinstance(info, dict):
            continue
        source = _source_path(info.get("source_path"))
        source_exists = bool(source and source.is_file())
        if source_exists:
            hashes[f"source:{name}"] = _content_hash(source)
        backup = next((path for path in (session_dir / "data" / f"{name}.parquet", session_dir / "data" / f"{name}.pkl") if path.is_file()), None)
        if backup is not None:
            hashes[f"backup:{name}"] = _content_hash(backup)
        datasets.append({"dataset": str(name), "source_path": str(source) if source else "", "original_exists": source_exists, "backup_exists": backup is not None, "identity_present": _has_current_identity(info.get("data_identity")), "source_hash": hashes.get(f"source:{name}", "")})
    artifact_sources = []
    if isinstance(analysis_state, dict):
        artifact_sources.append(("analysis_state", analysis_state))
    manifest = _read_json(session_dir / "artifacts.json")
    if manifest is not None:
        artifact_sources.append(("artifacts", manifest))
    artifacts: list[dict[str, Any]] = []
    for label, payload in artifact_sources:
        for ref in _artifact_references(payload, session_id, label):
            physical = _artifact_path(ref["path"], session_id)
            exists = physical.is_file()
            if exists:
                hashes[f"artifact:{ref['field']}"] = _content_hash(physical)
            artifacts.append({**ref, "exists": exists, "content_hash": hashes.get(f"artifact:{ref['field']}", "")})
    missing_original = [item["dataset"] for item in datasets if item["source_path"] and not item["original_exists"]]
    return {"session_id": session_id, "session_dir": str(session_dir), "workspace_meta_path": str(workspace_path), "workspace_meta_exists": workspace_path.exists(), "invalid_json": invalid_json, "datasets": datasets, "artifact_references": artifacts, "missing_original_datasets": missing_original, "read_only_required": bool(missing_original), "content_hashes": hashes}


def audit_route_a_migration() -> dict[str, Any]:
    """Read-only inventory of sessions requiring Route A identity migration."""
    sessions_dir = get_config().sessions_resolved
    records = [_session_record(path) for path in sorted(sessions_dir.iterdir()) if path.is_dir()]
    datasets = [dataset for record in records for dataset in record["datasets"]]
    artifacts = [artifact for record in records for artifact in record["artifact_references"]]
    summary = {"sessions": len(records), "sessions_with_workspace_meta": sum(record["workspace_meta_exists"] for record in records), "datasets": len(datasets), "identities_present": sum(dataset["identity_present"] for dataset in datasets), "identities_missing": sum(not dataset["identity_present"] for dataset in datasets), "missing_original_datasets": sum(len(record["missing_original_datasets"]) for record in records), "read_only_sessions_required": sum(record["read_only_required"] for record in records), "artifact_references": len(artifacts), "missing_artifact_references": sum(not artifact["exists"] for artifact in artifacts), "invalid_json_files": sum(len(record["invalid_json"]) for record in records), "content_hashes": sum(len(record["content_hashes"]) for record in records)}
    canonical = json.dumps({"schema": MIGRATION_SCHEMA, "summary": summary, "sessions": records}, ensure_ascii=False, sort_keys=True)
    return {"schema": MIGRATION_SCHEMA, "mode": "dry_run", "summary": summary, "sessions": records, "audit_hash": f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"}


def read_session_migration_status(session_id: str) -> dict[str, Any]:
    """Return explicit status; absence means legacy/unmigrated."""
    payload = _read_json(get_config().sessions_resolved / session_id / "migration_status.json")
    return dict(payload) if isinstance(payload, dict) else {}


def apply_route_a_migration() -> dict[str, Any]:
    """Write reviewed identity/status metadata after a dry-run has been reviewed."""
    audit = audit_route_a_migration()
    applied = {"identity_records": 0, "read_only_statuses": 0, "status_records": 0, "already_migrated": 0}
    for record in audit["sessions"]:
        session_dir, workspace_path = Path(record["session_dir"]), Path(record["workspace_meta_path"])
        workspace, changed = (_read_json(workspace_path) if record["workspace_meta_exists"] else {}), False
        if isinstance(workspace, dict):
            by_name = {item["dataset"]: item for item in record["datasets"]}
            for name, info in workspace.items():
                dataset = by_name.get(str(name), {})
                if isinstance(info, dict) and not dataset.get("identity_present") and dataset.get("source_hash"):
                    info["data_identity"] = _identity_from_source(dataset["source_hash"])
                    changed, applied["identity_records"] = True, applied["identity_records"] + 1
            if changed:
                workspace_path.write_text(json.dumps(workspace, ensure_ascii=False, indent=2), encoding="utf-8")
        if read_session_migration_status(record["session_id"]).get("schema") == MIGRATION_SCHEMA:
            applied["already_migrated"] += 1
            continue
        mode = "read_only_missing_original" if record["read_only_required"] else "identity_migrated"
        status = {"schema": MIGRATION_SCHEMA, "mode": mode, "session_id": record["session_id"], "missing_original_datasets": record["missing_original_datasets"], "audit_hash": audit["audit_hash"]}
        (session_dir / "migration_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        applied["status_records"] += 1
        if mode == "read_only_missing_original":
            applied["read_only_statuses"] += 1
    return {**audit, "mode": "applied", "applied": applied}


def collect_legacy_project_knowledge_for_review() -> dict:
    """Copy legacy project knowledge to a review area without promoting it."""
    cfg = get_config()
    review_root = cfg.workspace_resolved / "migration-review" / "project-knowledge"
    copied: list[str] = []
    for source_root in (cfg.objects_dir, cfg.projects_dir):
        for knowledge_dir in source_root.glob("*/knowledge") if source_root.exists() else []:
            if knowledge_dir.is_dir():
                target_dir = review_root / source_root.name / knowledge_dir.parent.name
                target_dir.mkdir(parents=True, exist_ok=True)
                for file_path in knowledge_dir.iterdir():
                    if file_path.is_file():
                        target = target_dir / file_path.name
                        shutil.copy2(file_path, target)
                        copied.append(str(target))
    return {"review_dir": str(review_root), "copied": copied, "copied_count": len(copied)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Route A session migration readiness")
    parser.add_argument("--apply", action="store_true", help="write reviewed identity/status metadata")
    args = parser.parse_args(argv)
    print(json.dumps(apply_route_a_migration() if args.apply else audit_route_a_migration(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
