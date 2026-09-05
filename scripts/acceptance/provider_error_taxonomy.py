# scripts/acceptance/provider_error_taxonomy.py
"""Classify real-Provider failures from litellm-style exceptions.

Acceptance-only: turns a bare exception name into a decision-grade error
class so the batch controller can distinguish global-fatal conditions
(quota, credentials) from scenario-level and transient failures.
"""
from __future__ import annotations

GLOBAL_FATAL_CLASSES = frozenset({"quota_exhausted", "credential_invalid"})
RETRYABLE_ERROR_CLASSES = frozenset({"rate_limited", "network_transient", "server_error"})

_QUOTA_TEXT_MARKERS = (
    "insufficient balance", "insufficient_quota", "arrearage", "余额不足", "quota exceeded",
)
_NETWORK_TYPE_NAMES = frozenset({
    "APIConnectionError", "APITimeoutError", "Timeout", "ConnectionError", "ReadTimeout",
})
_MESSAGE_LIMIT = 500


def _status(exc: BaseException):
    value = getattr(exc, "status_code", None)
    return int(value) if isinstance(value, int) else None


def classify_provider_error(exc: BaseException) -> str:
    status = _status(exc)
    name = type(exc).__name__
    text = str(exc).lower()
    if name in _NETWORK_TYPE_NAMES:
        return "network_transient"
    if status == 402 or (status == 400 and any(m in text for m in _QUOTA_TEXT_MARKERS)) \
            or any(m in text for m in _QUOTA_TEXT_MARKERS):
        return "quota_exhausted"
    if status in (401, 403):
        return "credential_invalid"
    if status == 429:
        return "rate_limited"
    if status is not None and status >= 500:
        return "server_error"
    if status is not None and status >= 400:
        return "content_rejected"
    if name in ("BadRequestError", "NotFoundError"):
        return "content_rejected"
    return "unclassified"


def error_evidence(exc: BaseException) -> dict:
    evidence: dict = {}
    status = _status(exc)
    if status is not None:
        evidence["http_status"] = status
    request_id = getattr(exc, "request_id", None)
    if request_id:
        evidence["request_id"] = str(request_id)[:120]
    message = str(exc)
    if message:
        evidence["error_message"] = message[:_MESSAGE_LIMIT]
    return evidence
