"""Request policy and stream ownership shared by product and acceptance clients."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequestPolicy:
    """Bound *physical* attempts, without silently increasing output limits.

    Additional output limits must be explicitly selected by a caller. They
    share the attempt allowance with transport retries, rather than multiplying
    it. A stream that has delivered any content is never replayed.
    """

    max_attempts: int = 4
    output_token_limits: tuple[int, ...] = ()
    retry_delay_seconds: float = 10

    def __post_init__(self):
        if self.max_attempts < 1 or self.retry_delay_seconds < 0:
            raise ValueError("invalid request policy")
        if any(limit < 1 for limit in self.output_token_limits):
            raise ValueError("output limits must be positive")


ONE_SHOT = RequestPolicy(max_attempts=1)


def close_stream(stream: Any) -> bool:
    """Close the owned transport; return whether a close contract was available.

    LiteLLM's synchronous wrapper exposes its underlying completion_stream.
    Closing only a Python consumer is insufficient when it wraps that stream.
    No claim is made about remote generation or billing after local close.
    """
    seen: set[int] = set()
    while stream is not None and id(stream) not in seen:
        seen.add(id(stream))
        close = getattr(stream, "close", None)
        if callable(close):
            result = close()
            return result is not False
        stream = getattr(stream, "completion_stream", None)
    return False


class RequestCapacityError(ValueError):
    """Rejected locally before a physical transport attempt."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ": " + message)


def _serialized(value):
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


from functools import lru_cache


@lru_cache(maxsize=32)
def _local_encoder(model_id, tokenizer_path=None):
    """Use only an installed/cached tokenizer. Never download an asset."""
    if tokenizer_path and not tokenizer_path.startswith("tiktoken:"):
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(tokenizer_path)
        return lambda text: len(tokenizer.encode(text).ids), "local_tokenizer_file"
    try:
        import tiktoken, tiktoken.registry, tiktoken_ext.openai_public
        import os, inspect, re, hashlib
        from pathlib import Path
        name = tokenizer_path.split(":", 1)[1] if tokenizer_path else tiktoken.model.encoding_name_for_model(model_id.split("/", 1)[-1])
        encoding = tiktoken.registry.ENCODINGS.get(name)
        if encoding is None:
            constructor = getattr(tiktoken_ext.openai_public, name, None)
            source = inspect.getsource(constructor) if constructor else ""
            asset = re.search(r'load_tiktoken_bpe\(\s*"([^"]+)",\s*expected_hash="([^"]+)"', source)
            if asset is None:
                return None, "utf8_conservative_estimate"
            import tempfile
            cache_dir = os.environ.get("TIKTOKEN_CACHE_DIR", os.environ.get("DATA_GYM_CACHE_DIR", str(Path(tempfile.gettempdir()) / "data-gym-cache")))
            if not cache_dir:
                return None, "utf8_conservative_estimate"
            cache = Path(cache_dir) / hashlib.sha1(asset[1].encode()).hexdigest()
            if not cache.is_file() or hashlib.sha256(cache.read_bytes()).hexdigest() != asset[2]:
                return None, "utf8_conservative_estimate"
            encoding = tiktoken.get_encoding(name)
        return lambda text: len(encoding.encode(text, disallowed_special=())), "local_tokenizer_estimate:" + name
    except (KeyError, ImportError, OSError, ValueError, TypeError):
        return None, "utf8_conservative_estimate"


def count_request_tokens(model_id, messages, tools=None, *, tokenizer_path=None, response_format=None):
    """Count the complete text request with explicit protocol headroom.

    JSON serialization deliberately includes roles, tool calls, schemas and
    response formats. Vendor framing remains an estimate; admission also
    reserves 10 percent of the configured context. No character/4 shortcut.
    """
    payload = {"messages": messages}
    if tools: payload["tools"] = tools
    if response_format: payload["response_format"] = response_format
    text = _serialized(payload)
    encoder, method = _local_encoder(model_id, tokenizer_path)
    count = encoder(text) if encoder else len(text.encode("utf-8"))
    return {"tokens": count + 32 * (len(messages) + len(tools or []) + 1), "method": method}


@dataclass(frozen=True)
class RequestBudget:
    model_id: str
    context_tokens: int
    max_input_tokens: int
    output_reserved: int
    safety_tokens: int
    source: str
    tokenizer_path: str | None = None

    @property
    def input_allowance(self):
        return min(self.max_input_tokens, self.context_tokens - self.output_reserved - self.safety_tokens)

    def estimate(self, messages, tools=None, *, response_format=None):
        result = count_request_tokens(self.model_id, messages, tools, tokenizer_path=self.tokenizer_path, response_format=response_format)
        return {**result, "input_allowance": self.input_allowance, "context_tokens": self.context_tokens,
                "max_input_tokens": self.max_input_tokens, "output_reserved": self.output_reserved,
                "safety_tokens": self.safety_tokens, "capacity_source": self.source}

    def admit(self, messages, tools=None, *, response_format=None):
        result = self.estimate(messages, tools, response_format=response_format)
        if result["tokens"] > self.input_allowance:
            raise RequestCapacityError("request_context_capacity", "完整请求预计输入 %s tokens，允许 %s；已计系统提示、历史、工具、输出预留及余量。" % (result["tokens"], self.input_allowance))
        return result


def resolve_request_budget(model_id, config, max_tokens=None):
    from .routing import model_token_limits
    import math
    known = model_token_limits(model_id)
    context = getattr(config, "model_context_tokens", None) or known["context"]
    incoming = getattr(config, "model_max_input_tokens", None) or (context if getattr(config, "model_context_tokens", None) else known["input"])
    output = getattr(config, "model_max_output_tokens", None) or known["output"]
    if not context or not incoming or (max_tokens is None and not output):
        raise RequestCapacityError("request_model_capacity_unknown", "请配置当前模型/端点的 MODEL_CONTEXT_TOKENS、必要时 MODEL_MAX_INPUT_TOKENS，以及 MODEL_MAX_OUTPUT_TOKENS 或 MAX_TOKENS；不猜测容量。")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens <= 0 or output and max_tokens > output):
        raise RequestCapacityError("request_output_capacity", "显式输出额度无效或超过当前模型/端点上限。")
    reserved = max_tokens if max_tokens is not None else output
    margin = max(1, math.ceil(context * 0.10))
    return RequestBudget(model_id, context, incoming, reserved, margin,
                         "endpoint_configuration" if getattr(config, "model_context_tokens", None) else known["source"],
                         getattr(config, "model_tokenizer", None))


def request_budget_status(config, messages, request_estimate=None):
    """Read-only UI projection; actual usage stays in the existing LLM log."""
    if isinstance(request_estimate, dict):
        result = dict(request_estimate)
        scope = "last_complete_request_estimate"
    else:
        try:
            policy = resolve_request_budget(config.model_id, config, config.max_tokens)
        except RequestCapacityError:
            return None
        result = policy.estimate(messages)
        scope = "history_only_estimate"
    used, allowance = result["tokens"], result["input_allowance"]
    return {"used":used,"threshold":allowance,"pct":min(round(used/max(allowance,1)*100),100),
            "scope":scope,"method":result["method"],"context_tokens":result["context_tokens"],
            "output_reserved":result["output_reserved"],"safety_tokens":result["safety_tokens"]}
