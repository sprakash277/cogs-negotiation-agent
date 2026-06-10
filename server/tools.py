"""Primitive LangChain tools for the Analytics Agent.

These wrap the app's existing grounded capabilities (Genie NL->SQL, contract
retrieval, the Fact-Pack deck builder) as ``@tool``-decorated callables so a
genuine tool-calling agent can decide *which* to use and chain them. Each tool
returns a compact, citable string the LLM can quote numbers / section names from.

Because the LLM only ever sees the string return value, structured side outputs
(the SQL Genie generated, the result columns/rows, the parsed deck dict) would
otherwise be lost to the UI. We capture them via a request-scoped ``ToolContext``
held in a ``contextvars.ContextVar``: the executor (analytics_agent.run) opens a
context for the request, each tool stashes its structured result into it, and
run() reads it back to rebuild the UI envelope. Using a ContextVar keeps the
LLM-facing tool schemas clean (the LLM never sees a context argument) and is
safe under concurrent requests. Pure LangChain — no LangGraph.
"""

from __future__ import annotations

import contextvars
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.tools import tool

from . import genie, knowledge
from .agents import build_fact_pack
from .data import get_supplier


@dataclass
class ToolContext:
    """Per-request scratchpad for structured side outputs (SQL / columns / rows /
    parsed deck) that the LLM-facing string return value would otherwise drop."""

    sql: Optional[str] = None
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    deck: Optional[dict] = None


_CTX: contextvars.ContextVar[Optional[ToolContext]] = contextvars.ContextVar(
    "tool_context", default=None
)


@contextmanager
def tool_context():
    """Open a fresh ToolContext for the duration of one agent run."""
    ctx = ToolContext()
    token = _CTX.set(ctx)
    try:
        yield ctx
    finally:
        _CTX.reset(token)


def _render_rows(columns: list, rows: list, limit: int = 10) -> str:
    """Small markdown-ish rendering of a result set so the agent can cite numbers."""
    if not columns or not rows:
        return ""
    head = " | ".join(str(c) for c in columns)
    body = "\n".join(" | ".join(str(c) for c in row) for row in rows[:limit])
    more = f"\n…({len(rows) - limit} more rows)" if len(rows) > limit else ""
    return f"{head}\n{body}{more}"


@tool
def query_scorecard(question: str) -> str:
    """Answer a quantitative question about Kroger beverage-category COGS using the
    Genie NL->SQL space over the certified scorecard data (spend, COGS, landed-cost
    index, OTIF, fill rate, rebates, trade funds, regional performance, rankings,
    comparisons). Use this for ANY question that needs real numbers. Returns Genie's
    narrative plus the SQL it ran and a small rendering of the result rows so you can
    cite exact figures."""
    g = genie.ask(question)
    text = g.get("text")
    sql = g.get("sql")
    columns = g.get("columns", []) or []
    rows = g.get("rows", []) or []
    ctx = _CTX.get()
    if ctx is not None:
        ctx.sql = sql
        ctx.columns = columns
        ctx.rows = rows
    if not text and not rows:
        return "Genie returned no answer or rows for that question. Try rephrasing the metric or supplier."
    parts: list[str] = []
    if text:
        parts.append(text.strip())
    table = _render_rows(columns, rows)
    if table:
        parts.append("RESULT ROWS:\n" + table)
    if sql:
        parts.append("SQL:\n" + sql.strip())
    return "\n\n".join(parts)


@tool
def retrieve_contract_clauses(query: str, supplier_key: Optional[str] = None) -> str:
    """Retrieve the most relevant Master Supply Agreement contract clauses for a
    supplier from the contract vector index. Use this whenever the user asks about
    contractual terms (pricing, COGS adjustment, rebates, trade funds, service
    levels, termination / re-source rights) or when drafting a negotiation brief.
    supplier_key is one of pepsi, coke, kdp (or omit to search across suppliers).
    Returns a formatted clause block; cite the bracketed [Section Name] when you
    rely on a clause."""
    clauses = knowledge.retrieve(query=query, supplier_key=supplier_key, k=4)
    return knowledge.context_block(clauses)


@tool
def build_deck(
    supplier_key: str,
    objective: str,
    scorecard_facts: Optional[str] = None,
    clauses: Optional[str] = None,
) -> str:
    """Build the FIXED 15-slide, 5-act negotiation deck (Opening, Market Context,
    Cost Breakdown, Levers, Close) for a supplier, fully grounded in the certified
    kroger_demo.cogs tables. Call this ONLY when the user explicitly asks for a
    deck, fact-pack, slides, or presentation. supplier_key is one of pepsi, coke,
    kdp. objective is the negotiation goal.

    GROUND THE DECK IN LIVE DATA FIRST. Before calling this you should:
      1. Call query_scorecard to pull the supplier's live metrics (spend, COGS,
         landed cost, YoY trend, OTIF / fill rate as relevant), then pass that
         tool's output in as ``scorecard_facts``.
      2. Call retrieve_contract_clauses for the same supplier and pass that
         output in as ``clauses``.
    Passing scorecard_facts makes every KPI value reflect the live numbers; passing
    clauses makes section callouts cite real contract [Section Names]. Omitting them
    falls back to a static baseline (lower fidelity) — avoid that for real requests.
    Returns the deck as a JSON string."""
    supplier = get_supplier(supplier_key)
    if not supplier:
        return (f"Unknown supplier '{supplier_key}'. Use one of: pepsi (PepsiCo), "
                f"coke (The Coca-Cola Company), kdp (Keurig Dr Pepper).")
    deck = build_fact_pack(supplier, objective, scorecard_facts=scorecard_facts, clauses=clauses)
    ctx = _CTX.get()
    if ctx is not None:
        ctx.deck = deck
    return json.dumps(deck)


# The tools the Analytics Agent binds to the LLM, plus a name->callable map the
# executor loop uses to dispatch tool calls back to the underlying function.
ANALYTICS_TOOLS = [query_scorecard, retrieve_contract_clauses, build_deck]
TOOLS_BY_NAME: dict[str, Any] = {t.name: t for t in ANALYTICS_TOOLS}
