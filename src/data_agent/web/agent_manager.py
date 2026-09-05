"""Per-session AgentLoop lifecycle management."""

from __future__ import annotations

import threading
import uuid
from typing import Callable, Optional

from data_agent.utils.logging import get_logger

logger = get_logger("web.agent_manager")


class AgentManager:
    """Manages per-session AgentLoop instances.

    Each session gets its own AgentLoop with web interaction mode enabled.
    Thread-safe via internal lock.
    """

    def __init__(self, *, auxiliary_client_factory: Callable[[], object] | None = None,
                 client_factory: Callable[..., object] | None = None):
        self._loops: dict[str, "AgentLoop"] = {}
        self._lock = threading.RLock()
        self._auxiliary_client_factory = auxiliary_client_factory
        self._client_factory = client_factory
        from data_agent.web.run_state import RunStates
        self.runs = RunStates()

    def get_or_create(
        self,
        session_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        with self._lock:
            return self._create_locked(session_id, model_id)

    def _create_locked(self, session_id=None, model_id=None):
        """Get existing or create new AgentLoop for a session.

        When creating a new AgentLoop for a session_id that already exists
        on disk (e.g. after server restart), automatically restores conversation
        history, object context, and workspace data.
        """
        from data_agent.agent.loop import AgentLoop, set_interaction_mode

        if session_id and session_id in self._loops:
            return self._loops[session_id]

        set_interaction_mode("web")
        sid = session_id or uuid.uuid4().hex[:12]

        client = None
        if self._client_factory is not None:
            client = self._client_factory(model_id=model_id)
        elif model_id:
            from data_agent.llm.client import LLMClient
            client = LLMClient(model_id=model_id)

        loop_options = {}
        if self._auxiliary_client_factory is not None:
            loop_options["auxiliary_llm_client"] = self._auxiliary_client_factory()
        loop = AgentLoop(client=client, session_id=sid, **loop_options)

        # Auto-restore session that exists on disk but was lost from memory
        if sid and not loop.messages:
            from data_agent.session.history import load_session
            sdata = load_session(sid)
            if sdata and sdata.get("messages"):
                loop.messages = sdata["messages"]
                loop.restore_object_context()
                loop._restore_workspace()
                logger.info("Session restored from disk",
                            extra={"extra_data": {"session_id": sid, "messages": len(loop.messages)}})

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
