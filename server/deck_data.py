"""Deterministic per-slide data fetch for the fixed 15-slide negotiation deck.

Where the Analytics Agent's Genie tool is NL->SQL (non-deterministic), the deck
needs the SAME numbers every time so it can be cited and trusted. This module
runs direct, parametrized SQL against the certified Delta tables in
``kroger_demo.cogs`` via the shared ``WorkspaceClient`` (statement execution on
the same Serverless warehouse data_foundation.py / build_market_data.py write
to). Each function returns plain dicts / lists ready to inject into a prompt.

Everything is defensive: a missing table or empty result yields ``[]`` / ``{}``
rather than raising, so the deck builder degrades gracefully BEFORE the data
load (build_market_data.py) has been run.
"""

from __future__ import annotations

import os
from typing import Any

from databricks.sdk.service.sql import StatementState

from .config import get_workspace_client

WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "a455a68035c1f578")
CATALOG = os.environ.get("COGS_CATALOG", "kroger_demo")
SCHEMA = os.environ.get("COGS_SCHEMA", "cogs")
FQ = f"{CATALOG}.{SCHEMA}"


def _query(sql: str, params: dict[str, Any] | None = None) -> tuple[list[str], list[list]]:
    """Run SQL and return (columns, rows). Returns ([], []) on any failure.

    Mirrors data_foundation.py's statement-execution + poll pattern. Parameters
    are passed via the SQL Statement Execution API's named-parameter binding
    (``:name`` placeholders) so values are never string-interpolated.
    """
    try:
        client = get_workspace_client()
        sql_params = None
        if params:
            from databricks.sdk.service.sql import StatementParameterListItem

            sql_params = [
                StatementParameterListItem(name=k, value=None if v is None else str(v))
                for k, v in params.items()
            ]
        resp = client.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=WAREHOUSE_ID,
            parameters=sql_params,
            wait_timeout="50s",
        )
        state = resp.status.state
        while state in (StatementState.PENDING, StatementState.RUNNING):
            resp = client.statement_execution.get_statement(resp.statement_id)
            state = resp.status.state
        if state != StatementState.SUCCEEDED:
            return [], []
        cols: list[str] = []
        if resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
            cols = [c.name for c in resp.manifest.schema.columns]
        rows: list[list] = []
        if resp.result and resp.result.data_array:
            rows = resp.result.data_array
        return cols, rows
    except Exception:
        return [], []


def _dicts(sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    cols, rows = _query(sql, params)
    if not cols or not rows:
        return []
    return [dict(zip(cols, r)) for r in rows]


def _num(v: Any) -> float | None:
    """Statement Execution returns all cells as strings; coerce numerics safely."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Slide 2 — Partnership Overview (supplier_scorecard)
# --------------------------------------------------------------------------- #
def partnership_overview(supplier_key: str) -> dict:
    rows = _dicts(
        f"""SELECT supplier, category, annual_spend, unit_volume, cogs_per_unit,
                   yoy_volume_change_pct, yoy_cogs_change_pct, landed_cost_index,
                   fill_rate_pct, otif_pct, rebate_tier, contract_expiry
            FROM {FQ}.supplier_scorecard
            WHERE supplier_key = :skey""",
        {"skey": supplier_key},
    )
    if not rows:
        return {}
    r = rows[0]
    return {
        "supplier": r.get("supplier"),
        "category": r.get("category"),
        "annual_spend": _num(r.get("annual_spend")),
        "unit_volume": _num(r.get("unit_volume")),
        "cogs_per_unit": _num(r.get("cogs_per_unit")),
        "yoy_volume_change_pct": _num(r.get("yoy_volume_change_pct")),
        "yoy_cogs_change_pct": _num(r.get("yoy_cogs_change_pct")),
        "landed_cost_index": _num(r.get("landed_cost_index")),
        "fill_rate_pct": _num(r.get("fill_rate_pct")),
        "otif_pct": _num(r.get("otif_pct")),
        "rebate_tier": r.get("rebate_tier"),
        "contract_expiry": r.get("contract_expiry"),
    }


# --------------------------------------------------------------------------- #
# Slide 3 — Commodity & Input Cost Trends (commodity_input_costs)
# --------------------------------------------------------------------------- #
def commodity_trends() -> dict:
    """Latest index + YoY per input, plus a trimmed monthly series for charting."""
    latest = _dicts(
        f"""WITH ranked AS (
              SELECT input_name, month, index_value, yoy_pct, unit,
                     ROW_NUMBER() OVER (PARTITION BY input_name ORDER BY month DESC) AS rn
              FROM {FQ}.commodity_input_costs
            )
            SELECT input_name, month, index_value, yoy_pct, unit
            FROM ranked WHERE rn = 1
            ORDER BY yoy_pct DESC NULLS LAST""",
    )
    inputs = [
        {
            "input_name": r.get("input_name"),
            "month": r.get("month"),
            "index_value": _num(r.get("index_value")),
            "yoy_pct": _num(r.get("yoy_pct")),
            "unit": r.get("unit"),
        }
        for r in latest
    ]
    # Compact monthly series (quarter-ends) so the line chart stays light.
    series = _dicts(
        f"""SELECT input_name, month, index_value
            FROM {FQ}.commodity_input_costs
            WHERE month >= add_months(
              (SELECT max(month) FROM {FQ}.commodity_input_costs), -12)
            ORDER BY input_name, month""",
    )
    by_input: dict[str, list[dict]] = {}
    for r in series:
        by_input.setdefault(r.get("input_name"), []).append(
            {"month": r.get("month"), "index_value": _num(r.get("index_value"))}
        )
    return {"inputs": inputs, "series": by_input}


# --------------------------------------------------------------------------- #
# Slide 4 — Competitive Landscape (competitive_benchmarks)
# --------------------------------------------------------------------------- #
def competitive_landscape(supplier_key: str) -> list[dict]:
    rows = _dicts(
        f"""SELECT product, region, our_shelf_price, competitor_name,
                   competitor_shelf_price, alt_supplier_quote, price_gap_pct
            FROM {FQ}.competitive_benchmarks
            WHERE supplier_key = :skey
            ORDER BY product, region""",
        {"skey": supplier_key},
    )
    return [
        {
            "product": r.get("product"),
            "region": r.get("region"),
            "our_shelf_price": _num(r.get("our_shelf_price")),
            "competitor_name": r.get("competitor_name"),
            "competitor_shelf_price": _num(r.get("competitor_shelf_price")),
            "alt_supplier_quote": _num(r.get("alt_supplier_quote")),
            "price_gap_pct": _num(r.get("price_gap_pct")),
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Slide 5 — Macroeconomic Factors (macro_indicators)
# --------------------------------------------------------------------------- #
def macro_factors(category: str = "beverage") -> list[dict]:
    rows = _dicts(
        f"""WITH ranked AS (
              SELECT metric, period, value, unit, exposure_note,
                     ROW_NUMBER() OVER (PARTITION BY metric ORDER BY period DESC) AS rn,
                     FIRST_VALUE(value) OVER (PARTITION BY metric ORDER BY period ASC) AS first_val
              FROM {FQ}.macro_indicators
              WHERE category = :cat
            )
            SELECT metric, period, value, unit, exposure_note, first_val
            FROM ranked WHERE rn = 1
            ORDER BY metric""",
        {"cat": category},
    )
    out: list[dict] = []
    for r in rows:
        latest = _num(r.get("value"))
        first = _num(r.get("first_val"))
        change = round(latest - first, 4) if (latest is not None and first is not None) else None
        out.append(
            {
                "metric": r.get("metric"),
                "period": r.get("period"),
                "value": latest,
                "unit": r.get("unit"),
                "change_since_start": change,
                "exposure_note": r.get("exposure_note"),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Slide 6 — SKU-level Cost Waterfall (sku_cost_waterfall)
# --------------------------------------------------------------------------- #
def cost_waterfall(supplier_key: str) -> list[dict]:
    rows = _dicts(
        f"""SELECT sku, materials_cost, manufacturing_cost, packaging_cost,
                   freight_cost, duty_cost, landed_cost,
                   prior_year_landed, proposed_landed
            FROM {FQ}.sku_cost_waterfall
            WHERE supplier_key = :skey
            ORDER BY landed_cost DESC""",
        {"skey": supplier_key},
    )
    return [
        {
            "sku": r.get("sku"),
            "materials_cost": _num(r.get("materials_cost")),
            "manufacturing_cost": _num(r.get("manufacturing_cost")),
            "packaging_cost": _num(r.get("packaging_cost")),
            "freight_cost": _num(r.get("freight_cost")),
            "duty_cost": _num(r.get("duty_cost")),
            "landed_cost": _num(r.get("landed_cost")),
            "prior_year_landed": _num(r.get("prior_year_landed")),
            "proposed_landed": _num(r.get("proposed_landed")),
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Slide 7 — Year-over-Year Cost Bridge (derived from sku_cost_waterfall)
# --------------------------------------------------------------------------- #
def yoy_bridge(supplier_key: str) -> dict:
    """Roll the SKU waterfall up to a prior -> current -> proposed bridge with a
    rough driver split (materials/mfg/packaging/freight/duty share of the rise)."""
    skus = cost_waterfall(supplier_key)
    if not skus:
        return {}
    prior = round(sum(s["prior_year_landed"] or 0 for s in skus), 2)
    current = round(sum(s["landed_cost"] or 0 for s in skus), 2)
    proposed = round(sum(s["proposed_landed"] or 0 for s in skus), 2)
    rise = current - prior
    # Attribute the rise across components by each component's share of current cost.
    comp_keys = [
        ("materials_cost", "Materials"),
        ("manufacturing_cost", "Manufacturing"),
        ("packaging_cost", "Packaging"),
        ("freight_cost", "Freight"),
        ("duty_cost", "Duty"),
    ]
    totals = {k: round(sum(s[k] or 0 for s in skus), 2) for k, _ in comp_keys}
    base = sum(totals.values()) or 1.0
    drivers = [
        {"driver": label, "amount": round(rise * (totals[k] / base), 2)}
        for k, label in comp_keys
    ]
    return {
        "prior_year_landed": prior,
        "current_landed": current,
        "proposed_landed": proposed,
        "total_increase": round(rise, 2),
        "proposed_savings": round(current - proposed, 2),
        "drivers": drivers,
    }


# --------------------------------------------------------------------------- #
# Slide 8 — Margin Impact (waterfall landed vs competitive shelf price)
# --------------------------------------------------------------------------- #
def margin_impact(supplier_key: str) -> list[dict]:
    """Per-SKU gross margin at current vs proposed landed cost, using the average
    competitor shelf price as the realized shelf proxy (best-effort match by
    leading product token; falls back to the supplier's blended shelf price)."""
    waterfall = cost_waterfall(supplier_key)
    bench = competitive_landscape(supplier_key)
    if not waterfall:
        return []
    shelf_prices = [b["our_shelf_price"] for b in bench if b.get("our_shelf_price")]
    blended_shelf = round(sum(shelf_prices) / len(shelf_prices), 2) if shelf_prices else None
    out: list[dict] = []
    for s in waterfall:
        # Try to match a benchmark product by shared leading token (e.g. "Pepsi").
        shelf = None
        token = (s["sku"] or "").split(" ")[0].lower()
        matches = [b["our_shelf_price"] for b in bench
                   if token and token in (b.get("product") or "").lower() and b.get("our_shelf_price")]
        if matches:
            shelf = round(sum(matches) / len(matches), 2)
        shelf = shelf or blended_shelf
        landed = s["landed_cost"]
        proposed = s["proposed_landed"]
        cur_margin = round((shelf - landed) / shelf * 100, 2) if (shelf and landed) else None
        new_margin = round((shelf - proposed) / shelf * 100, 2) if (shelf and proposed) else None
        out.append(
            {
                "sku": s["sku"],
                "shelf_price": shelf,
                "current_landed": landed,
                "proposed_landed": proposed,
                "current_margin_pct": cur_margin,
                "proposed_margin_pct": new_margin,
                "margin_gain_pts": round(new_margin - cur_margin, 2)
                if (cur_margin is not None and new_margin is not None) else None,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Slide 12 — Promotional & Trade Funding (supplier_scorecard + clauses)
# --------------------------------------------------------------------------- #
def trade_funding(supplier_key: str) -> dict:
    rows = _dicts(
        f"""SELECT supplier, annual_spend, trade_funds_pct, rebate_tier
            FROM {FQ}.supplier_scorecard
            WHERE supplier_key = :skey""",
        {"skey": supplier_key},
    )
    if not rows:
        return {}
    r = rows[0]
    spend = _num(r.get("annual_spend"))
    tf_pct = _num(r.get("trade_funds_pct"))
    trade_dollars = round(spend * tf_pct / 100, 0) if (spend and tf_pct is not None) else None
    return {
        "supplier": r.get("supplier"),
        "annual_spend": spend,
        "trade_funds_pct": tf_pct,
        "trade_funds_dollars": trade_dollars,
        "rebate_tier": r.get("rebate_tier"),
    }
