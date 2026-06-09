"""Author the COGS Negotiation Genie space over kroger_demo.cogs.

Builds the serialized_space with the helper, wraps it in the create payload,
and writes /tmp/create_genie_space.json for `databricks api post`.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(
    0,
    "/Users/sumit.prakash/.claude/plugins/cache/fe-vibe/fe-internal-tools/1.4.5/skills/genie-rooms/resources",
)
from genie_space_builder import GenieSpaceBuilder  # noqa: E402

WAREHOUSE = "a455a68035c1f578"
CAT = "kroger_demo.cogs"

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
    "- landed_cost_index is indexed to a category baseline of 100; >100 means the supplier "
    "is more expensive than the category average.\n"
    "- A POSITIVE yoy_cogs_change_pct is COST INFLATION (unfavorable to Kroger); a negative "
    "value is favorable. yoy_volume_change_pct is unit-volume growth.\n"
    "- All figures are trailing 52 weeks. Spend is annual USD."
)

space.add_metric_view(f"{CAT}.landed_cost_metrics")
space.add_table(f"{CAT}.supplier_scorecard")
space.add_table(f"{CAT}.regional_performance")

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
]:
    space.add_benchmark(name=q, expected_response=sql, response_format="SQL")

space.validate()

# The export proto requires every id-keyed list sorted by id.
sd = space.to_dict()


def _sort_by_id(container: dict, *path: str) -> None:
    node = container
    for key in path[:-1]:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return
    last = path[-1]
    if isinstance(node, dict) and isinstance(node.get(last), list):
        node[last].sort(key=lambda x: x.get("id", "") if isinstance(x, dict) else "")


for p in [
    ("instructions", "text_instructions"),
    ("instructions", "example_question_sqls"),
    ("instructions", "sql_functions"),
    ("instructions", "join_specs"),
    ("benchmarks", "questions"),
    ("config", "sample_questions"),
]:
    _sort_by_id(sd, *p)

payload = {
    "title": space.title,
    "description": space.description,
    "parent_path": "/Workspace/Users/sumit.prakash@databricks.com",
    "warehouse_id": space.warehouse_id,
    "serialized_space": json.dumps(sd),
}
with open("/tmp/create_genie_space.json", "w") as f:
    json.dump(payload, f, indent=2)
print("Wrote /tmp/create_genie_space.json")
print("tables:", [t.get("identifier") for t in space.to_dict()["data_sources"]["tables"]])
