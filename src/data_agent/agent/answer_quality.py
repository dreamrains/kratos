"""Deterministic answer-quality measurement primitives (no LLM).

Measurement-only. Extends the existing analysis-quality rubric with
answer-text claim extraction and agent-verification folding.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from data_agent.agent.analysis_quality_rubric import score_analysis_quality
from data_agent.agent.verification import verify_analysis_claims

SOFT_DIMENSIONS: dict[str, dict[str, str]] = {
    "rigor": {
        "name": "严谨与可信",
        "what": "结论可辩护、证据充分、不夸大、主动声明局限与口径",
        "anchor_1": "结论缺证据支撑，或含未声明的强断言/因果夸大",
        "anchor_3": "主要结论有证据，但对局限/口径交代不充分",
        "anchor_5": "每个关键结论可辩护，主动声明数据局限与口径陷阱（如前后对比不能排除自然增长）",
    },
    "insight_depth": {
        "name": "洞察深度",
        "what": "超越数值描述，给出业务含义、机制假设、横向对比",
        "anchor_1": "基本是数值罗列与描述，缺少业务解读",
        "anchor_3": "对部分数值有解读，但缺乏机制或对比",
        "anchor_5": "给出业务机制/因果假设，并结合横向对比与异常点",
    },
    "guidance": {
        "name": "引导与可行动性",
        "what": "明确的建议、下一步与决策含义",
        "anchor_1": "没有可行动建议",
        "anchor_3": "有方向性建议但不够具体或可执行",
        "anchor_5": "给出具体、可执行、与决策直接挂钩的建议",
    },
    "data_explanation": {
        "name": "数据说明清晰度",
        "what": "数值/口径/图表解释清楚，讲清含义而非堆数",
        "anchor_1": "堆砌数字，不解释含义或口径",
        "anchor_3": "解释了部分数字，但口径/单位/时间范围交代不全",
        "anchor_5": "数值、口径、单位、时间范围交代清楚，并与结论对应",
    },
    "direction_expansion": {
        "name": "分析方向拓展",
        "what": "主动提出值得继续深挖的分析方向",
        "anchor_1": "没有提出后续分析方向",
        "anchor_3": "提出了方向但宽泛或不切题",
        "anchor_5": "提出具体、切题、能带来新决策价值的深挖方向",
    },
}

SCENARIO_EXTRA_DIMENSIONS: dict[str, dict[str, str]] = {
    "synthesis": {
        "name": "多文件综合性",
        "what": "把多个文件/指标的发现串成连贯的业务图景",
        "anchor_1": "各文件结论各自孤立，没有综合",
        "anchor_3": "有简单串联，但缺乏整合判断",
        "anchor_5": "跨文件口径对齐，给出整合的业务判断与边界",
    }
}

_SENTENCE_SPLIT = re.compile(r"[^。！？\n]+[。！？]?")
# Terms that, when present, make a sentence a "material" claim.
_MATERIAL_HINTS = re.compile(
    r"\d|上升|下降|增长|降低|比|高于|低于|导致|因为|由于|主要|贡献|建议|应该|值得|推荐|"
    r"increase|decrease|higher|lower|cause|associate|correlat|predict|forecast|recommend|should|"
    r"seasonal|seasonality|季节性",
    re.IGNORECASE,
)
_EVIDENCE_MARKER = re.compile(r"\[\[evidence:([A-Za-z0-9_.:-]+)\]\]", re.IGNORECASE)
_QUANTITY = re.compile(
    r"(?<![\w.-])([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(%|percent(?:age points?)?|pp|CNY|USD|RMB|元|万元|亿元|人|次|件|个)?",
    re.IGNORECASE,
)
_TIME_SCOPE = re.compile(r"\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b")
_POPULATION_SCOPE = re.compile(
    r"\b(?:for|among|within)\s+([A-Za-z][A-Za-z0-9 _-]*?"
    r"(?:users|customers|orders|visitors|accounts|cohort))(?=[.,;]|$|\s*\[\[)",
    re.IGNORECASE,
)
_DIAGNOSTIC = re.compile(
    r"missing|unavailable|insufficient|not available|cannot be determined|cannot determine|"
    r"not estimable|cannot be estimated|"
    r"缺少|缺失|不可用|不足|无法判断|无法确定|不能判断",
    re.IGNORECASE,
)
_CAUSAL = re.compile(r"\bcaus(?:al|e|ed|es|ing)\b|导致|证明|使得", re.IGNORECASE)
_PREDICTION = re.compile(r"\bpredict|forecast|project(?:ed|ion)?|will\b|预测|预计|将会", re.IGNORECASE)
_RECOMMENDATION = re.compile(r"\brecommend|\bshould\b|建议|应该|推荐|值得", re.IGNORECASE)
_ASSOCIATION = re.compile(r"\bassociate|\bcorrelat|relationship|相关|关联", re.IGNORECASE)
_INCREASE = re.compile(r"increase|increased|higher|grew|growth|rise|rose|上升|增长|提高|提升|高于", re.IGNORECASE)
_DECREASE = re.compile(r"decrease|decreased|lower|decline|fell|drop|下降|降低|减少|低于", re.IGNORECASE)
_NO_CHANGE = re.compile(r"no (?:material |significant )?change|unchanged|持平|无显著变化", re.IGNORECASE)
_INDEPENDENT_VERIFICATION_CLAIM = re.compile(
    r"independently (?:verified|validated|recomputed)|statistically correct|"
    r"独立验证|独立复算|统计正确性已验证",
    re.IGNORECASE,
)
_HIGH_CONFIDENCE_CLAIM = re.compile(
    r"high confidence|confirmed|conclusive|certain(?:ly)?|definitive|"
    r"高置信|已确认|确定无疑|结论性",
    re.IGNORECASE,
)
_LIMITATION_DISCLOSURE = re.compile(
    r"limitation|caveat|descriptive only|association only|cannot rule out|"
    r"局限|限制|仅为描述|仅为关联|无法排除|不能排除",
    re.IGNORECASE,
)
_EXPLORATORY_LABEL = re.compile(
    r"exploratory|hypothesis|tentative|directional only|探索性|假设|初步方向",
    re.IGNORECASE,
)


def extract_material_claims(answer_text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index, raw in enumerate(_SENTENCE_SPLIT.findall(answer_text or "")):
        raw_text = raw.strip()
        text = strip_internal_evidence_markers(raw_text)
        if not text:
            continue
        claim_type = _claim_type(text)
        non_positive = claim_type in {"diagnostic", "limitation"}
        material = non_positive or bool(_MATERIAL_HINTS.search(text))
        evidence_ids = list(dict.fromkeys(_EVIDENCE_MARKER.findall(raw_text)))
        claim_id = f"claim_{index + 1}"
        claims.append({
            "id": claim_id,
            "claim_key": claim_id,
            "text": text,
            "claim": text,
            "claim_type": claim_type,
            "material": material,
            "requires_evidence": material and not non_positive,
            "quantities": _extract_quantities(text),
            "units": _units(text),
            "direction": _direction(text),
            "time_scope": _first_group(_TIME_SCOPE, text),
            "population_scope": _first_group(_POPULATION_SCOPE, text),
            "evidence_ids": evidence_ids,
            "evidence_id": evidence_ids[0] if len(evidence_ids) == 1 else "",
            "verification_overclaim": bool(_INDEPENDENT_VERIFICATION_CLAIM.search(text)),
            "confidence_assertion": "high" if _HIGH_CONFIDENCE_CLAIM.search(text) else "",
        })
    return claims


def strip_internal_evidence_markers(answer_text: str) -> str:
    """Remove synthesis-only EvidenceRecord markers from user-visible text."""

    text = re.sub(r"\s*\[\[evidence:[A-Za-z0-9_.:-]+\]\]", "", answer_text or "", flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+([.,;:!?。！？；：])", r"\1", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _claim_type(text: str) -> str:
    if _LIMITATION_DISCLOSURE.search(text):
        return "limitation"
    if _DIAGNOSTIC.search(text):
        return "diagnostic"
    if _CAUSAL.search(text):
        return "causal"
    if _PREDICTION.search(text):
        return "prediction"
    if _RECOMMENDATION.search(text):
        return "recommendation"
    if _ASSOCIATION.search(text):
        return "association"
    if _INCREASE.search(text) or _DECREASE.search(text) or _NO_CHANGE.search(text):
        return "comparison"
    if _extract_quantities(text):
        return "numeric"
    return "descriptive"


def _extract_quantities(text: str) -> list[dict[str, Any]]:
    time_spans = [match.span() for match in _TIME_SCOPE.finditer(text)]
    quantities: list[dict[str, Any]] = []
    for match in _QUANTITY.finditer(text):
        if any(match.start() < end and match.end() > start for start, end in time_spans):
            continue
        raw = match.group(0).strip()
        unit = (match.group(2) or "").strip()
        try:
            value = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        quantities.append({"raw": raw, "value": value, "unit": unit})
    return quantities


def _units(text: str) -> list[str]:
    return list(dict.fromkeys(
        item["unit"] for item in _extract_quantities(text) if item.get("unit")
    ))


def _direction(text: str) -> str:
    if _NO_CHANGE.search(text):
        return "no_change"
    if _DECREASE.search(text):
        return "decrease"
    if _INCREASE.search(text):
        return "increase"
    return ""


def _first_group(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    return str(match.group(1) if match.lastindex else match.group(0)).strip()


def build_final_answer_audit(
    answer_text: str,
    *,
    evidence_records: list[dict[str, Any]] | None = None,
    route_proposals: list[dict[str, Any]] | None = None,
    cleaning_logs: list[dict[str, Any]] | None = None,
    current_plan_id: str = "",
    current_dataset_versions: list[str] | set[str] | tuple[str, ...] | None = None,
    sessions_root: Any = None,
    current_session_id: str = "",
    current_plan_digest: str = "",
    current_step_digests: dict[str, str] | None = None,
    analysis_requirements: list[dict[str, Any]] | None = None,
    llm_critique: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit the actual candidate answer against exact, current evidence."""

    claims = extract_material_claims(answer_text)
    public_draft = strip_internal_evidence_markers(answer_text)
    has_limitation = bool(_LIMITATION_DISCLOSURE.search(public_draft))
    has_exploratory_label = bool(_EXPLORATORY_LABEL.search(public_draft))
    claims = [
        {
            **claim,
            "answer_has_limitation": has_limitation,
            "answer_has_exploratory_label": has_exploratory_label,
        }
        for claim in claims
    ]
    report = verify_analysis_claims(
        claims=claims,
        evidence_records=evidence_records or [],
        route_proposals=route_proposals or [],
        cleaning_logs=cleaning_logs or [],
        current_plan_id=current_plan_id,
        current_dataset_versions=current_dataset_versions,
        sessions_root=sessions_root,
        current_session_id=current_session_id,
        current_plan_digest=current_plan_digest,
        current_step_digests=current_step_digests,
        analysis_requirements=analysis_requirements or [],
        require_explicit_evidence_ids=True,
        strict_claim_semantics=True,
    )
    status = {
        "fail": "blocked",
        "pass_with_downgrades": "revise",
        "pass": "pass",
    }.get(str(report.get("overall_status") or ""), "blocked")
    public_text = public_draft
    digest = hashlib.sha256((answer_text or "").encode("utf-8")).hexdigest()
    audit_id = "final_audit_" + hashlib.sha256(
        (digest + str(report.get("id") or "")).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "contract_version": "final_answer_audit.v1",
        "id": audit_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "draft_digest": digest,
        "status": status,
        "public_text": public_text,
        "claims": claims,
        "claim_checks": list(report.get("claim_checks") or []),
        "verification_report_id": report.get("id"),
        "deterministic_overall_status": report.get("overall_status"),
        "llm_critique": dict(llm_critique) if isinstance(llm_critique, dict) else None,
    }


def _char_bigrams(text: str) -> set[str]:
    chars = re.sub(r"[\s0-9，。、！？：；,.!?;:\"'()\[\]]", "", text or "")
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[i : i + 2] for i in range(len(chars) - 1)}


def is_supported_by_evidence(claim_text: str, evidence_records: list[dict[str, Any]]) -> bool:
    # Character-bigram overlap is robust for Chinese without word segmentation
    # (handles particle differences like 提升 vs 提升了).
    claim_ng = _char_bigrams(claim_text)
    if not claim_ng:
        return False
    for record in evidence_records or []:
        hay = " ".join(
            str(record.get(field, ""))
            for field in ("claim", "result_summary", "metrics", "method")
        )
        hay_ng = _char_bigrams(hay)
        if hay_ng and len(claim_ng & hay_ng) / len(claim_ng) >= 0.4:
            return True
    return False


def _relationship_uses_from_state(state) -> list[dict[str, Any]]:
    uses: list[dict[str, Any]] = []
    for index, rel in enumerate(getattr(state, "file_relationships", []) or []):
        uses.append(
            {
                "relationship_id": str(rel.get("relationship_id") or f"relationship_{index + 1}"),
                "used_for_claim": bool(rel.get("used_for_claim")),
                "validation_status": str(rel.get("validation_status") or rel.get("status") or "unknown"),
                "time_scope_compatible": rel.get("time_scope_compatible"),
            }
        )
    return uses


def evaluate_fatal(answer_text: str, state) -> dict[str, Any]:
    evidence_records = getattr(state, "evidence_records", []) or []
    plan = getattr(state, "analysis_plan", None)
    plan = plan if isinstance(plan, dict) else {}
    audit = build_final_answer_audit(
        answer_text,
        evidence_records=evidence_records,
        route_proposals=getattr(state, "route_proposals", []) or [],
        cleaning_logs=getattr(state, "cleaning_logs", []) or [],
        current_plan_id=str(plan.get("id") or ""),
        analysis_requirements=_flatten_analysis_requirements(plan),
    )
    checks_by_id = {
        str(check.get("claim_id") or ""): check
        for check in audit.get("claim_checks") or []
        if isinstance(check, dict)
    }
    claims_in = [
        {
            "claim_key": claim["claim_key"],
            "material": claim["material"],
            "supported": checks_by_id.get(claim["id"], {}).get("status") == "passed",
            "status": checks_by_id.get(claim["id"], {}).get("status"),
            "reason_codes": checks_by_id.get(claim["id"], {}).get("reason_codes", []),
            "safe_action": checks_by_id.get(claim["id"], {}).get("safe_action"),
        }
        for claim in audit.get("claims") or []
    ]
    result = score_analysis_quality(
        claims=claims_in,
        relationship_uses=_relationship_uses_from_state(state),
    )
    blockers = list(result.get("blockers") or [])
    reports = getattr(state, "verification_reports", []) or []
    if reports and reports[-1].get("overall_status") == "fail":
        blockers.append("agent_verification_failed")
    unique = list(dict.fromkeys(blockers))
    ready = not unique
    result["blockers"] = unique
    result["claim_delivery_ready"] = ready
    result["global_publish_gate"] = ready
    result["final_answer_audit"] = audit
    return result


def _flatten_analysis_requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    grouped = plan.get("analysis_requirements")
    if not isinstance(grouped, dict):
        return []
    return [
        requirement
        for group in grouped.values()
        if isinstance(group, list)
        for requirement in group
        if isinstance(requirement, dict)
    ]


def build_judge_context(state, question: str) -> dict[str, Any]:
    bundles = getattr(state, "data_understanding_bundles", []) or []
    from data_agent.agent.data_understanding import build_user_data_brief

    # bundles[-1] is the latest understanding bundle; mirrors the runtime's
    # latest-bundle convention (loop.py:796 iterates bundles in reverse).
    brief = build_user_data_brief(bundles[-1]) if bundles else {"datasets": [], "relationships": []}
    return {"question": question, "data_brief": brief}
