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
            "MODEL_CONTEXT_TOKENS": "200000",
            "MODEL_MAX_OUTPUT_TOKENS": "128000",
            "MODEL_TOKENIZER": "tiktoken:o200k_base",
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
        inbox / "F-PROMO.csv",
        ["order_id", "channel", "order_amount", "incremental_revenue", "coupon_cost", "channel_cost"],
        [
            ["P1", "all", 20, 20, 3, 2],
            ["P2", "all", 25, 30, 4, 3],
            ["P3", "all", 35, 25, 2, 4],
            ["P4", "all", 40, 35, 5, 1],
        ],
    )
    _write_csv(
        inbox / "F-ACTION.csv",
        ["date", "amount", "campaign_cost", "net_contribution", "orders"],
        [[f"2026-09-{day:02d}", 100, 20, 80, 10] for day in range(7, 14)]
        + [[f"2026-09-{day:02d}", 110, 25, 85, 11] for day in range(14, 21)],
    )
    _write_csv(
        inbox / "F-SALES-EDGE.csv",
        ["order_id", "date", "channel", "amount"],
        [
            ["X", "2026-09-01", "A", 10], ["X", "2026-09-02", "A", None],
            ["Y", "2026-09-03", "A", 10], ["Z", "2026-09-04", "B", 0],
            ["Z", "2026-09-05", "B", 5], [None, "2026-09-06", "C", None],
        ],
    )
    _write_csv(
        inbox / "F-SALES-EDGE-V2.csv",
        ["order_id", "date", "channel", "amount"],
        [
            ["X", "2026-09-01", "A", 100], ["X", "2026-09-02", "A", None],
            ["Y", "2026-09-03", "A", 10], ["Z", "2026-09-04", "B", 0],
            ["Z", "2026-09-05", "B", 5], [None, "2026-09-06", "C", None],
        ],
    )
    _write_csv(
        inbox / "F-RET7.csv",
        ["day", "retention"],
        [[day, value] for day, value in enumerate((0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.10), 1)],
    )
    _write_csv(
        inbox / "F-HYP.csv",
        ["date", "amount"],
        [["2026-09-01", 10], ["2026-09-02", 20], ["2026-09-03", 20]],
    )
    _write_csv(
        inbox / "F-HYP-FLAT.csv",
        ["date", "amount"],
        [["2026-09-01", 10], ["2026-09-02", 10], ["2026-09-03", 10]],
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
        _write_csv(
            inbox / f"F-SRC{number}-FOUR.csv",
            ["source", "date", "amount"],
            [[f"source_{number}", f"2026-09-{day:02d}", number * (9 + day)]
             for day in range(1, 5)],
        )


    _write_csv(
        inbox / "F-YOY.csv", ["date", "amount"],
        [["2025-09-01", 50], ["2025-09-02", 50], ["2026-09-01", 60], ["2026-09-02", 60]],
    )



    # Four independent source tables for the original savings-card objectives.
    _write_csv(inbox / "F-CARD.csv", ["user_id", "card_amount"], [["u1",10],["u2",10],["u3",10]])
    _write_csv(inbox / "F-COUPON.csv", ["user_id", "coupon_cost"], [["u1",2],["u2",3],["u3",1]])
    _write_csv(inbox / "F-PAY-BEFORE.csv", ["order_id","user_id","date","category","amount"],
               [["b1","u1","2026-08-30","A",5],["b2","u2","2026-08-30","B",10],["b3","u3","2026-08-31","A",15]])
    _write_csv(inbox / "F-PAY-AFTER.csv", ["order_id","user_id","date","category","amount"],
               [["a1","u1","2026-09-01","A",10],["a2","u1","2026-09-02","B",20],
                ["a3","u2","2026-09-02","B",30],["a4","u3","2026-09-02","A",15],["a5","u3","2026-09-03","A",25]])
    _write_csv(inbox / "F-PROMO-V2.csv", ["order_id","channel","order_amount","incremental_revenue","coupon_cost","channel_cost"],
               [["P1","all",20,30,3,2],["P2","all",25,30,4,3],["P3","all",35,25,2,4],["P4","all",40,35,5,1]])


def _seed_legacy_confirmation_fixture() -> None:
    """Create the portable F5 legacy session used by IC-B05.

    The session is written through the production serializers.  The browser
    then loads it normally; no test-only route or alternate confirmation store
    is introduced.
    """
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.session.history import save_session

    session_id = "ic-b05-legacy"
    save_session(
        [{
            "role": "user",
            "content": "旧会话包含一个通用方法审批，恢复后应退役并重新判断真实业务缺口。",
        }],
        session_id,
    )
    state = AnalysisSessionState(session_id=session_id, data_state="data_loaded")
    state.pending_confirmations = [{
        "id": "legacy_method_pending",
        "status": "pending",
        "source": "method_playbook",
        "confirmation_type": "method_confirmation",
        "question": "是否按 Retention & Lifecycle 方法继续？",
        "options": [
            {"label": "按此方法继续", "value": "confirm_method"},
            {"label": "先补充目标口径", "value": "clarify_scope"},
        ],
        "blocking_reason": "历史模板要求确认方法。",
        "state_updates": {
            "method_confirmation": {"playbook_id": "retention_lifecycle"},
        },
    }]
    state.save()


class RunTrace:
    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "runtime.jsonl"
        self._lock = threading.Lock()

    def append(self, event: str, **payload: Any) -> None:
        record = {"timestamp": time.time(), "event": event, **payload}
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")



# Frozen scripted inputs, not production intent heuristics or semantic oracles.
P4_REQUESTS = {
    "CONS-01": ("什么是 p 值，如何正确解释？", "knowledge_qa", "在零假设和模型假定成立时，p 值表示得到当前或更极端结果的概率；不是零假设为真的概率，也不是效应大小。应同时报告效应、区间与检验前提。"),
    "CONS-01-EN": ("What is a p value and how should it be interpreted?", "knowledge_qa", "Under the null hypothesis and model assumptions, a p value is the probability of the observed or more extreme result. It is not the probability that the null is true or an effect size. Report effect size, intervals and assumptions as well."),
    "CONS-02": ("为电商留存设计分析方案，列出所需字段和步骤", "analysis_consultation", "先定义用户粒度、首购队列和观察窗口，需要用户ID、首购日期和后续事件日期；按队列计算各日仍活跃人数及有效分母，说明未成熟窗口、缺失和去重策略，再比较队列与不确定性。这里给方案，没有分析用户数据。"),
    "CONS-02-EN": ("Design an ecommerce retention analysis, including required fields and steps.", "analysis_consultation", "Define user grain, first-purchase cohorts and observation windows. Collect user IDs, first-purchase dates and later event dates. Calculate active users with eligible denominators, treat immature windows and missing or duplicate events explicitly, and compare cohorts with uncertainty. This is a plan, not a computed result."),
    "CONS-03": ("只解释回归和相关的区别，不执行分析", "knowledge_qa", "相关描述变量共同变化；回归描述在模型及其他变量条件下响应与解释变量的关系。两者都不能仅凭关联证明因果；需检查假定、混杂与研究设计。"),
    "CONS-04": ("换成给业务同事看的说明", "result_followup", "给业务同事：这些结果只说明已加载记录的情况，先确认适用范围再决定是否需要进一步分析。"),
    "CONS-05": ("解释刚才的收入下降", "result_followup", "没有可定位的原接受结果，不能声称本次收入已经下降；可先确定指标、窗口和数据来源。"),
    "INTENT-01": ("你好，请计算总收入", "directed_analysis", "当前只能交付 amount 原值，业务币种及收入定义仍未确认。"),
    "INTENT-02": ("不要分析留存，只导出当前表", "data_operation", "仅导出当前表，未启动留存分析。"),
    "INTENT-03": ("先解释同比含义，再算当前文件的同比", "directed_analysis", "同比比较相隔一年的同一时间窗口；本例由原文件两个同口径窗口比较，不能从这个变化推断因果。"),
}

P4_CARD_METRICS = ["最终收益", "复购率", "购买偏好", "付费频次", "付费ARPU", "人均付费金额", "日均付费金额", "单次付费金额", "金额区间分布"]
P4_REQUESTS.update({
    "INTENT-04": ("分析省钱卡的最终收益、复购率、购买偏好、付费频次、付费ARPU、人均付费金额、日均付费金额、单次付费金额、金额区间分布；判断连续付费是否因省钱卡刺激提升，说明计算方式", "directed_analysis", "本次计算口径：最终收益=card_after.amount合计+card_users.card_amount合计-card_coupons.coupon_cost合计；复购率=card_after中至少两笔支付的user_id数/card_users中不同user_id数；购买偏好=按category汇总card_after.amount；付费频次=按user_id计card_after支付记录数；付费ARPU=支付额/全体有效用户数，当前缺全体有效用户分母，保持未知；人均付费金额=支付额/当前不同付费user_id数；日均付费金额=支付额/最大与最小支付日期相差天数加1（含首尾）；单次付费金额=支付额/支付记录数；金额区间分布=按[0,20)、[20,40)统计支付记录数。以上仅为当前已提供记录的声明账面口径，单位未独立核定；前后支付次数只作描述，无对照不能证明省钱卡刺激效果。"),
    "INTENT-04-REORDER": ("分析省钱卡的购买偏好、付费频次、付费ARPU、人均付费金额、日均付费金额、单次付费金额、金额区间分布、最终收益、复购率；判断连续付费是否因省钱卡刺激提升，说明计算方式", "directed_analysis", "本次计算口径：最终收益=card_after.amount合计+card_users.card_amount合计-card_coupons.coupon_cost合计；复购率=card_after中至少两笔支付的user_id数/card_users中不同user_id数；购买偏好=按category汇总card_after.amount；付费频次=按user_id计card_after支付记录数；付费ARPU=支付额/全体有效用户数，当前缺全体有效用户分母，保持未知；人均付费金额=支付额/当前不同付费user_id数；日均付费金额=支付额/最大与最小支付日期相差天数加1（含首尾）；单次付费金额=支付额/支付记录数；金额区间分布=按[0,20)、[20,40)统计支付记录数。以上仅为当前已提供记录的声明账面口径，单位未独立核定；前后支付次数只作描述，无对照不能证明省钱卡刺激效果。"),
    "M06-TYPED": ("计算账面净收益", "directed_analysis", "结果只代表已提供列的账面算式，增量收入列不证明促销因果。"),
    "M06-TYPED-REUSE": ("继续计算同范围账面净收益", "directed_analysis", "当前有效成本口径应复用，事实仍绑定本次当前列求和。"),
    "M06-TYPED-CHANGE": ("加载新版本重新计算账面净收益", "directed_analysis", "换版后的成本选择需要重新核实。"),
})
P4_REQUESTS.update({
    "INTENT-05": ("计算7日收入和复购率", "directed_analysis", "收入仅为当前 amount 原值；缺少用户标识，复购未计算。"),
    "INTENT-05-CHANGE": ("窗口改为30日收入，不再要求复购率", "directed_analysis", "旧窗口与复购要求已撤回；30日收入只使用当前已提供记录。"),
    "INTENT-05-FOLLOW": ("用大白话解释刚才的30日收入", "result_followup", "这只是该窗口内已提供订单的金额相加；没有假设未上传记录，也未恢复已经撤回的复购要求。"),
})
P4_CARD_CODE = """cards = get_dataset('card_users')
coupons = get_dataset('card_coupons')
before = get_dataset('card_before')
after = get_dataset('card_after')
counts = after.groupby('user_id').size()
days = (after['date'].max().date() - after['date'].min().date()).days + 1
total = float(after['amount'].sum())
result = {
 '最终收益': total + float(cards['card_amount'].sum()) - float(coupons['coupon_cost'].sum()),
 '复购率': float((counts > 1).sum()) / int(cards['user_id'].nunique()),
 '购买偏好': {str(k): float(v) for k,v in after.groupby('category')['amount'].sum().items()},
 '付费频次': {str(k): int(v) for k,v in counts.items()},
 '人均付费金额': total / int(after['user_id'].nunique()),
 '日均付费金额': total / days,
 '单次付费金额': total / len(after),
 '金额区间分布': {'[0,20)': int(((after['amount'] >= 0) & (after['amount'] < 20)).sum()), '[20,40)': int(((after['amount'] >= 20) & (after['amount'] < 40)).sum())},
 '连续付费前后次数': {'before': int(len(before)), 'after': int(len(after))}
}
result"""

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
    def _current_host_snapshot(messages: list[dict], system: Any) -> dict[str, Any]:
        """Read the actual v2 model input; never rebuild a host fact."""
        marker = "</accepted_answer_contract>\n"
        for content in [str(system or ""), *(str(m.get("content") or "") for m in reversed(messages))]:
            offset = content.rfind(marker)
            if offset >= 0:
                host, _ = json.JSONDecoder().raw_decode(content[offset + len(marker):])
                if {"snapshot_digest", "requirements", "claims", "artifacts"}.issubset(host):
                    # Decode only the public model view, never hidden state.
                    # Shared scopes are exact references, not missing inputs.
                    if host.get("model_view_schema") == "publication_model_view.v1" and not host.get("model_view_issue"):
                        scopes = host["catalog_context"]["scopes"]
                        for target in host.get("execution_targets", []):
                            if "business_scope_ref" in target:
                                target["business_scope"] = scopes[target.pop("business_scope_ref")]
                            for delivery in target.get("necessary_deliveries", []):
                                if "scope_ref" in delivery:
                                    delivery["scope"] = scopes[delivery.pop("scope_ref")]
                    return host
        raise RuntimeError("rehearsal requires the current v2 host snapshot")

    def _draft(self, messages, system, text="", *, invalid_ref=False, gap_guidance=None):
        host = self._current_host_snapshot(messages, system)
        sections = []
        if host.get("model_view_issue"):
            return self._response(json.dumps({"schema": "answer_bindings.v2",
                "snapshot_digest": host["snapshot_digest"], "sections": []}, ensure_ascii=False))
        for req in host["requirements"]:
            if req["withdrawn"]:
                continue
            parts = [{"kind": "claim", "ref": cid} for cid in req["claim_ids"]]
            parts += [{"kind": "artifact", "ref": aid} for aid in req["artifact_ids"]]
            if invalid_ref:
                parts.append({"kind": "claim", "ref": "frozen_foreign_claim"})
            elif text and req["open_purposes"]:
                parts.append({"kind": "text", "purpose": req["open_purposes"][0],
                              "text": text, "claim_refs": req.get("context_claim_ids",req["claim_ids"])})
            # Explicit fixed-model proposals, not product rules or semantic
            # oracles. The normal publication service audits them once.
            guidance = (gap_guidance or {}).get(req["text"], {})
            if req["gap"] and not invalid_ref:
                for purpose in ("limitation", "conditional_action"):
                    if guidance.get(purpose):
                        parts.append({"kind": "text", "purpose": purpose,
                                      "text": guidance[purpose], "claim_refs": []})
            sections.append({"requirement_ids": [req["id"]], "parts": parts})
        return self._response(json.dumps({"schema": "answer_bindings.v2",
            "snapshot_digest": host["snapshot_digest"], "sections": sections}, ensure_ascii=False))

    def _audit_response(self, request):
        # Fixed scenario decisions exercise transport and locality only.
        # They are not a semantic-quality oracle or a model implementation.
        unsafe = {"本期成本每单高于基准期，因此下一窗口的停止条件已经触发，现在必须立即暂停增加预算。",
                  "渠道 A 的 D30 留存预计为 5%。"}
        decisions = [{"part_id": part["part_id"],
                      "disposition": "reject" if part["text"] in unsafe else "accept",
                      "reason": "冻结脚本裁决；只验证审核机制与局部隔离。",
                      "evidence_refs": part["requirement_ids"] + part["claim_refs"]}
                     for part in request["parts"]]
        self.trace.append("scripted_semantic_audit", part_count=len(decisions),
                          rejected=sum(d["disposition"] == "reject" for d in decisions))
        return self._response(json.dumps({"schema": "publication_audit.v2",
            "snapshot_digest": request["snapshot_digest"], "draft_digest": request["draft_digest"],
            "decisions": decisions}, ensure_ascii=False))

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
            if str(ref.get("dataset") or "") != "hyp" or ref.get("plan_id") != plan_id:
                continue
            payload = json.loads(Path(str(ref["artifact_path"])).read_text(encoding="utf-8"))
            hypotheses = payload.get("hypotheses") or []
            if hypotheses:
                return str(hypotheses[0]["id"]), plan_id, contract_id
        raise RuntimeError("B04 requires a persisted hypothesis set for dataset hyp")

    @classmethod
    def _hypothesis_evidence(cls, relation: str, observed: str, delta: int) -> dict[str, Any]:
        hypothesis_id, plan_id, contract_id = cls._current_hypothesis()
        from data_agent.agent.context import get_current_context

        receipts = get_current_context().analysis_state.tool_receipts
        receipt_id = next(
            (str(receipt["id"]) for receipt in reversed(receipts)
             if receipt.get("tool_name") == "compare_periods"
             and "hyp" in (receipt.get("data_identities") or {})),
            "",
        )
        if not receipt_id:
            raise RuntimeError("B04 relation requires an actual compare_periods receipt")
        return {
            "plan_id": plan_id,
            "step_id": "period_compare_amount",
            "claim_key": f"b04_{relation}_{observed}",
            "claim": "amount changed between the compared periods in hyp.",
            "dataset": "hyp",
            "dataset_contract_id": contract_id,
            "method": "compare_periods",
            "tool_calls": ["compare_periods"],
            "tool_receipt_ids": [receipt_id],
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

    @classmethod
    def _inferred_trend_evidence(cls, label: str) -> dict[str, Any]:
        from data_agent.agent.context import get_current_context

        state = get_current_context().analysis_state
        plan_id = str((state.analysis_plan or {}).get("id") or "")
        contract_id = next(
            (str(item.get("id") or "") for item in state.dataset_contracts
             if str(item.get("dataset") or "") == "hyp"),
            "",
        )
        hypothesis_id = ""
        for ref in reversed(state.hypothesis_sets):
            if ref.get("plan_id") != plan_id or ref.get("dataset") != "hyp":
                continue
            payload = json.loads(Path(str(ref["artifact_path"])).read_text(encoding="utf-8"))
            hypothesis_id = str((payload.get("hypotheses") or [{}])[0].get("id") or "")
            break
        if not hypothesis_id:
            raise RuntimeError("B04 inferred trend requires a current-plan hypothesis ID")
        receipt_id = next(
            (str(receipt["id"]) for receipt in reversed(state.tool_receipts)
             if receipt.get("tool_name") == "analyze_time_series"
             and receipt.get("arguments") == {"name": "hyp"}
             and "hyp" in (receipt.get("data_identities") or {})),
            "",
        )
        if not receipt_id:
            raise RuntimeError("B04 inferred trend requires a name-only time-series receipt")
        return {
            "claim_key": f"b04_inferred_{label}",
            "claim": "The current hyp amount trend is descriptive only.",
            "dataset": "hyp", "dataset_contract_id": contract_id,
            "method": "analyze_time_series", "tool_calls": ["analyze_time_series"],
            "tool_receipt_ids": [receipt_id],
            "result_summary": "Current amount trend came from the bound tool result.",
            "limitations": ["descriptive only; no causal inference"],
            "confidence": "medium",
            "measurements": [{"metric": "trend_slope", "value": 5 if label == "v1" else 0}],
            "competing_hypotheses": [{
                "hypothesis_id": hypothesis_id, "relation": "supports",
                "metric": "trend_slope", "observed": "increased" if label == "v1" else "flat",
            }],
        }

    @staticmethod
    def _response(text: str = "", calls: list[tuple[str, dict]] | None = None):
        from data_agent.llm.client import Response, ToolCall

        return Response(
            text=text,
            tool_calls=[ToolCall(f"p7-{index}-{name}", name, args) for index, (name, args) in enumerate(calls or [], 1)],
        )

    @staticmethod
    def _s2_inputs():
        # Reuse the original frozen business prompts, without marker rewriting.
        path = Path(__file__).with_name("p08_real_matrix_contract.json")
        return json.loads(path.read_text(encoding="utf-8"))["scenario_inputs"]

    @classmethod
    def _s2_key(cls, content):
        for scenario, spec in cls._s2_inputs().items():
            for number, prompt in enumerate(spec["prompts"], 1):
                if content == prompt or content.startswith(prompt + "\n"):
                    return scenario, number
        return None

    @staticmethod
    def _s2_context(prompt, field, default):
        marker = "\n" + field + ": "
        if marker not in prompt:
            return default
        return json.JSONDecoder().raw_decode(prompt.partition(marker)[2])[0]

    def _s2_intent(self, prompt):
        user = prompt.partition("用户输入:")[2].partition("会话上下文:")[0].strip()
        key = self._s2_key(user)
        if key is None:
            return None
        scenario, number = key
        original = self._s2_inputs()[scenario]["prompts"][number-1]
        canonical = self._s2_context(prompt, "canonical_requirements", [])
        active = [r for r in canonical if r.get("lifecycle_status") == "active"]
        def output(span, kind="result", datasets=None, **kw):
            return {"exact_span":span, "kind":kind, **({"purposes":["interpretation"]} if kind=="result" and kw.get("op","add")!="reuse" else {}), **({"business_scope":{"datasets":datasets}} if datasets else {}), **kw}
        route = "directed_analysis"
        if scenario == "M01" and number < 3:
            route = "knowledge_qa" if number == 1 else "analysis_consultation"
            outputs = [output(original, "knowledge")]
        elif scenario == "M05" and number > 1 or scenario == "M03" and number == 2:
            route = "result_followup"
            styles = {2:"business",3:"analyst",4:"manager",5:"plain",6:"technical"}
            outputs = [output(original,"presentation",presentation_style=styles.get(number,"technical"))]
        elif scenario == "M06" and number == 4:
            prior = next(r for r in reversed(active) if r["original_text"] == "账面净收益")
            outputs = [output("账面净收益",op="reuse",target_id=prior["id"])]
        elif scenario == "M01" and number == 3:
            outputs = [output("已验证的关键业务事实",datasets=["M01-sales"]),output("有条件的行动建议","conditional_action",["M01-sales"])]
        elif scenario == "M01":
            outputs = [output("两个七日窗口的金额、活动成本、净贡献、订单数",datasets=["M01-action"]),output("只有在下一同口径七日窗口净贡献不低于基准期、且成本每单不高于本期时，才考虑小规模受控试验；否则暂停增加预算并复核","conditional_action",["M01-action"])]
        elif scenario == "M02":
            outputs = [output("计算并解释 D1 至 D7 留存",datasets=["M02-retention"]),output("判断当前证据对 D30 能支持到什么程度",datasets=["M02-retention"])]
        elif scenario == "M03":
            outputs = [output("正文逐来源给出两日金额、绝对变化、相对变化和记录数",datasets=[f"M03-source-{i}" for i in range(1,7)]),output("同时展示六个来源各自的图表",datasets=[f"M03-source-{i}" for i in range(1,7)])]
        elif scenario == "M04":
            span = "提出并检验至少两种竞争性假设" if number == 1 else "重新判断哪些关系已失效、哪些仍未决"
            outputs = [output(span,datasets=["M04-hyp-v1"])]
            if number == 2:
                prior = next(r for r in reversed(active) if r["original_text"] == "提出并检验至少两种竞争性假设")
                outputs[0].update(op="replace",target_id=prior["id"])
        elif scenario == "M05":
            outputs = [output("订单记录数与 amount 总额",datasets=["M01-sales"])]
        elif number == 1:
            outputs = [output("分析名为 missing_orders 的数据集",datasets=["missing_orders"])]; outputs[0].pop("purposes",None)
        elif number == 2:
            outputs = [output("哪些结果已计算",datasets=["M01-sales"]),
                       output("哪些未计算",datasets=["M01-sales"]),output("哪些证据不足","gap",["M01-sales"])]; outputs[1].pop("purposes",None)
        else:
            outputs = [output("账面净收益",datasets=["m06_promo"])]
            if number == 5:
                prior = next(r for r in reversed(active) if r["original_text"] == "账面净收益")
                outputs[0].update(op="replace",target_id=prior["id"])
        result = {"intent_type":route,"clarity":"clear","ambiguities":[],"requested_outputs":outputs}
        uploads = self._s2_context(prompt,"current_uploads",{}).get("uploads",[])
        if scenario == "M04" and number == 2 or scenario == "M06" and number in {3,5}:
            assert len(uploads) == 1
            name = "M04-hyp-v1" if scenario == "M04" else "m06_promo"
            result["upload_bindings"] = [{"upload_id":uploads[0]["upload_id"],"dataset":name,"relation":"replace" if number in {2,5} else "new","exact_span":original.split("。",1)[0],**({"object_span":"m06_promo"} if scenario=="M06" else {})}]
        self.trace.append("s2_intent_proposal",scenario=scenario,number=number,proposal=result)
        return self._response(json.dumps(result,ensure_ascii=False))

    def _s2_next(self, key, messages, system):
        scenario, number = key
        host = self._current_host_snapshot(messages,system)
        marker = f"S2-{scenario}-{number}"
        step = self._rounds[marker]; self._rounds[marker] += 1
        self.trace.append("s2_model_proposal",scenario=scenario,number=number,step=step)
        def calls(*items): return self._response(calls=list(items))
        def declarations(req):
            if req.get("necessary_deliveries"): return [(d["kind"],d["scope"]) for d in req["necessary_deliveries"]]
            names = req.get("business_scope",{}).get("datasets",[])
            if req["semantic_kind"] == "conditional_action":
                return [("conditional_action",{"datasets":names})]
            specs=[]
            for name in names:
                if scenario=="M06" and number==2 and texts[req["id"]]=="哪些未计算":
                    specs.append(("measurement",{"datasets":[name],"metrics":["净收益"],"quantity":"value"}))
                elif scenario in {"M01","M05","M06"} and name == "M01-sales":
                    specs += [("measurement",{"datasets":[name],"quantity":q,**({"metrics":["amount"]} if q=="sum" else {})}) for q in ["rows","sum","calendar_days"]]
                elif scenario == "M01":
                    window={"period_a":"2026-09-07~2026-09-13","period_b":"2026-09-14~2026-09-20"}
                    specs += [("measurement",{"datasets":[name],"metrics":[metric],"quantity":q,"parameters":window}) for metric in ["amount","campaign_cost","net_contribution","orders"] for q in ["sum","difference","relative_change"]]
                    specs += [("measurement",{"datasets":[name],"quantity":q,"parameters":window}) for q in ["rows","calendar_days"]]
                elif scenario == "M02":
                    kinds=["scenario"] if req["id"] == result_ids[-1] else ["series","fit"]
                    specs += [(kind,{"datasets":[name],"metrics":["retention"]}) for kind in kinds]
                elif scenario == "M03":
                    if "图表" in texts[req["id"]]: specs.append(("chart",{"datasets":[name]}))
                    else:
                        window={"period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"}
                        specs += [("measurement",{"datasets":[name],"quantity":q,"parameters":window,**({"metrics":["amount"]} if q!="rows" else {})}) for q in ["sum","difference","relative_change","rows"]]
                elif scenario == "M04":
                    specs += [("table",{"datasets":[name]}),("measurement",{"datasets":[name],"metrics":["amount"],"quantity":"difference","parameters":{"period_a":"2026-09-01~2026-09-01","period_b":"2026-09-03~2026-09-03"}}),("hypothesis",{"datasets":[name],"metrics":["amount"]})]
                elif name == "m06_promo": specs.append(("measurement",{"datasets":[name],"metrics":["账面净收益"],"quantity":"value"}))
            return specs
        consult = scenario=="M01" and number<3
        followup = scenario=="M05" and number>1 or scenario=="M03" and number==2 or scenario=="M06" and number==4
        if not consult and not followup and scenario!="M06" or scenario=="M06" and number!=1 and not followup:
            if scenario=="M06" and number in {2,3,5} and step==0:
                if number==2:
                    return calls(("ask_user_question",{"question":"账面净收益应扣除哪些成本？","options":[{"label":"仅代金券成本","value":"coupon"},{"label":"代金券及渠道成本","value":"both"}],"confirmation_type":"metric_scope","blocking_reason":"成本范围改变账面净收益。"}))
                return calls(("ask_user_question",{"measurement_mapping":json.dumps({"exact_span":"账面净收益","dataset":"m06_promo","column":"incremental_revenue","cost_scopes":[["coupon_cost"],["coupon_cost","channel_cost"]]},ensure_ascii=False)}))
            plan_step = 1 if scenario=="M06" else 0
            if step==plan_step:
                texts={r["id"]:r["text"] for r in host["requirements"] if not r["withdrawn"]}
                targets=[r for r in host["execution_targets"] if r["id"] in texts and r["semantic_kind"] in {"result","conditional_action"}]
                result_ids=[r["id"] for r in targets if r["semantic_kind"]=="result"]
                products=[d for r in targets for d in (r.get("necessary_deliveries") or [{"requirement_id":r["id"],"kind":kind,"label":f"{scenario}-{i}-{kind}","scope":scope} for i,(kind,scope) in enumerate(declarations(r))])]
                names=sorted({n for d in products for n in d["scope"].get("datasets",[])})
                plan={"contract_version":"stage3c0b.v2","requirement_revision":host["requirement_revision"],"goal":self._s2_inputs()[scenario]["prompts"][number-1],"method_plan":[{"step_id":"s2_products","goal":"Complete original business products","expected_output":"Each requested original product and open obligation","evidence_requirements":["actual receipt"],"dataset_inputs":names,"required_deliveries":products}]}
                return calls(("record_analysis_plan",{"plan_json":plan}))
            execute_step=plan_step+1
            if step==execute_step:
                if scenario in {"M05","M06"} or scenario=="M01" and number==3:
                    if scenario=="M06" and number in {3,5}:
                        return calls(("derive_field",{"name":"m06_promo","field_name":"net_book_profit_v2" if number==5 else "net_book_profit","expression":"incremental_revenue - coupon_cost - channel_cost"}))
                    return calls(("describe_dataset",{"name":"M01-sales"}))
                if scenario=="M01":
                    return calls(("compare_periods",{"name":"M01-action","date_col":"date","metrics":"amount,campaign_cost,net_contribution,orders","period_a":"2026-09-07~2026-09-13","period_b":"2026-09-14~2026-09-20"}))
                if scenario=="M02": return calls(("curve_fitting",{"name":"M02-retention","x_col":"day","y_col":"retention","scenario_points":[30]}))
                if scenario=="M03": return calls(*[("compare_periods",{"name":f"M03-source-{i}","date_col":"date","metrics":"amount","period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"}) for i in range(1,7)])
                if scenario=="M04": return calls(("preview_data",{"name":"M04-hyp-v1","n":10}),("compare_periods",{"name":"M04-hyp-v1","date_col":"date","metrics":"amount","period_a":"2026-09-01~2026-09-01","period_b":"2026-09-03~2026-09-03"}))
            if scenario=="M04" and step==2:
                ids = re.findall(r"id=([A-Za-z0-9_-]+) \[",str(system).rsplit("<competing_hypotheses>",1)[-1].split("</competing_hypotheses>",1)[0])
                if not ids: raise RuntimeError("Current hypothesis IDs absent from model context")
                result = next(json.JSONDecoder().raw_decode(m["content"])[0] for m in reversed(messages)
                              if m.get("role")=="tool" and m.get("content","").lstrip().startswith('{\n  "period_a"'))
                delta = result["metrics"]["amount"]["diff"]
                observed = "increased" if delta>0 else "decreased" if delta<0 else "flat"
                evidence={"claim":"Current amount comparison is descriptive only","dataset":"M04-hyp-v1","method":"compare_periods","tool_calls":["compare_periods"],"result_summary":"Current comparison tool result","limitations":["No causal or population grant"],"confidence":"medium","measurements":[{"metric":"amount","value":delta,"delta":delta}],"competing_hypotheses":[{"hypothesis_id":hid,"relation":"supports" if delta else "refutes","metric":"amount","observed":observed} for hid in ids]}
                return calls(("record_evidence_record",{"record_json":evidence}))
            if scenario=="M03" and step==2:
                return calls(*[("create_chart",{"chart_type":"bar","data":f"M03-source-{i}","title":f"M03-source-{i} amount 原值","x_col":"date","y_col":"amount","purpose":"exploratory","scale_mode":"raw"}) for i in range(1,7)])
            if scenario=="M06" and number in {3,5} and step==3:
                return calls(("transform_data",{"name":"m06_promo_net_book_profit_v2" if number==5 else "m06_promo_net_book_profit","operation":"group_aggregate","group_by":["channel"],"aggregations":[{"column":c,"functions":["sum"]} for c in ["incremental_revenue","coupon_cost","channel_cost","net_book_profit_v2" if number==5 else "net_book_profit"]],"save_as":"m06_promo_net_total_v2" if number==5 else "m06_promo_net_total"}))
        if scenario=="M06" and number==1 and step==0: return calls(("list_data",{}))
        text = {
            ("M01",1):"p值是在零假设和检验前提成立时，得到同样或更极端结果的概率；不能解释为零假设为真的概率。",
            ("M01",2):"方案：先定义留存对象、起始事件和回访事件，准备稳定用户标识与事件日期，按同一队列计算逐日留存，核验观察窗口完整性。聚合留存序列可以描述曲线；用户级字段缺失时不能重建个体流失，也不能从拟合证明干预效果。",
            ("M01",3):"金额单位未知，只有当前上传订单的描述性证据。若后续同口径观察仍支持稳定性，可考虑小规模受控试验；出现缺失、异常或结果不稳定则停止扩大并复核。不能推断因果或总体。",
            ("M01",4):"只有在下一同口径七日窗口净贡献不低于基准期、且成本每单不高于本期时，才考虑小规模受控试验；否则暂停增加预算并复核。下一窗口尚未观测，当前不能声称任何分支已触发。金额单位未知，仅作描述比较，不能推断因果。",
            ("M02",1):"留存是当前聚合观测原值，单位未知，零值语义未知。D30真实值未知；各模型族只给拟合情景，参数、公式、R²与观测范围以原测量为准。不同族的情景差异反映敏感性；未做留出验证、回测或外部验证，不能作为已验证预测，也无需用户级字段才能描述这组聚合观测。",
            ("M03",1):"六来源分别保留原值、记录数和变化，金额单位未知。相邻日期比较不能叫同比；没有跨来源合计，也不能推断因果。各图只对应同一来源的原值。",
            ("M03",2):"逐来源事实与六张原图继续使用原接受答案；金额单位未知，未请求跨来源业务总额，压缩摘要不产生新事实。",
            ("M04",1):"原始序列与描述比较保留。竞争假设按真实工具测量核对；方向关系不能升级成因果，支持、反证、冲突和未决仍需逐项可审计。",
            ("M04",2):"v1原证据保留审计；当前v2独立测量不能继承旧版结论，变化关系仍需当前证据重新判断。仅为描述性判断，不能推断因果。",
            ("M06",1):"下一步：请上传 missing_orders 对应文件。",
            ("M06",2):"当前订单原值已计算。成本口径选择不提供成本金额；净收益和成本尚未计算，促销增量效果证据不足，不能将缺失成本归零或推断因果。",
            ("M06",3):"账面净收益只使用当前用户确认的列公式；金额单位未知，incremental_revenue仅为账面原值，不证明促销增量或因果。",
            ("M06",4):"复用同版本同范围的账面公式与原测量，不重新请求内部方法许可；金额单位未知，不证明促销增量或因果。",
            ("M06",5):"新版重新确认后的账面公式只属于当前来源版本；旧版金额与授权不作为新版证据。单位未知，不证明增量或因果。",
        }.get(key, "")
        if scenario=="M05":
            text=["事实摘要：先列当前订单的原始记录数与amount总额，再说明证据边界。","业务负责人：这些原值用于核对当前业务规模；行动前先确认成本和效果，不据此扩大投放。","分析师：计算方法为记录计数与amount原列求和；来源、日期范围和回执均随原测量保留。","管理者：当前证据只支持规模描述；决策条件是补齐成本与对照证据，条件不足时保留判断。","大白话：这是上传这批订单的数量和金额加总；这点信息还不能说明活动有没有用。","技术表达：使用describe_dataset原始计数及列求和，保留精确来源版本、观测日期和必要限制。"][number-1]+"金额单位未知，仅描述当前上传记录，不作总体或因果推断。"
        return self._draft(messages,system,text)

    def chat(self, messages, tools=None, system=None):  # auxiliary intent/playbook calls
        self.trace.append("auxiliary_call", messages=len(messages))
        prompt = str(messages[-1].get("content") or "") if messages else ""
        try:
            request = json.loads(prompt)
        except (ValueError, TypeError):
            request = None
        if isinstance(request, dict) and request.get("schema") == "publication_audit_request.v3":
            return self._audit_response(request)
        if "你是一个数据分析助手的意图分类器" in prompt:
            proposal = self._s2_intent(prompt)
            if proposal is not None: return proposal
            original_input = prompt.partition("用户输入:")[2].partition("会话上下文:")[0].strip().partition("\n分析文件: ")[0]
            for case, (content, route, _) in P4_REQUESTS.items():
                if original_input != f"【{case}】{content}":
                    continue
                kind = "presentation" if route == "result_followup" else "knowledge"
                outputs = [{"exact_span": content, "kind": kind}]
                if case == "INTENT-01":
                    outputs = [{"exact_span": "计算总收入", "kind": "result", 'business_scope': {'datasets': ['f_sales']}}]
                elif case == "INTENT-02":
                    outputs = [{"exact_span": "只导出当前表", "kind": "result", 'business_scope': {'datasets': ['f_sales']}}]
                elif case == "INTENT-05":
                    outputs=[{"exact_span":"7日收入","kind":"result",'business_scope':{'datasets': ['lifecycle_sales'], 'metrics': ['income7'], 'quantity': 'value', 'parameters': {'window_days':7}}},
                             {"exact_span":"复购率","kind":"result",'business_scope':{'datasets': ['lifecycle_sales'], 'metrics': ['repurchase'], 'quantity': 'value'}}]
                elif case == "INTENT-05-CHANGE":
                    declared,_=json.JSONDecoder().raw_decode(prompt.partition("canonical_requirements: ")[2])
                    old={r["original_text"]:r["id"] for r in declared if r["lifecycle_status"]=="active"}
                    outputs=[{"exact_span":"30日收入","kind":"result","op":"replace","target_id":old["7日收入"],'business_scope':{'datasets': ['lifecycle_sales'], 'metrics': ['income30'], 'quantity': 'value', 'parameters': {'window_days':30}}},
                             {"exact_span":"不再要求复购率","kind":"result","op":"withdraw","target_id":old["复购率"]}]
                elif case.startswith("INTENT-04"):
                    outputs = [{"exact_span": span, "kind": "result", 'business_scope': {'datasets': ['card_users','card_coupons','card_before','card_after'], 'metrics': [span], 'quantity': 'value'}} for span in sorted(P4_CARD_METRICS,key=content.index)]
                    outputs += [{"exact_span":"判断连续付费是否因省钱卡刺激提升","kind":"gap"},
                                {"exact_span":"说明计算方式","kind":"knowledge"}]
                elif case == "M06-TYPED-REUSE":
                    outputs = [{"exact_span":"账面净收益","kind":"presentation"}]
                elif case.startswith("M06-TYPED"):
                    outputs = [{"exact_span":"账面净收益","kind":"result",'business_scope':{'datasets': ['ic_promo'], 'metrics': ['账面净收益'], 'quantity': 'value'}}]
                    if case=="M06-TYPED-CHANGE":
                        declared,_=json.JSONDecoder().raw_decode(prompt.partition("canonical_requirements: ")[2])
                        prior=next(r for r in declared if r["original_text"]=="账面净收益" and r["lifecycle_status"]=="active" and r["semantic_kind"]=="result")
                        outputs[0].update(op="replace",target_id=prior["id"])

                elif case == "INTENT-03":
                    outputs = [{"exact_span": "先解释同比含义", "kind": "knowledge"},
                               {"exact_span": "再算当前文件的同比", "kind": "result", 'business_scope': {'datasets': ['yoy_sales']}}]
                return self._response(json.dumps({"intent_type": route, "ambiguities": [], "requested_outputs": outputs}, ensure_ascii=False))
            if original_input == "【CONTENT-B07】展示表格与公式和图表，保留当前原值与范围。":
                return self._response(json.dumps({"intent_type":"directed_analysis","ambiguities":[],"requested_outputs":[
                    {"exact_span":"表格与公式","kind":"result",'business_scope':{'datasets': ['presentation_sales']},"purposes":["knowledge"]},
                    {"exact_span":"图表","kind":"result",'business_scope':{'datasets': ['presentation_sales']},"purposes":["knowledge"]}]},ensure_ascii=False))
            if original_input.startswith(("【B03】","【B03-CHART】","【B03-PREVIEW】")):
                span=original_input.partition("】")[2].split("并展示六个来源各自的图表")[0].rstrip("；")
                window = {"period_a":"2026-09-01~2026-09-02","period_b":"2026-09-03~2026-09-04"} if original_input.startswith("【B03-PREVIEW】") else {"period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"}
                outputs=[{"exact_span":span,"kind":"result",'business_scope':{'datasets': [f'src_{i}' for i in range(1, 7)], 'metrics': ['amount'], 'parameters': window}}]
                if "并展示六个来源各自的图表" in original_input:
                    outputs.append({"exact_span":"并展示六个来源各自的图表","kind":"result",'business_scope':{'datasets': [f'src_{i}' for i in range(1, 7)]}})
                return self._response(json.dumps({"intent_type":"directed_analysis","ambiguities":[],"requested_outputs":outputs},ensure_ascii=False))
            if original_input.startswith("【B03-SYNTH】"):
                return self._response(json.dumps({"intent_type":"directed_analysis","ambiguities":[],"requested_outputs":[{"exact_span":original_input.partition("】")[2],"kind":"result",'business_scope':{'datasets': ['src_1','src_2']}}]},ensure_ascii=False))
            if original_input.startswith("【B03-PIVOT】"):
                return self._response(json.dumps({"intent_type":"directed_analysis","ambiguities":[],"requested_outputs":[{"exact_span":original_input.partition("】")[2],"kind":"result",'business_scope':{'datasets': ['pivot_sales']}}]},ensure_ascii=False))
            if original_input == "好的，继续。":
                return self._response(json.dumps({"intent_type":"result_followup","ambiguities":[],"requested_outputs":[{"exact_span":original_input,"kind":"presentation"}]},ensure_ascii=False))
            if original_input.startswith(("【B04】","【B04-INFER】")):
                tool="analyze_time_series" if original_input.startswith("【B04-INFER】") else "compare_periods"
                outputs=[]
                if "竞争假设" in original_input:
                    outputs=[{"exact_span":"竞争假设","kind":"result",'business_scope':{'datasets': ['hyp'], 'metrics': ['amount']}}]
                else:
                    outputs=[{"exact_span":original_input.partition("】")[2],"kind":"presentation"}]
                if original_input == "【B04-INFER】重新分析当前版本的 amount 竞争假设和描述性趋势。":
                    declared,_=json.JSONDecoder().raw_decode(prompt.partition("canonical_requirements: ")[2])
                    prior=next(r for r in declared if r["original_text"]=="竞争假设" and r["lifecycle_status"]=="active")
                    outputs[0].update(op="replace",target_id=prior["id"])
                plan=re.search(r"current_analysis_plan_id:\s*([A-Za-z0-9_-]+)",prompt)
                return self._response(json.dumps({"intent_type":"directed_analysis","ambiguities":[],"requested_outputs":outputs,
                    "continuation_of_plan_id":plan.group(1) if plan else ""},ensure_ascii=False))
            current_input = prompt.partition("用户输入:")[2].partition("会话上下文:")[0].lower()
            if original_input == "【B05-PY-NOROW】计算当前订单原值和含首尾的日期天数。":
                return self._response(json.dumps({"intent_type":"directed_analysis","ambiguities":[],"requested_outputs":[
                    {"exact_span":"当前订单原值","kind":"result",'business_scope':{'datasets': ['f_sales']}},
                    {"exact_span":"含首尾的日期天数","kind":"result",'business_scope':{'datasets': ['f_sales'], 'metrics': ['inclusive_days'], 'quantity': 'value'}}]},ensure_ascii=False))
            if original_input.startswith("【B02-MULTI】"):
                return self._response(json.dumps({"intent_type":"directed_analysis","ambiguities":[],"requested_outputs":[{"exact_span":original_input[len("【B02-MULTI】"):].strip(),"kind":"result","business_scope":{"datasets":["ret_a","ret_b"],"metrics":["retention"]}}]},ensure_ascii=False))
            # Frozen transport proposals bind the actual tool family. They
            # are input fixtures, never a production semantic classifier.
            fixed_targets = {
                "【b01-describe】": ("f_sales", "describe_dataset"),
                "【b02】": ("ret_a", "curve_fitting"),
                "【b02-neg】": ("ret_a", "curve_fitting"),
                "【b02-confirm】": ("ret_a", "curve_fitting"),
                "【b05-py】": ("f_sales", "run_python"),
                "【b05-py-norow】": ("f_sales", "run_python"),
                "【b01-edge】": ("edge_sales", "transform_data"),
            }
            for marker, (dataset, tool) in fixed_targets.items():
                if original_input.lower().startswith(marker):
                    return self._response(json.dumps({"intent_type": "directed_analysis", "ambiguities": [],
                        "requested_outputs": [{"exact_span": original_input[len(marker):].strip(), "kind": "result",
                            'business_scope': {'datasets': [dataset]}}]}, ensure_ascii=False))
            if any(marker in current_input for marker in (
                    "【b01-describe-action】", "【b01-describe-action-risk】")):
                return self._response(json.dumps({
                    "intent_type": "directed_analysis", "ambiguities": [],
                    "requested_outputs": [
                        {"exact_span": "记录数、amount 原值和日期范围", "kind": "result", 'business_scope': {'datasets': ['f_sales']}},
                        {"exact_span": "两个七日窗口的金额、活动成本、净贡献和订单数", "kind": "result", 'business_scope': {'datasets': ['action_sales']}},
                        {"exact_span": "有条件行动建议", "kind": "conditional_action", 'business_scope': {'datasets': ['action_sales']}},
                        {"exact_span": "只有下一同口径七日窗口净贡献不低于基准期且成本每单不高于本期", "kind": "conditional_action", 'business_scope': {'datasets': ['action_sales']}},
                        {"exact_span": "否则暂停增加预算并复核", "kind": "conditional_action", 'business_scope': {'datasets': ['action_sales']}},
                    ],
                }, ensure_ascii=False))
            if any(marker in current_input for marker in (
                    "【b01-action-multi】", "【b01-action-multi-neg】",
                    "【b01-action-multi-risk】", "【b01-action-multi-stale】")):
                requested = [
                    {"exact_span": "有条件行动建议", "kind": "conditional_action", 'business_scope': {'datasets': ['action_sales']}},
                    {"exact_span": "只有下一同口径七日窗口净贡献不低于基准期且成本每单不高于本期", "kind": "conditional_action", 'business_scope': {'datasets': ['action_sales']}},
                    {"exact_span": "否则暂停增加预算并复核", "kind": "conditional_action", 'business_scope': {'datasets': ['action_sales']}},
                ]
                if "保留上一轮已核的 f-sales 当前原值和日期范围" in current_input:
                    requested.append({
                        "exact_span": "保留上一轮已核的 F-SALES 当前原值和日期范围",
                        "kind": "result", 'business_scope': {'datasets': ['f_sales']},
                    })
                return self._response(json.dumps({
                    "intent_type": "directed_analysis", "ambiguities": [],
                    "requested_outputs": requested,
                }, ensure_ascii=False))
            if "【b01】" in current_input or "【b01-action】" in current_input:
                return self._response(json.dumps({
                    "intent_type": "directed_analysis", "ambiguities": [],
                    "requested_outputs": [
                        {"exact_span": "有条件行动建议", "kind": "conditional_action", 'business_scope': {'datasets': ['action_sales']}},
                    ],
                }, ensure_ascii=False))
            if "【b06-missing】" in current_input:
                return self._response(json.dumps({
                    "intent_type": "directed_analysis", "ambiguities": [],
                    "requested_outputs": [
                        {"exact_span": "分析 missing_orders", "kind": "result",
                         'business_scope': {'datasets': ['missing_orders']}},
                        {"exact_span": "明确说明缺口", "kind": "gap"},
                        {"exact_span": "只给一个具体下一步动作", "kind": "presentation"},
                    ],
                }, ensure_ascii=False))
            for marker, span, style, action_span in (
                ("【b05-business】", "业务负责人表达", "business", "建议的触发和停止条件"),
                ("【b05-analyst】", "分析师表达", "analyst", None),
                ("【b05-manager】", "管理者表达", "manager", "触发和停止条件"),
                ("【b05-plain】", "大白话重述", "plain", None),
                ("【b05-tech】", "技术表达", "technical", None),
            ):
                if marker in current_input:
                    requested = [{
                        "exact_span": span, "kind": "presentation",
                        "presentation_style": style,
                    }]
                    if action_span:
                        requested.append({
                            "exact_span": action_span, "kind": "conditional_action",
                        })
                    return self._response(json.dumps({
                        "intent_type": "result_followup", "ambiguities": [],
                        "requested_outputs": requested,
                    }, ensure_ascii=False))
        if ("你是一个数据分析助手的意图分类器" in prompt
                and any(marker in prompt.lower()
                        for marker in ("【ic-b03】", "【ic-b03-data】"))):
            return self._response(json.dumps({
                "intent_type": "directed_analysis", "ambiguities": [],
                "requested_outputs": [
                    {"exact_span": "促销净收益", "kind": "result"},
                    {"exact_span": "已算、未算和缺少证据分开", "kind": "gap"},
                ],
            }, ensure_ascii=False))
        if ("你是一个数据分析助手的意图分类器" in prompt
                and (re.search(r"用户输入:\s*【b04】继续第\d+步", prompt, re.I)
                     or original_input in {"【B04-INFER】更新版本后保留旧关系的失效边界。", "【B04-INFER】重新分析当前版本的 amount 竞争假设和描述性趋势。"})):
            plan_ref = re.search(r"current_analysis_plan_id:\s*([A-Za-z0-9_-]+)", prompt)
            if plan_ref:
                return self._response(json.dumps({
                    "intent_type": "directed_analysis", "clarity": "clear",
                    "ambiguities": [], "continuation_of_plan_id": plan_ref.group(1),
                }, ensure_ascii=False))
        return self._response('{"intent_type":"directed_analysis","clarity":"clear"}')

    def _next(self, marker: str, messages: list[dict], system: Any = None):
        # The scripted model declares products before dispatch through the same
        # registered tool as the natural model. Scenario prompts/oracles stay fixed.
        from copy import deepcopy
        from data_agent.agent.context import get_current_context
        from data_agent.agent.publication.requirements import target_datasets
        ctx=get_current_context();state=ctx.analysis_state
        user=self._last_user(messages)
        counter=marker+":"+user if marker in {"B04","B04-INFER"} else marker
        response=self._scenario_next(marker,messages,system)
        if not response.tool_calls or all(c.name in {"load_data","reload_data","record_evidence_record"} for c in response.tool_calls):return response
        current=[r for r in state.answer_requirements if r.get("lifecycle_status")=="active" and r["id"] in ctx.turn_requirement_ids and r["semantic_kind"] in {"result","conditional_action"}]
        key=(ctx.session_id,user,tuple(ctx.turn_requirement_ids))
        planned=getattr(self,"_planned_requests",set())
        self.trace.append("scripted_plan_preflight",marker=marker,current_ids=[r["id"] for r in current],turn_ids=ctx.turn_requirement_ids,already_planned=key in planned)
        if not current or key in planned:return response
        defaults={
            "B01":[("table",{"datasets":["f_sales"],"metrics":["amount_sum","amount_count"]}),("measurement",{"datasets":["f_sales"],"quantity":"rows"})],
            "B01-DESCRIBE":[("measurement",{"datasets":["f_sales"],"quantity":"rows"}),("measurement",{"datasets":["f_sales"],"metrics":["amount"],"quantity":"sum"}),("measurement",{"datasets":["f_sales"],"quantity":"calendar_days"})],
            "B05-PY":[("table",{"datasets":["f_sales"]})],
            "B05-PY-NOROW":[("table",{"datasets":["f_sales"]})],
            "B01-EDGE":[("table",{"datasets":["edge_sales"]})],
            "B03-PIVOT":[("table",{"datasets":["pivot_sales"]})],
            "B02":[(k,{"datasets":["ret_a"],"metrics":["retention"]}) for k in ["series","fit"]],
            "B02-NEG":[(k,{"datasets":["ret_a"],"metrics":["retention"]}) for k in ["series","fit"]],
            "B02-CONFIRM":[(k,{"datasets":["ret_a"],"metrics":["retention"]}) for k in ["series","fit"]],
            "INTENT-01":[("measurement",{"datasets":["f_sales"],"metrics":["amount"],"quantity":"sum"})],
            "INTENT-02":[("artifact",{"datasets":["f_sales"]})],
            "INTENT-03":[("measurement",{"datasets":["yoy_sales"],"metrics":["amount"],"quantity":"difference","parameters":{"period_a":"2025-09-01~2025-09-02","period_b":"2026-09-01~2026-09-02"}})],
            "CONTENT-B07":[("table",{"datasets":["presentation_sales"]}),("chart",{"datasets":["presentation_sales"]})],
            "B04":[("hypothesis",{"datasets":["hyp"],"metrics":["amount"]})],
            "B04-INFER":[("hypothesis",{"datasets":["hyp"],"metrics":["amount"]})],
        }
        if marker in {"B03","B03-CHART","B03-PREVIEW","CONTENT-B03"}:
            window={"period_a":"2026-09-01~2026-09-02","period_b":"2026-09-03~2026-09-04"} if marker=="B03-PREVIEW" else {"period_a":"2026-09-01~2026-09-01","period_b":"2026-09-02~2026-09-02"}
            defaults[marker]=[("measurement",{"datasets":[f"src_{i}"],"quantity":q,"parameters":window,**({"metrics":["amount"]} if q in {"sum","difference","relative_change"} else {})}) for i in range(1,7) for q in ["sum","difference","relative_change","rows","calendar_days"]]
            if marker=="B03-CHART":defaults[marker]+=[("chart",{"datasets":[f"src_{i}"]}) for i in range(1,7)]
        defaults["B02-MULTI"]=[(k,{"datasets":[n],"metrics":["retention"]}) for n in ["ret_a","ret_b"] for k in ["series","fit"]]
        if marker=="B03-SYNTH":defaults[marker]=[("measurement",{"datasets":["src_1","src_2"],"metrics":[n],"quantity":"difference","parameters":{"period_a":"2026-09-01~2026-09-02","period_b":"2026-09-03~2026-09-04"}}) for n in ["src_1","src_2"]]
        declarations=[]
        action_owner=next((r["id"] for r in current if r["semantic_kind"]=="conditional_action"),None)
        for req in current:
            if req["semantic_kind"]=="conditional_action" and req["id"]!=action_owner:continue
            if req.get("necessary_deliveries"):
                declarations.extend(deepcopy(req["necessary_deliveries"]));continue
            scope=deepcopy(req.get("business_scope",{}))
            if marker.startswith("INTENT-04"):
                scope["datasets"]=["card_users","card_coupons","card_before","card_after"]
                kind="table" if req["original_text"] in {"购买偏好","付费频次","金额区间分布","连续付费前后次数"} else "measurement"
                specs=[(kind,scope)]
            elif marker.startswith("M06-TYPED"):specs=[("measurement",{"datasets":["ic_promo"],"metrics":["账面净收益"],"quantity":"value"})]
            elif marker in {"INTENT-05","INTENT-05-CHANGE"}:specs=[("measurement",scope)]
            elif marker in defaults:
                specs=defaults[marker]
                # Independent same-turn goals choose their declared kind/scope.
                if marker=="CONTENT-B07":specs=[specs[1] if req["original_text"]=="图表" else specs[0]]
                if marker=="B05-PY-NOROW" and scope.get("metrics")==["inclusive_days"]:specs=[("measurement",scope)]
                if marker=="B03-CHART":specs=[d for d in specs if (d[0]=="chart")==("图表" in req["original_text"])]
            elif marker in {"B01-DESCRIBE-ACTION","B01-DESCRIBE-ACTION-RISK"} and req["semantic_kind"]=="result":
                specs=[("measurement",dict(scope,quantity=q)) for q in (["rows","sum","calendar_days"] if scope.get("datasets")==["f_sales"] else ["sum","difference","relative_change","rows","calendar_days"])]
            elif req["semantic_kind"]=="conditional_action":
                specs=[("measurement",{"datasets":scope.get("datasets",["action_sales"]),"metrics":[m],"quantity":q}) for m in ["amount","campaign_cost","net_contribution","orders"] for q in ["sum","difference","relative_change"]]+[("measurement",{"datasets":scope.get("datasets",["action_sales"]),"quantity":q}) for q in ["rows","calendar_days"]]
            else:
                if not scope.get("datasets"):return response
                specs=[("measurement",dict(scope,quantity=scope.get("quantity","rows")))]
            for i,(kind,bounds) in enumerate(specs):
                declarations.append({"requirement_id":req["id"],"kind":kind,"label":req["original_text"]+" / "+str(i),"scope":bounds})
        sources=sorted({n for d in declarations for n in d["scope"].get("datasets",[])})
        self.trace.append("scripted_plan_sources",marker=marker,sources={n:ctx.workspace._publication_dataset_exists(n) for n in sources})
        if not sources or any(not ctx.workspace._publication_dataset_exists(n) for n in sources):return response
        plan={"contract_version":"stage3c0b.v2","requirement_revision":state.requirement_revision,"goal":user,"method_plan":[{"step_id":"declared_products","goal":"执行原业务交付","expected_output":"逐项当前同版产品","dataset_inputs":sources,"combination_mode":"independent","evidence_requirements":["actual receipt"],"required_deliveries":declarations}],"visualization_strategy":[]}
        for step in plan["method_plan"]:step["required_deliveries"]=[{"id":d["id"]} if "id" in d else d for d in step["required_deliveries"]]
        self._rounds[counter]-=1
        planned.add(key);self._planned_requests=planned
        return self._response(calls=[("record_analysis_plan",{"plan_json":plan})])

    def _scenario_next(self, marker: str, messages: list[dict], system: Any = None):
        user = self._last_user(messages)
        counter = marker + ":" + user if marker in {"B04", "B04-INFER"} else marker
        step = self._rounds[counter]
        self._rounds[counter] += 1
        self.trace.append("scripted_round", marker=marker, step=step, user=user)

        if marker in {"INTENT-05","INTENT-05-CHANGE"}:
            if marker == "INTENT-05" and step == 0:
                return self._response(calls=[("load_data",{"source":"F-SALES.csv","name":"lifecycle_sales"})])
            if step == (1 if marker == "INTENT-05" else 0):
                window=7 if marker == "INTENT-05" else 30
                code="frame=get_dataset('lifecycle_sales')\nwindow=frame[frame['date'].between('2026-09-01','2026-09-"+str(window).zfill(2)+"')]\nresult={'income"+str(window)+"':float(window['amount'].sum())}\nresult"
                return self._response(calls=[("run_python",{"code":code,"business_parameters":{"window_days":window}})])
            return self._draft(messages,system,P4_REQUESTS[marker][2])

        if marker.startswith("INTENT-04"):
            if step == 0:
                return self._response(calls=[("load_data",{"source":f,"name":n}) for f,n in [
                    ("F-CARD.csv","card_users"),("F-COUPON.csv","card_coupons"),
                    ("F-PAY-BEFORE.csv","card_before"),("F-PAY-AFTER.csv","card_after")]])
            if step == 1:
                return self._response(calls=[("run_python",{"code":P4_CARD_CODE})])
            return self._draft(messages,system,P4_REQUESTS[marker][2], gap_guidance={
                "付费ARPU": {
                    "limitation": "当前缺少与支付额同范围的全体有效用户分母；现有付费用户数不能替代该分母。",
                    "conditional_action": "补充同范围全体有效用户分母并确认统计口径后，再重算付费ARPU。"},
                "判断连续付费是否因省钱卡刺激提升": {
                    "limitation": "当前前后支付记录只支持描述；缺少可核对照与一致时间窗口，尚不能识别刺激效果。",
                    "conditional_action": "补充可核对照与一致时间窗口，并确认研究设计后，再检验省钱卡刺激效果。"},
            })

        if marker.startswith("M06-TYPED"):
            reuse = marker == "M06-TYPED-REUSE"
            if step == 0 and not reuse:
                return self._response(calls=[("reload_data" if marker.endswith("CHANGE") else "load_data",
                    {"source":"F-PROMO-V2.csv" if marker.endswith("CHANGE") else "F-PROMO.csv","name":"ic_promo"})])
            if step == (0 if reuse else 1):
                mapping={"exact_span":"账面净收益","dataset":"ic_promo","column":"incremental_revenue",
                    "cost_scopes":[["coupon_cost"],["coupon_cost","channel_cost"]]}
                if reuse:
                    from data_agent.agent.context import get_current_context
                    mapping["source_message_ref"]=next(r["source_message_ref"] for r in get_current_context().analysis_state.answer_requirements
                        if r["original_text"]=="账面净收益" and r.get("business_scope",{}).get("metrics")==["账面净收益"])
                return self._response(calls=[("ask_user_question",{"measurement_mapping":json.dumps(mapping,ensure_ascii=False)})])
            if step == 2 and not reuse:
                return self._response(calls=[("transform_data",{"name":"ic_promo","operation":"group_aggregate","group_by":["channel"],
                    "aggregations":[{"column":c,"functions":["sum"]} for c in ["incremental_revenue","coupon_cost","channel_cost"]],"save_as":"ic_promo_summary_v2" if marker.endswith("CHANGE") else "ic_promo_summary"})])
            return self._draft(messages,system,P4_REQUESTS[marker][2])

        if marker in P4_REQUESTS:
            if marker in {"INTENT-01", "INTENT-02", "INTENT-03"} and step == 0:
                source, name = ("F-SALES.csv", "f_sales") if marker in {"INTENT-01", "INTENT-02"} else ("F-YOY.csv", "yoy_sales")
                return self._response(calls=[("load_data", {"source": source, "name": name})])
            if marker == "INTENT-01" and step == 1:
                return self._response(calls=[("describe_dataset", {"name": "f_sales"})])
            if marker == "INTENT-02" and step == 1:
                return self._response(calls=[("export_data", {"name":"f_sales","path":"output/current.csv","fmt":"csv"})])
            if marker == "INTENT-03" and step == 1:
                return self._response(calls=[("compare_periods", {"name": "yoy_sales", "date_col": "date", "metrics": "amount",
                    "period_a": "2025-09-01~2025-09-02", "period_b": "2026-09-01~2026-09-02"})])
            return self._draft(messages, system, P4_REQUESTS[marker][2])

        if marker == "B01-DESCRIBE":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "f_sales"})])
            if step == 1:
                return self._response(calls=[("describe_dataset", {"name": "f_sales"})])
            if step == 2:
                return self._response(calls=[("record_evidence_record", {"record_json": {
                    "claim": "当前导入订单的字段和范围已描述", "dataset": "f_sales",
                    "method": "describe_dataset", "tool_calls": ["describe_dataset"],
                    "result_summary": "以当前描述回执为准。",
                    "limitations": "没有验证总体代表性或行动效果。", "confidence": "medium",
                }})])
            return self._draft(messages, system, "当前只有 11 天记录，amount 合计 120；建议立即扩大投放。")

        if marker == "IC-B03-DESCRIBE":
            if step == 0:
                return self._response(calls=[("ask_user_question", {
                    "question": "净收益应采用哪种成本范围？",
                    "options": [
                        {"label": "仅代金券成本", "description": "只扣代金券直接成本。"},
                        {"label": "代金券及渠道成本", "description": "同时扣渠道成本。"},
                    ],
                    "confirmation_type": "scope_confirmation",
                    "blocking_reason": "成本范围会改变净收益口径。",
                })])
            if step == 1:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "ic_sales"})])
            if step == 2:
                return self._response(calls=[("describe_dataset", {"name": "ic_sales"})])
            if step == 3:
                return self._response(calls=[("record_evidence_record", {"record_json": {
                    "claim": "当前导入订单的字段和范围已描述", "dataset": "ic_sales",
                    "method": "describe_dataset", "tool_calls": ["describe_dataset"],
                    "result_summary": "以当前描述回执为准。",
                    "limitations": "成本金额与促销增量效果缺失。", "confidence": "medium",
                }})])
            return self._draft(messages, system, "已确认成本选择，所以 11 天净收益为 120，应立即扩大投放。")

        if marker == "B01-BUSINESS":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "f_sales"})])
            if step == 1:
                return self._response(calls=[("ask_user_question", {
                    "measurement_mapping": json.dumps({
                        "exact_span": "销售额", "dataset": "f_sales", "column": "amount",
                    }, ensure_ascii=False),
                })])
            if step == 2:
                return self._response(calls=[("transform_data", {
                    "name": "f_sales", "operation": "group_aggregate",
                    "group_by": ["channel"],
                    "aggregations": [{"column": "amount", "functions": ["sum", "count"]}],
                    "save_as": "f_sales_total",
                })])
            if step == 3:
                return self._response(calls=[("record_evidence_record", {"record_json": {
                    "claim": "当前渠道的 amount 原值与非空计数", "dataset": "f_sales_total",
                    "method": "group_aggregate", "tool_calls": ["transform_data"],
                    "result_summary": "以当前聚合回执为准。",
                    "limitations": "只覆盖当前十二条记录，业务单位需确认。",
                    "confidence": "medium",
                }})])
            return self._draft(messages, system, "请按用户对销售额的真实选择说明当前结果；未确认时保留 amount 原值。")

        if marker == "B01-EDGE":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES-EDGE.csv", "name": "edge_sales"})])
            if step == 1:
                return self._response(calls=[("transform_data", {
                    "name": "edge_sales", "operation": "group_aggregate",
                    "group_by": ["channel"],
                    "aggregations": [
                        {"column": "amount", "functions": ["sum", "count", "size"]},
                        {"column": "order_id", "functions": ["nunique"]},
                    ],
                    "save_as": "edge_summary",
                })])
            if step == 2:
                return self._response(calls=[("record_evidence_record", {"record_json": {
                    "claim": "当前分组聚合结果", "dataset": "edge_summary",
                    "method": "group_aggregate", "tool_calls": ["transform_data"],
                    "result_summary": "请以实际聚合回执及数据版本为准",
                    "limitations": "只描述当前六条原始记录，不推断总体。",
                    "confidence": "medium",
                }})])
            return self._draft(messages, system, "已完成三组聚合；请以当前回执核对各组结果。")

        if marker in {"B01-STALE", "B01-RECOMPUTE"}:
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES-EDGE.csv", "name": "edge_sales"})])
            if step == 1:
                return self._response(calls=[("transform_data", {
                    "name": "edge_sales", "operation": "group_aggregate",
                    "group_by": ["channel"],
                    "aggregations": [{"column": "amount", "functions": ["sum", "count"]}],
                })])
            if step == 2:
                return self._response(calls=[("reload_data", {"source": "F-SALES-EDGE-V2.csv", "name": "edge_sales"})])
            if marker == "B01-RECOMPUTE":
                if step == 3:
                    return self._response(calls=[("transform_data", {
                        "name": "edge_sales", "operation": "group_aggregate",
                        "group_by": ["channel"],
                        "aggregations": [{"column": "amount", "functions": ["sum", "count"]}],
                    })])
                if step == 4:
                    return self._response(calls=[("record_evidence_record", {"record_json": {
                        "claim": "当前 v2 三组聚合结果", "dataset": "edge_sales__grouped_2",
                        "method": "group_aggregate", "tool_calls": ["transform_data"],
                        "result_summary": "新版本按 channel 分组，以当前变换回执为准。",
                        "limitations": "仅覆盖当前六条记录，不能外推总体。",
                        "confidence": "medium",
                    }})])
                return self._draft(messages, system, "v2 聚合已重新执行；旧回执仅保留历史，新结果应来自当前版本。")
            return self._draft(messages, system, "源表已经更新到 v2；旧聚合值只属于 v1，当前结果需要重新计算。")

        if marker in {"B01-DESCRIBE-ACTION", "B01-DESCRIBE-ACTION-RISK"}:
            if step == 0:
                return self._response(calls=[
                    ("load_data", {"source": "F-SALES.csv", "name": "f_sales"}),
                    ("load_data", {"source": "F-ACTION.csv", "name": "action_sales"}),
                ])
            if step == 1:
                return self._response(calls=[
                    ("describe_dataset", {"name": "f_sales"}),
                    ("compare_periods", {
                        "name": "action_sales", "date_col": "date",
                        "metrics": "amount,campaign_cost,net_contribution,orders",
                        "period_a": "2026-09-07~2026-09-13",
                        "period_b": "2026-09-14~2026-09-20",
                    }),
                ])
            if step == 2:
                return self._response(calls=[
                    ("record_evidence_record", {"record_json": {
                        "claim": "当前导入订单的字段和范围已描述", "dataset": "f_sales",
                        "method": "describe_dataset", "tool_calls": ["describe_dataset"],
                        "result_summary": "以当前描述回执为准。",
                        "limitations": "没有验证总体代表性或行动效果。", "confidence": "medium",
                    }}),
                    ("record_evidence_record", {"record_json": {
                        "claim": "两段七日净贡献、成本与订单的描述性比较",
                        "dataset": "action_sales", "method": "compare_periods",
                        "tool_calls": ["compare_periods"],
                        "result_summary": "两段等长窗口的原回执为准。",
                        "limitations": "没有随机对照，不能将变化归因于投放。",
                        "confidence": "medium",
                    }}),
                ])

        if marker in {"B01-ACTION", "B01-DESCRIBE-ACTION", "B01-DESCRIBE-ACTION-RISK",
                      "B01-ACTION-MULTI", "B01-ACTION-MULTI-NEG",
                      "B01-ACTION-MULTI-RISK", "B01-ACTION-MULTI-STALE"}:
            if step == 0:
                if marker == "B01-ACTION-MULTI-STALE":
                    return self._response(calls=[
                        ("reload_data", {"source": "F-SALES-v2.csv", "name": "f_sales"}),
                        ("load_data", {"source": "F-ACTION.csv", "name": "action_sales"}),
                    ])
                return self._response(calls=[("load_data", {"source": "F-ACTION.csv", "name": "action_sales"})])
            if step == 1:
                return self._response(calls=[("compare_periods", {
                    "name": "action_sales", "date_col": "date",
                    "metrics": "amount,campaign_cost,net_contribution,orders",
                    "period_a": "2026-09-07~2026-09-13",
                    "period_b": "2026-09-14~2026-09-20",
                })])
            if step == 2:
                return self._response(calls=[("record_evidence_record", {"record_json": {
                    "claim": "两段七日净贡献、成本与订单的描述性比较",
                    "dataset": "action_sales", "method": "compare_periods",
                    "tool_calls": ["compare_periods"],
                    "result_summary": "两段等长窗口的原回执为准。",
                    "limitations": "没有随机对照，不能将变化归因于投放。",
                    "confidence": "medium",
                }})])
            action_text = (
                "本期成本每单高于基准期，因此下一窗口的停止条件已经触发，现在必须立即暂停增加预算。"
                if marker in {"B01-ACTION-MULTI-RISK", "B01-DESCRIBE-ACTION-RISK"} else
                "若下一同口径七日窗口的净贡献不低于基准期，且成本每单不高于本期，"
                "才考虑小规模受控试验；否则暂停增加预算并复核。"
            )
            return self._draft(messages, system, action_text,
                               invalid_ref=marker == "B01-ACTION-MULTI-NEG")

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
            return self._draft(messages, system, "已验证观察：当前 12 条订单金额合计为 120。行动建议：若下周同口径订单金额低于 120，先复核渠道投放；若连续两周低于 120，停止扩大投放并复核渠道成本。限制：这只是当前 12 条记录的描述，不能外推总体。")

        if marker == "B02-CONFIRM":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-RET7.csv", "name": "ret_a"})])
            if step == 1:
                return self._response(calls=[("ask_user_question", {
                    "measurement_mapping": json.dumps({
                        "exact_span": "留存序列", "dataset": "ret_a", "column": "retention",
                        "x_column": "day", "x_start": 1, "x_end": 7,
                    }, ensure_ascii=False),
                })])
            if step == 2:
                return self._response(calls=[("curve_fitting", {"name": "ret_a", "x_col": "day", "y_col": "retention"})])
            return self._draft(messages, system, "已完成当前留存观测及拟合；D30 尚无验证。")

        if marker == "B02-MULTI":
            if step == 0:
                return self._response(calls=[
                    ("load_data", {"source": "F-RET7.csv", "name": "ret_a"}),
                    ("load_data", {"source": "F-RET7.csv", "name": "ret_b"}),
                ])
            if step == 1:
                return self._response(calls=[
                    ("curve_fitting", {"name": "ret_a", "x_col": "day", "y_col": "retention"}),
                    ("curve_fitting", {"name": "ret_b", "x_col": "day", "y_col": "retention"}),
                ])
            return self._draft(messages, system, "两个来源的曲线均只描述当前观测，D30 没有验证。")

        if marker == "B02":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-RET7.csv", "name": "ret_a"})])
            if step == 1:
                return self._response(calls=[("curve_fitting", {"name": "ret_a", "x_col": "day", "y_col": "retention"})])
            return self._draft(messages, system, "已验证观察：D7 留存为 10%。当前不能预测 D30，建议继续收集至第 30 天后再验证。")

        if marker == "B02-NEG":
            if step == 0:
                return self._response(calls=[("curve_fitting", {"name": "ret_a", "x_col": "day", "y_col": "retention"})])
            # The first candidate must be stopped by the real publication guard.
            if step == 1:
                return self._draft(messages, system, "渠道 A 的 D30 留存预计为 5%。")
            return self._draft(messages, system, "当前只有 D1 至 D7 的观察，不能预测 D30；需补充至第 30 天的数据后再验证。")

        if marker == "B03-SYNTH":
            if step == 0:
                return self._response(calls=[
                    ("load_data", {"source": f"F-SRC{number}-FOUR.csv", "name": f"src_{number}"})
                    for number in (1, 2)
                ])
            if step == 1:
                return self._response(calls=[("synthesize_time_series", {
                    "datasets": "src_1,src_2", "date_col": "date",
                    "metrics": "src_1:amount,src_2:amount", "save_as": "aligned_pair",
                })])
            if step == 2:
                return self._response(calls=[("preview_data", {"name": "aligned_pair", "n": 2})])
            if step == 3:
                return self._response(calls=[("compare_periods", {
                    "name": "aligned_pair", "date_col": "date", "metrics": "src_1,src_2",
                    "period_a": "2026-09-01~2026-09-02",
                    "period_b": "2026-09-03~2026-09-04",
                })])
            return self._draft(messages, system, "两张来源已按日期并列对齐，各指标分开比较；不计算未经请求的合计。")

        if marker in {"B03", "CONTENT-B03", "B03-CHART", "B03-PREVIEW"}:
            if step == 0:
                calls: list[tuple[str, dict]] = []
                for number in range(1, 7):
                    name = f"src_{number}"
                    suffix = "-FOUR" if marker == "B03-PREVIEW" else ""
                    calls.append(("load_data", {"source": f"F-SRC{number}{suffix}.csv", "name": name}))
                return self._response(calls=calls)
            if marker == "B03-PREVIEW" and step == 1:
                return self._response(calls=[
                    ("preview_data", {"name": f"src_{number}", "n": 2})
                    for number in range(1, 7)
                ])
            if marker == "B03-PREVIEW" and step == 2:
                return self._response(calls=[
                    ("compare_periods", {
                        "name": f"src_{number}", "date_col": "date", "metrics": "amount",
                        "period_a": "2026-09-01~2026-09-02",
                        "period_b": "2026-09-03~2026-09-04",
                    })
                    for number in range(1, 7)
                ])
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
            if marker == "B03-CHART" and step == 2:
                return self._response(calls=[
                    ("create_chart", {
                        "chart_type": "bar", "data": f"src_{number}",
                        "title": f"src_{number} 两日 amount 原值",
                        "x_col": "date", "y_col": "amount", "purpose": "exploratory",
                        "scale_mode": "raw",
                    })
                    for number in range(1, 7)
                ])
            return self._draft(messages, system, "已完成六个来源的分组汇总。来源 1 至来源 6 均保留在本轮收据中；导出时应保留全部来源和每个来源的金额与记录数。")

        if marker in {"B07-PRESENTATION", "CONTENT-B07"}:
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "presentation_sales"})])
            if step == 1:
                return self._response(calls=[(
                    "create_chart",
                    {
                        "chart_type": "bar",
                        "data": "presentation_sales",
                        "title": "渠道金额对比",
                        "x_col": "date",
                        "y_col": "amount",
                        "purpose": "exploratory",
                    },
                )])
            if step == 2:
                return self._response(calls=[("run_python",{"code":"df=get_dataset('presentation_sales')\nresult={'amount_sum':float(df['amount'].sum()),'records':len(df),'average_amount':float(df['amount'].mean())}\nresult"})])
            return self._draft(messages, system, "## 当前数据概览\n\n"
                "| 指标 | 数值 | 口径 |\n"
                "|---|---:|---|\n"
                "| 订单金额 | 120 | 当前导入的 12 条订单 |\n"
                "| 订单数 | 12 | 当前导入记录数 |\n\n"
                "计算关系为：$$\\text{平均订单金额}=\\frac{120}{12}=10$$\n\n"
                "［［chart：渠道金额对比］］\n\n"
                "该结果只描述当前导入的 12 条记录，不能外推总体。")

        if marker == "IC-B01":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-RET7.csv", "name": "ic_retention"})])
            if step == 1:
                return self._response(calls=[("curve_fitting", {"name": "ic_retention", "x_col": "day", "y_col": "retention"})])
            return self._draft(messages, system, "已完成观测范围内的留存曲线拟合：D7 留存为 10%。"
                "结果只覆盖 D1 至 D7，不包含 D30 外推，也无需用户批准内部拟合方法。")

        if marker == "IC-B02":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "ic_sales"})])
            if step == 1:
                return self._response(calls=[(
                    "transform_data",
                    {
                        "name": "ic_sales",
                        "operation": "group_aggregate",
                        "group_by": ["channel"],
                        "aggregations": [{"column": "amount", "functions": ["sum", "count", "mean"]}],
                        "save_as": "ic_sales_summary",
                    },
                )])
            return self._draft(messages, system, "九项需求逐项结果：\n"
                "1. 最终收益：当前导入订单金额合计 120。\n"
                "2. 复购率：not_computed，当前夹具没有跨订单复购标识。\n"
                "3. 购买偏好：evidence_insufficient，只有单一渠道。\n"
                "4. 付费频次：当前 12 条记录。\n"
                "5. 付费 ARPU：evidence_insufficient，缺少独立用户分母。\n"
                "6. 人均付费：evidence_insufficient，缺少独立用户分母。\n"
                "7. 日均付费：当前 12 天合计 120，日均 10。\n"
                "8. 单次付费：当前 12 笔均值 10。\n"
                "9. 金额区间分布：当前 12 笔均为 10。\n"
                "连续付费提升没有对照，不能写成省钱卡造成的因果效果。")

        if marker in {"IC-B03", "IC-B03-DATA", "IC-B04-REUSE"}:
            if step == 0:
                if marker == "IC-B03-DATA":
                    from data_agent.agent.confirmation.runtime import metric_scope_formula_description

                    def scope_option(label: str, costs: list[str]) -> dict[str, str]:
                        formula = {
                            "schema_version": "metric_scope_formula.v1",
                            "dataset": "ic_promo",
                            "effect_column": "incremental_revenue",
                            "cost_columns": costs,
                        }
                        return {
                            "label": label,
                            "value": json.dumps(formula, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")),
                            "description": metric_scope_formula_description(formula),
                        }

                    return self._response(calls=[("ask_user_question", {
                        "question": "请确认本次账面净收益的列对应关系与成本范围：",
                        "options": [
                            scope_option("仅代金券成本", ["coupon_cost"]),
                            scope_option("代金券及渠道成本", ["coupon_cost", "channel_cost"]),
                        ],
                        "confirmation_type": "metric_scope",
                        "blocking_reason": "所选成本列改变本次账面净收益。",
                    })])
                return self._response(calls=[("ask_user_question", {
                    "question": "净收益应采用哪种成本范围？",
                    "options": [
                        {"label": "仅代金券成本", "description": "只扣除代金券直接成本。"},
                        {"label": "代金券及渠道成本", "description": "同时扣除渠道成本。"},
                    ],
                    "confirmation_type": "metric_scope",
                    "blocking_reason": "成本范围会改变净收益口径。",
                })])
            if marker == "IC-B03-DATA":
                if step == 1:
                    return self._response(calls=[("load_data", {
                        "source": "F-PROMO.csv", "name": "ic_promo",
                    })])
                if step == 2:
                    return self._response(calls=[("transform_data", {
                        "name": "ic_promo", "operation": "group_aggregate",
                        "group_by": ["channel"],
                        "aggregations": [
                            {"column": "order_amount", "functions": ["sum", "count"]},
                            {"column": "incremental_revenue", "functions": ["sum"]},
                            {"column": "coupon_cost", "functions": ["sum"]},
                            {"column": "channel_cost", "functions": ["sum"]},
                        ],
                        "save_as": "ic_promo_summary",
                    })])
                if step == 3:
                    return self._response(calls=[("record_evidence_record", {"record_json": {
                        "claim": "当前四条记录的原始收入、增量收入列和两项成本列已分别聚合",
                        "dataset": "ic_promo_summary", "method": "group_aggregate",
                        "tool_calls": ["transform_data"],
                        "result_summary": "各列原值以当前聚合回执为准；增量收入列本身不证明因果。",
                        "limitations": "成本范围由用户选择；不能从列名推断实验归因。",
                        "confidence": "medium",
                    }})])
                return self._draft(messages, system, "当前四条记录的订单金额、增量收入列和两项成本列已聚合；"
                    "业务成本范围已确认，净收益算式及其语义仍需当前来源与确认共同绑定。")
            if marker == "IC-B03":
                if step == 1:
                    return self._response(calls=[("load_data", {
                        "source": "F-SALES.csv", "name": "ic_sales",
                    })])
                if step == 2:
                    return self._response(calls=[("transform_data", {
                        "name": "ic_sales", "operation": "group_aggregate",
                        "group_by": ["channel"],
                        "aggregations": [{"column": "amount", "functions": ["sum", "count"]}],
                        "save_as": "ic_sales_total",
                    })])
                if step == 3:
                    return self._response(calls=[("record_evidence_record", {"record_json": {
                        "claim": "当前订单 amount 原值合计与非空计数",
                        "dataset": "ic_sales_total", "method": "group_aggregate",
                        "tool_calls": ["transform_data"],
                        "result_summary": "以当前聚合回执为准。",
                        "limitations": "成本金额与促销增量效果未提供，不能计算净收益。",
                        "confidence": "medium",
                    }})])
                return self._draft(messages, system, "当前订单 amount 总额和非空计数已计算；成本范围已确认，但成本金额及促销增量效果未提供，净收益未计算。")
            return self._draft(messages, system, "已复用当前业务范围内有效的成本口径回答；没有把它扩展成整个方法的永久许可。")

        if marker == "IC-B04-CHANGE":
            if step == 0:
                return self._response(calls=[("ask_user_question", {
                    "question": "比较窗口改为 7 天还是保留 30 天？",
                    "options": [
                        {"label": "7 天", "description": "按新的 7 天窗口计算。"},
                        {"label": "30 天", "description": "保留原 30 天窗口。"},
                    ],
                    "confirmation_type": "time_window",
                    "blocking_reason": "窗口变化会改变比较范围和结果。",
                })])
            return self._draft(messages, system, "已按新选择的窗口继续；旧成本范围回答没有替代这次窗口决定。")

        if marker == "IC-B05":
            if step == 0:
                return self._response(calls=[("ask_user_question", {
                    "question": "复购率分母应使用全部购卡用户还是到期用户？",
                    "options": [
                        {"label": "全部购卡用户", "description": "以全部购卡用户为分母。"},
                        {"label": "到期用户", "description": "只以已到期用户为分母。"},
                    ],
                    "confirmation_type": "metric_scope",
                    "blocking_reason": "分母会实质改变复购率。",
                })])
            return self._draft(messages, system, "真实分母问题已被跳过，因此没有把 skip 当成批准，也没有输出确定复购率；"
                "旧通用方法审批仅按 policy_retired 保留审计。")

        if marker == "IC-B06-METHOD":
            if step == 0:
                return self._response(calls=[("ask_user_question", {
                    "question": "是否使用留存方法继续？",
                    "options": [
                        {"label": "使用", "description": "批准内部方法。"},
                        {"label": "不使用", "description": "拒绝内部方法。"},
                    ],
                    "confirmation_type": "method_confirmation",
                    "blocking_reason": "模型声称内部方法需要批准。",
                })])
            return self._draft(messages, system, "内部方法许可问题已非阻塞处理，工具消息已闭合，任务继续。")

        if marker == "IC-B06-SEMANTIC":
            if step == 0:
                return self._response(calls=[("ask_user_question", {
                    "question": "应按自然周还是最近 7 天统计？",
                    "options": [
                        {"label": "自然周", "description": "按周一至周日。"},
                        {"label": "最近 7 天", "description": "按滚动七天。"},
                    ],
                    "confirmation_type": "time_window",
                    "blocking_reason": "时间口径会改变当前统计结果。",
                })])
            return self._draft(messages, system, "已按用户选择的真实时间口径恢复，SSE 终态保持唯一。")

        if marker == "B04-INFER":
            # Each frozen user leg has its own tool sequence. A rejected stale
            # terminal is redrafted in that leg; it cannot run the next request.
            if user == "【B04-INFER】更新版本后保留旧关系的失效边界。":
                if step == 0:
                    return self._response(calls=[("reload_data", {"source": "F-HYP-FLAT.csv", "name": "hyp"})])
                return self._draft(messages, system, "当前数据已更新为 v2；v1 的描述性关系只能作为旧版审计记录。")
            if user == "【B04-INFER】重新分析当前版本的 amount 竞争假设和描述性趋势。":
                if step == 0:
                    return self._response(calls=[("analyze_time_series", {"name": "hyp"})])
                if step == 1:
                    return self._response(calls=[("record_evidence_record", {"record_json": self._inferred_trend_evidence("v2")})])
                return self._draft(messages, system, "v2 当前 amount 为平坦描述性观察；旧版上升关系不能作为本版结论。")
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-HYP.csv", "name": "hyp"})])
            if step == 1:
                return self._response(calls=[("analyze_time_series", {"name": "hyp"})])
            if step == 2:
                return self._response(calls=[("record_evidence_record", {"record_json": self._inferred_trend_evidence("v1")})])
            return self._draft(messages, system, "当前 v1 的 amount 描述性趋势有同版回执；trend_slope 不是假设目标指标，不能提升该模型提案。")

        if marker == "B04":
            compare_up = {
                "name": "hyp", "date_col": "date", "metrics": "amount",
                "period_a": "2026-09-01~2026-09-01", "period_b": "2026-09-02~2026-09-02",
            }
            compare_flat = {
                "name": "hyp", "date_col": "date", "metrics": "amount",
                "period_a": "2026-09-02~2026-09-02", "period_b": "2026-09-03~2026-09-03",
            }
            turn = int(re.search(r"继续第(\d+)步", user).group(1)) if "继续第" in user else 1
            phases = {
                1: [("load_data", {"source":"F-HYP.csv","name":"hyp"}), ("compare_periods",compare_up),
                    ("record_evidence_record",{"record_json":{"claim":"amount changed between the compared periods in hyp.","dataset":"hyp","method":"compare_periods","tool_calls":["compare_periods"],"result_summary":"amount increased from 10 to 20.","limitations":"descriptive comparison only","confidence":"medium"}})],
                2: [("compare_periods",compare_up), ("record_evidence_record", "supports")],
                3: [("compare_periods",compare_flat), ("record_evidence_record", "refutes")],
                8: [("reload_data",{"source":"F-HYP-FLAT.csv","name":"hyp"})],
                9: [("compare_periods",compare_up)],
            }
            calls = phases.get(turn, [])
            if step < len(calls):
                tool, args = calls[step]
                if args == "supports": args = {"record_json":self._hypothesis_evidence("supports","increased",10)}
                if args == "refutes": args = {"record_json":self._hypothesis_evidence("refutes","flat",0)}
                return self._response(calls=[(tool,args)])
            return self._draft(messages, system, "当前竞争假设按宿主可核关系交付；无据因果解释保持未决，旧版本证据不能背书当前版本。")

        if marker == "B05-BUSINESS":
            return self._draft(messages, system, "面向业务：当前 12 条订单金额合计为 120。下周若低于 120，先检查渠道投放；该结论仅覆盖当前记录，不能外推总体。")
        if marker == "B05-PY":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "f_sales"})])
            if step == 1:
                return self._response(calls=[("run_python", {"code": (
                    "df = get_dataset('f_sales')\n"
                    "result = {'rows': int(df.shape[0]), "
                    "'amount_sum': float(df['amount'].sum()), "
                    "'date_min': str(df['date'].min()), "
                    "'date_max': str(df['date'].max())}\n"
                    "result"
                )})])
            return self._draft(messages, system, "当前订单记录数为 12，amount 原值合计 120；仅描述当前记录，单位未知。")
        if marker == "B05-PY-NOROW":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "f_sales"})])
            if step == 1:
                return self._response(calls=[("run_python", {"code": (
                    "df = get_dataset('f_sales')\n"
                    "result = {'order_count': int(df.shape[0]), "
                    "'amount_sum': float(df['amount'].sum()), "
                    "'date_min': str(df['date'].min().date()), "
                    "'date_max': str(df['date'].max().date()), "
                    "'inclusive_days': int((df['date'].max().date() - df['date'].min().date()).days) + 1}\n"
                    "result"
                )})])
            return self._draft(messages, system, "模型候选：12 条、120，9 月 1—12 日覆盖 11 天。")
        if marker == "B03-PIVOT":
            if step == 0:
                return self._response(calls=[("load_data", {"source": "F-SALES.csv", "name": "pivot_sales"})])
            if step == 1:
                return self._response(calls=[("transform_data", {
                    "name": "pivot_sales", "operation": "pivot",
                    "pivot_index": "channel", "pivot_columns": "date",
                    "pivot_values": "amount", "save_as": "pivot_dates",
                })])
            return self._draft(messages, system, "日期 pivot 已完成并持久化。")
        if marker == "B05-ANALYST":
            return self._draft(messages, system, "面向分析师：f_sales_total 经 group_aggregate 得到 amount_sum=120、amount_count=12；范围为当前 12 条订单，不能外推总体。")
        if marker == "B05-MANAGER":
            return self._draft(messages, system, "面向管理层：当前样本的订单金额为 120（12 条）。下周低于 120 时复核投放；该结果仅适用于当前样本，不能外推总体。")
        if marker == "B05-PLAIN":
            return self._draft(messages, system, "大白话：这 12 笔订单一共是 120。下周低于 120 就先查投放；这只说明眼前这批记录，不能代表全部订单。")
        if marker == "B05-TECH":
            return self._draft(messages, system, "分析表达：f_sales_total 经 group_aggregate 得到 amount_sum=120、amount_count=12；该描述性结果仅覆盖当前 12 条订单，不能外推总体。")
        if marker == "B06-TOOL":
            if step == 0:
                return self._response(calls=[("transform_data", {
                    "name": "missing_dataset", "operation": "group_aggregate",
                    "group_by": ["channel"], "aggregations": [{"column": "amount", "functions": ["sum"]}],
                    "save_as": "never_created",
                })])
            return self._draft(messages, system, "工具未能找到所需数据集，未发布计算结论；请先加载可用数据后再分析。")
        if marker == "B06-MISSING":
            if step == 0:
                return self._response(calls=[("list_data", {})])
            return self._draft(messages, system, "模型候选：请上传 missing_orders，或者改为分析现有数据集。")
        if marker == "B06-SAVE":
            return self._draft(messages, system, "这条回答必须在保存失败后被标记为未完成，不能作为已完成分析发布。")
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
            return self._draft(messages, system, "已触及工具调用预算，停止继续调用并保留当前可验证状态。")
        return self._draft(messages, system, "演练脚本未识别当前场景标记。")

    def stream_chat_structured(self, messages, tools=None, system=None):
        from data_agent.llm.client import StreamComplete

        # A Web confirmation resume appends the selected answer as the latest
        # user message.  The originating scenario remains the closest earlier
        # explicit marker and must retain control of the actual resumed loop.
        for message in reversed(messages):
            if message.get("role") == "user":
                key = self._s2_key(str(message.get("content") or ""))
                if key is not None:
                    yield StreamComplete(response=self._s2_next(key,messages,system))
                    return
        marker = "UNKNOWN"
        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            # Consultation fixtures share this existing scripted transport.
            content = str(message.get("content") or "").partition("\n分析文件: ")[0]
            case = next((case for case, (text, _, _) in P4_REQUESTS.items() if content == f"【{case}】{text}"), None)
            if case:
                marker = case
                break
            found = re.search(
                r"【(B(?:01-ACTION-MULTI-STALE|01-ACTION-MULTI-RISK|01-ACTION-MULTI-NEG|01-ACTION-MULTI|01-ACTION|01-BUSINESS|01-DESCRIBE-ACTION-RISK|01-DESCRIBE-ACTION|01-DESCRIBE|01-EDGE|01-STALE|01-RECOMPUTE|01|02-CONFIRM|02-MULTI|02-NEG|02|03-PIVOT|03-CHART|03-PREVIEW|03-SYNTH|03|04-INFER|04|05-PY-NOROW|05-PY|05-BUSINESS|05-ANALYST|05-MANAGER|05-PLAIN|05-TECH|06-MISSING|06-TOOL|06-SAVE|06-BUDGET|07-PRESENTATION)|CONTENT-B0[37]|IC-B(?:01|02|03-DESCRIBE|03-DATA|03|04-REUSE|04-CHANGE|05|06-METHOD|06-SEMANTIC))】",
                str(message.get("content") or ""),
            )
            if found:
                marker = found.group(1)
                break
        yield StreamComplete(response=self._next(marker, messages, system))


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
    _seed_legacy_confirmation_fixture()
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
    from data_agent.agent.loop import AgentLoop

    # Deterministically exercise the normal Web/SSE persistence-failure
    # branch. The failure is restricted to an explicit B06 test marker; the
    # browser must receive the production fail-closed ``unknown`` terminal,
    # never a completed turn or a durable final answer.
    original_auto_save = AgentLoop._auto_save

    def p7_auto_save_with_failure(loop):
        if any(
            "【B06-SAVE】" in str(message.get("content") or "")
            for message in getattr(loop, "messages", [])
            if isinstance(message, dict) and message.get("role") == "user"
        ):
            trace.append("injected_save_failure", session_id=loop.session_id)
            raise OSError("P7 injected session save failure")
        return original_auto_save(loop)

    AgentLoop._auto_save = p7_auto_save_with_failure

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
