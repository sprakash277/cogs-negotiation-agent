"""The agent logic — LangChain chains built on the pluggable LLM factory.

Each function here is a sub-agent of the COGS Negotiation Agent. They all obtain
their model via ``get_llm()`` and are therefore provider-agnostic: flip
LLM_PROVIDER between 'mosaic' and 'litellm' and every one of these keeps working.

Sub-agents:
  build_negotiation_brief() -> Negotiation Brief (talking points)
  build_fact_pack()         -> Fact-Pack & Deck narrative (structured JSON)
  rehearse_turn()           -> Vendor Rehearsal role-play reply
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from .llm import get_llm


def _money(n: float) -> str:
    if n >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"${n/1_000_000:.0f}M"
    return f"${n:,.0f}"


def _supplier_facts(s: dict) -> str:
    return (
        f"Supplier: {s['supplier']} | Category: {s['category']} | "
        f"Annual spend: {_money(s['annual_spend'])} | COGS/unit: ${s['cogs_per_unit']:.2f} | "
        f"Landed-cost index: {s['landed_cost_index']} (baseline 100) | "
        f"YoY COGS change: {s['yoy_cogs_change_pct']:+.1f}% | "
        f"YoY volume: {s['yoy_volume_change_pct']:+.1f}% | "
        f"Trade funds: {s['trade_funds_pct']:.1f}% of spend | "
        f"Fill rate: {s['fill_rate_pct']:.1f}% | OTIF: {s['otif_pct']:.1f}% | "
        f"Rebate tier: {s['rebate_tier']} | Contract expiry: {s['contract_expiry']}"
    )


# --------------------------------------------------------------------------- #
# Negotiation Brief
# --------------------------------------------------------------------------- #
BRIEF_SYSTEM = (
    "You are a senior category-procurement strategist at Kroger preparing a "
    "category negotiator to sit across the table from a major beverage supplier. "
    "You are sharp, numbers-driven, and you never invent figures — you reason only "
    "from the supplier facts provided. Produce a tight, board-ready negotiation brief."
)

BRIEF_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", BRIEF_SYSTEM),
    ("human",
     "Prepare a negotiation brief for the upcoming COGS negotiation with this supplier.\n\n"
     "SUPPLIER FACTS:\n{facts}\n\n"
     "RELEVANT CONTRACT CLAUSES (from the supplier's Master Supply Agreement — cite the "
     "bracketed section name when you rely on one):\n{contract_context}\n\n"
     "NEGOTIATION OBJECTIVE: {objective}\n\n"
     "Structure the brief with these sections, using crisp bullet points:\n"
     "1. Situation Summary (2-3 lines)\n"
     "2. Our Leverage (where Kroger has power — cite the numbers AND the contract clauses)\n"
     "3. Their Likely Position (what the supplier will argue)\n"
     "4. Target Outcomes (specific, quantified asks — reference the relevant contract section)\n"
     "5. Concession Ladder (what we give, in what order)\n"
     "6. Walk-Away / BATNA (note any termination / re-source rights from the contract)\n"
     "Keep it under 500 words. Be specific, tie every claim to a number, and ground "
     "contractual points in the clauses above (e.g. \"per [Service Levels & Supply Reliability]\")."),
])


def build_negotiation_brief(supplier: dict, objective: str) -> str:
    # Retrieve the most relevant contract clauses for this supplier + objective (RAG).
    contract_context = "(contract retrieval unavailable)"
    try:
        from .knowledge import context_block, retrieve

        clauses = retrieve(
            query=f"{objective} — pricing, COGS adjustment, rebates, trade funds, service levels",
            supplier_key=supplier["key"],
            k=4,
        )
        contract_context = context_block(clauses)
    except Exception:
        pass  # degrade gracefully to facts-only if the index isn't reachable

    chain = BRIEF_TEMPLATE | get_llm(temperature=0.3)
    resp = chain.invoke({
        "facts": _supplier_facts(supplier),
        "contract_context": contract_context,
        "objective": objective,
    })
    return resp.content


# --------------------------------------------------------------------------- #
# Fact-Pack & Deck (structured narrative -> rendered by the React deck viewer)
# --------------------------------------------------------------------------- #
DECK_SYSTEM = (
    "You are an analytics storyteller building a data-driven negotiation deck for "
    "a Kroger category negotiator. You output STRICT JSON only — no prose, no "
    "markdown fences. Every number you use must come from the supplier facts; do "
    "not fabricate. Tell a persuasive, evidence-led story."
)

DECK_INSTRUCTION = """Build a negotiation fact-pack deck for {supplier_name}.

SUPPLIER FACTS:
{facts}

OBJECTIVE: {objective}

Return JSON with EXACTLY this schema:
{{
  "title": "string - punchy deck title",
  "subtitle": "string - one line",
  "hypothesis": "string - 1-2 sentence thesis we will argue",
  "kpis": [
    {{"label": "string", "value": "string e.g. $1.84B", "delta": "string e.g. +6.8% YoY", "tone": "good|bad|neutral"}}
  ],
  "sections": [
    {{"heading": "string", "narrative": "string - 2-4 sentences", "callout": "string - the one-line headline takeaway"}}
  ],
  "asks": ["string - specific quantified negotiation ask", "..."]
}}

Include 4 kpis and 3 sections. tone reflects whether the metric favors Kroger's argument."""

DECK_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", DECK_SYSTEM),
    ("human", DECK_INSTRUCTION),
])


def build_fact_pack(supplier: dict, objective: str) -> dict:
    chain = DECK_TEMPLATE | get_llm(temperature=0.4)
    resp = chain.invoke({
        "supplier_name": supplier["supplier"],
        "facts": _supplier_facts(supplier),
        "objective": objective,
    })
    raw = resp.content.strip()
    # Be tolerant of accidental code fences.
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "title": f"{supplier['supplier']} — Negotiation Fact-Pack",
            "subtitle": "Auto-generated",
            "hypothesis": raw[:280],
            "kpis": [],
            "sections": [],
            "asks": [],
            "_parse_error": True,
        }


# --------------------------------------------------------------------------- #
# Vendor Rehearsal (role-play the supplier)
# --------------------------------------------------------------------------- #
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


def rehearse_turn(supplier: dict, history: list[dict], user_message: str) -> str:
    """history: [{'role': 'buyer'|'vendor', 'content': str}, ...]"""
    msgs = [SystemMessage(content=_rehearsal_system(supplier))]
    for turn in history:
        # In a rehearsal, the *buyer* is the human; the vendor is the assistant.
        if turn["role"] == "buyer":
            msgs.append(HumanMessage(content=turn["content"]))
        else:
            from langchain_core.messages import AIMessage
            msgs.append(AIMessage(content=turn["content"]))
    msgs.append(HumanMessage(content=user_message))

    llm = get_llm(temperature=0.7)
    return llm.invoke(msgs).content
