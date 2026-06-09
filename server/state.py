"""Operational state — Lakebase (Postgres OLTP) with an in-memory fallback.

When a Lakebase database resource is attached to the app, the runtime injects
PGHOST/PGUSER/PGDATABASE/PGPORT and we set ENDPOINT_NAME; this module then
persists saved briefs, decks, rehearsals, and the negotiation work queue to
Postgres. Tokens are minted fresh per connection via the OAuthConnection
pattern (no background refresh). If Lakebase isn't configured, it transparently
falls back to a process-local in-memory store so the app still runs.
"""

from __future__ import annotations

import json
import os
import threading
import uuid

LAKEBASE_INSTANCE = os.environ.get("LAKEBASE_INSTANCE", "")
USE_LAKEBASE = bool(os.environ.get("PGHOST") and LAKEBASE_INSTANCE)

_KINDS = ("briefs", "decks", "rehearsals", "queue")

# --------------------------------------------------------------------------- #
# In-memory fallback
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
_store: dict[str, dict] = {k: {} for k in _KINDS}


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def backend_name() -> str:
    return "lakebase" if USE_LAKEBASE else "in-memory"


# --------------------------------------------------------------------------- #
# Lakebase pool (built lazily on first use / app startup)
# --------------------------------------------------------------------------- #
_pool = None


def _build_pool():
    import psycopg
    from databricks.sdk import WorkspaceClient
    from psycopg_pool import ConnectionPool

    w = WorkspaceClient()
    instance = LAKEBASE_INSTANCE

    class OAuthConnection(psycopg.Connection):
        @classmethod
        def connect(cls, conninfo="", **kwargs):
            import uuid as _uuid

            cred = w.database.generate_database_credential(
                instance_names=[instance], request_id=_uuid.uuid4().hex
            )
            kwargs["password"] = cred.token
            return super().connect(conninfo, **kwargs)

    user = os.environ["PGUSER"]
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    db = os.environ.get("PGDATABASE", "databricks_postgres")
    sslmode = os.environ.get("PGSSLMODE", "require")
    return ConnectionPool(
        conninfo=f"dbname={db} user={user} host={host} port={port} sslmode={sslmode}",
        connection_class=OAuthConnection,
        min_size=1, max_size=10, max_lifetime=2700, open=False,
    )


def init() -> None:
    """Open the pool and ensure the schema. Call from the app startup hook."""
    global _pool
    if not USE_LAKEBASE:
        return
    _pool = _build_pool()
    _pool.open(wait=True, timeout=30.0)
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS agent_artifacts (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    supplier_key TEXT,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )"""
            )
        conn.commit()


def shutdown() -> None:
    if _pool is not None:
        _pool.close()


# --------------------------------------------------------------------------- #
# CRUD (route through these; backend chosen automatically)
# --------------------------------------------------------------------------- #
def save_artifact(kind: str, payload: dict) -> str:
    aid = _new_id()
    record = {"id": aid, **payload}
    if USE_LAKEBASE and _pool is not None:
        with _pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_artifacts (id, kind, supplier_key, payload) VALUES (%s, %s, %s, %s)",
                    (aid, kind, payload.get("supplier_key"), json.dumps(record)),
                )
            conn.commit()
        return aid
    with _lock:
        _store[kind][aid] = record
    return aid


def get_artifact(kind: str, aid: str) -> dict | None:
    if USE_LAKEBASE and _pool is not None:
        with _pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM agent_artifacts WHERE id = %s AND kind = %s", (aid, kind))
                row = cur.fetchone()
        return row[0] if row else None
    with _lock:
        return _store[kind].get(aid)


def list_artifacts(kind: str) -> list[dict]:
    if USE_LAKEBASE and _pool is not None:
        with _pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT payload FROM agent_artifacts WHERE kind = %s ORDER BY created_at DESC LIMIT 200",
                    (kind,),
                )
                rows = cur.fetchall()
        return [r[0] for r in rows]
    with _lock:
        return list(_store[kind].values())
