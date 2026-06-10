"""COGS Negotiation Agent packaged as an MLflow ChatAgent.

This wraps the SAME hybrid agent logic as the app in the MLflow ChatAgent
interface so it can be registered in Unity Catalog and deployed to a Mosaic AI
Model Serving endpoint — giving it inference tables, evaluation, and monitoring.

CRUCIAL: the LLM provider switch is preserved. This model calls server.llm.get_llm(),
which reads LLM_PROVIDER at runtime. Set that env var on the serving endpoint to
route mosaic <-> litellm without changing or re-logging the model.

`custom_inputs` keeps explicit control for callers who want it:
  {"task": "brief"|"deck"|"rehearse"|"chat", "supplier_key": "pepsi", "objective": "..."}

Routing mirrors the app's hybrid split:
  task == "rehearse"            -> Rehearsal Agent (adversarial vendor persona)
  everything else (brief/deck/
  chat/none)                    -> Analytics Agent (grounded tool-calling analyst)
"""

from __future__ import annotations

import json
from typing import Any, Optional

from mlflow.models import set_model
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse

from server import analytics_agent, rehearsal_agent
from server.agents import build_fact_pack, build_negotiation_brief
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
        supplier_key = ci.get("supplier_key")
        supplier_key = str(supplier_key) if supplier_key else None

        last = messages[-1].content if messages else ""
        history = [
            {"role": "buyer" if m.role == "user" else "vendor", "content": m.content}
            for m in messages[:-1]
        ]

        objective = str(ci.get("objective", DEFAULT_OBJECTIVE))

        if task in ("rehearse", "deck", "brief"):
            # Explicit tasks run the DETERMINISTIC builders directly — NOT the
            # tool-calling Analytics Agent. On a Model Serving endpoint the agent's
            # first step (query_scorecard -> Genie) fails under the auto-auth
            # identity, which would make the agent bail to prose. The builders are
            # self-contained: deck grounds via deck_data direct warehouse SQL, brief
            # via Vector Search — both work under automatic-auth passthrough (the
            # warehouse + cogs tables + VS index are declared resources). This keeps
            # the served model Genie-free, so it also works for eval/monitoring.
            supplier = get_supplier(supplier_key) if supplier_key else None
            if not supplier:
                text = f"Unknown supplier '{supplier_key}'. Try pepsi, coke, or kdp."
            elif task == "rehearse":
                text = rehearsal_agent.run(supplier, history, last)["answer"]
            elif task == "deck":
                text = json.dumps(build_fact_pack(supplier, objective), indent=2)
            else:  # brief
                text = build_negotiation_brief(supplier, objective)
        else:
            # chat / NL with no explicit task -> the tool-calling Analytics Agent
            # decides which tools to run. If Genie is unreachable server-side it
            # degrades to a grounded LLM answer (never a failed deck). If it built a
            # deck, surface the JSON in the content so downstream consumers get it.
            result = analytics_agent.run(last, history)
            text = result.get("answer") or ""
            if result.get("deck"):
                text = (text + "\n\n" if text else "") + json.dumps(result["deck"], indent=2)

        return ChatAgentResponse(
            messages=[ChatAgentMessage(role="assistant", content=text, id="0")]
        )


AGENT = CogsNegotiationAgent()
set_model(AGENT)
