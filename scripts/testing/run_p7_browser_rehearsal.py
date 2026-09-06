"""Serve an isolated, Provider-disabled Web rehearsal for P7 browser cases.

This is a test runner, not an alternative application path.  The browser talks
to the ordinary Flask/SSE endpoints; the ordinary AgentLoop executes its real
tools, persists its session, builds its Workbench projection, and validates a
publication before the response reaches the page.  Only the model transport is
scripted.  Any attempt to use the production Provider transport raises and is
recorded in the run trace.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


def _configure_environment(run_dir: Path) -> None:
    workspace_dir = run_dir / "workspace"
    sessions_dir = run_dir / "sessions"
    os.environ.update(
        {
            "API_BASE": "http://127.0.0.1:9",
            "API_KEY": "p7-browser-rehearsal-no-provider",
            "GOLDEN_LIVE_SMOKE": "0",
            "DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED": "0",
            "MCP_ENABLED": "false",
            "SKILL_AUTO_DISCOVER": "false",
            "WORKSPACE_DIR": str(workspace_dir),
            "SESSIONS_DIR": str(sessions_dir),
        }
    )
    (workspace_dir / "inbox").mkdir(parents=True, exist_ok=False)
    sessions_dir.mkdir(parents=True, exist_ok=False)


def _write_csv(path: Path, columns: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def _write_fixtures(run_dir: Path) -> None:
    inbox = run_dir / "workspace" / "inbox"
    _write_csv(
        inbox / "F-SALES.csv",
        ["order_id", "date", "channel", "amount"],
        [[f"O{i:02d}", f"2026-09-{i:02d}", "all", 10] for i in range(1, 13)],
    )
    _write_csv(
        inbox / "F-RET7.csv",
        ["day", "retention"],
        [[day, value] for day, value in enumerate((0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10), 1)],
    )
    _write_csv(
        inbox / "F-HYP.csv",
        ["date", "amount"],
        [["2026-09-01", 10], ["2026-09-02", 20]],
    )
    _write_csv(
        inbox / "F-HYP-FLAT.csv",
        ["date", "amount"],
        [["2026-09-01", 10], ["2026-09-02", 10]],
    )
    for number in range(1, 7):
        _write_csv(
            inbox / f"F-SRC{number}.csv",
            ["source", "date", "amount"],
            [
                [f"source_{number}", "2026-09-01", number * 10],
                [f"source_{number}", "2026-09-02", number * 11],
            ],
        )


class RunTrace:
    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "runtime.jsonl"
        self._lock = threading.Lock()

    def append(self, event: str, **payload: Any) -> None:
        record = {"timestamp": time.time(), "event": event, **payload}
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class ScriptedClient:
    """Small deterministic model replacement used only by this test server."""

    model_id = "p7-browser-scripted"
    max_tokens = 2048

    def __init__(self, trace: RunTrace) -> None:
        self.trace = trace
        self._rounds: dict[str, int] = defaultdict(int)

    def for_purpose(self, **_: Any) -> "ScriptedClient":
        return self

    def cancel(self) -> None:
        self.trace.append("scripted_cancel")

    def reset_cancellation(self) -> None:
        return None

    @staticmethod
    def _last_user(messages: list[dict]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content") or "")
        return ""

    @staticmethod
    def _current_hypothesis() -> tuple[str, str, str]:
        """Read the persisted production hypothesis artifact for B04 relations."""
        from data_agent.agent.context import get_current_context

        state = get_current_context().analysis_state
        plan_id = str((state.analysis_plan or {}).get("id") or "")
        contract_id = next(
            (str(item.get("id") or "") for item in state.dataset_contracts if str(item.get("dataset") or "") == "hyp"),
            "",
        )
        for ref in state.hypothesis_sets:
            if str(ref.get("dataset") or "") != "hyp":
                continue
            payload = json.loads(Path(str(ref["artifact_path"])).read_text(encoding="utf-8"))
            hypotheses = payload.get("hypotheses") or []
            if hypotheses:
                return str(hypotheses[0]["id"]), plan_id, contract_id
        raise RuntimeError("B04 requires a persisted hypothesis set for dataset hyp")

    @classmethod
    def _hypothesis_evidence(cls, relation: str, observed: str, delta: int) -> dict[str, Any]:
        hypothesis_id, plan_id, contract_id = cls._current_hypothesis()
        return {
            "plan_id": plan_id,
            "step_id": "period_compare_amount",
            "claim_key": f"b04_{relation}_{observed}",
            "claim": "amount changed between the compared periods in hyp.",
            "dataset": "hyp",
            "dataset_contract_id": contract_id,
            "method": "compare_periods",
            "tool_calls": ["compare_periods"],
            "result_summary": f"amount delta={delta} in the compared periods.",
            "limitations": ["descriptive comparison only"],
            "confidence": "medium",
            "sample_size": 2,
            "evidence_requirement": "amount",
            "measurements": [{
                "metric": "amount",
                "definition": "amount aggregated per period",
                "value": max(abs(delta), 1),
                "unit": "currency",
                "grain": "period",
                "population_scope": "all records",
                "time_scope": "2026-09",
                "method": "compare_periods",
                "denominator": "period days",
                "limitations": ["descriptive comparison only"],
                "delta": delta,
            }],
            "competing_hypotheses": [{
                "hypothesis_id": hypothesis_id,
                "relation": relation,
                "metric": "amount",
                "observed": observed,
            }],
        }

    @staticmethod
    def _response(text: str = "", calls: list[tuple[str, dict]] | None = None):
        from data_agent.llm.client import Response, ToolCall

        return Response(
            text=text,
            tool_calls=[ToolCall(f"p7-{index}-{name}", name, args) for index, (name, args) in enumerate(calls or [], 1)],
        )

    def chat(self, messages, tools=None, system=None):  # auxiliary intent/playbook calls
        self.trace.append("auxiliary_call", messages=len(messages))
        return self._response('{"intent_type":"directed_analysis","clarity":"clear"}')

    def _next(self, marker: str, messages: list[dict]):
        user = self._last_user(messages)
        step = self._rounds[marker]
        self._rounds[marker] += 1
        self.trace.append("scripted_round", marker=marker, step=step, user=user)

        if marker == "B01":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "f_sales"})])
            if step == 1:
                return self._response(calls=[(
                    "transform_data",
                    {
                        "name": "f_sales",
                        "operation": "group_aggregate",
                        "group_by": ["channel"],
                        "aggregations": [{"column": "amount", "functions": ["sum", "count"]}],
                        "save_as": "f_sales_total",
                    },
                )])
            if step == 2:
                return self._response(calls=[(
                    "record_evidence_record",
                    {"record_json": {
                        "claim": "当前 12 条订单金额合计为 120",
                        "dataset": "f_sales_total",
                        "method": "group_aggregate",
                        "tool_calls": ["transform_data"],
                        "result_summary": "amount_sum=120，amount_count=12",
                        "limitations": "仅覆盖当前导入的 12 条订单，不能外推总体。",
                        "confidence": "high",
                    }},
                )])
            return self._response(
                "已验证观察：当前 12 条订单金额合计为 120。行动建议：若下周同口径订单金额低于 120，先复核渠道投放；若连续两周低于 120，停止扩大投放并复核渠道成本。限制：这只是当前 12 条记录的描述，不能外推总体。"
            )

        if marker == "B02":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-RET7.csv", "name": "ret_a"})])
            if step == 1:
                return self._response(calls=[("curve_fitting", {"name": "ret_a", "x_col": "day", "y_col": "retention"})])
            return self._response("已验证观察：D7 留存为 10%。当前不能预测 D30，建议继续收集至第 30 天后再验证。")

        if marker == "B02-NEG":
            if step == 0:
                return self._response(calls=[("curve_fitting", {"name": "ret_a", "x_col": "day", "y_col": "retention"})])
            # The first candidate must be stopped by the real publication guard.
            if step == 1:
                return self._response("渠道 A 的 D30 留存预计为 5%。")
            return self._response("当前只有 D1 至 D7 的观察，不能预测 D30；需补充至第 30 天的数据后再验证。")

        if marker == "B03":
            if step == 0:
                calls: list[tuple[str, dict]] = []
                for number in range(1, 7):
                    name = f"src_{number}"
                    calls.append(("load_data", {"source": f"F-SRC{number}.csv", "name": name}))
                return self._response(calls=calls)
            if step == 1:
                calls = []
                for number in range(1, 7):
                    name = f"src_{number}"
                    calls.append((
                        "compare_periods",
                        {
                            "name": name,
                            "date_col": "date",
                            "metrics": "amount",
                            "period_a": "2026-09-01~2026-09-01",
                            "period_b": "2026-09-02~2026-09-02",
                        },
                    ))
                return self._response(calls=calls)
            return self._response(
                "已完成六个来源的分组汇总。来源 1 至来源 6 均保留在本轮收据中；导出时应保留全部来源和每个来源的金额与记录数。"
            )

        if marker == "B04":
            compare = {
                "name": "hyp", "date_col": "date", "metrics": "amount",
                "period_a": "2026-09-01~2026-09-01", "period_b": "2026-09-02~2026-09-02",
            }
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-HYP.csv", "name": "hyp"})])
            if step == 1:
                return self._response(calls=[("compare_periods", compare)])
            if step == 2:
                return self._response(calls=[("record_evidence_record", {"record_json": {
                    "claim": "amount changed between the compared periods in hyp.",
                    "dataset": "hyp",
                    "method": "compare_periods",
                    "tool_calls": ["compare_periods"],
                    "result_summary": "amount increased from 10 to 20 in the compared periods.",
                    "limitations": "descriptive comparison only",
                    "confidence": "medium",
                }})])
            if step == 3:
                return self._response("已创建竞争假设，当前仍待结构化证据区分。")
            if step == 4:
                return self._response(calls=[("compare_periods", compare)])
            if step == 5:
                return self._response(calls=[("record_evidence_record", {"record_json": self._hypothesis_evidence("supports", "increased", 10)})])
            if step == 6:
                return self._response("结构化支持证据已记录。")
            if step == 7:
                return self._response(calls=[("load_data", {"source": "F-HYP-FLAT.csv", "name": "hyp"})])
            if step == 8:
                return self._response(calls=[("compare_periods", compare)])
            if step == 9:
                return self._response(calls=[("record_evidence_record", {"record_json": self._hypothesis_evidence("refutes", "flat", 0)})])
            return self._response("结构化反证已记录；竞争解释保持未决。")

        if marker == "B05-BUSINESS":
            return self._response("面向业务：当前 12 条订单金额合计为 120。下周若低于 120，先检查渠道投放；该结论仅覆盖当前记录，不能外推总体。")
        if marker == "B05-ANALYST":
            return self._response("面向分析师：f_sales_total 经 group_aggregate 得到 amount_sum=120、amount_count=12；范围为当前 12 条订单，不能外推总体。")
        if marker == "B05-MANAGER":
            return self._response("面向管理层：当前样本的订单金额为 120（12 条）。下周低于 120 时复核投放；该结果仅适用于当前样本，不能外推总体。")
        if marker == "B05-PLAIN":
            return self._response("大白话：这 12 笔订单一共是 120。下周低于 120 就先查投放；这只说明眼前这批记录，不能代表全部订单。")
        if marker == "B05-TECH":
            return self._response("分析表达：f_sales_total 经 group_aggregate 得到 amount_sum=120、amount_count=12；该描述性结果仅覆盖当前 12 条订单，不能外推总体。")
        if marker == "B06-TOOL":
            if step == 0:
                return self._response(calls=[("transform_data", {
                    "name": "missing_dataset", "operation": "group_aggregate",
                    "group_by": ["channel"], "aggregations": [{"column": "amount", "functions": ["sum"]}],
                    "save_as": "never_created",
                })])
            return self._response("工具未能找到所需数据集，未发布计算结论；请先加载可用数据后再分析。")
        if marker == "B06-BUDGET":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "budget_sales"})])
            if step == 1:
                calls = []
                # This scenario is classified as a comprehensive report, whose
                # production budget profile permits 200 non-meta tool calls.
                # Send one more than the remaining allowance so AgentLoop itself
                # must raise BudgetExceeded; do not simulate that outcome here.
                for number in range(1, 206):
                    calls.append(("transform_data", {
                        "name": "budget_sales", "operation": "group_aggregate", "group_by": ["channel"],
                        "aggregations": [{"column": "amount", "functions": ["sum"]}], "save_as": f"budget_{number}",
                    }))
                return self._response(calls=calls)
            return self._response("已触及工具调用预算，停止继续调用并保留当前可验证状态。")
        return self._response("演练脚本未识别当前场景标记。")

    def stream_chat_structured(self, messages, tools=None, system=None):
        from data_agent.llm.client import StreamComplete

        # A Web confirmation resume appends the selected answer as the latest
        # user message.  The originating scenario remains the closest earlier
        # explicit marker and must retain control of the actual resumed loop.
        marker = "UNKNOWN"
        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            found = re.search(
                r"【(B(?:01|02-NEG|02|03|04|05-BUSINESS|05-ANALYST|05-MANAGER|05-PLAIN|05-TECH|06-TOOL|06-BUDGET))】",
                str(message.get("content") or ""),
            )
            if found:
                marker = found.group(1)
                break
        yield StreamComplete(response=self._next(marker, messages))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    if run_dir.exists():
        raise SystemExit(f"run directory must not exist: {run_dir}")
    run_dir.mkdir(parents=True)
    _configure_environment(run_dir)
    _write_fixtures(run_dir)
    trace = RunTrace(run_dir)
    trace.append("server_start", provider_enabled=False, port=args.port)

    # Belt-and-braces: a default client or accidental direct LiteLLM call fails
    # closed and leaves an auditable trace rather than touching a Provider.
    import data_agent.llm.client as llm_client

    def forbidden_completion(*_args: Any, **_kwargs: Any):
        trace.append("forbidden_provider_transport")
        raise RuntimeError("P7 browser rehearsal forbids Provider transport")

    llm_client.completion = forbidden_completion

    from data_agent.web.agent_manager import AgentManager
    from data_agent.web.app import create_app

    # These helpers construct module-global LLM clients lazily.  Bind them to
    # the same scripted transport so a local rehearsal has a true zero-call
    # Provider preflight rather than merely catching accidental fallbacks.
    import data_agent.agent.llm_intent as llm_intent
    import data_agent.agent.llm_playbook as llm_playbook
    import data_agent.agent.quality_judge as quality_judge

    llm_intent._client = ScriptedClient(trace)
    llm_playbook._client = ScriptedClient(trace)
    quality_judge._judge_client = ScriptedClient(trace)

    app = create_app()
    app.config["agent_manager"] = AgentManager(
        client_factory=lambda **_: ScriptedClient(trace),
        auxiliary_client_factory=lambda: ScriptedClient(trace),
    )

    @app.get("/__p7__/health")
    def p7_health():
        return {"ok": True, "provider_enabled": False, "run_dir": str(run_dir)}

    @app.get("/__p7__/trace")
    def p7_trace():
        return app.response_class(trace.path.read_text(encoding="utf-8"), mimetype="application/x-ndjson")

    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
