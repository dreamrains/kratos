"""Zero-Provider browser transport fixtures. All product tools remain real.

Each launch uses a new run directory. The fixture reads actual tool outputs to
compose subsequent messages; oracle values are never substituted for results.
"""
from __future__ import annotations
import argparse
import ast
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]


def call(tool_name, **arguments):
    return tool_name, arguments


class ScriptedTransport:
    def __init__(self, case, run_dir):
        self.case, self.run_dir = case, run_dir
        self.generators, self.records = {}, []
        self.lock = threading.RLock()

    def persist(self):
        from data_agent.utils.atomic_files import replace_file
        path = self.run_dir / "scripted-requests.json"
        temp = path.with_suffix(".tmp")
        with self.lock:
            temp.write_text(json.dumps({"real_provider_calls": 0, "transport": "scripted",
                                        "calls": self.records}, ensure_ascii=False, indent=2), encoding="utf-8")
            replace_file(temp, path)

    def result(self, name):
        from data_agent.agent.context import get_current_context
        from data_agent.config import get_config
        from data_agent.tools._utils import sanitize_filename
        ctx = get_current_context()
        receipt = next(r for r in reversed(ctx.analysis_state.tool_receipts) if r["tool_name"] == name)
        ref = "tool_outputs/" + sanitize_filename(receipt["tool_call_id"]) + "_detail.json"
        result = json.loads((get_config().sessions_resolved / ctx.session_id / ref).read_text(encoding="utf-8"))
        return result, ref

    def evidence(self, dataset, tools, claim, summary, **details):
        return call("record_evidence_record", record_json={
            "claim": claim, "dataset": dataset, "method": ", ".join(tools), "tool_calls": tools,
            "result_summary": summary, "limitations": ["仅描述观测数据，不支持因果解释或窗口外推。"],
            "confidence": "medium",
            "time_scope": "用户指定的已观测窗口", "calculation_method": ", ".join(tools),
            "method_detail": "使用当前会话工具结果及其数据版本", **details,
        })

    def evidence_id(self):
        from data_agent.agent.context import get_current_context
        return get_current_context().analysis_state.evidence_records[-1]["id"]

    def journey(self):
        if self.case == "M01":
            name = "游戏B留存"
            yield call("describe_dataset", name=name)
            yield call("detect_data_quality", name=name)
            yield self.evidence(name, ["describe_dataset", "detect_data_quality"], "数据结构与质量检查", "日期覆盖不代表采集截止时间；零值语义未知。")
            yield call("curve_fitting", name=name, series_columns="1天后,2天后,3天后,4天后,5天后,6天后,7天后,14天后,21天后,30天后", zero_values="exclude")
            result, ref = self.result("curve_fitting")
            best = result["fits"][0]
            summary = f"最佳族 {best['family']}；参数 {best['parameters']}；R²={best['r_squared']}；排除零值 {sum(p['n_excluded_zeros'] for p in result['points'])}。"
            yield call("read_file", path=ref)
            page, _ = self.result("read_file")
            if page.get("schema_version") == "file_page.v1":
                content = page["content"]
                for _ in range(100):
                    if page["next_offset"] is None:
                        break
                    yield call("read_file", path=ref, offset=page["next_offset"], expected_sha256=page["sha256"])
                    page, _ = self.result("read_file")
                    content += page["content"]
                assert page["next_offset"] is None and json.loads(content) == result
            bad = self.evidence(name, ["curve_fitting"], "观测范围内的最佳描述曲线", summary)[1]
            bad["record_json"] = {**bad["record_json"], "tool_calls": "curve_fitting, run_python", "confidence": "高"}
            yield call("record_evidence_record", **bad)
            yield self.evidence(name, ["curve_fitting"], "观测范围内的最佳描述曲线", summary, sample_size=62, metrics=best["parameters"])
            yield call("create_chart", chart_type="line", result_ref=ref, x_col="x", y_col="actual," + best["family"] + "_fit",
                       title="实际留存与最佳拟合（同一计算结果）", purpose="evidence", evidence_ids=self.evidence_id())
            yield summary + "\n\n实际与拟合两条序列来自同一份工具结果；只描述观测范围，不作因果或外推。"
        elif self.case == "M02":
            names = ["游戏A激励视频汇总数据报表", "游戏A内购数据", "游戏Abanner汇总数据"]
            for name in names:
                yield call("detect_data_quality", name=name)
            yield call("synthesize_time_series", datasets=",".join(names), date_col="日期",
                       metrics=",".join(f"{n}:{m}" for n, m in zip(names, ["视频广告收入", "内购收入", "BN_广告收入"])), save_as="three_source_daily")
            result, _ = self.result("synthesize_time_series")
            summary = f"按自然日聚合并外对齐，共 {result['aligned_rows']} 行；缺失覆盖 {result['missing_aligned_dates']}，保留 {len(result['source_identities'])} 个父版本。"
            yield self.evidence("three_source_daily", ["synthesize_time_series"], "三源同周期收入对比", summary, sample_size=result["aligned_rows"])
            yield call("create_chart", chart_type="line", data="three_source_daily", x_col="date", y_col=",".join(names), title="三源每日收入", purpose="evidence", evidence_ids=self.evidence_id())
            # The A02 title/scale mismatch must be rejected, then corrected.
            yield call("create_chart", chart_type="line", data="three_source_daily", x_col="date", y_col=",".join(names), title="三源收入（首日100）", scale_mode="normalize")
            yield call("create_chart", chart_type="line", data="three_source_daily", x_col="date", y_col=",".join(names), title="三源收入（首日100）", scale_mode="index100", purpose="evidence", evidence_ids=self.evidence_id())
            yield summary + "\n\n图中共变仅为描述性关系，不能解释为因果。"
            yield call("get_analysis_summary")
            yield "追问：三项收入已在相同日期单位下对齐；来源、覆盖与证据保留在本会话。共同变化不能证明共同原因，原因需独立验证。"
        elif self.case == "M03":
            name = "游戏互推"
            yield call("detect_data_quality", name=name)
            yield call("apply_type_conversion", name=name, column="卖量收入", target_type="numeric")
            conversion, _ = self.result("apply_type_conversion")
            clean = conversion["dataset"]
            yield call("run_python", purpose="披露数值解析损失及原始缺失；打印字典收据", code=f"d=get_dataset('{clean}')\ns=get_dataset('{name}__raw')\nprint({{'rows':len(s),'parseable':int(d['卖量收入'].notna().sum()),'missing':int(d['卖量收入'].isna().sum()),'original_dash':int((s['卖量收入']=='-').sum())}})")
            parsed, _ = self.result("run_python")
            parsed_values = parsed.get("result") or parsed["output"].strip()
            summary = parsed_values + "；'-' 保持缺失，不填零；按流量主游戏、广告主游戏、公司组合比较可观测收入，排名不完整。"
            yield call("transform_data", name=clean, operation="group_aggregate", group_by=["流量主游戏", "广告主游戏", "公司"],
                       aggregations=[{"column": "卖量收入", "functions": ["sum", "count", "size"]}], save_as="observable_income")
            yield call("top_n", name="observable_income", sort_by="卖量收入_sum", n=15, save_as="observable_top15")
            top, _ = self.result("top_n")
            coverage = "\n\n|组合|总记录|有效记录|缺失记录|可观测收入|\n|---|---:|---:|---:|---:|\n"
            for row in top["records"]:
                label = " / ".join(str(row[k]) for k in ["流量主游戏", "广告主游戏", "公司"])
                coverage += f"|{label}|{row['卖量收入_size']}|{row['卖量收入_count']}|{row['卖量收入_size']-row['卖量收入_count']}|{row['卖量收入_sum']}|\n"
            summary += coverage
            yield self.evidence(clean, ["run_python", "apply_type_conversion", "transform_data", "top_n"], "缺失覆盖限制下的可观测收入", summary,
                                sample_size=ast.literal_eval(parsed_values)["rows"], sample_unit="原始记录行")
            yield call("create_chart", chart_type="bar", data="observable_top15", label_columns="流量主游戏,广告主游戏,公司", y_col="卖量收入_sum", title="可观测收入 Top15（三维组合，缺失覆盖，非完整排名）", purpose="evidence", evidence_ids=self.evidence_id())
            yield summary + "图表仅展示可观测收入最高的15个三维组合；不是完整收益排名。"
        elif self.case == "M04":
            name = "省钱卡订单"
            yield call("detect_data_quality", name=name)
            yield call("compare_periods", name=name, date_col="支付时间", metrics="售价", period_a="2026-04-07~2026-04-21", period_b="2026-04-22~2026-05-06")
            result, _ = self.result("compare_periods")
            metric = result["metrics"]["售价"]
            summary = f"两期各 {result['period_a']['day_count']} 与 {result['period_b']['day_count']} 个自然日；订单 {result['period_a']['rows']} / {result['period_b']['rows']}；收入 {metric['period_a']} / {metric['period_b']}；日均 {metric['daily_avg_a']} / {metric['daily_avg_b']}。零订单日包含在日均分母。"
            yield self.evidence(name, ["compare_periods"], "两个固定完整期间的描述性差异", summary, sample_size=result["combined"]["row_count"], metrics=metric)
            yield call("write_file", path="output/period_summary.csv", content=f"period,revenue,orders,days\nA,{metric['period_a']},{result['period_a']['rows']},15\nB,{metric['period_b']},{result['period_b']['rows']},15\n")
            yield call("load_data", source="output/period_summary.csv", name="period_summary")
            yield call("create_chart", chart_type="bar", data_json=json.dumps([{"期间":"2026-04-07至04-21","收入":metric["period_a"]},{"期间":"2026-04-22至05-06","收入":metric["period_b"]}],ensure_ascii=False), x_col="期间", y_col="收入", title="两期收入（各15自然日）")
            yield summary + "\n\n不解释变化原因，不作因果或窗口外推。"
        elif self.case == "M05":
            name = "省钱卡购卡前后订单"
            yield call("detect_data_quality", name=name)
            quality, _ = self.result("detect_data_quality")
            duplicates = next((item["count"] for item in quality.get("issues", []) if item["type"] == "duplicate_rows"), 0)
            yield call("ab_test", name=name, group_col="用户类型（1是购卡前30天内，2是购卡后30天内）", metric_col="实收金额", unit_col="user_id", unit_aggregation="sum", method="ttest")
            result, _ = self.result("ab_test")
            summary = f"原始重复行 {duplicates} 条，主口径保留；前后窗口为文件标记的各30天，缺少独立对照。\n\n" + json.dumps(result, ensure_ascii=False)
            yield self.evidence(name, ["ab_test"], "以用户为单位的配对前后比较", summary, sample_size=result["paired_sample_size"], sample_unit="配对用户")
            groups = result.get("groups", {})
            rows = [{"组":key,"用户平均金额":value["mean"]} for key,value in groups.items()]
            yield call("create_chart", chart_type="bar", data_json=json.dumps(rows,ensure_ascii=False), x_col="组", y_col="用户平均金额", title="用户配对前后比较（原始重复行保留）")
            yield "以 user_id 配对并保留原始重复行。\n\n" + summary + "\n\n无对照的观察性比较，不得解释为购卡造成消费变化。"
        elif self.case == "M06":
            orders, pay, voucher = "省钱卡订单", "省钱卡0201到0510购卡用户付费数据", "省钱卡代金券明细订单"
            for name in [orders, pay, voucher]:
                yield call("detect_data_quality", name=name)
            yield call("run_python", purpose="只审计聚合键基数，不物化原始多对多join", code=f"a=get_dataset('{orders}')\nb=get_dataset('{pay}')\nac=a.groupby('user_id').size()\nbc=b.groupby('user_id').size()\nshared=ac.index.intersection(bc.index)\nresult={{'left_rows':len(a),'right_rows':len(b),'left_row_coverage':float(a['user_id'].isin(shared).mean()),'right_row_coverage':float(b['user_id'].isin(shared).mean()),'cardinality':'many-to-many' if ac.max()>1 and bc.max()>1 else 'other','projected_join_rows':int((ac.reindex(shared)*bc.reindex(shared)).sum()),'left_row_multiplier':float((ac.reindex(shared)*bc.reindex(shared)).sum()/len(a)),'right_row_multiplier':float((ac.reindex(shared)*bc.reindex(shared)).sum()/len(b)),'left_time_range':[str(a['支付时间'].min()),str(a['支付时间'].max())],'right_time_range':[str(b['支付时间'].min()),str(b['支付时间'].max())],'materialized_raw_join':False}}")
            result, _ = self.result("run_python")
            summary = result.get("result", "")
            yield self.evidence(orders, ["run_python"], "原始多对多关联风险审计", summary,
                                sample_size=ast.literal_eval(summary)["left_rows"], sample_unit="订单记录行；付费表行数另列")
            yield summary + "\n\n拒绝物化原始多对多 join；需先明确分析单位并分别聚合。代金券数据本轮独立。"
            yield call("cohort_analysis", name=pay, user_col="user_id", time_col="支付时间")
            result, _ = self.result("cohort_analysis")
            summary = json.dumps(result, ensure_ascii=False)
            yield self.evidence(pay, ["cohort_analysis"], "首次观测付费月份 cohort", summary, sample_size=sum(row["size"] for row in result["cohorts"]))
            yield call("create_chart", chart_type="bar", data_json=json.dumps([{"首次观测月":r["cohort"],"用户数":r["size"]} for r in result["cohorts"]],ensure_ascii=False), x_col="首次观测月", y_col="用户数", title="首次观测付费 cohort（右截断）")
            yield summary + "\n\n这是首次观测付费月份，不是购卡时间 cohort。未观察格子不代表零留存；末月不完整。"
            yield call("run_python", purpose="独立券张数、用户数、面值及实付单位审计", code=f"d=get_dataset('{voucher}')\nresult={{'voucher_rows':len(d),'distinct_primary_users':int(d['主用户ID'].nunique()),'status_counts':d['状态'].value_counts().to_dict(),'face_value_yuan':float(pd.to_numeric(d['代金券面值(分)'],errors='coerce').sum()/100),'paid_unit':'unknown','missing_received':int(d['领取时间'].isna().sum()),'missing_used':int(d['使用时间'].isna().sum())}}")
            result, _ = self.result("run_python")
            summary = result.get("result", "")
            yield self.evidence(voucher, ["run_python"], "代金券独立描述与单位披露", summary,
                                sample_size=ast.literal_eval(summary)["voucher_rows"], sample_unit="券张数")
            yield call("transform_data", name=voucher, operation="group_aggregate", group_by=["状态"], params=json.dumps({"agg_func":"size"}), save_as="voucher_status_counts")
            yield call("create_chart", chart_type="bar", data="voucher_status_counts", x_col="状态", y_col="count", title="券状态分布（计数单位：券张数）")
            yield summary + "\n\n券张数与去重用户数不同；面值单位为分，展示元时除以100；实付单位未知，不猜测。不关联原始表，不作因果解释。"

    def __call__(self, **kwargs):
        from data_agent.agent.context import get_current_context
        ctx = get_current_context()
        sid = ctx.session_id if ctx else "auxiliary"
        with self.lock:
            record = {"ordinal": len(self.records)+1, "session_id": sid, "stream": bool(kwargs.get("stream")), "status": "started"}
            self.records.append(record)
            self.persist()
        if not kwargs.get("stream"):
            record["status"] = "completed"
            self.persist()
            return NS(choices=[NS(message=NS(content="{}", tool_calls=None), finish_reason="stop")])
        def stream():
            try:
                messages = kwargs.get("messages", [])
                if any(m.get("role") == "user" and m.get("content") == "REHEARSAL_FAILURE" for m in messages[-2:]):
                    raise RuntimeError("scripted first-response failure for lifecycle regression")
                if any(m.get("role") == "user" and m.get("content") == "REHEARSAL_INTERRUPT" for m in messages[-2:]):
                    # Long enough for browser-control scheduling, still bounded
                    # if no cancellation arrives. No additional model request.
                    for _ in range(300):
                        time.sleep(0.2)
                        yield NS(choices=[NS(delta=NS(content=None,tool_calls=None,reasoning_content="waiting"),finish_reason=None)])
                    action = "异常中断预演未收到停止请求。"
                else:
                    generator = self.generators.setdefault(sid, self.journey())
                    action = next(generator, "本场景脚本已结束。")
                record["action"] = action[0] if isinstance(action, tuple) else "final_answer"
                # Deliberate bounded latency allows a real browser to observe
                # busy state without affecting computed results.
                time.sleep(0.15)
                if isinstance(action, tuple):
                    name, args = action
                    tc = NS(index=0,id=f"rehearsal_{record['ordinal']}",function=NS(name=name,arguments=json.dumps(args,ensure_ascii=False)))
                    preface = "先核对当前会话的数据和计算收据。\n\n" if name == "detect_data_quality" else None
                    yield NS(choices=[NS(delta=NS(content=preface,tool_calls=[tc],reasoning_content=None),finish_reason="tool_calls")])
                else:
                    yield NS(choices=[NS(delta=NS(content=action,tool_calls=None,reasoning_content=None),finish_reason="stop")])
                record["status"] = "completed"
            except GeneratorExit:
                record["status"] = "cancelled"
                raise
            except BaseException:
                record["status"] = "failed"
                raise
            finally:
                self.persist()
        return stream()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=[f"M{i:02d}" for i in range(1,7)])
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--port", type=int, default=5202)
    args = parser.parse_args()
    run = (ROOT / args.run_dir).resolve()
    if not run.is_relative_to(ROOT / "tmp") or run.exists():
        raise SystemExit("Expected a fresh isolated directory under tmp")
    run.mkdir(parents=True)
    os.environ.update(API_BASE="http://127.0.0.1:9", API_KEY="offline-only", GOLDEN_LIVE_SMOKE="0",
                      DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED="0", MCP_ENABLED="false", SKILL_AUTO_DISCOVER="false",
                      WORKSPACE_DIR=str(run / "workspace"), SESSIONS_DIR=str(run / "sessions"), LOG_FILE=str(run / "server.log"))
    from data_agent.config import get_config
    from data_agent.llm import client as client_module
    from data_agent.llm.request_policy import ONE_SHOT
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.lifecycle import AgentLifecycle
    from scripts.acceptance.release_source import release_source_digest
    def forbidden(**kwargs):
        raise RuntimeError("Zero-Provider rehearsal forbids un-injected requests")
    client_module.completion = forbidden
    transport = ScriptedTransport(args.case, run)
    transport.persist()
    factory = lambda model_id=None: client_module.LLMClient(model_id=model_id, max_tokens=8000, transport=transport, request_policy=ONE_SHOT)
    lifecycle = AgentLifecycle()
    lifecycle.initialize()
    app = create_app()
    app.config["agent_manager"] = AgentManager(client_factory=factory)
    manifest = {"case":args.case,"source_digest":release_source_digest(ROOT),"pid":os.getpid(),"real_provider_calls":0,"port":args.port}
    (run / "manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(manifest),flush=True)
    from werkzeug.serving import make_server
    from flask import request
    server = make_server("127.0.0.1", args.port, app, threaded=True)
    @app.post("/__rehearsal__/stop")
    def stop_rehearsal():
        if request.remote_addr != "127.0.0.1":
            return {"error": "localhost only"}, 403
        threading.Thread(target=server.shutdown, name="rehearsal-stop").start()
        return {"stopping": True}
    try:
        stop_path = os.environ.get("DATA_AGENT_ACCEPTANCE_STOP_PATH")
        if stop_path:
            server.timeout = 0.1
            while not Path(stop_path).exists():
                server.handle_request()
        else:
            server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        lifecycle.shutdown()
        transport.persist()
        (run / "shutdown.json").write_text(json.dumps({"lifecycle_shutdown": True, "real_provider_calls": 0,
            "threads": [{"name": t.name, "daemon": t.daemon} for t in threading.enumerate()]}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
