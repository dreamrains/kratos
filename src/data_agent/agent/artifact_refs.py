"""Shared hydration for compact JSON artifact references."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from data_agent.config import get_config


def hydrate_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_hydrate_ref(item) for item in items if isinstance(item, dict)]


def _hydrate_ref(item: dict[str, Any]) -> dict[str, Any]:
    artifact_path = _text(item.get("artifact_path"))
    if not artifact_path:
        return item
    artifact = _read_json_artifact(artifact_path)
    if artifact is None:
        return item
    return {**item, **artifact}


def _read_json_artifact(artifact_path: str) -> dict[str, Any] | None:
    try:
        path = Path(artifact_path)
        if path.suffix.lower() != ".json" or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def hydrate_trust_capsule_manifest(
    ref: dict[str, Any],
    *,
    expected_session_id: str,
    expected_plan_id: str,
    expected_body_digest: str,
    requested_ids: dict[str, list[str]] | None = None,
    per_component_limit: int = 8,
    include_confirmation: bool = False,
) -> dict[str, Any]:
    """Hydrate only explicitly requested trust identities from a verified manifest."""

    if not isinstance(ref, dict) or ref.get("contract_version") != "trust_capsule_manifest.v1":
        return {}
    safe_session_id = re.sub(
        r"[^A-Za-z0-9_.-]+", "_", str(expected_session_id or "")
    ).strip("._") or "session"
    assurance_root = (
        get_config().sessions_resolved / safe_session_id / "assurance"
    ).resolve()
    path = Path(str(ref.get("artifact_path") or "").strip()).resolve()
    if not path.is_relative_to(assurance_root):
        return {}
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    if hashlib.sha256(raw).hexdigest() != _text(ref.get("artifact_digest")):
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("contract_version") != "trust_capsule_manifest.v1":
        return {}
    if _text(payload.get("session_id")) != _text(expected_session_id):
        return {}
    body = payload.get("body")
    if not isinstance(body, dict):
        return {}
    canonical_body = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    body_digest = hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()
    if body_digest != _text(ref.get("body_digest")) or body_digest != _text(expected_body_digest):
        return {}
    plan = body.get("plan")
    if not isinstance(plan, dict) or _text(plan.get("id")) != _text(expected_plan_id):
        return {}

    requested = requested_ids if isinstance(requested_ids, dict) else {}
    limit = max(1, int(per_component_limit))
    result = {
        "active_confirmation": body.get("active_confirmation") if include_confirmation else None,
        "latest_audit": body.get("latest_audit"),
    }
    for component in ("datasets", "unresolved_hard_requirements", "evidence_bindings"):
        wanted = {
            _text(item) for item in requested.get(component, [])[:limit] if _text(item)
        }
        items = body.get(component)
        if not isinstance(items, list):
            result[component] = []
            continue
        if component == "datasets":
            identity = lambda item: _text(item.get("name"))
        else:
            identity = lambda item: _text(item.get("id"))
        result[component] = [
            dict(item)
            for item in items
            if isinstance(item, dict) and identity(item) in wanted
        ][:limit]
    return result
