"""Dual-mode auth + environment detection.

Detects whether the app is running inside Databricks Apps (auto-injected SP
credentials) or locally (Databricks CLI profile), and exposes a single
``WorkspaceClient`` + OAuth token accessor used by the LLM factory and any
governed data access.
"""

from __future__ import annotations

import os
from functools import lru_cache

from databricks.sdk import WorkspaceClient

# When running inside Databricks Apps, the runtime sets DATABRICKS_APP_NAME.
IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

# When running inside Mosaic AI Model Serving (the agent deployed as a model),
# the runtime sets these. In that case the SDK auto-authenticates against the
# endpoint's automatic-auth credentials (scoped to declared resources).
IS_MODEL_SERVING = bool(
    os.environ.get("IS_IN_DB_MODEL_SERVING_ENV")
    or os.environ.get("DB_MODEL_SERVING_HOST_URL")
    or os.environ.get("MLFLOW_DEPLOYMENT_FLAVOR_NAME")
)


@lru_cache(maxsize=1)
def get_workspace_client() -> WorkspaceClient:
    if IS_DATABRICKS_APP or IS_MODEL_SERVING:
        # Remote runtimes: auto-injected credentials, no profile.
        return WorkspaceClient()
    # Local: named CLI profile if provided, else ambient env.
    profile = os.environ.get("DATABRICKS_PROFILE")
    return WorkspaceClient(profile=profile) if profile else WorkspaceClient()


def get_oauth_token() -> str:
    """Return a bearer token that works for the Gateway URL and workspace APIs."""
    client = get_workspace_client()
    headers = client.config.authenticate()  # {'Authorization': 'Bearer <token>'}
    if headers and "Authorization" in headers:
        return headers["Authorization"].replace("Bearer ", "")
    # Fallback for PAT-style configs.
    return client.config.token or ""


def get_workspace_host() -> str:
    """Workspace host URL, always with an https:// scheme."""
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host
    return get_workspace_client().config.host
