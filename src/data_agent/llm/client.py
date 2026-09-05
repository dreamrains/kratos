from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

from data_agent.llm.request_policy import RequestPolicy, ONE_SHOT, close_stream

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
    """One injectable request boundary for sync, streaming and auxiliary work."""

    _MAX_RETRIES = 3  # Compatibility constant; per-instance policy is authoritative.
    _DEFAULT_TIMEOUT = 120
    allow_stream_sync_fallback = False
    manages_request_timeout = True
    _RETRYABLE = (litellm.RateLimitError, litellm.APIConnectionError,
                  litellm.ServiceUnavailableError, litellm.Timeout, litellm.InternalServerError)

    def __init__(self, model_id=None, api_base=None, api_key=None, max_tokens=None,
                 timeout=None, temperature=None, *, transport: Callable | None = None,
                 request_policy: RequestPolicy | None = None):
        cfg = get_config()
        self.model_id = normalize_model_id(model_id or cfg.model_id)
        self.api_base = api_base or cfg.api_base
        self.api_key = api_key or cfg.api_key
        self.max_tokens = max_tokens if max_tokens is not None else cfg.max_tokens
        self.timeout = timeout or self._DEFAULT_TIMEOUT
        self.temperature = temperature
        self.transport = transport
        self.request_policy = request_policy or RequestPolicy()
        self._cancelled = threading.Event()
        self._stream_lock = threading.Lock()
        self._active_stream = None

    def cancel(self):
        self._cancelled.set()
        with self._stream_lock:
            stream = self._active_stream
        if stream is not None:
            try:
                close_stream(stream)
            except Exception:
                # A Python iterator may currently be executing; the reader
                # still owns teardown, bounded by the transport timeout.
                logger.info("Cancellation requested; awaiting stream reader exit")

    def reset_cancellation(self):
        self._cancelled.clear()

    def for_purpose(self, *, max_tokens=None, timeout=None, request_policy=None):
        return LLMClient(model_id=self.model_id, api_base=self.api_base, api_key=self.api_key,
                         max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                         timeout=timeout or self.timeout, temperature=self.temperature,
                         transport=self.transport, request_policy=request_policy or ONE_SHOT)

    def _request(self, kwargs):
        # Disable nested SDK retries: every physical attempt traverses this seam.
        if self._cancelled.is_set():
            raise RuntimeError("LLM request cancelled before admission")
        return (self.transport or completion)(**{**kwargs, "num_retries": 0})

    def _base_kwargs(self, messages, tools=None, system=None):
        # Persistence/UI identity is local metadata, not a Provider field.
        messages = [
            {k: v for k, v in message.items() if k not in {"reply_id", "publication_rejected"}}
            for message in messages
        ]
        kwargs = {"model": self.model_id, "messages": messages, "timeout": self.timeout}
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if system:
            kwargs["messages"] = [{"role": "system", "content": system}] + list(messages)
        if tools:
            kwargs["tools"] = _convert_tools(tools)
        return kwargs

    def _pause(self, attempt):
        if self._cancelled.wait(self.request_policy.retry_delay_seconds * (2 ** attempt)):
            raise RuntimeError("LLM request cancelled during retry delay")

    @staticmethod
    def _silent_truncation(response):
        return (response.finish_reason == "length" and not response.text.strip()
                and not response.tool_calls)

    def chat(self, messages, tools=None, system=None):
        kwargs = self._base_kwargs(messages, tools, system)
        limits = iter(self.request_policy.output_token_limits)
        for attempt in range(self.request_policy.max_attempts):
            try:
                response = _parse_response(self._request(kwargs))
            except self._RETRYABLE:
                if attempt + 1 == self.request_policy.max_attempts:
                    raise
                self._pause(attempt)
                continue
            limit = next(limits, None) if self._silent_truncation(response) else None
            if limit is None or attempt + 1 == self.request_policy.max_attempts:
                return response
            kwargs = {**kwargs, "max_tokens": limit}

    def chat_once(self, messages, tools=None, system=None, response_format=None, max_tokens=None):
        kwargs = self._base_kwargs(messages, tools, system)
        if response_format is not None:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return _parse_response(self._request(kwargs))

    def stream_chat_structured(self, messages, tools=None, system=None):
        kwargs = {**self._base_kwargs(messages, tools, system), "stream": True}
        limits = iter(self.request_policy.output_token_limits)
        for attempt in range(self.request_policy.max_attempts):
            published = False
            terminal = None
            stream = self._stream_attempt(kwargs)
            try:
                for event in stream:
                    if isinstance(event, StreamTextDelta):
                        published = True
                        yield event
                    else:
                        terminal = event
            except self._RETRYABLE:
                # Replaying a partial stream can duplicate visible text or tool
                # arguments. Recover only before any provider delta was received.
                if published or self._received_delta or attempt + 1 == self.request_policy.max_attempts:
                    raise
                self._pause(attempt)
                continue
            finally:
                close_stream(stream)
            if terminal is None:
                raise RuntimeError("Provider stream ended without a terminal response")
            limit = next(limits, None) if not published and self._silent_truncation(terminal.response) else None
            if limit is None or attempt + 1 == self.request_policy.max_attempts:
                yield terminal
                return
            kwargs = {**kwargs, "max_tokens": limit}

    def _stream_attempt(self, kwargs):
        full_text, reasoning = "", ""
        finish_reason, completion_tokens = None, None
        tc_accum = {}
        self._received_delta = False
        stream = self._request(kwargs)
        with self._stream_lock:
            self._active_stream = stream
        try:
            if self._cancelled.is_set():
                return
            for chunk in stream:
                if self._cancelled.is_set():
                    return
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    completion_tokens = getattr(usage, "completion_tokens", completion_tokens)
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                if delta.content:
                    self._received_delta = True
                    text = _sanitize(delta.content)
                    full_text += text
                    yield StreamTextDelta(text=text)
                if getattr(delta, "reasoning_content", None):
                    self._received_delta = True
                    reasoning += _sanitize(delta.reasoning_content)
                if delta.tool_calls:
                    self._received_delta = True
                    for item in delta.tool_calls:
                        index = getattr(item, "index", None) or 0
                        entry = tc_accum.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        if item.id:
                            entry["id"] = item.id
                        if item.function:
                            if item.function.name:
                                entry["name"] = item.function.name
                            if item.function.arguments:
                                entry["arguments"] += item.function.arguments
        finally:
            try:
                close_stream(stream)
            finally:
                with self._stream_lock:
                    self._active_stream = None
        calls = []
        for index in sorted(tc_accum):
            entry = tc_accum[index]
            raw = _sanitize(entry["arguments"])
            try:
                arguments = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                arguments = {"raw": raw}
            calls.append(ToolCall(entry["id"], entry["name"], arguments))
        if finish_reason is None:
            raise RuntimeError("Provider stream ended without finish_reason")
        yield StreamComplete(Response(text=full_text, tool_calls=calls, finish_reason=finish_reason,
                                      reasoning_content=reasoning, completion_tokens=completion_tokens))

    def stream_chat(self, messages, tools=None, system=None):
        stream = self.stream_chat_structured(messages, tools, system)
        try:
            for event in stream:
                if isinstance(event, StreamTextDelta):
                    yield event.text
        finally:
            close_stream(stream)
