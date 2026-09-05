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
            "port": 5800 + i,
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
    # The child import path is explicit no matter which interpreter won:
    # repo root, its src/ tree, and the venv's frozen dependency set.  A
    # base-interpreter fallback cannot rely on editable-install .pth files
    # because PYTHONPATH entries never process them.
    import sysconfig

    parts = env["PYTHONPATH"].split(os.pathsep)
    repo_root = run_batch._repo_root()
    assert str(repo_root) in parts
    assert str(repo_root / "src") in parts
    assert sysconfig.get_paths()["purelib"] in parts


def test_direct_child_interpreter_fails_closed_without_any_direct_python(monkeypatch):
    monkeypatch.setattr(run_batch, "_spawns_direct", lambda executable: False)
    monkeypatch.setattr(sys, "_base_executable", "", raising=False)
    with pytest.raises(SystemExit, match="no direct python interpreter"):
        run_batch._direct_child_interpreter()


def test_child_pythonpath_orders_root_src_site_packages_before_existing():
    """Fix B regression: the case child env's PYTHONPATH must carry the
    repo root, src/ and the venv purelib ahead of any pre-existing entries,
    deduplicated, so an editable install resolves under any interpreter."""
    import sysconfig

    repo_root = run_batch._repo_root()
    site_packages = sysconfig.get_paths()["purelib"]
    existing = os.pathsep.join(["C:/already/here", site_packages])
    joined = run_batch._child_pythonpath(repo_root, site_packages, existing)
    parts = joined.split(os.pathsep)
    assert parts.index(str(repo_root)) < parts.index(str(repo_root / "src"))
    assert parts.index(str(repo_root / "src")) < parts.index(site_packages)
    assert parts[-1] == "C:/already/here"  # pre-existing entries kept after
    assert parts.count(site_packages) == 1  # and deduplicated


class _StubConfig:
    def __init__(self, api_base=None, api_key=None):
        self.api_base, self.api_key = api_base, api_key


def test_credentials_env_precedence_and_sources(tmp_path):
    # Legacy DATA_AGENT_* names stay hard overrides for old invocations.
    api_base, api_key, sources = run_batch._resolve_api_credentials(
        {"DATA_AGENT_API_BASE": "https://legacy.invalid/v1",
         "DATA_AGENT_API_KEY": "sk-legacy",
         "API_BASE": "https://project.invalid/v1", "API_KEY": "sk-project"},
        repo_root=tmp_path)
    assert (api_base, api_key) == ("https://legacy.invalid/v1", "sk-legacy")
    assert sources == {"api_base": "DATA_AGENT_API_BASE", "api_key": "DATA_AGENT_API_KEY"}
    # The project's real env names work without any legacy alias.
    api_base, api_key, sources = run_batch._resolve_api_credentials(
        {"API_BASE": "https://project.invalid/v1", "API_KEY": "sk-project"},
        repo_root=tmp_path)
    assert (api_base, api_key) == ("https://project.invalid/v1", "sk-project")
    assert sources == {"api_base": "API_BASE", "api_key": "API_KEY"}


def test_credentials_fall_back_to_the_config_layer(tmp_path, monkeypatch):
    monkeypatch.setattr("data_agent.config.get_config",
                        lambda: _StubConfig("https://config.invalid/v1", "sk-config"))
    api_base, api_key, sources = run_batch._resolve_api_credentials({}, repo_root=tmp_path)
    assert (api_base, api_key) == ("https://config.invalid/v1", "sk-config")
    assert sources == {"api_base": "config", "api_key": "config"}


def test_credentials_fall_back_to_repo_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr("data_agent.config.get_config", lambda: _StubConfig())
    (tmp_path / ".env").write_text(
        "# comment\nAPI_BASE=https://dotenv.invalid/v1\nOTHER=noise\nAPI_KEY=sk-dotenv\n",
        encoding="utf-8")
    api_base, api_key, sources = run_batch._resolve_api_credentials({}, repo_root=tmp_path)
    assert (api_base, api_key) == ("https://dotenv.invalid/v1", "sk-dotenv")
    assert sources == {"api_base": "repo .env", "api_key": "repo .env"}


def test_credentials_missing_everywhere_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("data_agent.config.get_config", lambda: _StubConfig())
    assert run_batch._resolve_api_credentials({}, repo_root=tmp_path)[:2] == (None, None)


def test_main_fails_closed_when_credentials_are_unavailable(tmp_path, monkeypatch):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setenv("AUTHORIZED_BATCH_SHA256", batch_digest)
    for name in ("DATA_AGENT_API_BASE", "DATA_AGENT_API_KEY", "API_BASE", "API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(run_batch, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr("data_agent.config.get_config", lambda: _StubConfig())

    def no_probe(*args, **kwargs):
        raise AssertionError("probe must not run without credentials")

    monkeypatch.setattr(run_batch, "run_probe", no_probe)
    monkeypatch.setattr(sys, "argv", [
        "run_batch", "--root", str(tmp_path), "--batch", str(batch_path),
        "--launcher", str(launcher), "--authorized",
    ])
    with pytest.raises(SystemExit, match="credential"):
        run_batch.main()


def _probe_receipt(tmp_path, calls, terminal_failure=None):
    path = tmp_path / "tmp" / "run" / "probe-receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"schema_version": 3, "candidate_id": "batch_probe", "source_digest": "probe",
         "call_cap": 1, "calls": calls, "blocked_attempts": 0,
         "terminal_failure": terminal_failure}, ensure_ascii=False), encoding="utf-8")
    return path


def _probe_call(status="completed", error_class=None):
    call = {"ordinal": 1, "model": "provider/model", "stream": False, "max_tokens": 16,
            "status": status, "started_at": "t0", "local_request_stopped": status != "started"}
    if error_class:
        call["error_class"] = error_class
    return call


def test_resume_probe_accepts_consumed_successful_receipt(tmp_path):
    receipt = _probe_receipt(tmp_path, [_probe_call()])
    result = run_batch._resume_prior_probe(receipt)
    assert result["ok"] is True
    assert result["error_class"] is None
    assert result["global_fatal"] is False
    assert result["calls"] == 1


def test_resume_probe_aborts_on_failed_receipt(tmp_path):
    receipt = _probe_receipt(
        tmp_path, [_probe_call("failed", "quota_exhausted")],
        terminal_failure={"code": "provider_request_failed", "error_class": "quota_exhausted"})
    result = run_batch._resume_prior_probe(receipt)
    assert result["ok"] is False
    assert result["error_class"] == "quota_exhausted"
    assert result["global_fatal"] is True


def test_resume_probe_fails_closed_on_incomplete_receipt(tmp_path):
    for calls in ([], [_probe_call("started")], [_probe_call("unknown")]):
        receipt = _probe_receipt(tmp_path, calls)
        result = run_batch._resume_prior_probe(receipt)
        assert result["ok"] is False
        assert result["error_class"] == "probe_receipt_incomplete"
        assert result["global_fatal"] is True


def test_authorized_relaunch_resumes_consumed_probe_without_a_new_call(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    _probe_receipt(tmp_path, [_probe_call()])  # the prior launch consumed it

    def no_probe(*args, **kwargs):
        raise AssertionError("consumed probe receipt must not trigger a new Provider call")

    monkeypatch.setattr(run_batch, "run_probe", no_probe)
    calls = _authorized_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, results=[0] * 6)
    run_batch.main()
    assert len(calls) == 6
    assert '"probe": "already consumed"' in capsys.readouterr().out


def _leftover_control(tmp_path, pid=12345):
    control = tmp_path / "tmp" / "run" / "M01" / "process-control"
    control.mkdir(parents=True)
    (control / "process-start.json").write_text(json.dumps(
        {"schema_version": "browser_process_start.v1", "pid": pid,
         "supervisor_pid": 999, "command": ["x"], "started_at": "t",
         "stop_request_path": str(control / "stop.request"),
         "stop_signal_path": str(control / "stop.signal"),
         "stop_timeout_seconds": 30}, ensure_ascii=False), encoding="utf-8")
    return control


def _archive(control, tmp_path, pid_running=lambda pid: False):
    return run_batch._archive_leftover_control_dir(
        control, case_id="M01",
        ledger_path=tmp_path / "tmp" / "run" / "provider-batch.json",
        receipt_path=tmp_path / "tmp" / "run" / "M01" / "calls.json",
        pid_running=pid_running)


def test_crashed_control_dir_archives_when_case_never_started(tmp_path):
    control = _leftover_control(tmp_path)
    archive = _archive(control, tmp_path)
    assert not control.exists()
    assert archive.parent == control.parent
    assert archive.name.startswith("process-control.archived-")
    assert archive.name.endswith("-crash-retry")
    assert archive.is_dir()


def test_crashed_control_dir_refuses_when_a_ledger_entry_exists(tmp_path):
    control = _leftover_control(tmp_path)
    ledger = tmp_path / "tmp" / "run" / "provider-batch.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps({"cases": [{"id": "M01", "status": "closed"}]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="ledger"):
        _archive(control, tmp_path)
    assert control.exists()


def test_crashed_control_dir_refuses_while_recorded_pid_is_running(tmp_path):
    control = _leftover_control(tmp_path)
    with pytest.raises(SystemExit, match="still running"):
        _archive(control, tmp_path, pid_running=lambda pid: True)
    assert control.exists()


def test_crashed_control_dir_refuses_when_a_provider_receipt_exists(tmp_path):
    control = _leftover_control(tmp_path)
    receipt = tmp_path / "tmp" / "run" / "M01" / "calls.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="receipt"):
        _archive(control, tmp_path)
    assert control.exists()


def test_crashed_control_dir_fails_closed_on_unreadable_start_record(tmp_path):
    control = _leftover_control(tmp_path)
    (control / "process-start.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(SystemExit, match="handle"):
        _archive(control, tmp_path)
    assert control.exists()


def test_authorized_loop_archives_crashed_control_dir_before_spawning(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    control = _leftover_control(tmp_path)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": True, "error_class": None, "global_fatal": False})
    monkeypatch.setattr(run_batch, "_pid_running", lambda pid: False)
    calls = _authorized_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, results=[0] * 6)
    run_batch.main()
    assert not control.exists()
    assert '"archived_control_dir"' in capsys.readouterr().out
    assert [call["command"][-1] for call in calls] == [f"M{i:02d}" for i in range(1, 7)]


def _serve_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, case_id, results=(0,)):
    """Authorized --serve CLI wiring with a counting subprocess.run stub."""
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
        "--launcher", str(launcher), "--authorized", "--serve", case_id,
    ])
    return calls


def test_serve_mode_spawns_exactly_one_supervised_child_for_the_named_case(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": True, "error_class": None, "global_fatal": False})
    calls = _serve_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, "M03")
    run_batch.main()
    assert len(calls) == 1  # never auto-continues to other frozen cases
    command = calls[0]["command"]
    separator = command.index("--")
    wrapper, inner = command[:separator], command[separator + 1:]
    supervisor = (tmp_path / "supervisor.py").resolve()
    assert wrapper[:2] == [sys.executable, str(supervisor)]
    assert wrapper[2:4] == ["--control-dir",
                            str((tmp_path / "tmp/run/M03/process-control").resolve())]
    assert inner[:3] == [sys.executable, "-m", "scripts.acceptance.real_provider_browser_batch"]
    assert inner[-3:] == [str(launcher.resolve()), "--case", "M03"]
    assert calls[0]["cwd"] == tmp_path
    assert calls[0]["env"]["AUTHORIZED_BATCH_SHA256"] == batch_digest
    assert calls[0]["env"]["DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED"] == "1"
    out = capsys.readouterr().out
    assert '"case": "M03"' in out and '"exit_code": 0' in out


def test_serve_mode_prints_url_control_dir_and_receipt_json(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": True, "error_class": None, "global_fatal": False})
    _serve_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, "M01")
    run_batch.main()
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()
             if line.startswith("{")]
    serve_lines = [item for item in lines if isinstance(item, dict) and "serve" in item]
    assert len(serve_lines) == 1
    line = serve_lines[0]
    assert line["serve"] == "M01"
    assert line["web_url"] == "http://127.0.0.1:5801"
    assert line["control_dir"] == str((tmp_path / "tmp/run/M01/process-control").resolve())
    assert line["receipt_path"] == str((tmp_path / "tmp/run/M01/calls.json").resolve())
    exits = [item for item in lines if isinstance(item, dict) and "process_exit" in item]
    assert len(exits) == 1  # exit record summary printed after the child exits


def test_serve_mode_resumes_consumed_probe_without_a_new_call(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    _probe_receipt(tmp_path, [_probe_call()])  # the prior launch consumed it

    def no_probe(*args, **kwargs):
        raise AssertionError("consumed probe receipt must not trigger a new Provider call")

    monkeypatch.setattr(run_batch, "run_probe", no_probe)
    calls = _serve_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, "M02")
    run_batch.main()
    assert len(calls) == 1
    assert '"probe": "already consumed"' in capsys.readouterr().out


def test_serve_mode_fails_closed_without_an_authorized_digest(tmp_path, monkeypatch):
    batch_path, launcher, _ = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setenv("AUTHORIZED_BATCH_SHA256", "sha256:" + "0" * 64)
    monkeypatch.setenv("DATA_AGENT_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("DATA_AGENT_API_KEY", "sk-test")
    spawned = []
    monkeypatch.setattr(run_batch.subprocess, "run",
                        lambda *args, **kwargs: spawned.append((args, kwargs))
                        or subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(sys, "argv", [
        "run_batch", "--root", str(tmp_path), "--batch", str(batch_path),
        "--launcher", str(launcher), "--authorized", "--serve", "M01",
    ])
    with pytest.raises(ValueError, match="authorization mismatch"):
        run_batch.main()
    assert spawned == []


def test_serve_mode_requires_the_authorization_step_first(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    monkeypatch.setenv("AUTHORIZED_BATCH_SHA256", batch_digest)
    spawned = []
    monkeypatch.setattr(run_batch.subprocess, "run",
                        lambda *args, **kwargs: spawned.append((args, kwargs))
                        or subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(sys, "argv", [
        "run_batch", "--root", str(tmp_path), "--batch", str(batch_path),
        "--launcher", str(launcher), "--serve", "M01",
    ])
    run_batch.main()
    assert spawned == []
    summary = json.loads(capsys.readouterr().out)
    assert summary["authorize_with"] == "AUTHORIZED_BATCH_SHA256=" + batch_digest


def test_serve_mode_archives_leftover_control_dir_for_the_served_case(tmp_path, monkeypatch, capsys):
    batch_path, launcher, batch_digest = _frozen_batch(tmp_path, monkeypatch)
    control = _leftover_control(tmp_path)
    monkeypatch.setattr(run_batch, "run_probe", lambda *args, **kwargs: {
        "ok": True, "error_class": None, "global_fatal": False})
    monkeypatch.setattr(run_batch, "_pid_running", lambda pid: False)
    calls = _serve_argv(tmp_path, monkeypatch, batch_path, launcher, batch_digest, "M01")
    run_batch.main()
    assert not control.exists()
    out = capsys.readouterr().out
    assert '"archived_control_dir"' in out
    assert len(calls) == 1 and calls[0]["command"][-1] == "M01"
