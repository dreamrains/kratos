"""Serve one isolated, auditable P08 real-Provider matrix batch.

The browser drives M01-M06 through the normal Web UI.  This launcher only
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


DEFAULT_CALL_CAP = 120
MATRIX_IDS = ["M01", "M02", "M03", "M04", "M05", "M06"]
MATRIX_SCHEMA_VERSION = "p08.real_matrix.v2"
MATRIX_CONTRACT_PATH = Path("scripts/testing/p08_real_matrix_contract.json")


def _frozen_matrix_contract(root: Path, port: int) -> dict[str, Any]:
    contract_path = (root / MATRIX_CONTRACT_PATH).resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("matrix") != MATRIX_IDS or set(contract.get("scenario_inputs", {})) != set(MATRIX_IDS):
        raise SystemExit("P08 matrix contract is incomplete or out of order")
    plan_path = (root / contract["matrix_plan"]["path"]).resolve()
    contract["matrix_plan"]["sha256"] = _sha256(plan_path)
    contract["contract_file"] = {
        "path": MATRIX_CONTRACT_PATH.as_posix(),
        "sha256": _sha256(contract_path),
    }
    contract["operator_protocol"]["service_port"] = port
    return contract


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


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
    _write_csv(fixtures / "M04-hyp-v1.csv", ["date", "amount"], [["2026-09-01", 10], ["2026-09-02", 20], ["2026-09-03", 20]])
    _write_csv(fixtures / "M04-hyp-v2.csv", ["date", "amount"], [["2026-09-01", 10], ["2026-09-02", 10], ["2026-09-03", 10]])


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _configure_isolation(run_dir: Path) -> None:
    os.environ.update({
        "WORKSPACE_DIR": str(run_dir / "workspace"),
        "SESSIONS_DIR": str(run_dir / "sessions"),
        "MCP_ENABLED": "false",
        "SKILL_AUTO_DISCOVER": "false",
        "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "1",
    })


def _prepare(root: Path, run_dir: Path, call_cap: int, port: int) -> dict[str, Any]:
    tmp_root = (root / "tmp").resolve()
    if not run_dir.is_relative_to(tmp_root) or run_dir.exists():
        raise SystemExit("run directory must be a fresh path inside repository tmp")
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
        "launcher_digest": _sha256(Path(__file__).resolve()),
        "request_policy": "one_shot",
        "model": cfg.model_id,
        "provider_endpoint": cfg.api_base,
        "call_cap": call_cap,
        "fixtures": {path.name: _sha256(path) for path in sorted(fixtures.glob("*.csv"))},
        **_frozen_matrix_contract(root, port),
        "workspace_dir": str(workspace.relative_to(root)),
        "sessions_dir": str(sessions.relative_to(root)),
        "provider_ledger": str((run_dir / "provider-calls.jsonl").relative_to(root)),
    }
    (run_dir / "freeze.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _load_frozen_preflight(root: Path, run_dir: Path, call_cap: int, port: int) -> dict[str, Any]:
    """Revalidate one preflight before serving it; never regenerate its inputs."""
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
        "call_cap": call_cap,
        **_frozen_matrix_contract(root, port),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise SystemExit(f"frozen preflight mismatch for {key}")
    fixtures = run_dir / "fixtures"
    actual_fixtures = {path.name: _sha256(path) for path in sorted(fixtures.glob("*.csv"))}
    if actual_fixtures != manifest.get("fixtures"):
        raise SystemExit("frozen preflight fixture digest mismatch")
    if not (run_dir / "workspace").is_dir() or not (run_dir / "sessions").is_dir():
        raise SystemExit("frozen preflight isolation directories are missing")
    _configure_isolation(run_dir)
    from data_agent.config import get_config
    cfg = get_config()
    if not cfg.api_base or not cfg.api_key:
        raise SystemExit("real Provider configuration is incomplete")
    if cfg.model_id != manifest.get("model") or cfg.api_base != manifest.get("provider_endpoint"):
        raise SystemExit("frozen preflight Provider configuration mismatch")
    return manifest


def _install_one_shot_request_policy(client_module: Any) -> None:
    """Make this acceptance process count one physical attempt per LLM request."""
    client_class = client_module.LLMClient
    if getattr(client_class, "_p08_one_shot_init_installed", False):
        return
    original_init = client_class.__init__

    def acceptance_init(self, *args, **kwargs):
        from data_agent.llm.request_policy import ONE_SHOT
        kwargs["request_policy"] = ONE_SHOT
        original_init(self, *args, **kwargs)

    client_class.__init__ = acceptance_init
    client_class._p08_one_shot_init_installed = True


class ProviderLedger:
    def __init__(self, path: Path, cap: int) -> None:
        self.path, self.cap, self.count = path, cap, 0
        self._lock = threading.Lock()

    def _write(self, event: str, **payload: Any) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": time.time(), "event": event, **payload}, ensure_ascii=False) + "\n")

    def wrap(self, completion):
        def audited_completion(*args, **kwargs):
            with self._lock:
                if self.count >= self.cap:
                    self._write("denied", reason="call_cap_reached", cap=self.cap)
                    raise RuntimeError("P08 Provider call cap reached")
                self.count += 1
                call_number = self.count
                self._write("started", call_number=call_number, model=str(kwargs.get("model") or ""), stream=bool(kwargs.get("stream")))
            try:
                result = completion(*args, **kwargs)
            except Exception as exc:
                with self._lock:
                    self._write("failed", call_number=call_number, error_type=type(exc).__name__)
                raise
            with self._lock:
                self._write("dispatched", call_number=call_number)
            return result
        return audited_completion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--call-cap", type=int, default=DEFAULT_CALL_CAP)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    if args.call_cap <= 0:
        raise SystemExit("call cap must be positive")
    root = Path(__file__).resolve().parents[2]
    run_dir = args.run_dir.resolve()
    if args.preflight:
        manifest = _prepare(root, run_dir, args.call_cap, args.port)
        print(_stdout_manifest("passed", manifest))
        return
    if not args.authorized:
        raise SystemExit("real Provider serving requires --authorized")
    manifest = _load_frozen_preflight(root, run_dir, args.call_cap, args.port)
    print(_stdout_manifest("revalidated", manifest))

    import data_agent.llm.client as client_module
    _install_one_shot_request_policy(client_module)
    ledger = ProviderLedger(run_dir / "provider-calls.jsonl", args.call_cap)
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
