"""LLM judge for golden answer soft dimensions.

Measurement-only. Uses a configurable judge model at temperature 0 and
parses structured JSON. Mirrors the one-shot pattern in llm_intent.py.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from data_agent.agent.answer_quality import SOFT_DIMENSIONS, SCENARIO_EXTRA_DIMENSIONS

_judge_client: Optional[Any] = None


def _all_dimension_specs() -> dict[str, dict[str, str]]:
    merged = dict(SOFT_DIMENSIONS)
    merged.update(SCENARIO_EXTRA_DIMENSIONS)
    return merged


def _get_judge_client():
    global _judge_client
    if _judge_client is None:
        from data_agent.config import get_config
        from data_agent.llm.client import LLMClient

        cfg = get_config()
        _judge_client = LLMClient(
            model_id=cfg.quality_judge_model,  # None -> default MODEL_ID
            max_tokens=800,
            temperature=0.0,
        )
    return _judge_client


def _extract_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _rubric_block(dimensions: list[str]) -> str:
    specs = _all_dimension_specs()
    lines = []
    for key in dimensions:
        spec = specs.get(key)
        if not spec:
            continue
        lines.append(
            f"- {key}（{spec['name']}）: {spec['what']}。"
            f"1分={spec['anchor_1']}；3分={spec['anchor_3']}；5分={spec['anchor_5']}。"
        )
    return "\n".join(lines)


_SYSTEM = (
    "你是一位资深数据分析评审。只返回 JSON，不要任何额外文字。"
    "评估的是面向业务决策的中文数据分析最终答案的质量。"
)


def _absolute_user_prompt(answer_text, question, data_brief, dimensions) -> str:
    return (
        f"业务问题：{question}\n"
        f"数据概况（非原始行）：{json.dumps(data_brief, ensure_ascii=False)}\n"
        f"待评答案：\n{answer_text}\n\n"
        f"按以下维度逐项打 1-5 分（整数），并给一句话理由。\n"
        f"{_rubric_block(dimensions)}\n"
        f'只返回 JSON，形如 {{"维度key": {{"score": 1, "rationale": "..."}}}}。'
    )


def _pairwise_user_prompt(baseline_answer, new_answer, question, data_brief, dimensions) -> str:
    return (
        f"业务问题：{question}\n"
        f"数据概况（非原始行）：{json.dumps(data_brief, ensure_ascii=False)}\n"
        f"答案A（baseline）：\n{baseline_answer}\n\n"
        f"答案B（new）：\n{new_answer}\n\n"
        f"按以下维度逐项判断 B 相对 A 是更好/持平/更差，并给一句话理由。\n"
        f"{_rubric_block(dimensions)}\n"
        f'只返回 JSON，形如 {{"维度key": {{"verdict": "better|same|worse", "rationale": "..."}}}}。'
    )


def _judge(user_prompt: str, client) -> dict[str, dict]:
    cli = client or _get_judge_client()
    try:
        resp = cli.chat(messages=[{"role": "user", "content": user_prompt}], system=_SYSTEM)
    except Exception:
        return {}
    parsed = _extract_json(getattr(resp, "text", "") or "")
    if not isinstance(parsed, dict):
        return {}
    return {str(k): v for k, v in parsed.items() if isinstance(v, dict)}


def judge_absolute(answer_text, question, data_brief, dimensions, client=None) -> dict[str, dict]:
    return _judge(_absolute_user_prompt(answer_text, question, data_brief, dimensions), client)


def judge_pairwise(baseline_answer, new_answer, question, data_brief, dimensions, client=None) -> dict[str, dict]:
    return _judge(_pairwise_user_prompt(baseline_answer, new_answer, question, data_brief, dimensions), client)
