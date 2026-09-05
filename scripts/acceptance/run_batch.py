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

from scripts.acceptance.provider_error_taxonomy import GLOBAL_FATAL_CLASSES, classify_provider_error
from scripts.acceptance.real_provider_browser_batch import preflight
from scripts.acceptance.strict_provider_guard import StrictProviderCallGuard


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
    # One fresh OS process per frozen case, exactly like the launcher flow:
    # in-process iteration is impossible because the supervisor gate, the
    # previous-case exit proof and the ledger's pid-liveness check all assume
    # each case is a new process.  The child re-runs its own preflight and
    # derives every per-case value from the same authorized batch digest.
    for entry in batch["cases"]:
        case_id = entry["id"]
        result = subprocess.run(
            [sys.executable, "-m", "scripts.acceptance.real_provider_browser_batch",
             "--root", str(root), "--batch", str(batch_path), "--launcher", str(launcher_path),
             "--case", case_id],
            cwd=root,
            env={**os.environ, "AUTHORIZED_BATCH_SHA256": checks["BATCH_SHA256"],
                 "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "1"},
        )
        print(json.dumps({"case": case_id, "exit_code": result.returncode}, ensure_ascii=False))
        if result.returncode != 0:
            # The batch ledger already records what closed; stop here rather
            # than spending the remaining frozen case budgets.
            raise SystemExit(f"case {case_id} failed with exit code {result.returncode}")


if __name__ == "__main__":
    main()
