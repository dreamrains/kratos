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
