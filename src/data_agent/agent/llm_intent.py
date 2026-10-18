"""LLM-based intent classification for ambiguous or natural language inputs.

Used as Layer 2 in the two-layer intent classification architecture.
Triggered when the fast rule path cannot confidently classify user input.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Optional

logger = logging.getLogger(__name__)

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

## 当前计划关系
会话上下文可能给出 current_analysis_plan_id 与 goal。仅当本轮明确是在继续该目标时，
返回完全相同的 continuation_of_plan_id；新目标、改动分析范围或无法判断时返回空字符串。
这只标识计划关系，不确认数据、业务口径或分析结论。

## 用户要求的输出
对需要实际分析的请求，可列出全部独立需求（最多128项，不得截断）的原文片段，分别标记
result、presentation、conditional_action 或 gap。exact_span 必须逐字取自
本轮用户输入；这只记录用户所求，不表示已完成、证据充分或建议安全。
presentation 包含表达方式与交付形式的限制，例如折叠、完整展示、导出可访问性；
即使这类要求写成“如果……就……”，也不是业务行动。
conditional_action 仅用于用户要求根据分析结果决定现实中的业务动作，
并给出触发或停止条件；不要把正文排版、数据交付或工具操作标为业务行动。
若用户要求把现有结果换一种表达，kind=presentation，并按语义选择
presentation_style：business、analyst、manager、plain 或 technical。
只标记表达方式，不把它当新数据或对行动建议的证据授权。
presentation_role=style 仅指用户明确改变受众/语言/深度的偏好；
图表、摘要、完整来源和导出要求是 delivery，解释已有结果是 explanation。
style 同时提议 presentation_scope：仅原文明确持续到后续轮次时为 session，
其余（含仅本轮及未明确持续）为 turn。本轮偏好不撤回会话偏好。
不能因风格变化撤回计算、图表或数据覆盖需求。
同一原文要求计算并解释时可给purposes=["interpretation"]，原结果目标仍单独核验。
原文需求必须保留；只登记业务范围，不猜工具、统计键或结果路径。执行前再声明必要交付。
当前上下文有唯一未完成任务或原答案，“好的，继续。”承接未完成交付，
不是新知识问答；按真实关系给result_followup/继续原计划以及原source_answer_id。
纯知识咨询仍为knowledge；方案条件可在答复中分支说明，不作为执行阻塞。
复用既有接受答案时，可给 source_answer_id="上下文中的原接受答案ID"；
不猜旧文件名、旧 packet 或最新缓存。数据存在不代表已计算。

## 需求变更与实际目标
requested_outputs 每项可含 op=add/replace/withdraw/reuse，替换/撤回/等价续问复用必须指明上下文中真实 target_id。reuse只给原文、原目标ID和同类kind，保留原业务范围与交付；不同业务目标用add，不因相同文字或候选工具自动合并；数据新版用replace，不复用旧版本目标。
result 可给business_scope={"datasets":["真实业务别名"],"metrics":["原指标列"],"quantity":"sum","parameters":{"period_a":"原业务窗口"}}。
纯操作可声明business_scope.operation={action:公开操作名,arguments:原调用参数}；数据派生/清洗同时给datasets，文件/扩展操作不附会数据来源。操作效果不属于数据事实。
quantity只表示用户要求的统计量（sum、mean、rows等），不要猜测技术工具或结果路径。缺少明确范围仍保留原需求为未计算，由执行前计划声明必要交付。多个来源和指标分别覆盖，原业务范围不可静默改变。
knowledge 用于一般知识咨询；不要因为存在数据自动要求执行分析。缺少完整解析仍保留原需求为未计算，不谎报覆盖。

## 本轮上传与实质口径
current_uploads是服务器验票并加载的本轮附件，prior_objects是上传前业务数据对象。
用户明确要求业务别名时，upload_bindings=[{"upload_id":"本轮真实票据ID","dataset":"逐字用户别名","relation":"new","exact_span":"完整原文命名要求"}]。
明确同一对象新版时，relation="replace"并给先前精确dataset；用户逐字点名对象时同时给object_span="原文精确业务别名"，该引用必须唯一出现于exact_span和本轮原文。其他已加载对象不造成该明确引用的歧义；未点名时仅在本轮票据和先前对象都唯一时直接替换。
不能靠文件名v1/v2、大小写或近似拼写判断对象关系；关系不唯一时标记歧义并询问。
实质计算口径尚未确定或用户要求当前版本重新确认时，measurement_mappings=[{"exact_span":"原文指标名","dataset":"确定的业务别名","column":"真实账面数值列","cost_scopes":[["真实成本列"],["成本列一","成本列二"]]}]。
这只是待确认的候选列范围；宿主核验原文、列、数据版本并生成既有公式确认。不要把另一文件的历史回答当作当前授权。
没有待确认口径时不要提议；无文件方案咨询按不同条件说明，不阻塞。

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
{"intent_type": "...", "reason": "...", "ambiguities": [{"field": "...", "issue": "..."}], "continuation_of_plan_id": "", "requested_outputs": [{"exact_span": "用户原文片段", "kind": "result"}]}"""

_client: Optional[object] = None


def _get_client():
    global _client
    if _client is None:
        from data_agent.llm.client import LLMClient
        _client = LLMClient()
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
    except Exception as exc:
        logger.warning("Intent classification call failed: %s", type(exc).__name__)
        return None

    if not response or not response.text:
        logger.info("Intent classification has no visible text: finish_reason=%s",
                    getattr(response, "finish_reason", "missing_response"))
        return None

    parsed = _extract_json(response.text)
    if parsed is None:
        logger.info("Intent classification JSON invalid: finish_reason=%s",
                    getattr(response, "finish_reason", "unknown"))
        return None

    intent_type = parsed.get("intent_type", "")
    if not isinstance(intent_type,str) or intent_type not in VALID_INTENT_TYPES:
        logger.info("Intent classification route invalid: finish_reason=%s",
                    getattr(response, "finish_reason", "unknown"))
        return None

    ambiguities = parsed.get("ambiguities", [])
    if not isinstance(ambiguities, list):
        ambiguities = []
    ambiguities = [row for row in ambiguities if isinstance(row,dict) and isinstance(row.get("field"),str) and isinstance(row.get("issue"),str)]

    proposed_outputs = parsed.get("requested_outputs")
    requested_outputs = []
    seen_spans = set()
    if isinstance(proposed_outputs, list) and len(proposed_outputs) <= 128:
        for item in proposed_outputs:
            if not isinstance(item, dict):
                continue
            span = item.get("exact_span")
            kind = item.get("kind")
            if (not isinstance(span, str) or not 1 <= len(span) <= 4000
                    or not isinstance(kind,str) or span not in user_input
                    or kind not in {"result", "knowledge", "presentation", "conditional_action", "gap"}):
                continue
            output = {"exact_span": span, "kind": kind}
            style = item.get("presentation_style")
            if kind == "presentation" and isinstance(style,str) and style in {
                "business", "analyst", "manager", "plain", "technical",
            }:
                output["presentation_style"] = style
            role=item.get("presentation_role")
            if kind=="presentation" and isinstance(role,str) and role in {"style","delivery","explanation"}:
                output["presentation_role"]=role
            if kind=="presentation" and role=="style" and "presentation_style" in output:
                # Preserve invalid proposals for atomic rejection by the host owner.
                output["presentation_scope"]=item.get("presentation_scope", "turn")
            source=item.get("source_answer_id")
            if isinstance(source,str) and 1<=len(source)<=128:
                output["source_answer_id"]=source
            op=item.get("op","add")
            if not isinstance(op,str) or op not in {"add","replace","withdraw","reuse"}: continue
            identity = (span, "data" if kind in {"result", "gap"} else kind, op, item.get("target_id") if op != "add" else None)
            if op != "add" and not isinstance(item.get("target_id"), str):
                continue
            if identity in seen_spans:
                continue
            seen_spans.add(identity)
            output["op"]=op
            if op!="add":
                output["target_id"]=item["target_id"]
            scope=item.get("business_scope")
            if scope is not None:
                # Preserve the proposal, including invalid fields. The canonical
                # requirement owner records a localized issue instead of widening it.
                output["business_scope"]=scope
            purposes = item.get("purposes")
            if isinstance(purposes,list) and purposes and len(purposes)<=4 and all(isinstance(v,str) and v in {"knowledge","interpretation","limitation","conditional_action"} for v in purposes) and len(set(purposes))==len(purposes):
                output["purposes"] = purposes
            requested_outputs.append(output)

    def proposals(key, required, optional):
        rows=parsed.get(key,[])
        if not isinstance(rows,list) or len(rows)>16: return []
        return [dict(row) for row in rows if isinstance(row,dict) and required<=set(row) and not set(row)-(required|optional)
                and isinstance(row.get("exact_span"),str) and user_input.count(row["exact_span"])==1 and row["exact_span"]]
    uploads=proposals("upload_bindings",{"upload_id","dataset","relation","exact_span"},{"object_span"})
    mappings=proposals("measurement_mappings",{"exact_span","dataset","column"},{"cost_scopes","x_column","x_start","x_end"})

    logger.info(
        "Intent classification accepted: finish_reason=%s proposed_outputs=%s valid_outputs=%s",
        getattr(response, "finish_reason", "unknown"),
        len(proposed_outputs) if isinstance(proposed_outputs, list) else 0,
        len(requested_outputs),
    )

    return {
        "intent_type": intent_type,
        "reason": parsed.get("reason", ""),
        "ambiguities": ambiguities,
        "requested_outputs": requested_outputs,
        "upload_bindings": uploads, "measurement_mappings": mappings,
        "continuation_of_plan_id": (
            parsed.get("continuation_of_plan_id")
            if isinstance(parsed.get("continuation_of_plan_id"), str) else ""
        ),
    }
