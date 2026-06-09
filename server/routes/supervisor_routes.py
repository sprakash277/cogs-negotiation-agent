"""Supervisor endpoint — single NL entry point that routes to the sub-agents."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import supervisor

router = APIRouter()


class SupervisorRequest(BaseModel):
    message: str
    history: list[dict] = []


@router.post("/supervisor/ask")
def ask(req: SupervisorRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message required")
    try:
        return supervisor.handle(req.message, req.history)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Supervisor error: {e}")
