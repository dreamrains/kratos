"""EventQueue: thread-safe bridge from sync AgentLoop generator to Flask SSE."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any, Optional


@dataclass
class SSEEvent:
    event: str
    data: dict[str, Any]


def _json_safe(value: Any) -> Any:
    """Return strict-JSON data so every emitted SSE payload is parseable."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


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

    def iter(self, heartbeat_interval_seconds: float = 2.0):
        """Yield SSE events plus comment keepalives while the run is active."""
        interval = max(float(heartbeat_interval_seconds), 0.001)
        while True:
            try:
                item = self._queue.get(timeout=interval)
            except Empty:
                if self._closed and self._queue.empty():
                    return
                # SSE comments carry no product event and are ignored by the
                # parser, but prove that the local service and response stream
                # are still alive while a Provider is legitimately silent.
                yield ": keepalive\n\n"
                continue
            if item is None:
                return
            payload = json.dumps(_json_safe(item.data), ensure_ascii=False, allow_nan=False)
            yield f"event: {item.event}\ndata: {payload}\n\n"
