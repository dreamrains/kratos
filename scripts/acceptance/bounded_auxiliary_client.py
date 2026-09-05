"""One-shot auxiliary adapter for frozen Web acceptance requests only."""

from __future__ import annotations


class OneShotAuxiliaryClient:
    # Optional intent/playbook deadlines must not detach this request and
    # start a concurrent main call. The wrapped client's transport owns the
    # frozen timeout; the global Provider guard still owns counting/failure.
    manages_request_timeout = True

    def __init__(self, client, *, max_tokens: int):
        if max_tokens not in (300, 800):
            raise ValueError("auxiliary max_tokens must be 300 or 800")
        self._client = client
        self.max_tokens = max_tokens

    def chat(self, messages, tools=None, system=None):
        return self._client.chat_once(
            messages=messages, tools=tools, system=system, max_tokens=self.max_tokens,
        )
