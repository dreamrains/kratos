"""Slash command execution endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from data_agent.web.schemas import CommandRequest

router = APIRouter()


@router.post("/commands/{name}")
async def execute_command(name: str, req: CommandRequest, request: Request):
    """Execute a slash command via the session's AgentLoop."""
    manager = request.app.state.agent_manager

    # Delegate to CommandRegistry-style dispatch
    if name == "compact":
        from data_agent.agent.compact import compact_history
        from data_agent.agent.loop import estimate_tokens
        # Get the current session's loop
        sessions = list(manager._loops.values())
        if not sessions:
            return {"status": "error", "message": "No active session"}
        loop = sessions[-1]
        loop.messages[:] = compact_history(
            loop.session_id, loop.client, loop.messages,
            loop._compact_state, token_threshold=loop.token_threshold,
        )
        return {"status": "ok", "message": "Context compacted"}

    elif name == "clear":
        sessions = list(manager._loops.values())
        if sessions:
            loop = sessions[-1]
            loop.messages = []
        return {"status": "ok", "message": "Conversation cleared"}

    elif name == "sessions":
        from data_agent.session.history import list_sessions
        return {"sessions": list_sessions()}

    elif name == "artifacts":
        sessions = list(manager._loops.values())
        if not sessions:
            return {"artifacts": []}
        from data_agent.session.history import list_artifacts
        return {"artifacts": list_artifacts(sessions[-1].session_id)}

    else:
        return {"status": "error", "message": f"Unknown command: {name}"}
