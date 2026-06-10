"""Knowledge Assistant data foundation: contract docs -> Volume + Vector Search.

1. Creates a UC Volume <catalog>.<schema>.contracts and writes a supplier
   agreement (MSA) document per supplier.
2. Chunks each agreement (clause-level) into a Delta table contract_chunks
   (CDF enabled) — the source for the vector index.
3. Creates the Vector Search endpoint if it doesn't exist, then a Delta Sync
   Vector Search index with managed embeddings (databricks-gte-large-en) on it.

Catalog/schema/endpoint/embedding model are resolved from deploy_config so the
knowledge base is portable to any workspace.

Run (VPN on): DATABRICKS_CONFIG_PROFILE=cogs-demo .venv/bin/python build_knowledge.py
"""

from __future__ import annotations

import io

from databricks.sdk.service.sql import StatementState

from deploy_config import (
    CATALOG as CAT,
    SCHEMA as SCH,
    EMBED_ENDPOINT as EMBED_MODEL,
    VS_ENDPOINT,
    get_workspace_client,
    resolve_warehouse_id,
    write_state,
)
from server.data import SUPPLIERS

VOLUME = f"{CAT}.{SCH}.contracts"
CHUNKS = f"{CAT}.{SCH}.contract_chunks"
INDEX = f"{CAT}.{SCH}.contract_chunks_index"

w = get_workspace_client()
# Resolved lazily in main(); placeholder so module import never makes a live call.
WAREHOUSE = ""


def run(sql: str, label: str):
    r = w.statement_execution.execute_statement(statement=sql, warehouse_id=WAREHOUSE, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"{label} FAILED: {r.status.error.message if r.status.error else r.status.state}")
    print(f"  • {label} … ok")
    return r


def contract_sections(s: dict) -> list[tuple[str, str]]:
    """Return (section_title, clause_text) pairs for one supplier's MSA."""
    name = s["supplier"]
    return [
        ("Pricing & Cost of Goods",
         f"Section 3 — Pricing. The base unit cost of goods (COGS) for {name} products supplied to Kroger "
         f"is set at ${s['cogs_per_unit']:.2f} per unit as of the current term, landed to Kroger distribution "
         f"centers. Pricing is indexed to a category baseline; {name}'s current landed-cost index is "
         f"{s['landed_cost_index']} (category baseline = 100). List-price changes require ninety (90) days' "
         f"written notice and are capped at the lesser of CPI-beverage or six percent (6%) per contract year."),
        ("Annual COGS Adjustment Mechanism",
         f"Section 4 — Cost Adjustments. Year-over-year COGS adjustments for {name} reflect verified input-cost "
         f"movement (aluminum, PET resin, sweetener, freight). The current year reflects a {s['yoy_cogs_change_pct']:+.1f}% "
         f"adjustment. Kroger reserves the right to audit cost build-ups and to reject pass-through of costs not "
         f"substantiated by third-party indices. Any adjustment above five percent (5%) triggers a joint cost-review."),
        ("Rebates & Growth Incentives",
         f"Section 6 — Rebates. {name} qualifies for {s['rebate_tier']} rebate treatment based on annual purchase "
         f"volume of approximately ${s['annual_spend']/1e9:.2f}B. Rebates are earned on incremental volume above the "
         f"prior-year baseline and are paid quarterly. Tier thresholds are recalculated annually; falling below a tier "
         f"floor reduces the rebate rate prospectively."),
        ("Trade Funds & Promotional Support",
         f"Section 7 — Trade & Marketing Funds. {name} commits trade and promotional funding equal to "
         f"{s['trade_funds_pct']:.1f}% of net purchases, allocated between scan-down, off-invoice, and shopper-marketing "
         f"programs. Unspent committed funds at year end roll over for one quarter only. Kroger may direct up to forty "
         f"percent (40%) of trade funds to scan-down at its discretion."),
        ("Service Levels & Supply Reliability",
         f"Section 9 — Service Levels. {name} shall maintain a case fill rate of at least 98.0% and on-time-in-full "
         f"(OTIF) of at least 95.0%. Current trailing performance is fill rate {s['fill_rate_pct']:.1f}% and OTIF "
         f"{s['otif_pct']:.1f}%. Sustained OTIF below the threshold for two consecutive quarters entitles Kroger to "
         f"service-level credits of 1.5% of affected purchases and to re-source volume without penalty."),
        ("Term, Renewal & Termination",
         f"Section 12 — Term. This agreement runs through {s['contract_expiry']}. Renewal is by mutual written "
         f"agreement; absent renewal terms ninety (90) days prior to expiry, pricing reverts to list. Either party may "
         f"terminate for uncured material breach on sixty (60) days' notice. Kroger may terminate for convenience on "
         f"one hundred eighty (180) days' notice."),
    ]


def upload_docs_and_chunks():
    run(f"CREATE VOLUME IF NOT EXISTS {VOLUME} COMMENT 'Supplier MSAs / contracts for the COGS negotiation agent'", "create volume")
    run(
        f"""CREATE OR REPLACE TABLE {CHUNKS} (
            id STRING, supplier_key STRING, supplier STRING, section STRING, content STRING
        ) TBLPROPERTIES (delta.enableChangeDataFeed = true)
        COMMENT 'Clause-level chunks of supplier MSAs, source for the contract vector index'""",
        "create contract_chunks",
    )

    values = []
    for s in SUPPLIERS:
        secs = contract_sections(s)
        # Full doc to the Volume
        doc = f"# MASTER SUPPLY AGREEMENT — {s['supplier']} ⇄ The Kroger Co.\n\n"
        doc += f"Category: {s['category']}\n\n"
        for title, text in secs:
            doc += f"## {title}\n\n{text}\n\n"
        path = f"/Volumes/{CAT}/{SCH}/contracts/{s['key']}_msa.md"
        w.files.upload(path, io.BytesIO(doc.encode("utf-8")), overwrite=True)
        print(f"  • uploaded {path}")
        # One chunk per section
        for i, (title, text) in enumerate(secs):
            cid = f"{s['key']}-{i}"
            esc = text.replace("'", "''")
            tt = title.replace("'", "''")
            values.append(f"('{cid}', '{s['key']}', '{s['supplier'].replace(chr(39), chr(39)*2)}', '{tt}', '{esc}')")
    run(f"INSERT INTO {CHUNKS} VALUES\n" + ",\n".join(values), f"load {len(values)} chunks")


def ensure_endpoint():
    """Create the Vector Search endpoint if it isn't already present."""
    from databricks.sdk.service.vectorsearch import EndpointType

    names = [e.name for e in w.vector_search_endpoints.list_endpoints()]
    if VS_ENDPOINT in names:
        print(f"  • vector search endpoint {VS_ENDPOINT} already exists")
        return
    print(f"  • creating vector search endpoint {VS_ENDPOINT} (waiting for PROVISIONED) …")
    w.vector_search_endpoints.create_endpoint_and_wait(
        name=VS_ENDPOINT, endpoint_type=EndpointType.STANDARD
    )
    print("  • endpoint ready")


def create_index():
    existing = [ix.name for ix in w.vector_search_indexes.list_indexes(endpoint_name=VS_ENDPOINT)]
    if INDEX in existing:
        print(f"  • index {INDEX} already exists — syncing")
        w.vector_search_indexes.sync_index(index_name=INDEX)
        return
    from databricks.sdk.service.vectorsearch import (
        DeltaSyncVectorIndexSpecRequest, EmbeddingSourceColumn,
        PipelineType, VectorIndexType,
    )
    print(f"  • creating Delta Sync index {INDEX} on {VS_ENDPOINT} …")
    w.vector_search_indexes.create_index(
        name=INDEX,
        endpoint_name=VS_ENDPOINT,
        primary_key="id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=CHUNKS,
            pipeline_type=PipelineType.TRIGGERED,
            embedding_source_columns=[
                EmbeddingSourceColumn(name="content", embedding_model_endpoint_name=EMBED_MODEL)
            ],
        ),
    )
    print("  • index creation submitted")


def main():
    global WAREHOUSE
    WAREHOUSE = resolve_warehouse_id(w)
    print(f"Building knowledge base in {CAT}.{SCH}")
    upload_docs_and_chunks()
    ensure_endpoint()
    create_index()
    write_state(contract_index=INDEX, vs_endpoint=VS_ENDPOINT)
    print("\nSubmitted. The index will take a few minutes to come ONLINE + sync.")
    print(f"  Volume:  /Volumes/{CAT}/{SCH}/contracts/")
    print(f"  Chunks:  {CHUNKS}")
    print(f"  Index:   {INDEX}  (endpoint {VS_ENDPOINT})")


if __name__ == "__main__":
    main()
