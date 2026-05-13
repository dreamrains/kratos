"""Intent classification with rule-based fast path and LLM fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

IntentType = Literal[
    "simple_response",
    "knowledge_qa",
    "analysis_consultation",
    "result_followup",
    "intent_negotiation",
    "data_requirement",
    "data_operation",
    "directed_analysis",
    "comprehensive_report",
]
Clarity = Literal["clear", "vague", "clarification_needed"]
DataState = Literal["no_data", "data_loaded", "insufficient_data", "unknown"]
AnalysisStage = Literal["discover", "scope", "plan", "execute", "report", "follow_up"]
RecommendedAction = Literal[
    "answer_directly",
    "ask_question",
    "guide_analysis",
    "request_data",
    "execute_operation",
    "run_analysis",
    "generate_report",
]


@dataclass
class TurnIntent:
    intent_type: IntentType
    clarity: Clarity
    data_state: DataState
    analysis_stage: AnalysisStage
    recommended_action: RecommendedAction
    reason: str = ""
    ambiguities: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Keyword sets ──────────────────────────────────────────

_CHAT_KEYWORDS = ("你好", "hello", "hi", "谢谢", "感谢", "thanks", "thank you")
_CONFIRMATION_KEYWORDS = (
    "好的", "明白", "明白了", "了解", "知道了", "收到", "ok", "okay",
    "继续", "是的", "对", "没错", "没问题", "可以", "同意", "理解",
)
_KNOWLEDGE_QA_PREFIXES = (
    "什么是", "是什么", "介绍一下", "解释一下", "什么是", "what is",
    "explain", "describe", "介绍一下", "告诉我什么是",
)
_ANALYSIS_CONSULT_KEYWORDS = (
    "怎么分析", "如何分析", "分析方法", "分析思路", "分析建议",
    "应该用", "该用什么", "合适的方法", "how to analyze", "which method",
    "这个思路对", "方法对吗", "用什么方法",
)
_RESULT_FOLLOWUP_KEYWORDS = (
    "为什么说", "为什么你认为", "怎么得出", "怎么解释", "这个结论",
    "这个结果", "可靠吗", "置信度", "p值", "样本量", "数据支持",
    "再详细", "具体说明", "能解释一下",
)
_OPERATION_KEYWORDS = (
    "汇总", "导出", "转换", "筛选", "过滤", "排序", "重命名", "选择",
    "合并", "透视", "分组", "按周", "按月", "按天", "按季", "按年",
    "计算", "求和", "求平均", "select", "filter", "rename", "sort",
    "export", "导成",
)
_REPORT_KEYWORDS = (
    "报告", "完整分析", "全面分析", "综合分析", "分析报告", "完整报告",
    "出个报告", "给我一份报告", "full report", "comprehensive analysis",
    "complete analysis report",
)
_DATA_REQUIREMENT_KEYWORDS = (
    "需要哪些数据", "要哪些数据", "准备哪些数据", "获取哪些数据", "什么数据",
    "需要什么表", "数据需求", "没有数据", "还缺什么数据", "what data",
    "which data", "need data",
)
_ANALYSIS_KEYWORDS = (
    "趋势", "对比", "比较", "归因", "为什么", "原因", "预测", "异常",
    "漏斗", "转化", "贡献", "效果", "是否值得", "长期运营", "有没有",
    "分析", "分布", "相关性", "增长", "下降", "上升",
    "trend", "compare", "why", "reason", "decline", "drop", "driver",
    "forecast", "predict", "effect", "causal", "funnel", "conversion",
    "evaluate", "analyze", "worth",
)
_GUIDANCE_KEYWORDS = (
    "不知道如何分析", "帮我看看", "看看这份数据", "分析一下",
    "有什么可以分析", "帮我分析", "看看数据",
)


# ── Legacy compatibility ──────────────────────────────────

_LEGACY_INTENT_MAP: dict[str, IntentType] = {
    "chat": "simple_response",
    "operation": "data_operation",
    "analysis_guidance": "analysis_consultation",
    "data_requirement": "data_requirement",
    "direct_analysis": "directed_analysis",
    "report": "comprehensive_report",
}

_PROMPT_LEVEL_MAP: dict[IntentType, str] = {
    "simple_response": "conversation",
    "knowledge_qa": "conversation",
    "analysis_consultation": "conversation",
    "result_followup": "conversation",
    "intent_negotiation": "guidance",
    "data_requirement": "guidance",
    "data_operation": "quick",
    "directed_analysis": "analysis",
    "comprehensive_report": "analysis",
}


def infer_data_state(session_context: str = "") -> DataState:
    if session_context and ("rows" in session_context or "columns:" in session_context):
        return "data_loaded"
    return "no_data"


def plan_turn_intent(user_input: str, session_context: str = "") -> TurnIntent:
    """Two-phase intent classification: rules first, LLM fallback for ambiguous cases."""
    text = (user_input or "").lower().strip()
    data_state = infer_data_state(session_context)

    # ── Phase 1: Rule-based fast path ──

    # Report request: check early so short keywords like "报告" are not swallowed
    if any(k in text for k in _REPORT_KEYWORDS):
        clarity = "vague" if len(text) < 4 else "clear"
        ambiguities = [{"field": "用户意图", "issue": "输入过短，可能是报告请求也可能是对话"}] if clarity == "vague" else []
        return TurnIntent(
            intent_type="comprehensive_report",
            clarity=clarity,
            data_state=data_state,
            analysis_stage="report" if data_state == "data_loaded" else "scope",
            recommended_action="generate_report" if data_state == "data_loaded" else "request_data",
            reason="用户请求报告或全面分析" + ("（短输入）" if clarity == "vague" else ""),
            ambiguities=ambiguities,
        )

    # Operation keywords in short input: classify but mark vague
    if len(text) < 4 and any(k in text for k in _OPERATION_KEYWORDS) and not any(k in text for k in _ANALYSIS_KEYWORDS):
        return TurnIntent(
            intent_type="data_operation",
            clarity="vague",
            data_state=data_state,
            analysis_stage="execute",
            recommended_action="execute_operation",
            reason="短输入命中操作关键词，意图不明确",
            ambiguities=[{"field": "用户意图", "issue": f"输入过短，可能需要数据操作（{text}），也可能是普通对话"}],
        )

    # Short confirmations and greetings (only if no meaningful keywords matched)
    if text in _CONFIRMATION_KEYWORDS or len(text) < 3:
        return _make("simple_response", "clear", data_state, "follow_up", "answer_directly", "短输入或确认语")
    if any(k in text for k in _CHAT_KEYWORDS) and len(text) < 15:
        return _make("simple_response", "clear", data_state, "follow_up", "answer_directly", "问候或致谢")

    # Knowledge QA: "什么是X" / "解释一下X"
    if any(text.startswith(p) for p in _KNOWLEDGE_QA_PREFIXES):
        return _make("knowledge_qa", "clear", data_state, "follow_up", "answer_directly", "知识问答")

    # Analysis consultation: "怎么分析" / "用什么方法"
    if any(k in text for k in _ANALYSIS_CONSULT_KEYWORDS):
        return _make("analysis_consultation", "vague", data_state, "follow_up", "answer_directly", "分析咨询或方法讨论")

    # Result followup: "为什么说" / "这个结论" / "可靠吗"
    if any(k in text for k in _RESULT_FOLLOWUP_KEYWORDS):
        return _make("result_followup", "clear", data_state, "follow_up", "answer_directly", "追问或质疑已有分析结果")

    # Data requirement (exact match, high priority)
    if any(k in text for k in _DATA_REQUIREMENT_KEYWORDS):
        return _make("data_requirement", "exploratory", data_state, "scope", "request_data", "用户询问分析所需数据")

    # Operation (only if no analysis intent)
    if any(k in text for k in _OPERATION_KEYWORDS) and not any(k in text for k in _ANALYSIS_KEYWORDS):
        return _make("data_operation", "clear", data_state, "execute", "execute_operation", "用户请求明确的数据操作")

    # Guidance: vague "分析一下" without specific direction
    if any(k in text for k in _GUIDANCE_KEYWORDS) and not any(k in text for k in _ANALYSIS_KEYWORDS):
        return _make(
            "intent_negotiation" if data_state == "data_loaded" else "data_requirement",
            "vague", data_state,
            "discover" if data_state == "data_loaded" else "scope",
            "guide_analysis" if data_state == "data_loaded" else "request_data",
            "用户需要分析方向引导",
        )

    # Analysis keywords with specific direction
    if any(k in text for k in _ANALYSIS_KEYWORDS):
        return _make(
            "directed_analysis" if data_state == "data_loaded" else "data_requirement",
            "clear" if data_state == "data_loaded" else "vague",
            data_state,
            "execute" if data_state == "data_loaded" else "scope",
            "run_analysis" if data_state == "data_loaded" else "request_data",
            "用户提出了具体分析问题",
        )

    # ── Phase 2: LLM fallback for unclassified input ──
    result = _try_llm_classify(text, session_context)
    if result is not None:
        intent_type_str, ambiguities = result
        return TurnIntent(
            intent_type=intent_type_str,
            clarity="vague" if ambiguities else "clear",
            data_state=data_state,
            analysis_stage=_stage_for(intent_type_str, data_state),
            recommended_action=_action_for(intent_type_str, data_state),
            reason="LLM分类",
            ambiguities=ambiguities,
        )

    # Default fallback
    return _make(
        "analysis_consultation" if data_state == "data_loaded" else "intent_negotiation",
        "vague", data_state,
        "discover" if data_state == "data_loaded" else "scope",
        "guide_analysis" if data_state == "data_loaded" else "ask_question",
        "默认按分析咨询处理",
    )


def _make(
    intent_type: str, clarity: str, data_state: str,
    stage: str, action: str, reason: str,
) -> TurnIntent:
    return TurnIntent(
        intent_type=intent_type,
        clarity=clarity,
        data_state=data_state,
        analysis_stage=stage,
        recommended_action=action,
        reason=reason,
    )


def _stage_for(intent_type: str, data_state: str) -> str:
    if intent_type in ("simple_response", "knowledge_qa", "analysis_consultation", "result_followup"):
        return "follow_up"
    if intent_type in ("intent_negotiation", "data_requirement"):
        return "scope" if data_state == "no_data" else "discover"
    if intent_type == "data_operation":
        return "execute"
    if intent_type == "directed_analysis":
        return "execute" if data_state == "data_loaded" else "scope"
    if intent_type == "comprehensive_report":
        return "report" if data_state == "data_loaded" else "scope"
    return "discover"


def _action_for(intent_type: str, data_state: str) -> str:
    if intent_type in ("simple_response", "knowledge_qa", "analysis_consultation", "result_followup"):
        return "answer_directly"
    if intent_type in ("intent_negotiation",):
        return "guide_analysis"
    if intent_type == "data_requirement":
        return "request_data"
    if intent_type == "data_operation":
        return "execute_operation"
    if intent_type == "directed_analysis":
        return "run_analysis" if data_state == "data_loaded" else "request_data"
    if intent_type == "comprehensive_report":
        return "generate_report" if data_state == "data_loaded" else "request_data"
    return "guide_analysis"


def _try_llm_classify(text: str, session_context: str) -> tuple[str, list] | None:
    try:
        from data_agent.agent.llm_intent import classify_intent_llm
        result = classify_intent_llm(text, session_context)
        if result is None:
            return None
        return result["intent_type"], result.get("ambiguities", [])
    except Exception:
        return None
