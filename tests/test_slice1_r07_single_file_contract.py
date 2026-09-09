"""Slice 1 R07: deterministic oracle and evidence-chart identity for D03."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.execution_control import TurnExecutionState
from data_agent.agent.trust_workflow_runtime import maybe_verify_turn_claims
from data_agent.agent.workbench_view import build_workbench_view
from data_agent.config import get_config
from data_agent.session.workspace import Workspace
from data_agent.tools.analysis_flow import record_evidence_record
from data_agent.tools.visualization import create_chart
from tests.support.real_data_manifest import reference_data_path


ROOT = Path(__file__).resolve().parents[1]
ORACLE_PATH = ROOT / "tests" / "real_data" / "slice1_r07_oracle.json"


def _oracle() -> dict:
    return json.loads(ORACLE_PATH.read_text(encoding="utf-8"))


def _daily_orders_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    source = pd.read_excel(reference_data_path("savings_card_orders"))
    source["支付时间"] = pd.to_datetime(source["支付时间"])
    source["date"] = source["支付时间"].dt.normalize()
    calendar = pd.date_range(source["date"].min(), source["date"].max(), freq="D")
    daily = (
        source.groupby("date")["售价"]
        .agg(orders="size", revenue="sum")
        .reindex(calendar, fill_value=0)
        .rename_axis("date")
        .reset_index()
    )
    return source, daily


def test_r07_oracle_is_recomputable_from_the_canonical_d03_file():
    oracle = _oracle()
    expected = oracle["expected"]
    source, daily = _daily_orders_frame()

    assert oracle["schema_version"] == "slice1_r07_single_file_oracle.v1"
    assert len(source) == expected["row_count"]
    assert source["user_id"].nunique() == expected["unique_users"]
    assert int(source["售价"].sum()) == expected["total_revenue"]
    assert str(daily["date"].min().date()) == expected["date_start"]
    assert str(daily["date"].max().date()) == expected["date_end"]
    assert len(daily) == expected["calendar_days"]
    assert int((daily["orders"] > 0).sum()) == expected["active_days"]
    assert [str(value.date()) for value in daily.loc[daily["orders"] == 0, "date"]] == expected["zero_order_days"]
    assert int(daily.iloc[:15]["revenue"].sum()) == expected["first_15_days_revenue"]
    assert int(daily.iloc[15:]["revenue"].sum()) == expected["last_15_days_revenue"]

    peak = daily.loc[daily["revenue"].idxmax()]
    assert str(peak["date"].date()) == expected["peak_day"]
    assert int(peak["revenue"]) == expected["peak_day_revenue"]
    assert int(peak["orders"]) == expected["peak_day_orders"]
    assert source.groupby("商品名称")["售价"].sum().astype(int).to_dict() == expected["product_revenue"]


def test_r07_evidence_chart_keeps_dataset_and_parent_identity(tmp_path):
    source, daily = _daily_orders_frame()
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    source_path = reference_data_path("savings_card_orders")
    state = AnalysisSessionState(session_id="slice1_r07")
    state.add_evidence_record({
        "id": "ev_r07_daily_revenue",
        "claim": "Daily revenue is aggregated from payment-time orders with zero-order days included.",
        "dataset": "d03_daily_revenue",
        "method": "group by payment date; sum price; complete daily calendar",
    })
    context = AgentContext(session_id="slice1_r07", workspace=Workspace(), analysis_state=state)

    try:
        with use_agent_context(context):
            context.workspace.add("d03_orders", source)
            context.workspace.set_metadata("d03_orders", "_source_path", str(source_path))
            context.workspace.set_metadata(
                "d03_orders", "source_fingerprint", "sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3",
            )
            context.workspace.derive(
                "d03_orders",
                "d03_daily_revenue",
                daily,
                expression="group_by=支付时间:day; aggregates=orders:count,revenue:sum; calendar=complete",
            )
            identity = context.workspace.get_data_identity("d03_daily_revenue")
            state.add_tool_receipt({"id": "r07_chart", "result_sha256": "sha256:fixture",
                                    "data_identities": {"d03_daily_revenue": identity}})
            state.evidence_records[0]["result_bindings"] = [{"receipt_id": "r07_chart", "result_sha256": "sha256:fixture",
                                                            "data_identities": {"d03_daily_revenue": identity}}]
            result = create_chart(
                chart_type="line",
                data="d03_daily_revenue",
                title="省钱卡日收入趋势（支付时间）",
                x_col="date",
                y_col="revenue",
                purpose="evidence",
                evidence_ids="ev_r07_daily_revenue",
            )

        assert result.startswith("Chart saved: sessions/slice1_r07/charts/")
        metadata_paths = list((tmp_path / "sessions" / "slice1_r07" / "charts").glob("*.json"))
        assert len(metadata_paths) == 1
        metadata = json.loads(metadata_paths[0].read_text(encoding="utf-8"))
        assert metadata["purpose"] == "evidence"
        assert metadata["evidence_ids"] == ["ev_r07_daily_revenue"]
        assert {key: metadata["data_identity"][key] for key in (
            "dataset", "source_dataset", "derived_from", "source_path", "source_fingerprint",
        )} == {
            "dataset": "d03_daily_revenue",
            "source_dataset": "d03_orders",
            "derived_from": "d03_orders",
            "source_path": str(source_path),
            "source_fingerprint": "sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3",
        }
        assert metadata["data_identity"]["version_id"] == context.workspace.get_data_identity("d03_daily_revenue")["version_id"]
        assert metadata["data_identity"]["parent_version_ids"] == [context.workspace.get_data_identity("d03_orders")["version_id"]]
        assert metadata["plotted_row_count"] == 30
    finally:
        cfg.sessions_dir = old_sessions


def test_r07_evidence_chart_rejects_unknown_evidence_id(tmp_path):
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    context = AgentContext(
        session_id="slice1_r07_unknown_evidence",
        workspace=Workspace(),
        analysis_state=AnalysisSessionState(session_id="slice1_r07_unknown_evidence"),
    )

    try:
        with use_agent_context(context):
            context.workspace.add("d03_daily_revenue", pd.DataFrame({
                "date": pd.date_range("2026-04-07", periods=2, freq="D"),
                "revenue": [100, 200],
            }))
            result = json.loads(create_chart(
                chart_type="line",
                data="d03_daily_revenue",
                title="Unbound evidence chart",
                x_col="date",
                y_col="revenue",
                purpose="evidence",
                evidence_ids="ev_not_created",
            ))

        assert result["error_type"] == "chart_validation"
        assert "do not resolve" in result["error"]
    finally:
        cfg.sessions_dir = old_sessions


def test_r07_evidence_chart_and_confirmed_conclusion_share_one_verified_record(tmp_path):
    """The D03 chart may be called evidence only after the record is verified."""
    source, daily = _daily_orders_frame()
    cfg = get_config()
    old_sessions = cfg.sessions_dir
    cfg.sessions_dir = tmp_path / "sessions"
    state = AnalysisSessionState(session_id="slice1_r07_verified")
    context = AgentContext(
        session_id="slice1_r07_verified",
        workspace=Workspace(),
        analysis_state=state,
        turn_state=TurnExecutionState(),
    )

    try:
        with use_agent_context(context):
            context.workspace.add("d03_orders", source)
            context.workspace.derive(
                "d03_orders",
                "d03_daily_revenue",
                daily,
                expression="group_by=支付时间:day; aggregates=orders:count,revenue:sum; calendar=complete",
            )
            receipt = state.add_tool_receipt({
                "id": "tr_r07_daily_aggregation",
                "tool_name": "derive_daily_revenue",
                "tool_call_id": "r07_daily_aggregation",
                "arguments": {"dataset": "d03_orders"},
                "dataset_refs": ["d03_orders", "d03_daily_revenue"],
                "result_sha256": "sha256:r07-oracle-daily-aggregation",
                "data_identities": {name: context.workspace.get_data_identity(name) for name in ["d03_orders", "d03_daily_revenue"]},
                "result_preview": "30 calendar days; zero-order days retained",
            })
            context.turn_state.tool_receipt_ids.append(receipt["id"])
            evidence = json.loads(record_evidence_record(json.dumps({
                "id": "ev_r07_daily_revenue_verified",
                "claim": "按支付时间汇总的 30 个自然日中，后 15 天收入低于前 15 天。",
                "dataset": "d03_daily_revenue",
                "method": "descriptive daily aggregation",
                "tool_calls": ["derive_daily_revenue"],
                "result_summary": "前 15 天收入 1818，后 15 天收入 684；4 个自然日零订单。",
                "limitations": ["描述性结果不能解释收入变化原因", "观察窗口仅 30 天、71 笔订单"],
                "confidence": "medium",
                "sample_size": 71,
                "time_scope": "2026-04-07 to 2026-05-06; complete daily calendar",
                "calculation_method": "sum price by payment date and reindex every calendar day",
                "method_detail": "Revenue is price sum; zero-order days are retained as zero.",
            }, ensure_ascii=False)))
            assert evidence["evidence_id"] == "ev_r07_daily_revenue_verified"
            assert state.evidence_records[0]["tool_receipt_ids"] == ["tr_r07_daily_aggregation"]

            chart_result = create_chart(
                chart_type="line",
                data="d03_daily_revenue",
                title="D03 verified daily revenue trend",
                x_col="date",
                y_col="revenue",
                purpose="evidence",
                evidence_ids="ev_r07_daily_revenue_verified",
            )
            verification = maybe_verify_turn_claims("分析收入趋势", state)

        assert chart_result.startswith("Chart saved: sessions/slice1_r07_verified/charts/")
        assert verification is not None
        assert verification["overall_status"] == "pass"
        view = build_workbench_view(state)
        assert [item["claim"] for item in view["verified_conclusions"]] == [
            "按支付时间汇总的 30 个自然日中，后 15 天收入低于前 15 天。"
        ]
        assert "limitations" not in view["verified_conclusions"][0]
    finally:
        cfg.sessions_dir = old_sessions
