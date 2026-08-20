from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from data_agent.v2.workbench_browser_fixture import build_provider_neutral_fixture


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the provider-neutral V2 Workbench browser fixture."
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-root", type=Path)
    args = parser.parse_args()
    state_root = args.state_root or Path(
        tempfile.mkdtemp(prefix="data-agent-v2-browser-")
    )
    app = build_provider_neutral_fixture(state_root)
    print(f"url=http://127.0.0.1:{args.port}/v2-workbench", flush=True)
    print(f"state_root={state_root.resolve()}", flush=True)
    print(
        f"fixture_csv={app.config['PROVIDER_NEUTRAL_FIXTURE_CSV']}", flush=True
    )
    app.run(
        host="127.0.0.1",
        port=args.port,
        threaded=True,
        debug=False,
        use_reloader=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
