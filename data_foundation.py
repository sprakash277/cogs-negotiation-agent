"""Build the Layer-3 data foundation in Unity Catalog.

Materializes the synthetic COGS data (server/data.py — the single source of truth)
as real Delta tables in kroger_demo.cogs, plus a certified Metric View for landed
cost / COGS. This is what Genie will sit on top of, replacing the in-app synthetic
data for the Scorecard and deck KPIs.

Run (VPN on): DATABRICKS_CONFIG_PROFILE=cogs-demo .venv/bin/python data_foundation.py
"""

from __future__ import annotations

import os

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from server.data import REGIONS, SUPPLIERS

PROFILE = os.environ.get("DATABRICKS_PROFILE", "cogs-demo")
WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "a455a68035c1f578")  # Serverless Starter
CATALOG = "kroger_demo"
SCHEMA = "cogs"

w = WorkspaceClient(profile=PROFILE)


def run(sql: str, label: str) -> None:
    print(f"  • {label} …", end=" ", flush=True)
    resp = w.statement_execution.execute_statement(
        statement=sql, warehouse_id=WAREHOUSE_ID, wait_timeout="50s"
    )
    state = resp.status.state
    # Poll if it didn't finish within the wait window.
    while state in (StatementState.PENDING, StatementState.RUNNING):
        resp = w.statement_execution.get_statement(resp.statement_id)
        state = resp.status.state
    if state != StatementState.SUCCEEDED:
        msg = resp.status.error.message if resp.status.error else state
        raise RuntimeError(f"{label} FAILED: {msg}")
    print("ok")


def sql_str(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return str(v)


def build_supplier_table() -> None:
    run(
        f"""CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.supplier_scorecard (
            supplier STRING, supplier_key STRING, category STRING,
            annual_spend BIGINT, cogs_per_unit DOUBLE, unit_volume BIGINT,
            landed_cost_index DOUBLE, yoy_cogs_change_pct DOUBLE, yoy_volume_change_pct DOUBLE,
            trade_funds_pct DOUBLE, fill_rate_pct DOUBLE, otif_pct DOUBLE,
            contract_expiry DATE, rebate_tier STRING, open_negotiation BOOLEAN
        ) COMMENT 'Trailing-52-week supplier COGS scorecard for the Kroger beverage category'""",
        "create supplier_scorecard",
    )
    cols = ("supplier", "key", "category", "annual_spend", "cogs_per_unit", "unit_volume",
            "landed_cost_index", "yoy_cogs_change_pct", "yoy_volume_change_pct",
            "trade_funds_pct", "fill_rate_pct", "otif_pct", "contract_expiry",
            "rebate_tier", "open_negotiation")
    rows = []
    for s in SUPPLIERS:
        vals = []
        for c in cols:
            v = s[c]
            if c == "contract_expiry":
                vals.append(f"DATE'{v}'")
            else:
                vals.append(sql_str(v))
        rows.append("(" + ", ".join(vals) + ")")
    run(
        f"INSERT INTO {CATALOG}.{SCHEMA}.supplier_scorecard VALUES\n" + ",\n".join(rows),
        "load supplier rows",
    )


def build_region_table() -> None:
    run(
        f"""CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.regional_performance (
            region STRING, dollar_sales BIGINT, yoy_pct DOUBLE, unit_sales BIGINT, stores INT
        ) COMMENT 'Beverage category regional performance, trailing 52 weeks'""",
        "create regional_performance",
    )
    rows = [
        f"({sql_str(r['region'])}, {r['dollar_sales']}, {r['yoy_pct']}, {r['unit_sales']}, {r['stores']})"
        for r in REGIONS
    ]
    run(
        f"INSERT INTO {CATALOG}.{SCHEMA}.regional_performance VALUES\n" + ",\n".join(rows),
        "load region rows",
    )


def build_metric_view() -> None:
    yaml_spec = f"""version: 0.1
source: {CATALOG}.{SCHEMA}.supplier_scorecard
dimensions:
  - name: Supplier
    expr: supplier
  - name: Category
    expr: category
  - name: Rebate Tier
    expr: rebate_tier
measures:
  - name: Total Spend
    expr: SUM(annual_spend)
  - name: Total Units
    expr: SUM(unit_volume)
  - name: Avg COGS per Unit
    expr: SUM(cogs_per_unit * unit_volume) / SUM(unit_volume)
  - name: Blended Landed Cost Index
    expr: SUM(landed_cost_index * annual_spend) / SUM(annual_spend)
  - name: Blended COGS Inflation Pct
    expr: SUM(yoy_cogs_change_pct * annual_spend) / SUM(annual_spend)
  - name: Avg Fill Rate
    expr: AVG(fill_rate_pct)
  - name: Avg OTIF
    expr: AVG(otif_pct)
"""
    run(
        f"""CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.landed_cost_metrics
        WITH METRICS
        LANGUAGE YAML
        COMMENT 'Certified COGS / landed-cost metrics for negotiation analytics'
        AS $${yaml_spec}$$""",
        "create metric view landed_cost_metrics",
    )


def main() -> None:
    print(f"Building data foundation in {CATALOG}.{SCHEMA} (warehouse {WAREHOUSE_ID})")
    run(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA} COMMENT 'COGS negotiation agent data'", "create schema")
    build_supplier_table()
    build_region_table()
    build_metric_view()
    print("\nDone. Tables + metric view ready:")
    print(f"  {CATALOG}.{SCHEMA}.supplier_scorecard")
    print(f"  {CATALOG}.{SCHEMA}.regional_performance")
    print(f"  {CATALOG}.{SCHEMA}.landed_cost_metrics  (metric view)")


if __name__ == "__main__":
    main()
