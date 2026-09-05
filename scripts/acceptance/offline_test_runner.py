"""Run the explicitly scoped offline suite in a new, non-reused directory."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("tests", nargs="*", default=["tests"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    run = (root / args.run_dir).resolve()
    if not run.is_relative_to(root / "tmp") or run.exists():
        raise SystemExit("run-dir must be a fresh directory inside repository tmp")
    run.mkdir(parents=True)
    os.environ.update(API_BASE="http://127.0.0.1:9", API_KEY="offline-only", GOLDEN_LIVE_SMOKE="0",
                      DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED="0", MCP_ENABLED="false", SKILL_AUTO_DISCOVER="false")
    # Isolate the cached runtime, without changing AgentConfig default tests.
    os.environ.pop("WORKSPACE_DIR", None)
    os.environ.pop("SESSIONS_DIR", None)
    sys.path[:0] = [str(root), str(root / "src")]
    from data_agent.config import get_config
    cfg = get_config()
    cfg.workspace_dir, cfg.sessions_dir = run / "workspace", run / "sessions"
    from data_agent.llm import client
    def forbidden(**kwargs):
        raise RuntimeError("Offline test: unmocked Provider request forbidden")
    client.completion = forbidden
    import pytest
    tests = args.tests or ["tests"]
    if any(not (root / name).resolve().is_relative_to(root / "tests") for name in tests):
        raise SystemExit("test collection must be explicitly scoped to tests")
    raise SystemExit(pytest.main([*tests, "-q", "-p", "no:cacheprovider",
                                 "--basetemp=" + str(run / "pytest"),
                                 "--junitxml=" + str(run / "junit.xml")]))


if __name__ == "__main__":
    main()
