"""Run deterministic, zero-Provider regression suites in an isolated directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import uuid


QUICK_TESTS = (
    "tests/test_execution_control.py",
    "tests/test_trusted_publication_pipeline.py",
    "tests/test_trusted_publication_facts.py",
    "tests/test_trusted_publication_semantics.py",
    "tests/test_trusted_publication_runtime.py::test_actual_sync_stream_terminal_owns_same_saved_answer_and_export",
    "tests/test_trusted_publication_runtime.py::test_old_session_is_readonly_at_api_manager_and_direct_loop",
    "tests/test_publication_runtime_sessions.py::test_s3_normal_q12_mixed_mapping_r09_concurrent_card_resume_actual_answer",
    "tests/test_confirmation_policy.py",
    "tests/test_confirmation_service.py",
    "tests/test_confirmation_runtime.py",
    "tests/test_confirmation_continuation.py",
    "tests/test_confirmation_session_api.py",
    "tests/test_trusted_publication_native_families.py",
    "tests/test_synthesis_policy.py",
    "tests/test_tool_recovery.py",
    "tests/test_web_overhaul.py",
    "tests/test_web_sse_lifecycle.py",
)

SLOW_TESTS = (
    "tests/real_data",
    "tests/test_comprehensive_analysis_flow.py",
    "tests/test_optimization_comparison.py",
    "tests/test_phase_comprehensive.py",
    "tests/test_pipeline_comprehensive.py",
)


def _new_run_dir(root: Path, requested: str | None) -> Path:
    if requested:
        run = (root / requested).resolve()
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run = (root / "tmp" / "test-runs" / f"{stamp}-{uuid.uuid4().hex[:8]}").resolve()
    tmp_root = (root / "tmp").resolve()
    if not run.is_relative_to(tmp_root) or run.exists():
        raise SystemExit("run directory must be a fresh path inside repository tmp")
    run.mkdir(parents=True)
    return run


def _suite_paths(suite: str, requested: list[str]) -> list[str]:
    if requested:
        return requested
    if suite == "quick":
        return list(QUICK_TESTS)
    if suite == "slow-offline":
        return list(SLOW_TESTS)
    return ["tests"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", nargs="?", choices=("quick", "full-offline", "slow-offline"), default="full-offline")
    parser.add_argument("paths", nargs="*", help="optional explicit paths below tests/")
    parser.add_argument("--run-dir", help="fresh path below tmp/; generated automatically when omitted")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    run = _new_run_dir(root, args.run_dir)
    paths = _suite_paths(args.suite, args.paths)
    # Named nodes keep the quick suite bounded; full-offline still collects all tests.
    resolved_paths = [(root / path.split("::", 1)[0]).resolve() for path in paths]
    tests_root = (root / "tests").resolve()
    if any(not path.is_relative_to(tests_root) or not path.exists() for path in resolved_paths):
        raise SystemExit("every test path must exist below tests/")

    os.environ.update(
        API_BASE="http://127.0.0.1:9",
        API_KEY="data-agent-offline-no-provider",
        GOLDEN_LIVE_SMOKE="0",
        DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED="0",
        MCP_ENABLED="false",
        SKILL_AUTO_DISCOVER="false",
        WORKSPACE_DIR=str(run / "workspace"),
        SESSIONS_DIR=str(run / "sessions"),
    )
    sys.path[:0] = [str(root), str(root / "src")]

    import pytest

    # Legacy capture helpers use this basename as their evidence partition.
    # Each complete run needs a fresh partition as well as a fresh parent.
    basetemp = run / uuid.uuid4().hex[:8]
    print(f"suite={args.suite} tests={len(paths)} run_dir={run.relative_to(root)} basetemp={basetemp.relative_to(root)} provider_calls=forbidden")
    raise SystemExit(pytest.main([
        *paths,
        "-q",
        "-p", "no:cacheprovider",
        "--basetemp=" + str(basetemp),
        "--junitxml=" + str(run / "junit.xml"),
    ]))


if __name__ == "__main__":
    main()
