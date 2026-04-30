"""Per-session AgentLoop lifecycle management."""

from __future__ import annotations

import threading
import uuid
from typing import Optional

from data_agent.utils.logging import get_logger

logger = get_logger("web.agent_manager")


class AgentManager:
    """Manages per-session AgentLoop instances.

    Each session gets its own AgentLoop with web interaction mode enabled.
    Thread-safe via internal lock.
    """

    def __init__(self):
        self._loops: dict[str, "AgentLoop"] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        session_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        """Get existing or create new AgentLoop for a session."""
        from data_agent.agent.loop import AgentLoop, set_interaction_mode

        if session_id and session_id in self._loops:
            return self._loops[session_id]

        set_interaction_mode("web")
        sid = session_id or uuid.uuid4().hex[:12]

        client = None
        if model_id:
            from data_agent.llm.client import LLMClient
            client = LLMClient(model_id=model_id)

        loop = AgentLoop(client=client, session_id=sid)
        with self._lock:
            self._loops[sid] = loop

        logger.info("AgentLoop created", extra={"extra_data": {"session_id": sid}})
        return loop

    def get(self, session_id: str):
        """Get existing AgentLoop or None."""
        return self._loops.get(session_id)

    def remove(self, session_id: str) -> None:
        """Remove AgentLoop from management."""
        with self._lock:
            self._loops.pop(session_id, None)
