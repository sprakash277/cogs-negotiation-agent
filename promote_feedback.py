"""Promote human feedback into evaluation cases (closes the human loop).

Reads the Lakebase `feedback` table, takes the thumbs-DOWN items (the ones worth
learning from), joins each to its saved artifact (brief/deck) for context, and
emits suggested eval cases you can fold into eval_agent.py's DATA. Thumbs-up
items are summarized as a quality signal.

Run (VPN on): DATABRICKS_CONFIG_PROFILE=cogs-demo .venv/bin/python promote_feedback.py
"""

from __future__ import annotations

import json
import os

import psycopg
from databricks.sdk import WorkspaceClient

INSTANCE = "cogs-lakebase"
HOST = "ep-blue-pine-e121z0sk.database.eastus2.azuredatabricks.net"
USER = os.environ.get("PGUSER", "sumit.prakash@databricks.com")

w = WorkspaceClient(profile=os.environ.get("DATABRICKS_PROFILE", "cogs-demo"))


def connect():
    cred = w.database.generate_database_credential(instance_names=[INSTANCE], request_id=os.urandom(8).hex())
    return psycopg.connect(host=HOST, user=USER, dbname="databricks_postgres",
                           sslmode="require", password=cred.token)


def main():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FILTER (WHERE rating='up'), count(*) FILTER (WHERE rating='down') FROM feedback")
        up, down = cur.fetchone()
        print(f"Feedback so far:  👍 {up}   👎 {down}")

        # Pull thumbs-down with the artifact's objective/supplier for context.
        cur.execute(
            """SELECT f.kind, f.rating, f.comment, f.supplier_key, a.payload
               FROM feedback f
               LEFT JOIN agent_artifacts a ON a.id = f.artifact_id
               WHERE f.rating = 'down'
               ORDER BY f.created_at DESC"""
        )
        rows = cur.fetchall()

    eval_cases = []
    for kind, rating, comment, supplier_key, payload in rows:
        task = {"briefs": "brief", "decks": "deck"}.get(kind, "chat")
        objective = (payload or {}).get("objective") if isinstance(payload, dict) else None
        case = {
            "inputs": {
                "question": objective or comment or "regenerate",
                "task": task,
                "supplier_key": supplier_key,
            },
            # The human's correction becomes the expectation to test against.
            "expectations": {"expected_facts": [comment]} if comment else {},
            "_source": "human_feedback_downvote",
        }
        eval_cases.append(case)

    out = "/tmp/feedback_eval_cases.json"
    with open(out, "w") as fh:
        json.dump(eval_cases, fh, indent=2)
    print(f"\nPromoted {len(eval_cases)} downvote(s) into eval cases -> {out}")
    if eval_cases:
        print("Fold these into eval_agent.py DATA, then re-run eval to measure the fix:")
        print(json.dumps(eval_cases[:3], indent=2))
    else:
        print("No downvotes yet — nothing to promote.")


if __name__ == "__main__":
    main()
