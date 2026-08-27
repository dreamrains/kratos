"""SSE completion is a durable publication boundary."""

from __future__ import annotations

from data_agent.web.blueprints.chat import _feed_events


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
