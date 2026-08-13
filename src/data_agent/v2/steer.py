from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from data_agent.v2.identity import require_storage_id


class SteerStatus(StrEnum):
    QUEUED = "queued"
    CONSUMED = "consumed"
    SUPERSEDED = "superseded"


class SteerConflict(RuntimeError):
    """A steer transition conflicts with its append-only history."""


@dataclass(frozen=True, slots=True)
class SteerRecord:
    steer_id: str
    client_request_id: str
    source_turn_id: str
    source_run_id: str
    message: str
    resume_payload: dict[str, Any]
    status: SteerStatus
    target_turn_id: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


_STEER_LOCK = threading.RLock()


def _line(value: dict[str, Any]) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


class SteerStore:
    """Append-only interaction ledger for next-turn steering messages."""

    def __init__(self, sessions_root: Path | str, session_id: str) -> None:
        safe_session_id = require_storage_id(session_id, "session_id")
        self.path = Path(sessions_root) / safe_session_id / "v2" / "steers.jsonl"

    @classmethod
    def from_v2_root(cls, v2_root: Path | str) -> "SteerStore":
        instance = object.__new__(cls)
        instance.path = Path(v2_root) / "steers.jsonl"
        return instance

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        values = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid steer JSONL at {self.path}:{line_number}"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError("invalid steer event")
            values.append(value)
        return values

    def _append(self, event: dict[str, Any]) -> None:
        event_id = require_storage_id(event.get("event_id", ""), "event_id")
        canonical = _line(event)
        for existing in self._events():
            if existing.get("event_id") != event_id:
                continue
            if _line(existing) == canonical:
                return
            raise SteerConflict(f"steer event conflict: {event_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def list_all(self) -> list[SteerRecord]:
        projected: dict[str, SteerRecord] = {}
        order: list[str] = []
        for event in self._events():
            steer_id = require_storage_id(event.get("steer_id", ""), "steer_id")
            event_type = str(event.get("event_type") or "")
            if event_type == "queued":
                if steer_id in projected:
                    raise SteerConflict(f"duplicate queued event for {steer_id}")
                payload = event.get("resume_payload")
                if not isinstance(payload, dict):
                    raise ValueError("steer resume_payload must be an object")
                projected[steer_id] = SteerRecord(
                    steer_id=steer_id,
                    client_request_id=event["client_request_id"],
                    source_turn_id=event["source_turn_id"],
                    source_run_id=event["source_run_id"],
                    message=event["message"],
                    resume_payload=dict(payload),
                    status=SteerStatus.QUEUED,
                )
                order.append(steer_id)
                continue
            current = projected.get(steer_id)
            if current is None:
                raise SteerConflict(f"steer transition without queued event: {steer_id}")
            if current.status is not SteerStatus.QUEUED:
                raise SteerConflict(
                    f"steer transition after {current.status.value}: {steer_id}"
                )
            if event_type == "consumed":
                projected[steer_id] = replace(
                    current,
                    status=SteerStatus.CONSUMED,
                    target_turn_id=event["target_turn_id"],
                )
            elif event_type == "superseded":
                projected[steer_id] = replace(
                    current,
                    status=SteerStatus.SUPERSEDED,
                    reason=str(event.get("reason") or "superseded"),
                )
            else:
                raise ValueError(f"unknown steer event_type: {event_type}")
        return [projected[steer_id] for steer_id in order]

    def get(self, steer_id: str) -> SteerRecord:
        safe_id = require_storage_id(steer_id, "steer_id")
        for item in self.list_all():
            if item.steer_id == safe_id:
                return item
        raise KeyError(f"unknown steer {safe_id}")

    def list_for_turn(self, turn_id: str) -> list[SteerRecord]:
        safe_turn_id = require_storage_id(turn_id, "turn_id")
        return [item for item in self.list_all() if item.source_turn_id == safe_turn_id]

    def queued_for_run(self, run_id: str) -> SteerRecord | None:
        safe_run_id = require_storage_id(run_id, "run_id")
        matches = [
            item
            for item in self.list_all()
            if item.source_run_id == safe_run_id and item.status is SteerStatus.QUEUED
        ]
        if len(matches) > 1:
            raise SteerConflict(f"run has multiple queued steers: {safe_run_id}")
        return matches[0] if matches else None

    def enqueue(
        self,
        *,
        source_turn_id: str,
        source_run_id: str,
        client_request_id: str,
        message: str,
        resume_payload: dict[str, Any],
    ) -> SteerRecord:
        safe_turn_id = require_storage_id(source_turn_id, "source_turn_id")
        safe_run_id = require_storage_id(source_run_id, "source_run_id")
        safe_client_id = require_storage_id(client_request_id, "client_request_id")
        normalized_message = str(message or "").strip()
        if not normalized_message:
            raise ValueError("steer message is required")
        if len(normalized_message) > 4000:
            raise ValueError("steer message must not exceed 4000 characters")
        if not isinstance(resume_payload, dict) or not resume_payload.get("analysis_kind"):
            raise ValueError("steer resume_payload requires analysis_kind")
        json.dumps(resume_payload, ensure_ascii=False, allow_nan=False)
        identity = _digest_id(safe_client_id)
        steer_id = f"steer_{identity}"
        with _STEER_LOCK:
            for existing in self.list_all():
                if existing.client_request_id != safe_client_id:
                    continue
                expected = (
                    existing.source_turn_id == safe_turn_id
                    and existing.source_run_id == safe_run_id
                    and existing.message == normalized_message
                    and existing.resume_payload == resume_payload
                )
                if not expected:
                    raise SteerConflict(
                        f"client_request_id has different steer content: {safe_client_id}"
                    )
                return existing
            queued = self.queued_for_run(safe_run_id)
            if queued is not None:
                self._append(
                    {
                        "event_id": f"steer_event_{_digest_id(queued.steer_id + ':superseded:' + steer_id)}",
                        "steer_id": queued.steer_id,
                        "event_type": "superseded",
                        "reason": f"replaced_by:{steer_id}",
                    }
                )
            self._append(
                {
                    "event_id": f"steer_event_{_digest_id(steer_id + ':queued')}",
                    "steer_id": steer_id,
                    "event_type": "queued",
                    "client_request_id": safe_client_id,
                    "source_turn_id": safe_turn_id,
                    "source_run_id": safe_run_id,
                    "message": normalized_message,
                    "resume_payload": resume_payload,
                }
            )
            return self.get(steer_id)

    def consume(self, steer_id: str, *, target_turn_id: str) -> SteerRecord:
        safe_steer_id = require_storage_id(steer_id, "steer_id")
        safe_target = require_storage_id(target_turn_id, "target_turn_id")
        with _STEER_LOCK:
            current = self.get(safe_steer_id)
            if current.status is SteerStatus.CONSUMED:
                if current.target_turn_id != safe_target:
                    raise SteerConflict("steer was consumed by a different target turn")
                return current
            if current.status is not SteerStatus.QUEUED:
                raise SteerConflict(f"cannot consume {current.status.value} steer")
            self._append(
                {
                    "event_id": f"steer_event_{_digest_id(safe_steer_id + ':consumed:' + safe_target)}",
                    "steer_id": safe_steer_id,
                    "event_type": "consumed",
                    "target_turn_id": safe_target,
                }
            )
            return self.get(safe_steer_id)

    def supersede_for_run(self, run_id: str, *, reason: str) -> SteerRecord | None:
        safe_run_id = require_storage_id(run_id, "run_id")
        normalized_reason = str(reason or "").strip() or "superseded"
        with _STEER_LOCK:
            queued = self.queued_for_run(safe_run_id)
            if queued is None:
                return None
            self._append(
                {
                    "event_id": f"steer_event_{_digest_id(queued.steer_id + ':superseded:' + normalized_reason)}",
                    "steer_id": queued.steer_id,
                    "event_type": "superseded",
                    "reason": normalized_reason,
                }
            )
            return self.get(queued.steer_id)


def _digest_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
