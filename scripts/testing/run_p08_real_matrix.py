"""Serve one isolated, auditable P08 real-Provider matrix batch.

The frozen HTTP driver drives M01-M06 through the normal app APIs.  This launcher only
creates fresh fixtures, freezes non-secret batch identity, and records each
physical Provider admission.  It deliberately has no retry, resume, or
scenario-selection feature.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any


DEFAULT_CALL_CAP = 180
P08_OUTPUT_MAX_TOKENS = 65_536
MATRIX_IDS = ["M01", "M02", "M03", "M04", "M05", "M06"]
MATRIX_SCHEMA_VERSION = "p08.real_matrix.v3"
MATRIX_CONTRACT_PATH = Path("scripts/testing/p08_real_matrix_contract.json")
HTTP_DRIVER_PATH = Path("scripts/testing/run_p08_http_matrix.py")


def _semantic_review_mode() -> str:
    if os.environ.get("DATA_AGENT_SEMANTIC_AUDIT_TRIAL", "") not in {"", "0"}:
        raise SystemExit("semantic audit trial mode is retired; v2 uses bounded_once")
    return "bounded_once"


def _frozen_matrix_contract(root: Path, port: int) -> dict[str, Any]:
    contract_path = (root / MATRIX_CONTRACT_PATH).resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("matrix") != MATRIX_IDS or set(contract.get("scenario_inputs", {})) != set(MATRIX_IDS):
        raise SystemExit("P08 matrix contract is incomplete or out of order")
    if contract.get("operator_protocol", {}).get("control_route") != "local_http_api":
        raise SystemExit("P08 HTTP batch requires the frozen local HTTP control route")
    plan_path = (root / contract["matrix_plan"]["path"]).resolve()
    contract["matrix_plan"]["sha256"] = _sha256(plan_path)
    contract["contract_file"] = {
        "path": MATRIX_CONTRACT_PATH.as_posix(),
        "sha256": _sha256(contract_path),
    }
    contract["http_driver_digest"] = _sha256((root / HTTP_DRIVER_PATH).resolve())
    contract["operator_protocol"]["service_port"] = port
    return contract


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _supplement_identity(root: Path, prior_run: Path | None) -> dict[str, Any] | None:
    """Bind a final-scenario addendum to one immutable call-cap failure."""
    if prior_run is None:
        return None
    prior = prior_run.resolve()
    if not prior.is_relative_to((root / "tmp").resolve()):
        raise SystemExit("supplement source must be inside repository tmp")
    freeze_path = prior / "freeze.json"
    ledger_path = prior / "provider-calls.jsonl"
    evidence_path = prior / "http-matrix.jsonl"
    if not all(path.is_file() for path in (freeze_path, ledger_path, evidence_path)):
        raise SystemExit("supplement source lacks frozen matrix evidence")
    base = json.loads(freeze_path.read_text(encoding="utf-8"))
    if base.get("matrix") != MATRIX_IDS or base.get("operator_protocol", {}).get("control_route") != "local_http_api":
        raise SystemExit("supplement source is not the complete HTTP matrix")
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cap = base.get("call_cap")
    started = [event.get("call_number") for event in events if event.get("event") == "started"]
    dispatched = [event.get("call_number") for event in events if event.get("event") == "dispatched"]
    settled = [event.get("call_number") for event in events
               if event.get("event") in {"completed", "stream_exhausted"}]
    denied = [event for event in events if event.get("event") == "denied"]
    if (not isinstance(cap, int) or started != list(range(1, cap + 1))
            or sorted(dispatched) != started or sorted(settled) != started
            or any(event.get("event") in {"failed", "stream_failed", "stream_closed"} for event in events)
            or len(denied) != 1 or denied[0].get("reason") != "call_cap_reached"
            or events[-1] != denied[0]):
        raise SystemExit("supplement source is not a clean call-cap stop")
    records = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    prior_scenarios = MATRIX_IDS[:-1]
    if [item.get("scenario") for item in records if item.get("action") == "ledger_reconciled"] != prior_scenarios:
        raise SystemExit("earlier scenarios lack sequential ledger reconciliation")
    final = records[-1] if records else {}
    if (final.get("scenario") != "M06" or final.get("action") != "persisted_reload"
            or final.get("run_state", {}).get("status") != "failed"
            or "resume: failed" not in final.get("errors", [])):
        raise SystemExit("M06 did not end as the recorded call-cap failure")
    session_id = final.get("session_id")
    state_path = prior / "sessions" / str(session_id) / "analysis_state.json"
    if not state_path.is_file() or json.loads(state_path.read_text(encoding="utf-8")).get("pending_confirmations"):
        raise SystemExit("failed M06 still has a resumable confirmation")
    return {
        "prior_run": prior.relative_to(root).as_posix(),
        "prior_source_commit": base.get("source_commit"),
        "prior_freeze_sha256": _sha256(freeze_path),
        "prior_ledger_sha256": _sha256(ledger_path),
        "prior_http_evidence_sha256": _sha256(evidence_path),
        "scenario": "M06",
    }


def _stdout_manifest(status: str, manifest: dict[str, Any]) -> str:
    """Return console-safe JSON while freeze.json retains readable UTF-8 text."""
    return json.dumps({"preflight": status, **manifest}, ensure_ascii=True)


def _write_csv(path: Path, columns: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def _write_fixtures(fixtures: Path) -> None:
    _write_csv(
        fixtures / "M01-sales.csv",
        ["order_id", "date", "channel", "amount"],
        [[f"O{i:02d}", f"2026-09-{i:02d}", "all", 10] for i in range(1, 13)],
    )
    _write_csv(
        fixtures / "M01-action.csv",
        ["date", "amount", "campaign_cost", "net_contribution", "orders"],
        [[f"2026-09-{day:02d}", 100, 20, 80, 10] for day in range(7, 14)]
        + [[f"2026-09-{day:02d}", 110, 25, 85, 11] for day in range(14, 21)],
    )
    _write_csv(
        fixtures / "M02-retention.csv",
        ["day", "retention"],
        [[day, value] for day, value in enumerate((0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10), 1)],
    )
    for number in range(1, 7):
        _write_csv(
            fixtures / f"M03-source-{number}.csv",
            ["source", "date", "amount"],
            [[f"source_{number}", "2026-09-01", number * 10], [f"source_{number}", "2026-09-02", number * 11]],
        )
    for filename, revenue in (("M06-promo.csv", [20,30,25,35]), ("M06-promo-v2.csv", [30,30,25,35])):
        _write_csv(fixtures / filename,
                   ["order_id", "channel", "order_amount", "incremental_revenue", "coupon_cost", "channel_cost"],
                   [[f"P{i+1}", "all", amount, value, coupon, channel]
                    for i,(amount,value,coupon,channel) in enumerate(zip([20,25,35,40],revenue,[3,4,2,5],[2,3,4,1]))])
    _write_csv(fixtures / "M04-hyp-v1.csv", ["date", "amount"], [["2026-09-01", 10], ["2026-09-02", 20], ["2026-09-03", 20]])
    _write_csv(fixtures / "M04-hyp-v2.csv", ["date", "amount"], [["2026-09-01", 10], ["2026-09-02", 10], ["2026-09-03", 10]])


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _require_clean_source(root: Path) -> None:
    """A commit is an exact batch identity only when no source edits shadow it."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, text=True, capture_output=True, check=True,
    )
    if result.stdout.strip():
        raise SystemExit("real Provider freeze requires a clean committed source tree")


def _configure_isolation(run_dir: Path, *, network_enabled: bool = False) -> None:
    os.environ.update({
        "WORKSPACE_DIR": str(run_dir / "workspace"),
        "SESSIONS_DIR": str(run_dir / "sessions"),
        "MCP_ENABLED": "false",
        "SKILL_AUTO_DISCOVER": "false",
        "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "1" if network_enabled else "0",
        "MAX_TOKENS": str(P08_OUTPUT_MAX_TOKENS),
    })


def _source_inventory(root: Path) -> dict[str, str]:
    suffixes = {".py", ".js", ".html", ".css", ".json", ".md", ".yaml", ".yml", ".txt"}
    paths = [p for name in ("src", "scripts", "tests") for p in (root / name).rglob("*")
             if p.is_file() and p.suffix in suffixes and "__pycache__" not in p.parts]
    paths += [root / name for name in ("AGENTS.md", "pyproject.toml", "uv.lock") if (root / name).is_file()]
    return {p.relative_to(root).as_posix(): _sha256(p) for p in sorted(paths)}


def _runtime_environment() -> dict[str, Any]:
    import sys
    from importlib.metadata import distributions
    return {"python":sys.version,"executable":sys.executable,
            "packages":{d.metadata["Name"]:d.version for d in distributions() if d.metadata["Name"]}}


def _public_config(cfg: Any) -> dict[str, Any]:
    return json.loads(cfg.model_dump_json(exclude={"api_key"}))


def _prepare(root: Path, run_dir: Path, call_cap: int, port: int,
             prior_run: Path | None = None) -> dict[str, Any]:
    _require_clean_source(root)
    tmp_root = (root / "tmp").resolve()
    if not run_dir.is_relative_to(tmp_root) or run_dir.exists():
        raise SystemExit("run directory must be a fresh path inside repository tmp")
    supplement = _supplement_identity(root, prior_run)
    fixtures = run_dir / "fixtures"
    workspace = run_dir / "workspace"
    sessions = run_dir / "sessions"
    fixtures.mkdir(parents=True)
    workspace.mkdir()
    sessions.mkdir()
    _write_fixtures(fixtures)

    _configure_isolation(run_dir)
    from data_agent.config import get_config
    cfg = get_config()
    if not cfg.api_base or not cfg.api_key:
        raise SystemExit("real Provider configuration is incomplete")
    manifest = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _git_head(root),
        "source_inventory": _source_inventory(root),
        "agent_config": _public_config(cfg),
        "runtime_environment": _runtime_environment(),
        "request_capture": "full non-secret request JSON and response/chunks; request/response SHA in the same authoritative ledger",
        "failure_policy": "serial admission; latch on first Provider/stream/accounting failure or unresolved in-flight call; no retry/fallback/resume",
        "launcher_digest": _sha256(Path(__file__).resolve()),
        "request_policy": "one_shot",
        "semantic_review_mode": _semantic_review_mode(),
        "model": cfg.model_id,
        "provider_endpoint": cfg.api_base,
        "max_tokens_per_call": cfg.max_tokens,
        "call_cap": call_cap,
        "execution_scope": ["M06"] if supplement else MATRIX_IDS,
        "supplement_of": supplement,
        "fixtures": {path.name: _sha256(path) for path in sorted(fixtures.glob("*.csv"))},
        **_frozen_matrix_contract(root, port),
        "workspace_dir": str(workspace.relative_to(root)),
        "sessions_dir": str(sessions.relative_to(root)),
        "provider_ledger": str((run_dir / "provider-calls.jsonl").relative_to(root)),
    }
    if supplement:
        base = json.loads((root / supplement["prior_run"] / "freeze.json").read_text(encoding="utf-8"))
        if (base.get("model") != manifest["model"]
                or base.get("provider_endpoint") != manifest["provider_endpoint"]
                or base.get("max_tokens_per_call") != manifest["max_tokens_per_call"]
                or base.get("semantic_review_mode") != manifest["semantic_review_mode"]
                or base.get("fixtures") != manifest["fixtures"]
                or base.get("scenario_inputs") != manifest["scenario_inputs"]
                or base.get("matrix_plan", {}).get("sha256") != manifest["matrix_plan"]["sha256"]
                or base.get("contract_file", {}).get("sha256") != manifest["contract_file"]["sha256"]):
            raise SystemExit("supplement changes model, mode or frozen scenario inputs")
    (run_dir / "freeze.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _load_frozen_preflight(root: Path, run_dir: Path, call_cap: int, port: int,
                           prior_run: Path | None = None) -> dict[str, Any]:
    """Revalidate one preflight before serving it; never regenerate its inputs."""
    _require_clean_source(root)
    freeze_path = run_dir / "freeze.json"
    if not freeze_path.is_file():
        raise SystemExit("authorized serving requires a completed preflight freeze.json")
    if (run_dir / "provider-calls.jsonl").exists():
        raise SystemExit("authorized serving refuses a run directory with an existing Provider ledger")
    manifest = json.loads(freeze_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "source_commit": _git_head(root),
        "launcher_digest": _sha256(Path(__file__).resolve()),
        "request_policy": "one_shot",
        "semantic_review_mode": _semantic_review_mode(),
        "call_cap": call_cap,
        "execution_scope": ["M06"] if prior_run else MATRIX_IDS,
        "supplement_of": _supplement_identity(root, prior_run),
        **_frozen_matrix_contract(root, port),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise SystemExit(f"frozen preflight mismatch for {key}")
    if manifest.get("runtime_environment") != _runtime_environment():
        raise SystemExit("frozen Python/runtime dependency environment changed")
    if manifest.get("source_inventory") != _source_inventory(root):
        raise SystemExit("frozen source inventory changed, including ignored runtime assets")
    fixtures = run_dir / "fixtures"
    actual_fixtures = {path.name: _sha256(path) for path in sorted(fixtures.glob("*.csv"))}
    if actual_fixtures != manifest.get("fixtures"):
        raise SystemExit("frozen preflight fixture digest mismatch")
    if not (run_dir / "workspace").is_dir() or not (run_dir / "sessions").is_dir():
        raise SystemExit("frozen preflight isolation directories are missing")
    _configure_isolation(run_dir, network_enabled=True)
    from data_agent.config import get_config
    cfg = get_config()
    if not cfg.api_base or not cfg.api_key:
        raise SystemExit("real Provider configuration is incomplete")
    if _public_config(cfg) != manifest.get("agent_config"):
        raise SystemExit("frozen complete non-secret agent configuration mismatch")
    if (cfg.model_id != manifest.get("model")
            or cfg.api_base != manifest.get("provider_endpoint")
            or cfg.max_tokens != manifest.get("max_tokens_per_call")
            or cfg.max_tokens != P08_OUTPUT_MAX_TOKENS):
        raise SystemExit("frozen preflight Provider configuration mismatch")
    return manifest


def _install_one_shot_request_policy(client_module: Any, ledger=None) -> None:
    """Make this acceptance process count one physical attempt per LLM request."""
    client_class = client_module.LLMClient
    if getattr(client_class, "_p08_one_shot_init_installed", False):
        return
    if ledger is not None:
        original_request = client_class._request
        def deadline_accounted_request(self, kwargs):
            try:
                return original_request(self, kwargs)
            except client_module.HardRequestTimeout:
                with ledger._lock:
                    ledger._provider_fault = True
                    ledger._record_locked("gate_fault", reason="host_deadline_exceeded")
                raise
        client_class._request = deadline_accounted_request
    original_init = client_class.__init__

    def acceptance_init(self, *args, **kwargs):
        from data_agent.llm.request_policy import ONE_SHOT
        kwargs["request_policy"] = ONE_SHOT
        original_init(self, *args, **kwargs)

    client_class.__init__ = acceptance_init
    client_class._p08_one_shot_init_installed = True


class ProviderLedger:
    def __init__(self, path: Path, cap: int, *, model: str | None = None,
                 endpoint: str | None = None) -> None:
        self.path, self.cap, self.count = path, cap, 0
        self.model, self.endpoint = model, endpoint
        self._lock = threading.Lock()
        self._fault: BaseException | None = None
        self._provider_fault = False
        self._pending: set[int] = set()

    def _finish(self, event: str, call_number: int, **payload: Any) -> None:
        with self._lock:
            self._record_locked(event, call_number=call_number, **payload)
            self._pending.discard(call_number)
            if event not in {"completed", "stream_exhausted"}:
                self._provider_fault = True

    def _capture(self, call_number: int, kind: str, payload: Any) -> tuple[str, str]:
        directory = self.path.parent / "provider-requests"
        directory.mkdir(exist_ok=True)
        path = directory / f"{call_number:04d}-{kind}.json"
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with path.open("xb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        return path.relative_to(self.path.parent).as_posix(), "sha256:" + hashlib.sha256(raw).hexdigest()

    def _write(self, event: str, **payload: Any) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": time.time(), "event": event, **payload}, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _record_locked(self, event: str, **payload: Any) -> None:
        if self._fault is not None:
            raise RuntimeError("P08 Provider ledger is unavailable") from self._fault
        try:
            self._write(event, **payload)
        except BaseException as exc:
            self._fault = exc
            raise RuntimeError("P08 Provider ledger write failed") from exc

    def _record(self, event: str, **payload: Any) -> None:
        with self._lock:
            self._record_locked(event, **payload)

    def wrap(self, completion):
        def audited_completion(*args, **kwargs):
            with self._lock:
                if self._fault is not None:
                    raise RuntimeError("P08 Provider ledger is unavailable") from self._fault
                if self._provider_fault or self._pending:
                    reason = "provider_failure_latched" if self._provider_fault else "in_flight_or_unknown"
                    self._record_locked("denied", reason=reason)
                    self._provider_fault = True
                    raise RuntimeError("P08 Provider admission blocked: " + reason)
                if ((self.model is not None and kwargs.get("model") != self.model)
                        or (self.endpoint is not None and kwargs.get("api_base") != self.endpoint)
                        or kwargs.get("num_retries", 0) != 0
                        or (kwargs.get("max_tokens") is not None and (not isinstance(kwargs["max_tokens"], int) or kwargs["max_tokens"] > P08_OUTPUT_MAX_TOKENS))
                        or (self.model is not None and not isinstance(kwargs.get("max_tokens"), int))
                        or bool(args)):
                    self._record_locked("denied", reason="frozen_request_mismatch")
                    self._provider_fault = True
                    raise RuntimeError("P08 frozen Provider request mismatch")
                if self.count >= self.cap:
                    self._record_locked("denied", reason="call_cap_reached", cap=self.cap)
                    raise RuntimeError("P08 Provider call cap reached")
                self.count += 1
                call_number = self.count
                try:
                    request = {k: v for k, v in kwargs.items() if k not in {"api_key", "headers", "extra_headers"}}
                    request_path, request_sha = self._capture(call_number, "request", request)
                except BaseException as exc:
                    self._fault = exc
                    raise RuntimeError("P08 Provider request capture failed before transport") from exc
                self._record_locked("started", call_number=call_number, model=str(kwargs.get("model") or ""), stream=bool(kwargs.get("stream")), request_path=request_path, request_sha256=request_sha)
                self._pending.add(call_number)
            try:
                result = completion(*args, **kwargs)
            except BaseException as exc:
                self._finish("failed", call_number, error_type=type(exc).__name__)
                raise
            try:
                self._record("dispatched", call_number=call_number)
            except BaseException:
                if kwargs.get("stream"):
                    from data_agent.llm.request_policy import close_stream
                    close_stream(result)
                raise
            if kwargs.get("stream"):
                try:
                    return _LedgerStream(result, self, call_number)
                except BaseException as exc:
                    self._finish("stream_failed", call_number, error_type=type(exc).__name__)
                    raise
            try:
                payload = result.model_dump() if hasattr(result, "model_dump") else result
                response_path, response_sha = self._capture(call_number, "response", payload)
            except BaseException as exc:
                self._finish("failed", call_number, error_type=type(exc).__name__, reason="response_capture_failed")
                raise
            self._finish("completed", call_number, response_path=response_path, response_sha256=response_sha)
            return result
        return audited_completion


class _LedgerStream:
    """Account for a returned stream only after it is consumed or closed."""

    def __init__(self, source: Any, ledger: ProviderLedger, call_number: int) -> None:
        self.source = source
        self.iterator = iter(source)
        self.ledger = ledger
        self.call_number = call_number
        self._lock = threading.Lock()
        self._settled = False
        self.chunks = []

    def __iter__(self):
        return self

    def _settle(self, event: str, **payload: Any) -> None:
        with self._lock:
            if self._settled:
                return
            self._settled = True
        if event == "stream_exhausted":
            try:
                path, sha = self.ledger._capture(self.call_number, "response", self.chunks)
                payload.update(response_path=path, response_sha256=sha)
            except BaseException as exc:
                self.ledger._finish("stream_failed", self.call_number, reason="response_capture_failed", error_type=type(exc).__name__)
                raise
        self.ledger._finish(event, self.call_number, **payload)

    def __next__(self):
        try:
            chunk = next(self.iterator)
            self.chunks.append(chunk.model_dump() if hasattr(chunk, "model_dump") else chunk)
            return chunk
        except StopIteration:
            self._settle("stream_exhausted")
            raise
        except BaseException as exc:
            self._settle("stream_failed", error_type=type(exc).__name__)
            raise

    def close(self) -> bool:
        try:
            self._settle("stream_closed")
        finally:
            from data_agent.llm.request_policy import close_stream
            closed = close_stream(self.source)
        return closed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--call-cap", type=int, default=DEFAULT_CALL_CAP)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--supplement-of", type=Path,
                        help="prior complete matrix stopped at the Provider cap; run M06 only")
    args = parser.parse_args()
    if args.call_cap <= 0:
        raise SystemExit("call cap must be positive")
    root = Path(__file__).resolve().parents[2]
    run_dir = args.run_dir.resolve()
    if args.preflight:
        manifest = _prepare(root, run_dir, args.call_cap, args.port, args.supplement_of)
        print(_stdout_manifest("passed", manifest))
        return
    if not args.authorized:
        raise SystemExit("real Provider serving requires --authorized")
    manifest = _load_frozen_preflight(root, run_dir, args.call_cap, args.port, args.supplement_of)
    print(_stdout_manifest("revalidated", manifest))

    import data_agent.llm.client as client_module
    ledger = ProviderLedger(run_dir / "provider-calls.jsonl", args.call_cap,
                            model=manifest["model"], endpoint=manifest["provider_endpoint"])
    _install_one_shot_request_policy(client_module, ledger=ledger)
    client_module.completion = ledger.wrap(client_module.completion)
    from data_agent.web.app import create_app
    app = create_app()

    @app.get("/p08-freeze")
    def p08_freeze():
        return app.response_class((run_dir / "freeze.json").read_text(encoding="utf-8"), mimetype="application/json")

    @app.get("/p08-ledger")
    def p08_ledger():
        path = run_dir / "provider-calls.jsonl"
        return app.response_class(path.read_text(encoding="utf-8") if path.exists() else "", mimetype="application/x-ndjson")

    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
