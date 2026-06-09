"""Log -> register (UC) -> deploy the COGS Negotiation Agent as a served model.

Run locally (VPN on) against the cogs-demo workspace:
    .venv/bin/python deploy_agent.py

Steps:
  1. Log the ChatAgent in agent_model.py to MLflow, bundling server/ as code.
  2. Register it to Unity Catalog as kroger_demo.models.cogs_negotiation_agent.
  3. Deploy to a Mosaic AI Model Serving endpoint, setting LLM_PROVIDER so the
     served agent routes through Mosaic (default) — switchable to litellm later.
"""

from __future__ import annotations

import os

import mlflow
from mlflow.models.resources import (
    DatabricksGenieSpace,
    DatabricksServingEndpoint,
    DatabricksSQLWarehouse,
    DatabricksVectorSearchIndex,
)

PROFILE = os.environ.get("DATABRICKS_PROFILE", "cogs-demo")
GENIE_SPACE_ID = "01f1642219cf135cb84f7e0dbc8d6957"
CONTRACT_INDEX = "kroger_demo.cogs.contract_chunks_index"
WAREHOUSE_ID = "a455a68035c1f578"
# Two profile env vars must agree:
#  - DATABRICKS_PROFILE      -> read by our server/config.py
#  - DATABRICKS_CONFIG_PROFILE -> read by the Databricks SDK's default auth,
#    which MLflow uses internally for artifact upload / registry calls.
# log_model also validates input_example by running predict() (a live LLM call),
# so both must point at the right workspace.
os.environ["DATABRICKS_PROFILE"] = PROFILE
os.environ["DATABRICKS_CONFIG_PROFILE"] = PROFILE

UC_MODEL = "kroger_demo.models.cogs_negotiation_agent"
LLM_ENDPOINT = "databricks-claude-sonnet-4-5"
EXPERIMENT = os.environ.get(
    "MLFLOW_EXPERIMENT", "/Users/sumit.prakash@databricks.com/cogs_negotiation_agent"
)

mlflow.set_tracking_uri(f"databricks://{PROFILE}")
mlflow.set_registry_uri(f"databricks-uc://{PROFILE}")
mlflow.set_experiment(EXPERIMENT)

INPUT_EXAMPLE = {
    "messages": [{"role": "user", "content": "Prepare a negotiation brief for PepsiCo."}],
    "custom_inputs": {"task": "brief", "supplier_key": "pepsi", "objective": "Reduce landed COGS by 3%."},
}

PIP_REQS = [
    "mlflow>=2.20",
    "langchain>=0.3",
    "langchain-core>=0.3",
    "langchain-openai>=0.2",
    "databricks-sdk>=0.30",
    "pydantic>=2.6",
]


def main() -> None:
    print(f"Logging agent to MLflow (profile={PROFILE})…")
    with mlflow.start_run(run_name="cogs_negotiation_agent"):
        info = mlflow.pyfunc.log_model(
            name="agent",
            python_model="agent_model.py",
            code_paths=["server"],
            input_example=INPUT_EXAMPLE,
            pip_requirements=PIP_REQS,
            resources=[
                DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT),
                DatabricksServingEndpoint(endpoint_name="databricks-gte-large-en"),
                DatabricksVectorSearchIndex(index_name=CONTRACT_INDEX),
                DatabricksGenieSpace(genie_space_id=GENIE_SPACE_ID),
                DatabricksSQLWarehouse(warehouse_id=WAREHOUSE_ID),
            ],
            registered_model_name=UC_MODEL,
        )
    print(f"Registered {UC_MODEL} -> version {info.registered_model_version}")

    print("Deploying to Mosaic AI Model Serving…")
    from databricks import agents

    deployment = agents.deploy(
        UC_MODEL,
        info.registered_model_version,
        environment_vars={
            # === the preserved LLM switch — change here to flip providers ===
            "LLM_PROVIDER": "mosaic",
            "LLM_MODEL": LLM_ENDPOINT,
            # data tools the supervisor / RAG brief use
            "GENIE_SPACE_ID": GENIE_SPACE_ID,
            "CONTRACT_INDEX": CONTRACT_INDEX,
            # For litellm:
            #   "LLM_PROVIDER": "litellm",
            #   "LITELLM_BASE_URL": "http://<kraig-litellm-proxy>:4000",
            #   "LITELLM_API_KEY": "{{secrets/<scope>/<key>}}",
            #   "LITELLM_MODEL": "claude-sonnet-4",
        },
    )
    print("Deployed.")
    print("  endpoint:", getattr(deployment, "endpoint_name", "(see Serving UI)"))
    print("  review app / query:", getattr(deployment, "query_endpoint", ""))


if __name__ == "__main__":
    main()
