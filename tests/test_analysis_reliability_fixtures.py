import pytest

from tests.fixtures.analysis_reliability import (
    build_aggregate_payment_frame,
    build_factor_relationship_frame,
    factor_relationship_prompt,
)
from tests.replay_assertions import assert_reliable_analysis_trace


def test_factor_fixture_is_deterministic_32_by_21():
    left = build_factor_relationship_frame()
    right = build_factor_relationship_frame()
    assert left.shape == (32, 21)
    assert left.equals(right)
    assert {"目标值", "活跃度", "价格", "渠道", "日期"} <= set(left.columns)


def test_aggregate_fixture_cannot_support_user_profile_claims():
    frame = build_aggregate_payment_frame()
    assert {"日期", "订单数", "收入"} <= set(frame.columns)
    assert not {"user_id", "年龄", "用户消费金额"} & set(frame.columns)


def test_replay_prompt_asks_for_significance_without_claiming_causality():
    prompt = factor_relationship_prompt()
    assert "显著" in prompt
    assert "影响因素" in prompt
    assert "因果" not in prompt


def test_trace_contract_accepts_one_complete_reliability_trace():
    assert_reliable_analysis_trace(
        [
            {"code": "grain_and_missingness_checked"},
            {"code": "univariate_relationship_checked"},
            {"code": "multivariable_method_attempted"},
            {"code": "limitations_prepared"},
            {"completion_state": "complete"},
        ],
        require_inferential_attempt=True,
    )


def test_trace_contract_requires_an_inferential_attempt_when_requested():
    with pytest.raises(AssertionError):
        assert_reliable_analysis_trace(
            [
                {"code": "grain_and_missingness_checked"},
                {"code": "univariate_relationship_checked"},
                {"code": "limitations_prepared"},
                {"completion_state": "complete"},
            ],
            require_inferential_attempt=True,
        )


def test_trace_contract_rejects_more_than_two_repeated_failures():
    with pytest.raises(AssertionError):
        assert_reliable_analysis_trace(
            [
                {"code": "grain_and_missingness_checked"},
                {"code": "univariate_relationship_checked"},
                {"code": "limitations_prepared"},
                {"completion_state": "complete"},
                {"same_failure_attempt": 3},
            ],
            require_inferential_attempt=False,
        )
