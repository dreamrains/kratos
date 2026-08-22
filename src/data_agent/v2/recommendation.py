from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from data_agent.v2.models import ClaimClass, FindingKind, OutcomeStatus


class RecommendationIntent(StrEnum):
    NONE = "none"
    INVESTIGATE = "investigate"
    ACT = "act"


class ActionRisk(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationMode(StrEnum):
    NONE = "none"
    INVESTIGATIVE_NEXT_STEP = "investigative_next_step"
    OPERATIONAL_ACTION = "operational_action"


@dataclass(frozen=True, slots=True)
class RecommendationContext:
    intent: RecommendationIntent
    outcome_status: OutcomeStatus
    finding_kind: FindingKind
    maximum_claim_class: ClaimClass
    action_risk: ActionRisk
    reversible: bool


@dataclass(frozen=True, slots=True)
class RecommendationDecision:
    mode: RecommendationMode
    reason_code: str
    narrative: str = ""


def decide_recommendation(context: RecommendationContext) -> RecommendationDecision:
    """Choose whether advice is justified without upgrading evidence strength."""

    if context.intent is RecommendationIntent.NONE:
        return RecommendationDecision(
            RecommendationMode.NONE,
            "user_did_not_request_recommendation",
        )
    if context.outcome_status is OutcomeStatus.LIMITED:
        return RecommendationDecision(
            RecommendationMode.INVESTIGATIVE_NEXT_STEP,
            "analysis_limit_requires_resolution",
            "先解决分析单位、分组口径或数据充分性限制，再评估行动方案。",
        )
    if context.outcome_status is OutcomeStatus.NULL_RESULT:
        return RecommendationDecision(
            RecommendationMode.INVESTIGATIVE_NEXT_STEP,
            "null_result_requires_more_information",
            "如该决策重要，应扩大有效样本、检查测量精度，并预先定义最小有意义差异后复验。",
        )
    if context.action_risk not in {ActionRisk.LOW, ActionRisk.MEDIUM} or not context.reversible:
        return RecommendationDecision(
            RecommendationMode.INVESTIGATIVE_NEXT_STEP,
            "action_risk_requires_stronger_evidence",
            "该行动风险较高或不可逆，先用随机化或准实验设计验证干预效果。",
        )
    if context.finding_kind is FindingKind.TIME_TREND:
        return RecommendationDecision(
            RecommendationMode.INVESTIGATIVE_NEXT_STEP,
            "historical_trend_requires_driver_validation",
            "可把历史趋势作为调查线索：检查季节、口径变化和同期外部事件，再用低风险、可逆的验证设计评估可干预因素。",
        )
    if context.finding_kind is FindingKind.FORECAST:
        return RecommendationDecision(
            RecommendationMode.INVESTIGATIVE_NEXT_STEP,
            "forecast_requires_scenario_monitoring",
            "可把基线预测用于情景规划，但应同时保留区间上下界、设置监控与更新条件；它不证明任何干预会产生预测中的结果。",
        )
    if context.finding_kind in {
        FindingKind.GROUP_COMPARISON,
        FindingKind.ASSOCIATION,
    } or context.maximum_claim_class is not ClaimClass.CAUSAL:
        return RecommendationDecision(
            RecommendationMode.INVESTIGATIVE_NEXT_STEP,
            "observational_evidence_requires_validation",
            "可把差异作为验证线索：先检查组间构成与混杂因素，并用低风险、可逆的小规模实验验证。",
        )
    if context.intent is RecommendationIntent.ACT:
        return RecommendationDecision(
            RecommendationMode.OPERATIONAL_ACTION,
            "low_risk_reversible_action_supported",
            "在明确监控指标和停止条件后，可小范围执行该低风险、可逆行动。",
        )
    return RecommendationDecision(
        RecommendationMode.INVESTIGATIVE_NEXT_STEP,
        "user_requested_investigation",
        "围绕当前发现补充机制、混杂与敏感性验证。",
    )
