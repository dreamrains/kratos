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


def _feed_events(eq: EventQueue, loop, turn_id: str, gen, runs=None):
    """Drain a stream_turn/resume generator into the EventQueue (runs in background thread)."""
    def _pct_payload():
        tu = _token_usage(loop)
        return tu if tu else {}

    status = "completed"
    errors = []

    def finish(terminal_status):
        from data_agent.llm.request_policy import close_stream
        close_stream(gen)
        notice = ""
        if terminal_status == "failed":
            notice = "**执行失败：** " + "；".join(errors or ["本轮分析未完成。"])
        elif terminal_status == "cancelled":
            notice = "**已停止：** 本轮执行已取消，未完成的分析不代表有效结论。"
        if notice:
            # One canonical message feeds live UI, history and exports. Keep
            # lifecycle metadata out of provider-specific message schemas.
            messages = loop.messages
            if not messages or messages[-1].get("content") != notice:
                messages.append({"role": "assistant", "content": notice})
        loop._auto_save()
        from data_agent.session.public_messages import assistant_replies
        from data_agent.session.history import load_session
        snapshot = load_session(loop.session_id) or {}
        replies = assistant_replies(snapshot.get("messages", []), loop.session_id)
        saved_messages = snapshot.get("messages", [])
        last_user = max((i for i, msg in enumerate(saved_messages) if msg.get("role") == "user"), default=-1)
        has_current_reply = any(msg.get("role") == "assistant" for msg in saved_messages[last_user + 1:])
        reply = replies[-1] if replies and has_current_reply else {}
        state = runs.finish(loop.session_id, turn_id, terminal_status, notice=notice) if runs is not None else {}
        eq.put(SSEEvent("turn_end", {
            "session_id": loop.session_id, "turn_id": turn_id,
            "reply_id": reply.get("reply_id"), "reply_content": reply.get("content"),
            "status": terminal_status, "run_state": state, "execution_notice": notice, **_pct_payload(),
        }))

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
                    "confirmation_id": event.get("confirmation_id") or event["suspension_id"],
                    "suspension_id": event["suspension_id"],
                    "version": event.get("version"),
                    "question": event["question"],
                    "options": event["options"],
                    "context": event["context"],
                    "multi_select": event.get("multi_select"),
                    "allow_free_text": event.get("allow_free_text"),
                    "confirmation_type": event.get("confirmation_type"),
                    "blocking_reason": event.get("blocking_reason"),
                    "related_task_id": event.get("related_task_id"),
                    "related_spec_id": event.get("related_spec_id"),
                }))
                finish("suspended")
                return
            elif etype == "error":
                status = "failed"
                errors.append(str(event["message"]))
                eq.put(SSEEvent("error", {"message": event["message"]}))
        if getattr(loop, "_interrupt_event", None) is not None and loop._interrupt_event.is_set():
            status = "cancelled"
        finish(status)
    except Exception as exc:
        eq.put(SSEEvent("error", {"message": str(exc)}))
        errors.append(str(exc))
        try:
            finish("failed")
        except Exception:
            # Persistence/teardown failure is not proof of a durable terminal.
            notice = "执行状态无法完整保存，请勿将本轮视为分析完成。"
            if runs is not None:
                runs.finish(loop.session_id, turn_id, "unknown", reason=type(exc).__name__, notice=notice)
            eq.put(SSEEvent("turn_end", {
                "session_id": loop.session_id, "turn_id": turn_id, "status": "unknown",
                "execution_notice": notice,
            }))
    finally:
        from data_agent.llm.request_policy import close_stream
        try:
            close_stream(gen)
        finally:
            eq.close()


def _sse_response(eq: EventQueue) -> Response:
    return Response(
        eq.iter(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Connection framing belongs to the WSGI server. A hop-by-hop
            # keep-alive header here can conflict with its terminating frame.
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
    upload_references = data.get("uploads", [])

    manager = current_app.config["agent_manager"]
    agent_loop = manager.get_or_create(session_id=session_id, model_id=model_id)

    turn_id = f"t_{uuid.uuid4().hex[:6]}"
    eq = EventQueue()
    sid = agent_loop.session_id
    from data_agent.web.run_state import SessionBusy
    runs = getattr(manager, "runs", None)
    try:
        if runs is not None:
            runs.begin(sid, turn_id)
        clear = getattr(agent_loop, "clear_interrupt", None)
        if callable(clear):
            clear()
        agent_loop._web_interrupt_prepared = True
    except SessionBusy as exc:
        return jsonify({"error": str(exc), "session_id": sid}), 409

    try:
        from data_agent.web.blueprints.uploads import (
            UploadBindingError,
            UploadIngestionError,
            bind_uploads_to_session,
            ingest_bound_uploads,
        )

        bound_uploads = bind_uploads_to_session(sid, upload_references)
        upload_turn_context = ingest_bound_uploads(agent_loop, bound_uploads)
    except (UploadBindingError, UploadIngestionError) as exc:
        if runs is not None:
            runs.finish(sid, turn_id, "failed", reason="upload_rejected")
        response = jsonify({"error": str(exc), "session_id": sid})
        response.status_code = 422
        response.headers["X-Data-Agent-Session-Id"] = sid
        return response

    def run_in_thread():
        eq.put(SSEEvent("turn_start", {
            "session_id": sid,
            "turn_id": turn_id,
            **(_token_usage(agent_loop) or {}),
        }))
        stream = (
            agent_loop.stream_turn(message, turn_context=upload_turn_context)
            if upload_turn_context
            else agent_loop.stream_turn(message)
        )
        _feed_events(eq, agent_loop, turn_id, stream, runs=runs)

    t = threading.Thread(target=run_in_thread, daemon=True)
    t.start()
    response = _sse_response(eq)
    # The client needs the durable id before it starts consuming the stream.
    # Keeping it in a response header makes pending-session migration robust
    # even when an intermediary coalesces the first SSE event.
    response.headers["X-Data-Agent-Session-Id"] = sid
    return response


@chat_bp.post("/chat/resume")
def resume_chat():
    """Resume a suspended turn after user answers ask_user_question."""
    data = request.get_json(force=True)
    session_id = str(data.get("session_id") or "").strip()
    confirmation_id = str(data.get("confirmation_id") or "").strip()
    expected_version = data.get("expected_version")
    idempotency_key = str(data.get("idempotency_key") or "").strip()
    user_response = data.get("user_response", "")

    if not confirmation_id:
        return jsonify({"error": "confirmation_id is required"}), 400
    if expected_version is None:
        return jsonify({"error": "expected_version is required"}), 400
    if not idempotency_key:
        return jsonify({"error": "idempotency_key is required"}), 400
    try:
        expected_version = int(expected_version)
    except (TypeError, ValueError):
        return jsonify({"error": "expected_version must be an integer"}), 400

    manager = current_app.config["agent_manager"]
    agent_loop = manager.get(session_id)
    if not agent_loop:
        return jsonify({"error": f"Session {session_id} not found"}), 404

    try:
        agent_loop._confirmation_runtime().get(agent_loop.session_id, confirmation_id)
    except KeyError:
        return jsonify({"error": f"runtime confirmation {confirmation_id} not found"}), 404

    turn_id = f"t_{uuid.uuid4().hex[:6]}"
    eq = EventQueue()
    sid = agent_loop.session_id
    from data_agent.web.run_state import SessionBusy
    runs = getattr(manager, "runs", None)
    try:
        if runs is not None:
            runs.begin(sid, turn_id)
        clear = getattr(agent_loop, "clear_interrupt", None)
        if callable(clear):
            clear()
    except SessionBusy as exc:
        return jsonify({"error": str(exc), "session_id": sid}), 409

    def run_in_thread():
        eq.put(SSEEvent("turn_start", {
            "session_id": sid,
            "turn_id": turn_id,
            **(_token_usage(agent_loop) or {}),
        }))
        _feed_events(eq, agent_loop, turn_id,
                     agent_loop.resume_turn_streaming(
                         confirmation_id,
                         user_response,
                         expected_version=expected_version,
                         idempotency_key=idempotency_key,
                     ), runs=runs)

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

    runs = getattr(manager, "runs", None)
    state = runs.cancelling(session_id) if runs is not None else {}
    agent_loop.request_interrupt()
    return jsonify({"status": "cancelling", "run_state": state})


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
    """Update LLM config at runtime and persist to .env."""
    data = request.get_json(force=True)
    from data_agent.config import update_runtime_config, persist_config_to_env
    filtered = {k: v for k, v in data.items() if k in ("model_id", "api_base", "api_key")}
    changed = update_runtime_config(filtered)
    if changed:
        persist_config_to_env(changed)
    return jsonify({"updated": list(changed.keys())})
