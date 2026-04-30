"""Session CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from data_agent.session.history import list_sessions, load_session, delete_session

router = APIRouter()


@router.get("/sessions")
async def get_sessions():
    return list_sessions()


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    data = load_session(session_id)
    if not data:
        raise HTTPException(404, "Session not found")
    return data


@router.delete("/sessions/{session_id}")
async def del_session(session_id: str):
    success = delete_session(session_id)
    if not success:
        raise HTTPException(404, "Session not found")
    return {"status": "deleted"}
