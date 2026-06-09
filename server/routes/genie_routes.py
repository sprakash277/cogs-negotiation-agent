"""Genie-backed endpoints: free-form NL ask + the Scorecard via Genie."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import os

from .. import genie
from ..config import get_workspace_host

router = APIRouter()

DASHBOARD_ID = os.environ.get("DASHBOARD_ID", "01f1643845191b049c9a3acf7531495b")


@router.get("/dashboard")
def dashboard():
    host = get_workspace_host().rstrip("/")
    return {
        "dashboard_id": DASHBOARD_ID,
        "embed_url": f"{host}/embed/dashboardsv3/{DASHBOARD_ID}",
        "full_url": f"{host}/dashboardsv3/{DASHBOARD_ID}/published",
    }

# The fixed question that drives the Scorecard table (real NL->SQL, real data).
SCORECARD_QUESTION = (
    "List every beverage supplier with their annual spend, COGS per unit, landed cost index, "
    "year over year COGS change percent, year over year volume change percent, trade funds percent, "
    "fill rate percent, OTIF percent, rebate tier, and contract expiry. One row per supplier, "
    "ordered by annual spend descending."
)


class AskRequest(BaseModel):
    question: str
    conversation_id: str | None = None


@router.get("/genie/status")
def status():
    return {"configured": genie.genie_configured(), "space_id": genie.GENIE_SPACE_ID}


@router.post("/genie/ask")
def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question required")
    try:
        return genie.ask(req.question, req.conversation_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Genie error: {e}")


@router.get("/genie/scorecard")
def scorecard():
    """Scorecard data sourced live from Genie (NL->SQL over kroger_demo.cogs)."""
    try:
        return genie.ask(SCORECARD_QUESTION)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Genie error: {e}")
