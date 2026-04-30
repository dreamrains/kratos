"""Artifact listing and file serving endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from data_agent.config import get_config
from data_agent.session.history import list_artifacts

router = APIRouter()


@router.get("/artifacts/{session_id}")
async def get_artifacts(session_id: str):
    return list_artifacts(session_id)


@router.get("/files/{path:path}")
async def serve_file(path: str):
    """Serve session artifacts (charts, reports) as static files."""
    cfg = get_config()
    file_path = cfg.project_resolved / path
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(str(file_path))
