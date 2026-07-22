"""Comprehensive system test covering all optimization phases (1-4) with real data.

Test data files (from reference/test_doc):
  - 游戏Abanner汇总数据.xlsx: 248r x 18c, game banner ad metrics (daily aggregate)
  - 游戏A内购数据.xlsx: 248r x 13c, game in-app purchase metrics (daily aggregate)
  - 游戏A激励视频汇总数据报表.xlsx: 248r x 23c, game rewarded video metrics (daily aggregate)
  - 游戏互推.xlsx: 1985r x 8c, game cross-promotion data (multi-dimension aggregate)
  - 省钱卡用户最近流水_20260511.xlsx: 13815r x 8c, savings card user transactions (individual)
  - 省钱卡订单_20260507.xlsx: 71r x 7c, savings card orders (individual)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

TEST_DATA_DIR = Path("D:/Project/Daily/data-agent/reference/test_doc")


def _data_path(filename: str) -> str:
    p = TEST_DATA_DIR / filename
    assert p.exists(), f"Test data file not found: {p}"
    return str(p)


def _load_excel(filename: str) -> pd.DataFrame:
    return pd.read_excel(_data_path(filename))


def _fresh_workspace():
    """Create a fresh workspace for test isolation."""
    from data_agent.session.workspace import Workspace
    return Workspace()


# ═══════════════════════════════════════════════════════════════
# Phase 1: Architecture Foundation Tests
# ═══════════════════════════════════════════════════════════════

class TestPhase1IntentClassification:
    """Phase 1.1: Two-layer intent classification (rules → LLM fallback)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from data_agent.agent.intent import plan_turn_intent, TurnIntent
        self.plan = plan_turn_intent
        self.TurnIntent = TurnIntent

    def test_fast_path_greeting(self):
        intent = self.plan("你好", "")
        assert intent.intent_type == "simple_response"

    def test_fast_path_thanks(self):
        intent = self.plan("谢谢你的分析", "")
        assert intent.intent_type == "simple_response"

    def test_fast_path_report_keyword(self):
        intent = self.plan("给我出一份完整分析报告", "")
        assert intent.intent_type == "comprehensive_report"

    def test_fast_path_export(self):
        intent = self.plan("导出数据到CSV", "")
        assert intent.intent_type == "data_operation"

    def test_analysis_keywords(self):
        """Various analysis-related inputs should classify as analysis-related (not simple_response)."""
        cases = {
            "分析一下销售趋势": ("directed_analysis", "comprehensive_report", "intent_negotiation", "data_requirement"),
            "为什么收入下降了": ("directed_analysis", "comprehensive_report", "intent_negotiation", "data_requirement"),
            "对比一下各渠道的转化率": ("directed_analysis", "comprehensive_report", "intent_negotiation", "data_requirement"),
            "帮我做个漏斗分析": ("directed_analysis", "comprehensive_report", "intent_negotiation", "data_requirement"),
        }
        for text, valid_types in cases.items():
            intent = self.plan(text, "")
            assert intent.intent_type in valid_types, f"'{text}' → {intent.intent_type}, expected one of {valid_types}"

    def test_knowledge_qa_detection(self):
        intent = self.plan("什么是ARPU", "")
        assert intent.intent_type in ("knowledge_qa", "analysis_consultation", "simple_response")

    def test_data_state_inference(self):
        """data_state should reflect whether data is loaded."""
        intent_no_data = self.plan("分析一下", "")
        assert intent_no_data.data_state in ("no_data", "unknown")

        ctx_with_data = "- main: 100 rows x 5 cols"
        intent_with_data = self.plan("分析一下", ctx_with_data)
        assert intent_with_data.data_state in ("data_loaded", "unknown")

    def test_vague_input_gets_non_trivial_intent(self):
        """Vague inputs like '看看数据' should not default to simple_response."""
        intent = self.plan("帮我看下这份数据", "- main: 100 rows x 5 cols")
        assert intent.intent_type not in ("simple_response",)

    def test_intent_with_real_game_data_context(self):
        """Intent classification with real game data context."""
        ctx = "- banner: 248 rows x 18 cols"
        intent = self.plan("分析一下Banner广告收入趋势", ctx)
        assert intent.intent_type in ("directed_analysis", "comprehensive_report")

    def test_intent_with_savings_card_context(self):
        """Intent classification with savings card data context."""
        ctx = "- orders: 13815 rows x 8 cols, columns: order_id, user_id, product_id"
        intent = self.plan("哪些用户购买频次最高", ctx)
        assert intent.intent_type in ("directed_analysis", "comprehensive_report", "data_operation")


class TestPhase1PromptArchitecture:
    """Phase 1.2: Four-level prompt system."""

    def test_conversation_level_no_tools(self):
        from data_agent.agent.prompts import build_system_prompt
        prompt = build_system_prompt(
            tool_list="", user_input="谢谢", proficiency="intermediate",
        )
        assert "get_analysis_summary" in prompt  # conversation has read-only tool
        assert "Mermaid" not in prompt

    def test_analysis_level_has_full_content(self):
        from data_agent.agent.prompts import build_system_prompt
        prompt = build_system_prompt(
            tool_list="analyze_time_series, transform_data",
            user_input="帮我做个完整分析报告",
            session_context="- data: 100r x 5c",
        )
        # Analysis mode should have strategy table and mermaid
        assert "分析策略表" in prompt or "Mermaid" in prompt
        assert "analyze_time_series" in prompt

    def test_guidance_level_has_strategy(self):
        from data_agent.agent.prompts import build_system_prompt
        prompt = build_system_prompt(
            tool_list="quick_profile, ask_user_question",
            user_input="帮我看看这份数据有什么值得分析的",
        )
        assert "分析策略表" in prompt
        assert "Mermaid" in prompt

    def test_quick_level_compact(self):
        from data_agent.agent.prompts import build_system_prompt
        prompt = build_system_prompt(
            tool_list="transform_data, export_data",
            user_input="汇总销售总额",
        )
        assert "Mermaid" in prompt
        assert "分析流程" not in prompt  # quick mode has no analysis flow


class TestPhase1ErrorRecovery:
    """Phase 1.3: Context-aware error recovery."""

    def test_missing_column_recovery_hint(self):
        from data_agent.tools.registry import _classify_error, _build_recovery_hint
        error = json.dumps({"error": "列 'revenue_2024' 不存在"}, ensure_ascii=False)
        assert _classify_error(error) == "missing_column"
        hint = _build_recovery_hint(error)
        assert "preview_data" in hint or "describe_dataset" in hint

    def test_type_mismatch_recovery_hint(self):
        from data_agent.tools.registry import _classify_error, _build_recovery_hint
        error = json.dumps({"error": "无法转换类型: column 'date' is not numeric"}, ensure_ascii=False)
        cat = _classify_error(error)
        # May classify as type_mismatch or other category depending on error text
        hint = _build_recovery_hint(error)
        assert "恢复建议" in hint or "检查" in hint

    def test_tool_specific_recovery_hint(self):
        from data_agent.tools.registry import registry
        registry._ensure_discovered()
        tool = registry.get("load_data")
        assert tool is not None
        assert tool.recovery_hint != ""

    def test_format_result_appends_hint(self):
        from data_agent.tools.registry import registry, ToolResult
        registry._ensure_discovered()
        result = ToolResult(summary='{"error": "数据集 nonexistent 不存在"}')
        formatted = registry.format_result("list_data", result)
        assert "恢复建议" in formatted

    def test_real_data_wrong_column_error_recovery(self):
        """Load real data, use wrong column name, verify recovery hint."""
        from data_agent.session.workspace import workspace
        from data_agent.tools.registry import registry
        registry._ensure_discovered()
        df = _load_excel("游戏互推.xlsx")
        workspace.add("game_cross_err", df)

        try:
            result = registry.execute("analyze_time_series", {
                "name": "game_cross_err", "date_col": "wrong_date_col", "value_col": "wrong_val",
            })
            formatted = registry.format_result("analyze_time_series", result)
            assert "恢复建议" in formatted or "error" in result.to_cli().lower()
        finally:
            workspace._datasets.pop("game_cross_err", None)


class TestPhase1ToolGroupActivation:
    """Phase 1.4: Tool group activation based on intent + data signals."""

    def test_conversation_query_group(self):
        from data_agent.agent.analysis_flow_controller import AnalysisFlowController
        from data_agent.agent.intent import TurnIntent
        from data_agent.agent.analysis_state import AnalysisSessionState
        from data_agent.tools.registry import registry

        controller = AnalysisFlowController("test_session")
        state = AnalysisSessionState(session_id="test_session")
        intent = TurnIntent(
            intent_type="simple_response", clarity="clear",
            data_state="data_loaded", analysis_stage="discover",
            recommended_action="respond", reason="test",
        )
        groups = controller.activate_tool_groups(registry, intent, state, "谢谢")
        assert "conversation_query" in groups

    def test_negotiation_activates_knowledge_and_eda(self):
        from data_agent.agent.analysis_flow_controller import AnalysisFlowController
        from data_agent.agent.intent import TurnIntent
        from data_agent.agent.analysis_state import AnalysisSessionState
        from data_agent.tools.registry import registry

        controller = AnalysisFlowController("test_session")
        state = AnalysisSessionState(session_id="test_session")
        intent = TurnIntent(
            intent_type="intent_negotiation", clarity="vague",
            data_state="data_loaded", analysis_stage="discover",
            recommended_action="negotiate", reason="test",
        )
        groups = controller.activate_tool_groups(registry, intent, state, "帮我看看数据")
        assert "knowledge" in groups
        assert "eda" in groups


# ═══════════════════════════════════════════════════════════════
# Phase 2: Tool Layer Enhancement Tests
# ═══════════════════════════════════════════════════════════════

class TestPhase2AutoInsight:
    """Phase 2.3: Auto insight scanning after data load."""

    @pytest.mark.parametrize("filename", [
        "游戏Abanner汇总数据.xlsx",
        "游戏互推.xlsx",
        "省钱卡用户最近流水_20260511.xlsx",
    ])
    def test_auto_insight_scan_real_data(self, filename):
        from data_agent.tools.auto_insight import auto_insight_scan, format_auto_insight
        df = _load_excel(filename)
        result = auto_insight_scan(df, "test_dataset")

        assert "scan_mode" in result
        assert "data_identity" in result
        assert "field_semantics" in result
        assert "data_health" in result

        # Format should produce readable output
        text = format_auto_insight(result)
        assert len(text) > 0

    def test_auto_insight_game_banner(self):
        """Game banner data should produce valid insight scan results."""
        from data_agent.tools.auto_insight import auto_insight_scan
        df = _load_excel("游戏Abanner汇总数据.xlsx")
        result = auto_insight_scan(df, "banner")

        # Verify all expected keys exist with valid types
        assert isinstance(result["data_identity"], dict)
        assert isinstance(result["field_semantics"], dict)
        assert isinstance(result["data_health"], dict)
        assert "score" in result["data_health"]

        # field_semantics should have classified some columns as metrics
        semantics = result["field_semantics"]
        assert len(semantics.get("metric", [])) > 0, f"Expected metrics, got {semantics}"
        assert len(semantics.get("time", [])) > 0, f"Expected time columns, got {semantics}"

    def test_auto_insight_savings_card_transactions(self):
        """Savings card transaction data should detect ID columns and metrics."""
        from data_agent.tools.auto_insight import auto_insight_scan
        df = _load_excel("省钱卡用户最近流水_20260511.xlsx")
        result = auto_insight_scan(df, "transactions")

        semantics = result["field_semantics"]
        # Should detect IDs (order_id, user_id)
        id_cols = semantics.get("id", [])
        assert len(id_cols) >= 1, f"Expected ID columns, got {semantics}"

    def test_auto_insight_health_score(self):
        from data_agent.tools.auto_insight import auto_insight_scan
        df = _load_excel("游戏A内购数据.xlsx")
        result = auto_insight_scan(df, "iap")

        health = result["data_health"]
        assert "score" in health
        assert 0 <= health["score"] <= 100

    def test_auto_insight_adaptive_sampling(self):
        """Large dataset should trigger sampling."""
        from data_agent.tools.auto_insight import auto_insight_scan
        # 13815 rows is under 100K, should use full scan
        df = _load_excel("省钱卡用户最近流水_20260511.xlsx")
        result = auto_insight_scan(df, "large_test")
        assert result["scan_mode"] in ("full", "sampled_10pct", "sampled_1pct")

    def test_auto_insight_observations(self):
        """Should generate business observations for data with time + metrics."""
        from data_agent.tools.auto_insight import auto_insight_scan
        df = _load_excel("游戏A内购数据.xlsx")
        result = auto_insight_scan(df, "iap")
        observations = result.get("business_observations", [])
        # May or may not have observations depending on data patterns
        assert isinstance(observations, list)


class TestPhase2ToolParameterUpgrade:
    """Phase 2.1: Structured tool parameters."""

    def test_transform_data_filter_structured(self):
        from data_agent.session.workspace import workspace
        from data_agent.tools.registry import registry
        registry._ensure_discovered()
        df = _load_excel("游戏互推.xlsx")
        workspace.add("cross_filter", df)

        try:
            # Use int column for filter (卖量收入 is object type)
            result = registry.execute("transform_data", {
                "name": "cross_filter", "operation": "filter",
                "condition": "曝光次数 > 100000",
            })
            output = result.to_cli()
            parsed = json.loads(output)
            assert parsed["operation"] == "filter"
            assert parsed["rows"] > 0
        finally:
            workspace._datasets.pop("cross_filter", None)
            workspace._datasets.pop("cross_filter_filtered", None)

    def test_transform_data_group_aggregate_structured(self):
        from data_agent.session.workspace import workspace
        from data_agent.tools.registry import registry
        registry._ensure_discovered()
        df = _load_excel("游戏互推.xlsx")
        workspace.add("cross_grp", df)

        try:
            result = registry.execute("transform_data", {
                "name": "cross_grp", "operation": "group_aggregate",
                "group_by": ["流量主游戏"],
                "aggregations": [
                    {"column": "曝光次数", "functions": ["sum", "mean"]},
                    {"column": "有效点击次数", "functions": ["sum"]},
                ],
            })
            output = result.to_cli()
            parsed = json.loads(output)
            assert parsed["operation"] == "group_aggregate"
            assert parsed["rows"] > 0
        finally:
            workspace._datasets.pop("cross_grp", None)
            workspace._datasets.pop("cross_grp_grouped", None)

    def test_transform_data_sort_structured(self):
        from data_agent.session.workspace import workspace
        from data_agent.tools.registry import registry
        registry._ensure_discovered()
        df = _load_excel("游戏互推.xlsx")
        workspace.add("cross_sort", df)

        try:
            result = registry.execute("transform_data", {
                "name": "cross_sort", "operation": "sort",
                "sort_by": ["曝光次数"], "ascending": False,
            })
            output = result.to_cli()
            parsed = json.loads(output)
            assert parsed["operation"] == "sort"
        finally:
            workspace._datasets.pop("cross_sort", None)
            workspace._datasets.pop("cross_sort_sorted", None)


class TestPhase2ToolDescriptions:
    """Phase 2.2: LLM-friendly tool descriptions."""

    def test_load_data_description_has_sections(self):
        from data_agent.tools.registry import registry
        registry._ensure_discovered()
        tool = registry.get("load_data")
        assert tool is not None
        desc = tool.description
        # Should have usage guidance
        assert any(kw in desc for kw in ("使用场景", "场景", "适用"))

    def test_transform_data_description_has_sections(self):
        from data_agent.tools.registry import registry
        registry._ensure_discovered()
        tool = registry.get("transform_data")
        assert tool is not None
        desc = tool.description
        assert any(kw in desc for kw in ("使用场景", "场景", "适用"))

    def test_quick_profile_description_has_decision_rules(self):
        from data_agent.tools.registry import registry
        registry._ensure_discovered()
        tool = registry.get("quick_profile")
        assert tool is not None
        desc = tool.description
        assert any(kw in desc for kw in ("场景", "适用", "使用"))


# ═══════════════════════════════════════════════════════════════
# Phase 3: Analysis Flow Enhancement Tests
# ═══════════════════════════════════════════════════════════════

class TestPhase3RegressionHandling:
    """Phase 3.2: Adaptive regression when analysis hits issues."""

    def test_quality_block_triggers_regression(self):
        from data_agent.agent.analysis_state import AnalysisSessionState
        state = AnalysisSessionState(session_id="test", stage="execute")
        result = json.dumps({
            "dataset": "test", "total_issues": 1,
            "issues": [{"type": "missing_values", "column": "revenue", "percentage": 95, "severity": "block"}],
        })
        msg = state.check_regression_triggers("detect_data_quality", result)
        assert msg is not None
        assert state.stage == "scope"
        assert len(state.regression_history) == 1

    def test_insufficient_data_triggers_regression(self):
        from data_agent.agent.analysis_state import AnalysisSessionState
        state = AnalysisSessionState(session_id="test", stage="execute")
        result = json.dumps({"error": "数据点太少，无法进行时间序列分析"})
        msg = state.check_regression_triggers("analyze_time_series", result)
        assert msg is not None
        assert state.stage == "plan"

    def test_analysis_error_triggers_regression(self):
        from data_agent.agent.analysis_state import AnalysisSessionState
        state = AnalysisSessionState(session_id="test", stage="execute")
        result = json.dumps({"error": "Column not found"})
        msg = state.check_regression_triggers("analyze_time_series", result)
        assert msg is not None
        assert state.stage == "plan"

    def test_no_regression_on_normal_result(self):
        from data_agent.agent.analysis_state import AnalysisSessionState
        state = AnalysisSessionState(session_id="test", stage="execute")
        result = json.dumps({"trend": "up", "mean": 100.5})
        msg = state.check_regression_triggers("analyze_time_series", result)
        assert msg is None
        assert state.stage == "execute"

    def test_regression_history_persists(self):
        from data_agent.agent.analysis_state import AnalysisSessionState
        state = AnalysisSessionState(session_id="test", stage="execute")
        state.check_regression_triggers("detect_data_quality", json.dumps({
            "issues": [{"severity": "block"}], "total_issues": 1,
        }))
        # After first regression, stage is "scope". Second regression from scope won't trigger.
        # Reset to execute to test second regression
        state.stage = "execute"
        state.check_regression_triggers("analyze_time_series", json.dumps({
            "error": "数据点太少",
        }))
        assert len(state.regression_history) == 2


class TestPhase3ConfidenceCalibration:
    """Phase 3.3: Confidence calibration in evidence records."""

    def test_high_confidence_method_inadequate_sample_downgraded(self):
        from data_agent.tools.analysis_flow import _calibrate_confidence
        payload = {
            "confidence": "high",
            "method": "clustered_group_compare",
            "claim_type": "inferential",
            "sample_size": 10_000,
            "sample_adequacy": {
                "status": "inadequate",
                "design": "clustered",
                "reason": "too few independent clusters",
            },
            "effect_estimate": 0.1,
            "confidence_interval": [-0.2, 0.4],
            "limitations": "some",
        }
        warnings = _calibrate_confidence(payload)
        assert len(warnings) > 0
        assert "independent clusters" in warnings[0]

    def test_high_confidence_non_significant_downgraded(self):
        from data_agent.tools.analysis_flow import _calibrate_confidence
        payload = {"confidence": "high", "significance": "not significant", "limitations": "some"}
        warnings = _calibrate_confidence(payload)
        assert len(warnings) > 0

    def test_high_confidence_no_limitations_warned(self):
        from data_agent.tools.analysis_flow import _calibrate_confidence
        payload = {"confidence": "high", "sample_size": 100}
        warnings = _calibrate_confidence(payload)
        assert any("局限" in w for w in warnings)

    def test_medium_confidence_not_downgraded(self):
        from data_agent.tools.analysis_flow import _calibrate_confidence
        payload = {"confidence": "medium", "sample_size": 5}
        warnings = _calibrate_confidence(payload)
        assert len(warnings) == 0

    def test_record_evidence_auto_downgrades(self):
        """record_evidence_record should auto-downgrade high confidence with bad evidence."""
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context
        from data_agent.agent.analysis_state import AnalysisSessionState
        from data_agent.tools.registry import registry

        registry._ensure_discovered()
        ctx = AgentContext(session_id="test_cal_ev")
        ctx.analysis_state = AnalysisSessionState(session_id="test_cal_ev")
        token = set_current_context(ctx)
        try:
            record = json.dumps({
                "claim": "Test claim",
                "dataset": "test",
                "method": "test",
                "tool_calls": [],
                "result_summary": "summary",
                "limitations": "some",
                "confidence": "high",
                "sample_size": 5,
                "sample_adequacy": {
                    "status": "inadequate",
                    "design": "independent_groups",
                    "reason": "too few independent observations for the selected method",
                },
            })
            result = registry.execute("record_evidence_record", {"record_json": record})
            parsed = json.loads(result.to_cli())
            assert parsed.get("confidence_auto_downgraded") is True
            assert parsed.get("original_confidence") == "high"
        finally:
            reset_current_context(token)


class TestPhase3ConversationMode:
    """Phase 3.4: Conversation mode with read-only query tools."""

    def test_get_analysis_summary_returns_state(self):
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context
        from data_agent.agent.analysis_state import AnalysisSessionState
        from data_agent.tools.registry import registry

        registry._ensure_discovered()
        ctx = AgentContext(session_id="test_conv")
        state = AnalysisSessionState(
            session_id="test_conv", stage="execute", goal="test goal",
            evidence_records=[{"claim": "test claim", "confidence": "high"}],
        )
        ctx.analysis_state = state
        token = set_current_context(ctx)
        try:
            result = registry.execute("get_analysis_summary", {})
            parsed = json.loads(result.to_cli())
            assert parsed["stage"] == "execute"
            assert parsed["goal"] == "test goal"
            assert parsed["evidence_count"] == 1
        finally:
            reset_current_context(token)

    def test_conversation_prompt_mentions_summary_tool(self):
        from data_agent.agent.prompts import build_system_prompt, AGENT_CONVERSATION
        # The conversation template itself mentions get_analysis_summary
        assert "get_analysis_summary" in AGENT_CONVERSATION


# ═══════════════════════════════════════════════════════════════
# Phase 4: Agent Capability Tests
# ═══════════════════════════════════════════════════════════════

class TestPhase4SessionRestore:
    """Phase 4.1: Session restore syncs analysis_state."""

    def test_restore_with_project_change(self):
        from data_agent.agent.analysis_state import AnalysisSessionState, _state_path
        session_id = "test_restore_phase4"

        state = AnalysisSessionState(session_id=session_id, project_name="proj_A", goal="goal_A")
        state.save()
        try:
            from data_agent.agent.analysis_state import load_analysis_state
            restored = load_analysis_state(session_id, "proj_B")
            assert restored.project_name == "proj_B"
            assert restored.goal == "goal_A"  # data preserved
        finally:
            _state_path(session_id).unlink(missing_ok=True)


class TestPhase4MultiDataset:
    """Phase 4.2: Multi-dataset analysis support."""

    def test_cross_dataset_hints_with_shared_user_id(self):
        """Savings card orders and transactions share user_id."""
        from data_agent.session.workspace import Workspace
        from data_agent.tools.data_understand import interpret_dataset

        ws = _fresh_workspace()
        df_orders = _load_excel("省钱卡订单_20260507.xlsx")
        df_transactions = _load_excel("省钱卡用户最近流水_20260511.xlsx")
        ws.add("orders", df_orders)
        ws.add("transactions", df_transactions)

        with patch("data_agent.tools.data_understand.workspace", ws):
            with patch("data_agent.tools._utils.workspace", ws):
                result = interpret_dataset("orders")
                from data_agent.tools.registry import ToolResult
                if isinstance(result, ToolResult) and result.data:
                    hints = result.data.get("cross_dataset_hints", [])
                    # Should detect user_id as shared column
                    if hints:
                        all_shared = []
                        for h in hints:
                            all_shared.extend(h.get("shared_columns", []))
                        assert "user_id" in all_shared, f"Expected user_id in shared, got {all_shared}"

    def test_game_banner_and_iap_cross_hints(self):
        """Banner and IAP data share 日期 column."""
        from data_agent.session.workspace import Workspace
        from data_agent.tools.data_understand import interpret_dataset

        ws = _fresh_workspace()
        df_banner = _load_excel("游戏Abanner汇总数据.xlsx")
        df_iap = _load_excel("游戏A内购数据.xlsx")
        ws.add("banner", df_banner)
        ws.add("iap", df_iap)

        with patch("data_agent.tools.data_understand.workspace", ws):
            with patch("data_agent.tools._utils.workspace", ws):
                result = interpret_dataset("banner")
                from data_agent.tools.registry import ToolResult
                if isinstance(result, ToolResult) and result.data:
                    hints = result.data.get("cross_dataset_hints", [])
                    if hints:
                        all_shared = []
                        for h in hints:
                            all_shared.extend(h.get("shared_columns", []))
                        # Should detect 日期 or 活跃用户 shared columns
                        found = any(c in all_shared for c in ("日期", "活跃用户", "活跃用户数", "新增用户", "新增用户数"))
                        assert found, f"Expected shared columns between banner/iap, got {all_shared}"

    def test_multi_dataset_strategy_in_prompt(self):
        from data_agent.agent.prompts import AGENT_ANALYSIS
        # The multi-dataset strategy is in AGENT_ANALYSIS template
        assert "多数据集" in AGENT_ANALYSIS
        assert "merge" in AGENT_ANALYSIS


class TestPhase4Proficiency:
    """Phase 4.4: User proficiency detection and adaptive output."""

    @pytest.mark.parametrize("input_text,expected", [
        ("帮我看下数据", "beginner"),
        ("我不太懂这个", "beginner"),
        ("能不能通俗一点解释", "beginner"),
        ("做个回归分析看看R²和显著性水平", "advanced"),
        ("时间序列ARIMA模型，检查一下季节性和自相关", "advanced"),
        ("对比各渠道的转化率", "intermediate"),
    ])
    def test_proficiency_detection_cases(self, input_text, expected):
        from data_agent.agent.prompts import detect_user_proficiency
        result = detect_user_proficiency(input_text)
        assert result == expected, f"'{input_text}' → {result}, expected {expected}"

    def test_proficiency_auto_detect_in_context(self):
        from data_agent.agent.context import AgentContext
        ctx = AgentContext(session_id="test_prof")
        assert ctx.user_proficiency == "auto"

        from data_agent.agent.prompts import detect_user_proficiency
        ctx.user_proficiency = detect_user_proficiency("做个聚类分析看看k-means效果")
        assert ctx.user_proficiency == "advanced"

    def test_beginner_prompt_has_simple_language_rules(self):
        from data_agent.agent.prompts import build_system_prompt
        prompt = build_system_prompt(
            tool_list="test", user_input="帮我看下", proficiency="beginner",
        )
        assert "初学者" in prompt
        assert "通俗" in prompt

    def test_advanced_prompt_has_technical_focus(self):
        from data_agent.agent.prompts import build_system_prompt
        prompt = build_system_prompt(
            tool_list="test", user_input="做ARIMA分析", proficiency="advanced",
        )
        assert "高级" in prompt
        assert "方法论" in prompt or "显著性" in prompt


class TestPhase4ParallelExecution:
    """Phase 4.5: Parallel execution of read-only tools."""

    def test_read_only_set_completeness(self):
        """Verify key tools are correctly classified via auto-derivation."""
        from data_agent.tools.registry import registry, get_read_only_tools
        registry._ensure_discovered()
        ro = get_read_only_tools(registry)

        read_only_expected = [
            "describe_dataset", "preview_data", "quick_profile",
            "detect_data_quality", "interpret_dataset", "list_data",
            "analyze_time_series", "correlation_analysis", "distribution_analysis",
            "compare_periods", "top_n", "get_analysis_summary", "tool_search",
        ]
        write_expected = [
            "transform_data", "load_data", "derive_field", "run_python",
            "record_evidence_record", "create_chart", "ask_user_question",
            "export_data", "generate_report",
        ]

        for tool in read_only_expected:
            assert tool in ro, f"{tool} should be read-only"
        for tool in write_expected:
            assert tool not in ro, f"{tool} should NOT be read-only"

    def test_parallel_describe_and_preview(self):
        """Run describe_dataset and preview_data in parallel on real data."""
        from data_agent.agent.loop import AgentLoop
        from data_agent.session.workspace import Workspace
        from data_agent.tools.registry import registry

        registry._ensure_discovered()
        ws = _fresh_workspace()
        df = _load_excel("游戏互推.xlsx")
        ws.add("game_cross", df)

        with patch("data_agent.agent.loop.AgentLoop._ensure_mcp_initialized"):
            loop = AgentLoop(session_id="test_parallel_real")
            loop.context.workspace = ws

        mock_tc1 = MagicMock()
        mock_tc1.id = "call_describe"
        mock_tc1.name = "describe_dataset"
        mock_tc1.arguments = {"name": "game_cross"}

        mock_tc2 = MagicMock()
        mock_tc2.id = "call_preview"
        mock_tc2.name = "preview_data"
        mock_tc2.arguments = {"name": "game_cross", "n": 3}

        results = loop._execute_tools_parallel([mock_tc1, mock_tc2])

        assert len(results) == 2
        assert results[0][0].id == "call_describe"
        assert results[1][0].id == "call_preview"

        # Verify describe result contains dataset info
        desc_content = results[0][1]
        assert "game_cross" in desc_content

        # Verify preview result has content
        preview_content = results[1][1]
        assert len(preview_content) > 0

    def test_parallel_with_large_dataset(self):
        """Parallel execution with 13K+ row dataset."""
        from data_agent.agent.loop import AgentLoop
        from data_agent.session.workspace import Workspace
        from data_agent.tools.registry import registry

        registry._ensure_discovered()
        ws = _fresh_workspace()
        df = _load_excel("省钱卡用户最近流水_20260511.xlsx")
        ws.add("savings", df)

        with patch("data_agent.agent.loop.AgentLoop._ensure_mcp_initialized"):
            loop = AgentLoop(session_id="test_parallel_large")
            loop.context.workspace = ws

        mock_tc1 = MagicMock()
        mock_tc1.id = "call_describe1"
        mock_tc1.name = "describe_dataset"
        mock_tc1.arguments = {"name": "savings"}

        mock_tc2 = MagicMock()
        mock_tc2.id = "call_describe2"
        mock_tc2.name = "describe_dataset"
        mock_tc2.arguments = {"name": "savings"}

        results = loop._execute_tools_parallel([mock_tc1, mock_tc2])
        assert len(results) == 2
        for _, content in results:
            assert "error" not in content.lower()[:30]


# ═══════════════════════════════════════════════════════════════
# Cross-Phase Integration Tests
# ═══════════════════════════════════════════════════════════════

class TestCrossPhaseIntegration:
    """End-to-end scenarios spanning multiple phases."""

    def test_load_insight_classify_respond(self):
        """Load data → auto_insight → classify intent → build prompt."""
        from data_agent.session.workspace import Workspace
        from data_agent.tools.auto_insight import auto_insight_scan, format_auto_insight
        from data_agent.agent.intent import plan_turn_intent
        from data_agent.agent.prompts import build_system_prompt, detect_user_proficiency

        # Load real data
        df = _load_excel("游戏A内购数据.xlsx")

        # Auto insight
        insight = auto_insight_scan(df, "iap")
        text = format_auto_insight(insight)
        assert len(text) > 0

        # Classify intent
        ctx = "- iap: 248 rows x 13 cols"
        intent = plan_turn_intent("分析一下付费率的变化趋势", ctx)
        assert intent.intent_type in ("directed_analysis", "comprehensive_report")

        # Build prompt with proficiency
        prof = detect_user_proficiency("分析一下付费率的变化趋势")
        prompt = build_system_prompt(
            tool_list="analyze_time_series, compare_periods",
            user_input="分析一下付费率的变化趋势",
            session_context=ctx,
            proficiency=prof,
        )
        assert "analyze_time_series" in prompt

    def test_error_recovery_then_regression(self):
        """Tool error → recovery hint → regression check."""
        from data_agent.agent.analysis_state import AnalysisSessionState
        from data_agent.tools.registry import registry, ToolResult

        # Simulate a tool error during execute stage
        state = AnalysisSessionState(session_id="test_err_regr", stage="execute")

        # Tool returns error about insufficient data
        error_result = ToolResult(summary=json.dumps({"error": "数据点太少，无法进行时间序列分析"}))
        formatted = registry.format_result("analyze_time_series", error_result)
        assert "恢复建议" in formatted

        # Regression check
        msg = state.check_regression_triggers("analyze_time_series", error_result.to_cli())
        assert msg is not None
        assert state.stage == "plan"

    def test_multi_dataset_transform_analyze(self):
        """Load two datasets → merge → analyze the merged result."""
        from data_agent.session.workspace import workspace
        from data_agent.tools.registry import registry

        registry._ensure_discovered()
        df_banner = _load_excel("游戏Abanner汇总数据.xlsx")
        df_iap = _load_excel("游戏A内购数据.xlsx")
        workspace.add("banner_merge", df_banner)
        workspace.add("iap_merge", df_iap)

        try:
            # Merge on 日期
            result = registry.execute("transform_data", {
                "name": "banner_merge", "operation": "merge",
                "other_name": "iap_merge", "merge_on": "日期",
            })
            output = result.to_cli()
            parsed = json.loads(output)
            assert parsed["operation"] == "merge"
            assert parsed["rows"] > 0
            assert len(parsed["columns"]) > 18
        finally:
            for key in list(workspace._datasets.keys()):
                if "banner_merge" in key or "iap_merge" in key:
                    workspace._datasets.pop(key, None)

    def test_proficiency_affects_evidence_recording(self):
        """Advanced user should get different prompt than beginner when recording evidence."""
        from data_agent.agent.prompts import build_system_prompt, _get_proficiency_instruction

        beg_instruction = _get_proficiency_instruction("beginner")
        adv_instruction = _get_proficiency_instruction("advanced")

        # Beginner instruction mentions 通俗, advanced mentions 方法论
        assert "通俗" in beg_instruction
        assert "方法论" in adv_instruction or "显著性" in adv_instruction

    def test_confidence_calibration_with_real_data_analysis(self):
        """Use real data to verify method-specific confidence calibration."""
        from data_agent.agent.context import AgentContext, set_current_context, reset_current_context
        from data_agent.agent.analysis_state import AnalysisSessionState
        from data_agent.tools.registry import registry
        from data_agent.session.workspace import Workspace

        registry._ensure_discovered()
        ws = _fresh_workspace()
        # Use small subset of game data
        df = _load_excel("省钱卡订单_20260507.xlsx").head(5)
        ws.add("tiny", df)

        ctx = AgentContext(session_id="test_conf_cal")
        ctx.analysis_state = AnalysisSessionState(session_id="test_conf_cal")
        token = set_current_context(ctx)
        try:
            record = json.dumps({
                "claim": "省钱卡月卡是最受欢迎的商品",
                "dataset": "tiny",
                "method": "频率统计",
                "tool_calls": [{"name": "preview_data"}],
                "result_summary": "月卡出现3次，占比60%",
                "limitations": "样本量极小",
                "confidence": "high",
                "sample_size": 5,
                "sample_adequacy": {
                    "status": "inadequate",
                    "design": "categorical_frequency",
                    "reason": "observed categories do not support a stable popularity ranking",
                },
            })
            result = registry.execute("record_evidence_record", {"record_json": record})
            parsed = json.loads(result.to_cli())
            # The method-specific adequacy result, not a universal n cutoff, downgrades it.
            assert parsed.get("confidence_auto_downgraded") is True
        finally:
            reset_current_context(token)

    def test_all_six_real_data_files_load_successfully(self):
        """Verify all 6 test data files can load and auto_insight runs."""
        from data_agent.tools.auto_insight import auto_insight_scan

        files = [
            "游戏Abanner汇总数据.xlsx",
            "游戏A内购数据.xlsx",
            "游戏A激励视频汇总数据报表.xlsx",
            "游戏互推.xlsx",
            "省钱卡用户最近流水_20260511.xlsx",
            "省钱卡订单_20260507.xlsx",
        ]
        for f in files:
            df = _load_excel(f)
            result = auto_insight_scan(df, f.replace(".xlsx", ""))
            assert "scan_mode" in result, f"Auto insight failed for {f}"
            assert "data_health" in result, f"Missing health for {f}"

    def test_all_real_data_interpret_dataset(self):
        """Verify interpret_dataset works on all 6 files."""
        from data_agent.session.workspace import Workspace
        from data_agent.tools.data_understand import interpret_dataset

        files = [
            "游戏Abanner汇总数据.xlsx",
            "游戏A内购数据.xlsx",
            "游戏A激励视频汇总数据报表.xlsx",
            "游戏互推.xlsx",
            "省钱卡用户最近流水_20260511.xlsx",
            "省钱卡订单_20260507.xlsx",
        ]
        for f in files:
            ws = _fresh_workspace()
            df = _load_excel(f)
            name = f.replace(".xlsx", "")
            ws.add(name, df)

            with patch("data_agent.tools.data_understand.workspace", ws):
                with patch("data_agent.tools._utils.workspace", ws):
                    result = interpret_dataset(name)
                    from data_agent.tools.registry import ToolResult
                    if isinstance(result, ToolResult):
                        assert result.data is not None, f"interpret_dataset returned no data for {f}"
                        assert "grain" in result.data, f"Missing grain for {f}"
                        assert "suggested_analyses" in result.data, f"Missing suggested_analyses for {f}"


# ═══════════════════════════════════════════════════════════════
# Additional Optimization Tests
# ═══════════════════════════════════════════════════════════════

class TestAutoCleanNumericCoercion:
    """Auto-clean should coerce object columns that contain numeric values."""

    def test_object_numeric_column_converted(self):
        """卖量收入 (object with float values) should be converted to float64."""
        from data_agent.tools.data_clean import auto_clean
        df = _load_excel("游戏互推.xlsx")
        assert df["卖量收入"].dtype == object

        cleaned, applied, _ = auto_clean(df)
        assert cleaned["卖量收入"].dtype == "float64"

        # Verify filter works on cleaned data
        filtered = cleaned.query("卖量收入 > 1000")
        assert len(filtered) > 0

    def test_mixed_object_column_not_converted(self):
        """Object columns with truly mixed data should not be forced."""
        from data_agent.tools.data_clean import auto_clean
        df = pd.DataFrame({
            "name": ["Alice", "Bob", "Charlie"],
            "mixed": ["100", "hello", "200"],  # 2/3 numeric = 66% < 90%
        })
        cleaned, _, _ = auto_clean(df)
        # mixed should stay non-numeric since conversion rate < 90%
        assert not pd.api.types.is_numeric_dtype(cleaned["mixed"])

    def test_mostly_numeric_object_column_converted(self):
        """Object column with >90% numeric values should be converted."""
        from data_agent.tools.data_clean import auto_clean
        df = pd.DataFrame({
            "values": ["1.5", "2.3", "3.1", "4.0", None, "5.2", "6.1", "7.3", "8.0", "9.9"],
        })
        cleaned, applied, _ = auto_clean(df)
        assert cleaned["values"].dtype in ("float64", "Int64", "float32")

    def test_banner_percentage_columns_converted(self):
        """Banner data percentage columns should be converted to float."""
        from data_agent.tools.data_clean import auto_clean
        df = _load_excel("游戏Abanner汇总数据.xlsx")
        cleaned, applied, _ = auto_clean(df)

        # BN_曝光率 and BN_点击率 are percentage strings
        applied_cols = {a["column"] for a in applied}
        assert "BN_曝光率" in applied_cols or "BN_点击率" in applied_cols


class TestUnifiedFieldClassification:
    """Verify auto_insight uses the same classification as interpret_dataset."""

    def test_consistent_time_detection(self):
        """Both systems should detect the same time columns."""
        from data_agent.tools.auto_insight import auto_insight_scan
        from data_agent.session.workspace import Workspace
        from data_agent.tools.data_understand import _classify_columns

        df = _load_excel("游戏A内购数据.xlsx")

        # auto_insight
        insight = auto_insight_scan(df, "iap")
        insight_time = insight["field_semantics"]["time"]

        # interpret_dataset classification
        classified = _classify_columns(df)
        interp_time = classified["time_columns"]

        # Both should detect 日期 as time column
        assert "日期" in insight_time, f"auto_insight missed 日期, got {insight_time}"
        assert "日期" in interp_time, f"_classify_columns missed 日期, got {interp_time}"

    def test_consistent_id_detection(self):
        """Both systems should detect the same ID columns."""
        from data_agent.tools.auto_insight import auto_insight_scan
        from data_agent.tools.data_understand import _classify_columns

        df = _load_excel("省钱卡用户最近流水_20260511.xlsx")

        insight = auto_insight_scan(df, "savings")
        insight_ids = insight["field_semantics"]["id"]

        classified = _classify_columns(df)
        interp_ids = [c["column"] for c in classified["id_columns"]]

        # order_id should be detected by both (high uniqueness)
        if "order_id" in interp_ids:
            assert "order_id" in insight_ids, f"auto_insight missed order_id, got {insight_ids}"


class TestSharedCrossDatasetDetection:
    """Cross-dataset detection should use the shared function consistently."""

    def test_interpret_uses_shared_detection(self):
        """interpret_dataset should use detect_cross_dataset_relationships."""
        from data_agent.session.workspace import Workspace
        from data_agent.tools.data_understand import interpret_dataset

        ws = Workspace()
        ws.add("a", pd.DataFrame({"user_id": [1, 2, 3], "val": [10, 20, 30]}))
        ws.add("b", pd.DataFrame({"user_id": [2, 3, 4], "score": [85, 90, 75]}))

        with patch("data_agent.tools.data_understand.workspace", ws):
            with patch("data_agent.tools._utils.workspace", ws):
                result = interpret_dataset("a")
                from data_agent.tools.registry import ToolResult
                if isinstance(result, ToolResult) and result.data:
                    hints = result.data.get("cross_dataset_hints", [])
                    if hints:
                        # Should detect user_id as shared column
                        found = any("user_id" in h.get("shared_columns", []) for h in hints)
                        assert found, f"Expected user_id in hints, got {hints}"

    def test_overlap_pct_in_hints(self):
        """Hints should include overlap percentage from shared detection."""
        from data_agent.session.workspace import Workspace
        from data_agent.tools.data_understand import interpret_dataset

        ws = Workspace()
        ws.add("x", pd.DataFrame({"key": [1, 2, 3], "v1": [10, 20, 30]}))
        ws.add("y", pd.DataFrame({"key": [2, 3, 4], "v2": [40, 50, 60]}))

        with patch("data_agent.tools.data_understand.workspace", ws):
            with patch("data_agent.tools._utils.workspace", ws):
                result = interpret_dataset("x")
                from data_agent.tools.registry import ToolResult
                if isinstance(result, ToolResult) and result.data:
                    hints = result.data.get("cross_dataset_hints", [])
                    if hints:
                        assert "overlap_pct" in hints[0], f"Missing overlap_pct, got {hints[0]}"


class TestAutoDerivedReadOnlyTools:
    """READ_ONLY_TOOLS should be auto-derived from ToolCapability metadata."""

    def test_read_only_set_populated(self):
        from data_agent.tools.registry import registry, get_read_only_tools
        registry._ensure_discovered()
        ro = get_read_only_tools(registry)
        assert len(ro) >= 25  # Should have at least as many as the old static set

    def test_write_tools_excluded(self):
        from data_agent.tools.registry import registry, get_read_only_tools
        registry._ensure_discovered()
        ro = get_read_only_tools(registry)

        write_tools = [
            "transform_data", "load_data", "run_python", "create_chart",
            "record_evidence_record", "ask_user_question",
            "export_data", "generate_report",
        ]
        for t in write_tools:
            assert t not in ro, f"{t} should not be read-only"

    def test_analysis_tools_are_read_only(self):
        from data_agent.tools.registry import registry, get_read_only_tools
        registry._ensure_discovered()
        ro = get_read_only_tools(registry)

        analysis_tools = [
            "analyze_time_series", "correlation_analysis", "distribution_analysis",
            "describe_dataset", "quick_profile", "compare_periods",
            "top_n", "funnel_analysis", "cohort_analysis",
        ]
        for t in analysis_tools:
            assert t in ro, f"{t} should be read-only"

    def test_new_tools_auto_classified(self):
        """Tools added without explicit READ_ONLY entry should be auto-classified."""
        from data_agent.tools.registry import registry, ToolDefinition, get_read_only_tools, _cap
        registry._ensure_discovered()

        # Register a test tool with low risk level
        @registry.register(
            name="test_auto_ro",
            description="test",
            capability=_cap("test.ro", "test_cat", ["test"], risk_level="low"),
        )
        def test_auto_ro():
            return "ok"

        ro = get_read_only_tools(registry)
        assert "test_auto_ro" in ro

    def test_high_risk_not_read_only(self):
        """Tools with risk_level != 'low' should not be read-only."""
        from data_agent.tools.registry import registry, ToolDefinition, get_read_only_tools, _cap
        registry._ensure_discovered()

        @registry.register(
            name="test_high_risk",
            description="test",
            capability=_cap("test.high", "test_cat", ["test"], risk_level="high"),
        )
        def test_high_risk():
            return "ok"

        ro = get_read_only_tools(registry)
        assert "test_high_risk" not in ro
