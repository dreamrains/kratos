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

    from data_agent.web.app import create_app
    app = create_app()
    app.config["lifecycle"] = lifecycle

    try:
        app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)
    finally:
        lifecycle.shutdown()


if __name__ == "__main__":
    main()
