"""One-command bootstrap of the COGS Negotiation Agent's data + AI assets.

Recreates the whole demo's workspace-side foundation in ANY fresh Databricks
workspace, in dependency order, capturing created IDs (Genie space, dashboard,
warehouse, vector index) into ``deploy_state.json`` as it goes. Downstream steps
and the app/served model read those IDs back from state.

Run (VPN on):
    python bootstrap.py                 # data + Genie + Vector Search + dashboard
    python bootstrap.py --deploy-agent  # ... and also log/register/serve the agent

Configure the target via env (or a .env you source) — see .env.example. With no
env set it targets the existing cogs-demo workspace unchanged.

It does NOT auto-run the app sync/deploy (slow + needs VPN). At the end it prints
deploy_state.json, the exact app.yaml env block to paste, and the follow-up
commands.
"""

from __future__ import annotations

import json
import sys

import deploy_config

# Build steps in dependency order. Each module exposes a no-arg main() and writes
# its created IDs into deploy_state.json.
import build_dashboard
import build_genie
import build_knowledge
import build_market_data
import data_foundation

STEPS = [
    ("data_foundation", data_foundation.main),
    ("build_market_data", build_market_data.main),
    ("build_genie", build_genie.main),
    ("build_knowledge", build_knowledge.main),
    ("build_dashboard", build_dashboard.main),
]


def _run_steps() -> None:
    for name, fn in STEPS:
        print(f"\n{'=' * 70}\n▶ {name}\n{'=' * 70}")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — surface + stop on first failure
            print(f"\n✗ Step '{name}' FAILED: {exc}")
            print("  Fix the cause and re-run; completed steps are idempotent and")
            print("  their captured IDs persist in deploy_state.json.")
            sys.exit(1)


def _print_handoff() -> None:
    state = deploy_config.read_state()
    print(f"\n{'=' * 70}\n✓ Bootstrap complete. deploy_state.json:\n{'=' * 70}")
    print(json.dumps(state, indent=2))

    catalog = state.get("catalog", deploy_config.CATALOG)
    schema = state.get("schema", deploy_config.SCHEMA)
    genie = state.get("genie_space_id", deploy_config.genie_space_id())
    dash = state.get("dashboard_id", deploy_config.dashboard_id())
    idx = state.get("contract_index", deploy_config.contract_index())
    warehouse = state.get("warehouse_id", "")

    print(f"\n{'-' * 70}\napp.yaml env block to paste (the app reads these at runtime):\n{'-' * 70}")
    for name, value in [
        ("GENIE_SPACE_ID", genie),
        ("CONTRACT_INDEX", idx),
        ("DASHBOARD_ID", dash),
        ("COGS_CATALOG", catalog),
        ("COGS_SCHEMA", schema),
        ("WAREHOUSE_ID", warehouse),
    ]:
        print(f'  - name: {name}\n    value: "{value}"')

    print(f"\n{'-' * 70}\nFollow-up commands (not auto-run):\n{'-' * 70}")
    print("  # 1. register + serve the agent (needs mlflow/databricks-agents installed)")
    print("  python deploy_agent.py            # or re-run: python bootstrap.py --deploy-agent")
    print("  # 2. build the frontend, then sync + deploy the app")
    print("  cd frontend && npm install && npm run build && cd ..")
    print("  databricks sync . /Users/<you>/cogs-negotiation-agent --exclude node_modules --exclude .venv")
    print("  databricks apps deploy cogs-negotiation-agent \\")
    print("    --source-code-path /Workspace/Users/<you>/cogs-negotiation-agent")
    print("  # 3. attach app resources: LLM serving endpoint (CAN_QUERY) + Lakebase (CAN_CONNECT_AND_CREATE)")


def main() -> None:
    deploy_agent_flag = "--deploy-agent" in sys.argv[1:]
    print(f"Bootstrapping COGS Negotiation Agent into "
          f"{deploy_config.CATALOG}.{deploy_config.SCHEMA} (profile {deploy_config.PROFILE})")
    _run_steps()

    if deploy_agent_flag:
        print(f"\n{'=' * 70}\n▶ deploy_agent\n{'=' * 70}")
        try:
            import deploy_agent
            deploy_agent.main()
        except Exception as exc:  # noqa: BLE001
            print(f"\n✗ Step 'deploy_agent' FAILED: {exc}")
            sys.exit(1)

    _print_handoff()


if __name__ == "__main__":
    main()
