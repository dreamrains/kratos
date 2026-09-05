"""Reusable fail-closed server bootstrap for real-Provider browser journeys."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from scripts.acceptance.release_source import release_source_digest
from scripts.acceptance.strict_provider_guard import (
    StrictProviderCallGuard,
    require_network_enabled_execution,
)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _normalized_file_hash(path: Path) -> str:
    return _sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def _configured_path(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def run_authorized_browser_server(
    *,
    root: Path,
    candidate_path: Path,
    launcher_path: Path,
    keep_guard_installed: bool = False,
) -> None:
    """Validate a frozen candidate, install one global guard, and serve it."""

    root = Path(root).resolve()
    candidate_path = Path(candidate_path).resolve()
    launcher_path = Path(launcher_path).resolve()
    for import_path in (root, root / "src"):
        if str(import_path) not in sys.path:
            sys.path.insert(0, str(import_path))

    candidate_bytes = candidate_path.read_bytes().replace(b"\r\n", b"\n")
    candidate = json.loads(candidate_bytes.decode("utf-8"))
    checks = {
        "candidate_sha256": _sha256_bytes(candidate_bytes),
        "launcher_sha256": _normalized_file_hash(launcher_path),
        "source_digest": release_source_digest(root),
        "prompt_sha256": _sha256_bytes(candidate["prompt"].encode("utf-8")),
        "oracle_sha256": _canonical_json_hash(candidate["oracle"]),
        "data_sha256": {
            item["id"]: _sha256_bytes((root / item["path"]).read_bytes())
            for item in candidate["data"]
        },
    }
    expected = {
        "candidate_sha256": os.environ.get("AUTHORIZED_CANDIDATE_SHA256", ""),
        "launcher_sha256": os.environ.get("AUTHORIZED_LAUNCHER_SHA256", ""),
        "source_digest": os.environ.get("AUTHORIZED_SOURCE_DIGEST", ""),
        "prompt_sha256": os.environ.get("AUTHORIZED_PROMPT_SHA256", ""),
        "oracle_sha256": os.environ.get("AUTHORIZED_ORACLE_SHA256", ""),
        "data_sha256": {item["id"]: item["sha256"] for item in candidate["data"]},
    }
    errors = [key + " mismatch" for key, value in checks.items() if value != expected[key]]
    if candidate.get("source_digest") != checks["source_digest"]:
        errors.append("candidate source_digest mismatch")

    from data_agent.config import get_config

    config = get_config()
    policy = candidate["provider_policy"]
    # Current acceptance uses one fixed output limit. Historical candidates
    # remain evidence, but cannot authorize hidden length escalation here.
    if policy.get("silent_length_ladder") != [policy.get("initial_max_tokens")]:
        errors.append("output token escalation is not supported by this acceptance launcher")
    auxiliary_budget = policy.get("auxiliary_initial_max_tokens", 300)
    if auxiliary_budget not in (300, 800) or auxiliary_budget not in policy["auxiliary_max_tokens"]:
        errors.append("auxiliary_initial_max_tokens outside authorization")
    if config.model_id != candidate["model"]:
        errors.append("model mismatch")
    if config.max_tokens != policy["initial_max_tokens"]:
        errors.append("MAX_TOKENS mismatch")
    if config.quality_judge_model not in {None, candidate["model"]}:
        errors.append("QUALITY_JUDGE_MODEL mismatch")
    if config.mcp_enabled:
        errors.append("MCP_ENABLED must be false")
    if not str(config.api_base or "").strip():
        errors.append("API_BASE is required")
    if not str(config.api_key or "").strip():
        errors.append("API_KEY is required")

    expected_workspace = (root / candidate["writes"]["workspace_dir"]).resolve()
    expected_sessions = (root / candidate["writes"]["sessions_dir"]).resolve()
    if _configured_path(root, config.workspace_dir) != expected_workspace:
        errors.append("WORKSPACE_DIR mismatch")
    if _configured_path(root, config.sessions_dir) != expected_sessions:
        errors.append("SESSIONS_DIR mismatch")

    report_path = (root / candidate["writes"]["report_path"]).resolve()
    receipt_path = (root / candidate["writes"]["provider_receipt_path"]).resolve()
    for label, path in (
        ("workspace", expected_workspace),
        ("sessions", expected_sessions),
        ("report", report_path),
        ("provider receipt", receipt_path),
    ):
        if path.exists():
            errors.append(f"{label} path already exists")
    if errors:
        raise SystemExit("preflight failed: " + "; ".join(errors))

    ready = {
        "ready": True,
        "checks": checks,
        "call_cap": policy["call_cap"],
        "api_base_present": True,
        "api_key_present": True,
    }
    if os.environ.get("DATA_AGENT_PREFLIGHT_ONLY") == "1":
        print(json.dumps(ready), flush=True)
        return

    # This gate is intentionally after every zero-call digest/path check and
    # before importing the runtime or installing a Provider completion hook.
    require_network_enabled_execution()

    from data_agent.llm import client as llm_client

    allowed_max_tokens = set(policy["silent_length_ladder"]) | set(policy["auxiliary_max_tokens"])
    original_completion = llm_client.completion
    from data_agent.llm.request_policy import ONE_SHOT
    guard = StrictProviderCallGuard(
        completion=original_completion,
        receipt_path=receipt_path,
        candidate_id=candidate["candidate_id"],
        source_digest=checks["source_digest"],
        call_cap=int(policy["call_cap"]),
        expected_model=candidate["model"],
        allowed_max_tokens=allowed_max_tokens,
        temperature=float(policy["temperature"]),
        timeout_seconds=int(policy["timeout_seconds"]),
    )
    guard.persist_receipt()
    # Factories inject the guard explicitly. Also protect the default transport
    # so an auxiliary/default client cannot escape accounting in this process.
    # This wraps a function, not product client methods or class behavior.
    llm_client.completion = guard.completion

    lifecycle = None
    try:
        from data_agent.lifecycle import AgentLifecycle
        from data_agent.web.app import create_app
        from data_agent.web.agent_manager import AgentManager
        from scripts.acceptance.bounded_auxiliary_client import OneShotAuxiliaryClient

        lifecycle = AgentLifecycle()
        lifecycle.initialize()
        app = create_app()
        app.config["agent_manager"] = AgentManager(
            client_factory=lambda model_id=None: llm_client.LLMClient(
                model_id=model_id or candidate["model"], max_tokens=int(policy["silent_length_ladder"][0]),
                temperature=float(policy["temperature"]), timeout=int(policy["timeout_seconds"]),
                transport=guard.completion, request_policy=ONE_SHOT,
            ),
            auxiliary_client_factory=lambda: OneShotAuxiliaryClient(
                llm_client.LLMClient(
                    model_id=candidate["model"],
                    transport=guard.completion, request_policy=ONE_SHOT,
                    max_tokens=auxiliary_budget,
                    temperature=float(policy["temperature"]),
                    timeout=int(policy["timeout_seconds"]),
                ),
                max_tokens=auxiliary_budget,
            ),
        )
        app.config["lifecycle"] = lifecycle
        app.config["strict_provider_call_guard"] = guard
        host = os.environ.get("DATA_AGENT_WEB_HOST", "127.0.0.1")
        port = int(os.environ.get("DATA_AGENT_WEB_PORT", "5189"))
        print(json.dumps({**ready, "network_execution_acknowledged": True}), flush=True)
        stop_path = os.environ.get("DATA_AGENT_ACCEPTANCE_STOP_PATH")
        if stop_path:
            from scripts.acceptance.browser_process import serve_until_stopped
            serve_until_stopped(app, host=host, port=port, stop_path=stop_path)
        else:
            app.run(host=host, port=port, threaded=True, debug=False)
    finally:
        try:
            guard.close()
            if lifecycle is not None:
                lifecycle.shutdown()
        finally:
            if not keep_guard_installed:
                llm_client.completion = original_completion
