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
    DatabricksTable,
    DatabricksVectorSearchIndex,
)

import deploy_config
from deploy_config import (
    CATALOG,
    EMBED_ENDPOINT,
    LLM_ENDPOINT,
    PROFILE,
    SCHEMA,
    UC_MODEL,
)

# Two profile env vars must agree:
#  - DATABRICKS_PROFILE      -> read by our server/config.py
#  - DATABRICKS_CONFIG_PROFILE -> read by the Databricks SDK's default auth,
#    which MLflow uses internally for artifact upload / registry calls.
# log_model also validates input_example by running predict() (a live LLM call),
# so both must point at the right workspace.
os.environ["DATABRICKS_PROFILE"] = PROFILE
os.environ["DATABRICKS_CONFIG_PROFILE"] = PROFILE

mlflow.set_tracking_uri(f"databricks://{PROFILE}")
mlflow.set_registry_uri(f"databricks-uc://{PROFILE}")

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
    w = deploy_config.get_workspace_client()
    # Resolve workspace-specific IDs now: deploy_state.json > env > cogs-demo default.
    genie_space = deploy_config.genie_space_id()
    contract_idx = deploy_config.contract_index()
    warehouse = deploy_config.resolve_warehouse_id(w)

    experiment = os.environ.get(
        "MLFLOW_EXPERIMENT",
        f"{deploy_config.resolve_parent_path(w)}/cogs_negotiation_agent",
    )
    mlflow.set_experiment(experiment)

    deck_tables = [
        "supplier_scorecard", "regional_performance", "landed_cost_metrics",
        "commodity_input_costs", "competitive_benchmarks", "macro_indicators",
        "sku_cost_waterfall",
    ]
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
                DatabricksServingEndpoint(endpoint_name=EMBED_ENDPOINT),
                DatabricksVectorSearchIndex(index_name=contract_idx),
                DatabricksGenieSpace(genie_space_id=genie_space),
                DatabricksSQLWarehouse(warehouse_id=warehouse),
                # Tables the deterministic deck builder (server/deck_data.py) reads
                # via direct warehouse SQL. Declaring them grants the served model's
                # automatic-auth identity SELECT so the served deck is grounded in
                # live data (not just bundled facts) — no Genie / no OBO required.
                *[DatabricksTable(table_name=f"{CATALOG}.{SCHEMA}.{t}") for t in deck_tables],
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
            # data tools the supervisor / RAG brief use — workspace-portable
            "GENIE_SPACE_ID": genie_space,
            "CONTRACT_INDEX": contract_idx,
            "COGS_CATALOG": CATALOG,
            "COGS_SCHEMA": SCHEMA,
            "WAREHOUSE_ID": warehouse,
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
