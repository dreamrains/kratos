"""Single transition authority for durable confirmation lifecycles."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Callable
from uuid import uuid4

from data_agent.agent.confirmation.actions import (
    ResolutionActionRegistry,
    ResolutionContext,
)
from data_agent.agent.confirmation.models import (
    AnswerMode,
    ConfirmationEvent,
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationStatus,
    FREE_TEXT_ANSWER_ACTIONS,
    QuestionCandidate,
)
from data_agent.agent.confirmation.policy import (
    QuestionPolicy,
    RequestDisposition,
)
from data_agent.agent.confirmation.store import ConfirmationStore
from data_agent.agent.confirmation_policy import is_obsolete_confirmation_record


class InvalidConfirmationTransition(RuntimeError):
    """Raised when an operation is not valid for the current state."""


class ConfirmationVersionConflict(RuntimeError):
    """Raised when a caller attempts to mutate a stale record version."""


class ConfirmationAnswerError(ValueError):
    """Raised when an answer does not satisfy the request contract."""


class SkipNotAllowed(InvalidConfirmationTransition):
    """Raised when a non-skippable confirmation is skipped."""


class ConfirmationResolutionFailed(RuntimeError):
    def __init__(self, record: ConfirmationRecord) -> None:
        self.record = record
        super().__init__(record.failure_reason or "confirmation resolution failed")


@dataclass(frozen=True)
class ServiceRequestResult:
    disposition: RequestDisposition
    reason: str
    record: ConfirmationRecord | None = None
    reused_confirmation_id: str = ""


_LOCKS_GUARD = threading.Lock()
_SESSION_LOCKS: dict[str, threading.RLock] = {}


def _session_lock(root: Path, session_id: str) -> threading.RLock:
    key = f"{root.resolve()}::{session_id}".casefold()
    with _LOCKS_GUARD:
        return _SESSION_LOCKS.setdefault(key, threading.RLock())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ConfirmationService:
    """Own all confirmation state changes and their durable event writes."""

    def __init__(
        self,
        sessions_root: Path,
        *,
        action_registry: ResolutionActionRegistry,
        policy: QuestionPolicy | None = None,
        clock: Callable[[], str] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.sessions_root = Path(sessions_root)
        self.action_registry = action_registry
        self.policy = policy or QuestionPolicy()
        self.clock = clock or _utc_now
        self.id_factory = id_factory or (lambda prefix: f"{prefix}_{uuid4().hex}")

    def request(self, candidate: QuestionCandidate) -> ServiceRequestResult:
        with _session_lock(self.sessions_root, candidate.session_id):
            if is_obsolete_confirmation_record(candidate):
                return ServiceRequestResult(
                    disposition=RequestDisposition.REJECTED,
                    reason="The confirmation belongs to a retired workflow.",
                )
            store = self._store(candidate.session_id)
            records = store.load_records()
            candidate = self._replace_obsolete_collision_id(candidate, records)
            current_records = tuple(
                record for record in records.values()
                if not is_obsolete_confirmation_record(record)
            )
            policy_result = self.policy.evaluate(candidate, existing=current_records)
            if policy_result.disposition != RequestDisposition.CONFIRMATION:
                return ServiceRequestResult(
                    disposition=policy_result.disposition,
                    reason=policy_result.reason,
                    reused_confirmation_id=policy_result.reused_confirmation_id,
                )

            existing = records.get(candidate.confirmation_id)
            if existing is not None:
                request_payload = policy_result.request.to_dict()
                existing_payload = existing.to_dict()
                if any(
                    existing_payload[key] != value
                    for key, value in request_payload.items()
                ):
                    raise ConfirmationVersionConflict(
                        "confirmation_id already belongs to a different request"
                    )
                return ServiceRequestResult(
                    disposition=RequestDisposition.CONFIRMATION,
                    reason="The confirmation already exists.",
                    record=existing,
                )

            matching_open = next(
                (
                    record
                    for record in current_records
                    if record.decision_key == candidate.decision_key
                    and record.data_version == candidate.data_version
                    and record.spec_version == candidate.spec_version
                    and record.status
                    not in {
                        ConfirmationStatus.RESOLVED,
                        ConfirmationStatus.SKIPPED,
                        ConfirmationStatus.CANCELLED,
                        ConfirmationStatus.EXPIRED,
                    }
                ),
                None,
            )
            if matching_open is not None:
                return ServiceRequestResult(
                    disposition=RequestDisposition.CONFIRMATION,
                    reason="A matching confirmation is already open.",
                    record=matching_open,
                )

            now = self.clock()
            record = ConfirmationRecord.from_request(policy_result.request, now=now)
            store.append(
                ConfirmationEvent.requested(
                    record,
                    event_id=self.id_factory("event"),
                )
            )
            return ServiceRequestResult(
                disposition=RequestDisposition.CONFIRMATION,
                reason=policy_result.reason,
                record=record,
            )

    @staticmethod
    def _replace_obsolete_collision_id(
        candidate: QuestionCandidate,
        records: dict[str, ConfirmationRecord],
    ) -> QuestionCandidate:
        occupied = records.get(candidate.confirmation_id)
        if occupied is None or not is_obsolete_confirmation_record(occupied):
            return candidate

        encoded = json.dumps(
            ConfirmationRequest.from_candidate(candidate).to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        base_id = f"{candidate.confirmation_id}_r{hashlib.sha256(encoded).hexdigest()[:10]}"
        replacement_id = base_id
        suffix = 2
        while True:
            replacement = replace(candidate, confirmation_id=replacement_id)
            existing = records.get(replacement_id)
            if existing is None:
                return replacement
            request_payload = ConfirmationRequest.from_candidate(replacement).to_dict()
            existing_payload = existing.to_dict()
            if (
                not is_obsolete_confirmation_record(existing)
                and all(existing_payload[key] == value for key, value in request_payload.items())
            ):
                return replacement
            replacement_id = f"{base_id}_{suffix}"
            suffix += 1

    def checkpoint(self, session_id: str) -> ConfirmationRecord | None:
        with _session_lock(self.sessions_root, session_id):
            store = self._store(session_id)
            records = store.load_records()
            for record in records.values():
                if is_obsolete_confirmation_record(record):
                    continue
                if record.status == ConfirmationStatus.SUSPENDED:
                    return record
            for record in records.values():
                if is_obsolete_confirmation_record(record):
                    continue
                if record.status in {
                    ConfirmationStatus.RESPONSE_RECEIVED,
                    ConfirmationStatus.APPLYING,
                    ConfirmationStatus.FAILED,
                }:
                    return record
            for record in records.values():
                if is_obsolete_confirmation_record(record):
                    continue
                if record.status == ConfirmationStatus.PENDING:
                    return self._transition(
                        store,
                        record,
                        ConfirmationStatus.SUSPENDED,
                        "suspended",
                        suspension_id=self.id_factory("suspension"),
                    )
            return None

    def get(self, session_id: str, confirmation_id: str) -> ConfirmationRecord:
        record = self._store(session_id).load_records().get(confirmation_id)
        if record is None:
            raise KeyError(confirmation_id)
        return record

    def restore(self, session_id: str) -> ConfirmationRecord | None:
        records = self._store(session_id).load_records()
        return next(
            (
                record
                for record in records.values()
                if record.status == ConfirmationStatus.SUSPENDED
                and not is_obsolete_confirmation_record(record)
            ),
            None,
        )

    def respond(
        self,
        session_id: str,
        confirmation_id: str,
        answer: Any,
        expected_version: int,
        idempotency_key: str,
    ) -> ConfirmationRecord:
        with _session_lock(self.sessions_root, session_id):
            store = self._store(session_id)
            record = self._record(store, confirmation_id)
            self._expect_actionable_user_record(record, "answer")
            response_id = self._idempotency_key(idempotency_key)

            if record.status == ConfirmationStatus.RESOLVED:
                normalized_answer = self._validate_answer(record, answer)
                if record.response_id == response_id and record.response == normalized_answer:
                    return record
                raise ConfirmationVersionConflict("the confirmation was already resolved")
            self._expect_version(record, expected_version)
            if record.status != ConfirmationStatus.SUSPENDED:
                raise InvalidConfirmationTransition(
                    f"cannot answer a {record.status.value} confirmation"
                )
            normalized_answer = self._validate_answer(record, answer)

            received = self._transition(
                store,
                record,
                ConfirmationStatus.RESPONSE_RECEIVED,
                "response_received",
                response=normalized_answer,
                response_id=response_id,
            )
            applying = self._transition(
                store,
                received,
                ConfirmationStatus.APPLYING,
                "applying",
            )
            try:
                self.action_registry.apply(
                    applying.resolution_action,
                    ResolutionContext(
                        session_id=session_id,
                        confirmation_id=confirmation_id,
                        parameters=applying.resolution_params,
                    ),
                    normalized_answer,
                    f"{confirmation_id}:{response_id}",
                )
            except Exception as exc:
                failed = self._transition(
                    store,
                    applying,
                    ConfirmationStatus.FAILED,
                    "failed",
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
                raise ConfirmationResolutionFailed(failed) from exc
            return self._transition(
                store,
                applying,
                ConfirmationStatus.RESOLVED,
                "resolved",
            )

    def skip(
        self,
        session_id: str,
        confirmation_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> ConfirmationRecord:
        with _session_lock(self.sessions_root, session_id):
            store = self._store(session_id)
            record = self._record(store, confirmation_id)
            self._expect_actionable_user_record(record, "skip")
            response_id = self._idempotency_key(idempotency_key)
            if (
                record.status == ConfirmationStatus.SKIPPED
                and record.response_id == response_id
            ):
                return record
            self._expect_version(record, expected_version)
            self._expect_open(record, "skip")
            if not record.skippable:
                raise SkipNotAllowed("this confirmation cannot be skipped")
            return self._transition(
                store,
                record,
                ConfirmationStatus.SKIPPED,
                "skipped",
                response="skipped",
                response_id=response_id,
            )

    def cancel(
        self,
        session_id: str,
        confirmation_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> ConfirmationRecord:
        with _session_lock(self.sessions_root, session_id):
            store = self._store(session_id)
            record = self._record(store, confirmation_id)
            self._expect_actionable_user_record(record, "cancel")
            response_id = self._idempotency_key(idempotency_key)
            if (
                record.status == ConfirmationStatus.CANCELLED
                and record.response_id == response_id
            ):
                return record
            self._expect_version(record, expected_version)
            self._expect_open(record, "cancel")
            return self._transition(
                store,
                record,
                ConfirmationStatus.CANCELLED,
                "cancelled",
                response="cancelled",
                response_id=response_id,
            )

    def expire(
        self,
        session_id: str,
        confirmation_id: str,
        expected_version: int,
        reason: str,
    ) -> ConfirmationRecord:
        # Expire is an internal archival primitive, so it may retire obsolete records.
        with _session_lock(self.sessions_root, session_id):
            store = self._store(session_id)
            record = self._record(store, confirmation_id)
            self._expect_version(record, expected_version)
            self._expect_open(record, "expire")
            return self._transition(
                store,
                record,
                ConfirmationStatus.EXPIRED,
                "expired",
                failure_reason=str(reason or "").strip(),
            )

    def _store(self, session_id: str) -> ConfirmationStore:
        return ConfirmationStore(self.sessions_root, session_id)

    @staticmethod
    def _record(store: ConfirmationStore, confirmation_id: str) -> ConfirmationRecord:
        record = store.load_records().get(confirmation_id)
        if record is None:
            raise KeyError(confirmation_id)
        return record

    @staticmethod
    def _expect_version(record: ConfirmationRecord, expected_version: int) -> None:
        if record.version != expected_version:
            raise ConfirmationVersionConflict(
                f"expected version {expected_version}, current version is {record.version}"
            )

    @staticmethod
    def _expect_open(record: ConfirmationRecord, operation: str) -> None:
        if record.status not in {ConfirmationStatus.PENDING, ConfirmationStatus.SUSPENDED}:
            raise InvalidConfirmationTransition(
                f"cannot {operation} a {record.status.value} confirmation"
            )

    @staticmethod
    def _expect_actionable_user_record(
        record: ConfirmationRecord,
        operation: str,
    ) -> None:
        if is_obsolete_confirmation_record(record):
            raise InvalidConfirmationTransition(
                f"cannot {operation} an obsolete confirmation"
            )

    @staticmethod
    def _idempotency_key(value: str) -> str:
        key = str(value or "").strip()
        if not key:
            raise ConfirmationAnswerError("idempotency_key is required")
        return key

    @staticmethod
    def _validate_answer(record: ConfirmationRecord, answer: Any) -> Any:
        values = {option.value for option in record.options}
        if record.answer_mode == AnswerMode.SINGLE_SELECT:
            if isinstance(answer, str) and answer in values:
                return answer
            # Record-only confirmations (e.g. ask_user_question) accept a custom
            # free-text answer, matching the CLI / web "type your own answer"
            # affordance. State-driving actions stay strict (see
            # FREE_TEXT_ANSWER_ACTIONS).
            if (
                record.resolution_action in FREE_TEXT_ANSWER_ACTIONS
                and isinstance(answer, str)
                and answer.strip()
            ):
                return answer.strip()
            raise ConfirmationAnswerError("answer must match one available option")
        if record.answer_mode == AnswerMode.MULTI_SELECT:
            if not isinstance(answer, (list, tuple)) or not answer:
                raise ConfirmationAnswerError("answer must select one or more options")
            normalized = [str(value).strip() for value in answer if str(value).strip()]
            if not normalized:
                raise ConfirmationAnswerError("answer must select one or more options")
            if len(set(normalized)) != len(normalized):
                raise ConfirmationAnswerError("answer contains duplicate options")
            # Record-only confirmations accept free-text entries alongside
            # option values (parity with single-select + CLI). State-driving
            # actions stay strict because they key off specific option values.
            if (
                record.resolution_action not in FREE_TEXT_ANSWER_ACTIONS
                and any(value not in values for value in normalized)
            ):
                raise ConfirmationAnswerError("answer contains invalid options")
            return normalized
        if not isinstance(answer, str) or not answer.strip():
            raise ConfirmationAnswerError("answer must contain text")
        return answer.strip()

    def _transition(
        self,
        store: ConfirmationStore,
        record: ConfirmationRecord,
        status: ConfirmationStatus,
        event_type: str,
        **changes: Any,
    ) -> ConfirmationRecord:
        updated = replace(
            record,
            status=status,
            version=record.version + 1,
            updated_at=self.clock(),
            **changes,
        )
        store.append(
            ConfirmationEvent(
                event_id=self.id_factory("event"),
                confirmation_id=updated.confirmation_id,
                session_id=updated.session_id,
                event_type=event_type,
                version=updated.version,
                occurred_at=updated.updated_at,
                record=updated,
            )
        )
        return updated
