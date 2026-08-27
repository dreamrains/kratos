"""Local-only Web acceptance server for publication synthesis.

This starts the production Flask app on localhost while injecting a
deterministic client.  The browser therefore exercises the actual SSE,
AgentLoop, tool registry, persistence and Workbench rendering path without
making a Provider request.  It is intentionally an acceptance aid, not a
runtime mode or an alternative web application.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


class _LocalPublicationClient:
    """A local main-journey script isolated from auxiliary semantic hooks."""

    allow_stream_sync_fallback = False
    provider_calls = 0

    def __init__(self) -> None:
        self._main_round = 0

    @property
    def main_rounds_served(self) -> int:
        return self._main_round

    def _main_response(self, messages, tools=None, system=None):
        del messages, tools, system
        from data_agent.llm.client import Response, ToolCall

        self._main_round += 1
        if self._main_round == 1:
            return Response(tool_calls=[ToolCall(
                id="local_load_orders",
                name="load_data",
                arguments={"source": "省钱卡订单.xlsx", "name": "publication_orders"},
            )])
        if self._main_round == 2:
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
        if self._main_round == 3:
            evidence = {
                "claim": "前 15 天售价总额为 1818，后 15 天为 684；两个连续窗口共 71 笔订单、覆盖 30 个自然日。",
                "dataset": "publication_orders",
                "method": "compare_periods",
                "tool_calls": [{"name": "compare_periods"}],
                "result_summary": "售价总额由 1818 降至 684，描述性变化为 -62.38%。",
                "limitations": ["无对照组或随机化，不能仅凭该比较推断因果关系。"],
                "confidence": "medium",
                "metrics": {"period_a": 1818, "period_b": 684, "change_pct": -62.38},
                "sample_size": "71",
                "time_scope": "2026-04-07 至 2026-05-06（两个连续 15 天窗口）",
                "calculation_method": "对两个互不重叠的自然日窗口分别求和并比较",
                "method_detail": "compare_periods，售价按窗口求和",
                "significance": "not tested",
                "correlation": "not applicable",
                "confidence_interval": "not estimated",
                "insight_type": "trend",
            }
            return Response(tool_calls=[ToolCall(
                id="local_record_period_evidence",
                name="record_evidence_record",
                arguments={"record_json": json.dumps(evidence, ensure_ascii=False)},
            )])
        if self._main_round == 4:
            # Deliberately omit the computed anchors.  The publication layer
            # must surface the receipt-backed values in the final response.
            return Response(
                text="模型解读：两个期间存在描述性差异；该比较不能单独证明因果关系。",
                finish_reason="stop",
            )
        raise RuntimeError("local publication client received an unexpected extra main round")

    def chat(self, messages, tools=None, system=None):
        from data_agent.llm.client import Response

        if tools:
            return self._main_response(messages, tools=tools, system=system)
        # Intent, playbook and requirement-extraction hooks are auxiliary to
        # this acceptance journey.  They must not consume a scripted main
        # round or manufacture Provider-like retries.
        return Response(text="", finish_reason="stop")

    def stream_chat_structured(self, messages, tools=None, system=None):
        from data_agent.llm.client import StreamComplete, StreamTextDelta

        response = self._main_response(messages, tools=tools, system=system)
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
            client = _LocalPublicationClient()
            self._loops[sid] = AgentLoop(
                client=client,
                auxiliary_llm_client=client,
                session_id=sid,
            )
        return self._loops[sid]

    def get(self, session_id):
        return self._loops.get(session_id)


def _forbid_default_provider_calls() -> None:
    """Fail fast if the local acceptance path escapes its injected client."""
    from data_agent.llm.client import LLMClient

    def blocked(*_args, **_kwargs):
        print(
            "[local publication synthesis] blocked unexpected default Provider call",
            flush=True,
        )
        traceback.print_stack(limit=12)
        raise RuntimeError("local acceptance forbids default Provider calls")

    LLMClient.chat = blocked
    LLMClient.stream_chat_structured = blocked


def main() -> None:
    import os

    from data_agent.tools import discover_tools
    from data_agent.web.app import create_app

    _forbid_default_provider_calls()
    discover_tools()
    app = create_app()
    app.config["agent_manager"] = _LocalPublicationManager()
    host = os.environ.get("DATA_AGENT_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("DATA_AGENT_WEB_PORT", "5011"))
    print(f"[local publication synthesis] http://{host}:{port}", flush=True)
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
