"""Rehearsal Agent — the isolated adversarial-vendor persona.

This is the deliberately-separate, higher-temperature half of the hybrid
architecture. It role-plays a tough Key Account Manager from the supplier so a
Kroger buyer can practice the live negotiation. It is kept in its own module —
with its own system prompt and its own (riskier) temperature — so it can be
evaluated independently for persona-adherence and safety, and so its in-character
push-back never leaks into the neutral, grounded Analytics Agent.

Pure LangChain — a single multi-turn chat invocation, no tools, no LangGraph.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .agents import _supplier_facts
from .llm import get_llm

REHEARSAL_TEMPERATURE = 0.7


def _rehearsal_system(supplier: dict) -> str:
    return (
        f"You are role-playing as a tough, experienced Key Account Manager from "
        f"{supplier['supplier']} in a live negotiation with a Kroger category buyer. "
        f"Stay fully in character. You defend your pricing and COGS position, push "
        f"back on concessions, and use plausible supplier arguments (input-cost "
        f"inflation, brand pull, innovation pipeline, trade-spend ROI). "
        f"You know your numbers: {_supplier_facts(supplier)}. "
        f"Be firm but professional. Keep replies to 2-4 sentences so the buyer can "
        f"practice responding. Never break character or mention you are an AI."
    )


def run(supplier: dict, history: list[dict], user_message: str) -> dict:
    """Play one vendor turn. Returns a UI envelope: {route, supplier, answer}.

    history: [{'role': 'buyer'|'vendor', 'content': str}, ...] — in a rehearsal the
    *buyer* is the human and the *vendor* is the assistant.
    """
    msgs = [SystemMessage(content=_rehearsal_system(supplier))]
    for turn in history:
        if turn.get("role") == "buyer":
            msgs.append(HumanMessage(content=turn.get("content", "")))
        else:
            msgs.append(AIMessage(content=turn.get("content", "")))
    msgs.append(HumanMessage(content=user_message))

    reply = get_llm(temperature=REHEARSAL_TEMPERATURE).invoke(msgs).content
    return {"route": "rehearse", "supplier": supplier["supplier"], "answer": reply}
