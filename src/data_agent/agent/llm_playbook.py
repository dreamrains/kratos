"""LLM-based playbook selection for ambiguous or complex user requests.

Used as Layer 2 in the two-layer playbook selection architecture.
Triggered when the keyword fast path cannot confidently select a playbook.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Optional

_PLAYBOOK_CATALOG = """
## 可用 Playbook 列表

1. data_understanding — 数据理解：探索数据结构、质量、可行分析路径
   适用：用户不清楚数据能做什么、想先了解数据
   问题类型：description, diagnostic

2. metric_overview — 指标概览：汇总关键指标、分布、排名
   适用：用户想看指标概况、排名、分布特征
   问题类型：description

3. trend_period_comparison — 趋势与对比：分析时间趋势、环比同比、异常变化
   适用：用户想看趋势、对比不同时间段、找异常变化
   问题类型：description, diagnostic, monitoring

4. driver_decomposition — 归因分解：按维度拆解指标变化、找驱动因素
   适用：用户想解释"为什么变了"、找原因、归因分析
   问题类型：diagnostic

5. funnel_conversion — 漏斗转化：分析转化步骤、流失环节
   适用：用户想分析漏斗、转化率、流失、用户路径
   问题类型：diagnostic

6. retention_lifecycle — 留存与生命周期：分析留存、复购、流失倾向
   适用：用户想分析留存、复购、用户生命周期、流失预测
   问题类型：diagnostic, prediction, monitoring

7. evaluation_causal — 因果评估：评估实验/策略效果、因果边界
   适用：用户想评估效果、做因果推断、A/B测试分析
   问题类型：evaluation, causal, decision

8. product_feature_analysis — 产品功能分析：分析功能采纳、价值、行为影响
   适用：用户想分析产品功能效果、功能使用情况
   问题类型：evaluation, diagnostic, opportunity

9. effect_evaluation — 效果评估：评估活动/策略/干预是否改变了目标指标
   适用：用户想评估活动/策略/政策效果、衡量投入产出
   问题类型：evaluation, causal, decision

10. revenue_profitability — 收入与盈利分析：分析收入、成本、ROI、利润
    适用：用户想分析收入、成本、利润率、ROI
    问题类型：description, evaluation, decision

11. user_behavior_analysis — 用户行为分析：分析用户频次、金额、偏好、分群
    适用：用户想了解用户行为模式、用户分群、行为偏好
    问题类型：description, diagnostic, opportunity

12. growth_opportunity — 增长机会：识别后续分析方向、优化机会
    适用：用户想找更多分析方向、发现优化机会
    问题类型：opportunity, decision

13. forecast_decision_simulation — 预测与决策模拟：预测指标、模拟场景、辅助决策
    适用：用户想做预测、模拟、预算规划、what-if分析
    问题类型：prediction, decision, monitoring
"""

_SELECTION_PROMPT_TEMPLATE = """\
你是一个数据分析 playbook 选择器。根据用户请求和数据特征，选择最合适的分析 playbook。

{_catalog}

## 选择规则
1. primary playbook 必须是最匹配用户意图的
2. supporting playbooks 最多2个，用于补充分析视角
3. 如果用户意图模糊，选择覆盖面最广的 playbook
4. 如果数据特征不支持某个 playbook，避免选择它
5. 给出选择理由

## 示例

用户: "最近一个月的转化率好像在下降，帮我看看到底是哪个环节出了问题"
数据: 有时间列、转化率列、步骤列
→ {{"primary": "funnel_conversion", "supporting": ["trend_period_comparison", "driver_decomposition"], "reason": "用户关注转化率下降，需要先分析漏斗各环节，再用趋势对比确认变化时间点"}}

用户: "这波营销活动到底值不值"
数据: 有活动标签、收入指标、成本数据
→ {{"primary": "effect_evaluation", "supporting": ["revenue_profitability", "growth_opportunity"], "reason": "效果评估需求，需要衡量活动对目标指标的影响，同时分析投入产出"}}

用户: "帮我看看这份数据能分析什么"
数据: 已加载，有日期、金额、渠道等字段
→ {{"primary": "data_understanding", "supporting": ["metric_overview", "trend_period_comparison"], "reason": "用户意图不明确，先做数据理解再推荐分析方向"}}

用户: "为什么上个月收入突然掉了20%"
数据: 有时间列、收入指标、维度列
→ {{"primary": "driver_decomposition", "supporting": ["trend_period_comparison", "revenue_profitability"], "reason": "归因分析需求，需要拆解收入下降的驱动因素"}}

用户: "预测一下下季度能做多少"
数据: 有历史月度收入数据
→ {{"primary": "forecast_decision_simulation", "supporting": ["trend_period_comparison"], "reason": "预测需求，基于历史趋势做外推"}}

用户: "不同渠道的用户付费行为有什么差异"
数据: 有渠道列、付费金额、用户ID
→ {{"primary": "user_behavior_analysis", "supporting": ["metric_overview"], "reason": "用户行为对比分析，需要分渠道分析付费行为模式"}}

## 当前输入

用户请求: __USER_INPUT__
数据特征: __DATA_FEATURES__
已选关键词playbook（如果有）: __KEYWORD_RESULT__

请返回 JSON:
{{"primary": "playbook_id", "supporting": ["id1", "id2"], "reason": "选择理由"}}"""

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
        raise _TimeoutException("LLM playbook selection timed out")

    if error_holder[0] is not None:
        raise error_holder[0]

    return result_holder[0]


def select_playbook_llm(
    user_input: str,
    data_features: str = "",
    keyword_result: str = "",
    client=None,
) -> Optional[dict]:
    """Use LLM to select the best playbook for ambiguous user requests.

    Returns dict with 'primary', 'supporting', 'reason' keys, or None on failure.
    """
    if client is None:
        client = _get_client()

    prompt = _SELECTION_PROMPT_TEMPLATE.replace("__USER_INPUT__", user_input).replace(
        "__DATA_FEATURES__", data_features or "未知（数据尚未加载或无特征描述）",
    ).replace(
        "__KEYWORD_RESULT__", keyword_result or "无（关键词未匹配）",
    ).replace(
        "{_catalog}", _PLAYBOOK_CATALOG,
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        response = _call_with_timeout(
            client.chat,
            (messages,),
            {"system": "你是一个JSON输出器，只返回JSON，不要其他内容。"},
            8,
        )
    except (_TimeoutException, Exception):
        return None

    if not response or not response.text:
        return None

    parsed = _extract_json(response.text)
    if parsed is None:
        return None

    primary = parsed.get("primary", "")
    if not primary:
        return None

    from data_agent.agent.method_playbooks import PLAYBOOKS
    if primary not in PLAYBOOKS:
        return None

    supporting = parsed.get("supporting", [])
    if not isinstance(supporting, list):
        supporting = []
    supporting = [s for s in supporting if s in PLAYBOOKS and s != primary][:2]

    return {
        "primary": primary,
        "supporting": supporting,
        "reason": parsed.get("reason", ""),
    }
