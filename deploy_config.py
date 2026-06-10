"""Shared deploy-time configuration + state for the COGS Negotiation Agent.

This is the single source of truth for the workspace/catalog/asset knobs used by
the one-time builder scripts (``data_foundation.py``, ``build_market_data.py``,
``build_genie.py``, ``build_knowledge.py``, ``build_dashboard.py``) and the
``deploy_agent.py`` registration/serving step. It lets the whole demo be
recreated in ANY fresh Databricks workspace from one ``bootstrap.py`` run.

Every knob is env-driven with the CURRENT cogs-demo values as defaults, so a
plain ``python <script>.py`` against cogs-demo behaves exactly as before. The
read order for resolved IDs is: ``deploy_state.json`` > env var > hardcoded
cogs-demo default.

This module is DEPLOY-ONLY tooling — it is intentionally NOT imported by the
``server/`` app package (which stays free of deploy deps and reads the same env
var names directly). Dependency-light on purpose: os, json, functools + the SDK.
"""

from __future__ import annotations

import functools
import json
import os

from databricks.sdk import WorkspaceClient

# --------------------------------------------------------------------------- #
# Env-driven knobs (defaults == current cogs-demo behavior).
# --------------------------------------------------------------------------- #
PROFILE = os.environ.get("DATABRICKS_PROFILE", "cogs-demo")
CATALOG = os.environ.get("COGS_CATALOG", "kroger_demo")
SCHEMA = os.environ.get("COGS_SCHEMA", "cogs")
WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "")  # "" => auto-pick a warehouse
VS_ENDPOINT = os.environ.get("VS_ENDPOINT", "kroger-recipe-search")
LLM_ENDPOINT = os.environ.get("LLM_MODEL", "databricks-claude-sonnet-4-5")
EMBED_ENDPOINT = os.environ.get("EMBED_MODEL", "databricks-gte-large-en")
# "" => resolve to the current user's /Users/<me> via w.current_user.me().
PARENT_PATH = os.environ.get("BOOTSTRAP_PARENT_PATH", "")

# --------------------------------------------------------------------------- #
# Derived identifiers.
# --------------------------------------------------------------------------- #
FQ = f"{CATALOG}.{SCHEMA}"
CONTRACT_INDEX = f"{CATALOG}.{SCHEMA}.contract_chunks_index"
UC_MODEL = f"{CATALOG}.models.cogs_negotiation_agent"

# --------------------------------------------------------------------------- #
# Hardcoded cogs-demo fallbacks. These keep existing scripts targeting the
# current cogs-demo assets when run there WITHOUT a seeded deploy_state.json
# (which is workspace-specific and never committed).
# --------------------------------------------------------------------------- #
_COGS_DEMO_GENIE_SPACE_ID = "01f1642219cf135cb84f7e0dbc8d6957"
_COGS_DEMO_DASHBOARD_ID = "01f1643845191b049c9a3acf7531495b"
_COGS_DEMO_WAREHOUSE_ID = "a455a68035c1f578"  # Serverless Starter

STATE_PATH = os.path.join(os.path.dirname(__file__), "deploy_state.json")


@functools.lru_cache(maxsize=1)
def get_workspace_client() -> WorkspaceClient:
    """Return a profile-scoped WorkspaceClient for deploy-time tooling."""
    return WorkspaceClient(profile=PROFILE)


# --------------------------------------------------------------------------- #
# State file helpers (deploy_state.json carries created IDs between steps).
# --------------------------------------------------------------------------- #
def read_state() -> dict:
    """Return the deploy_state.json contents (empty dict if absent/invalid)."""
    try:
        with open(STATE_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(**kwargs) -> dict:
    """Merge ``kwargs`` into deploy_state.json and persist. Returns merged state.

    None values are ignored so callers can pass optional fields freely.
    """
    state = read_state()
    state.update({k: v for k, v in kwargs.items() if v is not None})
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
    return state


def get_state(key: str, default=None):
    """Read a single key from deploy_state.json."""
    return read_state().get(key, default)


# --------------------------------------------------------------------------- #
# Warehouse resolution: state > env > auto-pick a live serverless warehouse.
# --------------------------------------------------------------------------- #
def resolve_warehouse_id(w: WorkspaceClient) -> str:
    """Return the SQL warehouse id to use, auto-picking + caching if needed.

    Resolution order:
      1. deploy_state.json["warehouse_id"] (a prior run cached one)
      2. WAREHOUSE_ID env var
      3. the cogs-demo default (so cogs-demo keeps working with no state)
      4. auto-pick the first available warehouse (prefer serverless / RUNNING)

    The resolved id is cached back into state so later steps reuse it.
    """
    cached = get_state("warehouse_id")
    if cached:
        return cached
    if WAREHOUSE_ID:
        write_state(warehouse_id=WAREHOUSE_ID)
        return WAREHOUSE_ID

    # If we're still pointed at cogs-demo defaults, prefer the known warehouse.
    if PROFILE == "cogs-demo" and CATALOG == "kroger_demo":
        write_state(warehouse_id=_COGS_DEMO_WAREHOUSE_ID)
        return _COGS_DEMO_WAREHOUSE_ID

    warehouses = list(w.warehouses.list())
    if not warehouses:
        raise RuntimeError(
            "No SQL warehouse found in this workspace. Create a (serverless) SQL "
            "warehouse or set WAREHOUSE_ID, then re-run."
        )

    def _score(wh) -> tuple:
        state = getattr(wh, "state", None)
        running = 1 if (state and str(state).upper().endswith("RUNNING")) else 0
        wtype = getattr(wh, "warehouse_type", None) or getattr(wh, "enable_serverless_compute", None)
        serverless = 1 if (getattr(wh, "enable_serverless_compute", False)) else 0
        return (running, serverless)

    best = sorted(warehouses, key=_score, reverse=True)[0]
    resolved = best.id
    print(f"  • auto-picked SQL warehouse '{getattr(best, 'name', resolved)}' ({resolved})")
    write_state(warehouse_id=resolved)
    return resolved


def resolve_parent_path(w: WorkspaceClient) -> str:
    """Return the Genie/dashboard parent path, defaulting to the current user's home."""
    if PARENT_PATH:
        return PARENT_PATH
    me = w.current_user.me()
    return f"/Users/{me.user_name}"


# --------------------------------------------------------------------------- #
# Resolved-ID accessors (state > hardcoded cogs-demo default).
# --------------------------------------------------------------------------- #
def genie_space_id() -> str:
    """Resolved Genie space id (state, else cogs-demo default)."""
    return get_state("genie_space_id", _COGS_DEMO_GENIE_SPACE_ID)


def dashboard_id() -> str:
    """Resolved Lakeview dashboard id (state, else cogs-demo default)."""
    return get_state("dashboard_id", _COGS_DEMO_DASHBOARD_ID)


def contract_index() -> str:
    """Resolved contract vector index FQN (state, else derived default)."""
    return get_state("contract_index", CONTRACT_INDEX)


def vs_endpoint() -> str:
    """Resolved Vector Search endpoint name (state, else config default)."""
    return get_state("vs_endpoint", VS_ENDPOINT)
