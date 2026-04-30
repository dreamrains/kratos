"""Chat SSE streaming endpoint — core of the Web API."""

from __future__ import annotations

import asyncio
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from data_agent.web.schemas import ChatRequest, ResumeRequest
from data_agent.web.event_bus import SSEEvent, EventQueue

router = APIRouter()


def _feed_events(eq: EventQueue, loop, turn_id: str, gen):
    """Drain a stream_turn/resume generator into the EventQueue (runs in thread)."""
    try:
        for event in gen:
            etype = event["type"]
            if etype == "llm_call_start":
                eq.put(SSEEvent("llm_call_start", {"round": event["round"]}))
            elif etype == "tool_call":
                eq.put(SSEEvent("tool_call", {
                    "tool_call_id": event["tool_call_id"],
                    "name": event["name"],
                    "arguments": event["arguments"],
                    "round": event["round"],
                }))
            elif etype == "tool_result":
                eq.put(SSEEvent("tool_result", {
                    "tool_call_id": event["tool_call_id"],
                    "name": event["name"],
                    "web": event["web"],
                    "duration_ms": event["duration_ms"],
                }))
            elif etype == "text_delta":
                eq.put(SSEEvent("text_delta", {"text": event["text"], "turn_id": turn_id}))
            elif etype == "suspended":
                eq.put(SSEEvent("suspended", {
                    "suspension_id": event["suspension_id"],
                    "question": event["question"],
                    "options": event["options"],
                    "context": event["context"],
                }))
                eq.put(SSEEvent("turn_end", {
                    "session_id": loop.session_id,
                    "turn_id": turn_id,
                    "status": "suspended",
                }))
                return
            elif etype == "error":
                eq.put(SSEEvent("error", {"message": event["message"]}))
        eq.put(SSEEvent("turn_end", {
            "session_id": loop.session_id,
            "turn_id": turn_id,
            "status": "completed",
        }))
    except Exception as e:
        eq.put(SSEEvent("error", {"message": str(e)}))
        eq.put(SSEEvent("turn_end", {
            "session_id": loop.session_id,
            "turn_id": turn_id,
            "status": "error",
        }))
    finally:
        eq.close()


def _sse_response(eq: EventQueue) -> StreamingResponse:
    return StreamingResponse(
        eq.aiter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """SSE streaming chat endpoint."""
    manager = request.app.state.agent_manager
    agent_loop = manager.get_or_create(
        session_id=req.session_id,
        model_id=req.model_id,
    )

    # Resume previous session messages if requested
    if req.resume_session_id and not agent_loop.messages:
        from data_agent.session.history import load_session
        data = load_session(req.resume_session_id)
        if data:
            agent_loop.messages = data.get("messages", [])

    turn_id = f"t_{uuid.uuid4().hex[:6]}"
    eq = EventQueue()
    sid = agent_loop.session_id

    def run_sync():
        eq.put(SSEEvent("turn_start", {"session_id": sid, "turn_id": turn_id}))
        _feed_events(eq, agent_loop, turn_id, agent_loop.stream_turn(req.message))

    asyncio.get_event_loop().run_in_executor(None, run_sync)
    return _sse_response(eq)


@router.post("/chat/resume")
async def resume_chat(req: ResumeRequest, request: Request):
    """Resume a suspended turn after user answers ask_user_question."""
    manager = request.app.state.agent_manager
    agent_loop = manager.get(req.session_id)
    if not agent_loop:
        raise HTTPException(404, f"Session {req.session_id} not found")

    turn_id = f"t_{uuid.uuid4().hex[:6]}"
    eq = EventQueue()
    sid = agent_loop.session_id

    def run_sync():
        eq.put(SSEEvent("turn_start", {"session_id": sid, "turn_id": turn_id}))
        _feed_events(eq, agent_loop, turn_id,
                      agent_loop.resume_turn_streaming(req.suspension_id, req.user_response))

    asyncio.get_event_loop().run_in_executor(None, run_sync)
    return _sse_response(eq)


@router.post("/chat/interrupt")
async def interrupt_chat(req: ChatRequest, request: Request):
    """Request interrupt of the current turn."""
    manager = request.app.state.agent_manager
    agent_loop = manager.get(req.session_id)
    if not agent_loop:
        raise HTTPException(404, f"Session {req.session_id} not found")
    agent_loop.request_interrupt()
    return {"status": "interrupt_requested"}
