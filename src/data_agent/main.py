"""Data Agent 入口点。"""

import os
import sys

# litellm 在 __init__ 时会远程获取 model cost map，设置 LOCAL 跳过网络请求
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")

from data_agent.agent.repl import run_repl
from data_agent.utils.unicode_io import configure_utf8_stdio


def _auto_discover_tools():
    """自动扫描并导入 data_agent.tools 中的所有模块以触发注册。"""
    from data_agent.tools import discover_tools
    discover_tools()


def main():
    if sys.platform == "win32":
        os.system("")
        configure_utf8_stdio()

    from data_agent.lifecycle import AgentLifecycle
    lifecycle = AgentLifecycle()
    try:
        lifecycle.initialize()
        run_repl()
    finally:
        lifecycle.shutdown()


if __name__ == "__main__":
    main()
