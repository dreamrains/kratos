"""LLM-based intent classification for ambiguous cases."""

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

_CLASSIFICATION_PROMPT = """\
Classify this user input for a data analysis assistant. Return ONLY valid JSON.

Valid intent types:
- simple_response: acknowledgments, confirmations, greetings, short replies
- knowledge_qa: asking about concepts, methods, definitions (e.g., "what is correlation?")
- analysis_consultation: asking for analysis advice, methodology guidance (e.g., "how should I analyze this?")
- result_followup: questioning, challenging, or asking about previous analysis results
- intent_negotiation: vague requests needing clarification (e.g., "help me look at this data")
- data_requirement: asking what data is needed
- data_operation: direct data operations (filter, group, sort, export, summarize)
- directed_analysis: specific analysis request (e.g., "analyze the revenue trend")
- comprehensive_report: request for full report or comprehensive analysis

Also detect ambiguities: unclear metric names, unspecified dimensions, vague time ranges, undefined terms.

User input: {user_input}
Session context: {session_context}

Return JSON: {{"intent_type": "...", "reason": "...", "ambiguities": [{{"field": "...", "issue": "..."}}]}}"""

_client: Optional[object] = None


def _get_client():
    global _client
    if _client is None:
        from data_agent.llm.client import LLMClient
        _client = LLMClient(max_tokens=200)
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

    prompt = _CLASSIFICATION_PROMPT.format(
        user_input=user_input,
        session_context=session_context,
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        response = _call_with_timeout(
            client.chat,
            (messages,),
            {"system": ""},
            5,
        )
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
