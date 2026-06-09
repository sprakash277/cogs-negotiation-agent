"""Multi-Agent Supervisor — routes a natural-language request to the right sub-agent.

This is the Layer-2 orchestration glue. Instead of the user picking a feature,
they just ask; the supervisor (an LLM router built on the pluggable get_llm())
classifies intent + extracts the supplier, then dispatches to:

  scorecard -> Genie (NL->SQL over kroger_demo.cogs)
  brief     -> Knowledge-Assistant-grounded negotiation brief
  deck      -> Fact-Pack deck builder
  rehearse  -> Vendor rehearsal agent
  chat      -> grounded general answer

Pure LangChain (no LangGraph dependency) — the router is one classify call,
then a deterministic dispatch in Python.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from . import genie
from .agents import build_fact_pack, build_negotiation_brief, rehearse_turn
from .data import get_supplier
from .llm import get_llm

DEFAULT_OBJECTIVE = (
    "Reduce landed COGS and improve trade-fund efficiency for the upcoming contract cycle."
)

ROUTER_SYSTEM = """You are the supervisor/router for a Kroger COGS negotiation assistant.
Classify the user's request into exactly ONE route and extract the supplier and a clean query.

Routes:
- scorecard: questions about numbers, metrics or data (spend, COGS, landed cost, OTIF, fill rate, rebates, trade funds, regions, rankings, comparisons). Answered by Genie NL->SQL.
- brief: requests to prepare/draft a negotiation brief, talking points, or strategy memo.
- deck: requests to build a fact-pack, deck, slides, or presentation.
- rehearse: requests to role-play, practice, simulate, or "negotiate against" the vendor.
- chat: greetings or anything that doesn't fit the above.

Suppliers (supplier_key): pepsi (PepsiCo), coke (The Coca-Cola Company), kdp (Keurig Dr Pepper).
If no supplier is clearly referenced, set supplier_key to null.

Respond with ONLY a JSON object, no prose:
{"route": "scorecard|brief|deck|rehearse|chat", "supplier_key": "pepsi|coke|kdp|null", "query": "<cleaned, self-contained question or objective>"}"""


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
        return {"route": "chat", "supplier_key": None, "query": message}
    if d.get("supplier_key") in ("null", "none", ""):
        d["supplier_key"] = None
    if d.get("route") not in {"scorecard", "brief", "deck", "rehearse", "chat"}:
        d["route"] = "chat"
    return d


def _needs_supplier(route: str) -> str:
    return (
        f"To {route}, tell me which supplier — PepsiCo, Coca-Cola, or Keurig Dr Pepper."
    )


def handle(message: str, history: list[dict] | None = None) -> dict:
    """Route and execute. Returns a unified envelope the UI can render by `route`."""
    d = _classify(message)
    route = d["route"]
    sk = d.get("supplier_key")
    query = d.get("query") or message
    supplier = get_supplier(sk) if sk else None
    out: dict = {"route": route, "supplier_key": sk}

    if route == "scorecard":
        g = genie.ask(query)
        out.update(answer=g.get("text"), sql=g.get("sql"),
                   columns=g.get("columns", []), rows=g.get("rows", []))
        return out

    if route == "brief":
        if not supplier:
            out.update(answer=_needs_supplier("draft a brief"))
            return out
        out.update(supplier=supplier["supplier"],
                   answer=build_negotiation_brief(supplier, query or DEFAULT_OBJECTIVE))
        return out

    if route == "deck":
        if not supplier:
            out.update(answer=_needs_supplier("build a deck"))
            return out
        out.update(supplier=supplier["supplier"],
                   deck=build_fact_pack(supplier, query or DEFAULT_OBJECTIVE))
        return out

    if route == "rehearse":
        if not supplier:
            out.update(answer=_needs_supplier("rehearse"))
            return out
        out.update(supplier=supplier["supplier"],
                   answer=rehearse_turn(supplier, history or [], message))
        return out

    # chat — try Genie (it grounds in real data); if no answer, fall back to LLM
    try:
        g = genie.ask(query)
        if g.get("text") or g.get("rows"):
            out.update(answer=g.get("text"), sql=g.get("sql"),
                       columns=g.get("columns", []), rows=g.get("rows", []))
            return out
    except Exception:
        pass
    ans = get_llm(temperature=0.3).invoke([
        SystemMessage(content="You are a Kroger beverage-category COGS negotiation assistant. "
                              "Be concise and practical."),
        HumanMessage(content=message),
    ]).content
    out.update(answer=ans)
    return out
