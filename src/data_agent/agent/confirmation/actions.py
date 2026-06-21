"""Typed and idempotent confirmation resolution actions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
import threading
from typing import Any, Callable, Mapping


class UnknownResolutionAction(KeyError):
    pass


class InvalidResolutionAnswer(ValueError):
    pass


class ResolutionConflict(RuntimeError):
    pass


class ResolutionActionFailed(RuntimeError):
    def __init__(self, receipt: "ResolutionReceipt") -> None:
        self.receipt = receipt
        super().__init__(receipt.error)


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _frozen_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True)
class ResolutionContext:
    session_id: str
    confirmation_id: str
    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _required(self.session_id, "session_id"))
        object.__setattr__(
            self,
            "confirmation_id",
            _required(self.confirmation_id, "confirmation_id"),
        )
        object.__setattr__(self, "parameters", _frozen_mapping(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "confirmation_id": self.confirmation_id,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True)
class ResolutionReceipt:
    resolution_id: str
    request_fingerprint: str
    action_name: str
    status: str
    output: Mapping[str, Any]
    error: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "resolution_id", _required(self.resolution_id, "resolution_id"))
        object.__setattr__(
            self,
            "request_fingerprint",
            _required(self.request_fingerprint, "request_fingerprint"),
        )
        object.__setattr__(self, "action_name", _required(self.action_name, "action_name"))
        if self.status not in {"succeeded", "failed"}:
            raise ValueError("receipt status must be succeeded or failed")
        object.__setattr__(self, "output", _frozen_mapping(self.output))
        object.__setattr__(self, "error", str(self.error or ""))


class InMemoryResolutionReceiptRepository:
    def __init__(self) -> None:
        self._receipts: dict[str, ResolutionReceipt] = {}
        self._lock = threading.RLock()

    def get(self, resolution_id: str) -> ResolutionReceipt | None:
        with self._lock:
            return self._receipts.get(resolution_id)

    def save(self, receipt: ResolutionReceipt) -> None:
        with self._lock:
            current = self._receipts.get(receipt.resolution_id)
            if current is not None and current != receipt:
                raise ResolutionConflict(
                    f"resolution_id {receipt.resolution_id} already has another receipt"
                )
            self._receipts[receipt.resolution_id] = receipt


Handler = Callable[[ResolutionContext, Any], Mapping[str, Any]]
Validator = Callable[[ResolutionContext, Any], bool]


class ResolutionActionRegistry:
    def __init__(
        self,
        receipts: InMemoryResolutionReceiptRepository | None = None,
    ) -> None:
        self._handlers: dict[str, tuple[Handler, Validator | None]] = {}
        self._receipts = receipts or InMemoryResolutionReceiptRepository()
        self._lock = threading.RLock()

    def register(
        self,
        action_name: str,
        handler: Handler,
        *,
        validator: Validator | None = None,
    ) -> None:
        name = _required(action_name, "action_name")
        with self._lock:
            if name in self._handlers:
                raise ValueError(f"action {name} is already registered")
            self._handlers[name] = (handler, validator)

    def apply(
        self,
        action_name: str,
        context: ResolutionContext,
        answer: Any,
        resolution_id: str,
    ) -> ResolutionReceipt:
        name = _required(action_name, "action_name")
        resolution_key = _required(resolution_id, "resolution_id")
        fingerprint = _fingerprint(name, context, answer)
        with self._lock:
            prior = self._receipts.get(resolution_key)
            if prior is not None:
                if prior.request_fingerprint != fingerprint:
                    raise ResolutionConflict(
                        f"resolution_id {resolution_key} cannot be reused"
                    )
                if prior.status == "failed":
                    raise ResolutionActionFailed(prior)
                return prior

            registered = self._handlers.get(name)
            if registered is None:
                raise UnknownResolutionAction(name)
            handler, validator = registered
            if validator is not None and not validator(context, answer):
                raise InvalidResolutionAnswer(
                    f"answer is invalid for action {name}"
                )
            try:
                output = handler(context, answer)
                if not isinstance(output, Mapping):
                    raise TypeError("resolution action output must be an object")
            except Exception as exc:
                receipt = ResolutionReceipt(
                    resolution_id=resolution_key,
                    request_fingerprint=fingerprint,
                    action_name=name,
                    status="failed",
                    output={},
                    error=f"{type(exc).__name__}: {exc}",
                )
                self._receipts.save(receipt)
                raise ResolutionActionFailed(receipt) from exc

            receipt = ResolutionReceipt(
                resolution_id=resolution_key,
                request_fingerprint=fingerprint,
                action_name=name,
                status="succeeded",
                output=output,
            )
            self._receipts.save(receipt)
            return receipt


def _fingerprint(
    action_name: str,
    context: ResolutionContext,
    answer: Any,
) -> str:
    encoded = json.dumps(
        {
            "action_name": action_name,
            "context": context.to_dict(),
            "answer": answer,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
