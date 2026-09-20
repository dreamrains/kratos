"""SSE completion is a durable publication boundary."""

from __future__ import annotations

import json
import math

from data_agent.web.blueprints.chat import _feed_events
from data_agent.web.event_bus import EventQueue, SSEEvent


class _Loop:
    session_id = "publication-order"
    messages: list[dict] = []

    def __init__(self) -> None:
        self.save_count = 0

    def _auto_save(self) -> None:
        self.save_count += 1


class _Queue:
    def __init__(self, loop: _Loop) -> None:
        self.loop = loop
        self.events = []
        self.save_count_at_turn_end = None
        self.closed = False

    def put(self, event) -> None:
        self.events.append(event)
        if event.event == "turn_end":
            self.save_count_at_turn_end = self.loop.save_count

    def close(self) -> None:
        self.closed = True


def test_turn_end_is_emitted_only_after_a_durable_save():
    loop = _Loop()
    queue = _Queue(loop)

    _feed_events(
        queue,
        loop,
        "turn-publication-order",
        iter(({"type": "text_delta", "text": "durable final answer"},)),
    )

    assert [event.event for event in queue.events] == ["text_delta", "turn_end"]
    assert queue.save_count_at_turn_end == 1
    assert queue.events[-1].data["status"] == "completed"
    assert queue.closed is True


def test_event_queue_serializes_non_finite_tool_values_as_strict_json_null():
    queue = EventQueue()
    queue.put(SSEEvent("tool_result", {"web": {"score": math.nan, "bounds": [math.inf, -math.inf]}}))
    queue.close()

    raw = "".join(queue.iter())
    payload = next(line[6:] for line in raw.splitlines() if line.startswith("data: "))
    decoded = json.loads(payload, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

    assert "NaN" not in raw and "Infinity" not in raw
    assert decoded == {"web": {"score": None, "bounds": [None, None]}}


def test_event_queue_emits_comment_keepalive_without_fabricating_product_events():
    queue = EventQueue()
    stream = queue.iter(heartbeat_interval_seconds=0.001)

    assert next(stream) == ": keepalive\n\n"
    queue.put(SSEEvent("turn_end", {"status": "completed"}))
    queue.close()
    remainder = "".join(stream)

    assert "event: turn_end" in remainder
    assert '"status": "completed"' in remainder
