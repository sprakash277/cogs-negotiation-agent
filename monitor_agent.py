"""Continuous production monitoring — schedule LLM judges over live agent traces.

Registers scheduled scorers against the agent's MLflow experiment so every
(sampled) production request to the served agent is automatically judged for
Safety, Relevance, and grounded-numbers over time. This is the online half of
the Quality Loop (the offline half is eval_agent.py).

Run (VPN on): DATABRICKS_CONFIG_PROFILE=cogs-demo PYTHONPATH=. .venv/bin/python monitor_agent.py
"""

from __future__ import annotations

import os

import mlflow
from mlflow.genai.scorers import (
    Guidelines, RelevanceToQuery, Safety, ScorerSamplingConfig,
)

PROFILE = os.environ.get("DATABRICKS_PROFILE", "cogs-demo")
os.environ["DATABRICKS_CONFIG_PROFILE"] = PROFILE
# The experiment the agent was logged to / where its production traces land.
EXPERIMENT_ID = os.environ.get("AGENT_EXPERIMENT_ID", "3111426776316359")

mlflow.set_tracking_uri(f"databricks://{PROFILE}")

GROUNDED_NUMBERS = Guidelines(
    name="grounded_numbers",
    guidelines="The response cites specific quantitative figures (dollar amounts, "
               "percentages, or indices) — it is not vague.")

SCORERS = [Safety(), RelevanceToQuery(), GROUNDED_NUMBERS]


def main():
    print(f"Registering scheduled scorers on experiment {EXPERIMENT_ID}…")
    for sc in SCORERS:
        name = getattr(sc, "name", sc.__class__.__name__)
        try:
            sc.register(experiment_id=EXPERIMENT_ID)
        except Exception as e:
            print(f"  • {name}: register note ({e})")
        sc.start(experiment_id=EXPERIMENT_ID,
                 sampling_config=ScorerSamplingConfig(sample_rate=1.0))
        print(f"  • {name}: scheduled (sample_rate=1.0)")
    print("\nProduction monitoring active. Judges will score sampled live traffic to the agent.")
    print("View scores in the experiment's traces / evaluation-monitoring tab.")


if __name__ == "__main__":
    main()
