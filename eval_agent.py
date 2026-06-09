"""Agent Evaluation with LLM judges (the Quality Loop, offline mode).

Runs an eval dataset through the DEPLOYED agent endpoint and scores every
response with Mosaic AI / MLflow LLM judges:
  - Correctness        (vs expected_facts)
  - RelevanceToQuery   (is the answer on-topic)
  - Safety             (no harmful content)
  - Guidelines(...)    (custom: cites numbers; briefs cite contract clauses)

Run (VPN on): DATABRICKS_CONFIG_PROFILE=cogs-demo PYTHONPATH=. .venv/bin/python eval_agent.py
"""

from __future__ import annotations

import json
import os

import mlflow
import requests
from databricks.sdk import WorkspaceClient
from mlflow.genai.scorers import Correctness, Guidelines, RelevanceToQuery, Safety

PROFILE = os.environ.get("DATABRICKS_PROFILE", "cogs-demo")
os.environ["DATABRICKS_CONFIG_PROFILE"] = PROFILE
ENDPOINT = "agents_kroger_demo-models-cogs_negotiation_agent"
EXPERIMENT = "/Users/sumit.prakash@databricks.com/cogs_negotiation_agent_eval"

mlflow.set_tracking_uri(f"databricks://{PROFILE}")
mlflow.set_experiment(EXPERIMENT)

_w = WorkspaceClient(profile=PROFILE)
_HOST = _w.config.host
_TOK = _w.config.authenticate()["Authorization"].split(" ", 1)[1]


def predict_fn(question: str, task: str = "chat", supplier_key: str | None = None,
               objective: str = "Reduce landed COGS and improve trade-fund efficiency."):
    """Call the deployed agent endpoint and return its text answer."""
    payload = {"messages": [{"role": "user", "content": question}],
               "custom_inputs": {"task": task, "supplier_key": supplier_key, "objective": objective}}
    r = requests.post(f"{_HOST}/serving-endpoints/{ENDPOINT}/invocations",
                      headers={"Authorization": f"Bearer {_TOK}", "Content-Type": "application/json"},
                      data=json.dumps(payload), timeout=120)
    r.raise_for_status()
    return (r.json().get("messages") or [{}])[-1].get("content", "")


DATA = [
    {"inputs": {"question": "Prepare a negotiation brief to fix OTIF and claw back COGS inflation.",
                "task": "brief", "supplier_key": "kdp"},
     "expectations": {"expected_facts": [
         "Keurig Dr Pepper COGS inflation is +9.3% year over year",
         "OTIF is 88.5%, below the 95% contractual target",
         "fill rate is 94.2%", "contract expires 2026-09-30"]}},
    {"inputs": {"question": "Draft a brief to reduce landed COGS for PepsiCo.",
                "task": "brief", "supplier_key": "pepsi"},
     "expectations": {"expected_facts": [
         "PepsiCo annual spend is about $1.84B",
         "COGS rose 6.8% year over year",
         "landed cost index is 104.2"]}},
    {"inputs": {"question": "Which supplier has the highest landed cost index, and what is it?",
                "task": "chat"},
     "expectations": {"expected_facts": ["Keurig Dr Pepper has the highest landed cost index", "108.9"]}},
    {"inputs": {"question": "What is the total annual beverage spend across all suppliers?",
                "task": "chat"},
     "expectations": {"expected_facts": ["about $4.57 billion total annual spend"]}},
    {"inputs": {"question": "Open the negotiation with a firm stance on pricing.",
                "task": "rehearse", "supplier_key": "coke"}},
]

GROUNDED_NUMBERS = Guidelines(
    name="grounded_numbers",
    guidelines="The response cites specific quantitative figures (dollar amounts, "
               "percentages, or indices) drawn from the supplier data — it is not vague.")
CITES_CONTRACT = Guidelines(
    name="briefs_cite_contract",
    guidelines="If the response is a negotiation brief, it references at least one "
               "contract clause by name (e.g. in square brackets like "
               "[Service Levels & Supply Reliability]). Non-brief responses pass automatically.")


def main():
    print(f"Evaluating endpoint {ENDPOINT} over {len(DATA)} cases with LLM judges…")
    with mlflow.start_run(run_name="cogs_agent_llm_judge_eval") as run:
        results = mlflow.genai.evaluate(
            data=DATA,
            predict_fn=predict_fn,
            scorers=[Correctness(), RelevanceToQuery(), Safety(),
                     GROUNDED_NUMBERS, CITES_CONTRACT],
        )
    print("\n=== Aggregate judge metrics ===")
    for k, v in (results.metrics or {}).items():
        print(f"  {k}: {v}")
    print(f"\nExperiment: {_HOST}/ml/experiments  · run_id={run.info.run_id}")


if __name__ == "__main__":
    main()
