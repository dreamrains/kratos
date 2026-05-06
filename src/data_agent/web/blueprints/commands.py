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

    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    manager = current_app.config["agent_manager"]
    agent_loop = manager.get(session_id)
    if not agent_loop:
        return jsonify({"error": f"Session {session_id} not found"}), 404

    before_tokens = estimate_tokens(agent_loop.messages)

    if len(agent_loop.messages) <= 10:
        return jsonify({
            "message": "对话历史较短，无需压缩。",
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
        })

    agent_loop.messages[:] = compact_history(
        session_id,
        agent_loop.client,
        agent_loop.messages,
        agent_loop._compact_state,
        token_threshold=0,  # Force compact regardless of threshold
    )
    agent_loop.invalidate_prompt_cache()
    agent_loop._auto_save()

    after_tokens = estimate_tokens(agent_loop.messages)

    return jsonify({
        "message": f"上下文已压缩：{before_tokens} → {after_tokens} tokens（节省 {before_tokens - after_tokens}）",
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "saved": before_tokens - after_tokens,
    })
