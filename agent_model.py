"""COGS Negotiation Agent packaged as an MLflow ChatAgent.

This is the SAME agent logic as the app (server/agents.py), wrapped in the
MLflow ChatAgent interface so it can be registered in Unity Catalog and deployed
to a Mosaic AI Model Serving endpoint — giving it inference tables, evaluation,
and monitoring.

CRUCIAL: the LLM provider switch is preserved. This model calls server.llm.get_llm(),
which reads LLM_PROVIDER at runtime. Set that env var on the serving endpoint to
route mosaic <-> litellm without changing or re-logging the model.

`custom_inputs` drives which sub-agent runs:
  {"task": "brief"|"deck"|"rehearse"|"chat", "supplier_key": "pepsi", "objective": "..."}
"""

from __future__ import annotations

import json
from typing import Any, Optional

from mlflow.models import set_model
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse

from server.agents import build_fact_pack, build_negotiation_brief, rehearse_turn
from server.data import get_supplier

DEFAULT_OBJECTIVE = (
    "Reduce landed COGS and improve trade-fund efficiency for the upcoming contract cycle."
)


class CogsNegotiationAgent(ChatAgent):
    def predict(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[Any] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> ChatAgentResponse:
        ci = custom_inputs or {}
        task = str(ci.get("task", "chat")).lower()
        # No default supplier: chat/default then injects ALL suppliers' facts so it
        # can answer cross-supplier questions; brief/deck/rehearse require an explicit one.
        supplier_key = ci.get("supplier_key")
        supplier_key = str(supplier_key) if supplier_key else None
        objective = str(ci.get("objective", DEFAULT_OBJECTIVE))

        last = messages[-1].content if messages else ""
        supplier = get_supplier(supplier_key) if supplier_key else None

        if task in ("brief", "deck", "rehearse") and not supplier:
            text = f"Unknown supplier '{supplier_key}'. Try pepsi, coke, or kdp."
        elif task == "brief":
            text = build_negotiation_brief(supplier, objective)  # RAG-grounded
        elif task == "deck":
            text = json.dumps(build_fact_pack(supplier, objective), indent=2)
        elif task == "rehearse":
            history = [
                {"role": "buyer" if m.role == "user" else "vendor", "content": m.content}
                for m in messages[:-1]
            ]
            text = rehearse_turn(supplier, history, last)
        else:
            # Default / chat: answer from the bundled supplier facts via the LLM.
            # (Genie-backed NL->SQL routing lives in the app, where the app SP has
            # Genie data access; a served model runs Genie under an automatic-auth
            # identity that can't execute the downstream SQL, so we keep the served
            # model self-contained and dependency-free here.)
            from langchain_core.messages import HumanMessage, SystemMessage

            from server.agents import _supplier_facts
            from server.data import SUPPLIERS
            from server.llm import get_llm

            facts = (
                _supplier_facts(supplier)
                if supplier
                else "\n".join(_supplier_facts(s) for s in SUPPLIERS)
            )
            sys = (
                "You are a Kroger beverage-category COGS negotiation analyst. Answer the "
                "question using ONLY these supplier facts; be concise and quantitative.\n\n"
                f"{facts}"
            )
            text = get_llm(temperature=0.2).invoke(
                [SystemMessage(content=sys), HumanMessage(content=last)]
            ).content

        return ChatAgentResponse(
            messages=[ChatAgentMessage(role="assistant", content=text, id="0")]
        )


AGENT = CogsNegotiationAgent()
set_model(AGENT)
