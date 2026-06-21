"""Durable session-scoped event storage for confirmations."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import threading
from typing import Callable, Mapping

from data_agent.agent.confirmation.models import ConfirmationEvent, ConfirmationRecord


class StoreIntegrityError(RuntimeError):
    """Raised when confirmation persistence cannot be trusted."""


@dataclass(frozen=True)
class StoreLoadResult:
    records: Mapping[str, ConfirmationRecord]
    event_ids: tuple[str, ...]
    integrity_status: str = "ok"
    error: str = ""
    events_by_id: Mapping[str, ConfirmationEvent] | None = None


_LOCKS_GUARD = threading.Lock()
_SESSION_LOCKS: dict[str, threading.RLock] = {}
_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve()).casefold()
    with _LOCKS_GUARD:
        return _SESSION_LOCKS.setdefault(key, threading.RLock())


class ConfirmationStore:
    """Append events and materialize a reconstructable record snapshot."""

    def __init__(
        self,
        sessions_root: Path,
        session_id: str,
        *,
        sync_file: Callable[[int], None] = os.fsync,
    ) -> None:
        if not _SAFE_SESSION_ID.fullmatch(str(session_id or "")) or session_id in {".", ".."}:
            raise StoreIntegrityError("session_id is not a safe path component")
        self.session_id = session_id
        self.directory = Path(sessions_root) / session_id / "confirmations"
        self.events_path = self.directory / "events.jsonl"
        self.snapshot_path = self.directory / "snapshot.json"
        self._sync_file = sync_file
        self._lock = _lock_for(self.directory)

    def append(self, event: ConfirmationEvent) -> StoreLoadResult:
        if event.session_id != self.session_id:
            raise StoreIntegrityError("event session does not match store session")
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            current = self._replay()
            if current.integrity_status != "ok":
                raise StoreIntegrityError(
                    current.error or f"event store status is {current.integrity_status}"
                )
            events_by_id = dict(current.events_by_id or {})
            existing_event = events_by_id.get(event.event_id)
            if existing_event is not None:
                if existing_event != event:
                    raise StoreIntegrityError(
                        f"event_id {event.event_id} has conflicting payloads"
                    )
                return current

            records = dict(current.records)
            existing_record = records.get(event.confirmation_id)
            expected_version = 1 if existing_record is None else existing_record.version + 1
            if event.version != expected_version:
                raise StoreIntegrityError(
                    f"event version {event.version} does not follow {expected_version - 1}"
                )

            encoded = (
                json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            with self.events_path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                self._sync_file(handle.fileno())

            records[event.confirmation_id] = event.record
            event_ids = (*current.event_ids, event.event_id)
            events_by_id[event.event_id] = event
            result = StoreLoadResult(
                records=records,
                event_ids=event_ids,
                events_by_id=events_by_id,
            )
            self._write_snapshot(result)
            return result

    def load(self) -> StoreLoadResult:
        with self._lock:
            result = self._replay()
            if result.integrity_status != "corrupt":
                self.directory.mkdir(parents=True, exist_ok=True)
                self._write_snapshot(result)
            return result

    def load_records(self) -> dict[str, ConfirmationRecord]:
        result = self.load()
        if result.integrity_status == "corrupt":
            raise StoreIntegrityError(result.error or "confirmation event store is corrupt")
        return dict(result.records)

    def _replay(self) -> StoreLoadResult:
        if not self.events_path.exists():
            return StoreLoadResult(records={}, event_ids=(), events_by_id={})
        try:
            content = self.events_path.read_bytes()
        except OSError as exc:
            return StoreLoadResult(
                records={},
                event_ids=(),
                integrity_status="corrupt",
                error=str(exc),
                events_by_id={},
            )

        records: dict[str, ConfirmationRecord] = {}
        event_ids: list[str] = []
        events_by_id: dict[str, ConfirmationEvent] = {}
        lines = content.splitlines(keepends=True)
        integrity_status = "ok"
        error = ""
        for index, raw_line in enumerate(lines):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line.decode("utf-8"))
                event = ConfirmationEvent.from_dict(payload)
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                is_unterminated_tail = index == len(lines) - 1 and not raw_line.endswith(
                    (b"\n", b"\r")
                )
                if is_unterminated_tail:
                    integrity_status = "truncated_tail"
                    error = str(exc)
                    break
                return StoreLoadResult(
                    records={},
                    event_ids=(),
                    integrity_status="corrupt",
                    error=f"invalid event at line {index + 1}: {exc}",
                    events_by_id={},
                )

            prior_event = events_by_id.get(event.event_id)
            if prior_event is not None:
                if prior_event != event:
                    return StoreLoadResult(
                        records={},
                        event_ids=(),
                        integrity_status="corrupt",
                        error=f"conflicting event_id {event.event_id}",
                        events_by_id={},
                    )
                continue
            if event.session_id != self.session_id:
                return StoreLoadResult(
                    records={},
                    event_ids=(),
                    integrity_status="corrupt",
                    error=f"event {event.event_id} belongs to another session",
                    events_by_id={},
                )
            prior_record = records.get(event.confirmation_id)
            expected_version = 1 if prior_record is None else prior_record.version + 1
            if event.version != expected_version:
                return StoreLoadResult(
                    records={},
                    event_ids=(),
                    integrity_status="corrupt",
                    error=f"invalid version for event {event.event_id}",
                    events_by_id={},
                )
            records[event.confirmation_id] = event.record
            event_ids.append(event.event_id)
            events_by_id[event.event_id] = event

        return StoreLoadResult(
            records=records,
            event_ids=tuple(event_ids),
            integrity_status=integrity_status,
            error=error,
            events_by_id=events_by_id,
        )

    def _write_snapshot(self, result: StoreLoadResult) -> None:
        payload = {
            "schema_version": 1,
            "session_id": self.session_id,
            "integrity_status": result.integrity_status,
            "error": result.error,
            "event_ids": list(result.event_ids),
            "records": {
                key: record.to_dict()
                for key, record in sorted(result.records.items())
            },
        }
        temp_path = self.snapshot_path.with_suffix(".json.tmp")
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            with temp_path.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                self._sync_file(handle.fileno())
            os.replace(temp_path, self.snapshot_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
