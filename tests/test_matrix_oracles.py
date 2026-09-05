# tests/test_matrix_oracles.py
from scripts.acceptance.matrix_oracles import (
    OBSERVER_GAP_CHECKS, ORACLE_VERSION, zero_semantics_violations,
)

PUBLISHED_OK = (
    "首个 30 天窗口内未观测到的用户记为右删失：因未满 30 天出现结构性 0=右删失，"
    "系统判定为删失而非真实 0，不代表用户流失。拟合 R²=0.98，不可外推超出观测窗口。"
)
DOMAIN_CLAIM = "这属于游戏行业典型的幂律区间，收入必然向头部集中。"
CAUSAL_CLAIM = "发放代金券导致付费提升 12%，因此应扩大投放。"


def test_censoring_statements_are_allowed():
    assert zero_semantics_violations(PUBLISHED_OK) == []


def test_unsourced_domain_claim_is_flagged():
    violations = zero_semantics_violations(DOMAIN_CLAIM)
    assert violations and "游戏行业典型的幂律区间" in violations[0]


def test_unqualified_causal_claim_is_flagged():
    violations = zero_semantics_violations(CAUSAL_CLAIM)
    assert violations and "导致" in violations[0]


def test_version_and_observer_gaps_declared():
    assert ORACLE_VERSION == "2026-09-05.1"
    assert "within_30s_completion_observation" in OBSERVER_GAP_CHECKS
