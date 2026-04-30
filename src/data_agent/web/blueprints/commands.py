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
