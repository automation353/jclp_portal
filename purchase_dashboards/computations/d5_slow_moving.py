"""Dashboard 5 — Slow & Non-Moving Stock Board.

Brief §Dashboard 5. Share of the master that isn't turning and the capital
inside it. Whether the classification is fresh is Decision 6 — the board
reports what Category says, and every tile drills to its rows.
"""

from ..drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_GROUP, C_ITYPE, C_LEAD, C_RATE, C_RM,
    C_SPEC, C_SR, C_STOCK, C_TALLY, C_VALUE, block, finalise, with_fields,
)
from ..field_map import num, txt


DASHBOARD_KEY = "d5"
TITLE = "Slow & Non-Moving Stock"

LINE_COLS = [C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_ITYPE, C_GROUP, C_STOCK, C_DAILY, C_COVER, C_LEAD, C_RATE, C_VALUE]


def compute(rows):
    n = len(rows)

    def stock(r): return num(r["data"].get("current_stock_kg")) or 0
    def rate(r):  return num(r["data"].get("rate")) or 0
    def cat(r):   return txt(r["data"].get("category"))
    def line(r):
        return dict(with_fields(r, "current_stock_kg", "daily_consumption",
                               "current_stock_days", "lead_time_days", "rate"),
                    value=stock(r) * rate(r))

    non_moving  = [r for r in rows if cat(r) == "Non Moving"]
    slow_moving = [r for r in rows if cat(r) == "Slow Moving"]
    fast        = [r for r in rows if cat(r) == "Fast Moving"]
    medium      = [r for r in rows if cat(r) == "Medium Fast"]
    active      = fast + medium

    dead_holding = [r for r in rows
                    if cat(r) in ("Non Moving", "Slow Moving") and stock(r) > 0]

    dead_rows = sorted([line(r) for r in dead_holding],
                       key=lambda x: x["value"], reverse=True)

    tiles = {
        "non_moving": {
            "label": "Material not used at all", "value": len(non_moving),
            "sub": f"of {n}", "kind": "warn",
        },
        "slow_moving": {
            "label": "Material used very slowly", "value": len(slow_moving),
            "sub": f"of {n}", "kind": "warn",
        },
        "fast_medium": {
            "label": "Material in regular use", "value": len(active),
            "sub": f"{len(fast)} fast · {len(medium)} medium fast — the genuinely active master",
            "kind": "score",
        },
        "dead_holding_stock": {
            "label": "Idle material lying in store", "value": len(dead_holding),
            "sub": "Non-moving or slow-moving items with a physical balance",
            "kind": "critical",
        },
    }

    tile_rows = {
        "non_moving":  block(LINE_COLS, sorted([line(r) for r in non_moving],
                                               key=lambda x: x["value"], reverse=True)),
        "slow_moving": block(LINE_COLS, sorted([line(r) for r in slow_moving],
                                               key=lambda x: x["value"], reverse=True)),
        "fast_medium": block(LINE_COLS, sorted([line(r) for r in active],
                                               key=lambda x: x["value"], reverse=True)),
        "dead_holding_stock": block(LINE_COLS, dead_rows),
    }

    return finalise(tiles, tile_rows)
