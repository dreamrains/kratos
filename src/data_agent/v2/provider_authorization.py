from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from data_agent.v2.identity import require_storage_id


class ProviderAuthorizationStatus(StrEnum):
    ISSUED = "issued"
    CONSUMED = "consumed"


class ProviderAuthorizationConflict(RuntimeError):
    """An authorization transition conflicts with append-only history."""


@dataclass(frozen=True, slots=True)
class ProviderAuthorizationRecord:
    authorization_id: str
    client_action_id: str
    purpose: str
    filename: str
    request_fingerprint: str
    provider_calls_authorized: int
    status: ProviderAuthorizationStatus
    planning_input_id: str = ""
    consumer_request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


_AUTHORIZATION_LOCK = threading.RLock()
_PLANNING_PURPOSE = "analysis_planning"


def _line(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _event_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def planning_request_fingerprint(
    *,
    purpose: str,
    filename: str,
    source_fingerprint: str,
    question: str,
    planning_input_id: str = "",
) -> str:
    normalized_purpose = str(purpose or "").strip()
    safe_filename = str(filename or "").strip()
    normalized_source = str(source_fingerprint or "").strip()
    normalized_question = str(question or "").strip()
    normalized_input = str(planning_input_id or "").strip()
    if normalized_input:
        normalized_input = require_storage_id(
            normalized_input, "planning_input_id"
        )
    if normalized_purpose != _PLANNING_PURPOSE:
        raise ValueError(f"purpose must equal {_PLANNING_PURPOSE}")
    if not safe_filename or Path(safe_filename).name != safe_filename:
        raise ValueError("filename must be a plain uploaded filename")
    if not normalized_source.startswith("sha256:") or len(normalized_source) != 71:
        raise ValueError("source_fingerprint must be a sha256 fingerprint")
    if not normalized_question:
        raise ValueError("question is required")
    canonical = _line(
        {
            "filename": safe_filename,
            "purpose": normalized_purpose,
            "question": normalized_question,
            "source_fingerprint": normalized_source,
            "planning_input_id": normalized_input,
        }
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


class ProviderAuthorizationStore:
    """Append-only, session-scoped ledger for exact-count Provider permission."""

    def __init__(self, sessions_root: Path | str, session_id: str) -> None:
        safe_session_id = require_storage_id(session_id, "session_id")
        self.path = (
            Path(sessions_root)
            / safe_session_id
            / "v2"
            / "provider_authorizations.jsonl"
        )

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid provider authorization JSONL at "
                    f"{self.path}:{line_number}"
                ) from exc
            if not isinstance(event, dict):
                raise ValueError("invalid provider authorization event")
            events.append(event)
        return events

    def _append(self, event: dict[str, Any]) -> None:
        event_id = require_storage_id(event.get("event_id", ""), "event_id")
        canonical = _line(event)
        for existing in self._events():
            if existing.get("event_id") != event_id:
                continue
            if _line(existing) == canonical:
                return
            raise ProviderAuthorizationConflict(
                f"provider authorization event conflict: {event_id}"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def list_all(self) -> list[ProviderAuthorizationRecord]:
        projected: dict[str, ProviderAuthorizationRecord] = {}
        order: list[str] = []
        for event in self._events():
            authorization_id = require_storage_id(
                event.get("authorization_id", ""), "authorization_id"
            )
            event_type = str(event.get("event_type") or "")
            if event_type == "issued":
                if authorization_id in projected:
                    raise ProviderAuthorizationConflict(
                        f"duplicate issued event for {authorization_id}"
                    )
                projected[authorization_id] = ProviderAuthorizationRecord(
                    authorization_id=authorization_id,
                    client_action_id=require_storage_id(
                        event.get("client_action_id", ""), "client_action_id"
                    ),
                    purpose=str(event.get("purpose") or ""),
                    filename=str(event.get("filename") or ""),
                    request_fingerprint=str(
                        event.get("request_fingerprint") or ""
                    ),
                    provider_calls_authorized=int(
                        event.get("provider_calls_authorized") or 0
                    ),
                    status=ProviderAuthorizationStatus.ISSUED,
                    planning_input_id=str(event.get("planning_input_id") or ""),
                )
                order.append(authorization_id)
                continue
            current = projected.get(authorization_id)
            if current is None:
                raise ProviderAuthorizationConflict(
                    f"authorization transition without issue: {authorization_id}"
                )
            if event_type != "consumed":
                raise ValueError(
                    f"unknown provider authorization event_type: {event_type}"
                )
            if current.status is not ProviderAuthorizationStatus.ISSUED:
                raise ProviderAuthorizationConflict(
                    f"authorization transition after {current.status.value}: "
                    f"{authorization_id}"
                )
            projected[authorization_id] = replace(
                current,
                status=ProviderAuthorizationStatus.CONSUMED,
                consumer_request_id=require_storage_id(
                    event.get("consumer_request_id", ""), "consumer_request_id"
                ),
            )
        return [projected[item_id] for item_id in order]

    def get(self, authorization_id: str) -> ProviderAuthorizationRecord:
        safe_id = require_storage_id(authorization_id, "authorization_id")
        for record in self.list_all():
            if record.authorization_id == safe_id:
                return record
        raise KeyError(f"unknown provider authorization {safe_id}")

    def issue(
        self,
        *,
        client_action_id: str,
        purpose: str,
        filename: str,
        source_fingerprint: str,
        question: str,
        provider_calls_authorized: int,
        confirm_provider_call: bool,
        planning_input_id: str = "",
    ) -> ProviderAuthorizationRecord:
        action_id = require_storage_id(client_action_id, "client_action_id")
        if confirm_provider_call is not True:
            raise ValueError("confirm_provider_call must equal true")
        if (
            isinstance(provider_calls_authorized, bool)
            or provider_calls_authorized != 1
        ):
            raise ValueError("provider_calls_authorized must equal 1")
        request_fingerprint = planning_request_fingerprint(
            purpose=purpose,
            filename=filename,
            source_fingerprint=source_fingerprint,
            question=question,
            planning_input_id=planning_input_id,
        )
        normalized_purpose = str(purpose).strip()
        normalized_filename = str(filename).strip()
        normalized_input = str(planning_input_id or "").strip()
        with _AUTHORIZATION_LOCK:
            existing = next(
                (
                    item
                    for item in self.list_all()
                    if item.client_action_id == action_id
                ),
                None,
            )
            if existing is not None:
                same = (
                    existing.purpose == normalized_purpose
                    and existing.filename == normalized_filename
                    and existing.request_fingerprint == request_fingerprint
                    and existing.provider_calls_authorized
                    == provider_calls_authorized
                    and existing.planning_input_id == normalized_input
                )
                if not same:
                    raise ProviderAuthorizationConflict(
                        f"client_action_id has different authorization content: "
                        f"{action_id}"
                    )
                return existing
            authorization_id = f"provider_auth_{uuid.uuid4().hex}"
            self._append(
                {
                    "event_id": (
                        "provider_auth_event_"
                        + _event_digest(authorization_id + ":issued")
                    ),
                    "authorization_id": authorization_id,
                    "event_type": "issued",
                    "client_action_id": action_id,
                    "purpose": normalized_purpose,
                    "filename": normalized_filename,
                    "request_fingerprint": request_fingerprint,
                    "provider_calls_authorized": provider_calls_authorized,
                    "planning_input_id": normalized_input,
                }
            )
            return self.get(authorization_id)

    def consume(
        self,
        authorization_id: str,
        *,
        client_request_id: str,
        purpose: str,
        filename: str,
        source_fingerprint: str,
        question: str,
        planning_input_id: str = "",
    ) -> ProviderAuthorizationRecord:
        safe_id = require_storage_id(authorization_id, "authorization_id")
        consumer_id = require_storage_id(client_request_id, "client_request_id")
        request_fingerprint = planning_request_fingerprint(
            purpose=purpose,
            filename=filename,
            source_fingerprint=source_fingerprint,
            question=question,
            planning_input_id=planning_input_id,
        )
        with _AUTHORIZATION_LOCK:
            current = self.get(safe_id)
            if current.request_fingerprint != request_fingerprint:
                raise ProviderAuthorizationConflict(
                    "provider authorization is bound to different request content"
                )
            if current.status is ProviderAuthorizationStatus.CONSUMED:
                if current.consumer_request_id != consumer_id:
                    raise ProviderAuthorizationConflict(
                        "provider authorization was consumed by a different request"
                    )
                return current
            self._append(
                {
                    "event_id": (
                        "provider_auth_event_"
                        + _event_digest(safe_id + ":consumed:" + consumer_id)
                    ),
                    "authorization_id": safe_id,
                    "event_type": "consumed",
                    "consumer_request_id": consumer_id,
                }
            )
            return self.get(safe_id)
