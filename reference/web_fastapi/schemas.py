"""Pydantic request/response models for Web API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model_id: Optional[str] = None
    resume_session_id: Optional[str] = None


class ResumeRequest(BaseModel):
    session_id: str
    suspension_id: str
    user_response: str


class CommandRequest(BaseModel):
    args: str = ""


class ObjectCreateRequest(BaseModel):
    name: str
    description: str = ""


class ObjectSwitchRequest(BaseModel):
    name: str
