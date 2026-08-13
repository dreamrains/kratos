"""Data Agent V2 Slice 1 semantic SSE and refresh endpoints."""

from __future__ import annotations

import threading
import uuid

from flask import Blueprint, Response, jsonify, request

from data_agent.config import get_config
from data_agent.v2.slice1 import Slice1DescriptiveRuntime
from data_agent.v2.store import V2FactStore
from data_agent.web.event_bus import EventQueue, SSEEvent

v2_bp = Blueprint("v2", __name__)


def _sse_response(queue: EventQueue) -> Response:
    return Response(
        queue.iter(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@v2_bp.post("/v2/describe")
def describe_v2() -> Response:
    """Run the Slice 1 explicit single-metric descriptive journey."""

    payload = request.get_json(force=True)
    session_id = str(payload.get("session_id") or f"v2_{uuid.uuid4().hex[:12]}").strip()
    turn_id = str(payload.get("turn_id") or f"turn_{uuid.uuid4().hex[:12]}").strip()
    cfg = get_config()
    runtime = Slice1DescriptiveRuntime(cfg.sessions_resolved, cfg.inbox_dir)
    queue = EventQueue()

    def run() -> None:
        try:
            for event in runtime.stream(
                session_id=session_id,
                turn_id=turn_id,
                filename=str(payload.get("filename") or ""),
                metric=str(payload.get("metric") or ""),
                question=str(payload.get("question") or ""),
            ):
                queue.put(SSEEvent(event.event, event.data))
        except Exception as exc:
            queue.put(
                SSEEvent(
                    "turn_failed",
                    {
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            )
        finally:
            queue.close()

    threading.Thread(target=run, daemon=True).start()
    return _sse_response(queue)


@v2_bp.get("/v2/sessions/<session_id>/turns/<turn_id>")
def get_v2_turn(session_id: str, turn_id: str):
    store = V2FactStore(get_config().sessions_resolved, session_id)
    try:
        turn = store.read_turn_blocks(turn_id)
    except KeyError:
        return jsonify({"error": "V2 turn not found"}), 404
    return jsonify(turn)
