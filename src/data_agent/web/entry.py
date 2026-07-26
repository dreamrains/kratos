"""Flask entry point for Data Agent Web GUI."""

import os
import sys
import threading
import webbrowser

from data_agent.utils.unicode_io import configure_utf8_stdio


def _open_browser(host: str, port: int):
    """Auto-open browser after a short delay."""
    def _open():
        import time
        time.sleep(1.0)
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            print(f"[web] 请在浏览器中打开 http://{host}:{port}")
    threading.Thread(target=_open, daemon=True).start()


def main():
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    if sys.platform == "win32":
        os.system("")
        configure_utf8_stdio()

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

    if not os.environ.get("DATA_AGENT_NO_BROWSER"):
        _open_browser(host, port)

    print(f"[web] 观澜 Data Agent 已启动：http://{host}:{port}")

    try:
        app.run(host=host, port=port, threaded=True, debug=False)
    finally:
        lifecycle.shutdown()


if __name__ == "__main__":
    main()
