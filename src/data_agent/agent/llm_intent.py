"""LLM-based intent classification for ambiguous or natural language inputs.

Used as Layer 2 in the two-layer intent classification architecture.
Triggered when the fast rule path cannot confidently classify user input.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Optional

VALID_INTENT_TYPES = frozenset({
    "simple_response",
    "knowledge_qa",
    "analysis_consultation",
    "result_followup",
    "intent_negotiation",
    "data_requirement",
    "data_operation",
    "directed_analysis",
    "comprehensive_report",
})

_CLASSIFICATION_PROMPT_TEMPLATE = """\
你是一个数据分析助手的意图分类器。根据用户输入和会话上下文，判断用户的意图类型。

## 意图类型定义

- simple_response: 简单回应（问候、确认、感谢、闲聊）
- knowledge_qa: 知识问答（询问概念、方法、定义，不涉及具体数据分析）
- analysis_consultation: 分析咨询（询问分析方法、思路、建议，不需要执行分析）
- result_followup: 结果追问（质疑、追问之前的分析结果和结论）
- intent_negotiation: 意图协商（模糊的分析需求，需要引导用户明确方向）
- data_requirement: 数据需求（询问需要什么数据、如何准备数据）
- data_operation: 数据操作（明确的筛选、排序、导出、分组、汇总等操作请求）
- directed_analysis: 定向分析（有明确方向的分析请求：趋势、对比、归因、预测等）
- comprehensive_report: 综合报告（请求完整分析报告、全面分析）

## 歧义检测
检测以下类型的歧义：
- 指标不明确（用户说"分析一下"但没说分析什么指标）
- 维度不明确（用户说"对比"但没说按什么维度）
- 时间范围不明确（用户说"趋势"但没说多长时间）
- 方法不明确（用户说"分析"但可能是多种分析方向）

## 示例

用户: "这数据感觉怪怪的"
→ {"intent_type": "intent_negotiation", "reason": "用户感觉数据有问题但表述模糊", "ambiguities": [{"field": "问题方向", "issue": "不确定是数据质量问题还是业务异常"}]}

用户: "帮我看下哪个渠道最赚钱"
→ {"intent_type": "directed_analysis", "reason": "有明确方向（渠道排名+金额指标）", "ambiguities": []}

用户: "我觉得上个月的销售数据不太对劲，能帮我查查吗"
→ {"intent_type": "directed_analysis", "reason": "用户怀疑数据异常，需要探索性分析", "ambiguities": [{"field": "异常范围", "issue": "不明确哪些指标、哪个时间段可能有问题"}]}

用户: "这份数据能看出什么"
→ {"intent_type": "intent_negotiation", "reason": "用户没有明确方向，需要推荐分析路径", "ambiguities": [{"field": "分析方向", "issue": "用户希望获得推荐"}]}

用户: "把北京地区的数据按月汇总一下"
→ {"intent_type": "data_operation", "reason": "明确的筛选+分组操作请求", "ambiguities": []}

用户: "上次说的那个结论，有更详细的解释吗"
→ {"intent_type": "result_followup", "reason": "追问之前分析结论的细节", "ambiguities": []}

用户: "A/B测试和因果分析有什么区别"
→ {"intent_type": "knowledge_qa", "reason": "纯知识问答，不涉及具体数据", "ambiguities": []}

用户: "我想知道用户为什么会流失"
→ {"intent_type": "directed_analysis", "reason": "有明确分析目标（归因分析）", "ambiguities": [{"field": "流失定义", "issue": "需要确认什么算流失用户"}]}

用户: "这个活动到底值不值得做"
→ {"intent_type": "directed_analysis", "reason": "效果评估/ROI分析需求", "ambiguities": [{"field": "评估范围", "issue": "需要确认活动范围、评估指标和时间窗口"}]}

## 当前输入

用户输入: __USER_INPUT__
会话上下文: __SESSION_CONTEXT__

请返回 JSON:
{"intent_type": "...", "reason": "...", "ambiguities": [{"field": "...", "issue": "..."}]}"""

_client: Optional[object] = None


def _get_client():
    global _client
    if _client is None:
        from data_agent.llm.client import LLMClient
        _client = LLMClient(max_tokens=300)
    return _client


class _TimeoutException(Exception):
    pass


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            text = text[brace_start:brace_end + 1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _call_with_timeout(fn, args, kwargs, timeout_seconds):
    result_holder = [None]
    error_holder = [None]

    def target():
        try:
            result_holder[0] = fn(*args, **kwargs)
        except Exception as exc:
            error_holder[0] = exc

    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        raise _TimeoutException("LLM classification timed out")

    if error_holder[0] is not None:
        raise error_holder[0]

    return result_holder[0]


def classify_intent_llm(
    user_input: str,
    session_context: str,
    client=None,
) -> Optional[dict]:
    if client is None:
        client = _get_client()

    prompt = _CLASSIFICATION_PROMPT_TEMPLATE.replace("__USER_INPUT__", user_input).replace(
        "__SESSION_CONTEXT__", session_context or "无上下文",
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        kwargs = {"system": "你是一个JSON输出器，只返回JSON，不要其他内容。"}
        if getattr(client, "manages_request_timeout", False) is True:
            response = client.chat(messages, **kwargs)
        else:
            response = _call_with_timeout(client.chat, (messages,), kwargs, 8)
    except (_TimeoutException, Exception):
        return None

    if not response or not response.text:
        return None

    parsed = _extract_json(response.text)
    if parsed is None:
        return None

    intent_type = parsed.get("intent_type", "")
    if intent_type not in VALID_INTENT_TYPES:
        return None

    ambiguities = parsed.get("ambiguities", [])
    if not isinstance(ambiguities, list):
        ambiguities = []

    return {
        "intent_type": intent_type,
        "reason": parsed.get("reason", ""),
        "ambiguities": ambiguities,
    }
