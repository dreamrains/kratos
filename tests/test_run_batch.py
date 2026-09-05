# tests/test_run_batch.py
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from scripts.acceptance import real_provider_browser_batch as browser_batch
from scripts.acceptance import run_batch
from scripts.acceptance.run_batch import run_probe


class _ProbeCompletion:
    def __init__(self, responses):
        self._responses = list(responses)

    def __call__(self, **kwargs):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _probe_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_AGENT_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("DATA_AGENT_API_KEY", "sk-test")
    return tmp_path / "probe-receipt.json"


def test_probe_reports_quota_as_global_fatal(tmp_path, monkeypatch):
    receipt = _probe_env(monkeypatch, tmp_path)

    class _Quota(Exception):
        status_code = 400

        def __str__(self):
            return "Error code: 400 - Insufficient Balance"

    result = run_probe(tmp_path, model="provider/model", api_base="https://example.invalid/v1",
                       api_key="sk-test", receipt_path=receipt,
                       completion=_ProbeCompletion([_Quota()]), backoff_seconds=0.0)
    assert result["ok"] is False
    assert result["error_class"] == "quota_exhausted"
    assert result["global_fatal"] is True
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["calls"][0]["error_class"] == "quota_exhausted"


def test_probe_success_returns_ok(tmp_path, monkeypatch):
    receipt = _probe_env(monkeypatch, tmp_path)
    result = run_probe(tmp_path, model="provider/model", api_base="https://example.invalid/v1",
                       api_key="sk-test", receipt_path=receipt,
                       completion=_ProbeCompletion([object()]), backoff_seconds=0.0)
    assert result["ok"] is True and result["error_class"] is None
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["candidate_id"] == "batch_probe"
    assert saved["call_cap"] == 1
    assert saved["calls"][0]["status"] == "completed"


def test_probe_lets_keyboard_interrupt_propagate(tmp_path, monkeypatch):
    receipt = _probe_env(monkeypatch, tmp_path)

    def interrupted(**kwargs):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_probe(tmp_path, model="provider/model", api_base="https://example.invalid/v1",
                  api_key="sk-test", receipt_path=receipt,
                  completion=interrupted, backoff_seconds=0.0)


def test_probe_refuses_to_silently_overwrite_prior_receipt(tmp_path, monkeypatch):
    receipt = _probe_env(monkeypatch, tmp_path)
    receipt.write_text('{"prior": true}', encoding="utf-8")
    with pytest.raises(FileExistsError, match="probe receipt already exists"):
        run_probe(tmp_path, model="provider/model", api_base="https://example.invalid/v1",
                  api_key="sk-test", receipt_path=receipt,
                  completion=_ProbeCompletion([]), backoff_seconds=0.0)
    assert json.loads(receipt.read_text(encoding="utf-8")) == {"prior": True}


def _frozen_batch(tmp_path, monkeypatch):
    """Task 5 fixture pattern: one fully verifiable six-case batch under tmp_path."""
    from scripts.acceptance.real_provider_browser_server import (
        _canonical_json_hash as canonical, _normalized_file_hash as digest,
    )
    monkeypatch.setattr(browser_batch, "release_source_digest", lambda _: "source")
    data = tmp_path / "data.bin"
    data.write_bytes(b"data")
    data_item = {"id": "data", "path": "data.bin", "sha256": digest(data)}
    launcher = tmp_path / "launcher.py"
    launcher.write_text("# launcher", encoding="utf-8")
    supervisor = tmp_path / "supervisor.py"
    supervisor.write_text("# supervisor", encoding="utf-8")
    retry_policy = {
        "max_retry_attempts": 1,
        "backoff_seconds": 20,
        "retry_error_classes": ["rate_limited", "network_transient", "server_error"],
    }
    cases = []
    for i in range(1, 7):
        cid = f"M{i:02d}"
        cases.append({
            "matrix_case_id": cid, "source_digest": "source", "model": "model",
            "data": [data_item], "prompt": "analyze", "prompts": ["analyze"],
            "oracle": {"test": True},
            "provider_policy": {
                "temperature": 0, "timeout_seconds": 120, "initial_max_tokens": 8000,
                "auxiliary_initial_max_tokens": 300, "auxiliary_max_tokens": [300, 800],
                "silent_length_ladder": [8000], "num_retries": 0,
                "retry_policy": json.loads(json.dumps(retry_policy)),
                "stream_sync_fallback": False, "model_fallback": False,
                "supplementary_run": False, "web_journeys": 1, "analysis_turns": 1,
                "call_cap": 2,
            },
            "writes": {"workspace_dir": f"tmp/run/{cid}/workspace",
                       "sessions_dir": f"tmp/run/{cid}/sessions",
                       "process_control_dir": f"tmp/run/{cid}/process-control",
                       "provider_receipt_path": f"tmp/run/{cid}/calls.json",
                       "report_path": f"docs/audit/{cid}.json"},
        })
    entries = []
    for case in cases:
        path = tmp_path / f"{case['matrix_case_id']}.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        entries.append({"id": case["matrix_case_id"], "path": path.name, "sha256": digest(path)})
    frozen = {
        "schema_version": "real_provider_browser_batch.v1", "batch_id": "B001",
        "source_digest": "source", "model": "model",
        "call_cap": 12, "isolation_root": "tmp/run", "report_path": "docs/audit/batch.json",
        "supervisor_path": supervisor.name, "supervisor_sha256": digest(supervisor),
        "launcher_sha256": digest(launcher), "data_bundle_sha256": canonical([data_item]),
        "prompt_bundle_sha256": canonical({c["matrix_case_id"]: c["prompts"] for c in cases}),
        "oracle_bundle_sha256": canonical({c["matrix_case_id"]: c["oracle"] for c in cases}),
        "cases": entries,
    }
    batch_path = tmp_path / "batch-candidate.json"
    batch_path.write_text(json.dumps(frozen), encoding="utf-8")
    return batch_path, launcher, digest(batch_path)


def test_main_without_authorized_prints_digest_and_launches_nothing(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setenv("AUTHORIZED_BATCH_SHA256", batch_digest)
    spawned = []
    monkeypatch.setattr(run_batch.subprocess, "run",
                        lambda *args, **kwargs: spawned.append((args, kwargs)) or subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(sys, "argv", [
        "run_batch", "--root", str(tmp_path), "--batch", str(batch_path), "--launcher", str(launcher),
    ])
    run_batch.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["batch_id"] == "B001"
    assert summary["authorize_with"] == "AUTHORIZED_BATCH_SHA256=" + batch_digest
    assert summary["cases"] == [f"M{i:02d}" for i in range(1, 7)]
    assert spawned == []


def _authorized_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, results):
    """Authorized CLI wiring with a counting subprocess.run stub.

    ``results[i]`` is the return code served to the i-th spawned case.
    """
    monkeypatch.setenv("AUTHORIZED_BATCH_SHA256", batch_digest)
    monkeypatch.setenv("DATA_AGENT_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("DATA_AGENT_API_KEY", "sk-test")
    monkeypatch.setattr(run_batch, "_direct_child_interpreter",
                        lambda: (sys.executable, dict(os.environ)))
    calls = []

    def fake_run(command, *, cwd, env):
        calls.append({"command": list(command), "cwd": cwd, "env": dict(env)})
        return subprocess.CompletedProcess(command, results[len(calls) - 1])

    monkeypatch.setattr(run_batch.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "run_batch", "--root", str(tmp_path), "--batch", str(batch_path),
        "--launcher", str(launcher), "--authorized",
    ])
    return calls


def test_probe_failure_launches_no_case_subprocess(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": False, "error_class": "quota_exhausted", "global_fatal": True})
    calls = _authorized_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, results=[])
    with pytest.raises(SystemExit, match="probe failed"):
        run_batch.main()
    assert calls == []


def test_authorized_loop_spawns_one_supervised_subprocess_per_case(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": True, "error_class": None, "global_fatal": False})
    calls = _authorized_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, results=[0] * 6)
    run_batch.main()
    assert [call["command"][-1] for call in calls] == [f"M{i:02d}" for i in range(1, 7)]
    supervisor = (tmp_path / "supervisor.py").resolve()
    for index, call in enumerate(calls):
        command = call["command"]
        separator = command.index("--")
        wrapper, inner = command[:separator], command[separator + 1:]
        # The case child is spawned THROUGH the frozen supervisor CLI...
        assert wrapper[:2] == [sys.executable, str(supervisor)]
        assert wrapper[2:4] == ["--control-dir",
                                str((tmp_path / f"tmp/run/M{index + 1:02d}/process-control").resolve())]
        # ...and the supervised command tail is exactly what the supervisor
        # gate (_require_current_supervisor) demands of the recorded
        # process-start.json: frozen launcher path + --case + case id.
        assert inner[:3] == [sys.executable, "-m", "scripts.acceptance.real_provider_browser_batch"]
        assert inner[-3:] == [str(launcher.resolve()), "--case", command[-1]]
    first = calls[0]
    assert first["cwd"] == tmp_path
    assert first["env"]["AUTHORIZED_BATCH_SHA256"] == batch_digest
    assert first["env"]["DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED"] == "1"
    assert '"case": "M01"' in capsys.readouterr().out


def test_authorized_loop_stops_at_first_failing_case(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": True, "error_class": None, "global_fatal": False})
    calls = _authorized_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, results=[0, 1])
    with pytest.raises(SystemExit, match="M02 failed"):
        run_batch.main()
    assert [call["command"][-1] for call in calls] == ["M01", "M02"]


def _closed_ledger(tmp_path):
    """A batch ledger with one closed case, as left by a completed M01."""
    ledger_path = tmp_path / "tmp/run/provider-batch.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps({
        "schema_version": 2, "batch_sha256": "sha256:x",
        "cases": [{"id": "M01", "status": "closed",
                   "terminal_failure": {"code": "acceptance_server_closed"}}]}),
        encoding="utf-8")
    return ledger_path


def test_case_loop_failure_still_audits_without_masking_exit_code(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    _closed_ledger(tmp_path)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": True, "error_class": None, "global_fatal": False})
    audited = []
    import scripts.acceptance.audit_batch as audit_module
    monkeypatch.setattr(audit_module, "audit_batch",
                        lambda root, path: audited.append((root, path)) or {
                            "cases": [{"case_id": "M01", "hard_gate": {"passed": True},
                                       "failed_oracles": [], "observer_gaps": ["x"]}],
                            "summary": {"cases_closed_audited": 1},
                            "report_path": "docs/audit/aud.json"})
    calls = _authorized_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, results=[0, 1])
    with pytest.raises(SystemExit, match="M02 failed"):
        run_batch.main()
    assert audited == [(tmp_path, batch_path)]
    out = capsys.readouterr().out
    assert "audit M01: hard_gate=PASS" in out
    assert [call["command"][-1] for call in calls] == ["M01", "M02"]


def test_audit_failure_is_reported_and_never_masks_the_batch_result(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    _closed_ledger(tmp_path)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": True, "error_class": None, "global_fatal": False})

    def broken_audit(root, path):
        raise RuntimeError("synthetic audit failure")

    import scripts.acceptance.audit_batch as audit_module
    monkeypatch.setattr(audit_module, "audit_batch", broken_audit)
    _authorized_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, results=[0, 1])
    with pytest.raises(SystemExit, match="M02 failed"):
        run_batch.main()
    assert '"audit": "failed"' in capsys.readouterr().out


def test_wrapper_spawn_chain_passes_the_frozen_supervisor_gate(tmp_path):
    """End-to-end proof of the C1 fix's contract, without a real batch.

    Runs the exact wrapper shape run_batch builds (frozen supervisor CLI,
    --control-dir, --, child command ending in launcher --case <id>) through
    the REAL supervisor binary and the pid-stable interpreter run_batch
    resolves.  The stand-in launcher does what run_case does before
    ledger.begin: prove itself a direct supervised child via
    require_supervised_child, then stop via stop.request so the supervisor
    records a graceful process-exit.json for the next case.
    """
    from pathlib import Path

    from scripts.acceptance import browser_process

    root = tmp_path
    launcher = root / "standin-launcher.py"
    launcher.write_text(
        "import os, pathlib, sys, time\n"
        "sys.path.insert(0, os.environ['DATA_AGENT_TEST_STANDIN_ROOT'])\n"
        "from scripts.acceptance.browser_process import require_supervised_child\n"
        "stop = pathlib.Path(os.environ['DATA_AGENT_ACCEPTANCE_STOP_PATH'])\n"
        "start = require_supervised_child(\n"
        "    stop.parent, expected_pid=os.getpid(), expected_stop_signal=stop,\n"
        "    expected_command_tail=[str(pathlib.Path(sys.argv[0]).resolve()),\n"
        "                           '--case', sys.argv[-1]])\n"
        "assert start['command'][-3:] == [str(pathlib.Path(sys.argv[0]).resolve()),\n"
        "                                 '--case', sys.argv[-1]]\n"
        "stop.with_name('stop.request').touch()\n"
        "while not stop.exists():\n"
        "    time.sleep(0.01)\n",
        encoding="utf-8")
    control = root / "tmp" / "run" / "M01" / "process-control"
    repo_root = Path(run_batch.__file__).resolve().parents[2]
    child_interpreter, child_env = run_batch._direct_child_interpreter()
    result = subprocess.run(
        [child_interpreter, str(Path(browser_process.__file__).resolve()),
         "--control-dir", str(control),
         "--",
         child_interpreter, str(launcher.resolve()), "--case", "M01"],
        cwd=root, env={**child_env, "DATA_AGENT_TEST_STANDIN_ROOT": str(repo_root)},
        timeout=60,
    )
    assert result.returncode == 0
    start = json.loads((control / "process-start.json").read_text(encoding="utf-8"))
    assert start["command"][-3:] == [str(launcher.resolve()), "--case", "M01"]
    proof = json.loads((control / "process-exit.json").read_text(encoding="utf-8"))
    assert proof["graceful_exit"] is True
    assert proof["exit_code"] == 0


def test_direct_child_interpreter_returns_a_pid_stable_child():
    executable, env = run_batch._direct_child_interpreter()
    assert run_batch._spawns_direct(executable)
    if executable == sys.executable:
        assert env == dict(os.environ)
    else:
        # A base-interpreter fallback keeps the venv's frozen dependency set.
        import sysconfig
        assert sysconfig.get_paths()["purelib"] in env["PYTHONPATH"]


def test_direct_child_interpreter_fails_closed_without_any_direct_python(monkeypatch):
    monkeypatch.setattr(run_batch, "_spawns_direct", lambda executable: False)
    monkeypatch.setattr(sys, "_base_executable", "", raising=False)
    with pytest.raises(SystemExit, match="no direct python interpreter"):
        run_batch._direct_child_interpreter()
