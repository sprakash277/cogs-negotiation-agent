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
from typing import Literal, Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

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
# Fact-Pack & Deck — FIXED 15-slide, 5-act structure
# --------------------------------------------------------------------------- #
# The deck is a CONTRACT: 15 slides across 5 acts, each slide grounded in a
# specific source. DECK_MANIFEST is the single source of truth for slide_no,
# act, title, purpose, and which grounded data feeds it. The builder generates
# ONE act at a time (5 structured-output LLM calls), injecting that act's
# manifest entries + that act's real data, then validates/repairs the result so
# we NEVER return a deck missing a slide.
#
# grounding ∈ {scorecard, commodity, competitive, macro, waterfall, bridge,
#              margin, clauses, modeled, synthesis}
DECK_MANIFEST: list[dict] = [
    # Act 1 — Opening
    {"no": 1, "act": "Opening", "title": "Executive Summary",
     "purpose": "The ask, timeline, key levers, and target outcome on one slide.",
     "grounding": "synthesis"},
    {"no": 2, "act": "Opening", "title": "Partnership Overview",
     "purpose": "Volume history, strategic importance, growth trajectory.",
     "grounding": "scorecard"},
    # Act 2 — Market Context
    {"no": 3, "act": "Market Context", "title": "Commodity & Input Cost Trends",
     "purpose": "Raw-material indices, freight, energy over 12-24 months.",
     "grounding": "commodity"},
    {"no": 4, "act": "Market Context", "title": "Competitive Landscape",
     "purpose": "Shelf-price benchmarks and alternate-supplier quotes.",
     "grounding": "competitive"},
    {"no": 5, "act": "Market Context", "title": "Macroeconomic Factors",
     "purpose": "FX, tariffs, labor inflation, supply-chain disruption.",
     "grounding": "macro"},
    # Act 3 — Cost Breakdown
    {"no": 6, "act": "Cost Breakdown", "title": "SKU-level Cost Waterfall",
     "purpose": "Materials -> mfg -> packaging -> freight -> duty -> landed.",
     "grounding": "waterfall"},
    {"no": 7, "act": "Cost Breakdown", "title": "Year-over-Year Cost Bridge",
     "purpose": "Prior COGS -> variances by driver -> proposed COGS.",
     "grounding": "bridge"},
    {"no": 8, "act": "Cost Breakdown", "title": "Margin Impact Analysis",
     "purpose": "Gross margin by SKU, current vs proposed.",
     "grounding": "margin"},
    # Act 4 — Levers
    {"no": 9, "act": "Levers", "title": "Volume Commitment Scenarios",
     "purpose": "Tiered pricing ladders against committed volume.",
     "grounding": "modeled"},
    {"no": 10, "act": "Levers", "title": "Payment Terms & Working Capital",
     "purpose": "Net terms, early-pay discount, consignment.",
     "grounding": "clauses"},
    {"no": 11, "act": "Levers", "title": "Spec/Packaging Changes",
     "purpose": "SKU rationalization, pack consolidation, material substitution.",
     "grounding": "clauses"},
    {"no": 12, "act": "Levers", "title": "Promotional & Trade Funding",
     "purpose": "Co-op, off-invoice, scan-backs, MDF.",
     "grounding": "clauses"},
    # Act 5 — Close
    {"no": 13, "act": "Close", "title": "Scenario Comparison",
     "purpose": "Two-to-three deal structures side by side.",
     "grounding": "modeled"},
    {"no": 14, "act": "Close", "title": "Proposed Terms & Ask",
     "purpose": "Clean one-pager: price, effective date, volume commitment, payment terms, review cadence.",
     "grounding": "synthesis"},
    {"no": 15, "act": "Close", "title": "Appendix",
     "purpose": "Raw data, supplier audits, references.",
     "grounding": "synthesis"},
]

# Ordered list of (act_name, [slide_no, ...]) the builder iterates over.
ACTS: list[tuple[str, list[int]]] = []
for _m in DECK_MANIFEST:
    if not ACTS or ACTS[-1][0] != _m["act"]:
        ACTS.append((_m["act"], []))
    ACTS[-1][1].append(_m["no"])

_MANIFEST_BY_NO = {m["no"]: m for m in DECK_MANIFEST}


# --- Structured-output models (pydantic v2) -------------------------------- #
class DataCallout(BaseModel):
    label: str = Field(..., description="Short metric label, e.g. 'Annual spend'.")
    value: str = Field(..., description="Display value taken verbatim from the injected data, e.g. '$1.84B'.")
    delta: Optional[str] = Field(None, description="Optional change/trend, e.g. '+6.8% YoY'.")
    source: str = Field(..., description="Table or contract section the value came from, e.g. 'supplier_scorecard'.")


class ChartSpec(BaseModel):
    kind: Literal["line", "waterfall", "bridge", "bars", "scenario", "none"] = "none"
    series: list[dict] = Field(default_factory=list, description="Chart points; shape depends on kind.")


class SlideContent(BaseModel):
    slide_no: int
    title: str
    headline: str = Field(..., description="One-line takeaway / the slide's argument.")
    narrative: str = Field(..., description="2-4 sentences of supporting prose.")
    bullets: list[str] = Field(default_factory=list)
    data_callouts: list[DataCallout] = Field(default_factory=list)
    chart: Optional[ChartSpec] = None
    citations: list[str] = Field(default_factory=list, description="Contract [Section Names] or table sources cited.")


class DeckAct(BaseModel):
    act: str
    slides: list[SlideContent]


DECK_SYSTEM = (
    "You are an analytics storyteller building ONE ACT of a fixed 15-slide Kroger "
    "beverage-category COGS negotiation deck. You argue from Kroger's side of the "
    "table, but only on the strength of evidence. HARD RULES: "
    "(1) Every numeric value in a data_callout MUST come from the GROUNDED DATA "
    "block provided for this act — never invent, estimate, or recall a figure. "
    "(2) Set each data_callout.source to the exact table or contract section the "
    "value came from (e.g. 'supplier_scorecard', 'commodity_input_costs', "
    "'sku_cost_waterfall', or a contract [Section Name]). "
    "(3) For slides whose grounding is 'modeled' or 'synthesis' and that have no "
    "hard data, you may still propose structures, but label any non-sourced figure "
    "with source 'analyst input' — do NOT pretend it came from a table. "
    "(4) For slides 10-12 (payment terms, spec/packaging, trade funding), cite the "
    "relevant contract [Section Names] from the CONTRACT CLAUSES in `citations`. "
    "(5) Produce EXACTLY the slides listed in the SLIDE MANIFEST for this act, with "
    "slide_no and title matching the manifest verbatim. "
    "Pick a chart.kind that fits the data (line for trends, waterfall for cost "
    "components, bridge for the YoY bridge, bars for comparisons, scenario for "
    "deal options, none if no chart helps) and populate chart.series from the data. "
    "(6) Keep chart.series COMPACT — at most ~15 points total; downsample or pick "
    "the most decision-relevant inputs rather than echoing every data point. Keep "
    "narrative to 2-4 sentences and bullets to <=4 so the act fits the response budget."
)

DECK_HUMAN = """Build act "{act_name}" of the negotiation deck for {supplier_name}.

OBJECTIVE: {objective}

SLIDE MANIFEST FOR THIS ACT (produce exactly these, slide_no + title verbatim):
{manifest}

SUPPLIER BASELINE (context only; prefer the grounded data below for numbers):
{facts}

GROUNDED DATA FOR THIS ACT (the ONLY source of numeric figures — JSON):
{grounded}

CONTRACT CLAUSES (cite [Section Names] for slides 10-12 when relevant):
{clauses}

Return the act with one SlideContent per manifest entry."""

DECK_ACT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", DECK_SYSTEM),
    ("human", DECK_HUMAN),
])


def _act_grounded_data(act_name: str, supplier_key: str, scorecard_facts: str | None) -> dict:
    """Pull the real, deterministic data each act needs from server.deck_data.

    Degrades gracefully: any per-call failure yields an empty value, and if the
    deck_data module / connection is unavailable entirely we return {} so the
    builder still produces a (lower-fidelity) deck from the supplier baseline.
    """
    try:
        from . import deck_data
    except Exception:
        return {}

    def _safe(fn, *args):
        try:
            return fn(*args)
        except Exception:
            return None

    if act_name == "Opening":
        return {"partnership_overview": _safe(deck_data.partnership_overview, supplier_key),
                "live_scorecard_text": scorecard_facts}
    if act_name == "Market Context":
        # commodity_trends carries a full 24-month series per input (7 x ~13 pts).
        # That bloats the prompt AND tempts the model to echo every point into
        # chart.series, blowing the output-token budget. Downsample each series to
        # quarterly points so the trend stays legible but the payload stays small.
        commodity = _safe(deck_data.commodity_trends) or {}
        series = commodity.get("series")
        if isinstance(series, dict):
            commodity["series"] = {
                name: pts[::3] + (pts[-1:] if pts and (len(pts) - 1) % 3 != 0 else [])
                for name, pts in series.items()
            }
        return {"commodity_trends": commodity,
                "competitive_landscape": _safe(deck_data.competitive_landscape, supplier_key),
                "macro_factors": _safe(deck_data.macro_factors)}
    if act_name == "Cost Breakdown":
        return {"cost_waterfall": _safe(deck_data.cost_waterfall, supplier_key),
                "yoy_bridge": _safe(deck_data.yoy_bridge, supplier_key),
                "margin_impact": _safe(deck_data.margin_impact, supplier_key)}
    if act_name == "Levers":
        return {"trade_funding": _safe(deck_data.trade_funding, supplier_key),
                "partnership_overview": _safe(deck_data.partnership_overview, supplier_key)}
    # Close — synthesizes from everything; give it the headline numbers again.
    return {"partnership_overview": _safe(deck_data.partnership_overview, supplier_key),
            "yoy_bridge": _safe(deck_data.yoy_bridge, supplier_key),
            "trade_funding": _safe(deck_data.trade_funding, supplier_key)}


def _placeholder_slide(slide_no: int) -> SlideContent:
    m = _MANIFEST_BY_NO[slide_no]
    return SlideContent(
        slide_no=slide_no,
        title=m["title"],
        headline="Analyst input required",
        narrative=m["purpose"],
        bullets=[],
        data_callouts=[],
        chart=ChartSpec(kind="none", series=[]),
        citations=[],
    )


def _generate_act(
    act_name: str,
    slide_nos: list[int],
    supplier: dict,
    objective: str,
    grounded: dict,
    clauses: str | None,
) -> list[SlideContent]:
    """Generate one act's slides via structured output, validating slide_no/title
    against the manifest. Retries ONCE on a bad result; fills any still-missing or
    mismatched slide with a structured placeholder. Never raises."""
    manifest_lines = "\n".join(
        f"- slide {n}: \"{_MANIFEST_BY_NO[n]['title']}\" — {_MANIFEST_BY_NO[n]['purpose']}"
        for n in slide_nos
    )
    payload = {
        "act_name": act_name,
        "supplier_name": supplier["supplier"],
        "objective": objective,
        "manifest": manifest_lines,
        "facts": _supplier_facts(supplier),
        "grounded": json.dumps(grounded, default=str, indent=2),
        "clauses": clauses or "(no contract clauses were gathered)",
    }

    def _attempt() -> dict[int, SlideContent]:
        # Decks emit large structured payloads (multiple slides, each with bullets,
        # callouts and a chart series). The default 4096 output cap truncates an
        # act mid-generation (LengthFinishReasonError) and loses the whole act, so
        # give act generation a wider output budget.
        llm = get_llm(temperature=0.2, max_tokens=8192).with_structured_output(DeckAct)
        chain = DECK_ACT_TEMPLATE | llm
        act: DeckAct = chain.invoke(payload)
        # Index by slide_no, snapping titles back to the manifest to guarantee match.
        out: dict[int, SlideContent] = {}
        for s in act.slides:
            if s.slide_no in slide_nos:
                s.title = _MANIFEST_BY_NO[s.slide_no]["title"]
                out[s.slide_no] = s
        return out

    by_no: dict[int, SlideContent] = {}
    try:
        by_no = _attempt()
    except Exception:
        by_no = {}
    # Retry once if any slide is missing.
    if any(n not in by_no for n in slide_nos):
        try:
            retry = _attempt()
            by_no = {**retry, **by_no} if not by_no else {**by_no, **{k: v for k, v in retry.items() if k not in by_no}}
        except Exception:
            pass
    # Fill any still-missing slide with a structured placeholder.
    return [by_no.get(n) or _placeholder_slide(n) for n in slide_nos]


def build_fact_pack(
    supplier: dict,
    objective: str,
    scorecard_facts: str | None = None,
    clauses: str | None = None,
) -> dict:
    """Build the FIXED 15-slide, 5-act negotiation deck, fully grounded in real data.

    Generates ONE act at a time (5 structured-output LLM calls), injecting that
    act's manifest entries + its deterministic grounded data (from
    server.deck_data) so every numeric callout traces back to a table or contract
    section. When the agent has already gathered LIVE grounding (scorecard_facts
    from query_scorecard, clauses from retrieve_contract_clauses), they are passed
    through to the prompt as additional context.

    Backward-safe: the legacy caller in server/routes/agentic.py invokes
    build_fact_pack(supplier, objective) with no scorecard_facts/clauses — that
    still works, degrading to the supplier baseline + whatever deck_data returns.
    NEVER returns a deck missing slides.
    """
    supplier_key = supplier.get("key", "")
    act_objs: list[DeckAct] = []
    for act_name, slide_nos in ACTS:
        grounded = _act_grounded_data(act_name, supplier_key, scorecard_facts)
        slides = _generate_act(act_name, slide_nos, supplier, objective, grounded, clauses)
        act_objs.append(DeckAct(act=act_name, slides=slides))

    deck = {
        "title": f"{supplier['supplier']} — COGS Negotiation Deck",
        "subtitle": f"{supplier.get('category', 'Beverage')} · 5-act fact pack",
        "objective": objective,
        "supplier": supplier["supplier"],
        "acts": [a.model_dump() for a in act_objs],
        "format_version": "15-slide-v1",
    }
    return deck


# --------------------------------------------------------------------------- #
# Vendor Rehearsal (role-play the supplier)
# --------------------------------------------------------------------------- #
def rehearse_turn(supplier: dict, history: list[dict], user_message: str) -> str:
    """Thin shim: the adversarial vendor persona now lives in its own module
    (server/rehearsal_agent.py) so it can be evaluated independently. This symbol
    is kept for back-compat with agent_model.py and server/routes/agentic.py, which
    expect a plain string reply. Imported lazily to avoid a circular import
    (rehearsal_agent re-uses _supplier_facts from here).

    history: [{'role': 'buyer'|'vendor', 'content': str}, ...]
    """
    from . import rehearsal_agent

    return rehearsal_agent.run(supplier, history, user_message)["answer"]
