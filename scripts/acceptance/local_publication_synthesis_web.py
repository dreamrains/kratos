"""Local-only Web acceptance server for publication synthesis.

This starts the production Flask app on localhost while injecting a
deterministic client.  The browser therefore exercises the actual SSE,
AgentLoop, tool registry, persistence and Workbench rendering path without
making a Provider request.  It is intentionally an acceptance aid, not a
runtime mode or an alternative web application.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


class _LocalPublicationClient:
    """A three-round response script whose tools execute against real data."""

    def __init__(self) -> None:
        self._round = 0

    def _response(self, messages, tools=None, system=None):
        del messages, tools, system
        from data_agent.llm.client import Response, ToolCall

        self._round += 1
        if self._round == 1:
            return Response(tool_calls=[ToolCall(
                id="local_load_orders",
                name="load_data",
                arguments={"source": "publication_synthesis_orders.xlsx", "name": "publication_orders"},
            )])
        if self._round == 2:
            return Response(tool_calls=[ToolCall(
                id="local_compare_periods",
                name="compare_periods",
                arguments={
                    "name": "publication_orders",
                    "date_col": "支付时间",
                    "metrics": "售价",
                    "period_a": "2026-04-07~2026-04-21",
                    "period_b": "2026-04-22~2026-05-06",
                },
            )])
        if self._round == 3:
            # Deliberately omit the computed anchors.  The publication layer
            # must surface the receipt-backed values in the final response.
            return Response(
                text="模型解读：两个期间存在描述性差异；该比较不能单独证明因果关系。",
                finish_reason="stop",
            )
        raise RuntimeError("local publication client received an unexpected extra round")

    def chat(self, messages, tools=None, system=None):
        return self._response(messages, tools=tools, system=system)

    def stream_chat_structured(self, messages, tools=None, system=None):
        from data_agent.llm.client import StreamComplete, StreamTextDelta

        response = self._response(messages, tools=tools, system=system)
        if response.text:
            yield StreamTextDelta(text=response.text)
        yield StreamComplete(response=response)


class _LocalPublicationManager:
    """Construct normal web-mode loops with the local acceptance client."""

    def __init__(self) -> None:
        self._loops = {}

    def get_or_create(self, session_id=None, model_id=None):
        del model_id
        from data_agent.agent.loop import AgentLoop, set_interaction_mode

        sid = session_id or "local_publication_synthesis"
        if sid not in self._loops:
            set_interaction_mode("web")
            self._loops[sid] = AgentLoop(client=_LocalPublicationClient(), session_id=sid)
        return self._loops[sid]

    def get(self, session_id):
        return self._loops.get(session_id)


def _place_reference_upload() -> None:
    from data_agent.config import get_config
    from scripts.acceptance.real_data_manifest import REFERENCE_DATA

    source = REFERENCE_DATA.path("savings_card_orders")
    target = get_config().inbox_dir / "publication_synthesis_orders.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def main() -> None:
    import os

    from data_agent.tools import discover_tools
    from data_agent.web.app import create_app

    discover_tools()
    _place_reference_upload()
    app = create_app()
    app.config["agent_manager"] = _LocalPublicationManager()
    host = os.environ.get("DATA_AGENT_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("DATA_AGENT_WEB_PORT", "5011"))
    print(f"[local publication synthesis] http://{host}:{port}", flush=True)
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
