"""Run one frozen, controlled Phase 5/C Shadow calibration batch.

This uses the existing P08 Provider ledger and client admission path. It has
no browser automation, no retries, no natural-model quality claim, and no
effect on published answers. Preflight is zero-call; --authorized is separate.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "docs/audit/2026-09-25-shadow-c-calibration-cases.json"
MAX_CALLS = 8
MAX_OUTPUT_TOKENS = 4096


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str:
    return _digest(path.read_bytes().replace(b"\r\n", b"\n"))


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _require_clean_checkout() -> None:
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT, text=True,
    )
    if status.strip():
        raise SystemExit("Shadow calibration requires a clean tracked checkout")


def _fixture_builder():
    # The four fixed cases intentionally use the same content-equivalent
    # receipt/trace fixture already exercised by the audit-view tests.
    path = ROOT / "tests/test_publication_audit_view_offline.py"
    spec = importlib.util.spec_from_file_location("shadow_calibration_fixture", path)
    if spec is None or spec.loader is None:
        raise SystemExit("controlled fixture module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._accepted_observation


def _prepare(run_dir: Path) -> dict[str, Any]:
    from data_agent.agent.publication_audit import build_shadow_audit_request
    from data_agent.agent.publication_synthesis import validate_final_narrative
    from data_agent.config import get_config

    tmp_root = (ROOT / "tmp").resolve()
    if not run_dir.is_relative_to(tmp_root) or run_dir.exists():
        raise SystemExit("run directory must be a fresh path inside repository tmp")
    _require_clean_checkout()
    matrix = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if (matrix.get("schema_version") != "shadow_c_calibration_cases.v1"
            or len(matrix.get("cases", [])) != 4):
        raise SystemExit("controlled C case matrix changed shape")
    cfg = get_config()
    if not cfg.model_id or not cfg.api_base or not cfg.api_key:
        raise SystemExit("Provider configuration incomplete")
    builder = _fixture_builder()
    bundles = []
    for case in matrix["cases"]:
        state, packet, history, answer = builder(
            lead_prose=case["lead_prose"], extra_prose=case["extra_prose"],
        )
        visible = case["lead_prose"] + "[[claim:claim_revenue]]" + case["extra_prose"]
        if validate_final_narrative(visible, packet) is not None:
            raise SystemExit(f"case {case['id']} fails existing narrative gate")
        request = build_shadow_audit_request(
            packet, answer, state=state, canonical_history=history,
        )
        if (request.get("status") != "ready" or len(request["claims"]) != 1
                or request["claims"][0]["local_explanation"].get("status") != "same_line_untrusted"
                or "99%" in _json_bytes(request).decode("utf-8")):
            raise SystemExit(f"case {case['id']} is not a bounded Shadow input")
        bundles.append({
            "case_id": case["id"], "oracle": case["oracle"],
            "state": state.to_dict(), "packet": packet,
            "history": {"messages": history.messages, "revision": history.revision,
                        "sha256": history.sha256, "message_count": history.message_count},
            "answer": answer,
            "request_identity": {key: request[key] for key in (
                "prompt_version", "prompt_sha256", "input_digest", "audit_view_digest",
                "packet_digest", "answer_sha256",
            )},
        })
    run_dir.mkdir(parents=True)
    bundle_bytes = _json_bytes(bundles)
    (run_dir / "bundles.json").write_bytes(bundle_bytes)
    manifest = {
        "schema_version": "shadow_c_freeze.v1",
        "source_commit": _head(), "runner_sha256": _file_digest(Path(__file__)),
        "fixture_module_sha256": _file_digest(ROOT / "tests/test_publication_audit_view_offline.py"),
        "cases_sha256": _file_digest(CASES_PATH),
        "bundles_sha256": _digest(bundle_bytes),
        "model": cfg.model_id, "provider_endpoint": cfg.api_base,
        "call_cap": MAX_CALLS, "output_token_cap": MAX_OUTPUT_TOKENS,
        "case_ids": [case["id"] for case in matrix["cases"]],
        "request_identities": {item["case_id"]: item["request_identity"] for item in bundles},
        "provider_ledger": str((run_dir / "provider-calls.jsonl").relative_to(ROOT)),
        "results_path": str((run_dir / "results.json").relative_to(ROOT)),
        "source_class": matrix["source_class"],
        "natural_tier": "not_in_this_freeze",
        "request_policy": "one_shot_no_retry",
    }
    (run_dir / "freeze.json").write_bytes(_json_bytes(manifest))
    return manifest


def _load_frozen(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from data_agent.config import get_config

    _require_clean_checkout()
    manifest = json.loads((run_dir / "freeze.json").read_text(encoding="utf-8"))
    bundle_path = run_dir / "bundles.json"
    cfg = get_config()
    checks = {
        "schema_version": "shadow_c_freeze.v1",
        "source_commit": _head(), "runner_sha256": _file_digest(Path(__file__)),
        "fixture_module_sha256": _file_digest(ROOT / "tests/test_publication_audit_view_offline.py"),
        "cases_sha256": _file_digest(CASES_PATH),
        "bundles_sha256": _digest(bundle_path.read_bytes()),
        "model": cfg.model_id, "provider_endpoint": cfg.api_base,
        "call_cap": MAX_CALLS, "output_token_cap": MAX_OUTPUT_TOKENS,
        "request_policy": "one_shot_no_retry",
        "provider_ledger": str((run_dir / "provider-calls.jsonl").relative_to(ROOT)),
        "results_path": str((run_dir / "results.json").relative_to(ROOT)),
    }
    if not cfg.api_key or any(manifest.get(key) != value for key, value in checks.items()):
        raise SystemExit("frozen Shadow preflight mismatch or Provider unavailable")
    if (run_dir / "provider-calls.jsonl").exists() or (run_dir / "results.json").exists():
        raise SystemExit("frozen Shadow batch is already started")
    bundles = json.loads(bundle_path.read_text(encoding="utf-8"))
    if ([item.get("case_id") for item in bundles] != manifest.get("case_ids")
            or len(bundles) > MAX_CALLS
            or {item["case_id"]: item["request_identity"] for item in bundles}
            != manifest.get("request_identities")):
        raise SystemExit("frozen Shadow case identities changed")
    return manifest, bundles


def _run(run_dir: Path, manifest: dict[str, Any], bundles: list[dict[str, Any]]) -> dict[str, Any]:
    os.environ["DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED"] = "1"
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.agent.publication_audit import build_shadow_audit_request, run_shadow_audit_once
    from data_agent.session.history import CanonicalHistorySnapshot
    from data_agent.llm.request_policy import ONE_SHOT
    from run_p08_real_matrix import ProviderLedger
    import data_agent.llm.client as client_module

    ledger = ProviderLedger(run_dir / "provider-calls.jsonl", MAX_CALLS)
    client_module.completion = ledger.wrap(client_module.completion)
    client = client_module.LLMClient(max_tokens=MAX_OUTPUT_TOKENS, timeout=30, request_policy=ONE_SHOT)
    rows = []
    stopped = False
    for bundle in bundles:
        case_id = bundle["case_id"]
        if stopped:
            rows.append({"case_id": case_id, "status": "blocked_not_started"})
            continue
        state = AnalysisSessionState.from_dict(bundle["state"], bundle["state"]["session_id"])
        history = CanonicalHistorySnapshot(**bundle["history"])
        packet, answer = bundle["packet"], bundle["answer"]
        request = build_shadow_audit_request(
            packet, answer, state=state, canonical_history=history,
        )
        if (request.get("status") != "ready"
                or any(request.get(key) != value for key, value in bundle["request_identity"].items())):
            rows.append({"case_id": case_id, "status": "blocked_not_started",
                         "reason": "request_identity_drift"})
            stopped = True
            continue
        result = run_shadow_audit_once(
            packet, answer, state=state, canonical_history=history,
            enabled=True, remaining_call_budget=MAX_CALLS - ledger.count,
            client=client,
        )
        rows.append({"case_id": case_id, "oracle": bundle["oracle"], **result})
        (run_dir / "results.json").write_bytes(_json_bytes({
            "source_commit": manifest["source_commit"], "cases": rows,
            "provider_initiated_calls": ledger.count,
        }))
        if result.get("reason") in {"client_error", "empty_visible_output"} or ledger.count > MAX_CALLS:
            stopped = True
    summary = {"source_commit": manifest["source_commit"], "cases": rows,
               "provider_initiated_calls": ledger.count, "publication_effect": "none"}
    (run_dir / "results.json").write_bytes(_json_bytes(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    if not run_dir.is_relative_to((ROOT / "tmp").resolve()):
        raise SystemExit("run directory must stay below repository tmp")
    if args.preflight:
        manifest = _prepare(run_dir)
        print(json.dumps({"preflight": "passed", **manifest}, ensure_ascii=True))
        return
    manifest, bundles = _load_frozen(run_dir)
    result = _run(run_dir, manifest, bundles)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
