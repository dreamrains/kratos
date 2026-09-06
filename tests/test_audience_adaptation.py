"""P6 (D07): audience adaptation separated from proficiency (A01–A08)."""

from data_agent.agent.prompts import (
    build_system_prompt,
    detect_audience,
    detect_user_proficiency,
    resolve_proficiency,
)


def _prompt(user_input: str, proficiency: str = "intermediate", audience: str | None = None) -> str:
    effective_audience = audience if audience is not None else detect_audience(user_input)
    return build_system_prompt(
        tool_list="list_data",
        user_input=user_input,
        proficiency=proficiency,
        audience=effective_audience,
    )


class TestAudienceDetection:

    def test_a01_business_self_identification(self):
        assert detect_audience("我是业务人员，解释这些结果") == "business"
        prompt = _prompt("我是业务人员，解释这些结果")
        assert "受众适配（业务人员）" in prompt
        assert "业务含义" in prompt or "业务含义" in prompt

    def test_a02_analyst_self_identification(self):
        assert detect_audience("我是数据分析师，给方法细节") == "analyst"
        prompt = _prompt("我是数据分析师，给方法细节")
        assert "受众适配（数据分析师）" in prompt
        assert "口径" in prompt and "方法" in prompt

    def test_a03_manager_report_request(self):
        assert detect_audience("给管理层汇报这些结论") == "manager"
        prompt = _prompt("给管理层汇报这些结论")
        assert "受众适配（管理者）" in prompt
        assert "优先级" in prompt and "停止条件" in prompt

    def test_a04_shared_baseline_present_for_every_audience(self):
        audiences = ("business", "analyst", "manager", "general")
        prompts = {a: _prompt("分析收入趋势", audience=a) for a in audiences}
        baseline_markers = ("数值", "范围", "限制")
        for audience, prompt in prompts.items():
            assert "受众适配" in prompt, audience
            assert all(marker in prompt for marker in baseline_markers), audience

    def test_a05_current_turn_request_wins_over_previous(self):
        assert detect_audience("我是业务人员，解释这些结果") == "business"
        assert detect_audience("换成数据分析师视角，给出方法和误差") == "analyst"

    def test_a06_plain_language_switches_proficiency_per_turn(self):
        assert resolve_proficiency("auto", "用大白话解释这个结果", []) == "beginner"
        assert resolve_proficiency("auto", "给出 p 值、置信区间与效应量", []) == "advanced"

    def test_a07_no_identity_inferred_from_data_or_questions(self):
        assert detect_audience("分析经理带来的数据") == "general"
        assert detect_audience("什么是回归分析") == "general"

    def test_a08_mixed_request_keeps_per_turn_audience_and_shared_facts(self):
        audience = detect_audience("给管理层汇报，同时保留分析师口径")
        assert audience == "manager"
        prompt = _prompt("给管理层汇报，同时保留分析师口径")
        assert "受众适配（管理者）" in prompt
        # 共用底线保证同一事实集：分析口径信息在底线中保留
        assert "限制" in prompt

    def test_auto_proficiency_is_not_overwritten_by_detection(self):
        # D07: auto 检测值不得写回，后续轮次仍可重新检测
        assert detect_user_proficiency("用大白话", None) == "beginner"
        assert detect_user_proficiency("再看p值和置信区间", None) == "advanced"
