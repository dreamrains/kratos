"""Fail-closed Provider call guard for authorization-bounded acceptance runs.

This module is deliberately acceptance-only.  Product runtime may choose to
degrade after an optional auxiliary LLM failure, but a frozen real-Provider
journey must stop contacting the Provider after its first failed request.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Mapping

from data_agent.llm.request_policy import close_stream


NETWORK_EXECUTION_ACK_ENV = "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED"


class ProviderJourneyHalted(RuntimeError):
    """A frozen journey has reached a terminal condition."""
    error_domain = "acceptance"


class ProviderPolicyViolation(ProviderJourneyHalted):
    """A request falls outside the frozen Provider policy."""


class ProviderFailureLatch:
    """Remember the first terminal failure for all logical call paths."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failure: dict[str, Any] | None = None

    @property
    def failure_code(self) -> str:
        with self._lock:
            return str((self._failure or {}).get("code") or "")

    def trip(self, code: str, **details: Any) -> dict[str, Any]:
        with self._lock:
            if self._failure is None:
                self._failure = {
                    "code": str(code),
                    "failed_at": _utc_now(),
                    **{key: value for key, value in details.items() if value not in (None, "")},
                }
            return dict(self._failure)

    def snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._failure) if self._failure is not None else None


def require_network_enabled_execution(environment: Mapping[str, str] | None = None) -> None:
    """Require an explicit executor acknowledgement before a real-Provider run.

    This is intentionally not a network probe: an undeclared probe would be an
    extra external request outside the frozen browser journey.  The executor
    must set the marker only when it has launched the process through a
    network-enabled, user-approved execution path.
    """

    env = os.environ if environment is None else environment
    if str(env.get(NETWORK_EXECUTION_ACK_ENV, "")).strip() != "1":
        raise ProviderPolicyViolation("network_enabled_execution_not_acknowledged")


class StrictProviderCallGuard:
    """Count Provider attempts and permanently close after the first failure."""

    def __init__(
        self,
        *,
        completion: Callable[..., Any],
        receipt_path: Path,
        candidate_id: str,
        source_digest: str,
        call_cap: int,
        expected_model: str,
        allowed_max_tokens: set[int] | list[int] | tuple[int, ...],
        temperature: float,
        timeout_seconds: int,
        retry_backoff_seconds: float = 20.0,
    ) -> None:
        if int(call_cap) < 1:
            raise ValueError("call_cap must be positive")
        self._completion = completion
        self._receipt_path = Path(receipt_path)
        self._candidate_id = str(candidate_id)
        self._source_digest = str(source_digest)
        self._call_cap = int(call_cap)
        self._expected_model = str(expected_model)
        self._allowed_max_tokens = {int(value) for value in allowed_max_tokens}
        self._temperature = float(temperature)
        self._timeout_seconds = int(timeout_seconds)
        self._retry_backoff_seconds = float(retry_backoff_seconds)
        self._lock = threading.Lock()
        self._latch = ProviderFailureLatch()
        self._records: list[dict[str, Any]] = []
        self._blocked_attempts = 0
        self._streams: dict[int, _CountedStream] = {}

    @property
    def calls_started(self) -> int:
        with self._lock:
            return len(self._records)

    @property
    def terminal_failure(self) -> dict[str, Any] | None:
        return self._latch.snapshot()

    def persist_receipt(self) -> None:
        """Persist even a zero-call run so process teardown can be audited."""
        with self._lock:
            self._write_receipt_locked()

    def close(self, timeout_seconds: float = 2.0) -> bool:
        """Stop admissions, close owned streams, and prove local quiescence.

        A stuck transport remains unknown; process exit must not rewrite it as
        completed. Remote generation/billing cannot be inferred from close().
        """
        with self._lock:
            self._latch.trip("acceptance_server_closed")
            streams = list(self._streams.values())
            self._write_receipt_locked()
        for stream in streams:
            stream.close()
        with self._lock:
            if all(r.get("local_request_stopped") for r in self._records):
                return True
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            with self._lock:
                if all(r.get("local_request_stopped") for r in self._records):
                    return True
            time.sleep(0.01)
        with self._lock:
            for record in self._records:
                if record["status"] == "started":
                    record.update(status="unknown", finished_at=_utc_now(), local_request_stopped=False)
            self._write_receipt_locked()
        return False

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": 3,
            "candidate_id": self._candidate_id,
            "source_digest": self._source_digest,
            "call_cap": self._call_cap,
            "calls": self._records,
            "blocked_attempts": self._blocked_attempts,
            "terminal_failure": self._latch.snapshot(),
        }

    def _write_receipt_locked(self) -> None:
        self._receipt_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._receipt_path.with_suffix(f"{self._receipt_path.suffix}.tmp")
        temporary.write_text(
            json.dumps(self._payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        from data_agent.utils.atomic_files import replace_file
        replace_file(temporary, self._receipt_path)

    def _trip_without_provider(self, code: str, exception_type: type[ProviderJourneyHalted], **details: Any) -> None:
        self._latch.trip(code, **details)
        with self._lock:
            self._blocked_attempts += 1
            self._write_receipt_locked()
        raise exception_type(code)

    def _start(self, kwargs: dict[str, Any], retry_of: int | None = None) -> dict[str, Any]:
        failure = self._latch.snapshot()
        if failure is not None:
            with self._lock:
                self._blocked_attempts += 1
                self._write_receipt_locked()
            raise ProviderJourneyHalted(str(failure["code"]))

        model = str(kwargs.get("model") or "")
        max_tokens = int(kwargs.get("max_tokens") or 0)
        if model != self._expected_model:
            self._trip_without_provider(
                "provider_model_change_forbidden",
                ProviderPolicyViolation,
                observed_model=model,
            )
        if max_tokens not in self._allowed_max_tokens:
            self._trip_without_provider(
                "provider_max_tokens_outside_authorization",
                ProviderPolicyViolation,
                observed_max_tokens=max_tokens,
            )

        with self._lock:
            # Re-check under the receipt lock so a failure recorded by another
            # logical path cannot race with this call's admission.
            failure = self._latch.snapshot()
            if failure is not None:
                self._blocked_attempts += 1
                self._write_receipt_locked()
                raise ProviderJourneyHalted(str(failure["code"]))
            active = next((item for item in self._records if item["status"] == "started"), None)
            if active is not None:
                self._latch.trip(
                    "provider_concurrent_call_forbidden",
                    active_ordinal=active["ordinal"],
                )
                self._blocked_attempts += 1
                self._write_receipt_locked()
                raise ProviderJourneyHalted("provider_concurrent_call_forbidden")
            if len(self._records) >= self._call_cap:
                self._latch.trip("provider_call_cap_exceeded")
                self._blocked_attempts += 1
                self._write_receipt_locked()
                raise ProviderJourneyHalted("provider_call_cap_exceeded")
            record = {
                "ordinal": len(self._records) + 1,
                "model": model,
                "stream": bool(kwargs.get("stream")),
                "max_tokens": max_tokens,
                "status": "started",
                "started_at": _utc_now(),
                "local_request_stopped": False,
                "remote_billing": "unknown",
            }
            if retry_of is not None:
                record["retry_of"] = int(retry_of)
            self._records.append(record)
            self._write_receipt_locked()
            return record

    def _finish(self, record: dict[str, Any], status: str, error: BaseException | None = None,
                *, trip_latch: bool = True) -> None:
        with self._lock:
            if record["status"] != "started":
                return
            record["status"] = status
            record["finished_at"] = _utc_now()
            record["local_request_stopped"] = status != "unknown"
            record["response_received"] = status == "completed"
            record["completion_semantics"] = "transport_exhausted" if record["stream"] else "response_returned"
            if status in {"cancelled", "unknown"}:
                self._latch.trip("provider_request_" + status, ordinal=record["ordinal"])
            if error is not None:
                from scripts.acceptance.provider_error_taxonomy import (
                    classify_provider_error, error_evidence,
                )
                record["error_type"] = type(error).__name__
                error_class = classify_provider_error(error)
                record["error_class"] = error_class
                record.update(error_evidence(error))
                if trip_latch:
                    self._latch.trip(
                        "provider_request_failed",
                        ordinal=record["ordinal"],
                        error_type=type(error).__name__,
                        error_class=error_class,
                    )
            self._write_receipt_locked()

    def completion(self, **kwargs: Any) -> Any:
        from scripts.acceptance.provider_error_taxonomy import (
            RETRYABLE_ERROR_CLASSES, classify_provider_error,
        )
        guarded_kwargs = dict(kwargs)
        guarded_kwargs["num_retries"] = 0
        guarded_kwargs["temperature"] = self._temperature
        guarded_kwargs["timeout"] = self._timeout_seconds
        record = self._start(guarded_kwargs)
        try:
            response = self._completion(**guarded_kwargs)
        except BaseException as exc:
            error_class = classify_provider_error(exc)
            retryable = (
                error_class in RETRYABLE_ERROR_CLASSES
                and self.calls_started < self._call_cap
                and self._latch.snapshot() is None
            )
            self._finish(record, "failed", exc, trip_latch=not retryable)
            if not retryable:
                raise
            time.sleep(self._retry_backoff_seconds)
            retry_record = self._start(guarded_kwargs, retry_of=record["ordinal"])
            try:
                response = self._completion(**guarded_kwargs)
            except BaseException as exc2:
                self._finish(retry_record, "failed", exc2)
                raise
            self._finish(retry_record, "completed")
            return self._dispatch_response(guarded_kwargs, retry_record, response)
        if not guarded_kwargs.get("stream"):
            self._finish(record, "completed")
        return self._dispatch_response(guarded_kwargs, record, response)

    def _dispatch_response(self, guarded_kwargs: dict[str, Any], record: dict[str, Any], response: Any) -> Any:
        if not guarded_kwargs.get("stream"):
            return response
        stream = _CountedStream(self, record, response)
        with self._lock:
            self._streams[record["ordinal"]] = stream
            shutdown = self._latch.snapshot() is not None
        if shutdown:
            stream.close()
        return stream


class _CountedStream:
    """Own the provider iterator, including close-before-first-next()."""

    def __init__(self, guard, record, response):
        self.guard, self.record, self.response = guard, record, response
        self.iterator = iter(response)
        self._reading = threading.Lock()
        self._cancelled = threading.Event()
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self):
        with self._reading:
            if self._closed or self._cancelled.is_set():
                raise StopIteration
            try:
                item = next(self.iterator)
            except StopIteration:
                self._closed = True
                self.guard._finish(self.record, "completed")
                raise
            except BaseException as exc:
                self._closed = True
                try:
                    close_stream(self.response)
                except BaseException:
                    self.guard._finish(self.record, "unknown", exc)
                else:
                    self.guard._finish(self.record, "cancelled" if self._cancelled.is_set() else "failed", exc)
                raise
            if self._cancelled.is_set():
                self._finish_close()
                raise StopIteration
            return item

    def _finish_close(self):
        try:
            proven = close_stream(self.response)
        except BaseException:
            proven = False
        self._closed = True
        self.guard._finish(self.record, "cancelled" if proven else "unknown")
        return proven

    def close(self):
        self._cancelled.set()
        if self._closed:
            return bool(self.record.get("local_request_stopped"))
        if self._reading.acquire(blocking=False):
            try:
                return self._finish_close()
            finally:
                self._reading.release()
        # A reader still owns next(). Close its transport, but leave the record
        # in flight until the reader exits. guard.close() bounds that wait.
        try:
            close_stream(self.response)
        except BaseException:
            pass
        return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
