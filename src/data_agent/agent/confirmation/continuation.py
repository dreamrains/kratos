"""Integrity-protected continuation records for suspended turns."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping


class ContinuationIntegrityError(RuntimeError):
    pass


class ContinuationStatus(str, Enum):
    SUSPENDED = "suspended"
    RESUMED = "resumed"
    CANCELLED = "cancelled"
    FAILED = "failed"


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _safe_id(value: Any, name: str) -> str:
    text = _required(value, name)
    if not _SAFE_ID.fullmatch(text) or text in {".", ".."}:
        raise ValueError(f"{name} is not a safe identifier")
    return text


@dataclass(frozen=True)
class ContinuationRecord:
    confirmation_id: str
    session_id: str
    turn_id: str
    message_version: int
    completed_tool_call_ids: tuple[str, ...]
    blocked_operation: str
    request_identity: str
    status: ContinuationStatus

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "confirmation_id",
            _safe_id(self.confirmation_id, "confirmation_id"),
        )
        object.__setattr__(self, "session_id", _safe_id(self.session_id, "session_id"))
        object.__setattr__(self, "turn_id", _safe_id(self.turn_id, "turn_id"))
        version = int(self.message_version)
        if version < 0:
            raise ValueError("message_version cannot be negative")
        object.__setattr__(self, "message_version", version)
        tool_ids = tuple(
            _safe_id(value, "completed_tool_call_id")
            for value in (self.completed_tool_call_ids or ())
        )
        if len(set(tool_ids)) != len(tool_ids):
            raise ValueError("completed_tool_call_ids must be unique")
        object.__setattr__(self, "completed_tool_call_ids", tool_ids)
        object.__setattr__(
            self,
            "blocked_operation",
            _required(self.blocked_operation, "blocked_operation"),
        )
        object.__setattr__(
            self,
            "request_identity",
            _required(self.request_identity, "request_identity"),
        )
        status = self.status
        if not isinstance(status, ContinuationStatus):
            status = ContinuationStatus(status)
        object.__setattr__(self, "status", status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmation_id": self.confirmation_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "message_version": self.message_version,
            "completed_tool_call_ids": list(self.completed_tool_call_ids),
            "blocked_operation": self.blocked_operation,
            "request_identity": self.request_identity,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContinuationRecord":
        return cls(
            confirmation_id=payload.get("confirmation_id", ""),
            session_id=payload.get("session_id", ""),
            turn_id=payload.get("turn_id", ""),
            message_version=payload.get("message_version", -1),
            completed_tool_call_ids=tuple(payload.get("completed_tool_call_ids", ())),
            blocked_operation=payload.get("blocked_operation", ""),
            request_identity=payload.get("request_identity", ""),
            status=ContinuationStatus(payload.get("status", "")),
        )


class ContinuationStore:
    def __init__(
        self,
        sessions_root: Path,
        session_id: str,
        *,
        sync_file: Callable[[int], None] = os.fsync,
    ) -> None:
        try:
            self.session_id = _safe_id(session_id, "session_id")
        except ValueError as exc:
            raise ContinuationIntegrityError(str(exc)) from exc
        self.directory = (
            Path(sessions_root)
            / self.session_id
            / "confirmations"
            / "continuations"
        )
        self._sync_file = sync_file

    def path_for(self, confirmation_id: str) -> Path:
        try:
            safe_confirmation_id = _safe_id(confirmation_id, "confirmation_id")
        except ValueError as exc:
            raise ContinuationIntegrityError(str(exc)) from exc
        return self.directory / f"{safe_confirmation_id}.json"

    def save(self, record: ContinuationRecord) -> Path:
        if record.session_id != self.session_id:
            raise ContinuationIntegrityError(
                "continuation session does not match store session"
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(record.confirmation_id)
        temp_path = path.with_suffix(".json.tmp")
        payload = record.to_dict()
        envelope = {
            "payload": payload,
            "checksum": _checksum(payload),
        }
        encoded = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            with temp_path.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                self._sync_file(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        return path

    def load(self, confirmation_id: str) -> ContinuationRecord:
        path = self.path_for(confirmation_id)
        if not path.exists():
            raise ContinuationIntegrityError(
                f"continuation {confirmation_id} not found"
            )
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            payload = envelope["payload"]
            checksum = envelope["checksum"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ContinuationIntegrityError(
                f"continuation {confirmation_id} is unreadable: {exc}"
            ) from exc
        if checksum != _checksum(payload):
            raise ContinuationIntegrityError(
                f"continuation {confirmation_id} checksum mismatch"
            )
        try:
            record = ContinuationRecord.from_dict(payload)
        except (TypeError, ValueError) as exc:
            raise ContinuationIntegrityError(
                f"continuation {confirmation_id} is invalid: {exc}"
            ) from exc
        if record.confirmation_id != confirmation_id:
            raise ContinuationIntegrityError(
                "continuation confirmation_id does not match requested record"
            )
        if record.session_id != self.session_id:
            raise ContinuationIntegrityError(
                "continuation session does not match store session"
            )
        return record


def _checksum(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
