"""Conservative local negation handling for deterministic keyword rules.

This is not intent inference. Ambiguous wording still matches; only explicit
local prohibitions remove keywords from a deterministic rule.
"""
from __future__ import annotations

import re


_NEGATION = re.compile(
    r"不要|不得|不做|不作|不能(?!排除|否认)|不应|不支持|不输出|不解释|不把|"
    r"不需要|无需|无须|避免|禁止|并非|不是|"
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
            # Double negation is ambiguous, so retain the safety gate.
            if len(negations) != 1:
                return True
    return False
