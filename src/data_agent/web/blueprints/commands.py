"""Slash command execution via chat message.

Commands are sent as regular chat messages (e.g. "/help") and processed
by the AgentLoop through its normal message handling pipeline.
"""

from flask import Blueprint, current_app, jsonify, request

commands_bp = Blueprint("commands", __name__)


@commands_bp.post("/commands/<name>")
def execute_command(name: str):
    """Execute a slash command by injecting it as a chat message."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    args = data.get("args", "")

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    manager = current_app.config["agent_manager"]
    agent_loop = manager.get(session_id)
    if not agent_loop:
        return jsonify({"error": f"Session {session_id} not found"}), 404

    command_text = f"/{name}"
    if args:
        command_text += f" {args}"

    # For web, commands are handled as regular chat input through the /api/chat endpoint.
    # This endpoint is a fallback for direct command invocation.
    return jsonify({
        "message": "Use /api/chat with the command as the message text.",
        "command": command_text,
    })


@commands_bp.post("/compact")
def compact_context():
    """Manually compact the conversation context for a session."""
    from data_agent.agent.compact import estimate_tokens, compact_history, CompactState
    from data_agent.session.history import (
        CanonicalHistoryConflict,
        load_canonical_history,
        save_session,
    )

    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    focus = data.get("focus") or None

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    manager = current_app.config["agent_manager"]
    agent_loop = manager.get(session_id)
    if not agent_loop:
        return jsonify({"error": f"Session {session_id} not found"}), 404

    snapshot = load_canonical_history(session_id)
    if snapshot.message_count == 0 and agent_loop.messages:
        return jsonify({
            "error": "canonical_history_unavailable",
            "message": "持久化会话历史不可用，未执行压缩。",
        }), 409

    before_tokens = estimate_tokens(snapshot.messages)

    if snapshot.message_count <= 10:
        return jsonify({
            "message": "对话历史较短，无需压缩。",
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
        })

    candidate_state = CompactState(
        has_compacted=agent_loop._compact_state.has_compacted,
        last_summary=agent_loop._compact_state.last_summary,
        recent_files=list(agent_loop._compact_state.recent_files),
    )
    compacted = compact_history(
        session_id,
        agent_loop.client,
        snapshot.messages,
        candidate_state,
        focus=focus,
        token_threshold=0,  # Force compact regardless of threshold
        history_identity={
            "history_revision": snapshot.revision,
            "history_sha256": snapshot.sha256,
            "canonical_message_count": snapshot.message_count,
        },
    )
    if compacted == snapshot.messages:
        return jsonify({
            "message": "当前历史没有可独立压缩的完整早期轮次，已保留原对话。",
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "saved": 0,
            "history_revision": snapshot.revision,
        })

    try:
        save_session(
            compacted,
            session_id,
            data_file=agent_loop._last_data_file,
            extra_meta=agent_loop._build_session_meta(),
            merge_protect=False,
            expected_history_revision=snapshot.revision,
            expected_history_sha256=snapshot.sha256,
        )
    except CanonicalHistoryConflict:
        return jsonify({
            "error": "canonical_history_conflict",
            "message": "压缩期间会话已有新消息，已放弃写回并保留最新历史。",
        }), 409

    written = load_canonical_history(session_id)
    agent_loop.messages[:] = written.messages
    agent_loop._last_jsonl_idx = len(agent_loop.messages)
    agent_loop._compact_state = candidate_state
    agent_loop.invalidate_prompt_cache()

    after_tokens = estimate_tokens(agent_loop.messages)

    return jsonify({
        "message": f"上下文已压缩：{before_tokens} → {after_tokens} tokens（节省 {before_tokens - after_tokens}）",
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "saved": before_tokens - after_tokens,
        "history_revision": written.revision,
    })
