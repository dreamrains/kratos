"""Freeze or serve one bounded, opt-in natural Provider typed-claim trial.

The existing application/browser performs the matrix. This launcher reuses the
P08 one-shot policy and ProviderLedger; preflight performs zero Provider calls.
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

try:
    from scripts.testing.run_p08_real_matrix import (
        ProviderLedger, _install_one_shot_request_policy,
    )
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    # Direct `python scripts/testing/run_typed_trial_real.py` adds this file's
    # directory rather than the repository root to sys.path.
    from run_p08_real_matrix import ProviderLedger, _install_one_shot_request_policy


SCHEMA = "typed_trial.real_freeze.v1"
CONTRACT = Path("scripts/testing/typed_trial_real_contract.json")
CALL_CAP = 30
OUTPUT_CAP = 65536
TIMEOUT_SECONDS = 600


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _value_sha256(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _require_clean_source(root: Path) -> None:
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("tracked source must be clean before freeze or serving")


def _contract(root: Path) -> dict:
    path = root / CONTRACT
    value = json.loads(path.read_text(encoding="utf-8"))
    if (value.get("schema_version") != "typed_trial.real_matrix.v1"
            or value.get("matrix") != ["M03-P", "M03-N"]
            or set(value.get("scenarios", {})) != set(value["matrix"])):
        raise SystemExit("typed trial contract mismatch")
    expected = [f"F-SRC{number}.csv" for number in range(1, 7)]
    for name in value["matrix"]:
        case = value["scenarios"][name]
        if (case.get("fixtures") != expected or not case.get("prompt")
                or not case.get("oracles")):
            raise SystemExit(f"incomplete typed trial case: {name}")
    return value


def _write_fixtures(directory: Path) -> None:
    for number in range(1, 7):
        with (directory / f"F-SRC{number}.csv").open(
            "w", newline="", encoding="utf-8",
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(["source", "date", "amount"])
            writer.writerow([f"source_{number}", "2026-09-01", number * 10])
            writer.writerow([f"source_{number}", "2026-09-02", number * 11])


def _isolation(run_dir: Path, *, network: bool) -> None:
    os.environ.update({
        "WORKSPACE_DIR": str(run_dir / "workspace"),
        "SESSIONS_DIR": str(run_dir / "sessions"),
        "MCP_ENABLED": "false",
        "SKILL_AUTO_DISCOVER": "false",
        "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "1" if network else "0",
    })


def _identity(root: Path, run_dir: Path, port: int) -> dict:
    from data_agent.config import get_config

    cfg = get_config()
    if not cfg.api_base or not cfg.api_key:
        raise SystemExit("real Provider configuration is incomplete")
    contract = _contract(root)
    return {
        "schema_version": SCHEMA,
        "source_commit": _git(root, "rev-parse", "HEAD"),
        "launcher_digest": _sha256(Path(__file__).resolve()),
        "contract_digest": _sha256(root / CONTRACT),
        "matrix": contract["matrix"],
        "scenario_digests": {
            name: {
                "prompt": _value_sha256(contract["scenarios"][name]["prompt"]),
                "oracles": _value_sha256(contract["scenarios"][name]["oracles"]),
                "fixtures": contract["scenarios"][name]["fixtures"],
            }
            for name in contract["matrix"]
        },
        "operator_protocol": contract["operator_protocol"],
        "fixture_digests": {
            path.name: _sha256(path) for path in sorted((run_dir / "fixtures").glob("*.csv"))
        },
        "model": cfg.model_id,
        "provider_endpoint": cfg.api_base,
        "request_policy": "one_shot_no_retry",
        "call_cap": CALL_CAP,
        "output_cap_per_call": OUTPUT_CAP,
        "timeout_seconds_per_call": TIMEOUT_SECONDS,
        "service_port": port,
        "provider_ledger": str((run_dir / "provider-calls.jsonl").relative_to(root)),
        "workspace_dir": str((run_dir / "workspace").relative_to(root)),
        "sessions_dir": str((run_dir / "sessions").relative_to(root)),
    }


def preflight(root: Path, run_dir: Path, port: int) -> dict:
    _require_clean_source(root)
    if not run_dir.is_relative_to((root / "tmp").resolve()) or run_dir.exists():
        raise SystemExit("run directory must be a fresh path inside repository tmp")
    (run_dir / "fixtures").mkdir(parents=True)
    (run_dir / "workspace").mkdir()
    (run_dir / "sessions").mkdir()
    _write_fixtures(run_dir / "fixtures")
    _isolation(run_dir, network=False)
    manifest = {
        **_identity(root, run_dir, port),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "freeze.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return manifest


def revalidate(root: Path, run_dir: Path, port: int) -> dict:
    _require_clean_source(root)
    freeze = run_dir / "freeze.json"
    if not freeze.is_file() or (run_dir / "provider-calls.jsonl").exists():
        raise SystemExit("authorized serving needs an unused freeze and no ledger")
    if not (run_dir / "workspace").is_dir() or not (run_dir / "sessions").is_dir():
        raise SystemExit("isolation directories missing")
    _isolation(run_dir, network=False)
    frozen = json.loads(freeze.read_text(encoding="utf-8"))
    identity = _identity(root, run_dir, port)
    if any(frozen.get(key) != value for key, value in identity.items()):
        raise SystemExit("frozen source, Provider, contract, fixture or budget mismatch")
    return frozen


def serve(root: Path, run_dir: Path, port: int) -> None:
    frozen = revalidate(root, run_dir, port)
    _isolation(run_dir, network=True)
    import data_agent.llm.client as client_module
    from data_agent.agent.loop import AgentLoop
    from data_agent.web.app import create_app

    _install_one_shot_request_policy(client_module)
    original_init = client_module.LLMClient.__init__

    def bounded_init(client, *args, **kwargs):
        kwargs.setdefault("max_tokens", OUTPUT_CAP)
        kwargs.setdefault("timeout", TIMEOUT_SECONDS)
        original_init(client, *args, **kwargs)

    client_module.LLMClient.__init__ = bounded_init
    original_completion = client_module.completion

    def bounded_completion(*args, **kwargs):
        requested = kwargs.get("max_tokens")
        timeout = kwargs.get("timeout")
        if (not isinstance(requested, int) or requested <= 0 or requested > OUTPUT_CAP
                or not isinstance(timeout, (int, float)) or timeout <= 0
                or timeout > TIMEOUT_SECONDS):
            raise RuntimeError("typed trial Provider request exceeds frozen bounds")
        return original_completion(*args, **kwargs)

    ledger = ProviderLedger(run_dir / "provider-calls.jsonl", CALL_CAP)
    client_module.completion = ledger.wrap(bounded_completion)
    original_loop_init = AgentLoop.__init__

    def typed_trial_init(loop, *args, **kwargs):
        kwargs["typed_trial"] = True
        original_loop_init(loop, *args, **kwargs)

    AgentLoop.__init__ = typed_trial_init
    app = create_app()

    @app.get("/__typed_trial__/health")
    def typed_trial_health():
        return {"ok": True, "provider_enabled": True, "typed_trial": True,
                "source_commit": frozen["source_commit"], "matrix": frozen["matrix"]}

    print(json.dumps({"freeze": str(run_dir / "freeze.json"), "provider_ledger":
                      frozen["provider_ledger"], "call_cap": CALL_CAP}, ensure_ascii=True))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--preflight", action="store_true")
    choice.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    run_dir = args.run_dir.resolve()
    if args.preflight:
        manifest = preflight(root, run_dir, args.port)
        print(json.dumps({"preflight": "passed", **manifest}, ensure_ascii=True))
    else:
        serve(root, run_dir, args.port)


if __name__ == "__main__":
    main()
