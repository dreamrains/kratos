"""LLM model listing endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/models")
async def list_models():
    from data_agent.config import get_config
    cfg = get_config()
    return {
        "current": cfg.model_id,
        "available": [
            {"id": cfg.model_id, "name": cfg.model_id, "is_current": True},
        ],
    }
