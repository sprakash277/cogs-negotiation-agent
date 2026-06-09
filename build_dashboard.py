"""Build / update + publish the AI/BI (Lakeview) dashboard over kroger_demo.cogs.

Global filters page (Supplier, Rebate Tier, Region) + overview page with KPI
counters (that respect the filters), supplier bars, regional bars, detail table.
Counters aggregate off the `suppliers` dataset so the Supplier/Rebate filters
flow through to them. Tests queries, then PATCHes the existing dashboard +
republishes.
"""

from __future__ import annotations

import json

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

PROFILE = "cogs-demo"
WAREHOUSE = "a455a68035c1f578"
PARENT = "/Users/sumit.prakash@databricks.com"
DASHBOARD_ID = "01f1643845191b049c9a3acf7531495b"
w = WorkspaceClient(profile=PROFILE)

SUPPLIERS_SQL = (
    "SELECT supplier, category, annual_spend, cogs_per_unit, unit_volume, landed_cost_index, "
    "yoy_cogs_change_pct, yoy_volume_change_pct, trade_funds_pct, fill_rate_pct, otif_pct, "
    "contract_expiry, rebate_tier FROM kroger_demo.cogs.supplier_scorecard"
)
REGIONS_SQL = (
    "SELECT region, dollar_sales, yoy_pct, unit_sales, stores FROM kroger_demo.cogs.regional_performance"
)


def test_query(sql, label):
    r = w.statement_execution.execute_statement(statement=sql, warehouse_id=WAREHOUSE, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"{label} FAILED: {r.status.error.message if r.status.error else r.status.state}")
    print(f"  • query ok: {label}")


def text(name, md, x, y, w_, h):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": [md]}},
            "position": {"x": x, "y": y, "width": w_, "height": h}}


def counter_agg(name, field, expr, title, x, y):
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {
        "datasetName": "suppliers", "fields": [{"name": field, "expression": expr}], "disaggregated": False}}],
        "spec": {"version": 2, "widgetType": "counter",
                 "encodings": {"value": {"fieldName": field, "displayName": title}},
                 "frame": {"showTitle": True, "title": title}}},
        "position": {"x": x, "y": y, "width": 2, "height": 3}}


def bar(name, ds, xf, yf, yexpr, title, x, y, color="#FF6F3C"):
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {
        "datasetName": ds, "fields": [{"name": xf, "expression": f"`{xf}`"},
                                       {"name": yf, "expression": yexpr}], "disaggregated": False}}],
        "spec": {"version": 3, "widgetType": "bar",
                 "encodings": {"x": {"fieldName": xf, "scale": {"type": "categorical", "sort": {"by": "y-reversed"}}, "displayName": xf},
                               "y": {"fieldName": yf, "scale": {"type": "quantitative"}, "displayName": title},
                               "label": {"show": True}},
                 "frame": {"showTitle": True, "title": title}, "mark": {"colors": [color]}}},
        "position": {"x": x, "y": y, "width": 3, "height": 5}}


def flt(name, ds, field, title, x, y):
    qn = f"{ds}_{field}"
    return {"widget": {"name": name, "queries": [{"name": qn, "query": {
        "datasetName": ds, "fields": [{"name": field, "expression": f"`{field}`"}], "disaggregated": False}}],
        "spec": {"version": 2, "widgetType": "filter-multi-select",
                 "encodings": {"fields": [{"fieldName": field, "displayName": title, "queryName": qn}]},
                 "frame": {"showTitle": True, "title": title}}},
        "position": {"x": x, "y": y, "width": 2, "height": 2}}


def build_serialized():
    datasets = [
        {"name": "suppliers", "displayName": "Suppliers", "queryLines": [SUPPLIERS_SQL]},
        {"name": "regions", "displayName": "Regions", "queryLines": [REGIONS_SQL]},
    ]
    filters_page = {
        "name": "global_filters", "displayName": "Filters", "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
        "layout": [
            flt("f-supplier", "suppliers", "supplier", "Supplier", 0, 0),
            flt("f-rebate", "suppliers", "rebate_tier", "Rebate Tier", 2, 0),
            flt("f-region", "regions", "region", "Region", 4, 0),
        ],
    }
    overview = {
        "name": "overview", "displayName": "Overview", "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            text("title", "## COGS Negotiation — Beverage Category", 0, 0, 6, 1),
            text("subtitle", "Certified COGS, landed cost & supplier scorecard · trailing 52 weeks · source: kroger_demo.cogs · use the Filters tab", 0, 1, 6, 1),
            counter_agg("c-spend", "sum(annual_spend)", "SUM(`annual_spend`)", "Total Annual Spend ($)", 0, 2),
            counter_agg("c-infl", "avg(yoy_cogs_change_pct)", "AVG(`yoy_cogs_change_pct`)", "Avg COGS Inflation (%)", 2, 2),
            counter_agg("c-otif", "avg(otif_pct)", "AVG(`otif_pct`)", "Avg OTIF (%)", 4, 2),
            text("h-supplier", "### Supplier Comparison", 0, 5, 6, 1),
            bar("b-spend", "suppliers", "supplier", "sum(annual_spend)", "SUM(`annual_spend`)", "Annual Spend by Supplier", 0, 6),
            bar("b-index", "suppliers", "supplier", "max(landed_cost_index)", "MAX(`landed_cost_index`)", "Landed Cost Index by Supplier", 3, 6, color="#FB7185"),
            text("h-region", "### Regional Performance", 0, 11, 6, 1),
            bar("b-rsales", "regions", "region", "sum(dollar_sales)", "SUM(`dollar_sales`)", "Dollar Sales by Region", 0, 12, color="#22D3EE"),
            bar("b-rgrowth", "regions", "region", "max(yoy_pct)", "MAX(`yoy_pct`)", "YoY Growth % by Region", 3, 12, color="#64FFDA"),
            text("h-detail", "### Supplier Detail", 0, 17, 6, 1),
            {"widget": {"name": "t-detail", "queries": [{"name": "main_query", "query": {
                "datasetName": "suppliers", "fields": [
                    {"name": "supplier", "expression": "`supplier`"},
                    {"name": "annual_spend", "expression": "`annual_spend`"},
                    {"name": "cogs_per_unit", "expression": "`cogs_per_unit`"},
                    {"name": "landed_cost_index", "expression": "`landed_cost_index`"},
                    {"name": "yoy_cogs_change_pct", "expression": "`yoy_cogs_change_pct`"},
                    {"name": "otif_pct", "expression": "`otif_pct`"},
                    {"name": "fill_rate_pct", "expression": "`fill_rate_pct`"},
                    {"name": "rebate_tier", "expression": "`rebate_tier`"},
                    {"name": "contract_expiry", "expression": "`contract_expiry`"}],
                "disaggregated": True}}],
                "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": [
                    {"fieldName": "supplier", "displayName": "Supplier"},
                    {"fieldName": "annual_spend", "displayName": "Annual Spend"},
                    {"fieldName": "cogs_per_unit", "displayName": "COGS/Unit"},
                    {"fieldName": "landed_cost_index", "displayName": "Landed Idx"},
                    {"fieldName": "yoy_cogs_change_pct", "displayName": "COGS YoY %"},
                    {"fieldName": "otif_pct", "displayName": "OTIF %"},
                    {"fieldName": "fill_rate_pct", "displayName": "Fill %"},
                    {"fieldName": "rebate_tier", "displayName": "Rebate Tier"},
                    {"fieldName": "contract_expiry", "displayName": "Expiry"}]},
                    "frame": {"showTitle": True, "title": "Supplier Scorecard"}}},
                "position": {"x": 0, "y": 18, "width": 6, "height": 6}},
        ],
    }
    return json.dumps({"datasets": datasets, "pages": [filters_page, overview],
                       "uiSettings": {"theme": {"widgetHeaderAlignment": "ALIGNMENT_UNSPECIFIED"}}})


def main():
    print("Testing queries…")
    test_query(SUPPLIERS_SQL, "suppliers")
    test_query(REGIONS_SQL, "regions")
    print("Updating dashboard…")
    w.api_client.do("PATCH", f"/api/2.0/lakeview/dashboards/{DASHBOARD_ID}", body={
        "display_name": "COGS Negotiation — Beverage Category",
        "serialized_dashboard": build_serialized(),
    })
    print("Publishing…")
    w.api_client.do("POST", f"/api/2.0/lakeview/dashboards/{DASHBOARD_ID}/published", body={"warehouse_id": WAREHOUSE})
    print("PUBLISHED with global filters")


if __name__ == "__main__":
    main()
