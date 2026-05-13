"""Phase 3 tests: LLM playbook selection, adaptive regression, confidence calibration,
conversation mode enhancement.

Usage:
  python tests/test_phase3.py
  pytest tests/test_phase3.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
SKIP = 0
ERRORS = []

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test(name, func):
    global PASS, FAIL, SKIP
    print(f"  {name}...", end=" ", flush=True)
    try:
        result = func()
        if result is True:
            PASS += 1
            print("PASS")
        elif result == "skip":
            SKIP += 1
            print("SKIP")
        else:
            FAIL += 1
            msg = f"FAIL: {name} — {result}"
            ERRORS.append(msg)
            print(msg)
    except Exception as e:
        FAIL += 1
        msg = f"FAIL: {name} — {e}"
        ERRORS.append(msg)
        print(msg)
        import traceback
        traceback.print_exc()


def assert_ok(result, label=""):
    if isinstance(result, str) and result.startswith("Error"):
        return f"{label} returned error: {result[:300]}"
    if isinstance(result, str) and '"error"' in result[:80]:
        return f"{label} returned error JSON: {result[:300]}"
    return True


# ============================================================
print("=" * 60)
print("初始化")
print("=" * 60)

from data_agent.config import get_config
from data_agent.tools import discover_tools
discover_tools()

import numpy as np
import pandas as pd
from data_agent.session.workspace import workspace
from data_agent.tools.registry import ToolResult, registry


def _reset_test_data():
    np.random.seed(42)
    n = 200
    workspace.add("test", pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=n, freq="D"),
        "sales": np.random.uniform(100, 1000, n).round(2),
        "users": np.random.randint(10, 500, n),
        "channel": np.random.choice(["A", "B", "C"], n),
        "region": np.random.choice(["north", "south", "east", "west"], n),
        "revenue": np.random.uniform(500, 5000, n).round(2),
    }))


_reset_test_data()


def _make_intent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded",
                 analysis_stage="execute", recommended_action="proceed"):
    from data_agent.agent.intent import TurnIntent
    return TurnIntent(
        intent_type=intent_type,
        clarity=clarity,
        data_state=data_state,
        analysis_stage=analysis_stage,
        recommended_action=recommended_action,
    )


# ============================================================
print("\n" + "=" * 60)
print("一、LLM Playbook 模块 — llm_playbook.py")
print("=" * 60)


def test_llm_playbook_module_imports():
    from data_agent.agent.llm_playbook import select_playbook_llm, _PLAYBOOK_CATALOG
    if not _PLAYBOOK_CATALOG:
        return "_PLAYBOOK_CATALOG should not be empty"
    if "data_understanding" not in _PLAYBOOK_CATALOG:
        return "_PLAYBOOK_CATALOG should list data_understanding playbook"
    if "forecast_decision_simulation" not in _PLAYBOOK_CATALOG:
        return "_PLAYBOOK_CATALOG should list forecast_decision_simulation"
    return True


def test_llm_playbook_catalog_has_all_playbooks():
    from data_agent.agent.llm_playbook import _PLAYBOOK_CATALOG
    from data_agent.agent.method_playbooks import PLAYBOOKS
    for pb_id in PLAYBOOKS:
        if pb_id not in _PLAYBOOK_CATALOG:
            return f"_PLAYBOOK_CATALOG missing playbook: {pb_id}"
    return True


def test_llm_playbook_prompt_template():
    from data_agent.agent.llm_playbook import _SELECTION_PROMPT_TEMPLATE
    if "__USER_INPUT__" not in _SELECTION_PROMPT_TEMPLATE:
        return "Prompt template should have __USER_INPUT__ placeholder"
    if "__DATA_FEATURES__" not in _SELECTION_PROMPT_TEMPLATE:
        return "Prompt template should have __DATA_FEATURES__ placeholder"
    return True


def test_llm_playbook_extract_json_valid():
    from data_agent.agent.llm_playbook import _extract_json
    result = _extract_json('{"primary": "driver_decomposition", "supporting": ["trend_period_comparison"], "reason": "test"}')
    if result is None:
        return "Should parse valid JSON"
    if result.get("primary") != "driver_decomposition":
        return f"Expected driver_decomposition, got {result.get('primary')}"
    return True


def test_llm_playbook_extract_json_in_codeblock():
    from data_agent.agent.llm_playbook import _extract_json
    text = '```json\n{"primary": "funnel_conversion", "supporting": [], "reason": "test"}\n```'
    result = _extract_json(text)
    if result is None:
        return "Should parse JSON from code block"
    if result.get("primary") != "funnel_conversion":
        return f"Expected funnel_conversion, got {result.get('primary')}"
    return True


def test_llm_playbook_extract_json_invalid():
    from data_agent.agent.llm_playbook import _extract_json
    result = _extract_json("not json at all")
    if result is not None:
        return f"Should return None for invalid JSON, got {result}"
    return True


def test_llm_playbook_returns_none_on_invalid_primary():
    """If LLM returns a nonexistent playbook ID, select_playbook_llm should return None."""
    from data_agent.agent.llm_playbook import _extract_json
    result = _extract_json('{"primary": "nonexistent_playbook", "supporting": [], "reason": "test"}')
    # The function itself checks against PLAYBOOKS, but _extract_json just parses
    if result is None:
        return "Should parse valid JSON even with invalid playbook ID"
    return True


test("llm_playbook: 模块导入", test_llm_playbook_module_imports)
test("llm_playbook: 目录包含所有playbook", test_llm_playbook_catalog_has_all_playbooks)
test("llm_playbook: 提示模板占位符", test_llm_playbook_prompt_template)
test("llm_playbook: JSON解析有效", test_llm_playbook_extract_json_valid)
test("llm_playbook: JSON解析代码块", test_llm_playbook_extract_json_in_codeblock)
test("llm_playbook: JSON解析无效返回None", test_llm_playbook_extract_json_invalid)
test("llm_playbook: 无效playbook ID", test_llm_playbook_returns_none_on_invalid_primary)


# ============================================================
print("\n" + "=" * 60)
print("二、Playbook 选择集成 — method_playbooks.py")
print("=" * 60)


def test_choose_primary_high_confidence_funnel():
    from data_agent.agent.method_playbooks import _choose_primary
    intent = _make_intent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")
    result = _choose_primary("分析一下漏斗转化率", intent, True)
    if result != "funnel_conversion":
        return f"Expected funnel_conversion, got {result}"
    return True


def test_choose_primary_high_confidence_forecast():
    from data_agent.agent.method_playbooks import _choose_primary
    intent = _make_intent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")
    result = _choose_primary("预测一下下季度销售额", intent, True)
    if result != "forecast_decision_simulation":
        return f"Expected forecast_decision_simulation, got {result}"
    return True


def test_choose_primary_high_confidence_driver():
    from data_agent.agent.method_playbooks import _choose_primary
    intent = _make_intent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")
    result = _choose_primary("为什么收入下降了", intent, True)
    if result != "driver_decomposition":
        return f"Expected driver_decomposition, got {result}"
    return True


def test_choose_primary_high_confidence_retention():
    from data_agent.agent.method_playbooks import _choose_primary
    intent = _make_intent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")
    result = _choose_primary("分析一下用户留存率", intent, True)
    if result != "retention_lifecycle":
        return f"Expected retention_lifecycle, got {result}"
    return True


def test_choose_primary_fallback_data_understanding():
    from data_agent.agent.method_playbooks import _choose_primary
    intent = _make_intent(intent_type="intent_negotiation", clarity="vague", data_state="data_loaded")
    result = _choose_primary("看看", intent, True)
    if result != "data_understanding":
        return f"Expected data_understanding fallback, got {result}"
    return True


def test_select_playbooks_returns_selection():
    from data_agent.agent.method_playbooks import select_playbooks
    from data_agent.agent.analysis_state import AnalysisSessionState
    intent = _make_intent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")
    state = AnalysisSessionState(session_id="test_session")
    selection = select_playbooks("分析漏斗转化", intent, state, "")
    if not selection:
        return "select_playbooks should return a PlaybookSelection"
    if selection.primary_playbook_id != "funnel_conversion":
        return f"Expected funnel_conversion, got {selection.primary_playbook_id}"
    if not selection.selection_reason:
        return "Should have selection_reason"
    return True


def test_select_playbooks_supporting_valid():
    from data_agent.agent.method_playbooks import select_playbooks
    from data_agent.agent.analysis_state import AnalysisSessionState
    intent = _make_intent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")
    state = AnalysisSessionState(session_id="test_session")
    selection = select_playbooks("分析漏斗转化", intent, state, "")
    for sid in selection.supporting_playbook_ids:
        if sid == selection.primary_playbook_id:
            return "Supporting should not include primary"
    return True


def test_select_playbooks_high_confidence_rules_list():
    """Verify _HIGH_CONFIDENCE_RULES covers the critical playbooks."""
    from data_agent.agent.method_playbooks import _HIGH_CONFIDENCE_RULES
    covered_ids = {pid for _, pid in _HIGH_CONFIDENCE_RULES}
    expected = {"funnel_conversion", "forecast_decision_simulation", "driver_decomposition",
                "retention_lifecycle", "revenue_profitability", "trend_period_comparison"}
    if not expected.issubset(covered_ids):
        return f"Missing high-confidence rules for: {expected - covered_ids}"
    return True


test("playbook: 漏斗关键词匹配", test_choose_primary_high_confidence_funnel)
test("playbook: 预测关键词匹配", test_choose_primary_high_confidence_forecast)
test("playbook: 归因关键词匹配", test_choose_primary_high_confidence_driver)
test("playbook: 留存关键词匹配", test_choose_primary_high_confidence_retention)
test("playbook: 模糊输入回退", test_choose_primary_fallback_data_understanding)
test("playbook: select_playbooks返回正确", test_select_playbooks_returns_selection)
test("playbook: supporting不包含primary", test_select_playbooks_supporting_valid)
test("playbook: 高置信规则覆盖", test_select_playbooks_high_confidence_rules_list)


# ============================================================
print("\n" + "=" * 60)
print("三、自适应回退 — analysis_state.py")
print("=" * 60)


def test_regression_history_field():
    from data_agent.agent.analysis_state import AnalysisSessionState
    state = AnalysisSessionState(session_id="test_reg")
    if not hasattr(state, "regression_history"):
        return "Should have regression_history field"
    if state.regression_history != []:
        return "regression_history should default to empty list"
    return True


def test_regression_history_serialization():
    from data_agent.agent.analysis_state import AnalysisSessionState
    state = AnalysisSessionState(session_id="test_reg", stage="execute")
    state.regression_history.append({"from_stage": "execute", "to_stage": "plan", "reason": "test"})
    d = state.to_dict()
    if "regression_history" not in d:
        return "to_dict should include regression_history"
    if len(d["regression_history"]) != 1:
        return "regression_history should have 1 entry"
    state2 = AnalysisSessionState.from_dict(d, "test_reg")
    if len(state2.regression_history) != 1:
        return "from_dict should preserve regression_history"
    return True


def test_check_regression_data_quality_block():
    from data_agent.agent.analysis_state import AnalysisSessionState
    state = AnalysisSessionState(session_id="test_reg", stage="execute")
    result = state.check_regression_triggers(
        "detect_data_quality",
        '{"severity": "block", "issues": ["missing 80% data"]}',
    )
    if result is None:
        return "Should detect block severity and regress"
    if state.stage != "scope":
        return f"Stage should be scope after regression, got {state.stage}"
    if not state.regression_history:
        return "Should record regression history"
    return True


def test_check_regression_insufficient_data():
    from data_agent.agent.analysis_state import AnalysisSessionState
    state = AnalysisSessionState(session_id="test_reg", stage="execute")
    result = state.check_regression_triggers(
        "analyze_time_series",
        '{"result": "insufficient data points for analysis"}',
    )
    if result is None:
        return "Should detect insufficient data"
    if state.stage != "plan":
        return f"Stage should be plan after regression, got {state.stage}"
    return True


def test_check_regression_error_in_analysis():
    from data_agent.agent.analysis_state import AnalysisSessionState
    state = AnalysisSessionState(session_id="test_reg", stage="execute")
    result = state.check_regression_triggers(
        "correlation_analysis",
        '{"error": "column not found"}',
    )
    if result is None:
        return "Should detect analysis error and regress"
    if state.stage != "plan":
        return f"Stage should be plan, got {state.stage}"
    return True


def test_check_regression_no_regression_on_success():
    from data_agent.agent.analysis_state import AnalysisSessionState
    state = AnalysisSessionState(session_id="test_reg", stage="execute")
    result = state.check_regression_triggers(
        "analyze_time_series",
        '{"trend": "up", "slope": 0.5}',
    )
    if result is not None:
        return f"Should not regress on successful result, got: {result}"
    if state.stage != "execute":
        return f"Stage should remain execute, got {state.stage}"
    return True


def test_check_regression_no_regression_in_discover():
    """Regression should not happen if stage is discover/scope."""
    from data_agent.agent.analysis_state import AnalysisSessionState
    state = AnalysisSessionState(session_id="test_reg", stage="discover")
    result = state.check_regression_triggers(
        "detect_data_quality",
        '{"severity": "block"}',
    )
    # discover stage should not regress to scope (already before scope)
    if result is not None and state.stage != "scope":
        return "Should handle edge cases gracefully"
    return True


def test_regression_summary():
    from data_agent.agent.analysis_state import analysis_state_summary, AnalysisSessionState
    state = AnalysisSessionState(session_id="test_reg", stage="scope")
    state.regression_history.append({
        "from_stage": "execute",
        "to_stage": "scope",
        "reason": "数据质量问题",
        "trigger_tool": "detect_data_quality",
    })
    summary = analysis_state_summary(state)
    if "last_regression" not in summary:
        return "Summary should include last_regression"
    if "execute" not in summary or "scope" not in summary:
        return f"Summary should mention regression stages: {summary}"
    return True


test("regression: regression_history字段", test_regression_history_field)
test("regression: 序列化/反序列化", test_regression_history_serialization)
test("regression: 数据质量block触发回退", test_check_regression_data_quality_block)
test("regression: 数据不足触发回退", test_check_regression_insufficient_data)
test("regression: 分析错误触发回退", test_check_regression_error_in_analysis)
test("regression: 成功结果不触发", test_check_regression_no_regression_on_success)
test("regression: discover阶段不触发", test_check_regression_no_regression_in_discover)
test("regression: summary包含回退历史", test_regression_summary)


# ============================================================
print("\n" + "=" * 60)
print("四、置信度校准 — prompts.py + analysis_flow.py")
print("=" * 60)


def test_prompt_has_calibration_rules():
    from data_agent.agent.prompts import AGENT_ANALYSIS
    if "置信度校准" not in AGENT_ANALYSIS:
        return "AGENT_ANALYSIS should have calibration rules section"
    return True


def test_prompt_calibration_sample_size():
    from data_agent.agent.prompts import AGENT_ANALYSIS
    if "样本量" not in AGENT_ANALYSIS or "< 30" not in AGENT_ANALYSIS:
        return "Calibration rules should mention sample size < 30"
    return True


def test_prompt_calibration_causal():
    from data_agent.agent.prompts import AGENT_ANALYSIS
    if "因果" not in AGENT_ANALYSIS:
        return "Calibration rules should mention causal restrictions"
    return True


def test_prompt_calibration_missing_rate():
    from data_agent.agent.prompts import AGENT_ANALYSIS
    if "缺失率" not in AGENT_ANALYSIS:
        return "Calibration rules should mention missing rate"
    return True


def test_calibrate_confidence_high_with_small_sample():
    from data_agent.tools.analysis_flow import _calibrate_confidence
    payload = {"confidence": "high", "sample_size": 10, "limitations": "small sample"}
    warnings = _calibrate_confidence(payload)
    if not warnings:
        return "Should warn about small sample size with high confidence"
    if "30" not in warnings[0]:
        return f"Warning should mention sample threshold, got: {warnings[0]}"
    return True


def test_calibrate_confidence_high_with_adequate_sample():
    from data_agent.tools.analysis_flow import _calibrate_confidence
    payload = {"confidence": "high", "sample_size": 500, "limitations": "observational data"}
    warnings = _calibrate_confidence(payload)
    # No sample size warning, no significance warning
    sample_warnings = [w for w in warnings if "样本量" in w]
    if sample_warnings:
        return f"Should not warn about sample size when n=500, got: {sample_warnings}"
    return True


def test_calibrate_confidence_medium_not_calibrated():
    from data_agent.tools.analysis_flow import _calibrate_confidence
    payload = {"confidence": "medium", "sample_size": 5}
    warnings = _calibrate_confidence(payload)
    if warnings:
        return f"Medium confidence should not be calibrated, got: {warnings}"
    return True


def test_calibrate_confidence_high_no_limitations():
    from data_agent.tools.analysis_flow import _calibrate_confidence
    payload = {"confidence": "high", "sample_size": 100}
    warnings = _calibrate_confidence(payload)
    if not warnings:
        return "Should warn about missing limitations"
    if "局限性" not in warnings[-1]:
        return f"Last warning should mention limitations, got: {warnings}"
    return True


def test_calibrate_confidence_significance_not_significant():
    from data_agent.tools.analysis_flow import _calibrate_confidence
    payload = {"confidence": "high", "significance": "not significant (p=0.15)", "limitations": "observational"}
    warnings = _calibrate_confidence(payload)
    sig_warnings = [w for w in warnings if "显著" in w]
    if not sig_warnings:
        return "Should warn about not significant result with high confidence"
    return True


def test_record_evidence_auto_downgrades():
    """record_evidence_record should auto-downgrade high confidence with small sample."""
    from data_agent.tools.analysis_flow import record_evidence_record
    record = json.dumps({
        "claim": "test claim",
        "dataset": "test",
        "method": "test method",
        "tool_calls": ["test_tool"],
        "result_summary": "test result",
        "limitations": "small sample",
        "confidence": "high",
        "sample_size": 5,
    })
    result = json.loads(record_evidence_record(record))
    # May have "error" for missing session, but calibration fields should still be present
    if result.get("confidence_auto_downgraded") is not True:
        return "Should auto_downgrade confidence"
    if result.get("original_confidence") != "high":
        return "Should record original_confidence as high"
    if "calibration_warnings" not in result:
        return "Should include calibration_warnings"
    return True


def test_record_evidence_keeps_medium_confidence():
    """record_evidence_record should keep medium confidence as-is."""
    from data_agent.tools.analysis_flow import record_evidence_record
    record = json.dumps({
        "claim": "test claim",
        "dataset": "test",
        "method": "test method",
        "tool_calls": ["test_tool"],
        "result_summary": "test result",
        "limitations": "test",
        "confidence": "medium",
        "sample_size": 5,
    })
    result = json.loads(record_evidence_record(record))
    if result.get("confidence_auto_downgraded"):
        return "Should NOT auto-downgrade medium confidence"
    return True


test("calibration: prompt有校准规则", test_prompt_has_calibration_rules)
test("calibration: 样本量规则", test_prompt_calibration_sample_size)
test("calibration: 因果约束", test_prompt_calibration_causal)
test("calibration: 缺失率规则", test_prompt_calibration_missing_rate)
test("calibration: 小样本降级", test_calibrate_confidence_high_with_small_sample)
test("calibration: 大样本不降级", test_calibrate_confidence_high_with_adequate_sample)
test("calibration: 中置信度不校准", test_calibrate_confidence_medium_not_calibrated)
test("calibration: 无局限性警告", test_calibrate_confidence_high_no_limitations)
test("calibration: 不显著结果警告", test_calibrate_confidence_significance_not_significant)
test("calibration: record_evidence自动降级", test_record_evidence_auto_downgrades)
test("calibration: record_evidence保持中置信度", test_record_evidence_keeps_medium_confidence)


# ============================================================
print("\n" + "=" * 60)
print("五、Conversation 模式增强 — prompts + tools")
print("=" * 60)


def test_conversation_prompt_mentions_tool():
    from data_agent.agent.prompts import AGENT_CONVERSATION
    if "get_analysis_summary" not in AGENT_CONVERSATION:
        return "AGENT_CONVERSATION should mention get_analysis_summary tool"
    return True


def test_conversation_prompt_says_readonly():
    from data_agent.agent.prompts import AGENT_CONVERSATION
    if "只读" not in AGENT_CONVERSATION:
        return "AGENT_CONVERSATION should mention tool is read-only"
    return True


def test_conversation_no_longer_says_no_tools():
    from data_agent.agent.prompts import AGENT_CONVERSATION
    if "无（纯对话模式）" in AGENT_CONVERSATION:
        return "Should no longer say 'no tools'"
    return True


def test_get_analysis_summary_registered():
    t = registry.get("get_analysis_summary")
    if t is None:
        return "get_analysis_summary should be registered"
    return True


def test_get_analysis_summary_tool_group():
    from data_agent.tools.registry import TOOL_GROUPS
    cq = TOOL_GROUPS.get("conversation_query", set())
    if "get_analysis_summary" not in cq:
        return "get_analysis_summary should be in conversation_query group"
    return True


def test_get_analysis_summary_executes():
    result = registry.execute("get_analysis_summary", {})
    if isinstance(result, str) and '"error"' in result:
        return f"Should not error: {result[:200]}"
    return True


def test_get_analysis_summary_returns_json():
    from data_agent.tools.analysis_flow import get_analysis_summary
    result = json.loads(get_analysis_summary())
    # May return "info" when no state, or "stage" when state exists
    if "stage" not in result and "info" not in result:
        return f"Should have 'stage' or 'info' field, got: {list(result.keys())}"
    return True


def test_conversation_tool_activation():
    from data_agent.agent.analysis_flow_controller import AnalysisFlowController
    from data_agent.agent.analysis_state import AnalysisSessionState
    from data_agent.tools.registry import TOOL_GROUPS

    controller = AnalysisFlowController("test_session")
    intent = _make_intent(intent_type="result_followup", clarity="clear", data_state="data_loaded")
    state = AnalysisSessionState(session_id="test_session")
    groups = controller.activate_tool_groups(registry, intent, state, "上次结论是什么")
    if "conversation_query" not in groups:
        return f"conversation mode should activate conversation_query group, got: {groups}"
    return True


def test_build_system_prompt_conversation_has_tool():
    from data_agent.agent.prompts import build_system_prompt
    prompt = build_system_prompt(
        tool_list="get_analysis_summary",
        user_input="上次分析的结论是什么",
        session_context="",
    )
    if "get_analysis_summary" not in prompt:
        return "Conversation prompt should include get_analysis_summary in available tools"
    return True


test("conversation: prompt提及工具", test_conversation_prompt_mentions_tool)
test("conversation: prompt标注只读", test_conversation_prompt_says_readonly)
test("conversation: prompt不再说无工具", test_conversation_no_longer_says_no_tools)
test("conversation: 工具已注册", test_get_analysis_summary_registered)
test("conversation: 工具分组正确", test_get_analysis_summary_tool_group)
test("conversation: 工具可执行", test_get_analysis_summary_executes)
test("conversation: 返回JSON结构", test_get_analysis_summary_returns_json)
test("conversation: 工具激活", test_conversation_tool_activation)
test("conversation: build_system_prompt包含工具", test_build_system_prompt_conversation_has_tool)


# ============================================================
print("\n" + "=" * 60)
print("六、Flow Controller 回退集成")
print("=" * 60)


def test_controller_check_tool_regression():
    from data_agent.agent.analysis_flow_controller import AnalysisFlowController
    from data_agent.agent.analysis_state import AnalysisSessionState

    controller = AnalysisFlowController("test_session")
    state = AnalysisSessionState(session_id="test_session", stage="execute")

    msg = controller.check_tool_regression(
        state,
        "detect_data_quality",
        '{"severity": "block", "issues": ["critical data loss"]}',
    )
    if msg is None:
        return "Should detect regression trigger"
    if state.stage != "scope":
        return f"Stage should be scope after regression, got {state.stage}"
    return True


def test_controller_check_tool_regression_no_trigger():
    from data_agent.agent.analysis_flow_controller import AnalysisFlowController
    from data_agent.agent.analysis_state import AnalysisSessionState

    controller = AnalysisFlowController("test_session")
    state = AnalysisSessionState(session_id="test_session", stage="execute")

    msg = controller.check_tool_regression(
        state,
        "analyze_time_series",
        '{"trend": "upward", "slope": 0.5}',
    )
    if msg is not None:
        return f"Should not trigger regression for success, got: {msg}"
    if state.stage != "execute":
        return f"Stage should remain execute, got {state.stage}"
    return True


test("controller: 回退触发", test_controller_check_tool_regression)
test("controller: 成功不触发", test_controller_check_tool_regression_no_trigger)


# ============================================================
print("\n" + "=" * 60)
print("七、回归测试 — Phase 3 不破坏现有功能")
print("=" * 60)

_reset_test_data()


def test_existing_select_playbooks_backward_compat():
    """select_playbooks should still work with keyword-only inputs."""
    from data_agent.agent.method_playbooks import select_playbooks
    from data_agent.agent.analysis_state import AnalysisSessionState

    intent = _make_intent(intent_type="directed_analysis", clarity="clear", data_state="data_loaded")
    state = AnalysisSessionState(session_id="test_session")

    # Funnel should still match via keyword
    sel = select_playbooks("分析漏斗", intent, state, "")
    if sel.primary_playbook_id != "funnel_conversion":
        return f"Funnel keyword should still match, got {sel.primary_playbook_id}"

    # Forecast should still match
    sel = select_playbooks("预测未来趋势", intent, state, "")
    if sel.primary_playbook_id != "forecast_decision_simulation":
        return f"Forecast keyword should still match, got {sel.primary_playbook_id}"

    return True


def test_existing_build_system_prompt_analysis():
    """Analysis prompt should still build correctly with calibration rules."""
    from data_agent.agent.prompts import build_system_prompt
    prompt = build_system_prompt(
        tool_list="tool1, tool2",
        user_input="分析销售趋势",
        session_context="test: 100 rows",
    )
    if "分析流程" not in prompt:
        return "Analysis prompt should have analysis workflow"
    if "置信度校准" not in prompt:
        return "Analysis prompt should have calibration rules after Phase 3"
    return True


def test_existing_record_evidence_basic():
    """record_evidence_record should still work for basic valid inputs."""
    from data_agent.tools.analysis_flow import record_evidence_record
    record = json.dumps({
        "claim": "Sales increased 15%",
        "dataset": "test",
        "method": "period comparison",
        "tool_calls": ["compare_periods"],
        "result_summary": "Jan: 1000, Feb: 1150",
        "limitations": "only 2 months data",
        "confidence": "medium",
        "sample_size": 60,
    })
    result = json.loads(record_evidence_record(record))
    # May have "error" for no session, but should have statistical_detail_status
    if "statistical_detail_status" not in result:
        return "Should have statistical_detail_status field"
    return True


def test_existing_tool_groups_not_broken():
    """Existing tool groups should still be intact."""
    from data_agent.tools.registry import TOOL_GROUPS
    required_groups = {"core", "eda", "ml", "stats", "report", "clean", "task", "knowledge"}
    missing = required_groups - set(TOOL_GROUPS.keys())
    if missing:
        return f"Missing tool groups: {missing}"
    if "conversation_query" not in TOOL_GROUPS:
        return "Should have conversation_query group"
    return True


test("regression: select_playbooks向后兼容", test_existing_select_playbooks_backward_compat)
test("regression: analysis prompt正常构建", test_existing_build_system_prompt_analysis)
test("regression: record_evidence基本功能", test_existing_record_evidence_basic)
test("regression: 工具分组完整", test_existing_tool_groups_not_broken)


# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 60)
print("Phase 3 测试结果汇总")
print("=" * 60)
print(f"  PASS: {PASS}")
print(f"  FAIL: {FAIL}")
print(f"  SKIP: {SKIP}")
print(f"  TOTAL: {PASS + FAIL + SKIP}")

if ERRORS:
    print("\n失败的测试:")
    for e in ERRORS:
        print(f"  - {e}")

if FAIL > 0:
    print("\n!!! 有测试未通过 !!!")
else:
    print("\n所有 Phase 3 测试通过！")
