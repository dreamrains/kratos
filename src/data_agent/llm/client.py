from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator, Optional

import litellm
from litellm import completion

from data_agent.config import get_config


class ToolCall:
    __slots__ = ("id", "name", "arguments")

    def __init__(self, id: str, name: str, arguments: dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments


class Response:
    __slots__ = (
        "text",
        "tool_calls",
        "finish_reason",
        "reasoning_content",
        "unreported_output_tokens",
    )

    def __init__(
        self,
        text: str = "",
        tool_calls: Optional[list[ToolCall]] = None,
        finish_reason: str = "stop",
        reasoning_content: str = "",
        unreported_output_tokens: Optional[int] = None,
    ):
        self.text = text
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.reasoning_content = reasoning_content
        self.unreported_output_tokens = unreported_output_tokens

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

    return Response(
        text=text,
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason or "stop",
        reasoning_content=reasoning,
    )


class LLMClient:
    """统一的 LLM 客户端，基于 LiteLLM 兼容多种模型后端。"""

    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 10
    _DEFAULT_TIMEOUT = 120  # seconds

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
        self.model_id = model_id or cfg.model_id
        self.api_base = api_base or cfg.api_base
        self.api_key = api_key or cfg.api_key
        self.max_tokens = max_tokens or cfg.max_tokens
        self.timeout = timeout or self._DEFAULT_TIMEOUT
        self.temperature = temperature

    def _base_kwargs(self, messages, tools=None, system=None, max_tokens: Optional[int] = None) -> dict:
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": max(1, min(self.max_tokens, int(max_tokens))) if max_tokens is not None else self.max_tokens,
            "timeout": self.timeout,
        }
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

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Response:
        """同步调用 LLM，返回统一 Response。带速率限制重试。"""
        kwargs = self._base_kwargs(messages, tools, system, max_tokens=max_tokens)

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

    def stream_chat_structured(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterator[StreamEvent]:
        """流式调用 LLM，逐 token yield StreamTextDelta，最后 yield StreamComplete。

        支持工具调用：流式阶段累积 tool_call 参数，完成后放入 StreamComplete.response。
        """
        kwargs = self._base_kwargs(messages, tools, system, max_tokens=max_tokens)
        kwargs["stream"] = True
        aggregate_output_limit = int(kwargs["max_tokens"])
        aggregate_emitted_tokens = 0
        aggregate_unreported_tokens = 0

        def record_emitted(value: Any, *, visible_text: bool = False) -> None:
            nonlocal aggregate_emitted_tokens, aggregate_unreported_tokens
            text = str(value or "")
            if text:
                amount = max(1, (len(text) + 3) // 4)
                aggregate_emitted_tokens += amount
                if not visible_text:
                    aggregate_unreported_tokens += amount

        def attach_unreported_usage(exc: Exception) -> None:
            try:
                setattr(exc, "unreported_output_tokens", aggregate_unreported_tokens)
            except Exception:
                pass

        # Accumulate full response parts
        full_text = ""
        reasoning_text = ""
        finish_reason = "stop"
        # tool_calls accumulation: index -> {id, name, arguments_str}
        tc_accum: dict[int, dict[str, str]] = {}

        for attempt in range(self._MAX_RETRIES + 1):
            try:
                for chunk in completion(**kwargs):
                    choice = chunk.choices[0]
                    delta = choice.delta
                    provider_finish_reason = getattr(choice, "finish_reason", None)
                    if provider_finish_reason:
                        finish_reason = str(provider_finish_reason)

                    # Text content
                    if delta.content:
                        text = _sanitize(delta.content)
                        full_text += text
                        record_emitted(text, visible_text=True)
                        yield StreamTextDelta(text=text)

                    # Reasoning content (for models that support it)
                    if getattr(delta, "reasoning_content", None):
                        reasoning_delta = _sanitize(delta.reasoning_content)
                        reasoning_text += reasoning_delta
                        record_emitted(reasoning_delta)

                    # Tool call deltas
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index if hasattr(tc_delta, "index") and tc_delta.index is not None else 0
                            if idx not in tc_accum:
                                tc_accum[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc_delta.id:
                                tc_accum[idx]["id"] = tc_delta.id
                                record_emitted(tc_delta.id)
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tc_accum[idx]["name"] = tc_delta.function.name
                                    record_emitted(tc_delta.function.name)
                                if tc_delta.function.arguments:
                                    tc_accum[idx]["arguments"] += tc_delta.function.arguments
                                    record_emitted(tc_delta.function.arguments)

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
                    finish_reason=finish_reason,
                    reasoning_content=reasoning_text,
                    unreported_output_tokens=aggregate_unreported_tokens,
                )
                yield StreamComplete(response=response)
                return

            except litellm.RateLimitError as exc:
                remaining = max(0, aggregate_output_limit - aggregate_emitted_tokens)
                if attempt < self._MAX_RETRIES and remaining > 0:
                    import time
                    delay = self._RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"\n[yellow]⚠ 流式速率限制，{delay}s 后重试 ({attempt + 1}/{self._MAX_RETRIES})...[/yellow]")
                    time.sleep(delay)
                    kwargs["max_tokens"] = remaining
                    # Reset accumulators for retry
                    full_text = ""
                    reasoning_text = ""
                    finish_reason = "stop"
                    tc_accum.clear()
                else:
                    attach_unreported_usage(exc)
                    raise
            except (litellm.APIConnectionError, litellm.ServiceUnavailableError, litellm.Timeout, litellm.InternalServerError) as exc:
                remaining = max(0, aggregate_output_limit - aggregate_emitted_tokens)
                if attempt < self._MAX_RETRIES and remaining > 0:
                    import time
                    delay = self._RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"\n[yellow]⚠ 流式服务不可用，{delay}s 后重试 ({attempt + 1}/{self._MAX_RETRIES})...[/yellow]")
                    time.sleep(delay)
                    kwargs["max_tokens"] = remaining
                    full_text = ""
                    reasoning_text = ""
                    finish_reason = "stop"
                    tc_accum.clear()
                else:
                    attach_unreported_usage(exc)
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
