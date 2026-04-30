"""FastAPI dependency injection helpers."""

from __future__ import annotations

from fastapi import Request


def get_agent_manager(request: Request):
    return request.app.state.agent_manager
