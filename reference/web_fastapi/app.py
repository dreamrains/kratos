"""FastAPI app factory for Data Agent Web GUI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from data_agent.web.agent_manager import AgentManager


def create_app() -> FastAPI:
    app = FastAPI(title="Data Agent", version="0.1.0")

    # CORS for Vite dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup():
        from data_agent.lifecycle import AgentLifecycle
        lifecycle = AgentLifecycle()
        lifecycle.initialize()
        app.state.lifecycle = lifecycle
        app.state.agent_manager = AgentManager()

    # Register routers
    from data_agent.web.routes import chat, sessions, commands, artifacts, objects, models
    app.include_router(chat.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(commands.router, prefix="/api")
    app.include_router(artifacts.router, prefix="/api")
    app.include_router(objects.router, prefix="/api")
    app.include_router(models.router, prefix="/api")

    # Serve static frontend in production
    dist_dir = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")

    return app
