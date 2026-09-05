# scripts/acceptance/matrix_oracles.py
"""Versioned, property-based oracle checks for the browser matrix.

Replaces per-batch tmp scripts whose exact-string blacklists could not
distinguish a property violation from a statistically correct statement.
"""
from __future__ import annotations

import re

ORACLE_VERSION = "2026-09-05.1"

OBSERVER_GAP_CHECKS = frozenset({"within_30s_completion_observation"})

# 统计上正确的删失/缺失语义表述：发布文本允许出现。
_CENSORING_ALLOW_PATTERNS = (
    re.compile(r"右删失"),
    re.compile(r"删失而非真实\s*0"),
    re.compile(r"结构性\s*0=右删失"),
    re.compile(r"未满\s*30\s*天出现结构性"),
)

# 属性 1：无溯源的领域断言（原 A04 黑名单条目的属性化）。
_DOMAIN_CLAIM_PATTERNS = (
    re.compile(r".{0,12}(典型的?幂律区间|行业惯例|业内公认).{0,12}"),
)

# 属性 2：未限定的因果断言（观察性数据不得声称因果）。
_CAUSAL_PATTERNS = (
    re.compile(r".{0,20}(导致|造成了|因此应).{0,20}"),
)

_QUALIFIER_MARKERS = ("可能", "或与", "相关而非因果", "关联", "在观测窗口内", "删失", "右删失")


def zero_semantics_violations(text: str) -> list[str]:
    violations: list[str] = []
    for pattern in _DOMAIN_CLAIM_PATTERNS:
        match = pattern.search(text)
        if match:
            violations.append(f"domain_claim: {match.group(0)}")
    for pattern in _CAUSAL_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        window = match.group(0)
        if any(marker in window for marker in _QUALIFIER_MARKERS):
            continue  # 已有限定词/删失说明的表述不属于未限定因果
        violations.append(f"unqualified_causal: {window}")
    return violations
