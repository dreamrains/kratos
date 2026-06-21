"""Immutable contracts for the confirmation runtime."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class ConfirmationContractError(ValueError):
    """Raised when a confirmation contract is incomplete or unsafe."""


class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    SUSPENDED = "suspended"
    RESPONSE_RECEIVED = "response_received"
    APPLYING = "applying"
    RESOLVED = "resolved"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


class AnswerMode(str, Enum):
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    FREE_TEXT = "free_text"


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ConfirmationContractError(f"{field_name} is required")
    return text


def _tuple_of_text(values: Any, field_name: str) -> tuple[str, ...]:
    result = tuple(str(value).strip() for value in (values or ()) if str(value).strip())
    if not result:
        raise ConfirmationContractError(f"{field_name} is required")
    if len(set(result)) != len(result):
        raise ConfirmationContractError(f"{field_name} values must be unique")
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ConfirmationContractError("resolution_params must be an object")
    return MappingProxyType(dict(value))


def _known_fields(cls, payload: Mapping[str, Any]) -> dict[str, Any]:
    names = {item.name for item in fields(cls)}
    return {key: value for key, value in payload.items() if key in names}


@dataclass(frozen=True)
class ConfirmationOption:
    label: str
    value: str
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _required_text(self.label, "option label"))
        object.__setattr__(self, "value", _required_text(self.value, "option value"))
        object.__setattr__(self, "description", str(self.description or "").strip())

    def to_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "value": self.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConfirmationOption":
        return cls(
            label=payload.get("label", ""),
            value=payload.get("value", ""),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class QuestionCandidate:
    """A producer proposal that policy may accept, reuse, or downgrade."""

    confirmation_id: str
    session_id: str
    turn_id: str
    decision_key: str
    source: str
    operation: str
    question: str
    decision_impact: str
    answer_mode: AnswerMode
    options: tuple[ConfirmationOption, ...]
    blocking_surfaces: tuple[str, ...]
    skippable: bool
    resolution_action: str
    resolution_params: Mapping[str, Any] = field(default_factory=dict)
    data_version: str = ""
    spec_version: str = ""
    safe_default: str = ""

    def __post_init__(self) -> None:
        for name in (
            "confirmation_id",
            "session_id",
            "turn_id",
            "decision_key",
            "source",
            "question",
            "decision_impact",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        mode = self.answer_mode
        if not isinstance(mode, AnswerMode):
            mode = AnswerMode(mode)
        object.__setattr__(self, "answer_mode", mode)
        options = tuple(self.options or ())
        if any(not isinstance(option, ConfirmationOption) for option in options):
            raise ConfirmationContractError("options must contain ConfirmationOption values")
        object.__setattr__(self, "options", options)
        object.__setattr__(
            self,
            "blocking_surfaces",
            tuple(str(value).strip() for value in (self.blocking_surfaces or ()) if str(value).strip()),
        )
        object.__setattr__(self, "operation", str(self.operation or "").strip())
        object.__setattr__(self, "resolution_action", str(self.resolution_action or "").strip())
        object.__setattr__(self, "resolution_params", _mapping(self.resolution_params))
        object.__setattr__(self, "data_version", str(self.data_version or "").strip())
        object.__setattr__(self, "spec_version", str(self.spec_version or "").strip())
        object.__setattr__(self, "safe_default", str(self.safe_default or "").strip())


@dataclass(frozen=True)
class ConfirmationRequest:
    confirmation_id: str
    session_id: str
    turn_id: str
    decision_key: str
    source: str
    operation: str
    question: str
    decision_impact: str
    answer_mode: AnswerMode
    options: tuple[ConfirmationOption, ...]
    blocking_surfaces: tuple[str, ...]
    skippable: bool
    resolution_action: str
    resolution_params: Mapping[str, Any] = field(default_factory=dict)
    data_version: str = ""
    spec_version: str = ""
    safe_default: str = ""

    def __post_init__(self) -> None:
        for name in (
            "confirmation_id",
            "session_id",
            "turn_id",
            "decision_key",
            "source",
            "question",
            "decision_impact",
            "resolution_action",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        object.__setattr__(self, "operation", str(self.operation or "").strip())
        mode = self.answer_mode
        if not isinstance(mode, AnswerMode):
            mode = AnswerMode(mode)
        object.__setattr__(self, "answer_mode", mode)
        options = tuple(self.options or ())
        if any(not isinstance(option, ConfirmationOption) for option in options):
            raise ConfirmationContractError("options must contain ConfirmationOption values")
        option_values = [option.value for option in options]
        if len(set(option_values)) != len(option_values):
            raise ConfirmationContractError("option values must be unique")
        if mode in {AnswerMode.SINGLE_SELECT, AnswerMode.MULTI_SELECT} and not options:
            raise ConfirmationContractError("select answer modes require options")
        if mode == AnswerMode.FREE_TEXT and options:
            raise ConfirmationContractError("free_text answer mode cannot define options")
        object.__setattr__(self, "options", options)
        object.__setattr__(
            self,
            "blocking_surfaces",
            _tuple_of_text(self.blocking_surfaces, "blocking_surfaces"),
        )
        object.__setattr__(self, "resolution_params", _mapping(self.resolution_params))
        object.__setattr__(self, "data_version", str(self.data_version or "").strip())
        object.__setattr__(self, "spec_version", str(self.spec_version or "").strip())
        object.__setattr__(self, "safe_default", str(self.safe_default or "").strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmation_id": self.confirmation_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "decision_key": self.decision_key,
            "source": self.source,
            "operation": self.operation,
            "question": self.question,
            "decision_impact": self.decision_impact,
            "answer_mode": self.answer_mode.value,
            "options": [option.to_dict() for option in self.options],
            "blocking_surfaces": list(self.blocking_surfaces),
            "skippable": self.skippable,
            "resolution_action": self.resolution_action,
            "resolution_params": dict(self.resolution_params),
            "data_version": self.data_version,
            "spec_version": self.spec_version,
            "safe_default": self.safe_default,
        }

    @classmethod
    def from_candidate(cls, candidate: QuestionCandidate) -> "ConfirmationRequest":
        return cls(
            confirmation_id=candidate.confirmation_id,
            session_id=candidate.session_id,
            turn_id=candidate.turn_id,
            decision_key=candidate.decision_key,
            source=candidate.source,
            operation=candidate.operation,
            question=candidate.question,
            decision_impact=candidate.decision_impact,
            answer_mode=candidate.answer_mode,
            options=candidate.options,
            blocking_surfaces=candidate.blocking_surfaces,
            skippable=candidate.skippable,
            resolution_action=candidate.resolution_action,
            resolution_params=candidate.resolution_params,
            data_version=candidate.data_version,
            spec_version=candidate.spec_version,
            safe_default=candidate.safe_default,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConfirmationRequest":
        values = _known_fields(cls, payload)
        values["answer_mode"] = AnswerMode(values.get("answer_mode", ""))
        values["options"] = tuple(
            ConfirmationOption.from_dict(option)
            for option in values.get("options", ())
        )
        values["blocking_surfaces"] = tuple(values.get("blocking_surfaces", ()))
        return cls(**values)


@dataclass(frozen=True)
class ConfirmationRecord(ConfirmationRequest):
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    suspension_id: str = ""
    response: Any = None
    response_id: str = ""
    failure_reason: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        status = self.status
        if not isinstance(status, ConfirmationStatus):
            status = ConfirmationStatus(status)
        object.__setattr__(self, "status", status)
        if int(self.version) < 1:
            raise ConfirmationContractError("version must be at least 1")
        object.__setattr__(self, "version", int(self.version))
        object.__setattr__(self, "created_at", _required_text(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _required_text(self.updated_at, "updated_at"))
        object.__setattr__(self, "suspension_id", str(self.suspension_id or "").strip())
        object.__setattr__(self, "response_id", str(self.response_id or "").strip())
        object.__setattr__(self, "failure_reason", str(self.failure_reason or "").strip())

    @classmethod
    def from_request(cls, request: ConfirmationRequest, *, now: str) -> "ConfirmationRecord":
        request_values = {
            item.name: getattr(request, item.name)
            for item in fields(ConfirmationRequest)
        }
        return cls(
            **request_values,
            status=ConfirmationStatus.PENDING,
            version=1,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload.update({
            "status": self.status.value,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "suspension_id": self.suspension_id,
            "response": self.response,
            "response_id": self.response_id,
            "failure_reason": self.failure_reason,
        })
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConfirmationRecord":
        values = _known_fields(cls, payload)
        values["answer_mode"] = AnswerMode(values.get("answer_mode", ""))
        values["status"] = ConfirmationStatus(values.get("status", ""))
        values["options"] = tuple(
            ConfirmationOption.from_dict(option)
            for option in values.get("options", ())
        )
        values["blocking_surfaces"] = tuple(values.get("blocking_surfaces", ()))
        return cls(**values)


@dataclass(frozen=True)
class ConfirmationEvent:
    event_id: str
    confirmation_id: str
    session_id: str
    event_type: str
    version: int
    occurred_at: str
    record: ConfirmationRecord

    def __post_init__(self) -> None:
        for name in ("event_id", "confirmation_id", "session_id", "event_type", "occurred_at"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if self.record.confirmation_id != self.confirmation_id:
            raise ConfirmationContractError("event confirmation_id must match record")
        if self.record.session_id != self.session_id:
            raise ConfirmationContractError("event session_id must match record")
        if int(self.version) != self.record.version:
            raise ConfirmationContractError("event version must match record")
        object.__setattr__(self, "version", int(self.version))

    @classmethod
    def requested(cls, record: ConfirmationRecord, *, event_id: str) -> "ConfirmationEvent":
        return cls(
            event_id=event_id,
            confirmation_id=record.confirmation_id,
            session_id=record.session_id,
            event_type="requested",
            version=record.version,
            occurred_at=record.updated_at,
            record=record,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "confirmation_id": self.confirmation_id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "version": self.version,
            "occurred_at": self.occurred_at,
            "record": self.record.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConfirmationEvent":
        values = _known_fields(cls, payload)
        values["record"] = ConfirmationRecord.from_dict(values["record"])
        return cls(**values)
