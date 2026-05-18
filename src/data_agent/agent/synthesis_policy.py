"""Deterministic synthesis policy selection.

This module converts intent, analysis state, and user constraints into a small
instruction contract for final-answer synthesis. It intentionally uses only
local rules so identical inputs produce identical output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape as html_escape
from typing import Any


@dataclass(frozen=True)
class SynthesisPolicy:
    answer_mode: str
    insight_depth: str
    business_translation: str
    risk_boundary: str
    required_moves: list[str]
    suppressed_moves: list[str]
    wording_style: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def derive_synthesis_policy(
    intent: Any = None,
    state: Any = None,
    user_input: str = "",
    data_profile: Any = None,
    tool_error_count: int = 0,
    user_requirements: Any = None,
    proficiency: str | None = None,
    analysis_spec: dict[str, Any] | None = None,
    evidence_records: list[dict[str, Any]] | None = None,
    **_: Any,
) -> SynthesisPolicy:
    """Derive a deterministic answer synthesis policy.

    Parameters accept concrete repository objects or plain dictionaries. Extra
    keyword arguments are ignored for forward compatibility with pipeline calls.
    """

    text = _join_text(user_input, user_requirements)
    profile_text = _text(data_profile)
    intent_type = _get(intent, "intent_type", "")
    action = _get(intent, "recommended_action", "")
    spec = analysis_spec if analysis_spec is not None else (_get(state, "analysis_spec", None) or {})
    evidence = evidence_records if evidence_records is not None else (_get(state, "evidence_records", None) or [])
    evidence = list(evidence or [])
    wording_style = _wording_style(proficiency)

    if _is_terse(text) or _is_direct_intent(intent_type, action):
        return SynthesisPolicy(
            answer_mode="direct",
            insight_depth="none",
            business_translation="not_applicable",
            risk_boundary="descriptive",
            required_moves=["core_answer"],
            suppressed_moves=["business_meaning", "assumptions"],
            wording_style=wording_style,
            reason="Direct or terse request; suppressing business translation.",
        )

    if not evidence:
        return SynthesisPolicy(
            answer_mode="exploratory",
            insight_depth="none",
            business_translation="not_applicable",
            risk_boundary="descriptive",
            required_moves=["core_answer", "limitation", "next_step"],
            suppressed_moves=["business_meaning", "decision_recommendation"],
            wording_style=wording_style,
            reason="No evidence records are available, so synthesis stays exploratory.",
        )

    advisory = _is_advisory_request(text, profile_text, intent_type)
    uncertain = _has_low_confidence(evidence) or _is_uncertain_context(text, profile_text, spec)
    reasons: list[str] = []
    if advisory:
        reasons.append("advisory or predictive request")
    if uncertain:
        reasons.append("low confidence or high uncertainty")
    if tool_error_count >= 2:
        reasons.append(f"{tool_error_count} tool errors")

    if advisory:
        required_moves = [
            "core_answer",
            "evidence",
            "method_note",
            "assumptions",
            "limitation",
            "business_meaning",
            "next_step",
        ]
        return SynthesisPolicy(
            answer_mode="advisory",
            insight_depth="standard",
            business_translation="cautious",
            risk_boundary="predictive",
            required_moves=required_moves,
            suppressed_moves=[],
            wording_style=wording_style,
            reason=_reason(reasons, "Evidence supports a cautious advisory synthesis."),
        )

    required_moves = [
        "core_answer",
        "evidence",
        "method_note",
        "limitation",
        "business_meaning",
        "next_step",
    ]
    if uncertain and "assumptions" not in required_moves:
        required_moves.insert(3, "assumptions")

    return SynthesisPolicy(
        answer_mode="analytical",
        insight_depth="light",
        business_translation="cautious",
        risk_boundary="descriptive",
        required_moves=required_moves,
        suppressed_moves=["decision_recommendation"],
        wording_style=wording_style,
        reason=_reason(reasons, "Evidence supports a light analytical synthesis."),
    )


def build_synthesis_instruction(policy: SynthesisPolicy) -> str:
    """Format a compact XML-like instruction block for prompt assembly."""

    answer_mode = _escape_prompt_value(policy.answer_mode, quote=True)
    insight_depth = _escape_prompt_value(policy.insight_depth, quote=True)
    business_translation = _escape_prompt_value(policy.business_translation, quote=True)
    risk_boundary = _escape_prompt_value(policy.risk_boundary, quote=True)
    wording_style = _escape_prompt_value(policy.wording_style, quote=True)
    required = ",".join(_escape_prompt_value(move) for move in policy.required_moves)
    suppressed = ",".join(_escape_prompt_value(move) for move in policy.suppressed_moves)
    reason = _escape_prompt_value(policy.reason)
    return (
        "<synthesis_policy "
        f'answer_mode="{answer_mode}" '
        f'insight_depth="{insight_depth}" '
        f'business_translation="{business_translation}" '
        f'risk_boundary="{risk_boundary}" '
        f'wording_style="{wording_style}">'
        f"<required_moves>{required}</required_moves>"
        f"<suppressed_moves>{suppressed}</suppressed_moves>"
        f"<reason>{reason}</reason>"
        "</synthesis_policy>"
    )


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    return str(value).lower()


def _join_text(*values: Any) -> str:
    return " ".join(_text(value) for value in values if value is not None).strip()


def _is_direct_intent(intent_type: str, action: str) -> bool:
    return intent_type in {"simple_response", "data_operation"} or action in {
        "answer_directly",
        "execute_operation",
    }


def _is_terse(text: str) -> bool:
    terse_markers = (
        "formula only",
        "no explanation",
        "just the formula",
        "only answer",
        "answer only",
        "terse",
        "brief",
    )
    return any(marker in text for marker in terse_markers)


def _is_advisory_request(text: str, profile_text: str, intent_type: str) -> bool:
    advisory_markers = (
        "advis",
        "recommend",
        "decision",
        "should we",
        "worth",
        "ltv",
        "lifetime value",
        "forecast",
        "predict",
        "projection",
        "estimate future",
    )
    if intent_type == "comprehensive_report":
        return True
    combined = f"{text} {profile_text}"
    return any(marker in combined for marker in advisory_markers)


def _has_low_confidence(evidence: list[Any]) -> bool:
    low_markers = {"low", "weak", "uncertain", "medium_low"}
    for record in evidence:
        confidence = _text(_get(record, "confidence", None))
        if any(marker in confidence for marker in low_markers):
            return True
    return False


def _is_uncertain_context(text: str, profile_text: str, spec: Any) -> bool:
    combined = f"{text} {profile_text} {_text(spec)}"
    uncertainty_markers = (
        "uncertain",
        "sparse",
        "missing",
        "no revenue",
        "assumption",
    )
    return any(marker in combined for marker in uncertainty_markers)


def _wording_style(proficiency: str | None) -> str:
    level = (proficiency or "").lower().strip()
    if level in {"beginner", "novice", "nontechnical", "non-technical"}:
        return "plain_language"
    if level in {"advanced", "expert", "technical"}:
        return "technical_concise"
    return "balanced"


def _reason(reasons: list[str], fallback: str) -> str:
    if not reasons:
        return fallback
    return f"{fallback} Triggered by: {', '.join(reasons)}."


def _escape_prompt_value(value: Any, *, quote: bool = False) -> str:
    return html_escape(str(value), quote=quote)
