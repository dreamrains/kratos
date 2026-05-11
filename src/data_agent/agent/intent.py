"""Lightweight intent planner for analysis conversations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


IntentType = Literal[
    "chat",
    "operation",
    "analysis_guidance",
    "data_requirement",
    "direct_analysis",
    "report",
]
Clarity = Literal["clear", "vague", "exploratory"]
DataState = Literal["no_data", "data_loaded", "insufficient_data", "unknown"]
AnalysisStage = Literal["discover", "scope", "plan", "execute", "report", "follow_up"]
RecommendedAction = Literal[
    "answer",
    "ask_question",
    "propose_methods",
    "request_data",
    "inspect_data",
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

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataRequirement:
    topic: str
    required_data: list[str] = field(default_factory=list)
    recommended_data: list[str] = field(default_factory=list)
    limitations_without_data: list[str] = field(default_factory=list)


@dataclass
class AnalysisSpec:
    goal: str
    question_type: str
    metrics: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    time_scope: str = ""
    required_data: list[str] = field(default_factory=list)
    method_plan: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class EvidenceRecord:
    claim: str
    dataset: str
    method: str
    tool_calls: list[str] = field(default_factory=list)
    result_summary: str = ""
    limitations: list[str] = field(default_factory=list)
    confidence: str = "medium"


_CHAT_KEYWORDS = ("你好", "hello", "hi", "谢谢", "感谢", "thanks")
_OPERATION_KEYWORDS = (
    "汇总", "导出", "转换", "筛选", "过滤", "排序", "重命名", "选择",
    "合并", "透视", "分组", "按周", "按月", "按天", "按季", "按年",
    "计算", "求和", "求平均", "select", "filter", "rename", "sort",
)
_REPORT_KEYWORDS = ("报告", "完整分析", "全面分析", "综合分析", "分析报告", "完整报告")
_DATA_REQUIREMENT_KEYWORDS = (
    "需要哪些数据", "要哪些数据", "准备哪些数据", "获取哪些数据", "什么数据",
    "需要什么表", "数据需求", "没有数据", "还缺什么数据",
)
_GUIDANCE_KEYWORDS = (
    "不知道如何分析", "怎么分析", "如何分析", "分析方法", "分析思路",
    "帮我看看", "看看这份数据", "分析一下", "有什么可以分析",
)
_ANALYSIS_KEYWORDS = (
    "趋势", "对比", "比较", "归因", "为什么", "原因", "预测", "异常",
    "漏斗", "转化", "贡献", "效果", "是否值得", "长期运营", "有没有",
)


_DATA_REQUIREMENT_KEYWORDS += (
    "what data", "which data", "data required", "required data", "data requirements",
    "need data", "what datasets", "which datasets",
)

_ANALYSIS_KEYWORDS += (
    "trend", "compare", "comparison", "why", "reason", "decline", "drop", "driver",
    "decomposition", "attribution", "forecast", "predict", "prediction", "evaluate",
    "evaluation", "effect", "causal", "worth", "long-term", "long term", "funnel",
    "conversion", "drop-off", "dropoff", "retention", "churn", "roi", "what-if",
)


def infer_data_state(session_context: str = "") -> DataState:
    if session_context and ("rows" in session_context or "columns:" in session_context):
        return "data_loaded"
    return "no_data"


def plan_turn_intent(user_input: str, session_context: str = "") -> TurnIntent:
    """Infer a deterministic, explainable turn intent.

    This is intentionally rule-based for Phase 1.  The output is structured so a
    later LLM classifier can be swapped in without changing downstream prompts.
    """
    text = (user_input or "").lower()
    data_state = infer_data_state(session_context)

    if any(k in text for k in _DATA_REQUIREMENT_KEYWORDS):
        return TurnIntent(
            intent_type="data_requirement",
            clarity="exploratory",
            data_state=data_state,
            analysis_stage="scope",
            recommended_action="request_data",
            reason="用户在询问分析所需数据或数据缺口",
        )

    if any(k in text for k in _REPORT_KEYWORDS):
        return TurnIntent(
            intent_type="report",
            clarity="clear",
            data_state=data_state,
            analysis_stage="report",
            recommended_action="generate_report" if data_state == "data_loaded" else "request_data",
            reason="用户请求报告或全面分析",
        )

    if any(k in text for k in _OPERATION_KEYWORDS) and not any(k in text for k in _ANALYSIS_KEYWORDS):
        return TurnIntent(
            intent_type="operation",
            clarity="clear",
            data_state=data_state,
            analysis_stage="execute",
            recommended_action="run_analysis",
            reason="用户请求明确的数据操作",
        )

    if any(k in text for k in _GUIDANCE_KEYWORDS):
        return TurnIntent(
            intent_type="analysis_guidance" if data_state == "data_loaded" else "data_requirement",
            clarity="vague",
            data_state=data_state,
            analysis_stage="discover" if data_state == "data_loaded" else "scope",
            recommended_action="propose_methods" if data_state == "data_loaded" else "request_data",
            reason="用户需要分析方向引导",
        )

    if any(k in text for k in _ANALYSIS_KEYWORDS):
        return TurnIntent(
            intent_type="direct_analysis" if data_state == "data_loaded" else "data_requirement",
            clarity="clear" if data_state == "data_loaded" else "exploratory",
            data_state=data_state,
            analysis_stage="execute" if data_state == "data_loaded" else "scope",
            recommended_action="run_analysis" if data_state == "data_loaded" else "request_data",
            reason="用户提出了业务分析问题",
        )

    if any(k in text for k in _CHAT_KEYWORDS) or len(text.strip()) < 8:
        return TurnIntent(
            intent_type="chat",
            clarity="clear",
            data_state=data_state,
            analysis_stage="follow_up",
            recommended_action="answer",
            reason="普通对话或短输入",
        )

    return TurnIntent(
        intent_type="analysis_guidance" if data_state == "data_loaded" else "data_requirement",
        clarity="vague",
        data_state=data_state,
        analysis_stage="discover" if data_state == "data_loaded" else "scope",
        recommended_action="propose_methods" if data_state == "data_loaded" else "request_data",
        reason="默认按分析咨询处理",
    )
