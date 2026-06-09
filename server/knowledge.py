"""Knowledge Assistant — retrieval over the contract vector index.

Queries the kroger_demo.cogs.contract_chunks_index (managed-embeddings Delta
Sync index) to pull the most relevant contract clauses for a supplier, which
the Negotiation Brief agent then grounds its talking points in.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

from .config import get_workspace_client

CONTRACT_INDEX = os.environ.get("CONTRACT_INDEX", "kroger_demo.cogs.contract_chunks_index")


def knowledge_configured() -> bool:
    return bool(CONTRACT_INDEX)


def retrieve(query: str, supplier_key: str | None = None, k: int = 4) -> list[dict]:
    """Return top-k contract clauses [{supplier, section, content, score}]."""
    client = get_workspace_client()
    filters = json.dumps({"supplier_key": supplier_key}) if supplier_key else None
    res = client.vector_search_indexes.query_index(
        index_name=CONTRACT_INDEX,
        columns=["supplier", "section", "content"],
        query_text=query,
        num_results=k,
        filters_json=filters,
    )
    out: list[dict] = []
    if res.result and res.result.data_array:
        cols = [c.name for c in res.manifest.columns] if res.manifest and res.manifest.columns else []
        for row in res.result.data_array:
            out.append(dict(zip(cols, row)))
    return out


def context_block(clauses: list[dict]) -> str:
    """Format retrieved clauses for prompt injection, with citable section names."""
    if not clauses:
        return "(no contract clauses retrieved)"
    parts = []
    for c in clauses:
        section = c.get("section", "Clause")
        content = c.get("content", "")
        parts.append(f"[{section}]\n{content}")
    return "\n\n".join(parts)


@lru_cache(maxsize=1)
def index_status() -> dict:
    return {"index": CONTRACT_INDEX, "configured": knowledge_configured()}
