from __future__ import annotations

import json

import pytest

from scripts.acceptance.strict_provider_guard import (
    ProviderJourneyHalted,
    ProviderPolicyViolation,
    StrictProviderCallGuard,
    require_network_enabled_execution,
)


class _Completion:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return response


def _guard(tmp_path, completion, *, call_cap=4):
    return StrictProviderCallGuard(
        completion=completion,
        receipt_path=tmp_path / "provider-calls.json",
        candidate_id="candidate-test",
        source_digest="sha256:source",
        call_cap=call_cap,
        expected_model="provider/model",
        allowed_max_tokens={300, 800, 8000},
        temperature=0.0,
        timeout_seconds=120,
    )


def _call(guard, *, max_tokens=300, stream=False):
    return guard.completion(
        model="provider/model",
        max_tokens=max_tokens,
        stream=stream,
        temperature=0.7,
        timeout=1,
        num_retries=5,
    )


def test_transient_receipt_rename_does_not_repeat_provider_request(tmp_path, monkeypatch):
    from pathlib import Path
    completion = _Completion([object()])
    guard = _guard(tmp_path, completion)
    original = Path.replace
    failures = []

    def replace(self, target):
        if len(failures) < 2:
            failures.append(1)
            error = PermissionError('reader holds snapshot')
            error.winerror = 5
            raise error
        return original(self, target)

    monkeypatch.setattr(Path, 'replace', replace)
    monkeypatch.setattr('data_agent.utils.atomic_files.time.sleep', lambda _: None)
    _call(guard)
    receipt = json.loads((tmp_path/'provider-calls.json').read_text())
    assert len(completion.calls) == 1
    assert len(receipt['calls']) == 1 and receipt['calls'][0]['status'] == 'completed'


def test_permanent_receipt_denial_prevents_provider_admission(tmp_path, monkeypatch):
    from pathlib import Path
    completion = _Completion([object()])
    guard = _guard(tmp_path, completion)
    attempts = []

    def denied(self, target):
        attempts.append(1)
        error = PermissionError('persistent denial')
        error.winerror = 5
        raise error

    monkeypatch.setattr(Path, 'replace', denied)
    monkeypatch.setattr('data_agent.utils.atomic_files.time.sleep', lambda _: None)
    with pytest.raises(PermissionError):
        _call(guard)
    assert len(attempts) == 40
    assert completion.calls == []
    assert not (tmp_path/'provider-calls.json').exists()


def test_first_auxiliary_failure_blocks_the_main_call_without_touching_provider(tmp_path):
    completion = _Completion([RuntimeError("connection failed"), object()])
    guard = _guard(tmp_path, completion)

    with pytest.raises(RuntimeError, match="connection failed"):
        _call(guard, max_tokens=300)
    with pytest.raises(ProviderJourneyHalted, match="provider_request_failed"):
        _call(guard, max_tokens=8000)

    assert len(completion.calls) == 1
    assert completion.calls[0]["num_retries"] == 0
    assert completion.calls[0]["temperature"] == 0.0
    assert completion.calls[0]["timeout"] == 120
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 3
    assert receipt["blocked_attempts"] == 1
    assert receipt["terminal_failure"]["code"] == "provider_request_failed"
    assert receipt["terminal_failure"]["ordinal"] == 1
    assert len(receipt["calls"]) == 1
    assert receipt["calls"][0]["status"] == "failed"
    assert receipt["calls"][0]["error_type"] == "RuntimeError"
    assert receipt["calls"][0]["started_at"].endswith("Z")
    assert receipt["calls"][0]["finished_at"].endswith("Z")


def test_stream_failure_trips_the_same_global_latch(tmp_path):
    def broken_stream():
        yield {"delta": "partial"}
        raise TimeoutError("stream failed")

    completion = _Completion([broken_stream(), object()])
    guard = _guard(tmp_path, completion)

    stream = _call(guard, max_tokens=8000, stream=True)
    with pytest.raises(TimeoutError, match="stream failed"):
        list(stream)
    with pytest.raises(ProviderJourneyHalted, match="provider_request_failed"):
        _call(guard, max_tokens=300)

    assert len(completion.calls) == 1
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert receipt["calls"][0]["stream"] is True
    assert receipt["calls"][0]["status"] == "failed"
    assert receipt["terminal_failure"]["error_type"] == "TimeoutError"


def test_concurrent_logical_call_is_blocked_before_it_can_reach_provider(tmp_path):
    def successful_stream():
        yield {"delta": "done"}

    completion = _Completion([successful_stream(), object()])
    guard = _guard(tmp_path, completion)

    stream = _call(guard, max_tokens=8000, stream=True)
    with pytest.raises(ProviderJourneyHalted, match="provider_concurrent_call_forbidden"):
        _call(guard, max_tokens=300)
    assert list(stream) == [{"delta": "done"}]

    assert len(completion.calls) == 1
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert receipt["calls"][0]["status"] == "completed"
    assert receipt["blocked_attempts"] == 1
    assert receipt["terminal_failure"]["code"] == "provider_concurrent_call_forbidden"


def test_call_cap_is_terminal_and_does_not_count_or_dispatch_the_blocked_attempt(tmp_path):
    completion = _Completion([object(), object(), object()])
    guard = _guard(tmp_path, completion, call_cap=2)

    _call(guard, max_tokens=300)
    _call(guard, max_tokens=8000)
    with pytest.raises(ProviderJourneyHalted, match="provider_call_cap_exceeded"):
        _call(guard, max_tokens=800)

    assert len(completion.calls) == 2
    assert guard.calls_started == 2
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert [call["status"] for call in receipt["calls"]] == ["completed", "completed"]
    assert receipt["blocked_attempts"] == 1
    assert receipt["terminal_failure"]["code"] == "provider_call_cap_exceeded"


def test_policy_violation_closes_the_journey_before_any_provider_call(tmp_path):
    completion = _Completion([object()])
    guard = _guard(tmp_path, completion)

    with pytest.raises(ProviderPolicyViolation, match="provider_model_change_forbidden"):
        guard.completion(model="other/model", max_tokens=300)
    with pytest.raises(ProviderJourneyHalted, match="provider_model_change_forbidden"):
        _call(guard, max_tokens=300)

    assert completion.calls == []
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert receipt["calls"] == []
    assert receipt["blocked_attempts"] == 2
    assert receipt["terminal_failure"]["code"] == "provider_model_change_forbidden"


def test_network_execution_requires_an_explicit_executor_acknowledgement():
    with pytest.raises(ProviderPolicyViolation, match="network_enabled_execution_not_acknowledged"):
        require_network_enabled_execution({})

    require_network_enabled_execution({"DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "1"})

    # Codex retains this inherited flag even for an approved unsandboxed
    # process, so it cannot be used as a runtime capability signal.
    require_network_enabled_execution({
        "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "1",
        "CODEX_SANDBOX_NETWORK_DISABLED": "1",
    })
