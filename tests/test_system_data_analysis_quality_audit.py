"""System audit tests for real-data analysis quality and knowledge memory flow."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import data_agent.config as config_module
from data_agent.agent.context import AgentContext, reset_current_context, set_current_context
from data_agent.config import AgentConfig
from data_agent.session.workspace import Workspace, workspace


TEST_DOC_DIR = Path(__file__).resolve().parents[1] / "reference" / "test_doc"


@pytest.fixture
def audit_env(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    ctx = AgentContext(session_id="system_audit", workspace=Workspace(), project_name="system-audit")
    token = set_current_context(ctx)
    try:
        yield cfg, ctx
    finally:
        reset_current_context(token)


def _skip_if_missing(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path} not found")


def _load_json_tool_result(raw: str) -> dict:
    assert not raw.startswith("Error:"), raw
    return json.loads(raw)


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_game_purchase_analysis_outputs_reproducible_metric_quality(audit_env):
    """Real game revenue analysis should expose reproducible metric relationships."""
    data_file = TEST_DOC_DIR / "游戏A内购数据.xlsx"
    _skip_if_missing(data_file)

    from data_agent.tools.data_io import load_data
    from data_agent.tools.data_understand import describe_dataset
    from data_agent.tools.eda import analyze_time_series, correlation_analysis

    load_result = load_data(str(data_file.resolve()), name="game_purchase")
    assert "Error" not in load_result

    df = workspace.get("game_purchase")
    assert df is not None
    required = {"日期", "活跃用户", "新增用户", "付费人数", "内购收入", "内购arpu", "内购arppu"}
    assert required <= set(df.columns)

    valid = df[(df["活跃用户"] > 0) & df["内购收入"].notna() & df["内购arpu"].notna()].copy()
    recomputed_arpu = valid["内购收入"] / valid["活跃用户"]
    max_arpu_delta = (recomputed_arpu - valid["内购arpu"]).abs().max()
    assert max_arpu_delta < 0.002

    described = _load_json_tool_result(describe_dataset("game_purchase"))
    assert described["shape"]["rows"] >= 200
    assert any(field["name"] == "内购收入" for field in described["fields"])

    trend = _load_json_tool_result(analyze_time_series("game_purchase", date_col="日期", value_col="内购收入"))
    assert trend["data_points"] >= 200
    assert {"direction", "slope", "r_squared", "method", "inference_status"} <= set(trend["trend"])
    assert "p_value" not in trend["trend"]
    assert "significant" not in trend["trend"]
    assert trend["suggested_next"]

    corr = _load_json_tool_result(
        correlation_analysis(
            "game_purchase",
            columns="活跃用户,新增用户,付费人数,内购收入,内购arpu,内购arppu",
        )
    )
    assert {"活跃用户", "新增用户", "付费人数", "内购收入"} <= set(corr["columns_analyzed"])
    assert "high_correlations" in corr


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_retention_analysis_records_quality_limits_for_descriptive_claims(audit_env):
    """Retention findings should be traceable and avoid unqualified high confidence."""
    data_file = TEST_DOC_DIR / "游戏B留存.xlsx"
    _skip_if_missing(data_file)

    from data_agent.tools.data_io import load_data
    from data_agent.tools.analysis_flow import record_evidence_record

    load_result = load_data(str(data_file.resolve()), name="game_retention")
    assert "Error" not in load_result

    df = workspace.get("game_retention")
    assert df is not None
    assert {"日新增", "1天后", "7天后"} <= set(df.columns)

    weighted_day1 = float((df["日新增"] * df["1天后"]).sum() / df["日新增"].sum())
    weighted_day7 = float((df["日新增"] * df["7天后"]).sum() / df["日新增"].sum())
    simple_day1 = float(df["1天后"].mean())

    assert 0 < weighted_day7 < weighted_day1 < 1
    assert abs(weighted_day1 - simple_day1) > 0.001

    payload = {
        "claim": "游戏B 1日留存显著高于7日留存",
        "dataset": "game_retention",
        "method": "descriptive retention analysis",
        "tool_calls": ["load_data"],
        "result_summary": f"weighted D1={weighted_day1:.2%}, weighted D7={weighted_day7:.2%}",
        "limitations": [],
        "confidence": "high",
        "metrics": ["日新增", "1天后", "7天后"],
        "sample_size": str(len(df)),
        "time_scope": "63 days",
        "calculation_method": "weighted retention by 日新增",
        "significance": "unknown",
    }
    evidence = _load_json_tool_result(record_evidence_record(json.dumps(payload, ensure_ascii=False)))

    assert evidence["confidence_auto_downgraded"] is True
    assert evidence["original_confidence"] == "high"
    assert evidence["calibration_warnings"]
    assert "统计" in " ".join(evidence.get("auto_generated_limitations", []))


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_savings_card_order_flow_analysis_has_joinable_user_level_evidence(audit_env):
    """Savings-card analysis should support user-level order/flow joins and repeat metrics."""
    order_file = TEST_DOC_DIR / "省钱卡订单.xlsx"
    flow_file = TEST_DOC_DIR / "省钱卡0201到0510购卡用户付费数据.xlsx"
    _skip_if_missing(order_file)
    _skip_if_missing(flow_file)

    from data_agent.tools.data_io import load_data
    from data_agent.tools.data_understand import assess_readiness

    assert "Error" not in load_data(str(order_file.resolve()), name="card_orders")
    assert "Error" not in load_data(str(flow_file.resolve()), name="recent_flow")

    orders = workspace.get("card_orders")
    flow = workspace.get("recent_flow")
    assert orders is not None and flow is not None
    assert {"user_id", "商品名称", "售价", "支付时间", "创建时间"} <= set(orders.columns)
    assert {"user_id", "下单金额", "实收金额", "支付时间", "创角时间"} <= set(flow.columns)

    card_users = set(orders["user_id"].astype(str))
    flow_users = set(flow["user_id"].astype(str))
    matched_users = card_users & flow_users
    assert len(matched_users) / len(card_users) >= 0.9

    user_order_counts = orders.groupby("user_id").size()
    repeat_rate = float((user_order_counts >= 2).sum() / user_order_counts.size)
    assert 0 <= repeat_rate <= 1

    total_paid = float(orders["售价"].sum())
    assert total_paid > 0

    readiness = _load_json_tool_result(assess_readiness("card_orders", intent="分析省钱卡订单收入和复购"))
    assert readiness["dataset"] == "card_orders"
    assert readiness["rows"] == len(orders)
    assert readiness["cols"] == len(orders.columns)
    assert readiness["overall"] in {"ready", "ready_with_warnings", "blocked"}
    assert readiness["findings"] is not None
    assert readiness["recommendations"]


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_memory_and_retrieval_do_not_pollute_analysis_context_from_ordinary_real_data_session(audit_env):
    """Ordinary analysis sessions should index evidence but not create memory noise."""
    cfg, _ctx = audit_env

    from data_agent.knowledge.evidence import EvidenceStore
    from data_agent.knowledge.memory import MemoryStore
    from data_agent.knowledge.retrieval import KnowledgeRetrievalService
    from data_agent.session.history import save_session

    save_session(
        [
            {
                "role": "user",
                "content": "请分析游戏A内购数据.xlsx，重点看付费人数、内购收入、ARPU 和 ARPPU 的趋势。",
            },
            {
                "role": "assistant",
                "content": "已读取字段：日期、活跃用户、付费人数、内购收入、内购arpu、内购arppu。",
            },
        ],
        "ordinary_real_data_analysis",
        extra_meta={"project_name": "game"},
    )

    evidence = EvidenceStore(cfg.knowledge_dir, sessions_dir=cfg.sessions_resolved)
    indexed = evidence.search("内购收入 ARPU ARPPU", project_id="game", limit=5)
    assert indexed

    memories = MemoryStore(cfg.knowledge_dir).list(status="candidate")
    assert memories == []

    service = KnowledgeRetrievalService(root=cfg.knowledge_dir, sessions_dir=cfg.sessions_resolved)
    without_budget = service.retrieve(
        "游戏A 内购收入 ARPU ARPPU",
        project_id="game",
        include_evidence=True,
        max_total_retrieval_chars=1200,
    )
    with_budget = service.retrieve(
        "游戏A 内购收入 ARPU ARPPU",
        project_id="game",
        include_evidence=True,
        max_evidence_chars=800,
        max_total_retrieval_chars=1200,
    )

    assert without_budget.evidence_items == []
    assert with_budget.evidence_items
    assert with_budget.metadata["total_retrieval_chars"] <= 1200
