"""Build the market-context + cost-breakdown data foundation in Unity Catalog.

Materializes four synthetic-but-realistic Delta tables in ``kroger_demo.cogs``
that ground the FIXED 15-slide negotiation deck (acts 2-4): commodity / input
cost trends, competitive shelf-price benchmarks, macroeconomic indicators, and
SKU-level cost waterfalls (with prior-year + proposed landed cost for the YoY
bridge and scenario modeling). Mirrors data_foundation.py's connection +
statement-execution pattern so the swap to live Genie/SQL is mechanical.

All data is SYNTHETIC and beverage-category specific for pepsi / coke / kdp.
Generation is DETERMINISTIC (seeded) so it is reproducible run-to-run, and the
script is idempotent (CREATE OR REPLACE TABLE).

Run (VPN on): DATABRICKS_CONFIG_PROFILE=cogs-demo .venv/bin/python build_market_data.py
  (or:        DATABRICKS_PROFILE=cogs-demo .venv/bin/python build_market_data.py)

DO NOT confuse with data_foundation.py — that builds the supplier_scorecard /
regional_performance / landed_cost_metrics core. Run data_foundation.py first;
this script adds the market + cost-breakdown tables on top of the same schema.
"""

from __future__ import annotations

import random
from datetime import date

from databricks.sdk.service.sql import StatementState

from deploy_config import CATALOG, SCHEMA, get_workspace_client, resolve_warehouse_id, write_state

SEED = 8451  # deterministic generation — reproducible across runs

w = get_workspace_client()
# Resolved lazily in main() so importing this module never makes a live call.
WAREHOUSE_ID = ""


def run(sql: str, label: str) -> None:
    print(f"  • {label} …", end=" ", flush=True)
    resp = w.statement_execution.execute_statement(
        statement=sql, warehouse_id=WAREHOUSE_ID, wait_timeout="50s"
    )
    state = resp.status.state
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


def _row(*vals) -> str:
    return "(" + ", ".join(sql_str(v) for v in vals) + ")"


# --------------------------------------------------------------------------- #
# 1. commodity_input_costs — 24 monthly points per input (raw materials,
#    packaging, freight, energy). Index base 100, realistic drift/inflation.
# --------------------------------------------------------------------------- #
# (input_name, unit, annual_drift_pct, monthly_volatility)
COMMODITY_INPUTS = [
    ("PET Resin", "index (base 100)", 7.5, 1.8),
    ("Aluminum", "index (base 100)", 9.0, 2.4),
    ("Sugar/HFCS", "index (base 100)", 5.5, 1.2),
    ("Concentrate", "index (base 100)", 3.0, 0.7),
    ("Corrugate Packaging", "index (base 100)", 6.0, 1.5),
    ("Diesel Freight", "index (base 100)", 11.0, 3.1),
    ("Natural Gas Energy", "index (base 100)", 8.5, 4.0),
]


def build_commodity_input_costs(rng: random.Random) -> None:
    run(
        f"""CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.commodity_input_costs (
            input_name STRING, month DATE, index_value DOUBLE, yoy_pct DOUBLE, unit STRING
        ) COMMENT 'Monthly commodity / input-cost indices (base 100) for the beverage category, 24-month trailing window'""",
        "create commodity_input_costs",
    )
    # 24 months ending at the current month-start; oldest first.
    months: list[date] = []
    y, m = 2024, 7
    for _ in range(24):
        months.append(date(y, m, 1))
        m += 1
        if m > 12:
            m, y = 1, y + 1

    rows: list[str] = []
    for name, unit, drift, vol in COMMODITY_INPUTS:
        # Build a 24-month index series starting at base 100 with monthly drift.
        monthly_drift = drift / 12.0
        series: list[float] = []
        level = 100.0
        for _ in range(24):
            level = level * (1 + monthly_drift / 100.0) + rng.uniform(-vol, vol)
            series.append(round(level, 2))
        for i, mo in enumerate(months):
            yoy = None
            if i >= 12 and series[i - 12]:
                yoy = round((series[i] / series[i - 12] - 1) * 100, 2)
            rows.append(
                f"({sql_str(name)}, DATE'{mo.isoformat()}', {series[i]}, "
                f"{sql_str(yoy)}, {sql_str(unit)})"
            )
    run(
        f"INSERT INTO {CATALOG}.{SCHEMA}.commodity_input_costs VALUES\n" + ",\n".join(rows),
        "load commodity rows",
    )


# --------------------------------------------------------------------------- #
# 2. competitive_benchmarks — products x regions per supplier.
# --------------------------------------------------------------------------- #
# supplier_key -> [(product, competitor_name)]
COMPETITIVE = {
    "pepsi": [
        ("Pepsi 12pk 12oz Cans", "Coca-Cola 12pk"),
        ("Gatorade 8pk 20oz", "Powerade 8pk"),
        ("Aquafina 24pk 16.9oz", "Private Label Water"),
    ],
    "coke": [
        ("Coca-Cola 12pk 12oz Cans", "Pepsi 12pk"),
        ("Powerade 8pk 20oz", "Gatorade 8pk"),
        ("Dasani 24pk 16.9oz", "Private Label Water"),
    ],
    "kdp": [
        ("Dr Pepper 12pk 12oz Cans", "Coca-Cola 12pk"),
        ("Snapple 6pk 16oz", "Private Label Tea"),
        ("Canada Dry 12pk 12oz", "Schweppes 12pk"),
    ],
}
COMP_REGIONS = ["Pacific", "South Atlantic", "West South Central"]


def build_competitive_benchmarks(rng: random.Random) -> None:
    run(
        f"""CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.competitive_benchmarks (
            supplier_key STRING, product STRING, region STRING,
            our_shelf_price DOUBLE, competitor_name STRING, competitor_shelf_price DOUBLE,
            alt_supplier_quote DOUBLE, price_gap_pct DOUBLE
        ) COMMENT 'Shelf-price benchmarks vs competitors + alternate-supplier quotes by region'""",
        "create competitive_benchmarks",
    )
    rows: list[str] = []
    for skey, products in COMPETITIVE.items():
        for product, competitor in products:
            base = round(rng.uniform(6.49, 9.99), 2)
            for region in COMP_REGIONS:
                our = round(base + rng.uniform(-0.4, 0.4), 2)
                # Competitor typically within +/- a few percent.
                comp = round(our * (1 + rng.uniform(-0.06, 0.04)), 2)
                # Alt-supplier private-label / contract quote is below shelf.
                alt = round(our * (1 - rng.uniform(0.08, 0.18)), 2)
                gap = round((our / comp - 1) * 100, 2) if comp else None
                rows.append(_row(skey, product, region, our, competitor, comp, alt, gap))
    run(
        f"INSERT INTO {CATALOG}.{SCHEMA}.competitive_benchmarks VALUES\n" + ",\n".join(rows),
        "load competitive rows",
    )


# --------------------------------------------------------------------------- #
# 3. macro_indicators — FX, tariffs, labor inflation, supply-chain by quarter.
# --------------------------------------------------------------------------- #
QUARTERS = ["2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2"]
# (metric, unit, base, qoq_drift, exposure_note)
MACRO_METRICS = [
    ("USD/MXN", "rate", 17.1, 0.35,
     "Concentrate + bottling sourced from Mexico; weaker peso is a COGS tailwind for Kroger."),
    ("USD/EUR", "rate", 0.92, 0.006,
     "Specialty ingredients + machinery priced in EUR; euro strength pressures landed cost."),
    ("Aluminum Import Tariff", "%", 10.0, 0.0,
     "Section 232 aluminum tariff feeds directly into can-cost inflation claims."),
    ("Sugar TRQ Tariff", "%", 3.5, 0.1,
     "Tariff-rate-quota on imported sugar; caps the supplier's input-cost argument."),
    ("Labor Cost Inflation", "% YoY", 4.2, -0.25,
     "Manufacturing + warehouse wage growth; supplier cites this as a fixed-cost driver."),
    ("Supply-Chain Disruption Index", "index (base 100)", 118.0, -6.0,
     "Easing logistics stress undercuts surcharge / freight-recovery asks."),
]


def build_macro_indicators(rng: random.Random) -> None:
    run(
        f"""CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.macro_indicators (
            metric STRING, category STRING, period STRING, value DOUBLE, unit STRING, exposure_note STRING
        ) COMMENT 'Macroeconomic indicators (FX, tariffs, labor, supply-chain) by quarter with negotiation exposure notes'""",
        "create macro_indicators",
    )
    rows: list[str] = []
    for metric, unit, base, drift, note in MACRO_METRICS:
        level = base
        for q in QUARTERS:
            level = round(level + drift + rng.uniform(-abs(drift) * 0.3 or 0.02, abs(drift) * 0.3 or 0.02), 4)
            rows.append(_row(metric, "beverage", q, level, unit, note))
    run(
        f"INSERT INTO {CATALOG}.{SCHEMA}.macro_indicators VALUES\n" + ",\n".join(rows),
        "load macro rows",
    )


# --------------------------------------------------------------------------- #
# 4. sku_cost_waterfall — several SKUs per supplier. landed = sum of components.
#    prior_year_landed + proposed_landed power the YoY bridge + scenarios.
# --------------------------------------------------------------------------- #
SKUS = {
    "pepsi": ["Pepsi 12pk 12oz", "Gatorade 8pk 20oz", "Aquafina 24pk", "Mtn Dew 12pk 12oz"],
    "coke": ["Coca-Cola 12pk 12oz", "Powerade 8pk 20oz", "Dasani 24pk", "Sprite 12pk 12oz"],
    "kdp": ["Dr Pepper 12pk 12oz", "Snapple 6pk 16oz", "Canada Dry 12pk", "7UP 12pk 12oz"],
}


def build_sku_cost_waterfall(rng: random.Random) -> None:
    run(
        f"""CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.sku_cost_waterfall (
            supplier_key STRING, sku STRING,
            materials_cost DOUBLE, manufacturing_cost DOUBLE, packaging_cost DOUBLE,
            freight_cost DOUBLE, duty_cost DOUBLE, landed_cost DOUBLE,
            prior_year_landed DOUBLE, proposed_landed DOUBLE
        ) COMMENT 'SKU-level landed-cost waterfall (materials->mfg->packaging->freight->duty) with prior-year + Kroger-proposed landed cost'""",
        "create sku_cost_waterfall",
    )
    rows: list[str] = []
    for skey, skus in SKUS.items():
        for sku in skus:
            materials = round(rng.uniform(2.10, 3.40), 2)
            manufacturing = round(rng.uniform(0.80, 1.40), 2)
            packaging = round(rng.uniform(0.60, 1.20), 2)
            freight = round(rng.uniform(0.35, 0.85), 2)
            duty = round(rng.uniform(0.05, 0.30), 2)
            landed = round(materials + manufacturing + packaging + freight + duty, 2)
            # Prior year was 4-9% lower (the supplier's recent inflation).
            prior = round(landed / (1 + rng.uniform(0.04, 0.09)), 2)
            # Kroger's proposed landed cost claws 2.5-6% back off current.
            proposed = round(landed * (1 - rng.uniform(0.025, 0.06)), 2)
            rows.append(_row(skey, sku, materials, manufacturing, packaging,
                             freight, duty, landed, prior, proposed))
    run(
        f"INSERT INTO {CATALOG}.{SCHEMA}.sku_cost_waterfall VALUES\n" + ",\n".join(rows),
        "load sku waterfall rows",
    )


def main() -> None:
    global WAREHOUSE_ID
    WAREHOUSE_ID = resolve_warehouse_id(w)
    print(f"Building market + cost-breakdown data in {CATALOG}.{SCHEMA} (warehouse {WAREHOUSE_ID}, seed {SEED})")
    run(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA} COMMENT 'COGS negotiation agent data'", "create schema")
    # One RNG, seeded once and threaded through so the full dataset is deterministic.
    rng = random.Random(SEED)
    build_commodity_input_costs(rng)
    build_competitive_benchmarks(rng)
    build_macro_indicators(rng)
    build_sku_cost_waterfall(rng)
    write_state(catalog=CATALOG, schema=SCHEMA, warehouse_id=WAREHOUSE_ID)
    print("\nDone. Market + cost-breakdown tables ready:")
    for t in ("commodity_input_costs", "competitive_benchmarks", "macro_indicators", "sku_cost_waterfall"):
        print(f"  {CATALOG}.{SCHEMA}.{t}")


if __name__ == "__main__":
    main()
