"""Flask entry point for Data Agent Web GUI."""

import os
import sys


def main():
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    if sys.platform == "win32":
        os.system("")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    from data_agent.lifecycle import AgentLifecycle
    lifecycle = AgentLifecycle()
    lifecycle.initialize()

    # Ensure vendor JS files are available
    from data_agent.web.vendor_check import ensure_vendor_files
    ensure_vendor_files()

    from data_agent.web.app import create_app
    app = create_app()
    app.config["lifecycle"] = lifecycle
    host = os.environ.get("DATA_AGENT_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("DATA_AGENT_WEB_PORT", "5001"))

    try:
        app.run(host=host, port=port, threaded=True, debug=False)
    finally:
        lifecycle.shutdown()


if __name__ == "__main__":
    main()
