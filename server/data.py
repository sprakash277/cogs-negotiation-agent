"""Synthetic COGS / supplier data for the Kroger beverage category.

This is the demo stand-in for what will eventually be Unity Catalog Delta
tables + Metric Views queried via Genie. The shape mirrors a certified
"landed cost" metric view so the swap is mechanical later:

    get_supplier_scorecard()  -> what a Genie NL->SQL call would return
    get_category_overview()   -> category-level KPIs (the deck hero numbers)

Numbers are illustrative only. Beverage category, FY trailing 52 weeks.
"""

from __future__ import annotations

# Trailing-52-week supplier scorecard. Dollars in USD.
SUPPLIERS: list[dict] = [
    {
        "supplier": "PepsiCo",
        "key": "pepsi",
        "category": "Carbonated Soft Drinks",
        "annual_spend": 1_842_000_000,
        "cogs_per_unit": 0.62,
        "unit_volume": 2_970_000_000,
        "landed_cost_index": 104.2,      # vs category baseline 100
        "yoy_cogs_change_pct": 6.8,      # COGS inflation pushed by supplier
        "yoy_volume_change_pct": -1.9,
        "trade_funds_pct": 11.4,         # promo / trade dollars as % of spend
        "fill_rate_pct": 96.1,
        "otif_pct": 91.3,                # on-time-in-full
        "contract_expiry": "2026-12-31",
        "rebate_tier": "Tier 3 (>$1.5B)",
        "open_negotiation": True,
    },
    {
        "supplier": "The Coca-Cola Company",
        "key": "coke",
        "category": "Carbonated Soft Drinks",
        "annual_spend": 2_010_000_000,
        "cogs_per_unit": 0.59,
        "unit_volume": 3_405_000_000,
        "landed_cost_index": 101.7,
        "yoy_cogs_change_pct": 5.1,
        "yoy_volume_change_pct": 0.4,
        "trade_funds_pct": 13.2,
        "fill_rate_pct": 97.4,
        "otif_pct": 93.8,
        "contract_expiry": "2027-06-30",
        "rebate_tier": "Tier 3 (>$1.5B)",
        "open_negotiation": True,
    },
    {
        "supplier": "Keurig Dr Pepper",
        "key": "kdp",
        "category": "CSD + Coffee Systems",
        "annual_spend": 720_000_000,
        "cogs_per_unit": 0.71,
        "unit_volume": 905_000_000,
        "landed_cost_index": 108.9,
        "yoy_cogs_change_pct": 9.3,
        "yoy_volume_change_pct": 2.7,
        "trade_funds_pct": 8.6,
        "fill_rate_pct": 94.2,
        "otif_pct": 88.5,
        "contract_expiry": "2026-09-30",
        "rebate_tier": "Tier 2 ($500M-$1.5B)",
        "open_negotiation": True,
    },
]

# Region rows for the deck's regional-performance table / US map.
REGIONS: list[dict] = [
    {"region": "Pacific",            "dollar_sales": 982_000_000, "yoy_pct": 3.1,  "unit_sales": 1_540_000_000, "stores": 412},
    {"region": "Mountain",          "dollar_sales": 511_000_000, "yoy_pct": 1.4,  "unit_sales": 820_000_000,   "stores": 233},
    {"region": "West South Central","dollar_sales": 1_188_000_000,"yoy_pct": 4.6, "unit_sales": 1_910_000_000, "stores": 489},
    {"region": "East North Central","dollar_sales": 1_044_000_000,"yoy_pct": -0.8,"unit_sales": 1_705_000_000, "stores": 521},
    {"region": "South Atlantic",    "dollar_sales": 1_402_000_000,"yoy_pct": 2.2, "unit_sales": 2_180_000_000, "stores": 603},
    {"region": "Middle Atlantic",   "dollar_sales": 770_000_000, "yoy_pct": 0.6,  "unit_sales": 1_150_000_000, "stores": 318},
    {"region": "New England",       "dollar_sales": 398_000_000, "yoy_pct": 1.0,  "unit_sales": 590_000_000,   "stores": 174},
]


def get_supplier_scorecard(supplier_key: str | None = None) -> list[dict]:
    if supplier_key:
        return [s for s in SUPPLIERS if s["key"] == supplier_key.lower()]
    return SUPPLIERS


def get_supplier(supplier_key: str | None) -> dict | None:
    if not supplier_key:
        return None
    for s in SUPPLIERS:
        if s["key"] == supplier_key.lower():
            return s
    return None


def get_category_overview() -> dict:
    total_spend = sum(s["annual_spend"] for s in SUPPLIERS)
    total_units = sum(s["unit_volume"] for s in SUPPLIERS)
    weighted_cogs = sum(s["cogs_per_unit"] * s["unit_volume"] for s in SUPPLIERS) / total_units
    weighted_yoy = sum(s["yoy_cogs_change_pct"] * s["annual_spend"] for s in SUPPLIERS) / total_spend
    return {
        "category": "Beverages",
        "total_spend": total_spend,
        "total_units": total_units,
        "avg_cogs_per_unit": round(weighted_cogs, 3),
        "blended_cogs_inflation_pct": round(weighted_yoy, 2),
        "supplier_count": len(SUPPLIERS),
        "regions": REGIONS,
    }
