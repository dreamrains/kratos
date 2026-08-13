from __future__ import annotations

import hashlib
import threading
from dataclasses import asdict, dataclass
from typing import Iterable, Iterator

from data_agent.v2.models import EventType, ExecutionEvent, OutcomeStatus
from data_agent.v2.projection import project_run
from data_agent.v2.slice1 import RuntimeEvent
from data_agent.v2.store import TurnPublicationBlocked, V2FactStore
from data_agent.v2.steer import SteerRecord, SteerStatus, SteerStore


class StopRequestConflict(RuntimeError):
    """The requested run is not in a state where stop can win."""


@dataclass(frozen=True, slots=True)
class StopReceipt:
    status: str
    session_id: str
    turn_id: str
    run_id: str
    commitment_ids: tuple[str, ...]


class ActiveRun:
    """Process-local signal paired with durable V2 interruption facts."""

    def __init__(
        self,
        *,
        store: V2FactStore,
        steer_store: SteerStore,
        session_id: str,
        turn_id: str,
        request_context: dict[str, str],
        resume_payload: dict,
    ) -> None:
        self.store = store
        self.steer_store = steer_store
        self.session_id = session_id
        self.turn_id = turn_id
        self.request_context = dict(request_context)
        self.resume_payload = dict(resume_payload)
        self.run_id = ""
        self.commitment_ids: tuple[str, ...] = ()
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._steer_notifications: list[str] = []

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def _wait_for_durable_stop(self, timeout: float = 5.0) -> bool:
        if self.stop_requested:
            return True
        control = self.store.read_turn_control(self.turn_id)
        if control.get("status") not in {"stop_requested", "interrupted"}:
            return False
        return self._stop.wait(timeout=timeout)

    def _observe(self, event: RuntimeEvent) -> None:
        if event.event == "turn_started":
            self.run_id = str(event.data.get("run_id") or "").strip()
        elif event.event == "commitment_snapshot":
            self.commitment_ids = tuple(
                str(item.get("commitment_id") or "").strip()
                for item in event.data.get("commitments") or ()
                if str(item.get("commitment_id") or "").strip()
            )

    def request_stop(self) -> StopReceipt:
        with self._lock:
            if not self.run_id or not self.commitment_ids:
                raise StopRequestConflict("run has not reached a stoppable boundary")
            reservation = self.store.request_turn_interrupt(self.turn_id, self.run_id)
            if reservation in {"completed", "failed"}:
                raise StopRequestConflict(f"run is already {reservation}")
            self.steer_store.supersede_for_run(
                self.run_id, reason="source_run_interrupted"
            )
            commitments = {
                item.commitment_id: item
                for item in self.store.read_commitments(run_id=self.run_id)
            }
            for commitment_id in self.commitment_ids:
                commitment = commitments.get(commitment_id)
                if commitment is None:
                    raise StopRequestConflict(
                        f"active commitment is not durable: {commitment_id}"
                    )
                identity = hashlib.sha256(
                    f"{self.run_id}:{commitment_id}:user_interrupted".encode("utf-8")
                ).hexdigest()[:24]
                self.store.append_event(
                    ExecutionEvent(
                        event_id=f"event_interrupt_{identity}",
                        run_id=self.run_id,
                        commitment_id=commitment_id,
                        event_type=EventType.USER_INTERRUPTED,
                        tool_call_id=f"control_{identity}",
                        tool_name="v2.run_control",
                        capability="control.interrupt",
                        dataset_version_ids=commitment.dataset_version_ids,
                        result_ref=f"turn:{self.turn_id}:interrupted",
                        message="user requested stop",
                    )
                )
            self.store.write_turn_blocks(
                self.turn_id,
                [],
                status="interrupted",
                request_context=self.request_context,
            )
            self._stop.set()
            return StopReceipt(
                status="interrupted",
                session_id=self.session_id,
                turn_id=self.turn_id,
                run_id=self.run_id,
                commitment_ids=self.commitment_ids,
            )

    def request_steer(
        self,
        *,
        expected_run_id: str,
        client_request_id: str,
        message: str,
    ) -> SteerRecord:
        with self._lock:
            if not self.run_id or expected_run_id != self.run_id:
                raise StopRequestConflict("steer expected_run_id is stale")
            if self.stop_requested:
                raise StopRequestConflict("cannot steer an interrupted run")
            record = self.steer_store.enqueue(
                source_turn_id=self.turn_id,
                source_run_id=self.run_id,
                client_request_id=client_request_id,
                message=message,
                resume_payload=self.resume_payload,
            )
            self._steer_notifications.append(record.steer_id)
            return record

    def _drain_steer_events(self) -> Iterator[RuntimeEvent]:
        with self._lock:
            notifications = tuple(self._steer_notifications)
            self._steer_notifications.clear()
        for steer_id in notifications:
            record = self.steer_store.get(steer_id)
            if record.status is not SteerStatus.QUEUED:
                continue
            yield RuntimeEvent(
                "steer_received",
                {
                    "session_id": self.session_id,
                    "turn_id": self.turn_id,
                    "run_id": self.run_id,
                    "steer_id": record.steer_id,
                    "status": record.status.value,
                    "message": record.message,
                },
            )

    def _terminal_events(self) -> Iterator[RuntimeEvent]:
        projection = project_run(*self.store.read_run_facts(self.run_id))
        yield RuntimeEvent(
            "outcome_snapshot",
            {
                "publishable": False,
                "outcomes": {
                    key: asdict(value) for key, value in projection.outcomes.items()
                },
            },
        )
        yield RuntimeEvent(
            "turn_interrupted",
            {
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "run_id": self.run_id,
                "status": OutcomeStatus.INTERRUPTED.value,
            },
        )

    def stream(self, source: Iterable[RuntimeEvent]) -> Iterator[RuntimeEvent]:
        iterator = iter(source)
        try:
            while True:
                yield from self._drain_steer_events()
                if self.stop_requested and self.commitment_ids:
                    yield from self._terminal_events()
                    return
                try:
                    event = next(iterator)
                except StopIteration:
                    return
                except TurnPublicationBlocked:
                    if self._wait_for_durable_stop():
                        yield from self._terminal_events()
                        return
                    raise
                except Exception:
                    if self._wait_for_durable_stop():
                        yield from self._terminal_events()
                        return
                    raise
                self._observe(event)
                if self.stop_requested and self.commitment_ids:
                    yield from self._terminal_events()
                    return
                yield event
        finally:
            close = getattr(iterator, "close", None)
            if self.stop_requested and callable(close):
                close()


class ActiveRunRegistry:
    """Tracks signals only; durable facts remain authoritative."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[tuple[str, str], ActiveRun] = {}

    def register(
        self,
        *,
        store: V2FactStore,
        steer_store: SteerStore | None = None,
        session_id: str,
        turn_id: str,
        request_context: dict[str, str],
        resume_payload: dict | None = None,
    ) -> ActiveRun:
        with self._lock:
            if any(key[0] == session_id for key in self._runs):
                raise StopRequestConflict(
                    f"session {session_id} already has an active run"
                )
            active = ActiveRun(
                store=store,
                steer_store=steer_store or SteerStore.from_v2_root(store.root),
                session_id=session_id,
                turn_id=turn_id,
                request_context=request_context,
                resume_payload=resume_payload or request_context,
            )
            self._runs[(session_id, turn_id)] = active
            return active

    def unregister(self, active: ActiveRun) -> None:
        with self._lock:
            key = (active.session_id, active.turn_id)
            if self._runs.get(key) is active:
                self._runs.pop(key, None)

    def request_stop(self, session_id: str, turn_id: str) -> StopReceipt:
        with self._lock:
            active = self._runs.get((session_id, turn_id))
        if active is None:
            raise StopRequestConflict("run is not active")
        return active.request_stop()

    def request_steer(
        self,
        session_id: str,
        turn_id: str,
        *,
        expected_run_id: str,
        client_request_id: str,
        message: str,
    ) -> SteerRecord:
        with self._lock:
            active = self._runs.get((session_id, turn_id))
        if active is None:
            raise StopRequestConflict("run is not active")
        return active.request_steer(
            expected_run_id=expected_run_id,
            client_request_id=client_request_id,
            message=message,
        )
