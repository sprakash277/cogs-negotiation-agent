"""Genie Conversation API client for the app.

The app calls this to answer Scorecard / KPI / free-form questions via NL->SQL
over the kroger_demo.cogs Genie space, instead of the synthetic data. Returns
the generated SQL, the result columns/rows, and Genie's narrative text.

Runs as the app service principal, which must have: CAN_RUN on the Genie space,
CAN_USE on the warehouse, and SELECT on kroger_demo.cogs.*.
"""

from __future__ import annotations

import os
from functools import lru_cache

from .config import get_workspace_client

GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "01f1642219cf135cb84f7e0dbc8d6957")


def genie_configured() -> bool:
    return bool(GENIE_SPACE_ID)


def _extract(client, msg) -> dict:
    """Pull text + SQL + tabular result out of a finished Genie message."""
    out = {"text": None, "sql": None, "columns": [], "rows": [], "conversation_id": msg.conversation_id}
    for att in (msg.attachments or []):
        if getattr(att, "text", None) and att.text.content:
            out["text"] = att.text.content
        if getattr(att, "query", None):
            out["sql"] = att.query.query
            try:
                res = client.genie.get_message_attachment_query_result(
                    space_id=GENIE_SPACE_ID,
                    conversation_id=msg.conversation_id,
                    message_id=msg.id,
                    attachment_id=att.attachment_id,
                )
                sr = res.statement_response
                if sr and sr.manifest and sr.manifest.schema and sr.manifest.schema.columns:
                    out["columns"] = [c.name for c in sr.manifest.schema.columns]
                if sr and sr.result and sr.result.data_array:
                    out["rows"] = sr.result.data_array
            except Exception as e:  # surface but don't crash the answer
                out["query_error"] = str(e)
    return out


def ask(question: str, conversation_id: str | None = None) -> dict:
    client = get_workspace_client()
    if conversation_id:
        msg = client.genie.create_message_and_wait(
            space_id=GENIE_SPACE_ID, conversation_id=conversation_id, content=question
        )
    else:
        msg = client.genie.start_conversation_and_wait(
            space_id=GENIE_SPACE_ID, content=question
        )
    return _extract(client, msg)


@lru_cache(maxsize=1)
def space_url() -> str:
    from .config import get_workspace_host

    return f"{get_workspace_host().rstrip('/')}/genie/rooms/{GENIE_SPACE_ID}"
