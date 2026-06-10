"""Analytics Agent — a genuine tool-calling agent for the analyst-side work.

This is the neutral, grounded, pro-Kroger half of the hybrid architecture. It
binds the primitive tools in server/tools.py to the LLM and runs a manual
executor loop: the model decides which tools to call (and chains them — e.g.
query_scorecard -> retrieve_contract_clauses -> build_deck) until it has enough
to answer. Owns scorecard / brief / deck / chat.

Pure LangChain (no LangGraph): we call llm.bind_tools(...) and drive the
tool-call loop ourselves, appending ToolMessage results and re-invoking. The
adversarial Vendor Rehearsal persona is deliberately NOT here — it lives in
server/rehearsal_agent.py so the two can be evaluated independently.
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from .llm import get_llm
from .tools import ANALYTICS_TOOLS, TOOLS_BY_NAME, tool_context

MAX_ITERS = 4

ANALYTICS_SYSTEM = (
    "You are the analyst for a Kroger beverage-category COGS negotiation team. You "
    "are neutral, rigorous, and you argue from Kroger's side of the table — but only "
    "on the strength of evidence. Your prime directive: GROUND EVERY NUMBER IN TOOL "
    "OUTPUT. Never fabricate, estimate, or recall figures from memory; if you need a "
    "metric, call query_scorecard. When you make a contractual point, call "
    "retrieve_contract_clauses and cite the clause by its bracketed [Section Name]. "
    "DECK PROTOCOL — when the user asks for a deck, fact-pack, slides, or "
    "presentation, follow this exact multi-hop chain and DO NOT skip steps: "
    "(1) FIRST call query_scorecard to pull the supplier's live metrics (spend, "
    "COGS, landed cost, trend, and OTIF / fill rate as relevant); "
    "(2) THEN call retrieve_contract_clauses for that supplier (supplier_key one of "
    "pepsi, coke, kdp) to get citable clauses; "
    "(3) THEN call build_deck, passing scorecard_facts set to the query_scorecard "
    "output and clauses set to the retrieve_contract_clauses output so the deck is "
    "grounded in live numbers and cites real contract sections. "
    "NEVER call build_deck without first gathering scorecard numbers. "
    "You may chain tools: "
    "pull the numbers, pull the clauses, then synthesize. If a question is conversational "
    "and needs no data, answer briefly and practically. Be concise, quantitative, and "
    "tie every claim to a figure or a clause you actually retrieved."
)


def _to_lc_messages(history: list[dict] | None) -> list:
    """Map the UI's history (role: buyer/vendor/user/assistant) to LC messages.
    Anything that isn't clearly the assistant is treated as a human turn."""
    msgs: list = []
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content", "")
        if not content:
            continue
        if role in ("assistant", "vendor", "ai"):
            msgs.append(AIMessage(content=content))
        else:  # user / buyer / anything else
            msgs.append(HumanMessage(content=content))
    return msgs


def run(message: str, history: list[dict] | None = None) -> dict:
    """Run the tool-calling executor and return a UI-compatible envelope.

    Envelope keys: route, answer, tool_trace [{tool, args}], deck (parsed dict or
    None), sql / columns / rows (from the last query_scorecard call, if any).
    """
    llm = get_llm(temperature=0.1).bind_tools(ANALYTICS_TOOLS)

    messages: list = [SystemMessage(content=ANALYTICS_SYSTEM)]
    messages.extend(_to_lc_messages(history))
    messages.append(HumanMessage(content=message))

    tool_trace: list[dict] = []

    # The ToolContext captures structured side outputs (sql/rows/deck) the tools
    # produce, which the string tool results don't carry back to the UI.
    with tool_context() as ctx:
        final = None
        for _ in range(MAX_ITERS):
            ai: AIMessage = llm.invoke(messages)
            messages.append(ai)
            calls = getattr(ai, "tool_calls", None) or []
            if not calls:
                final = ai
                break
            for call in calls:
                name = call.get("name")
                args = call.get("args", {}) or {}
                tool_trace.append({"tool": name, "args": args})
                tool = TOOLS_BY_NAME.get(name)
                if tool is None:
                    result = f"Unknown tool '{name}'."
                else:
                    try:
                        result = tool.invoke(args)
                    except Exception as e:  # keep the loop alive; let the model recover
                        result = f"Tool '{name}' failed: {e}"
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=call.get("id", name))
                )
        else:
            # Ran out of iterations mid-tool-loop: do one final tool-free pass.
            final = llm.invoke(messages)

        answer = final.content if final is not None else ""
        return {
            "route": "analytics",
            "answer": answer,
            "tool_trace": tool_trace,
            "deck": ctx.deck,
            "sql": ctx.sql,
            "columns": ctx.columns,
            "rows": ctx.rows,
        }
