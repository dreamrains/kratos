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
# 每一个因果措辞都要被检查：不能让第一句已限定的表述掩盖后文未限定的断言。
# 因此按措辞逐个 finditer，限定词判定窗口取该措辞所在的句子（句号/分号/问叹号
# 分隔），而不是固定长度的前后文——固定长度窗口会把上一句的限定词带入本句，
# 或在吞掉后文措辞后被整段抑制。
_CAUSAL_PATTERNS = (
    re.compile(r"导致|造成了|因此应"),
)

_SENTENCE_PATTERN = re.compile(r"[^。！？!?；;\n]+")

_QUALIFIER_MARKERS = ("可能", "或与", "相关而非因果", "关联", "在观测窗口内", "删失", "右删失")


def zero_semantics_violations(text: str) -> list[str]:
    violations: list[str] = []
    for pattern in _DOMAIN_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            violations.append(f"domain_claim: {match.group(0)}")
    sentences = [(match.start(), match.end(), match.group(0))
                 for match in _SENTENCE_PATTERN.finditer(text)]
    for pattern in _CAUSAL_PATTERNS:
        for match in pattern.finditer(text):
            window = next(sentence for start, end, sentence in sentences
                          if start <= match.start() and match.end() <= end)
            if any(marker in window for marker in _QUALIFIER_MARKERS):
                continue  # 已有限定词/删失说明的表述不属于未限定因果
            violation = f"unqualified_causal: {window}"
            if violation not in violations:  # 同一句中的多个因果措辞只报一次
                violations.append(violation)
    return violations
