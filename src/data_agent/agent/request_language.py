"""Conservative local negation handling for deterministic keyword rules.

This is not intent inference. Ambiguous wording still matches; only explicit
local prohibitions remove keywords from a deterministic rule.
"""
from __future__ import annotations

import re


_NEGATION = re.compile(
    r"不要|不得|不做|不作|不能(?!排除|否认)|不应|不支持|不输出|不解释|不把|"
    r"不需要|无需|无须|避免|禁止|并非|不是|"
    r"不算|不计算|不分析|不统计|不预测|不估算|"
    r"\b(?:do not|don't|must not|should not|cannot|without|avoid|no|not)\b",
    re.IGNORECASE,
)
_BOUNDARY = re.compile(r"[，,、。；;！？!?\n]|但是|然而|\b(?:but|however)\b", re.IGNORECASE)


def has_affirmative_keyword(text: str, keywords) -> bool:
    for keyword in keywords:
        pattern = re.escape(keyword)
        if keyword.isascii() and keyword[0].isalpha():
            pattern = r"\b" + pattern + r"\b"
        for match in re.finditer(pattern, text, re.IGNORECASE):
            prefix = _BOUNDARY.split(text[:match.start()])[-1][-60:]
            negations = list(_NEGATION.finditer(prefix))
            # 紧邻前缀的“不/没/无”在分句截断后仍构成否定（如“不预测”）。
            immediately_preceded = (
                match.start() > 0 and text[match.start() - 1] in "不没无"
            )
            if immediately_preceded and not negations:
                negations = ["immediate"]
            # Double negation is ambiguous, so retain the safety gate.
            if len(negations) != 1:
                return True
    return False


def keyword_negation_state(text: str, keyword: str) -> str:
    """Tri-state presence of one keyword: affirmative / negated / ambiguous / absent.

    Unlike ``has_affirmative_keyword`` (a boolean safety gate where ambiguity
    counts as present), this reports the actual state so intent routing can
    defer genuinely contradictory input to the semantic layer instead of
    forcing a confident label.
    """
    pattern = re.escape(keyword)
    if keyword.isascii() and keyword[0].isalpha():
        pattern = r"\b" + pattern + r"\b"
    for match in re.finditer(pattern, text, re.IGNORECASE):
        prefix = _BOUNDARY.split(text[:match.start()])[-1][-60:]
        negations = list(_NEGATION.finditer(prefix))
        if len(negations) == 1:
            return "negated"
        if len(negations) > 1:
            return "ambiguous"
        return "affirmative"
    return "absent"


def keyword_group_state(text: str, keywords) -> str:
    """Aggregate tri-state over a keyword group.

    Precedence: affirmative > ambiguous > negated > absent. A single
    affirmative occurrence is enough to treat the request as present; any
    ambiguous occurrence without an affirmative one defers rather than
    guessing.
    """
    states = [keyword_negation_state(text, keyword) for keyword in keywords]
    if "affirmative" in states:
        return "affirmative"
    if "ambiguous" in states:
        return "ambiguous"
    if "negated" in states:
        return "negated"
    return "absent"
