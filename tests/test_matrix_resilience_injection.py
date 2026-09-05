# tests/test_matrix_resilience_injection.py
"""Integrated fault-injection: the three flows the spec requires.

1. quota error stops the batch AND the batch is resumable;
2. rate limit retries once and the journey continues;
3. three consecutive same-signature failures stop the batch.
"""
from __future__ import annotations

import json

from scripts.acceptance.real_provider_browser_batch import batch_stop_reason
from scripts.acceptance.strict_provider_guard import StrictProviderCallGuard


class _Flaky:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _QuotaError(Exception):
    status_code = 400

    def __str__(self):
        return "Error code: 400 - Insufficient Balance"


class _RateLimit(Exception):
    status_code = 429


def _guard(tmp_path, completion, cap=8):
    return StrictProviderCallGuard(
        completion=completion, receipt_path=tmp_path / "r.json", candidate_id="c",
        source_digest="sha256:s", call_cap=cap, expected_model="m",
        allowed_max_tokens={300}, temperature=0.0, timeout_seconds=30,
        retry_backoff_seconds=0.0,
    )


def test_flow_quota_stops_batch_and_resume_derives(tmp_path, monkeypatch):
    guard = _guard(tmp_path, _Flaky([_QuotaError()]))
    try:
        guard.completion(model="m", max_tokens=300, stream=False, messages=[])
    except _QuotaError:
        pass
    receipt = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    failure = receipt["terminal_failure"]
    assert failure["error_class"] == "quota_exhausted"
    assert batch_stop_reason([{"id": "M01", "status": "closed", "terminal_failure": failure}]) \
        == "provider_failure_global_fatal:quota_exhausted"
    # 恢复派生路径由 tests/test_resume_batch.py 覆盖；此处只验证停批触发条件与原因码。


def test_flow_rate_limit_retries_and_journey_continues(tmp_path):
    completion = _Flaky([_RateLimit(), object(), object()])
    guard = _guard(tmp_path, completion)
    guard.completion(model="m", max_tokens=300, stream=False, messages=[])
    receipt = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert receipt["terminal_failure"] is None
    assert [c["status"] for c in receipt["calls"]] == ["failed", "completed"]
    # 后续逻辑调用仍可继续（未熔断）。
    guard.completion(model="m", max_tokens=300, stream=False, messages=[])
    assert len(completion.calls) == 3


def test_flow_three_same_signature_scenarios_stop_batch(tmp_path):
    def failure(code, cls, status):
        return {"code": code, "error_class": cls, "http_status": status}

    records = [{"id": f"M0{i}", "status": "closed",
                "terminal_failure": failure("provider_request_failed", "content_rejected", 400)}
               for i in (1, 2, 3)]
    assert batch_stop_reason(records) == "consecutive_same_signature:content_rejected:400"
