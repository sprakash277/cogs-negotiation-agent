"""Read-only data endpoints: deck hub, scorecard, category overview, health."""

from __future__ import annotations

from fastapi import APIRouter

from ..data import get_category_overview, get_supplier_scorecard
from ..knowledge import index_status
from ..llm import llm_status
from ..state import backend_name

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "llm": llm_status(),
        "state_backend": backend_name(),
        "knowledge": index_status(),
    }


@router.get("/overview")
def overview():
    return get_category_overview()


@router.get("/scorecard")
def scorecard(supplier: str | None = None):
    return {"suppliers": get_supplier_scorecard(supplier)}


@router.get("/hub")
def hub():
    """Deck-hub gallery cards — one per supplier negotiation."""
    cards = []
    for s in get_supplier_scorecard():
        cards.append({
            "key": s["key"],
            "supplier": s["supplier"],
            "category": s["category"],
            "annual_spend": s["annual_spend"],
            "yoy_cogs_change_pct": s["yoy_cogs_change_pct"],
            "contract_expiry": s["contract_expiry"],
            "open_negotiation": s["open_negotiation"],
        })
    return {"cards": cards}
