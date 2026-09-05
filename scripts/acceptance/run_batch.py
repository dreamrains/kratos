# scripts/acceptance/run_batch.py
"""One-command batch orchestration: freeze-check, probe, run, audit.

The probe is one minimal authorized call (max_tokens=16, cap=1) with its
own receipt, spent before any scenario setup so credential or balance
failures do not burn scenario budgets.  Mid-batch exhaustion is handled
by resume batches, not by this probe.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.acceptance.provider_error_taxonomy import GLOBAL_FATAL_CLASSES, classify_provider_error
from scripts.acceptance.real_provider_browser_batch import _inside, preflight
from scripts.acceptance.strict_provider_guard import StrictProviderCallGuard


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
    interpreter with the venv's site-packages preserved on PYTHONPATH so the
    case child still sees exactly the frozen dependency set.  Without a
    direct interpreter the supervisor pid gate cannot hold, so fail closed
    instead of spawning children the gate would reject at M01.
    """
    import sysconfig

    for executable in (sys.executable, getattr(sys, "_base_executable", "") or ""):
        if executable and _spawns_direct(executable):
            env = dict(os.environ)
            if executable != sys.executable:
                site_packages = sysconfig.get_paths()["purelib"]
                env["PYTHONPATH"] = os.pathsep.join(
                    part for part in (site_packages, env.get("PYTHONPATH", "")) if part)
            return executable, env
    raise SystemExit(
        "no direct python interpreter available: the frozen supervisor pid gate "
        "requires case children that keep the spawned pid, but every candidate "
        "interpreter re-execs another process")


def run_probe(root: Path, *, model: str, api_base: str, api_key: str, receipt_path: Path,
              completion=None, backoff_seconds: float = 5.0) -> dict:
    root = root.resolve()
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
    except BaseException as exc:  # probe failures are data, not crashes
        error_class = classify_provider_error(exc)
        return {"ok": False, "error_class": error_class,
                "global_fatal": error_class in GLOBAL_FATAL_CLASSES}
    return {"ok": True, "error_class": None, "global_fatal": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--authorized", action="store_true")
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
    probe = run_probe(root, model=batch["model"], api_base=os.environ["DATA_AGENT_API_BASE"],
                      api_key=os.environ["DATA_AGENT_API_KEY"],
                      receipt_path=root / batch["isolation_root"] / "probe-receipt.json")
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
    for case, entry in zip(cases, batch["cases"]):
        case_id = entry["id"]
        control_dir = _inside(root, case["writes"]["process_control_dir"])
        result = subprocess.run(
            [child_interpreter, str(supervisor_path),
             "--control-dir", str(control_dir),
             "--",
             child_interpreter, "-m", "scripts.acceptance.real_provider_browser_batch",
             "--root", str(root), "--batch", str(batch_path), "--launcher", str(launcher_path),
             "--case", case_id],
            cwd=root,
            env={**child_env, "AUTHORIZED_BATCH_SHA256": checks["BATCH_SHA256"],
                 "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "1"},
        )
        print(json.dumps({"case": case_id, "exit_code": result.returncode}, ensure_ascii=False))
        if result.returncode != 0:
            # The batch ledger already records what closed; stop here rather
            # than spending the remaining frozen case budgets.
            raise SystemExit(f"case {case_id} failed with exit code {result.returncode}")


if __name__ == "__main__":
    main()
