# tests/test_provider_error_taxonomy.py
from scripts.acceptance.provider_error_taxonomy import (
    GLOBAL_FATAL_CLASSES, RETRYABLE_ERROR_CLASSES,
    classify_provider_error, error_evidence,
)


class _FakeProviderError(Exception):
    def __init__(self, message="", status_code=None, request_id=None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


def test_quota_exhausted_by_status_402():
    assert classify_provider_error(_FakeProviderError("x", status_code=402)) == "quota_exhausted"

def test_quota_exhausted_by_text_on_400():
    # DeepSeek 余额不足是 400 + 文本，必须文本匹配
    exc = _FakeProviderError("Error code: 400 - Insufficient Balance", status_code=400)
    assert classify_provider_error(exc) == "quota_exhausted"

def test_credential_invalid():
    assert classify_provider_error(_FakeProviderError("bad key", status_code=401)) == "credential_invalid"
    assert classify_provider_error(_FakeProviderError("forbidden", status_code=403)) == "credential_invalid"

def test_rate_limited_and_server_error():
    assert classify_provider_error(_FakeProviderError("slow down", status_code=429)) == "rate_limited"
    assert classify_provider_error(_FakeProviderError("boom", status_code=503)) == "server_error"

def test_content_rejected_default_for_400():
    assert classify_provider_error(_FakeProviderError("bad request", status_code=400)) == "content_rejected"

def test_network_transient_by_type_name():
    for name in ("APIConnectionError", "APITimeoutError", "Timeout", "ConnectionError"):
        exc = _FakeProviderError(name)
        exc.__class__.__name__ = name
        assert classify_provider_error(exc) == "network_transient", name

def test_unclassified_for_unknown():
    assert classify_provider_error(ValueError("local bug")) == "unclassified"

def test_error_evidence_truncates_and_collects():
    exc = _FakeProviderError("E" * 900, status_code=402, request_id="req-1")
    ev = error_evidence(exc)
    assert ev == {"http_status": 402, "request_id": "req-1", "error_message": "E" * 500}

def test_fatal_and_retryable_sets():
    assert GLOBAL_FATAL_CLASSES == {"quota_exhausted", "credential_invalid"}
    assert RETRYABLE_ERROR_CLASSES == {"rate_limited", "network_transient", "server_error"}
