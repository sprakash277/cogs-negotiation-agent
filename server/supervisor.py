"""Top-level persona router — the thin 2-way split of the hybrid architecture.

The old 5-way classify-then-dispatch is gone. Routing now happens along
persona/risk lines, not feature lines:

  rehearse  -> Rehearsal Agent   (adversarial vendor persona, temp 0.7, isolated)
  analytics -> Analytics Agent   (neutral, grounded tool-calling analyst; owns
                                  scorecard / brief / deck / chat — the LLM picks
                                  and chains the tools itself)

So the only decision left for the router is "is this a rehearsal turn?" — and if
so, which supplier (rehearsal NEEDS a supplier to role-play). Everything else
falls through to the Analytics Agent, which decides for itself whether to query
Genie, retrieve contract clauses, build a deck, or just chat.

Pure LangChain (no LangGraph) — one tiny LLM classify, then dispatch.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from . import analytics_agent, rehearsal_agent
from .data import get_supplier
from .llm import get_llm

ROUTER_SYSTEM = """You are the persona router for a Kroger COGS negotiation assistant.
Decide whether the user wants to ROLE-PLAY / REHEARSE a live negotiation against a
supplier (practice, simulate, "negotiate against", "let's role-play", "you be the
vendor"), versus anything analytical (questions about numbers/metrics, drafting a
brief, building a deck, or general chat).

Rehearsal REQUIRES a supplier to role-play. Suppliers (supplier_key): pepsi (PepsiCo),
coke (The Coca-Cola Company), kdp (Keurig Dr Pepper). If no supplier is clearly
referenced, set supplier_key to null.

Respond with ONLY a JSON object, no prose:
{"rehearse": true|false, "supplier_key": "pepsi|coke|kdp|null"}"""


def _classify(message: str) -> dict:
    raw = get_llm(temperature=0).invoke(
        [SystemMessage(content=ROUTER_SYSTEM), HumanMessage(content=message)]
    ).content.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return {"rehearse": False, "supplier_key": None}
    if d.get("supplier_key") in ("null", "none", ""):
        d["supplier_key"] = None
    d["rehearse"] = bool(d.get("rehearse"))
    return d


def _needs_supplier() -> str:
    return "To rehearse, tell me which supplier — PepsiCo, Coca-Cola, or Keurig Dr Pepper."


def handle(message: str, history: list[dict] | None = None) -> dict:
    """Route by persona and execute. Returns a unified envelope the UI renders by
    `route` ("rehearse" or "analytics")."""
    d = _classify(message)

    if d["rehearse"]:
        supplier = get_supplier(d.get("supplier_key"))
        if not supplier:
            return {"route": "rehearse", "supplier_key": d.get("supplier_key"),
                    "answer": _needs_supplier()}
        out = rehearsal_agent.run(supplier, history or [], message)
        out["supplier_key"] = supplier["key"]
        return out

    # Everything analytical (scorecard / brief / deck / chat) -> tool-calling agent.
    out = analytics_agent.run(message, history)
    out.setdefault("supplier_key", None)
    return out
