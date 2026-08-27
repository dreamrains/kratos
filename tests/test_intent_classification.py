"""Comprehensive tests for the intent classification system.

Covers:
  - All 9 intent types with Chinese and English inputs
  - data_loaded vs no_data session context
  - TurnIntent dataclass, to_dict, fields
  - _stage_for and _action_for helpers
  - _LEGACY_INTENT_MAP backward compatibility
  - _PROMPT_LEVEL_MAP correctness
  - Edge cases: empty, whitespace, very short input
  - Ambiguity detection
  - LLM fallback via mocking _try_llm_classify
  - infer_data_state
  - Report keywords (including short ones like "报告")
  - Analysis keywords (evaluate, analyze, worth) with data loaded
  - Operation keywords only when no analysis keywords present
  - Guidance keywords branch by data state
"""

from dataclasses import fields
from unittest.mock import patch

import pytest

from data_agent.agent.intent import (
    _LEGACY_INTENT_MAP,
    _PROMPT_LEVEL_MAP,
    TurnIntent,
    _action_for,
    _stage_for,
    infer_data_state,
    plan_turn_intent,
)

# ── Shared fixtures ──────────────────────────────────────────

DATA_LOADED_CTX = "- main: 10 rows x 3 cols, columns: date, revenue, channel"
NO_DATA_CTX = ""


# ══════════════════════════════════════════════════════════════
# 1. TurnIntent dataclass
# ══════════════════════════════════════════════════════════════

class TestTurnIntentDataclass:

    def test_fields_present(self):
        """TurnIntent must expose exactly the expected fields."""
        expected = {
            "intent_type", "clarity", "data_state",
            "analysis_stage", "recommended_action", "execution_readiness",
            "reason", "ambiguities",
        }
        actual = {f.name for f in fields(TurnIntent)}
        assert actual == expected

    def test_to_dict_returns_dict(self):
        ti = TurnIntent(
            intent_type="simple_response",
            clarity="clear",
            data_state="no_data",
            analysis_stage="follow_up",
            recommended_action="answer_directly",
        )
        d = ti.to_dict()
        assert isinstance(d, dict)
        assert d["intent_type"] == "simple_response"
        assert d["clarity"] == "clear"
        assert d["data_state"] == "no_data"
        assert d["analysis_stage"] == "follow_up"
        assert d["recommended_action"] == "answer_directly"
        assert d["execution_readiness"] == "missing_data"
        assert d["reason"] == ""
        assert d["ambiguities"] == []

    def test_to_dict_with_ambiguities(self):
        ti = TurnIntent(
            intent_type="directed_analysis",
            clarity="vague",
            data_state="data_loaded",
            analysis_stage="execute",
            recommended_action="run_analysis",
            reason="test",
            ambiguities=[{"kind": "ambiguous_direction", "detail": "trend vs comparison"}],
        )
        d = ti.to_dict()
        assert len(d["ambiguities"]) == 1
        assert d["ambiguities"][0]["kind"] == "ambiguous_direction"

    def test_default_reason_and_ambiguities(self):
        ti = TurnIntent(
            intent_type="simple_response",
            clarity="clear",
            data_state="no_data",
            analysis_stage="follow_up",
            recommended_action="answer_directly",
        )
        assert ti.reason == ""
        assert ti.ambiguities == []

    def test_reason_set(self):
        ti = TurnIntent(
            intent_type="simple_response",
            clarity="clear",
            data_state="no_data",
            analysis_stage="follow_up",
            recommended_action="answer_directly",
            reason="问候或致谢",
        )
        assert ti.reason == "问候或致谢"


# ══════════════════════════════════════════════════════════════
# 2. infer_data_state
# ══════════════════════════════════════════════════════════════

class TestInferDataState:

    def test_no_data_empty(self):
        assert infer_data_state("") == "no_data"

    def test_no_data_text_without_rows(self):
        assert infer_data_state("session started") == "no_data"

    def test_data_loaded_with_rows(self):
        assert infer_data_state(DATA_LOADED_CTX) == "data_loaded"

    def test_data_loaded_with_columns_prefix(self):
        assert infer_data_state("columns: a, b, c") == "data_loaded"

    def test_data_loaded_with_rows_only(self):
        assert infer_data_state("20 rows loaded") == "data_loaded"


# ══════════════════════════════════════════════════════════════
# 3. _stage_for helper
# ══════════════════════════════════════════════════════════════

class TestStageFor:

    @pytest.mark.parametrize("intent_type", [
        "simple_response", "knowledge_qa", "analysis_consultation", "result_followup",
    ])
    def test_conversation_intents_return_follow_up(self, intent_type):
        assert _stage_for(intent_type, "no_data") == "follow_up"
        assert _stage_for(intent_type, "data_loaded") == "follow_up"

    @pytest.mark.parametrize("intent_type", ["intent_negotiation", "data_requirement"])
    def test_guidance_intents_no_data_scope(self, intent_type):
        assert _stage_for(intent_type, "no_data") == "scope"

    @pytest.mark.parametrize("intent_type", ["intent_negotiation", "data_requirement"])
    def test_guidance_intents_data_loaded_discover(self, intent_type):
        assert _stage_for(intent_type, "data_loaded") == "discover"

    def test_data_operation_execute(self):
        assert _stage_for("data_operation", "no_data") == "execute"
        assert _stage_for("data_operation", "data_loaded") == "execute"

    def test_directed_analysis_no_data_scope(self):
        assert _stage_for("directed_analysis", "no_data") == "scope"

    def test_directed_analysis_data_loaded_execute(self):
        assert _stage_for("directed_analysis", "data_loaded") == "execute"

    def test_comprehensive_report_no_data_scope(self):
        assert _stage_for("comprehensive_report", "no_data") == "scope"

    def test_comprehensive_report_data_loaded_report(self):
        assert _stage_for("comprehensive_report", "data_loaded") == "report"

    def test_unknown_intent_returns_discover(self):
        assert _stage_for("something_else", "no_data") == "discover"


# ══════════════════════════════════════════════════════════════
# 4. _action_for helper
# ══════════════════════════════════════════════════════════════

class TestActionFor:

    @pytest.mark.parametrize("intent_type", [
        "simple_response", "knowledge_qa", "analysis_consultation", "result_followup",
    ])
    def test_conversation_intents_answer_directly(self, intent_type):
        assert _action_for(intent_type, "no_data") == "answer_directly"
        assert _action_for(intent_type, "data_loaded") == "answer_directly"

    def test_intent_negotiation_guide_analysis(self):
        assert _action_for("intent_negotiation", "no_data") == "guide_analysis"
        assert _action_for("intent_negotiation", "data_loaded") == "guide_analysis"

    def test_data_requirement_request_data(self):
        assert _action_for("data_requirement", "no_data") == "request_data"
        assert _action_for("data_requirement", "data_loaded") == "request_data"

    def test_data_operation_execute(self):
        assert _action_for("data_operation", "no_data") == "execute_operation"
        assert _action_for("data_operation", "data_loaded") == "execute_operation"

    def test_directed_analysis_no_data_request_data(self):
        assert _action_for("directed_analysis", "no_data") == "request_data"

    def test_directed_analysis_data_loaded_run(self):
        assert _action_for("directed_analysis", "data_loaded") == "run_analysis"

    def test_comprehensive_report_no_data_request_data(self):
        assert _action_for("comprehensive_report", "no_data") == "request_data"

    def test_comprehensive_report_data_loaded_generate(self):
        assert _action_for("comprehensive_report", "data_loaded") == "synthesize_analysis"

    def test_unknown_intent_returns_guide(self):
        assert _action_for("something_else", "no_data") == "guide_analysis"


# ══════════════════════════════════════════════════════════════
# 5. _LEGACY_INTENT_MAP backward compatibility
# ══════════════════════════════════════════════════════════════

class TestLegacyIntentMap:

    def test_all_legacy_keys_mapped(self):
        expected_keys = {"chat", "operation", "analysis_guidance", "data_requirement", "direct_analysis", "report"}
        assert set(_LEGACY_INTENT_MAP.keys()) == expected_keys

    def test_legacy_mappings_target_valid_intents(self):
        valid = {
            "simple_response", "knowledge_qa", "analysis_consultation",
            "result_followup", "intent_negotiation", "data_requirement",
            "data_operation", "directed_analysis", "comprehensive_report",
        }
        for v in _LEGACY_INTENT_MAP.values():
            assert v in valid

    def test_specific_mappings(self):
        assert _LEGACY_INTENT_MAP["chat"] == "simple_response"
        assert _LEGACY_INTENT_MAP["operation"] == "data_operation"
        assert _LEGACY_INTENT_MAP["analysis_guidance"] == "analysis_consultation"
        assert _LEGACY_INTENT_MAP["data_requirement"] == "data_requirement"
        assert _LEGACY_INTENT_MAP["direct_analysis"] == "directed_analysis"
        assert _LEGACY_INTENT_MAP["report"] == "comprehensive_report"


# ══════════════════════════════════════════════════════════════
# 6. _PROMPT_LEVEL_MAP correctness
# ══════════════════════════════════════════════════════════════

class TestPromptLevelMap:

    def test_covers_all_nine_intents(self):
        all_intents = {
            "simple_response", "knowledge_qa", "analysis_consultation",
            "result_followup", "intent_negotiation", "data_requirement",
            "data_operation", "directed_analysis", "comprehensive_report",
        }
        assert set(_PROMPT_LEVEL_MAP.keys()) == all_intents

    @pytest.mark.parametrize("intent_type", [
        "simple_response", "knowledge_qa", "analysis_consultation", "result_followup",
    ])
    def test_conversation_level(self, intent_type):
        assert _PROMPT_LEVEL_MAP[intent_type] == "conversation"

    @pytest.mark.parametrize("intent_type", ["intent_negotiation", "data_requirement"])
    def test_guidance_level(self, intent_type):
        assert _PROMPT_LEVEL_MAP[intent_type] == "guidance"

    def test_data_operation_quick(self):
        assert _PROMPT_LEVEL_MAP["data_operation"] == "quick"

    @pytest.mark.parametrize("intent_type", ["directed_analysis", "comprehensive_report"])
    def test_analysis_level(self, intent_type):
        assert _PROMPT_LEVEL_MAP[intent_type] == "analysis"

    def test_values_in_valid_set(self):
        valid_levels = {"conversation", "quick", "guidance", "analysis"}
        for v in _PROMPT_LEVEL_MAP.values():
            assert v in valid_levels


# ══════════════════════════════════════════════════════════════
# 7. Edge cases: empty, whitespace, very short input
# ══════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_empty_string(self):
        result = plan_turn_intent("", NO_DATA_CTX)
        assert result.intent_type == "simple_response"
        assert result.clarity == "clear"

    def test_whitespace_only(self):
        result = plan_turn_intent("   ", NO_DATA_CTX)
        assert result.intent_type == "simple_response"

    def test_very_short_input_two_chars(self):
        result = plan_turn_intent("ab", NO_DATA_CTX)
        assert result.intent_type == "simple_response"
        assert result.reason == "短输入或确认语"

    def test_very_short_input_single_char(self):
        result = plan_turn_intent("x", DATA_LOADED_CTX)
        assert result.intent_type == "simple_response"

    def test_none_like_input(self):
        """plan_turn_intent treats empty/falsy as simple_response."""
        result = plan_turn_intent("", DATA_LOADED_CTX)
        assert result.intent_type == "simple_response"

    def test_whitespace_with_data_loaded(self):
        result = plan_turn_intent("  \t ", DATA_LOADED_CTX)
        assert result.intent_type == "simple_response"
        assert result.data_state == "data_loaded"


# ══════════════════════════════════════════════════════════════
# 8. simple_response intent
# ══════════════════════════════════════════════════════════════

class TestSimpleResponse:

    @pytest.mark.parametrize("text", [
        "你好", "hello", "hi", "谢谢", "thanks",
    ])
    def test_greetings_and_thanks(self, text):
        result = plan_turn_intent(text, NO_DATA_CTX)
        assert result.intent_type == "simple_response"
        assert result.recommended_action == "answer_directly"

    @pytest.mark.parametrize("text", [
        "好的", "明白", "了解了", "ok", "继续", "没问题",
    ])
    def test_confirmations(self, text):
        result = plan_turn_intent(text, NO_DATA_CTX)
        assert result.intent_type == "simple_response"

    def test_greeting_with_data_loaded(self):
        result = plan_turn_intent("hello", DATA_LOADED_CTX)
        assert result.intent_type == "simple_response"
        assert result.data_state == "data_loaded"


# ══════════════════════════════════════════════════════════════
# 9. knowledge_qa intent
# ══════════════════════════════════════════════════════════════

class TestKnowledgeQA:

    @pytest.mark.parametrize("text", [
        "什么是回归分析",
        "是什么原因导致异常",
        "解释一下p值",
        "what is standard deviation",
        "explain overfitting",
        "describe A/B testing",
    ])
    def test_knowledge_qa_prefixes(self, text):
        result = plan_turn_intent(text, NO_DATA_CTX)
        assert result.intent_type == "knowledge_qa"
        assert result.recommended_action == "answer_directly"

    def test_knowledge_qa_with_data_loaded(self):
        result = plan_turn_intent("什么是相关系数", DATA_LOADED_CTX)
        assert result.intent_type == "knowledge_qa"
        assert result.data_state == "data_loaded"


# ══════════════════════════════════════════════════════════════
# 10. analysis_consultation intent
# ══════════════════════════════════════════════════════════════

class TestAnalysisConsultation:

    @pytest.mark.parametrize("text", [
        "怎么分析这份数据比较好",
        "如何分析用户留存",
        "分析方法有哪些",
        "应该用什么模型",
        "how to analyze this dataset",
        "which method should I use",
    ])
    def test_consultation_keywords(self, text):
        result = plan_turn_intent(text, NO_DATA_CTX)
        assert result.intent_type == "analysis_consultation"
        assert result.recommended_action == "answer_directly"
        assert result.clarity == "clear"


# ══════════════════════════════════════════════════════════════
# 11. result_followup intent
# ══════════════════════════════════════════════════════════════

class TestResultFollowup:

    @pytest.mark.parametrize("text", [
        "为什么说这个趋势是显著的",
        "这个结论可靠吗",
        "怎么得出这个结果的",
        "能解释一下这个p值吗",
        "这个结果说明什么",
    ])
    def test_followup_keywords(self, text):
        result = plan_turn_intent(text, DATA_LOADED_CTX)
        assert result.intent_type == "result_followup"
        assert result.recommended_action == "answer_directly"
        assert result.clarity == "clear"


# ══════════════════════════════════════════════════════════════
# 12. comprehensive_report intent
# ══════════════════════════════════════════════════════════════

class TestComprehensiveReport:

    @pytest.mark.parametrize("text", [
        "报告",
        "完整分析",
        "综合分析",
        "出个报告",
        "给我一份报告",
        "full report",
        "comprehensive analysis",
        "complete analysis report",
    ])
    def test_report_keywords_no_data(self, text):
        result = plan_turn_intent(text, NO_DATA_CTX)
        assert result.intent_type == "comprehensive_report"
        assert result.data_state == "no_data"
        assert result.recommended_action == "request_data"
        assert result.analysis_stage == "scope"

    @pytest.mark.parametrize("text", [
        "报告",
        "分析报告",
        "完整报告",
        "full report",
    ])
    def test_report_keywords_with_data(self, text):
        result = plan_turn_intent(text, DATA_LOADED_CTX)
        assert result.intent_type == "comprehensive_report"
        assert result.data_state == "data_loaded"
        assert result.recommended_action == "synthesize_analysis"
        assert result.analysis_stage == "report"

    def test_short_report_keyword_chinese(self):
        """The single keyword '报告' must classify as report even though len < 3
        because report check happens before the short-input check."""
        result = plan_turn_intent("报告", NO_DATA_CTX)
        assert result.intent_type == "comprehensive_report"

    def test_short_report_keyword_data_loaded(self):
        result = plan_turn_intent("报告", DATA_LOADED_CTX)
        assert result.intent_type == "comprehensive_report"
        assert result.recommended_action == "synthesize_analysis"

    def test_report_with_file_reference_is_pending_load(self):
        result = plan_turn_intent("Create a full report from orders.csv", NO_DATA_CTX)

        assert result.intent_type == "comprehensive_report"
        assert result.execution_readiness == "pending_load"
        assert result.recommended_action == "load_then_analyze"
        assert result.analysis_stage == "scope"


# ══════════════════════════════════════════════════════════════
# 13. data_requirement intent
# ══════════════════════════════════════════════════════════════

class TestDataRequirement:

    @pytest.mark.parametrize("text", [
        "需要哪些数据",
        "要哪些数据",
        "准备哪些数据",
        "什么数据能做这个分析",
        "没有数据怎么办",
        "what data do I need",
        "which data is required",
        "need data for analysis",
    ])
    def test_requirement_keywords(self, text):
        result = plan_turn_intent(text, NO_DATA_CTX)
        assert result.intent_type == "data_requirement"
        assert result.recommended_action == "request_data"

    def test_hypothetical_csv_preparation_question_is_data_requirement(self):
        text = "What csv files should I prepare if I want to analyze revenue decline?"

        result = plan_turn_intent(text, NO_DATA_CTX)

        assert result.intent_type == "data_requirement"
        assert result.execution_readiness == "missing_data"
        assert result.recommended_action == "request_data"


# ══════════════════════════════════════════════════════════════
# 14. data_operation intent (only without analysis keywords)
# ══════════════════════════════════════════════════════════════

class TestDataOperation:

    @pytest.mark.parametrize("text", [
        "汇总一下数据",
        "导出csv",
        "筛选出金额大于100的",
        "排序按日期",
        "重命名列名",
        "按月分组",
        "计算总和",
        "select all records",
        "filter by date",
        "export to csv",
        "sort by revenue",
    ])
    def test_pure_operation_keywords(self, text):
        result = plan_turn_intent(text, NO_DATA_CTX)
        assert result.intent_type == "data_operation"
        assert result.recommended_action == "execute_operation"

    def test_operation_not_triggered_with_analysis_keyword(self):
        """Operation keywords co-present with analysis keywords should NOT
        produce data_operation."""
        text = "分析一下趋势并汇总"  # contains both "分析" and "汇总"
        result = plan_turn_intent(text, DATA_LOADED_CTX)
        # "分析" is in _ANALYSIS_KEYWORDS, so this should be directed_analysis
        assert result.intent_type != "data_operation"

    def test_operation_with_data_loaded(self):
        result = plan_turn_intent("导出数据", DATA_LOADED_CTX)
        assert result.intent_type == "data_operation"
        assert result.data_state == "data_loaded"


# ══════════════════════════════════════════════════════════════
# 15. directed_analysis intent
# ══════════════════════════════════════════════════════════════

class TestDirectedAnalysis:

    @pytest.mark.parametrize("text", [
        "最近三个月的收入趋势如何",
        "对比两个渠道的表现",
        "为什么用户增长下降了",
        "预测下个季度的营收",
        "异常值检测",
        "这份数据的趋势分析",
        "evaluate the ROI of this campaign",
        "analyze the correlation between variables",
        "is this worth continuing",
    ])
    def test_analysis_keywords_with_data(self, text):
        result = plan_turn_intent(text, DATA_LOADED_CTX)
        # "analyze" removed from _ANALYSIS_KEYWORDS; may fall to LLM fallback
        assert result.intent_type in ("directed_analysis", "intent_negotiation")
        assert result.recommended_action == "run_analysis"
        assert result.data_state == "data_loaded"

    @pytest.mark.parametrize("text", [
        "趋势分析",
        "对比分析",
        "原因分析",
    ])
    def test_analysis_keywords_no_data_redirect(self, text):
        result = plan_turn_intent(text, NO_DATA_CTX)
        assert result.intent_type == "directed_analysis"
        assert result.execution_readiness == "missing_data"
        assert result.recommended_action == "request_data"

    def test_clear_analysis_with_file_paths_is_pending_load_directed_analysis(self):
        text = (
            "Please analyze revenue decline and retention change in these files:\n"
            "D:\\Project\\Daily\\data\\orders.xlsx\n"
            "D:\\Project\\Daily\\data\\payments.csv\n"
            "Focus on trend, driver decomposition, and limitations."
        )

        result = plan_turn_intent(text, NO_DATA_CTX)

        assert result.intent_type == "directed_analysis"
        assert result.clarity == "clear"
        assert result.data_state == "no_data"
        assert result.execution_readiness == "pending_load"
        assert result.recommended_action == "load_then_analyze"

    def test_clear_analysis_without_data_source_is_missing_data(self):
        result = plan_turn_intent("Analyze why revenue declined by channel", NO_DATA_CTX)

        assert result.intent_type == "directed_analysis"
        assert result.execution_readiness == "missing_data"
        assert result.recommended_action == "request_data"

    def test_evaluate_keyword(self):
        result = plan_turn_intent("evaluate the model performance", DATA_LOADED_CTX)
        assert result.intent_type == "directed_analysis"

    def test_analyze_keyword(self):
        # "analyze" removed from _ANALYSIS_KEYWORDS to avoid blocking guidance.
        # Without a specific analysis direction keyword, falls to LLM or guidance.
        result = plan_turn_intent("analyze the revenue data", DATA_LOADED_CTX)
        assert result.intent_type in ("directed_analysis", "intent_negotiation")

    def test_worth_keyword(self):
        result = plan_turn_intent("is this product worth investing in", DATA_LOADED_CTX)
        assert result.intent_type == "directed_analysis"


# ══════════════════════════════════════════════════════════════
# 16. intent_negotiation / data_requirement via guidance keywords
# ══════════════════════════════════════════════════════════════

class TestGuidanceBranching:

    def test_guidance_data_loaded_becomes_intent_negotiation(self):
        """When data is loaded, guidance keywords -> intent_negotiation."""
        result = plan_turn_intent("帮我看看这份数据", DATA_LOADED_CTX)
        assert result.intent_type == "intent_negotiation"
        assert result.recommended_action == "guide_analysis"
        assert result.clarity == "clear"

    def test_guidance_no_data_becomes_data_requirement(self):
        """When no data, guidance keywords -> data_requirement."""
        result = plan_turn_intent("帮我看看这份数据", NO_DATA_CTX)
        assert result.intent_type == "data_requirement"
        assert result.recommended_action == "request_data"

    def test_guidance_keyword_with_analysis_keyword_not_guidance(self):
        """Guidance keywords co-present with analysis keywords should not
        trigger the guidance branch; they fall through to the analysis branch."""
        # "分析" is in both _ANALYSIS_KEYWORDS and "分析一下" in _GUIDANCE_KEYWORDS
        # The code checks guidance ONLY when no analysis keywords present
        result = plan_turn_intent("分析一下趋势", DATA_LOADED_CTX)
        assert result.intent_type == "directed_analysis"

    def test_guidance_keyword_without_analysis_keyword(self):
        result = plan_turn_intent("看看数据有什么", DATA_LOADED_CTX)
        # "看看数据" is in _GUIDANCE_KEYWORDS, no analysis keyword present
        assert result.intent_type == "intent_negotiation"


# ══════════════════════════════════════════════════════════════
# 17. data_loaded vs no_data state propagation
# ══════════════════════════════════════════════════════════════

class TestDataStatePropagation:

    def test_no_data_state(self):
        result = plan_turn_intent("你好", NO_DATA_CTX)
        assert result.data_state == "no_data"

    def test_data_loaded_state(self):
        result = plan_turn_intent("你好", DATA_LOADED_CTX)
        assert result.data_state == "data_loaded"

    def test_directed_analysis_different_actions_by_data(self):
        r_no = plan_turn_intent("趋势分析", NO_DATA_CTX)
        r_yes = plan_turn_intent("趋势分析", DATA_LOADED_CTX)
        assert r_no.recommended_action == "request_data"
        assert r_yes.recommended_action == "run_analysis"

    @patch("data_agent.agent.intent._try_llm_classify", return_value=None)
    def test_default_fallback_data_loaded(self, _mock):
        """Unclassified input with data_loaded falls to analysis_consultation."""
        result = plan_turn_intent("something completely unknown xyz", DATA_LOADED_CTX)
        # No rule matches, LLM returns None -> default fallback
        assert result.data_state == "data_loaded"
        assert result.intent_type == "analysis_consultation"
        assert result.recommended_action == "guide_analysis"

    @patch("data_agent.agent.intent._try_llm_classify", return_value=None)
    def test_default_fallback_no_data(self, _mock):
        """Unclassified input without data falls to intent_negotiation."""
        result = plan_turn_intent("something completely unknown xyz", NO_DATA_CTX)
        assert result.data_state == "no_data"
        assert result.intent_type == "intent_negotiation"
        assert result.recommended_action == "ask_question"


# ══════════════════════════════════════════════════════════════
# 18. LLM fallback via mock
# ══════════════════════════════════════════════════════════════

class TestLLMFallback:

    @patch("data_agent.agent.intent._try_llm_classify")
    def test_llm_returns_intent(self, mock_llm):
        """When rule path does not match and LLM returns a result, use it."""
        mock_llm.return_value = ("knowledge_qa", [])
        result = plan_turn_intent("something completely unknown xyz", NO_DATA_CTX)
        assert result.intent_type == "knowledge_qa"
        assert result.reason == "LLM语义分类"

    @patch("data_agent.agent.intent._try_llm_classify")
    def test_llm_returns_with_ambiguities(self, mock_llm):
        mock_llm.return_value = (
            "directed_analysis",
            [{"kind": "ambiguous_scope", "detail": "trend or comparison"}],
        )
        result = plan_turn_intent("something completely unknown xyz", DATA_LOADED_CTX)
        assert result.intent_type == "directed_analysis"
        assert result.clarity == "vague"
        assert len(result.ambiguities) == 1
        assert result.ambiguities[0]["kind"] == "ambiguous_scope"

    @patch("data_agent.agent.intent._try_llm_classify")
    def test_llm_returns_none_falls_to_default(self, mock_llm):
        mock_llm.return_value = None
        result = plan_turn_intent("something completely unknown xyz", NO_DATA_CTX)
        # Falls to the default fallback path
        assert result.intent_type == "intent_negotiation"
        assert result.reason == "默认按分析咨询处理"

    @patch("data_agent.agent.intent._try_llm_classify")
    def test_llm_not_called_when_rule_matches(self, mock_llm):
        """The LLM should not be invoked when the rule-based path succeeds."""
        plan_turn_intent("什么是回归", NO_DATA_CTX)
        mock_llm.assert_not_called()

    @patch("data_agent.agent.intent._try_llm_classify")
    def test_llm_stage_and_action_derived_correctly(self, mock_llm):
        mock_llm.return_value = ("comprehensive_report", [])
        result = plan_turn_intent("xyzzy unseen input", DATA_LOADED_CTX)
        assert result.analysis_stage == "report"
        assert result.recommended_action == "synthesize_analysis"


# ══════════════════════════════════════════════════════════════
# 19. Case insensitivity
# ══════════════════════════════════════════════════════════════

class TestCaseInsensitivity:

    def test_uppercase_greeting(self):
        result = plan_turn_intent("HELLO", NO_DATA_CTX)
        assert result.intent_type == "simple_response"

    def test_uppercase_report(self):
        result = plan_turn_intent("FULL REPORT", DATA_LOADED_CTX)
        assert result.intent_type == "comprehensive_report"

    def test_mixed_case_filter(self):
        result = plan_turn_intent("Filter the data", DATA_LOADED_CTX)
        assert result.intent_type == "data_operation"


# ══════════════════════════════════════════════════════════════
# 20. Priority / ordering checks
# ══════════════════════════════════════════════════════════════

class TestPriorityOrdering:

    def test_report_beats_short_input(self):
        """Report check comes before the short-input check."""
        # "报告" is 2 chars (< 3), but should be report, not simple_response
        result = plan_turn_intent("报告", NO_DATA_CTX)
        assert result.intent_type == "comprehensive_report"

    def test_report_beats_confirmation(self):
        # "完整报告" is 4 chars, contains "报告"
        result = plan_turn_intent("完整报告", NO_DATA_CTX)
        assert result.intent_type == "comprehensive_report"

    def test_knowledge_qa_beats_analysis(self):
        """Knowledge QA prefixes checked before analysis keywords."""
        result = plan_turn_intent("什么是趋势分析", NO_DATA_CTX)
        assert result.intent_type == "knowledge_qa"

    def test_consultation_beats_analysis(self):
        """Analysis consultation checked before analysis keywords."""
        result = plan_turn_intent("怎么分析趋势", NO_DATA_CTX)
        assert result.intent_type == "analysis_consultation"

    def test_data_requirement_beats_operation(self):
        """Data requirement keywords checked before operation."""
        result = plan_turn_intent("需要什么数据来汇总", NO_DATA_CTX)
        assert result.intent_type == "data_requirement"

    def test_operation_not_triggered_with_analysis(self):
        """When both operation and analysis keywords present, analysis wins."""
        result = plan_turn_intent("按月分析趋势", DATA_LOADED_CTX)
        assert result.intent_type == "directed_analysis"

    def test_guidance_suppressed_when_analysis_keyword_present(self):
        """When guidance text also contains a directional analysis keyword,
        the directional keyword takes precedence."""
        # "帮我分析收入趋势" has both guidance ("帮我分析") and analysis ("趋势") keywords
        result = plan_turn_intent("帮我分析收入趋势", DATA_LOADED_CTX)
        assert result.intent_type == "directed_analysis"

        # "分析一下" (no direction) should now go to intent_negotiation
        # since "分析" was removed from _ANALYSIS_KEYWORDS
        result2 = plan_turn_intent("分析一下", DATA_LOADED_CTX)
        assert result2.intent_type == "intent_negotiation"
