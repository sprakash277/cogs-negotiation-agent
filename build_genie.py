"""Author + create/update the COGS Negotiation Genie space over <catalog>.<schema>.

Builds the serialized_space with the helper, then ACTUALLY creates (or PATCHes,
if a space id is already in deploy_state.json) the Genie space via the REST API,
captures the returned space_id into deploy_state.json, and also writes
/tmp/create_genie_space.json for reference / `databricks api post`.

Catalog/schema/warehouse/parent path are resolved from deploy_config so the
space is portable to any workspace.
"""

from __future__ import annotations

import json
import sys

from deploy_config import (
    FQ,
    get_state,
    get_workspace_client,
    resolve_parent_path,
    resolve_warehouse_id,
    write_state,
)

sys.path.insert(
    0,
    "/Users/sumit.prakash/.claude/plugins/cache/fe-vibe/fe-internal-tools/1.4.5/skills/genie-rooms/resources",
)
from genie_space_builder import GenieSpaceBuilder  # noqa: E402

w = get_workspace_client()
# Resolved lazily in main(); placeholder so module import never makes a live call.
WAREHOUSE = ""
CAT = FQ  # e.g. "kroger_demo.cogs"

space = GenieSpaceBuilder(
    title="COGS Negotiation — Beverage Category",
    description=(
        "Certified COGS, landed-cost, and supplier-scorecard analytics for Kroger "
        "beverage category negotiations (PepsiCo, Coca-Cola, Keurig Dr Pepper). "
        "Powers the Supplier Scorecard and Fact-Pack decks in the COGS Negotiation Agent."
    ),
    warehouse_id=WAREHOUSE,
)

space.set_instructions(
    "You answer questions for Kroger category negotiators about beverage-supplier COGS.\n"
    "- For COGS, landed-cost, spend, and inflation roll-ups, PREFER the metric view "
    f"`{CAT}.landed_cost_metrics`; its measures must be wrapped in MEASURE(), e.g. "
    "SELECT `Supplier`, MEASURE(`Total Spend`) FROM ... GROUP BY `Supplier`.\n"
    f"- Supplier-level facts (fill rate, OTIF, trade funds, contract expiry, rebate tier) "
    f"are in `{CAT}.supplier_scorecard` (one row per supplier).\n"
    f"- Regional sales are in `{CAT}.regional_performance`.\n"
    f"- Commodity / input-cost indices (PET resin, aluminum, sugar/HFCS, concentrate, "
    f"corrugate, diesel freight, natural gas) are in `{CAT}.commodity_input_costs`, "
    "monthly, base 100, with yoy_pct; >100 means above the 24-month-ago baseline.\n"
    f"- Shelf-price benchmarks vs competitors + alternate-supplier quotes are in "
    f"`{CAT}.competitive_benchmarks` (our_shelf_price vs competitor_shelf_price, "
    "alt_supplier_quote, price_gap_pct) by product and region.\n"
    f"- Macro indicators (FX USD/MXN + USD/EUR, tariffs, labor inflation, supply-chain "
    f"disruption index) are in `{CAT}.macro_indicators`, one row per metric per quarter "
    "(period like '2025-Q1'), each with an exposure_note for negotiation framing.\n"
    f"- SKU-level landed-cost waterfalls are in `{CAT}.sku_cost_waterfall`: landed_cost = "
    "materials_cost + manufacturing_cost + packaging_cost + freight_cost + duty_cost; "
    "prior_year_landed and proposed_landed support the YoY bridge and Kroger's proposed terms.\n"
    "- landed_cost_index is indexed to a category baseline of 100; >100 means the supplier "
    "is more expensive than the category average.\n"
    "- A POSITIVE yoy_cogs_change_pct is COST INFLATION (unfavorable to Kroger); a negative "
    "value is favorable. yoy_volume_change_pct is unit-volume growth.\n"
    "- All figures are trailing 52 weeks. Spend is annual USD."
)

space.add_metric_view(f"{CAT}.landed_cost_metrics")
space.add_table(f"{CAT}.supplier_scorecard")
space.add_table(f"{CAT}.regional_performance")
space.add_table(f"{CAT}.commodity_input_costs")
space.add_table(f"{CAT}.competitive_benchmarks")
space.add_table(f"{CAT}.macro_indicators")
space.add_table(f"{CAT}.sku_cost_waterfall")

space.add_example_sql(
    title="Which supplier has the highest COGS inflation?",
    sql=(
        "SELECT supplier, yoy_cogs_change_pct, landed_cost_index\n"
        f"FROM {CAT}.supplier_scorecard\n"
        "ORDER BY yoy_cogs_change_pct DESC"
    ),
)
space.add_example_sql(
    title="Total spend and blended COGS inflation by supplier",
    sql=(
        "SELECT `Supplier`, MEASURE(`Total Spend`) AS total_spend,\n"
        "       MEASURE(`Blended COGS Inflation Pct`) AS cogs_inflation_pct\n"
        f"FROM {CAT}.landed_cost_metrics\n"
        "GROUP BY `Supplier`\n"
        "ORDER BY total_spend DESC"
    ),
)
space.add_example_sql(
    title="Top regions by beverage dollar sales growth",
    sql=(
        "SELECT region, dollar_sales, yoy_pct\n"
        f"FROM {CAT}.regional_performance\n"
        "ORDER BY yoy_pct DESC"
    ),
)
space.add_example_sql(
    title="Latest commodity input-cost indices ranked by YoY increase",
    sql=(
        "WITH ranked AS (\n"
        "  SELECT input_name, month, index_value, yoy_pct,\n"
        "         ROW_NUMBER() OVER (PARTITION BY input_name ORDER BY month DESC) AS rn\n"
        f"  FROM {CAT}.commodity_input_costs)\n"
        "SELECT input_name, index_value, yoy_pct FROM ranked WHERE rn = 1\n"
        "ORDER BY yoy_pct DESC"
    ),
)
space.add_example_sql(
    title="SKU landed-cost waterfall and proposed savings for a supplier",
    sql=(
        "SELECT sku, materials_cost, manufacturing_cost, packaging_cost,\n"
        "       freight_cost, duty_cost, landed_cost, prior_year_landed, proposed_landed,\n"
        "       round(landed_cost - proposed_landed, 2) AS proposed_savings\n"
        f"FROM {CAT}.sku_cost_waterfall\n"
        "WHERE supplier_key = 'pepsi'\n"
        "ORDER BY landed_cost DESC"
    ),
)
space.add_example_sql(
    title="Shelf-price gap vs competitors by product",
    sql=(
        "SELECT product, region, our_shelf_price, competitor_shelf_price,\n"
        "       alt_supplier_quote, price_gap_pct\n"
        f"FROM {CAT}.competitive_benchmarks\n"
        "WHERE supplier_key = 'coke'\n"
        "ORDER BY price_gap_pct DESC"
    ),
)

for q, sql in [
    ("Which supplier has the highest COGS inflation year over year?",
     f"SELECT supplier, yoy_cogs_change_pct FROM {CAT}.supplier_scorecard "
     "ORDER BY yoy_cogs_change_pct DESC LIMIT 1"),
    ("What is our total annual spend across all beverage suppliers?",
     f"SELECT MEASURE(`Total Spend`) AS total_spend FROM {CAT}.landed_cost_metrics"),
    ("Rank suppliers by landed cost index.",
     f"SELECT supplier, landed_cost_index FROM {CAT}.supplier_scorecard "
     "ORDER BY landed_cost_index DESC"),
    ("Which supplier has the worst on-time-in-full performance?",
     f"SELECT supplier, otif_pct FROM {CAT}.supplier_scorecard ORDER BY otif_pct ASC LIMIT 1"),
    ("Show me regional dollar sales sorted by growth.",
     f"SELECT region, dollar_sales, yoy_pct FROM {CAT}.regional_performance ORDER BY yoy_pct DESC"),
    ("Which input cost is rising fastest year over year?",
     "WITH ranked AS (SELECT input_name, yoy_pct, "
     "ROW_NUMBER() OVER (PARTITION BY input_name ORDER BY month DESC) AS rn "
     f"FROM {CAT}.commodity_input_costs) "
     "SELECT input_name, yoy_pct FROM ranked WHERE rn = 1 ORDER BY yoy_pct DESC LIMIT 1"),
    ("What is the total proposed landed-cost savings for Pepsi across SKUs?",
     "SELECT round(SUM(landed_cost - proposed_landed), 2) AS proposed_savings "
     f"FROM {CAT}.sku_cost_waterfall WHERE supplier_key = 'pepsi'"),
    ("Where is our shelf price above the competitor for Coca-Cola?",
     "SELECT product, region, price_gap_pct "
     f"FROM {CAT}.competitive_benchmarks WHERE supplier_key = 'coke' AND price_gap_pct > 0 "
     "ORDER BY price_gap_pct DESC"),
    ("What is the latest USD/MXN FX rate exposure?",
     "WITH ranked AS (SELECT metric, value, period, "
     "ROW_NUMBER() OVER (PARTITION BY metric ORDER BY period DESC) AS rn "
     f"FROM {CAT}.macro_indicators WHERE metric = 'USD/MXN') "
     "SELECT metric, value, period FROM ranked WHERE rn = 1"),
]:
    space.add_benchmark(name=q, expected_response=sql, response_format="SQL")


def _sort_by_id(container: dict, *path: str) -> None:
    node = container
    for key in path[:-1]:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return
    last = path[-1]
    if isinstance(node, dict) and isinstance(node.get(last), list):
        node[last].sort(key=lambda x: x.get("id", "") if isinstance(x, dict) else "")


def main() -> None:
    # Resolve workspace-specific bits now (deferred from import time).
    warehouse = resolve_warehouse_id(w)
    space.set_warehouse(warehouse)
    parent_path = resolve_parent_path(w)

    space.validate()

    # The export proto requires every id-keyed list sorted by id.
    sd = space.to_dict()
    for p in [
        ("instructions", "text_instructions"),
        ("instructions", "example_question_sqls"),
        ("instructions", "sql_functions"),
        ("instructions", "join_specs"),
        ("benchmarks", "questions"),
        ("config", "sample_questions"),
    ]:
        _sort_by_id(sd, *p)

    serialized = json.dumps(sd)
    payload = {
        "title": space.title,
        "description": space.description,
        "parent_path": parent_path,
        "warehouse_id": space.warehouse_id,
        "serialized_space": serialized,
    }
    # Reference copy (harmless) for `databricks api post`.
    with open("/tmp/create_genie_space.json", "w") as f:
        json.dump(payload, f, indent=2)
    print("Wrote /tmp/create_genie_space.json")
    print("tables:", [t.get("identifier") for t in sd["data_sources"]["tables"]])

    existing_id = get_state("genie_space_id")
    if existing_id:
        # PATCH the existing space — parent_path is immutable, omit it.
        print(f"Updating existing Genie space {existing_id} …")
        patch_body = {k: v for k, v in payload.items() if k != "parent_path"}
        w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{existing_id}", body=patch_body)
        space_id = existing_id
    else:
        print("Creating Genie space …")
        resp = w.api_client.do("POST", "/api/2.0/genie/spaces", body=payload)
        space_id = (resp or {}).get("space_id") or (resp or {}).get("id")
        if not space_id:
            raise RuntimeError(f"Genie space create returned no space_id: {resp}")

    write_state(genie_space_id=space_id)
    print(f"Genie space id: {space_id}")


if __name__ == "__main__":
    main()
