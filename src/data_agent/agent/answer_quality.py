"""Deterministic answer-quality measurement primitives (no LLM).

Measurement-only. Extends the existing analysis-quality rubric with
answer-text claim extraction and agent-verification folding.
"""

from __future__ import annotations

import re
from typing import Any

from data_agent.agent.analysis_quality_rubric import score_analysis_quality

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
_MATERIAL_HINTS = re.compile(r"\d|上升|下降|增长|降低|比|高于|低于|导致|因为|由于|主要|贡献|建议|应该|值得|推荐")


def extract_material_claims(answer_text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index, raw in enumerate(_SENTENCE_SPLIT.findall(answer_text or "")):
        text = raw.strip()
        if not text:
            continue
        material = bool(_MATERIAL_HINTS.search(text))
        claims.append({"claim_key": f"claim_{index + 1}", "text": text, "material": material})
    return claims


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
    claims_in = [
        {
            "claim_key": c["claim_key"],
            "material": c["material"],
            "supported": is_supported_by_evidence(c["text"], getattr(state, "evidence_records", []) or [])
            if c["material"]
            else True,
        }
        for c in extract_material_claims(answer_text)
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
    return result


def build_judge_context(state, question: str) -> dict[str, Any]:
    bundles = getattr(state, "data_understanding_bundles", []) or []
    from data_agent.agent.data_understanding import build_user_data_brief

    brief = build_user_data_brief(bundles[-1]) if bundles else {"datasets": [], "relationships": []}
    return {"question": question, "data_brief": brief}
