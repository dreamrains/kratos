from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator, Optional

import litellm
from litellm import completion

from data_agent.config import get_config


class ToolCall:
    __slots__ = ("id", "name", "arguments", "arguments_parse_error")

    def __init__(
        self,
        id: str,
        name: str,
        arguments: Any,
        *,
        arguments_parse_error: str = "",
    ):
        self.id = id
        self.name = name
        self.arguments = arguments
        self.arguments_parse_error = str(arguments_parse_error or "")


class Response:
    __slots__ = ("text", "tool_calls", "finish_reason", "reasoning_content")

    def __init__(
        self,
        text: str = "",
        tool_calls: Optional[list[ToolCall]] = None,
        finish_reason: str = "stop",
        reasoning_content: str = "",
    ):
        self.text = text
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.reasoning_content = reasoning_content

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


def prepare_provider_prompt(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    system: Optional[str] = None,
) -> tuple[list[dict], list[dict]]:
    """Return the exact messages and tool schema sent to LiteLLM."""

    prepared_messages = list(messages)
    if system:
        prepared_messages = [{"role": "system", "content": system}] + prepared_messages
    return prepared_messages, _convert_tools(tools or [])


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
            arguments_parse_error = ""
            if isinstance(args, str):
                args = _sanitize(args)
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    arguments_parse_error = "invalid_json"
                    args = {"raw": args}
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                    arguments_parse_error=arguments_parse_error,
                )
            )

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

    def _base_kwargs(self, messages, tools=None, system=None) -> dict:
        prepared_messages, prepared_tools = prepare_provider_prompt(
            messages, tools, system
        )
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": prepared_messages,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if prepared_tools:
            kwargs["tools"] = prepared_tools
        return kwargs

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
    ) -> Response:
        """同步调用 LLM，返回统一 Response。带速率限制重试。"""
        kwargs = self._base_kwargs(messages, tools, system)

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

    def chat_once(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
    ) -> Response:
        """Make exactly one provider request without an implicit retry."""

        return _parse_response(completion(**self._base_kwargs(messages, tools, system)))

    def stream_chat_structured(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        system: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """流式调用 LLM，逐 token yield StreamTextDelta，最后 yield StreamComplete。

        支持工具调用：流式阶段累积 tool_call 参数，完成后放入 StreamComplete.response。
        """
        kwargs = self._base_kwargs(messages, tools, system)
        kwargs["stream"] = True

        # Accumulate full response parts
        full_text = ""
        reasoning_text = ""
        # tool_calls accumulation: index -> {id, name, arguments_str}
        tc_accum: dict[int, dict[str, str]] = {}

        for attempt in range(self._MAX_RETRIES + 1):
            try:
                for chunk in completion(**kwargs):
                    choice = chunk.choices[0]
                    delta = choice.delta

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
                    arguments_parse_error = ""
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        arguments_parse_error = "invalid_json"
                        args = {"raw": args_str}
                    tool_calls.append(ToolCall(
                        id=entry["id"],
                        name=entry["name"],
                        arguments=args,
                        arguments_parse_error=arguments_parse_error,
                    ))

                response = Response(
                    text=full_text,
                    tool_calls=tool_calls,
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
