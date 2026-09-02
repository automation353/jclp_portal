"""Dashboard 6 — Buffer Capital Board.

Brief §Dashboard 6. What JCPL's own safety-stock policy commits in cash
before a PO is raised, plus the MTS lines where the policy switches itself
off via the 500 kg threshold on Green Level (Decision 7).
"""

from ..drill import (
    C_COVER, C_DAILY, C_GROUP, C_ITYPE, C_LEAD, C_LEVELS, C_RATE, C_RM,
    C_SPEC, C_SR, C_STOCK, C_TALLY, C_VALUE, block, finalise, with_fields,
)
from ..field_map import num, rupees_in, txt


DASHBOARD_KEY = "d6"
TITLE = "Buffer Capital"

BUFFER_COLS = [C_SR, C_TALLY, C_RM, C_SPEC, C_ITYPE, C_LEVELS,
               {"key": "green_level", "label": "Green level", "numeric": True},
               C_STOCK, C_DAILY, C_COVER, C_LEAD, C_RATE, C_VALUE]


def compute(rows):
    def stock(r): return num(r["data"].get("current_stock_kg")) or 0
    def rate(r):  return num(r["data"].get("rate")) or 0
    def gl(r):    return num(r["data"].get("green_level")) or 0
    def itype(r): return txt(r["data"].get("inventory_type"))

    def line(r, value):
        return dict(with_fields(r, "levels", "green_level", "current_stock_kg",
                               "daily_consumption", "current_stock_days",
                               "lead_time_days", "rate"),
                    value=value)

    mts = [r for r in rows if itype(r) == "MTS"]
    mto = [r for r in rows if itype(r) == "MTO"]
    mts_no_buffer = [r for r in mts if gl(r) == 0]

    buffer_committed = sum(gl(r) * rate(r) for r in rows)

    active = [r for r in rows if gl(r) > 0]
    total_gl_kg  = sum(gl(r) for r in active)
    total_cs_kg  = sum(stock(r) for r in active)

    overstock = [r for r in rows if stock(r) > gl(r) > 0]
    overstock_val = sum((stock(r) - gl(r)) * rate(r) for r in overstock)

    diff_kg = total_cs_kg - total_gl_kg

    tiles = {
        "buffer_committed": {
            "label": "Money needed for minimum stock",
            "value": rupees_in(buffer_committed),
            "sub": "Green Level × Rate across all rows",
            "kind": "info", "indicative": True,
        },
        "mts_lines": {
            "label": "Material kept ready in advance (MTS)", "value": len(mts),
            "sub": "Items the policy says must be buffered",
            "kind": "info",
        },
        "mto_lines": {
            "label": "Material bought only against order (MTO)", "value": len(mto),
            "sub": "Bought only against demand — no buffer expected",
            "kind": "info",
        },
        "mts_no_buffer": {
            "label": "Minimum level not fixed", "value": len(mts_no_buffer),
            "sub": "Classified MTS but Green Level is zero — policy failure (Decision 7)",
            "kind": "critical",
        },
        "stock_above_green": {
            "label": "Extra stock above minimum level",
            "value": f"{abs(diff_kg):,.0f} kg  ·  {rupees_in(overstock_val)}",
            "sub": f"{len(overstock)} lines holding more than policy asks for",
            "kind": "warn" if overstock else "info",
            "indicative": True,
        },
    }

    tile_rows = {
        "buffer_committed": block(
            BUFFER_COLS,
            sorted([line(r, gl(r) * rate(r)) for r in rows if gl(r) > 0],
                   key=lambda x: x["value"], reverse=True),
        ),
        "mts_lines": block(
            BUFFER_COLS,
            sorted([line(r, gl(r) * rate(r)) for r in mts],
                   key=lambda x: x["value"], reverse=True),
        ),
        "mto_lines": block(
            BUFFER_COLS,
            [line(r, gl(r) * rate(r)) for r in mto],
        ),
        "mts_no_buffer": block(
            BUFFER_COLS + [{"key": "note", "label": "Why"}],
            [dict(line(r, 0),
                  note="MTS with Green Level = 0 (blocked by the Levels ≤ 500 rule)")
             for r in mts_no_buffer],
        ),
        "stock_above_green": block(
            BUFFER_COLS + [{"key": "excess_kg", "label": "Excess (kg)", "numeric": True}],
            sorted([dict(line(r, (stock(r) - gl(r)) * rate(r)),
                         excess_kg=round(stock(r) - gl(r), 2)) for r in overstock],
                   key=lambda x: x["excess_kg"], reverse=True),
        ),
    }

    return finalise(tiles, tile_rows)
