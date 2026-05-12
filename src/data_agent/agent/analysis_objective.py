"""Business objective inference for professional analysis flow."""

from __future__ import annotations

from typing import Any


QUESTION_TYPES = {
    "description",
    "comparison",
    "effect_evaluation",
    "attribution",
    "forecast",
    "diagnosis",
    "decision",
    "opportunity",
}


def infer_analysis_objective(user_input: str, dataset_profile: str = "") -> dict[str, Any]:
    text = (user_input or "").lower()
    profile = (dataset_profile or "").lower()
    combined = f"{text} {profile}"

    question_type = _question_type(text)
    business_object = _business_object(text)
    if business_object == "unknown":
        business_object = _business_object(profile)
    requires_counterfactual = question_type in {"effect_evaluation", "attribution", "decision"} and _has_any(
        text,
        ["effect", "impact", "changed", "effective", "causal", "whether", "是否", "效果", "影响", "有效"],
    )
    decision_risk = _decision_risk(question_type, text, requires_counterfactual)
    analysis_depth = "deep" if decision_risk == "high" else "standard"

    return {
        "question_type": question_type,
        "business_object": business_object,
        "decision_risk": decision_risk,
        "analysis_depth": analysis_depth,
        "requires_counterfactual": requires_counterfactual,
        "expected_outputs": _expected_outputs(question_type),
    }


def _question_type(text: str) -> str:
    if _has_any(text, ["forecast", "predict", "prediction", "预算", "预测", "预估"]):
        return "forecast"
    if _has_any(text, ["why", "decline", "drop", "diagnose", "driver", "原因", "为什么", "下降", "诊断"]):
        return "diagnosis"
    if _has_any(text, ["attribute", "attribution", "decomposition", "归因", "拆解"]):
        return "attribution"
    if _has_any(text, ["effective", "effect", "impact", "changed", "evaluate", "evaluation", "是否有效", "效果", "影响"]):
        return "effect_evaluation"
    if _has_any(text, ["decide", "decision", "worth", "continue", "是否值得", "决策", "继续"]):
        return "decision"
    if _has_any(text, ["opportunity", "next analysis", "还能分析", "分析方向", "机会"]):
        return "opportunity"
    if _has_any(text, ["compare", "comparison", "versus", "对比", "比较"]):
        return "comparison"
    return "description"


def _business_object(text: str) -> str:
    if _has_any(text, ["feature", "功能"]):
        return "feature"
    if _has_any(text, ["campaign", "marketing", "活动", "营销"]):
        return "campaign"
    if _has_any(text, ["user", "users", "用户"]):
        return "user"
    if _has_any(text, ["product", "sku", "商品", "产品"]):
        return "product"
    if _has_any(text, ["revenue", "income", "sales", "收入", "收益", "营收"]):
        return "revenue"
    if _has_any(text, ["cost", "profit", "roi", "成本", "利润"]):
        return "cost"
    if _has_any(text, ["channel", "渠道"]):
        return "channel"
    return "unknown"


def _decision_risk(question_type: str, text: str, requires_counterfactual: bool) -> str:
    if requires_counterfactual or question_type in {"forecast", "decision"}:
        return "high"
    if question_type in {"diagnosis", "attribution", "opportunity"}:
        return "medium"
    if _has_any(text, ["roi", "budget", "投入", "预算", "是否值得"]):
        return "high"
    return "low"


def _expected_outputs(question_type: str) -> list[str]:
    outputs = ["conclusions", "metrics", "recommendations", "next_analysis"]
    if question_type in {"effect_evaluation", "attribution", "forecast", "diagnosis", "decision"}:
        outputs.insert(2, "validation")
    return outputs


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term.lower() in text for term in terms)
