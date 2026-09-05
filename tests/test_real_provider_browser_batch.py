from __future__ import annotations

import json
import os
import sys

import pytest

from scripts.acceptance import real_provider_browser_batch as batch
from scripts.acceptance.strict_provider_guard import StrictProviderCallGuard, ProviderJourneyHalted


def _ledger(tmp_path):
    return batch.BatchLedger(tmp_path / "batch.json", batch_hash="sha256:batch",
                             case_ids=[f"M{i:02d}" for i in range(1, 7)], call_cap=12)


def _guard(tmp_path, case_id, completion):
    return StrictProviderCallGuard(completion=completion, receipt_path=tmp_path / f"{case_id}.json",
                                   candidate_id=case_id, source_digest="sha256:source", call_cap=2,
                                   expected_model="model", allowed_max_tokens={300}, temperature=0, timeout_seconds=120)


def test_all_six_provider_failures_are_case_local_and_no_case_is_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "_pid_running", lambda _: False)
    dispatched = []
    for i in range(1, 7):
        case_id = f"M{i:02d}"
        ledger = _ledger(tmp_path)  # reload durable accounting for each process
        ledger.begin(case_id, 2)

        def failed(**kw):
            dispatched.append(case_id)
            raise RuntimeError("transport failure")

        guard = _guard(tmp_path, case_id, failed)
        guard.persist_receipt()
        with pytest.raises(RuntimeError):
            guard.completion(model="model", max_tokens=300)
        with pytest.raises(ProviderJourneyHalted):
            guard.completion(model="model", max_tokens=300)
        guard.close()
        ledger.finish(tmp_path / f"{case_id}.json", candidate_id=case_id, source_digest="sha256:source")
    assert dispatched == [f"M{i:02d}" for i in range(1, 7)]
    result = _ledger(tmp_path).state
    assert result["real_calls"] == 6
    assert result["blocked_attempts"] == 6
    assert all(c["status"] == "closed" for c in result["cases"])
    with pytest.raises(ValueError, match="already consumed"):
        _ledger(tmp_path).begin("M01", 2)


def test_process_lock_prevents_two_servers_in_one_batch(tmp_path):
    with batch.process_lock(tmp_path / "batch.lock"):
        with pytest.raises(OSError):
            with batch.process_lock(tmp_path / "batch.lock"):
                pytest.fail("concurrent process lock acquired")


def test_crash_start_marker_cannot_be_reset_or_skipped(tmp_path):
    _ledger(tmp_path).begin("M01", 2)
    with pytest.raises(ValueError, match="unproven"):
        _ledger(tmp_path).begin("M02", 2)
    with pytest.raises(ValueError, match="unproven"):
        _ledger(tmp_path).begin("M01", 2)


def test_in_flight_receipt_does_not_close_case(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.begin("M01", 2)
    guard = _guard(tmp_path, "M01", lambda **_: iter([]))
    stream = guard.completion(model="model", max_tokens=300, stream=True)
    guard.close()
    with pytest.raises(ValueError, match="in-flight"):
        ledger.finish(tmp_path / "M01.json", candidate_id="M01", source_digest="sha256:source")
    assert _ledger(tmp_path).state["cases"][0]["status"] == "started"
    list(stream)


def test_closed_guard_never_dispatches_after_server_teardown(tmp_path):
    calls = []
    guard = _guard(tmp_path, "M01", lambda **kw: calls.append(kw))
    guard.persist_receipt()
    guard.close()
    with pytest.raises(ProviderJourneyHalted, match="acceptance_server_closed"):
        guard.completion(model="model", max_tokens=300)
    assert not calls


def test_previous_pid_must_exit_before_next_case(tmp_path, monkeypatch):
    ledger = _ledger(tmp_path)
    ledger.begin("M01", 2)
    guard = _guard(tmp_path, "M01", lambda **_: object())
    guard.close()
    ledger.finish(tmp_path / "M01.json", candidate_id="M01", source_digest="sha256:source")
    monkeypatch.setattr(batch, "_pid_running", lambda _: True)
    with pytest.raises(ValueError, match="not exited"):
        _ledger(tmp_path).begin("M02", 2)


def test_batch_cap_cannot_be_replenished_by_next_case(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "_pid_running", lambda _: False)
    ledger = batch.BatchLedger(tmp_path / "batch.json", batch_hash="sha256:batch", case_ids=["M01", "M02"], call_cap=2)
    ledger.begin("M01", 2)
    guard = _guard(tmp_path, "M01", lambda **_: object())
    guard.completion(model="model", max_tokens=300)
    guard.completion(model="model", max_tokens=300)
    guard.close()
    ledger.finish(tmp_path / "M01.json", candidate_id="M01", source_digest="sha256:source")
    with pytest.raises(ValueError, match="budget"):
        ledger.begin("M02", 2)


def test_receipt_identity_mismatch_is_not_treated_as_zero_calls(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.begin("M01", 2)
    guard = _guard(tmp_path, "wrong-case", lambda **_: object())
    guard.close()
    with pytest.raises(ValueError, match="identity mismatch"):
        ledger.finish(tmp_path / "wrong-case.json", candidate_id="M01", source_digest="sha256:source")


FROZEN_RETRY_POLICY = {
    "max_retry_attempts": 1,
    "backoff_seconds": 20,
    "retry_error_classes": ["rate_limited", "network_transient", "server_error"],
}


def _frozen_batch_factory(tmp_path, monkeypatch):
    from scripts.acceptance.real_provider_browser_server import _normalized_file_hash as digest, _canonical_json_hash as canonical
    data = tmp_path / "data.bin"
    data.write_bytes(b"data")
    data_item = {"id": "data", "path": "data.bin", "sha256": digest(data)}
    launcher = tmp_path / "launcher.py"
    launcher.write_text("# launcher", encoding="utf-8")
    supervisor = tmp_path / "supervisor.py"
    supervisor.write_text("# supervisor", encoding="utf-8")
    monkeypatch.setattr(batch, "release_source_digest", lambda _: "source")
    cases = []
    for i in range(1, 7):
        cid = f"M{i:02d}"
        cases.append({
            "matrix_case_id": cid, "source_digest": "source", "model": "model", "data": [data_item],
            "prompt": "analyze", "prompts": ["analyze"], "oracle": {"test": True},
            "provider_policy": {
                "temperature": 0, "timeout_seconds": 120, "initial_max_tokens": 8000,
                "auxiliary_initial_max_tokens": 300, "auxiliary_max_tokens": [300, 800],
                "silent_length_ladder": [8000], "num_retries": 0,
                "retry_policy": json.loads(json.dumps(FROZEN_RETRY_POLICY)),
                "stream_sync_fallback": False, "model_fallback": False,
                "supplementary_run": False, "web_journeys": 1, "analysis_turns": 1, "call_cap": 2,
            },
            "writes": {"workspace_dir": f"tmp/run/{cid}/workspace", "sessions_dir": f"tmp/run/{cid}/sessions",
                       "process_control_dir": f"tmp/run/{cid}/process-control",
                       "provider_receipt_path": f"tmp/run/{cid}/calls.json", "report_path": f"docs/audit/{cid}.json"},
        })
    frozen = {
        "schema_version": "real_provider_browser_batch.v1", "source_digest": "source", "model": "model",
        "call_cap": 12, "isolation_root": "tmp/run", "report_path": "docs/audit/batch.json",
        "supervisor_path": supervisor.name,
        "supervisor_sha256": digest(supervisor),
        "launcher_sha256": digest(launcher), "data_bundle_sha256": canonical([data_item]),
        "prompt_bundle_sha256": canonical({c["matrix_case_id"]: c["prompts"] for c in cases}),
        "oracle_bundle_sha256": canonical({c["matrix_case_id"]: c["oracle"] for c in cases}),
    }
    batch_path, env = _rewrite_case_files(frozen, cases, tmp_path)
    return frozen, cases, batch_path, launcher, env


def _rewrite_case_files(frozen, cases, tmp_path):
    """Rewrite mutated case candidates plus the batch manifest so that every
    digest, envelope and authorization check still passes preflight."""
    from scripts.acceptance.real_provider_browser_server import _normalized_file_hash as digest
    entries = []
    for case in cases:
        path = tmp_path / f"{case['matrix_case_id']}.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        entries.append({"id": case["matrix_case_id"], "path": path.name, "sha256": digest(path)})
    frozen["cases"] = entries
    batch_path = tmp_path / "batch-candidate.json"
    batch_path.write_text(json.dumps(frozen), encoding="utf-8")
    env = {"AUTHORIZED_BATCH_SHA256": digest(batch_path), "AUTHORIZED_SOURCE_DIGEST": "source"}
    env.update({"AUTHORIZED_" + key.upper(): value for key, value in frozen.items() if key.endswith("sha256")})
    return batch_path, env


def _frozen_fixture(tmp_path, monkeypatch):
    _, _, path, launcher, env = _frozen_batch_factory(tmp_path, monkeypatch)
    return path, launcher, env


def test_whole_matrix_preflight_is_read_only_and_zero_provider(tmp_path, monkeypatch):
    path, launcher, env = _frozen_fixture(tmp_path, monkeypatch)
    frozen, cases, checks = batch.preflight(tmp_path, path, launcher, env)
    assert len(cases) == 6
    assert not (tmp_path / "tmp").exists()
    assert not (tmp_path / "docs").exists()


def test_batch_digest_alone_authorizes_the_values_committed_by_candidate(tmp_path, monkeypatch):
    path, launcher, env = _frozen_fixture(tmp_path, monkeypatch)
    frozen, cases, checks = batch.preflight(
        tmp_path,
        path,
        launcher,
        {"AUTHORIZED_BATCH_SHA256": env["AUTHORIZED_BATCH_SHA256"]},
    )
    assert len(cases) == 6
    assert checks["BATCH_SHA256"] == env["AUTHORIZED_BATCH_SHA256"]


def test_authorized_batch_digest_accepts_equivalent_bare_sha256(tmp_path, monkeypatch):
    path, launcher, env = _frozen_fixture(tmp_path, monkeypatch)
    bare = env["AUTHORIZED_BATCH_SHA256"].removeprefix("sha256:")
    _, cases, _ = batch.preflight(tmp_path, path, launcher, {"AUTHORIZED_BATCH_SHA256": bare})
    assert len(cases) == 6


def test_main_propagates_verified_source_and_launcher_to_nested_case_preflight(tmp_path, monkeypatch):
    launcher = tmp_path / "launcher.py"
    launcher.write_text("# launcher", encoding="utf-8")
    case_path = tmp_path / "M01.json"
    case_path.write_text("{}", encoding="utf-8")
    case = {
        "matrix_case_id": "M01",
        "model": "model",
        "prompt": "analyze",
        "oracle": {"test": True},
        "port": 5501,
        "writes": {"workspace_dir": "tmp/run/M01/workspace", "sessions_dir": "tmp/run/M01/sessions"},
    }
    frozen = {"cases": [{"path": "M01.json"}]}
    checks = {"SOURCE_DIGEST": "sha256:source", "LAUNCHER_SHA256": "sha256:launcher"}
    observed = []
    monkeypatch.setattr(batch, "preflight", lambda *args: (frozen, [case], checks))
    monkeypatch.setattr(batch, "run_authorized_browser_server", lambda **kwargs: observed.append(dict(os.environ)))
    monkeypatch.setattr(sys, "argv", ["batch", "--case", "M01", "--preflight-only"])

    mutated_keys = {
        "MODEL_ID", "QUALITY_JUDGE_MODEL", "MAX_TOKENS", "MCP_ENABLED", "SKILL_AUTO_DISCOVER",
        "WORKSPACE_DIR", "SESSIONS_DIR", "LOG_FILE", "DATA_AGENT_WEB_HOST", "DATA_AGENT_WEB_PORT",
        "AUTHORIZED_SOURCE_DIGEST", "AUTHORIZED_LAUNCHER_SHA256", "AUTHORIZED_CANDIDATE_SHA256",
        "AUTHORIZED_PROMPT_SHA256", "AUTHORIZED_ORACLE_SHA256", "DATA_AGENT_PREFLIGHT_ONLY",
    }
    previous = {key: os.environ.get(key) for key in mutated_keys}
    try:
        batch.main(root=tmp_path, batch_path=tmp_path / "batch.json", launcher_path=launcher)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert len(observed) == 1
    assert observed[0]["AUTHORIZED_SOURCE_DIGEST"] == "sha256:source"
    assert observed[0]["AUTHORIZED_LAUNCHER_SHA256"] == "sha256:launcher"


@pytest.mark.parametrize("target", ["M06.json", "data.bin", "launcher.py", "supervisor.py"])
def test_any_case_data_or_launcher_mismatch_blocks_whole_batch(tmp_path, monkeypatch, target):
    path, launcher, env = _frozen_fixture(tmp_path, monkeypatch)
    (tmp_path / target).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        batch.preflight(tmp_path, path, launcher, env)
    assert not (tmp_path / "tmp").exists()


def test_no_implicit_authorization_from_candidate_values(tmp_path, monkeypatch):
    path, launcher, env = _frozen_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="authorization mismatch"):
        batch.preflight(tmp_path, path, launcher, {})


def test_preflight_requires_retry_policy_contract(tmp_path, monkeypatch):
    frozen, cases, batch_path, launcher, _ = _frozen_batch_factory(tmp_path, monkeypatch)
    for case in cases:
        case["provider_policy"].pop("retry_policy", None)
    _, env = _rewrite_case_files(frozen, cases, tmp_path)
    with pytest.raises(ValueError, match="retry policy"):
        batch.preflight(tmp_path, batch_path, launcher, env)


def test_preflight_rejects_widened_retry_classes(tmp_path, monkeypatch):
    frozen, cases, batch_path, launcher, _ = _frozen_batch_factory(tmp_path, monkeypatch)
    cases[0]["provider_policy"]["retry_policy"]["retry_error_classes"].append("quota_exhausted")
    _, env = _rewrite_case_files(frozen, cases, tmp_path)
    with pytest.raises(ValueError, match="retry policy"):
        batch.preflight(tmp_path, batch_path, launcher, env)


def test_real_execution_supervisor_gate_binds_pid_signal_and_frozen_launcher(tmp_path):
    launcher = (tmp_path / "launcher.py").resolve()
    launcher.write_text("# launcher", encoding="utf-8")
    control = (tmp_path / "run" / "M01" / "process-control").resolve()
    control.mkdir(parents=True)
    case = {"matrix_case_id": "M01", "writes": {"process_control_dir": "run/M01/process-control"}}
    record = {
        "schema_version": "browser_process_start.v1",
        "pid": os.getpid(),
        "supervisor_pid": max(1, os.getpid() - 1),
        "command": [sys.executable, str(launcher), "--case", "M01"],
        "started_at": "recorded",
        "stop_request_path": str(control / "stop.request"),
        "stop_signal_path": str(control / "stop.signal"),
        "stop_timeout_seconds": 30,
    }
    (control / "process-start.json").write_text(json.dumps(record), encoding="utf-8")
    previous = os.environ.get("DATA_AGENT_ACCEPTANCE_STOP_PATH")
    os.environ["DATA_AGENT_ACCEPTANCE_STOP_PATH"] = str(control / "stop.signal")
    try:
        assert batch._require_current_supervisor(tmp_path, case, launcher)["pid"] == os.getpid()
        record["command"][-1] = "M02"
        (control / "process-start.json").write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(ValueError, match="not proven"):
            batch._require_current_supervisor(tmp_path, case, launcher)
    finally:
        if previous is None:
            os.environ.pop("DATA_AGENT_ACCEPTANCE_STOP_PATH", None)
        else:
            os.environ["DATA_AGENT_ACCEPTANCE_STOP_PATH"] = previous
