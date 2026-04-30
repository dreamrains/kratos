"""EventQueue: thread-safe bridge from sync AgentLoop generator to Flask SSE."""

from __future__ import annotations

import json
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any, Optional


@dataclass
class SSEEvent:
    event: str
    data: dict[str, Any]


class EventQueue:
    """Thread-safe queue bridging sync AgentLoop generator to Flask SSE response.

    Usage:
        eq = EventQueue()
        # In background thread:
        eq.put(SSEEvent("text_delta", {"text": "hello"}))
        eq.close()
        # In Flask route:
        return Response(eq.iter(), mimetype='text/event-stream')
    """

    def __init__(self):
        self._queue: Queue[Optional[SSEEvent]] = Queue()
        self._closed = False

    def put(self, event: SSEEvent) -> None:
        self._queue.put(event)

    def close(self) -> None:
        self._closed = True
        self._queue.put(None)  # sentinel

    def iter(self):
        """Sync generator yielding SSE-formatted strings for Flask Response."""
        while True:
            try:
                item = self._queue.get(timeout=0.05)
            except Empty:
                if self._closed and self._queue.empty():
                    return
                continue
            if item is None:
                return
            yield f"event: {item.event}\ndata: {json.dumps(item.data, ensure_ascii=False)}\n\n"
