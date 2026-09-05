"""Single-use, serial browser matrix bootstrap. Never drives the browser.

Each invocation is one new OS process for one frozen case. A process-lifetime
lock prevents concurrent servers; a durable start record prevents reruns after
crash. Fixed, non-transferable case caps sum to at most the batch hard cap.
The selected case uses the ordinary fail-closed Web server and Provider guard.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from scripts.acceptance.real_provider_browser_server import (
    _canonical_json_hash, _normalized_file_hash, _sha256_bytes,
    run_authorized_browser_server,
)
from scripts.acceptance.release_source import release_source_digest
from scripts.acceptance.strict_provider_guard import require_network_enabled_execution


def _time():
    return datetime.now(timezone.utc).isoformat()


def _write(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    from data_agent.utils.atomic_files import replace_file
    replace_file(temporary, path)


def _inside(root, relative):
    path = (root / relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("frozen path escapes repository")
    return path


def _pid_running(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, read-only
        if not handle:
            if ctypes.get_last_error() == 87:  # process does not exist
                return False
            raise OSError("cannot prove prior process exit")
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _authorized_batch_digest(value) -> str:
    """Canonicalize the one external authorization token.

    The frozen batch digest commits to the source digest, launcher,
    supervisor, data, prompts, oracles and every case candidate.  Requiring
    operators to retype all seven derived hashes for every serial case adds no
    cryptographic binding and created an avoidable A04 launch failure.  A bare
    64-character SHA-256 value and its ``sha256:`` form are the same token.
    """
    text = str(value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return "sha256:" + text
    if re.fullmatch(r"sha256:[0-9a-f]{64}", text):
        return text
    return ""


def preflight(root: Path, batch_path: Path, launcher_path: Path, environment=None):
    """Read-only verification of the whole matrix before any selected case."""
    env = os.environ if environment is None else environment
    root = root.resolve()
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if batch["schema_version"] != "real_provider_browser_batch.v1":
        raise ValueError("invalid batch schema")
    cases = []
    for entry in batch["cases"]:
        path = _inside(root, entry["path"])
        if _normalized_file_hash(path) != entry["sha256"]:
            raise ValueError("case candidate mismatch: " + entry["id"])
        case = json.loads(path.read_text(encoding="utf-8"))
        if case["matrix_case_id"] != entry["id"]:
            raise ValueError("case identity mismatch")
        if case["source_digest"] != batch["source_digest"] or case["model"] != batch["model"]:
            raise ValueError("case source/model mismatch")
        policy = case["provider_policy"]
        if any(policy.get(key) != value for key, value in {
            "temperature": 0, "timeout_seconds": 120, "initial_max_tokens": 8000,
            "auxiliary_initial_max_tokens": 300, "auxiliary_max_tokens": [300, 800],
            "silent_length_ladder": [8000], "num_retries": 0,
            "stream_sync_fallback": False, "model_fallback": False,
            "supplementary_run": False, "web_journeys": 1,
        }.items()):
            raise ValueError("case request policy outside strict batch contract")
        retry_policy = policy.get("retry_policy")
        if retry_policy != {
            "max_retry_attempts": 1,
            "backoff_seconds": 20,
            "retry_error_classes": ["rate_limited", "network_transient", "server_error"],
        }:
            raise ValueError("case request policy outside strict batch contract: retry policy")
        if not case["prompts"] or case["prompt"] != case["prompts"][0] or len(case["prompts"]) != policy["analysis_turns"]:
            raise ValueError("case prompt/turn envelope mismatch")
        cases.append(case)
    full_matrix = ["M01", "M02", "M03", "M04", "M05", "M06"]
    case_ids = [c["matrix_case_id"] for c in cases]
    resumes_from = batch.get("resumes_from")
    if resumes_from is None:
        if case_ids != full_matrix:
            raise ValueError("matrix must contain M01-M06 exactly once in order")
    else:
        # A resume batch re-attempts only the voided and never-run cases of a
        # global-fatal stop; completed cases are never re-run.  Accept an
        # in-order subsequence of the full matrix whose omitted ids are
        # exactly the completed cases recorded in resumes_from.
        rank = {case_id: index for index, case_id in enumerate(full_matrix)}
        order = [rank.get(case_id) for case_id in case_ids]
        omitted = set(full_matrix) - set(case_ids)
        completed = set(resumes_from.get("completed_cases") or [])
        if (not case_ids or None in order or sorted(order) != order
                or len(set(order)) != len(order) or omitted != completed):
            raise ValueError("resume matrix must be an in-order M01-M06 subsequence "
                             "omitting exactly the completed cases")
    caps = [c["provider_policy"]["call_cap"] for c in cases]
    if any(type(cap) is not int or cap < 1 for cap in caps) or sum(caps) > batch["call_cap"]:
        raise ValueError("case caps exceed the non-transferable batch envelope")
    data = {item["id"]: item for c in cases for item in c["data"]}
    for case in cases:
        for item in case["data"]:
            if item != data[item["id"]]:
                raise ValueError("inconsistent shared data definition")
    for item in data.values():
        if _sha256_bytes(_inside(root, item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError("data mismatch: " + item["id"])
    checks = {
        "BATCH_SHA256": _normalized_file_hash(batch_path),
        "SOURCE_DIGEST": release_source_digest(root),
        "LAUNCHER_SHA256": _normalized_file_hash(launcher_path),
        "SUPERVISOR_SHA256": _normalized_file_hash(_inside(root, batch["supervisor_path"])),
        "DATA_BUNDLE_SHA256": _canonical_json_hash([data[key] for key in sorted(data)]),
        "PROMPT_BUNDLE_SHA256": _canonical_json_hash({c["matrix_case_id"]: c["prompts"] for c in cases}),
        "ORACLE_BUNDLE_SHA256": _canonical_json_hash({c["matrix_case_id"]: c["oracle"] for c in cases}),
    }
    if checks["BATCH_SHA256"] != _authorized_batch_digest(env.get("AUTHORIZED_BATCH_SHA256")):
        raise ValueError("BATCH_SHA256 authorization mismatch")
    if checks["SOURCE_DIGEST"] != batch["source_digest"]:
        raise ValueError("stale batch source")
    for key in ("DATA_BUNDLE_SHA256", "PROMPT_BUNDLE_SHA256", "ORACLE_BUNDLE_SHA256", "LAUNCHER_SHA256", "SUPERVISOR_SHA256"):
        if checks[key] != batch[key.lower()]:
            raise ValueError(key + " frozen value mismatch")
    # Backward-compatible callers may still provide the derived values.  If
    # present they remain fail-closed, but they are no longer repeated manual
    # authorization inputs: the authorized batch digest already commits to
    # the corresponding fields above.
    for key in ("SOURCE_DIGEST", "DATA_BUNDLE_SHA256", "PROMPT_BUNDLE_SHA256", "ORACLE_BUNDLE_SHA256",
                "LAUNCHER_SHA256", "SUPERVISOR_SHA256"):
        supplied = env.get("AUTHORIZED_" + key)
        if supplied is not None and supplied != checks[key]:
            raise ValueError(key + " authorization mismatch")
    isolation = _inside(root, batch["isolation_root"])
    if not isolation.is_relative_to(root / "tmp"):
        raise ValueError("batch isolation must be under tmp")
    if not _inside(root, batch["report_path"]).is_relative_to(root / "docs/audit"):
        raise ValueError("batch report outside audit")
    directories, files = [], []
    for case in cases:
        for key, relative in case["writes"].items():
            path = _inside(root, relative)
            if key in {"workspace_dir", "sessions_dir", "process_control_dir"}:
                if not path.is_relative_to(isolation):
                    raise ValueError("case directory outside isolation")
                directories.append(path)
            else:
                if key != "report_path" and not path.is_relative_to(isolation):
                    raise ValueError("receipt outside isolation")
                if key == "report_path" and not path.is_relative_to(root / "docs/audit"):
                    raise ValueError("case report outside audit")
                files.append(path)
    if len(set(files)) != len(files) or len(set(directories)) != len(directories):
        raise ValueError("duplicate output targets")
    for a in directories:
        if any(a != b and (a.is_relative_to(b) or b.is_relative_to(a)) for b in directories):
            raise ValueError("overlapping case directories")
    for case in cases:
        receipt_parent = _inside(root, case["writes"]["provider_receipt_path"]).parent
        control = _inside(root, case["writes"]["process_control_dir"])
        if control != receipt_parent / "process-control":
            raise ValueError("process control directory must be receipt-local")
    return batch, cases, checks


def _require_current_supervisor(root: Path, case: dict, launcher_path: Path) -> dict:
    from scripts.acceptance.browser_process import require_supervised_child

    control = _inside(root, case["writes"]["process_control_dir"])
    stop_signal = os.environ.get("DATA_AGENT_ACCEPTANCE_STOP_PATH", "")
    if not stop_signal:
        raise ValueError("current supervised acceptance process not proven")
    return require_supervised_child(
        control,
        expected_pid=os.getpid(),
        expected_stop_signal=stop_signal,
        expected_command_tail=[str(launcher_path.resolve()), "--case", case["matrix_case_id"]],
    )


@contextmanager
def process_lock(path: Path):
    """Nonblocking OS lock, automatically released if the process dies."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            # Locking a byte beyond EOF is supported on Windows.
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def _locally_terminal(call, receipt):
    if receipt.get("schema_version", 2) >= 3:
        return (call["status"] in {"completed", "failed", "cancelled"}
                and call.get("local_request_stopped") is True)
    # Preserve historical receipt semantics. Never reinterpret a started call.
    return call["status"] in {"completed", "failed"}


_GLOBAL_FATAL_CLASSES = frozenset({"quota_exhausted", "credential_invalid"})


def batch_stop_reason(closed_records: list[dict]) -> str | None:
    """Batch-wide stop is reserved for global-fatal conditions or a
    cross-scenario pattern (three consecutive closed cases with the same
    error signature).  Any other scenario failure must not skip the
    remaining frozen cases."""
    consecutive: list[tuple[str, str | None]] = []
    for record in closed_records:
        failure = record.get("terminal_failure") or {}
        if failure.get("code") != "provider_request_failed":
            consecutive.clear()
            continue
        error_class = failure.get("error_class") or "unclassified"
        if error_class in _GLOBAL_FATAL_CLASSES:
            return f"provider_failure_global_fatal:{error_class}"
        signature = (error_class, failure.get("http_status"))
        if consecutive and consecutive[-1] == signature:
            consecutive.append(signature)
        else:
            consecutive = [signature]
        if len(consecutive) >= 3:
            return f"consecutive_same_signature:{signature[0]}:{signature[1]}"
    return None


class BatchLedger:
    """Used only while holding process_lock for the entire case lifetime."""

    def __init__(self, path: Path, *, batch_hash: str, case_ids: list[str], call_cap: int):
        self.path, self.case_ids, self.call_cap = path, case_ids, call_cap
        if path.exists():
            self.state = json.loads(path.read_text(encoding="utf-8"))
            if self.state["batch_sha256"] != batch_hash:
                raise ValueError("batch receipt identity mismatch")
        else:
            self.state = {"schema_version": 2, "batch_sha256": batch_hash, "cases": [], "real_calls": 0,
                          "real_calls_semantics": "closed_case_calls_only", "calls_started_observed": 0,
                          "blocked_attempts": 0}

    def begin(self, case_id, cap):
        history = self.state["cases"]
        if any(c["status"] != "closed" for c in history):
            raise ValueError("previous case teardown/accounting unproven")
        for previous in history:
            if _pid_running(previous["pid"]):
                raise ValueError("previous case process has not exited")
            # Closed guards cannot start more real calls. Reconcile any late
            # locally blocked attempts only after OS-level process exit.
            receipt = json.loads(Path(previous["receipt_path"]).read_text(encoding="utf-8"))
            if len(receipt["calls"]) != previous["real_calls"] or any(
                not _locally_terminal(c, receipt) for c in receipt["calls"]
            ):
                raise ValueError("closed case real-call accounting changed")
            previous["blocked_attempts"] = receipt["blocked_attempts"]
            previous["receipt_sha256"] = _normalized_file_hash(Path(previous["receipt_path"]))
        self.state["blocked_attempts"] = sum(c["blocked_attempts"] for c in history)
        if len(history) >= len(self.case_ids) or case_id != self.case_ids[len(history)]:
            raise ValueError("case already consumed or outside frozen order")
        if self.state["real_calls"] + cap > self.call_cap:
            raise ValueError("batch budget cannot admit full frozen case cap")
        history.append({"id": case_id, "status": "started", "call_cap": cap, "started_at": _time(), "pid": os.getpid()})
        _write(self.path, self.state)

    def finish(self, receipt_path, *, candidate_id, source_digest):
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        record = self.state["cases"][-1]
        calls = receipt["calls"]
        if receipt["candidate_id"] != candidate_id or receipt["source_digest"] != source_digest:
            raise ValueError("case receipt identity mismatch")
        # Preserve consumption even when teardown fails. This is a checkpoint,
        # not a live meter: the per-case receipt remains authoritative.
        record["calls_started_observed"] = len(calls)
        self.state["calls_started_observed"] = sum(c.get("calls_started_observed", c.get("real_calls", 0)) for c in self.state["cases"])
        _write(self.path, self.state)
        if any(not _locally_terminal(c, receipt) for c in calls):
            raise ValueError("in-flight or unknown Provider consumption")
        if receipt["call_cap"] != record["call_cap"] or len(calls) > record["call_cap"]:
            raise ValueError("case receipt cap mismatch")
        if [c["ordinal"] for c in calls] != list(range(1, len(calls) + 1)):
            raise ValueError("case receipt sequence mismatch")
        if not receipt.get("terminal_failure"):
            raise ValueError("case guard not closed")
        record.update(status="closed", finished_at=_time(), real_calls=len(calls),
                      blocked_attempts=receipt["blocked_attempts"], terminal_failure=receipt["terminal_failure"],
                      receipt_path=str(receipt_path.resolve()), receipt_sha256=_normalized_file_hash(receipt_path))
        self.state["real_calls"] += len(calls)
        self.state["blocked_attempts"] += receipt["blocked_attempts"]
        _write(self.path, self.state)


def run_case(root: Path, batch_path: Path, launcher_path: Path, case_id: str,
             *, preflight_only: bool = False) -> None:
    """One frozen case, self-contained: preflight, env derivation, execution.

    Split out of ``main`` (which stays the argparse CLI) so a batch runner
    can loop cases in one process without re-implementing authorization,
    environment or ledger semantics.
    """
    batch, cases, checks = preflight(root, batch_path, launcher_path)
    index = [c["matrix_case_id"] for c in cases].index(case_id)
    case = cases[index]
    case_path = root / batch["cases"][index]["path"]
    os.environ.update(
        MODEL_ID=case["model"], QUALITY_JUDGE_MODEL=case["model"], MAX_TOKENS="8000",
        MCP_ENABLED="false", SKILL_AUTO_DISCOVER="false",
        WORKSPACE_DIR=str(root / case["writes"]["workspace_dir"]),
        SESSIONS_DIR=str(root / case["writes"]["sessions_dir"]),
        LOG_FILE=str(root / case["writes"]["workspace_dir"] / "server.log"),
        DATA_AGENT_WEB_HOST="127.0.0.1", DATA_AGENT_WEB_PORT=str(case["port"]),
        # These are derived from the batch candidate after its one external
        # digest has been authorized and every frozen component has been
        # recomputed.  The nested single-case guard still verifies them, but
        # operators no longer have to transcribe the same identities again.
        AUTHORIZED_SOURCE_DIGEST=checks["SOURCE_DIGEST"],
        AUTHORIZED_LAUNCHER_SHA256=checks["LAUNCHER_SHA256"],
        AUTHORIZED_CANDIDATE_SHA256=_normalized_file_hash(case_path),
        AUTHORIZED_PROMPT_SHA256=_sha256_bytes(case["prompt"].encode("utf-8")),
        AUTHORIZED_ORACLE_SHA256=_canonical_json_hash(case["oracle"]),
    )
    # The single-case server's read-only preflight also checks credentials,
    # workspace configuration and fresh case paths. No marker or ledger writes.
    os.environ["DATA_AGENT_PREFLIGHT_ONLY"] = "1"
    run_authorized_browser_server(root=root, candidate_path=case_path, launcher_path=launcher_path)
    if preflight_only:
        return
    require_network_enabled_execution()
    _require_current_supervisor(root, case, launcher_path)
    isolation = root / batch["isolation_root"]
    with process_lock(isolation / "batch.lock"):
        ledger = BatchLedger(isolation / "provider-batch.json", batch_hash=checks["BATCH_SHA256"],
                             case_ids=[c["matrix_case_id"] for c in cases], call_cap=batch["call_cap"])
        from scripts.acceptance.browser_process import require_graceful_exit
        for previous in ledger.state["cases"]:
            if previous.get("status") != "closed":
                raise ValueError("previous case teardown/accounting unproven")
            previous_case = cases[[item["matrix_case_id"] for item in cases].index(previous["id"])]
            proof = _inside(root, previous_case["writes"]["process_control_dir"]) / "process-exit.json"
            require_graceful_exit(proof, expected_pid=previous["pid"])
        stop_reason = batch_stop_reason([c for c in ledger.state["cases"] if c.get("status") == "closed"])
        if stop_reason:
            raise ValueError("Provider failure stopped the whole batch: " + stop_reason)
        ledger.begin(case_id, case["provider_policy"]["call_cap"])
        os.environ.pop("DATA_AGENT_PREFLIGHT_ONLY", None)
        try:
            run_authorized_browser_server(root=root, candidate_path=case_path,
                                          launcher_path=launcher_path, keep_guard_installed=True)
        finally:
            # No try/except: missing/uncertain receipts must leave a durable
            # started marker, blocking the batch instead of resetting counts.
            ledger.finish(root / case["writes"]["provider_receipt_path"],
                          candidate_id=case["candidate_id"], source_digest=checks["SOURCE_DIGEST"])


def main(*, root: Path, batch_path: Path, launcher_path: Path):
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=[f"M{i:02d}" for i in range(1, 7)], required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    run_case(root, batch_path, launcher_path, args.case, preflight_only=args.preflight_only)


if __name__ == "__main__":
    # One-case OS-process entry: ``python -m scripts.acceptance.real_provider_browser_batch``.
    # The batch runner spawns one of these per frozen case; each child runs its
    # own preflight and derives every authorized value from the batch digest.
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--case", choices=[f"M{i:02d}" for i in range(1, 7)], required=True)
    parser.add_argument("--preflight-only", action="store_true")
    _args = parser.parse_args()
    run_case(Path(_args.root).resolve(), Path(_args.batch), Path(_args.launcher),
             _args.case, preflight_only=_args.preflight_only)
