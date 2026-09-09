"""Intent classification with rule-based fast path and LLM fallback.

Two-layer architecture:
  Layer 1: Fast rule path — handles clear, unambiguous patterns (greetings,
           confirmations, explicit report/operation keywords). Returns immediately
           with clarity="clear" when confident.
  Layer 2: LLM semantic classification — handles all ambiguous, vague, or
           natural language inputs. Triggered when fast path returns no result
           or returns a vague result.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from data_agent.file_formats import SUPPORTED_DATA_EXTENSIONS

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
ExecutionReadiness = Literal["ready", "pending_load", "missing_data", "insufficient_data"]
AnalysisStage = Literal["discover", "scope", "plan", "execute", "report", "follow_up"]
RecommendedAction = Literal[
    "answer_directly",
    "ask_question",
    "guide_analysis",
    "request_data",
    "load_then_analyze",
    "execute_operation",
    "run_analysis",
    "synthesize_analysis",
]


@dataclass
class TurnIntent:
    intent_type: IntentType
    clarity: Clarity
    data_state: DataState
    analysis_stage: AnalysisStage
    recommended_action: RecommendedAction
    execution_readiness: ExecutionReadiness = "missing_data"
    reason: str = ""
    ambiguities: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Keyword sets for fast path ────────────────────────────

_CHAT_KEYWORDS = (
    "你好", "hello", "hi", "谢谢", "感谢", "thanks", "thank you",
    # Whole-phrase politeness: stripping bare "谢谢" from "谢谢你的分析"
    # would leave a noun phrase that hijacks the main task, so the full
    # polite templates are stripped as units. A real task still survives:
    # "谢谢，请继续分析收入趋势" strips to a non-empty imperative.
    "谢谢你的分析", "谢谢您的分析", "感谢你的分析", "感谢您的分析",
    "谢谢你的帮助", "谢谢您的帮助", "感谢你的帮助", "谢谢你的解释",
    "辛苦了", "麻烦你了", "多谢了",
)
_CONFIRMATION_KEYWORDS = (
    "好的", "明白", "明白了", "了解", "了解了", "知道了", "收到", "ok", "okay",
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
    "漏斗", "转化", "贡献", "效果", "情景模拟", "模拟分析", "是否值得", "长期运营", "有没有",
    "分布", "相关性", "增长", "下降", "上升",
    "频次", "频率", "最高", "最低", "排名", "排行", "前几", "最多", "最少",
    "trend", "compare", "why", "reason", "decline", "drop", "driver",
    "forecast", "predict", "effect", "causal", "funnel", "conversion",
    "evaluate", "worth", "analyze", "correlation", "top", "rank", "ranking",
)
_GUIDANCE_KEYWORDS = (
    "不知道如何分析", "帮我看看", "看看这份数据", "分析一下",
    "有什么可以分析", "帮我分析", "看看数据",
)
# Explicit execution imperatives: when one of these appears together with a
# consultation keyword, the executable request is the main task and the
# consultation ("并给出分析建议") becomes an output requirement.
_EXECUTION_REQUEST_MARKERS = (
    "请分析", "请帮我分析", "帮我分析", "麻烦分析", "麻烦帮我分析",
    "请直接分析", "直接分析", "开始分析", "来分析一下", "分析并", "并分析",
    "请计算", "帮我计算", "请预测", "帮我预测", "请对比", "帮我对比",
    "请执行分析", "跑一下分析",
    "please analyze", "help me analyze", "analyze and", "and analyze",
    "please calculate", "please compute", "please predict", "please compare",
    "run the analysis", "start the analysis",
)
# Leading consultation questions keep the consultation branch even when an
# execution imperative appears later: the main task is then genuinely mixed.
_CONSULT_QUESTION_PREFIXES = (
    "怎么", "如何", "应该怎么", "应该如何", "怎样", "该怎样", "该不该", "要不要",
    "是否应该", "哪种方法", "什么方法",
    "how to", "how should", "which method", "what method",
)


# ── Legacy compatibility ──────────────────────────────────

_DATA_FILE_EXTENSIONS = tuple(sorted(SUPPORTED_DATA_EXTENSIONS))
_HYPOTHETICAL_DATA_PHRASES = (
    "what csv", "which csv", "what files", "which files", "what data",
    "need to prepare", "should i prepare", "should we prepare",
)

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


def has_loadable_data_reference(text: str) -> bool:
    lowered = (text or "").lower()
    if any(phrase in lowered for phrase in _HYPOTHETICAL_DATA_PHRASES):
        return False
    return any(ext in lowered for ext in _DATA_FILE_EXTENSIONS)


def infer_execution_readiness(user_input: str, session_context: str = "") -> ExecutionReadiness:
    data_state = infer_data_state(session_context)
    if data_state == "data_loaded":
        return "ready"
    if data_state == "insufficient_data":
        return "insufficient_data"
    if has_loadable_data_reference(user_input):
        return "pending_load"
    return "missing_data"


def plan_turn_intent(
    user_input: str,
    session_context: str = "",
    *,
    llm_client=None,
) -> TurnIntent:
    """Two-layer intent classification: fast rules → LLM fallback."""
    text = (user_input or "").lower().strip()
    data_state = infer_data_state(session_context)
    readiness = infer_execution_readiness(user_input, session_context)

    # ── Layer 1: Fast rule path ──
    fast_result = _try_fast_path(text, data_state, readiness)

    # If fast path is confident, return immediately (no LLM cost)
    if fast_result is not None and fast_result.clarity == "clear":
        return fast_result

    # ── Layer 2: LLM semantic classification ──
    # Triggered when fast path returns nothing or returns vague result
    llm_result = _try_llm_classify(text, session_context, client=llm_client)
    if llm_result is not None:
        intent_type, ambiguities = llm_result
        return TurnIntent(
            intent_type=intent_type,
            clarity="vague" if ambiguities else "clear",
            data_state=data_state,
            analysis_stage=_stage_for(intent_type, data_state, readiness),
            recommended_action=_action_for(intent_type, data_state, readiness),
            execution_readiness=readiness,
            reason="LLM语义分类",
            ambiguities=ambiguities,
        )

    # ── Layer 3: Fallback ──
    # Use fast path vague result if available, otherwise default
    if fast_result is not None:
        return fast_result
    fallback_intent = "analysis_consultation" if data_state == "data_loaded" else "intent_negotiation"
    return _make(
        fallback_intent,
        "vague", data_state,
        "discover" if data_state == "data_loaded" else "scope",
        "guide_analysis" if data_state == "data_loaded" else "ask_question",
        "默认按分析咨询处理",
    )


def _try_fast_path(text: str, data_state: DataState, readiness: ExecutionReadiness) -> TurnIntent | None:
    """Layer 1: rule-based classification for clear, unambiguous patterns.

    Returns None when no rule matches confidently. Returns a TurnIntent with
    clarity="clear" for confident matches, or clarity="vague" for partial matches.

    The fast path only accepts inputs whose main task is unambiguous: pure
    greetings, negation-free keyword hits, or compound requests whose main
    task is still identifiable. Negated keywords never trigger their branch,
    and contradictory or double-negated input defers to the semantic layer.
    """
    from data_agent.agent.request_language import keyword_group_state

    # ── Ultra-short input (< 3 chars) ──
    if len(text) < 3:
        # Check operation/report keywords before falling through to conversation
        if text in _OPERATION_KEYWORDS:
            return _make("data_operation", "clear", data_state, "execute", "execute_operation", "短输入命中操作关键词")
        if text == "报告":
            return _make(
                "comprehensive_report",
                "clear", data_state,
                "report" if data_state == "data_loaded" else "scope",
                "synthesize_analysis" if data_state == "data_loaded" else "request_data",
                "报告关键词",
            )
        if text in _CONFIRMATION_KEYWORDS:
            return _make("simple_response", "clear", data_state, "follow_up", "answer_directly", "短输入确认语")
        return _make("simple_response", "clear", data_state, "follow_up", "answer_directly", "短输入或确认语")

    # ── Pure greeting / thanks: the whole input is conversational filler ──
    # A greeting followed by a real request must not swallow the main task,
    # so only conversation-only input takes this branch.
    if _is_pure_chat(text):
        return _make("simple_response", "clear", data_state, "follow_up", "answer_directly", "问候或致谢")

    # ── Confirmations ──
    if text in _CONFIRMATION_KEYWORDS:
        return _make("simple_response", "clear", data_state, "follow_up", "answer_directly", "确认语")

    # ── Report request (high priority, negation-aware) ──
    report_state = keyword_group_state(text, _REPORT_KEYWORDS)
    if report_state == "affirmative":
        return _make(
            "comprehensive_report",
            "clear", data_state,
            _stage_for("comprehensive_report", data_state, readiness),
            _action_for("comprehensive_report", data_state, readiness),
            "用户请求报告或全面分析",
        )
    if report_state == "ambiguous":
        # Double negation around a report request is contradictory; the
        # semantic layer decides instead of a forced confident label.
        return None

    # ── Knowledge QA (starts with question prefix) ──
    if any(text.startswith(p) for p in _KNOWLEDGE_QA_PREFIXES):
        return _make("knowledge_qa", "clear", data_state, "follow_up", "answer_directly", "知识问答")

    # ── Analysis consultation vs. execution (compound inputs) ──
    consult_state = keyword_group_state(text, _ANALYSIS_CONSULT_KEYWORDS)
    has_execution_marker = any(marker in text for marker in _EXECUTION_REQUEST_MARKERS)
    if consult_state == "ambiguous":
        return None
    if consult_state == "affirmative":
        if not has_execution_marker:
            return _make("analysis_consultation", "clear", data_state, "follow_up", "answer_directly", "分析咨询或方法讨论")
        if text.startswith(_CONSULT_QUESTION_PREFIXES):
            # A leading method question plus an execution imperative leaves
            # the main task genuinely unclear; defer to the semantic layer.
            return None
        # Execution imperative with a consultative tail: the main task stays
        # executable and the consultation becomes an output requirement.
        # Fall through to the analysis branches below.

    # ── Result followup ──
    if any(k in text for k in _RESULT_FOLLOWUP_KEYWORDS):
        return _make("result_followup", "clear", data_state, "follow_up", "answer_directly", "追问或质疑已有分析结果")

    # ── Data requirement ──
    if any(k in text for k in _DATA_REQUIREMENT_KEYWORDS) or any(k in text for k in _HYPOTHETICAL_DATA_PHRASES):
        return _make("data_requirement", "clear", data_state, "scope", "request_data", "用户询问分析所需数据")

    # ── Pure data operation (only when no analysis keywords present) ──
    operation_state = keyword_group_state(text, _OPERATION_KEYWORDS)
    analysis_state = keyword_group_state(text, _ANALYSIS_KEYWORDS)
    if analysis_state == "ambiguous":
        return None
    if operation_state == "affirmative" and analysis_state != "affirmative":
        if len(text) < 4:
            return _make(
                "data_operation", "vague", data_state, "execute", "execute_operation",
                "短输入命中操作关键词，意图不明确",
                [{"field": "用户意图", "issue": f"输入过短，可能需要数据操作（{text}），也可能是普通对话"}],
            )
        return _make("data_operation", "clear", data_state, "execute", "execute_operation", "用户请求明确的数据操作")

    # ── Guidance: vague "分析一下" without specific direction ──
    if any(k in text for k in _GUIDANCE_KEYWORDS) and analysis_state != "affirmative":
        return _make(
            "intent_negotiation" if data_state == "data_loaded" else "data_requirement",
            "clear", data_state,
            "discover" if data_state == "data_loaded" else "scope",
            "guide_analysis" if data_state == "data_loaded" else "request_data",
            "用户需要分析方向引导",
        )

    # ── Analysis keywords with specific direction ──
    if analysis_state == "affirmative":
        return _make(
            "directed_analysis",
            "clear", data_state,
            _stage_for("directed_analysis", data_state, readiness),
            _action_for("directed_analysis", data_state, readiness),
            "用户提出了具体分析问题",
        )

    # ── No confident rule match → return None to trigger LLM ──
    return None


_CHAT_FILLER_PARTICLES = ("呀", "啊", "呢", "吧", "啦", "哦", "哈", "嘿", "嗯", "哟", "呦", "诶")
_PUNCT_PATTERN = re.compile(r"[\s，。！!？?~,.;；：:、]+")


def _is_pure_chat(text: str) -> bool:
    """True only when the input is entirely greeting/thanks/confirmation filler."""
    remainder = text
    # Longest first: stripping "谢谢" before "谢谢你的分析" would leave a
    # noun phrase that looks like an analysis request.
    for keyword in sorted((*_CHAT_KEYWORDS, *_CONFIRMATION_KEYWORDS), key=len, reverse=True):
        if keyword:
            remainder = remainder.replace(keyword, " ")
    remainder = _PUNCT_PATTERN.sub("", remainder)
    remainder = "".join(ch for ch in remainder if ch not in _CHAT_FILLER_PARTICLES)
    return remainder == ""


def _make(
    intent_type: str, clarity: str, data_state: str,
    stage: str, action: str, reason: str,
    ambiguities: list[dict] | None = None,
    execution_readiness: str | None = None,
) -> TurnIntent:
    if execution_readiness is None:
        if action in ("run_analysis", "synthesize_analysis") or data_state == "data_loaded":
            execution_readiness = "ready"
        elif action == "load_then_analyze":
            execution_readiness = "pending_load"
        else:
            execution_readiness = "missing_data"
    return TurnIntent(
        intent_type=intent_type,
        clarity=clarity,
        data_state=data_state,
        analysis_stage=stage,
        recommended_action=action,
        execution_readiness=execution_readiness,
        reason=reason,
        ambiguities=ambiguities or [],
    )


def _stage_for(intent_type: str, data_state: str, readiness: str | None = None) -> str:
    readiness = readiness or ("ready" if data_state == "data_loaded" else "missing_data")
    if intent_type in ("simple_response", "knowledge_qa", "analysis_consultation", "result_followup"):
        return "follow_up"
    if intent_type in ("intent_negotiation", "data_requirement"):
        return "scope" if data_state == "no_data" else "discover"
    if intent_type == "data_operation":
        return "execute"
    if intent_type == "directed_analysis":
        return "execute" if readiness == "ready" else "scope"
    if intent_type == "comprehensive_report":
        return "report" if readiness == "ready" else "scope"
    return "discover"


def _action_for(intent_type: str, data_state: str, readiness: str | None = None) -> str:
    readiness = readiness or ("ready" if data_state == "data_loaded" else "missing_data")
    if intent_type in ("simple_response", "knowledge_qa", "analysis_consultation", "result_followup"):
        return "answer_directly"
    if intent_type in ("intent_negotiation",):
        return "guide_analysis"
    if intent_type == "data_requirement":
        return "request_data"
    if intent_type == "data_operation":
        return "execute_operation"
    if intent_type == "directed_analysis":
        if readiness == "ready":
            return "run_analysis"
        if readiness == "pending_load":
            return "load_then_analyze"
        return "request_data"
    if intent_type == "comprehensive_report":
        if readiness == "ready":
            return "synthesize_analysis"
        if readiness == "pending_load":
            return "load_then_analyze"
        return "request_data"
    return "guide_analysis"


def _try_llm_classify(text: str, session_context: str, *, client=None) -> tuple[str, list] | None:
    try:
        from data_agent.agent.llm_intent import classify_intent_llm
        result = classify_intent_llm(text, session_context, client=client)
        if result is None:
            return None
        return result["intent_type"], result.get("ambiguities", [])
    except Exception:
        return None
