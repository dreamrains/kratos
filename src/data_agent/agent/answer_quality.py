"""Deterministic answer-quality measurement primitives (no LLM).

Measurement-only. Extends the existing analysis-quality rubric with
answer-text claim extraction and agent-verification folding.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Sequence

from data_agent.agent.analysis_quality_rubric import score_analysis_quality
from data_agent.agent.verification import verify_analysis_claims

ClaimAction = Literal["verified", "exploratory", "unsupported"]
PublicationMode = Literal["tiered", "strict"]

# Local suffix appended to current traceable computations that cannot be
# published as verified (e.g. completion is ``complete_with_limits``). Kept
# Chinese-only because the published answer is Chinese; a parallel English
# suffix would weaken the signal.
EXPLORATORY_CLAIM_SUFFIX = "（探索性，未经独立校验）"

# Strict-mode fail-safe banner. When the tiered renderer cannot safely
# recover (an unsupported claim could not be cleanly replaced in place, or
# the audit was missing so claims were re-derived from the draft text),
# strict mode prepends this Chinese diagnostic so the reader can see that
# publication was downgraded. Tiered mode recovers silently — same per-claim
# rules, no banner. The five deterministic blockers fire in BOTH modes; this
# banner is a strict-only observability surface, not an additional gate.
STRICT_RECOVERY_DIAGNOSTIC = (
    "> 严格发布模式：部分结论因校验信息不完整未能精确还原，"
    "已按最低确定性阻断并降级发布，请结合下方标注审阅。"
)

# Reason-code → Chinese diagnostic mapping for unsupported claims. Each
# diagnostic names the missing evidence, method, or data so the reader can
# tell what blocked publication. The five deterministic blockers
# (fabricated value, contradictory direction, stale dataset, cross-scope
# evidence, causal upgrade) all yield ``unsupported`` and route through here.
_UNSUPPORTED_DIAGNOSTICS: dict[str, str] = {
    "missing_evidence_identity": "无法发布该数值：缺少对应的当前计算证据标识",
    "numeric_mismatch": "无法发布该数值：与当前计算证据的数值不一致",
    "unit_mismatch": "无法发布该数值：单位口径与证据不一致",
    "direction_mismatch": "无法发布该方向结论：与证据方向不一致",
    "time_scope_mismatch": "无法发布该结论：时间口径与证据不一致",
    "population_scope_mismatch": "无法发布该结论：人群口径与证据不一致",
    "confidence_mismatch": "无法发布该结论：置信度表述与证据不一致",
    "verification_level_overclaim": "无法发布该结论：所选证据的核验等级不足以支撑该表述",
    "stale_dataset_evidence": "无法发布该结论：证据对应的输入数据版本已过期",
    "stale_plan_evidence": "无法发布该结论：证据属于历史计划版本",
    "evidence_outside_current_plan": "无法发布该结论：证据不在当前分析计划范围内",
    "evidence_identity_not_found": "无法发布该结论：引用的证据在当前计划中不存在",
    "causal_claim_not_identified": "无法发布该因果结论：未满足因果识别方法要求",
    "unmet_block_claim_requirement": "无法发布该结论：未满足所需的统计分析保证",
    "claim_guard_blocked": "无法发布该结论：声明性保证检查未通过",
    "computation_integrity_failure": "无法发布该结论：计算完整性校验失败",
    "unsupported_claim": "无法发布该结论：缺少当前证据支撑",
}
_UNSUPPORTED_DEFAULT_DIAGNOSTIC = "无法发布该结论：缺少当前证据支撑"

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
_EVIDENCE_MARKER = re.compile(
    r"\[\[evidence:([A-Za-z0-9_.:-]+)"
    r"(?:#([A-Za-z0-9_.:-]+))?\]\]",
    re.IGNORECASE,
)
_EVIDENCE_MARKER_RUN = re.compile(
    rf"(?:{_EVIDENCE_MARKER.pattern})+",
    _EVIDENCE_MARKER.flags,
)
_QUANTITY = re.compile(
    r"(?<![\w.-])([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(%|percent(?:age points?)?|pp|CNY|USD|RMB|元|万元|亿元|人|次|件|个)?",
    re.IGNORECASE,
)
_TIME_SCOPE = re.compile(r"\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b")
_POPULATION_SCOPE = re.compile(
    r"\b(?:for|among|within)\s+([A-Za-z][A-Za-z0-9 _-]*?"
    r"(?:users|customers|orders|visitors|accounts|cohort))(?=\s*[.,;]|$|\s*\[\[)",
    re.IGNORECASE,
)
_DIAGNOSTIC = re.compile(
    r"missing|unavailable|insufficient|not available|cannot be determined|cannot determine|"
    r"not estimable|cannot be estimated|"
    r"缺少|缺失|不可用|不足|无法判断|无法确定|不能判断|不可估计|无法估计",
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
        marker_pairs = list(dict.fromkeys(_EVIDENCE_MARKER.findall(raw_text)))
        evidence_refs = [
            {"evidence_id": evidence_id, "measurement_key": measurement_key}
            for evidence_id, measurement_key in marker_pairs
        ]
        evidence_ids = list(dict.fromkeys(
            ref["evidence_id"] for ref in evidence_refs
        ))
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
            "evidence_refs": evidence_refs,
            "evidence_id": evidence_ids[0] if len(evidence_ids) == 1 else "",
            "verification_overclaim": bool(_INDEPENDENT_VERIFICATION_CLAIM.search(text)),
            "confidence_assertion": "high" if _HIGH_CONFIDENCE_CLAIM.search(text) else "",
        })
    return claims


def strip_internal_evidence_markers(answer_text: str) -> str:
    """Remove synthesis-only EvidenceRecord markers from user-visible text."""

    source = answer_text or ""
    parts: list[str] = []
    cursor = 0
    punctuation = ".,;:!?。！？；："
    for match in _EVIDENCE_MARKER_RUN.finditer(source):
        prefix = source[cursor:match.start()]
        next_index = match.end()
        while next_index < len(source) and source[next_index] in " \t":
            next_index += 1
        follows_punctuation = (
            next_index < len(source) and source[next_index] in punctuation
        )
        if follows_punctuation:
            after = source[next_index]
        else:
            after = source[match.end()] if match.end() < len(source) else ""
        parts.append(prefix)
        before = source[match.start() - 1] if match.start() else ""
        if (
            not follows_punctuation
            and before
            and after
            and not before.isspace()
            and not after.isspace()
        ):
            parts.append(" ")
        cursor = next_index if follows_punctuation else match.end()
    parts.append(source[cursor:])
    return "".join(parts)


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
    from data_agent.agent.evidence_contracts import (
        analysis_plan_semantic_digest,
        analysis_step_semantic_digest,
    )
    from data_agent.agent.context import authoritative_dataset_versions

    method_plan = plan.get("method_plan")
    method_plan = method_plan if isinstance(method_plan, list) else []
    current_step_digests = {
        str(step.get("step_id") or ""): analysis_step_semantic_digest(step)
        for step in method_plan
        if isinstance(step, dict) and str(step.get("step_id") or "")
    }
    audit = build_final_answer_audit(
        answer_text,
        evidence_records=evidence_records,
        route_proposals=getattr(state, "route_proposals", []) or [],
        cleaning_logs=getattr(state, "cleaning_logs", []) or [],
        current_plan_id=str(plan.get("id") or ""),
        current_dataset_versions=authoritative_dataset_versions(),
        current_plan_digest=(
            analysis_plan_semantic_digest(plan)
            if plan.get("id")
            else ""
        ),
        current_step_digests=current_step_digests,
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


@dataclass(frozen=True)
class PublicationResult:
    """Result of claim-tier publication rendering.

    ``text`` is the published answer with verified/exploratory findings kept
    and unsupported claims replaced in place by Chinese diagnostics.
    ``actions`` maps each audit claim id to its publication action. ``diagnostics``
    carries per-claim audit metadata for turn diagnostics; it never re-derives
    a publication decision on its own.
    """

    text: str
    actions: dict[str, ClaimAction]
    diagnostics: tuple[dict[str, Any], ...]


def _diagnostic_for_reason_codes(reason_codes: Sequence[str]) -> str:
    for code in reason_codes or ():
        text = _UNSUPPORTED_DIAGNOSTICS.get(str(code))
        if text:
            return text
    return _UNSUPPORTED_DEFAULT_DIAGNOSTIC


def _completion_status_value(completion: Any) -> str:
    if completion is None:
        return ""
    for attr in ("status", "completion_status"):
        value = getattr(completion, attr, None)
        if value:
            return str(value)
    if isinstance(completion, dict):
        for key in ("status", "completion_status"):
            value = completion.get(key)
            if value:
                return str(value)
    return ""


def _claim_material_flag(claim: dict[str, Any]) -> bool:
    value = claim.get("material")
    if isinstance(value, bool):
        return value
    text = str(claim.get("text") or claim.get("claim") or "")
    if not text:
        return False
    claim_type = str(claim.get("claim_type") or "").strip()
    if claim_type in {"diagnostic", "limitation"}:
        return True
    return bool(_MATERIAL_HINTS.search(text))


def _claim_text(claim: dict[str, Any]) -> str:
    return str(claim.get("text") or claim.get("claim") or "").strip()


def _claim_identifier(claim: dict[str, Any]) -> str:
    return str(claim.get("id") or claim.get("claim_id") or claim.get("claim_key") or "").strip()


def _find_unconsumed_span(
    haystack: str,
    needle: str,
    consumed: list[tuple[int, int]],
) -> int:
    if not needle:
        return -1
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return -1
        end = idx + len(needle)
        if all(end <= c_start or idx >= c_end for c_start, c_end in consumed):
            return idx
        start = idx + 1


def render_audited_analysis_answer(
    *,
    draft: str,
    audit: dict[str, Any] | None,
    completion: Any,
    mode: PublicationMode = "tiered",
) -> PublicationResult:
    """Render ``draft`` under claim-tier publication rules.

    The renderer is deterministic and never calls another tool. It uses the
    existing audit (claims + claim_checks) to decide per-claim actions:

    * ``verified`` — claim passed audit and the completion status is
      ``complete``. Original text is retained.
    * ``exploratory`` — claim passed but completion is limited, or audit
      status is ``downgraded``, or the audit itself is missing. The claim
      text is retained and the local suffix ``（探索性，未经独立校验）`` is
      appended for material claims.
    * ``unsupported`` — claim failed the audit (any reason code in the
      deterministic blocker set, including fabricated values, contradictory
      directions, stale dataset evidence, cross-scope evidence, and causal
      upgrades). The claim span is replaced in place with a Chinese
      diagnostic naming the missing evidence, method, or data.

    Headings, tables, non-claim prose, method, and limitations stay in their
    original order. The five deterministic blockers fire in BOTH modes; the
    exploratory suffix rule is unchanged across modes.

    Strict vs tiered — fail-safe rollback net. The two modes share the
    per-claim rules above. ``strict`` is additionally more conservative: when
    the tiered renderer cannot safely recover — (a) at least one unsupported
    claim could NOT be cleanly replaced in place and had to be appended as a
    trailing diagnostic block, OR (b) the audit is missing so claims were
    re-derived from the draft text — ``strict`` emits a visible Chinese
    recovery banner (``STRICT_RECOVERY_DIAGNOSTIC``) at the top of the
    returned text and records it in ``PublicationResult.diagnostics``.
    ``tiered`` recovers silently with no banner. This makes ``strict`` a real
    rollback net: the published text is identical to ``tiered`` when recovery
    is clean, but observably more cautious when it is not. The legacy
    whole-answer English fallback must not appear in either mode.
    """

    draft_text = strip_internal_evidence_markers(draft or "")
    public_text = draft_text
    audit_present = isinstance(audit, dict)
    if audit_present:
        audited_public = str(audit.get("public_text") or "").strip()
        if audited_public:
            public_text = audited_public

    completion_status = _completion_status_value(completion)
    # An answer published without an audit must not claim ``verified`` —
    # force ``complete`` to False so every material claim downgrades to
    # exploratory. This matches the docstring of the loop's
    # ``_render_audited_publication`` and is the safer behavior.
    complete = completion_status == "complete" and audit_present

    raw_audit_claims: list[dict[str, Any]] = []
    audit_claims_provided = False
    if audit_present:
        raw_audit_claims = [
            claim for claim in (audit.get("claims") or [])
            if isinstance(claim, dict)
        ]
        audit_claims_provided = bool(raw_audit_claims)
    if not raw_audit_claims:
        raw_audit_claims = extract_material_claims(public_text)

    checks_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(audit, dict):
        for check in audit.get("claim_checks") or []:
            if not isinstance(check, dict):
                continue
            claim_id = str(check.get("claim_id") or "").strip()
            if claim_id:
                checks_by_id[claim_id] = check

    actions: dict[str, ClaimAction] = {}
    diagnostics: list[dict[str, Any]] = []
    spans: list[tuple[int, int, str, ClaimAction, dict[str, Any], bool]] = []
    unmatched_unsupported: list[tuple[str, dict[str, Any]]] = []
    consumed: list[tuple[int, int]] = []

    for claim in raw_audit_claims:
        claim_id = _claim_identifier(claim)
        if not claim_id:
            continue
        claim_text = _claim_text(claim)
        check = checks_by_id.get(claim_id, {})
        status = str(check.get("status") or "").strip()
        if status == "failed":
            action: ClaimAction = "unsupported"
        elif status == "downgraded" or not complete:
            action = "exploratory"
        else:
            action = "verified"
        actions[claim_id] = action
        material = _claim_material_flag(claim)
        diagnostics.append({
            "claim_id": claim_id,
            "action": action,
            "audit_status": status,
            "material": material,
            "reason_codes": list(check.get("reason_codes") or []),
        })
        if not claim_text:
            continue
        match_index = _find_unconsumed_span(public_text, claim_text, consumed)
        if match_index >= 0:
            spans.append((
                match_index,
                match_index + len(claim_text),
                claim_id,
                action,
                check,
                material,
            ))
            consumed.append((match_index, match_index + len(claim_text)))
            consumed.sort()
        elif action == "unsupported":
            unmatched_unsupported.append((claim_id, check))

    spans.sort(key=lambda item: (item[0], item[1]))

    pieces: list[str] = []
    cursor = 0
    for start, end, _claim_id, action, check, material in spans:
        if start < cursor:
            continue
        pieces.append(public_text[cursor:start])
        original_span = public_text[start:end]
        if action == "verified":
            pieces.append(original_span)
        elif action == "exploratory":
            pieces.append(original_span)
            if material:
                pieces.append(EXPLORATORY_CLAIM_SUFFIX)
        else:
            pieces.append(_diagnostic_for_reason_codes(check.get("reason_codes") or []))
        cursor = end
    pieces.append(public_text[cursor:])

    if unmatched_unsupported:
        pieces.append("\n\n")
        for _claim_id, check in unmatched_unsupported:
            pieces.append(_diagnostic_for_reason_codes(check.get("reason_codes") or []))
            pieces.append("\n")

    text = "".join(pieces).rstrip()

    # Strict-only fail-safe rollback net. When the tiered renderer cannot
    # safely recover — (a) an unsupported claim could not be cleanly replaced
    # in place and had to be appended as a trailing diagnostic block, or
    # (b) the audit was missing so claims were re-derived from the draft —
    # strict mode prepends a visible Chinese recovery banner and records it
    # in diagnostics. Tiered mode recovers silently (no banner). The five
    # deterministic blockers fire in BOTH modes above; this is an
    # observability surface, not an additional gate.
    if mode == "strict" and (unmatched_unsupported or not audit_claims_provided):
        diagnostics.append({
            "event": "strict_recovery_diagnostic",
            "text": STRICT_RECOVERY_DIAGNOSTIC,
            "unmatched_unsupported": len(unmatched_unsupported),
            "audit_missing": not audit_claims_provided,
        })
        text = STRICT_RECOVERY_DIAGNOSTIC + "\n\n" + (text if text else "")

    if text:
        text = text + "\n"
    return PublicationResult(
        text=text,
        actions=actions,
        diagnostics=tuple(diagnostics),
    )
