"""Agentic endpoints: negotiation brief, fact-pack deck, vendor rehearsal.

All three call the provider-agnostic agents in ``server.agents``, which in turn
use the pluggable ``get_llm()`` factory.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agents import build_fact_pack, build_negotiation_brief, rehearse_turn
from ..data import get_supplier
from ..state import get_artifact, list_artifacts, save_artifact

router = APIRouter()


class BriefRequest(BaseModel):
    supplier_key: str
    objective: str = "Reduce landed COGS and improve trade-fund efficiency for the upcoming contract cycle."


class DeckRequest(BaseModel):
    supplier_key: str
    objective: str = "Reduce landed COGS and improve trade-fund efficiency for the upcoming contract cycle."


class RehearsalTurn(BaseModel):
    supplier_key: str
    message: str
    history: list[dict] = []


def _require_supplier(key: str) -> dict:
    s = get_supplier(key)
    if not s:
        raise HTTPException(status_code=404, detail=f"Unknown supplier '{key}'")
    return s


@router.post("/brief")
def negotiation_brief(req: BriefRequest):
    supplier = _require_supplier(req.supplier_key)
    text = build_negotiation_brief(supplier, req.objective)
    # Surface the contract clauses the brief was grounded in (best-effort).
    sources = []
    try:
        from ..knowledge import retrieve

        sources = [
            {"section": c.get("section"), "supplier": c.get("supplier")}
            for c in retrieve(req.objective, supplier_key=req.supplier_key, k=4)
        ]
    except Exception:
        pass
    aid = save_artifact("briefs", {
        "supplier_key": req.supplier_key,
        "supplier": supplier["supplier"],
        "objective": req.objective,
        "content": text,
    })
    return {"id": aid, "supplier": supplier["supplier"], "content": text, "sources": sources}


@router.post("/deck")
def fact_pack(req: DeckRequest):
    supplier = _require_supplier(req.supplier_key)
    deck = build_fact_pack(supplier, req.objective)
    aid = save_artifact("decks", {
        "supplier_key": req.supplier_key,
        "supplier": supplier["supplier"],
        "objective": req.objective,
        "deck": deck,
    })
    return {"id": aid, "supplier": supplier["supplier"], "deck": deck}


@router.post("/rehearse")
def rehearse(req: RehearsalTurn):
    supplier = _require_supplier(req.supplier_key)
    reply = rehearse_turn(supplier, req.history, req.message)
    return {"supplier": supplier["supplier"], "reply": reply}


@router.get("/artifacts/{kind}")
def artifacts(kind: str):
    if kind not in {"briefs", "decks", "rehearsals"}:
        raise HTTPException(status_code=400, detail="kind must be briefs|decks|rehearsals")
    return {"items": list_artifacts(kind)}


@router.get("/artifacts/{kind}/{aid}")
def artifact(kind: str, aid: str):
    item = get_artifact(kind, aid)
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    return item
