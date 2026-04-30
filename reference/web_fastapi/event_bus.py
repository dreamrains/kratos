"""EventQueue: thread-safe bridge from sync generator to async SSE."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any, Optional


@dataclass
class SSEEvent:
    event: str
    data: dict[str, Any]


class EventQueue:
    """Thread-safe queue bridging sync AgentLoop generator to async SSE consumer.

    Usage:
        eq = EventQueue()
        # In sync thread:
        eq.put(SSEEvent("text_delta", {"text": "hello"}))
        eq.close()
        # In async SSE handler:
        async for chunk in eq.aiter():
            yield chunk
    """

    def __init__(self):
        self._queue: Queue[Optional[SSEEvent]] = Queue()
        self._closed = False

    def put(self, event: SSEEvent) -> None:
        self._queue.put(event)

    def close(self) -> None:
        self._closed = True
        self._queue.put(None)  # sentinel

    async def aiter(self):
        """Async generator yielding SSE-formatted strings."""
        loop = asyncio.get_event_loop()
        while True:
            try:
                item = await loop.run_in_executor(None, self._queue.get, True, 0.05)
            except Empty:
                if self._closed and self._queue.empty():
                    return
                continue
            if item is None:
                return
            yield f"event: {item.event}\ndata: {json.dumps(item.data, ensure_ascii=False)}\n\n"
