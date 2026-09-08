"""IC3: method selection keeps the user's main goal and respects negation.

M-series from the intent-clarification acceptance matrix: negated sub-goals
must not hijack the primary playbook (M03/M06), single-metric requests must
keep their concrete playbook (M04), and selection provenance is recorded
without claiming failures that did not happen (O01/O02).
"""

from unittest.mock import patch

from data_agent.agent.intent import TurnIntent
from data_agent.agent.method_playbooks import choose_playbook


def _intent():
    return TurnIntent(
        intent_type="directed_analysis",
        clarity="clear",
        data_state="data_loaded",
        analysis_stage="execute",
        recommended_action="run_analysis",
        execution_readiness="ready",
    )


def _no_llm(**_kwargs):
    return None


class TestNegationAndGoalPriority:

    @patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm)
    def test_m03_negated_retention_does_not_hijack_revenue_goal(self):
        selection = choose_playbook(
            "不要分析留存，只分析省钱卡的收益构成", _intent(), has_data=True,
        )

        assert selection.primary_playbook_id != "retention_lifecycle"
        assert selection.primary_playbook_id in {
            "revenue_profitability", "product_feature_analysis", "effect_evaluation",
        }

    @patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm)
    def test_m06_curve_fit_without_prediction_is_not_forecast(self):
        selection = choose_playbook(
            "拟合当前留存曲线，不预测 D30", _intent(), has_data=True,
        )

        assert selection.primary_playbook_id != "forecast_decision_simulation"

    @patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm)
    def test_m04_single_repurchase_request_keeps_concrete_playbook(self):
        selection = choose_playbook(
            "仅计算复购率，口径为购卡用户在 30 天内的再次购买占比", _intent(), has_data=True,
        )

        # 单一明确指标：不被强制升级为综合留存/流失建模
        assert selection.primary_playbook_id != "forecast_decision_simulation"
        assert selection.analysis_spec is not None or selection.primary_playbook_id

    @patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm)
    def test_m01_composite_savings_card_goal_not_narrowed(self):
        selection = choose_playbook(
            "分析省钱卡的功能效果、收益、复购和付费行为", _intent(), has_data=True,
        )

        # 综合功能/效果请求：主方法应是功能/效果/收益主线，而不是留存细分
        assert selection.primary_playbook_id in {
            "product_feature_analysis", "effect_evaluation", "revenue_profitability",
            "user_behavior_analysis",
        }
        # 子目标（收益/复购/行为）不因主方法选择而丢失
        joined = " ".join(selection.supporting_playbook_ids) + " " + selection.primary_playbook_id
        assert "revenue" in joined.lower() or "behavior" in joined.lower() or "effect" in joined.lower()


class TestSelectionProvenance:

    def test_o01_llm_primary_with_rule_supporting_is_a_legal_combination(self):
        def fake_llm(**_kwargs):
            return {"primary": "revenue_profitability", "supporting": []}

        with patch("data_agent.agent.llm_playbook.select_playbook_llm", fake_llm):
            selection = choose_playbook(
                "评估省钱卡的最终收益与复购情况", _intent(), has_data=True,
            )

        assert selection.primary_source == "llm"
        # 空 supporting 由规则补充是合法组合（O01）
        assert selection.supporting_playbook_ids
        assert selection.supporting_source == "rule"

    @patch("data_agent.agent.llm_playbook.select_playbook_llm", _no_llm)
    def test_o02_keyword_fallback_does_not_claim_llm(self):
        selection = choose_playbook("分析收益", _intent(), has_data=True)

        assert selection.primary_source in {"keyword", "default"}
        assert selection.primary_source != "llm"
