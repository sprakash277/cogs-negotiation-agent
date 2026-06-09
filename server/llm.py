"""
Pluggable LLM factory for the COGS Negotiation Agent.

The whole point of this module: every agent / chain in the app calls
``get_llm()`` and receives a LangChain ``BaseChatModel``. NONE of them know or
care which provider is live. Switching providers is a single env var
(``LLM_PROVIDER``) — no code change, no redeploy of agent logic.

Two providers are supported today:

  mosaic   (default) -> Databricks Mosaic AI Gateway
                        Routes through the workspace's dedicated AI Gateway URL
                        (https://<ws-id>.ai-gateway.cloud.databricks.com/mlflow/v1)
                        so guardrails / rate limits / usage counters /
                        inference tables all register. This is the governed path.

  litellm            -> A LiteLLM proxy (OpenAI-compatible).
                        By default LiteLLM is expected to route UPSTREAM through
                        the same Mosaic Gateway (LITELLM_ROUTES_VIA_MOSAIC=true),
                        keeping ONE governance/observability boundary. Flip it to
                        let LiteLLM go direct to external providers (two
                        boundaries — see the governance note in the README).

Both providers are OpenAI wire-compatible, so both are constructed as
``ChatOpenAI`` pointed at a different ``base_url`` + ``api_key`` + ``model``.
That uniformity is what makes the switch a one-liner.

A third native option (``databricks`` -> ``ChatDatabricks``) is included behind
a flag for teams that want the native integration instead of the Gateway URL;
note it does NOT traverse the AI Gateway subdomain, so Gateway UI counters stay
empty. Prefer ``mosaic`` for the governed path.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


# --------------------------------------------------------------------------- #
# Provider resolution
# --------------------------------------------------------------------------- #

def _provider() -> str:
    return os.environ.get("LLM_PROVIDER", "mosaic").strip().lower()


def _default_model() -> str:
    # A single knob for the default model name. Each provider maps it to the
    # right served-model identifier below.
    return os.environ.get("LLM_MODEL", "databricks-claude-sonnet-4-5")


def _mosaic_gateway_url() -> str:
    """OpenAI-compatible base URL for the governed Databricks path.

    Preference order:
      1. AI_GATEWAY_URL if set — use it verbatim. On workspaces that expose the
         dedicated AI Gateway subdomain (mostly AWS today) this is
         https://<ws-id>.ai-gateway.cloud.databricks.com/mlflow/v1.
      2. Otherwise fall back to the workspace serving-endpoints route
         (https://<workspace-host>/serving-endpoints). This is the correct
         OpenAI-compatible path on Azure, records in system.serving.endpoint_usage,
         and honors AI-Gateway config attached to the endpoint (guardrails, rate
         limits, inference tables).
    """
    url = os.environ.get("AI_GATEWAY_URL", "").strip()
    if url:
        return url.rstrip("/")
    from .config import get_workspace_host

    host = get_workspace_host().rstrip("/")
    if not host:
        raise RuntimeError(
            "Cannot resolve the LLM base URL: AI_GATEWAY_URL is unset and the "
            "workspace host could not be determined. Set AI_GATEWAY_URL or ensure "
            "DATABRICKS_HOST / a CLI profile is configured."
        )
    return f"{host}/serving-endpoints"


def _databricks_token() -> str:
    """OAuth token for Databricks. Works for the App SP remotely and the CLI locally."""
    # Imported lazily so the module loads even if the SDK isn't configured yet.
    from .config import get_oauth_token, IS_DATABRICKS_APP

    if IS_DATABRICKS_APP:
        return os.environ.get("DATABRICKS_TOKEN") or get_oauth_token()
    return get_oauth_token()


# --------------------------------------------------------------------------- #
# The factory
# --------------------------------------------------------------------------- #

def get_llm(provider: str | None = None, **overrides: Any) -> BaseChatModel:
    """Return a LangChain chat model for the active (or requested) provider.

    Args:
        provider: Override the env-configured provider for this one call
                  (e.g. run the rehearsal agent on litellm while everything
                  else stays on mosaic). Defaults to ``LLM_PROVIDER`` / "mosaic".
        **overrides: Per-call model kwargs (temperature, max_tokens, model, ...).

    Returns:
        A ``BaseChatModel`` — every downstream chain treats it identically.
    """
    provider = (provider or _provider()).lower()
    temperature = overrides.pop("temperature", 0.2)
    max_tokens = overrides.pop("max_tokens", 4096)
    model = overrides.pop("model", _default_model())

    if provider == "mosaic":
        return _build_mosaic(model, temperature, max_tokens, **overrides)
    if provider == "litellm":
        return _build_litellm(model, temperature, max_tokens, **overrides)
    if provider == "databricks":
        return _build_databricks_native(model, temperature, max_tokens, **overrides)

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. Expected one of: mosaic, litellm, databricks."
    )


def _build_mosaic(model: str, temperature: float, max_tokens: int, **kw: Any) -> BaseChatModel:
    """Mosaic AI Gateway via the governed Gateway URL (OpenAI-compatible)."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=_mosaic_gateway_url(),
        api_key=_databricks_token(),
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kw,
    )


def _build_litellm(model: str, temperature: float, max_tokens: int, **kw: Any) -> BaseChatModel:
    """LiteLLM proxy (OpenAI-compatible). Same client class, different base_url."""
    from langchain_openai import ChatOpenAI

    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError(
            "LITELLM_BASE_URL is not set. Point it at your LiteLLM proxy, e.g. "
            "http://litellm:4000 (or http://localhost:4000 for local dev)."
        )

    # When LiteLLM routes upstream through Mosaic, the model name it expects is
    # whatever you registered in the proxy's config (LITELLM_MODEL). When it
    # goes direct, that's a provider model string like 'claude-sonnet-4'.
    litellm_model = os.environ.get("LITELLM_MODEL", model)
    api_key = os.environ.get("LITELLM_API_KEY", "not-needed")

    return ChatOpenAI(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=litellm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kw,
    )


def _build_databricks_native(model: str, temperature: float, max_tokens: int, **kw: Any) -> BaseChatModel:
    """Native ChatDatabricks integration.

    NOTE: this calls the serving endpoint directly, NOT the AI Gateway subdomain,
    so Gateway UI counters / inference tables do not register. Use 'mosaic' for
    the governed path; this exists for teams that prefer the native class.
    """
    from databricks_langchain import ChatDatabricks

    return ChatDatabricks(
        endpoint=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kw,
    )


# --------------------------------------------------------------------------- #
# Introspection helper (surfaced on /api/health so the UI can show the mode)
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def llm_status() -> dict:
    provider = _provider()
    status = {
        "provider": provider,
        "model": _default_model(),
    }
    if provider == "mosaic":
        try:
            status["gateway_url"] = _mosaic_gateway_url()
        except Exception:
            status["gateway_url"] = os.environ.get("AI_GATEWAY_URL", "(unset)")
        status["governed"] = True
    elif provider == "litellm":
        via_mosaic = os.environ.get("LITELLM_ROUTES_VIA_MOSAIC", "true").lower() == "true"
        status["litellm_base_url"] = os.environ.get("LITELLM_BASE_URL", "(unset)")
        status["routes_via_mosaic"] = via_mosaic
        status["governed"] = via_mosaic
    return status
