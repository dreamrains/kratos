"""Chat SSE streaming endpoint — core of the Web API."""

from __future__ import annotations

import json
import threading
import uuid

from flask import Blueprint, Response, current_app, jsonify, request

from data_agent.web.event_bus import SSEEvent, EventQueue

chat_bp = Blueprint("chat", __name__)


def _token_usage(loop) -> dict | None:
    from data_agent.agent.compact import estimate_tokens
    from data_agent.config import get_config
    from data_agent.web.blueprints.sessions import _get_model_context_window

    cfg = get_config()
    context_window = _get_model_context_window(cfg.model_id)
    if context_window is None:
        return None

    used = estimate_tokens(loop.messages)
    return {"used": used, "threshold": context_window, "pct": min(round(used / max(context_window, 1) * 100), 100)}


def _feed_events(eq: EventQueue, loop, turn_id: str, gen):
    """Drain a stream_turn/resume generator into the EventQueue (runs in background thread)."""
    def _pct_payload():
        tu = _token_usage(loop)
        return tu if tu else {}

    try:
        for event in gen:
            etype = event["type"]
            if etype == "llm_call_start":
                eq.put(SSEEvent("llm_call_start", {"round": event["round"], **_pct_payload()}))
            elif etype == "tool_call":
                eq.put(SSEEvent("tool_call", {
                    "tool_call_id": event["tool_call_id"],
                    "name": event["name"],
                    "arguments": event["arguments"],
                    "round": event["round"],
                }))
            elif etype == "tool_result":
                eq.put(SSEEvent("tool_result", {
                    "tool_call_id": event["tool_call_id"],
                    "name": event["name"],
                    "web": event.get("web"),
                    "duration_ms": event.get("duration_ms"),
                }))
                # Forward task updates when task tools are called
                if event["name"] in ("task_create", "task_update"):
                    eq.put(SSEEvent("task_update", {}))
            elif etype == "text_delta":
                eq.put(SSEEvent("text_delta", {"text": event["text"], "turn_id": event.get("turn_id") or turn_id}))
            elif etype == "_response":
                pass  # Internal event, skip
            elif etype == "suspended":
                eq.put(SSEEvent("suspended", {
                    "suspension_id": event["suspension_id"],
                    "question": event["question"],
                    "options": event["options"],
                    "context": event["context"],
                    "confirmation_type": event.get("confirmation_type"),
                    "blocking_reason": event.get("blocking_reason"),
                    "related_task_id": event.get("related_task_id"),
                    "related_spec_id": event.get("related_spec_id"),
                }))
                eq.put(SSEEvent("turn_end", {
                    "session_id": loop.session_id,
                    "turn_id": turn_id,
                    "status": "suspended",
                    **_pct_payload(),
                }))
                return
            elif etype == "error":
                eq.put(SSEEvent("error", {"message": event["message"]}))
        eq.put(SSEEvent("turn_end", {
            "session_id": loop.session_id,
            "turn_id": turn_id,
            "status": "completed",
            **_pct_payload(),
        }))
    except Exception as e:
        eq.put(SSEEvent("error", {"message": str(e)}))
        eq.put(SSEEvent("turn_end", {
            "session_id": loop.session_id,
            "turn_id": turn_id,
            "status": "error",
        }))
    finally:
        try:
            loop._auto_save()
        except Exception:
            pass
        eq.close()


def _sse_response(eq: EventQueue) -> Response:
    return Response(
        eq.iter(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@chat_bp.post("/chat")
def chat():
    """SSE streaming chat endpoint."""
    data = request.get_json(force=True)
    message = data.get("message", "")
    session_id = data.get("session_id")
    model_id = data.get("model_id")
    resume_session_id = data.get("resume_session_id")

    manager = current_app.config["agent_manager"]
    agent_loop = manager.get_or_create(session_id=session_id, model_id=model_id)

    if resume_session_id and not agent_loop.messages:
        from data_agent.session.history import load_session
        sdata = load_session(resume_session_id)
        if sdata:
            agent_loop.messages = sdata.get("messages", [])

    turn_id = f"t_{uuid.uuid4().hex[:6]}"
    eq = EventQueue()
    sid = agent_loop.session_id

    def run_in_thread():
        eq.put(SSEEvent("turn_start", {
            "session_id": sid,
            "turn_id": turn_id,
            **(_token_usage(agent_loop) or {}),
        }))
        _feed_events(eq, agent_loop, turn_id, agent_loop.stream_turn(message))

    t = threading.Thread(target=run_in_thread, daemon=True)
    t.start()
    return _sse_response(eq)


@chat_bp.post("/chat/resume")
def resume_chat():
    """Resume a suspended turn after user answers ask_user_question."""
    data = request.get_json(force=True)
    session_id = data.get("session_id", "")
    suspension_id = data.get("suspension_id", "")
    user_response = data.get("user_response", "")

    manager = current_app.config["agent_manager"]
    agent_loop = manager.get(session_id)
    if not agent_loop:
        return jsonify({"error": f"Session {session_id} not found"}), 404

    turn_id = f"t_{uuid.uuid4().hex[:6]}"
    eq = EventQueue()
    sid = agent_loop.session_id

    def run_in_thread():
        eq.put(SSEEvent("turn_start", {
            "session_id": sid,
            "turn_id": turn_id,
            **(_token_usage(agent_loop) or {}),
        }))
        _feed_events(eq, agent_loop, turn_id,
                     agent_loop.resume_turn_streaming(suspension_id, user_response))

    t = threading.Thread(target=run_in_thread, daemon=True)
    t.start()
    return _sse_response(eq)


@chat_bp.post("/chat/interrupt")
def interrupt_chat():
    """Request interrupt of the current turn."""
    data = request.get_json(force=True)
    session_id = data.get("session_id", "")

    manager = current_app.config["agent_manager"]
    agent_loop = manager.get(session_id)
    if not agent_loop:
        return jsonify({"error": f"Session {session_id} not found"}), 404

    agent_loop.request_interrupt()
    return jsonify({"status": "interrupt_requested"})


@chat_bp.get("/models")
def list_models():
    """Return current model info and available model list."""
    from data_agent.config import get_config
    cfg = get_config()

    # Read recent models from sessions for a dynamic list
    recent_models = set()
    recent_models.add(cfg.model_id)
    try:
        from data_agent.session.history import _sessions_dir
        for d in _sessions_dir().iterdir():
            if not d.is_dir():
                continue
            meta_path = d / "meta.json"
            if meta_path.exists():
                import json as _json
                meta = _json.loads(meta_path.read_text(encoding="utf-8"))
                m = meta.get("model_id")
                if m:
                    recent_models.add(m)
    except Exception:
        pass

    all_models = sorted(recent_models, key=lambda m: (m != cfg.model_id, m))

    return jsonify({
        "current": cfg.model_id,
        "api_base": cfg.api_base,
        "models": all_models,
    })


# ── Config ──────────────────────────────────────────────────


@chat_bp.get("/config")
def get_config_info():
    """Return current LLM config (key masked)."""
    from data_agent.config import get_config
    cfg = get_config()
    key = cfg.api_key or ""
    masked = ("*" * (len(key) - 4) + key[-4:]) if len(key) > 4 else "****" if key else ""
    return jsonify({
        "model_id": cfg.model_id,
        "api_base": cfg.api_base or "",
        "api_key_masked": masked,
        "has_key": bool(key),
    })


@chat_bp.post("/config")
def update_config_info():
    """Update LLM config at runtime (not persisted to .env)."""
    data = request.get_json(force=True)
    from data_agent.config import update_runtime_config
    changed = update_runtime_config({
        k: v for k, v in data.items() if k in ("model_id", "api_base", "api_key")
    })
    return jsonify({"updated": list(changed.keys())})
