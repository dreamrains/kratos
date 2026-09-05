# scripts/acceptance/run_batch.py
"""One-command batch orchestration: freeze-check, probe, run, audit.

The probe is one minimal authorized call (max_tokens=16, cap=1) with its
own receipt, spent before any scenario setup so credential or balance
failures do not burn scenario budgets.  Mid-batch exhaustion is handled
by resume batches, not by this probe.  A relaunch resumes a consumed
successful probe instead of aborting on its exclusive-create receipt.

``--serve CASE`` runs one frozen case and blocks until it exits, for
browser journeys driven by an external operator session; the printed
control dir takes a stop.request file, and no other case is started.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.acceptance.provider_error_taxonomy import GLOBAL_FATAL_CLASSES, classify_provider_error
from scripts.acceptance.real_provider_browser_batch import _inside, _pid_running, preflight
from scripts.acceptance.strict_provider_guard import StrictProviderCallGuard


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _child_pythonpath(repo_root: Path, site_packages: str, existing: str | None) -> str:
    """Import path for case children under ANY direct interpreter.

    The project package is an editable install, and .pth files are processed
    only for a real site-packages directory, never for PYTHONPATH entries, so
    the base-interpreter fallback needs the repo root, its src/ tree and the
    venv's purelib spelled out explicitly.  Pre-existing entries survive after
    those three, deduplicated.
    """
    ordered = [str(repo_root), str(repo_root / "src"), site_packages]
    ordered += [part for part in (existing or "").split(os.pathsep) if part.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for part in ordered:
        key = os.path.normcase(os.path.abspath(part))
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
    return os.pathsep.join(unique)


def _repo_env_value(env_path: Path, name: str) -> str | None:
    """One key from a .env file; values are never echoed elsewhere."""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() != name:
                continue
            value = value.strip().strip('"').strip("'")
            return value or None
    except OSError:
        return None
    return None


def _resolve_api_credentials(environment, *, repo_root: Path):
    """(api_base, api_key, sources) for the one authorized probe call.

    Order per credential: legacy DATA_AGENT_* env override, then the
    project's real API_BASE/API_KEY env names, then the config layer exactly
    as the counted server loads it, then the repo .env.  Values themselves
    are never returned into any log line by the caller.
    """
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    env_names = {"api_base": ("DATA_AGENT_API_BASE", "API_BASE"),
                 "api_key": ("DATA_AGENT_API_KEY", "API_KEY")}
    for field, names in env_names.items():
        for name in names:
            candidate = str(environment.get(name) or "").strip()
            if candidate:
                values[field], sources[field] = candidate, name
                break
    if len(values) < 2:
        try:
            from data_agent.config import get_config

            config = get_config()  # same construction path as the counted server
            for field in ("api_base", "api_key"):
                if field not in values and str(getattr(config, field) or "").strip():
                    values[field], sources[field] = str(getattr(config, field)).strip(), "config"
        except Exception:
            pass  # config-layer failure falls through to the repo .env below
    for field, name in (("api_base", "API_BASE"), ("api_key", "API_KEY")):
        if field not in values:
            from_env = _repo_env_value(Path(repo_root) / ".env", name)
            if from_env:
                values[field], sources[field] = from_env, "repo .env"
    return values.get("api_base"), values.get("api_key"), sources


def _spawns_direct(executable: str) -> bool:
    """True when a child of ``executable`` keeps the pid the parent observed.

    The supervisor contract binds the recorded process-start.json pid to the
    case child's own os.getpid().  Some venv launchers (uv trampolines)
    re-exec a base interpreter, which silently breaks that binding.
    """
    with tempfile.NamedTemporaryFile("r", suffix=".pid", delete=False) as handle:
        output = Path(handle.name)
    try:
        proc = subprocess.Popen(
            [executable, "-c",
             "import os; print(os.getpid(), file=open(os.environ['DATA_AGENT_PID_PROBE'], 'w'))"],
            env={**os.environ, "DATA_AGENT_PID_PROBE": str(output)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc.wait(timeout=60)
        return output.read_text(encoding="utf-8").strip() == str(proc.pid)
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        output.unlink(missing_ok=True)


def _direct_child_interpreter() -> tuple[str, dict[str, str]]:
    """Resolve an interpreter whose children keep the spawned pid.

    Prefers the current interpreter; falls back to the venv's base
    interpreter.  Either way the child env carries an explicit PYTHONPATH
    (repo root, src/, venv purelib, then any pre-existing entries) so the
    editable install resolves under any of them.  Without a direct
    interpreter the supervisor pid gate cannot hold, so fail closed instead
    of spawning children the gate would reject at M01.
    """
    import sysconfig

    for executable in (sys.executable, getattr(sys, "_base_executable", "") or ""):
        if executable and _spawns_direct(executable):
            env = dict(os.environ)
            env["PYTHONPATH"] = _child_pythonpath(
                _repo_root(), sysconfig.get_paths()["purelib"], env.get("PYTHONPATH"))
            return executable, env
    raise SystemExit(
        "no direct python interpreter available: the frozen supervisor pid gate "
        "requires case children that keep the spawned pid, but every candidate "
        "interpreter re-execs another process")


def run_probe(root: Path, *, model: str, api_base: str, api_key: str, receipt_path: Path,
              completion=None, backoff_seconds: float = 5.0) -> dict:
    root = root.resolve()
    receipt_path = Path(receipt_path)
    if receipt_path.exists():
        # Prior probe evidence must never be silently replaced: overwriting
        # would hide a previous run's consumption behind a fresh receipt.
        raise FileExistsError(f"probe receipt already exists, refusing to overwrite: {receipt_path}")
    if completion is None:
        os.environ.setdefault("DATA_AGENT_API_BASE", api_base)
        os.environ.setdefault("DATA_AGENT_API_KEY", api_key)
        from data_agent.llm import client as llm_client
        completion = llm_client.completion
    guard = StrictProviderCallGuard(
        completion=completion, receipt_path=receipt_path, candidate_id="batch_probe",
        source_digest="probe", call_cap=1, expected_model=model,
        allowed_max_tokens={16}, temperature=0.0, timeout_seconds=30,
        retry_backoff_seconds=backoff_seconds,
    )
    try:
        guard.completion(model=model, max_tokens=16, stream=False,
                         messages=[{"role": "user", "content": "ping"}], api_base=api_base,
                         api_key=api_key)
    except Exception as exc:
        # Probe failures are data, not crashes.  Only ordinary exceptions are
        # classified: KeyboardInterrupt / SystemExit must propagate so the
        # operator can still interrupt an authorized batch.
        error_class = classify_provider_error(exc)
        return {"ok": False, "error_class": error_class,
                "global_fatal": error_class in GLOBAL_FATAL_CLASSES}
    return {"ok": True, "error_class": None, "global_fatal": False}


def _resume_prior_probe(receipt_path: Path) -> dict:
    """Classify an existing probe receipt instead of overwriting it (fix C).

    A relaunch after the launcher's own crash must not abort on the receipt
    the previous launch already wrote.  Success is accepted ONLY for a fully
    locally-terminal, call-bearing receipt; anything ambiguous fails closed.
    """
    try:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
        calls = receipt["calls"]
        if not isinstance(calls, list):
            raise ValueError("calls missing")
        terminal_failure = receipt.get("terminal_failure")
        failed = [call for call in calls if call.get("status") == "failed"]
        if calls and all(call.get("status") == "completed" for call in calls) \
                and not failed and not terminal_failure:
            return {"ok": True, "error_class": None, "global_fatal": False,
                    "calls": len(calls)}
        if failed or terminal_failure:
            failure = terminal_failure or {}
            error_class = (failure.get("error_class")
                           or (failed[-1].get("error_class") if failed else None)
                           or "unclassified")
            return {"ok": False, "error_class": error_class,
                    "global_fatal": error_class in GLOBAL_FATAL_CLASSES}
        raise ValueError("probe receipt incomplete")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {"ok": False, "error_class": "probe_receipt_incomplete", "global_fatal": True}


def _archive_leftover_control_dir(control: Path, *, case_id: str, ledger_path: Path,
                                  receipt_path: Path, pid_running=None) -> Path:
    """Archive a crashed launch's process-control dir (fix D).

    browser_process.supervise mkdir(exist_ok=False), so a leftover dir from a
    crashed first launch blocks every retry.  It is archived ONLY when the
    case provably never started consuming the batch: no ledger entry for the
    case, no provider receipt, and every recorded pid dead.  Anything else is
    the operator's call, never a silent reset.
    """
    check_pid = pid_running or _pid_running

    def manual(reason: str) -> SystemExit:
        return SystemExit(
            f"case {case_id}: leftover process-control dir {control} must be handled "
            f"manually ({reason}); refusing to archive it automatically")

    if receipt_path.exists():
        raise manual(f"provider receipt exists at {receipt_path}")
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            entries = ledger.get("cases")
            if not isinstance(entries, list):
                raise ValueError
        except (OSError, ValueError, json.JSONDecodeError):
            raise manual(f"batch ledger at {ledger_path} is unreadable")
        if any(isinstance(record, dict) and record.get("id") == case_id for record in entries):
            raise manual(f"batch ledger at {ledger_path} already has an entry for {case_id}")
    start_path = control / "process-start.json"
    if start_path.exists():
        try:
            start = json.loads(start_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise manual("process-start.json is unreadable")
        pid = start.get("pid") if isinstance(start, dict) else None
        if not isinstance(pid, int) or isinstance(pid, bool):
            raise manual("process-start.json records no usable pid")
        try:
            running = check_pid(pid)
        except OSError:
            raise manual(f"cannot prove recorded pid {pid} is not running")
        if running:
            raise manual(f"recorded pid {pid} is still running")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = control.with_name(f"{control.name}.archived-{stamp}-crash-retry")
    while archive.exists():
        archive = archive.with_name(archive.name + "-1")
    control.rename(archive)
    return archive


def _audit_closed_cases_best_effort(root: Path, batch: dict, batch_path: Path) -> None:
    """Spec S8 auto-audit after the case loop.  Purely best-effort: any
    failure is reported, never raised, so the case loop's exit code (and
    Ctrl-C) stays the authoritative batch result."""
    try:
        ledger_path = root / batch["isolation_root"] / "provider-batch.json"
        if not ledger_path.is_file():
            return
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        if not any(record.get("status") == "closed" for record in ledger.get("cases", [])):
            return
        from scripts.acceptance.audit_batch import audit_batch
        report = audit_batch(root, batch_path)
        for case in report["cases"]:
            gate = "PASS" if case["hard_gate"]["passed"] else "FAIL"
            print(f"audit {case['case_id']}: hard_gate={gate} "
                  f"failed_oracles={len(case['failed_oracles'])} "
                  f"observer_gaps={len(case['observer_gaps'])}", flush=True)
        print(json.dumps({"audit_report": report["report_path"],
                          "summary": report["summary"]}, ensure_ascii=False), flush=True)
    except Exception as exc:  # reporting only; never masks the batch result
        print(json.dumps({"audit": "failed", "error": f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False), flush=True)


def _spawn_supervised_case(*, root: Path, supervisor_path: Path, child_interpreter: str,
                           child_env: dict[str, str], batch_path: Path, launcher_path: Path,
                           case_id: str, control_dir: Path, checks: dict) -> subprocess.CompletedProcess:
    """One supervisor-wrapped frozen case child (the only spawn shape there is)."""
    return subprocess.run(
        [child_interpreter, str(supervisor_path),
         "--control-dir", str(control_dir),
         "--",
         child_interpreter, "-m", "scripts.acceptance.real_provider_browser_batch",
         "--root", str(root), "--batch", str(batch_path),
         "--launcher", str(launcher_path),
         "--case", case_id],
        cwd=root,
        env={**child_env, "AUTHORIZED_BATCH_SHA256": checks["BATCH_SHA256"],
             "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "1"},
    )


def _exit_record_summary(control_dir: Path):
    """Summarize the supervisor's process-exit.json after a child exits."""
    try:
        proof = json.loads((control_dir / "process-exit.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "missing"
    return {key: proof.get(key) for key in (
        "pid", "exit_code", "process_exited", "graceful_exit",
        "elapsed_after_stop_seconds", "timeout_reached", "forced_termination")}


def _serve_single_case(*, root: Path, batch: dict, batch_path: Path, cases: list, checks: dict,
                       serve_case: str, child_interpreter: str, child_env: dict[str, str],
                       supervisor_path: Path, launcher_path: Path) -> None:
    """Fix F: run exactly one frozen case and block until it exits.

    The journey driver (an external browser automation session) owns the
    timeline: it stops the case by writing stop.request into the printed
    control dir, and the supervisor turns that into a graceful stop plus a
    process-exit.json proof.  Authorization, probe-or-resume and the crashed
    control-dir archive rules are identical to the batch loop; no other
    frozen case is ever started from here.
    """
    ids = [case["matrix_case_id"] for case in cases]
    if serve_case not in ids:
        raise SystemExit(f"--serve case {serve_case!r} is not in the frozen batch: {ids}")
    case = cases[ids.index(serve_case)]
    control_dir = _inside(root, case["writes"]["process_control_dir"])
    receipt_path = _inside(root, case["writes"]["provider_receipt_path"])
    if control_dir.exists():
        archive = _archive_leftover_control_dir(
            control_dir, case_id=serve_case,
            ledger_path=root / batch["isolation_root"] / "provider-batch.json",
            receipt_path=receipt_path)
        print(json.dumps({"case": serve_case, "archived_control_dir": str(archive)},
                         ensure_ascii=False), flush=True)
    print(json.dumps({"serve": serve_case,
                      "web_url": f"http://127.0.0.1:{case['port']}",
                      "control_dir": str(control_dir),
                      "stop_request": str(control_dir / "stop.request"),
                      "receipt_path": str(receipt_path)}, ensure_ascii=False), flush=True)
    try:
        result = _spawn_supervised_case(
            root=root, supervisor_path=supervisor_path, child_interpreter=child_interpreter,
            child_env=child_env, batch_path=batch_path, launcher_path=launcher_path,
            case_id=serve_case, control_dir=control_dir, checks=checks)
        print(json.dumps({"case": serve_case, "exit_code": result.returncode},
                         ensure_ascii=False), flush=True)
        print(json.dumps({"case": serve_case,
                          "process_exit": _exit_record_summary(control_dir)},
                         ensure_ascii=False), flush=True)
    finally:
        # Same best-effort audit as the batch loop; never masks the exit code.
        _audit_closed_cases_best_effort(root, batch, batch_path)
    if result.returncode != 0:
        raise SystemExit(f"case {serve_case} failed with exit code {result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--serve", metavar="CASE", default=None,
                        help="run only this frozen case and block until it exits "
                             "(external journey driving); no other case is started")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    batch_path, launcher_path = Path(args.batch).resolve(), Path(args.launcher).resolve()
    batch, cases, checks = preflight(root, batch_path, launcher_path)
    if not args.authorized:
        print(json.dumps({
            "batch_id": batch["batch_id"],
            "authorize_with": "AUTHORIZED_BATCH_SHA256=" + checks["BATCH_SHA256"],
            "cases": [entry["id"] for entry in batch["cases"]],
        }, ensure_ascii=False, indent=2))
        return
    api_base, api_key, credential_sources = _resolve_api_credentials(os.environ, repo_root=_repo_root())
    if not api_base or not api_key:
        raise SystemExit(
            "API credentials unavailable for the probe: set API_BASE/API_KEY (or the "
            "legacy DATA_AGENT_API_BASE/DATA_AGENT_API_KEY) in the environment, the "
            "config layer, or the repo .env; values are never printed")
    print(json.dumps({"credentials": credential_sources}, ensure_ascii=False), flush=True)
    probe_receipt = root / batch["isolation_root"] / "probe-receipt.json"
    if probe_receipt.exists():
        # A relaunch keeps the prior launch's probe evidence (fix C): a
        # consumed successful probe never triggers a new Provider call.
        probe = _resume_prior_probe(probe_receipt)
        if probe["ok"]:
            print(json.dumps({"probe": "already consumed", "receipt": str(probe_receipt),
                              "calls": probe["calls"]}, ensure_ascii=False), flush=True)
        else:
            print(json.dumps({"probe": probe, "receipt": str(probe_receipt)},
                             ensure_ascii=False), flush=True)
    else:
        probe = run_probe(root, model=batch["model"], api_base=api_base, api_key=api_key,
                          receipt_path=probe_receipt)
        print(json.dumps({"probe": probe}, ensure_ascii=False))
    if not probe["ok"]:
        raise SystemExit("probe failed: " + str(probe["error_class"]))
    # One fresh OS process per frozen case, spawned THROUGH the frozen
    # supervisor exactly like the manual launcher chain.  In-process iteration
    # is impossible because the supervisor gate, the previous-case exit proof
    # and the ledger's pid-liveness check all assume each case is a new
    # process; spawning the case child bare is equally impossible because
    # run_case's supervisor gate (_require_current_supervisor) proves the
    # child is a DIRECT supervised process before ledger.begin, and M02's
    # graceful-exit proof is only written by the supervisor.  browser_process
    # creates the case's frozen process-control directory, starts the child
    # with DATA_AGENT_ACCEPTANCE_STOP_PATH pointing at the receipt-local stop
    # signal, and records process-start.json/process-exit.json.  The supervised
    # command ends with the frozen launcher path plus --case <id> (the
    # --launcher argument value supplies that tail), which is exactly the
    # expected_command_tail the gate demands; the child re-runs its own
    # preflight and derives every per-case value from the authorized digest.
    # The interpreter must keep the spawned pid (see _direct_child_interpreter)
    # or the recorded process-start pid would never equal the child's own.
    child_interpreter, child_env = _direct_child_interpreter()
    supervisor_path = _inside(root, batch["supervisor_path"])
    if args.serve is not None:
        _serve_single_case(root=root, batch=batch, batch_path=batch_path, cases=cases,
                           checks=checks, serve_case=args.serve,
                           child_interpreter=child_interpreter, child_env=child_env,
                           supervisor_path=supervisor_path, launcher_path=launcher_path)
        return
    ledger_path = root / batch["isolation_root"] / "provider-batch.json"
    try:
        for case, entry in zip(cases, batch["cases"]):
            case_id = entry["id"]
            control_dir = _inside(root, case["writes"]["process_control_dir"])
            if control_dir.exists():
                archive = _archive_leftover_control_dir(
                    control_dir, case_id=case_id, ledger_path=ledger_path,
                    receipt_path=_inside(root, case["writes"]["provider_receipt_path"]))
                print(json.dumps({"case": case_id, "archived_control_dir": str(archive)},
                                 ensure_ascii=False), flush=True)
            result = _spawn_supervised_case(
                root=root, supervisor_path=supervisor_path, child_interpreter=child_interpreter,
                child_env=child_env, batch_path=batch_path, launcher_path=launcher_path,
                case_id=case_id, control_dir=control_dir, checks=checks)
            print(json.dumps({"case": case_id, "exit_code": result.returncode},
                             ensure_ascii=False))
            if result.returncode != 0:
                # The batch ledger already records what closed; stop here rather
                # than spending the remaining frozen case budgets.
                raise SystemExit(
                    f"case {case_id} failed with exit code {result.returncode}")
    finally:
        # Any exit path with at least one closed case still gets the offline
        # auto-audit; it must never mask the case loop's exit code.
        _audit_closed_cases_best_effort(root, batch, batch_path)


if __name__ == "__main__":
    main()
