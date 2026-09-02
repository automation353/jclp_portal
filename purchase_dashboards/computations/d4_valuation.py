"""Dashboard 4 — Inventory On Hand & Valuation Board.

Brief §Dashboard 4. What JCPL holds right now in kg and rupees, cut by
material group. Every rupee is Rate: indicative until Decision 5 closes.
"""

from collections import defaultdict

from ..drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_GROUP, C_LEAD, C_RATE, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, C_VALUE, add_inventory, block, finalise, with_fields,
)
from ..field_map import num, rupees_in, txt


DASHBOARD_KEY = "d4"
TITLE = "Inventory On Hand & Valuation"

LINE_COLS = [C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP, C_STOCK, C_DAILY, C_COVER, C_LEAD, C_RATE, C_VALUE]


def compute(rows):
    n = len(rows)

    def stock(r):    return num(r["data"].get("current_stock_kg")) or 0
    def rate(r):     return num(r["data"].get("rate")) or 0
    def group_of(r): return txt(r["data"].get("group")) or "(no group)"

    def line(r):
        return dict(with_fields(r, "current_stock_kg", "daily_consumption",
                               "current_stock_days", "lead_time_days", "rate"),
                    value=stock(r) * rate(r))

    total_value = sum(stock(r) * rate(r) for r in rows)
    holding   = [r for r in rows if stock(r) > 0]
    zero      = [r for r in rows if stock(r) == 0]
    no_rate   = [r for r in rows if rate(r) == 0]


    by_value, by_kg, by_lines = defaultdict(float), defaultdict(float), defaultdict(int)
    for r in rows:
        g = group_of(r)
        by_value[g] += stock(r) * rate(r)
        by_kg[g]    += stock(r)
        by_lines[g] += 1

    if by_value:
        top_group, top_val = max(by_value.items(), key=lambda kv: kv[1])
        top_share = (top_val / total_value * 100) if total_value else 0
    else:
        top_group, top_val, top_share = "—", 0, 0

    # Dead/non-moving stock value (consolidated from D1 + D5 per #6)
    dead_holding = [r for r in rows
                    if txt(r["data"].get("category")) in ("Non Moving", "Slow Moving")
                    and stock(r) > 0]
    dead_value = sum(stock(r) * rate(r) for r in dead_holding)

    group_rows = [
        {"group": g, "lines": by_lines[g], "current_stock_kg": round(by_kg[g], 2),
         "value": by_value[g]}
        for g in sorted(by_value, key=lambda x: -by_value[x])
    ]

    tiles = {
        "total_value": {
            "label": "Total value of stock in store",
            "value": rupees_in(total_value),
            "sub": f"Current Stock × Rate across {n} rows",
            "kind": "info", "indicative": True,
        },
        "holding_stock": {
            "label": "Material actually lying in store",
            "value": len(holding), "sub": f"of {n}",
            "kind": "info",
        },
        "zero_stock": {
            "label": "Material showing nil stock",
            "value": len(zero),
            "sub": "Some are lookup failures, not empty bins — see Decision 2",
            "kind": "warn",
        },
        "largest_group": {
            "label": "Highest value item group",
            "value": top_group,
            "sub": f"{rupees_in(top_val)}  ·  {top_share:.0f}% of total",
            "kind": "info", "indicative": True,
        },
        "no_rate": {
            "label": "Rate not entered",
            "value": len(no_rate),
            "sub": f"of {n}  ·  value not counted in any rupee tile",
            "kind": "critical",
        },
        "dead_stock_capital": {
            "label": "Money sleeping in old stock",
            "value": rupees_in(dead_value),
            "sub": f"{len(dead_holding)} slow / non-moving lines still holding stock",
            "kind": "warn", "indicative": True,
        },
    }

    tile_rows = {
        "total_value": block(
            LINE_COLS,
            sorted([line(r) for r in holding], key=lambda x: x["value"], reverse=True),
        ),
        "holding_stock": block(
            LINE_COLS,
            sorted([line(r) for r in holding], key=lambda x: x["current_stock_kg"] or 0,
                   reverse=True),
        ),
        "zero_stock": block(
            add_inventory([C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP]),
            [line(r) for r in zero],
        ),
        "largest_group": block(
            LINE_COLS,
            sorted([line(r) for r in rows if group_of(r) == top_group],
                   key=lambda x: x["value"], reverse=True),
        ),
        "no_rate": block(
            add_inventory([C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP, C_STOCK]),
            [line(r) for r in no_rate],
        ),
        "dead_stock_capital": block(
            [C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP, C_STOCK, C_RATE, C_VALUE],
            sorted([line(r) for r in dead_holding],
                   key=lambda x: x["value"], reverse=True),
        ),
        # group breakdown lives on its own key so the UI can show it too
        "group_breakdown": block(
            [{"key": "group", "label": "Group"},
             {"key": "lines", "label": "Lines", "numeric": True},
             C_STOCK, C_VALUE],
            group_rows,
        ),
    }

    # group_breakdown is a supporting table, not a tile — expose it as one so
    # it stays reachable from the card grid.
    tiles["group_breakdown"] = {
        "label": "Group-wise value split",
        "value": len(group_rows),
        "sub": "One row per material group — line count, kg and value",
        "kind": "info", "indicative": True,
    }

    return finalise(tiles, tile_rows)
