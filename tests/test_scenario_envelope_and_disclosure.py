"""P1-4: cross-clause scenario summaries, bidirectional pairing, host-rendered
disclosure.

Real failure (GLM r2 M02, session 08c2ac223941): the model's summary clause
"三族常用曲线外推到 D30 给出的结果从 0.01% 到 3.6% 甚至负值" references the
receipt families without naming them inline (they sit in the table above), so
clause-local family pairing failed and an honest answer died at the gate.

Design (2026-09-21 realignment + Codex hardening): arithmetic stays the
decisive closed-class check; range-summary clauses verify against the
receipt-computed min/max envelope; value-before-family phrasing pairs
bidirectionally; the four disclosure phrases stop being a gate requirement
because the host renders the disclosure block itself.
"""

from __future__ import annotations

import pytest

from data_agent.agent import publication_synthesis as ps


@pytest.fixture
def scope():
    return {
        "tool": "curve_fitting", "extrapolation_allowed": False,
        "observed_x_range": [1.0, 7.0], "source_dataset": "M02-retention",
        "scenario_extrapolation": {
            "status": "descriptive_fit_only", "effective_n": 7, "validation": "none",
            "models": [
                {"family": "exponential", "parameters": {"a": 0.73892193, "b": -0.28583215}, "r_squared": 0.99946726},
                {"family": "logarithmic", "parameters": {"a": 0.56522015, "b": -0.23771293}, "r_squared": 0.99519237},
                {"family": "power", "parameters": {"a": 0.67600697, "b": -0.86571711}, "r_squared": 0.85626503},
            ],
        },
    }


def _issues(text: str, scope: dict) -> list[dict]:
    return ps._extrapolation_issues(text, [scope])


class TestRangeEnvelope:
    def test_real_r2_summary_clause_publishes(self, scope):
        # Verbatim clause from the r2 rejected final answer.
        text = (
            "当前证据无法支持对 D30 的可靠估计。三族常用曲线外推到 D30 给出的结果"
            "从 **0.01% 到 3.6% 甚至负值**，分歧达两个数量级——这本身就是证据不足的直接证明。"
        )
        assert _issues(text, scope) == []

    def test_range_outside_family_envelope_still_rejects(self, scope):
        text = "三族外推到 D30 的结果从 0.01% 到 50%，分歧极大。"
        issues = _issues(text, scope)
        assert issues and issues[0]["code"] == "unbound_time_point_claim"

    def test_single_anonymous_value_outside_all_families_rejects(self, scope):
        text = "外推到 D30 约为 50%。"
        issues = _issues(text, scope)
        assert issues


class TestBidirectionalPairing:
    def test_value_before_family_pairs_correctly(self, scope):
        text = (
            "以下为拟合情景。D30 处：约 0.014%（指数）到 约 3.56%（幂律），"
            "对数给出负值故不适用。"
        )
        assert _issues(text, scope) == []

    def test_value_before_family_wrong_number_rejects(self, scope):
        text = "以下为拟合情景。D30 处：约 5%（指数）到 约 3.56%（幂律）。"
        issues = _issues(text, scope)
        assert issues


class TestDisclosureRegexesRetired:
    def test_scenario_passes_without_prose_disclosures(self, scope):
        # No 情景/R²= /未验证/敏感性 phrases anywhere: the host renders the
        # disclosure block, so the gate only enforces arithmetic.
        text = "按回执参数演算：幂律模型情景延伸 D30 约为 3.56%。"
        assert _issues(text, scope) == []

    def test_true_violation_still_rejected_without_disclosures(self, scope):
        text = "按回执参数演算：幂律模型情景延伸 D30 约为 9.9%。"
        assert _issues(text, scope)


class TestHostRenderedDisclosure:
    def test_appendix_renders_disclosure_for_scenario_sources(self):
        packet = {"sources": [{
            "receipt_id": "rcpt_1", "tool_name": "curve_fitting",
            "summary": "三族拟合（观测区间内）",
            "facts": [{"path": "effective_n", "value": 7}],
            "scenario_extrapolation": {
                "status": "descriptive_fit_only", "validation": "none",
                "models": [{"family": "power", "r_squared": 0.8563}],
            },
        }]}
        rendered = ps.render_verified_appendix(packet)
        assert "拟合情景披露" in rendered
        assert "未做留出验证" in rendered and "回测" in rendered and "外部数据验证" in rendered
        assert "敏感性" in rendered

    def test_appendix_without_scenario_sources_has_no_disclosure(self):
        packet = {"sources": [{
            "receipt_id": "rcpt_2", "tool_name": "describe_dataset",
            "summary": "描述", "facts": [],
        }]}
        rendered = ps.render_verified_appendix(packet)
        assert "拟合情景披露" not in rendered
