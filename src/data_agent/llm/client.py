from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Iterator, Optional

import litellm
from litellm import completion

from data_agent.config import get_config
from data_agent.llm.routing import normalize_model_id


logger = logging.getLogger(__name__)


class ToolCall:
    __slots__ = ("id", "name", "arguments")

    def __init__(self, id: str, name: str, arguments: dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments


class Response:
    __slots__ = ("text", "tool_calls", "finish_reason", "reasoning_content", "completion_tokens")

    def __init__(
        self,
        text: str = "",
        tool_calls: Optional[list[ToolCall]] = None,
        finish_reason: str = "stop",
        reasoning_content: str = "",
        completion_tokens: Optional[int] = None,
    ):
        self.text = text
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.reasoning_content = reasoning_content
        self.completion_tokens = completion_tokens

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


# ── Streaming events ──────────────────────────────────────


@dataclass
class StreamTextDelta:
    text: str


@dataclass
class StreamComplete:
    response: Response


StreamEvent = StreamTextDelta | StreamComplete


def _convert_tools(tool_defs: list[dict]) -> list[dict]:
    """将内部工具定义转换为 LiteLLM 的 tools 格式。"""
    result = []
    for t in tool_defs:
        result.append({"type": "function", "function": t})
    return result


def _sanitize(text: str) -> str:
    """清理字符串中的非法 UTF-8 代理字符。"""
    if not text:
        return text
    return text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")


def _parse_response(resp: Any) -> Response:
    """将 LiteLLM 响应转换为统一的 Response 对象。"""
    choice = resp.choices[0]
    message = choice.message

    text = _sanitize(message.content or "")
    reasoning = _sanitize(getattr(message, "reasoning_content", "") or "")
    tool_calls = []
    if message.tool_calls:
        for tc in message.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                args = _sanitize(args)
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

    usage = getattr(resp, "usage", None)
    completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None

    return Response(
        text=text,
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason or "stop",
        reasoning_content=reasoning,
        completion_tokens=completion_tokens,
    )


class LLMClient:
    """统一的 LLM 客户端，基于 LiteLLM 兼容多种模型后端。"""

    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 10
    _DEFAULT_TIMEOUT = 120  # seconds
    # Reasoning models can spend the whole completion budget on hidden
    # reasoning before any visible text (finish_reason=length, empty text).
    # Retry a bounded ladder of larger budgets instead of failing silently;
    # 2 escalations => at most 3 requests per logical call.
    _MAX_BUDGET_ESCALATIONS = 2
    _ESCALATION_FALLBACK = 8192
    _MAX_OUTPUT_TOKENS = 128000

    def __init__(
        self,
        model_id: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        cfg = get_config()
        self.model_id = normalize_model_id(model_id or cfg.model_id)
        self.api_base = api_base or cfg.api_base
        self.api_key = api_key or cfg.api_key
        self.max_tokens = max_tokens if max_tokens is not None else cfg.max_tokens
        self.timeout = timeout or self._DEFAULT_TIMEOUT
        self.temperature = temperature

    def _base_kwargs(self, messages, tools=None, system=None) -> dict:
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "timeout": self.timeout,
        }
        # Omitted budget: the provider's model default applies and follows
        # model upgrades without local maintenance.
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if system:
            kwargs["messages"] = [{"role": "system", "content": system}] + list(kwargs["messages"])
        if tools:
            kwargs["tools"] = _convert_tools(tools)
        return kwargs

    def _next_budget_after_truncation(self, current: Optional[int], response: Response) -> Optional[int]:
        """Return the next budget rung when reasoning exhausted the output.

        Only the silent-failure shape (finish_reason=length with zero visible
        text) escalates; a partial answer is surfaced to the caller as-is.
        Returns None when no higher rung exists (cap reached or not truncated).
        """
        if getattr(response, "finish_reason", None) != "length":
            return None
        if (getattr(response, "text", "") or "").strip():
            return None
        if current is not None:
            rung = current * 4
        else:
            # Provider-managed budget with unknown default: derive the rung
            # from what the truncated attempt actually consumed.
            used = response.completion_tokens or self._ESCALATION_FALLBACK
            rung = used * 4
        rung = min(rung, self._MAX_OUTPUT_TOKENS)
        if rung <= (current or 0):
            return None
        logger.info(
            "Escalating output budget after reasoning truncation",
            extra={"extra_data": {"from": current, "to": rung, "completion_tokens": response.completion_tokens}},
        )
        return rung

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
    ) -> Response:
        """同步调用 LLM，返回统一 Response。带速率限制重试。"""
        kwargs = self._base_kwargs(messages, tools, system)
        response = None
        for _ in range(self._MAX_BUDGET_ESCALATIONS + 1):
            response = self._chat_with_transport_retries(kwargs)
            next_budget = self._next_budget_after_truncation(kwargs.get("max_tokens"), response)
            if next_budget is None:
                return response
            kwargs = {**kwargs, "max_tokens": next_budget}
        return response

    def _chat_with_transport_retries(self, kwargs: dict) -> Response:
        last_error = None
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                resp = completion(**kwargs)
                return _parse_response(resp)
            except litellm.RateLimitError as e:
                last_error = e
                if attempt < self._MAX_RETRIES:
                    import time
                    delay = self._RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"\n[yellow]⚠ 速率限制，{delay}s 后重试 ({attempt + 1}/{self._MAX_RETRIES})...[/yellow]")
                    time.sleep(delay)
                else:
                    raise
            except (litellm.APIConnectionError, litellm.ServiceUnavailableError, litellm.Timeout, litellm.InternalServerError) as e:
                last_error = e
                if attempt < self._MAX_RETRIES:
                    import time
                    delay = self._RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"\n[yellow]⚠ 服务暂时不可用，{delay}s 后重试 ({attempt + 1}/{self._MAX_RETRIES})...[/yellow]")
                    time.sleep(delay)
                else:
                    raise
        raise last_error  # unreachable; kept for type completeness

    def chat_once(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
        response_format: Optional[dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
    ) -> Response:
        """Make exactly one synchronous Provider request without retry or fallback.

        This is intentionally separate from ``chat()``.  It is for an
        externally authorized, count-bounded evaluation batch where a failed
        request must consume its slot and stop the batch instead of being
        retried implicitly.  ``max_tokens`` overrides the client-level budget
        so a frozen escalation ladder can drive each attempt explicitly.
        """
        kwargs = self._base_kwargs(messages, tools, system)
        # LiteLLM may otherwise apply its retry policy independently of this
        # client.  Gate C counts request attempts, so this path must opt out.
        kwargs["num_retries"] = 0
        if response_format is not None:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return _parse_response(completion(**kwargs))

    def stream_chat_structured(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """流式调用 LLM，逐 token yield StreamTextDelta，最后 yield StreamComplete。

        支持工具调用：流式阶段累积 tool_call 参数，完成后放入 StreamComplete.response。
        推理耗尽输出预算（零可见正文 + finish_reason=length）时，透明地按更大
        预算重开流；已向消费者发布过正文则不再重开，保留真实 finish_reason。
        """
        kwargs = self._base_kwargs(messages, tools, system)
        kwargs["stream"] = True
        terminal = None
        for _ in range(self._MAX_BUDGET_ESCALATIONS + 1):
            published_text = False
            for event in self._stream_attempt(kwargs):
                if isinstance(event, StreamTextDelta):
                    published_text = True
                    yield event
                else:
                    terminal = event
            if terminal is None:
                return
            next_budget = None
            if not published_text:
                next_budget = self._next_budget_after_truncation(kwargs.get("max_tokens"), terminal.response)
            if next_budget is None:
                yield terminal
                return
            kwargs = {**kwargs, "max_tokens": next_budget}
        yield terminal

    def _stream_attempt(self, kwargs: dict) -> Iterator[StreamEvent]:
        """Consume one streaming request with transport retries only."""
        # Accumulate full response parts
        full_text = ""
        reasoning_text = ""
        finish_reason: Optional[str] = None
        # tool_calls accumulation: index -> {id, name, arguments_str}
        tc_accum: dict[int, dict[str, str]] = {}

        for attempt in range(self._MAX_RETRIES + 1):
            try:
                for chunk in completion(**kwargs):
                    choice = chunk.choices[0]
                    delta = choice.delta
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                    # Text content
                    if delta.content:
                        text = _sanitize(delta.content)
                        full_text += text
                        yield StreamTextDelta(text=text)

                    # Reasoning content (for models that support it)
                    if getattr(delta, "reasoning_content", None):
                        reasoning_text += _sanitize(delta.reasoning_content)

                    # Tool call deltas
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index if hasattr(tc_delta, "index") and tc_delta.index is not None else 0
                            if idx not in tc_accum:
                                tc_accum[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc_delta.id:
                                tc_accum[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tc_accum[idx]["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tc_accum[idx]["arguments"] += tc_delta.function.arguments

                # Streaming complete — build final Response
                tool_calls = []
                for idx in sorted(tc_accum.keys()):
                    entry = tc_accum[idx]
                    args_str = _sanitize(entry["arguments"])
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        args = {"raw": args_str}
                    tool_calls.append(ToolCall(
                        id=entry["id"],
                        name=entry["name"],
                        arguments=args,
                    ))

                response = Response(
                    text=full_text,
                    tool_calls=tool_calls,
                    finish_reason=finish_reason or "stop",
                    reasoning_content=reasoning_text,
                )
                yield StreamComplete(response=response)
                return

            except litellm.RateLimitError:
                if attempt < self._MAX_RETRIES:
                    import time
                    delay = self._RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"\n[yellow]⚠ 流式速率限制，{delay}s 后重试 ({attempt + 1}/{self._MAX_RETRIES})...[/yellow]")
                    time.sleep(delay)
                    # Reset accumulators for retry
                    full_text = ""
                    reasoning_text = ""
                    tc_accum.clear()
                else:
                    raise
            except (litellm.APIConnectionError, litellm.ServiceUnavailableError, litellm.Timeout, litellm.InternalServerError):
                if attempt < self._MAX_RETRIES:
                    import time
                    delay = self._RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"\n[yellow]⚠ 流式服务不可用，{delay}s 后重试 ({attempt + 1}/{self._MAX_RETRIES})...[/yellow]")
                    time.sleep(delay)
                    full_text = ""
                    reasoning_text = ""
                    tc_accum.clear()
                else:
                    raise

    def stream_chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
    ) -> Iterator[str]:
        """流式调用 LLM，yield 文本片段。"""
        kwargs = self._base_kwargs(messages, tools, system)
        kwargs["stream"] = True

        for chunk in completion(**kwargs):
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
