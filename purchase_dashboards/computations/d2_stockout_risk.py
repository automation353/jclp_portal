"""Dashboard 2 — Stock-Out & Cover Risk Board.

Brief §Dashboard 2. Lines whose cover is shorter than lead time will stop
production even if a PO goes out today. The measurable-lines tile is the
honest denominator and drills to exactly which rows this board can speak
about.
"""

from ..drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_LEAD, C_RATE, C_RM, C_SPEC, C_SR, C_STOCK,
    C_TALLY, C_TOORDER, C_VALUE, add_inventory, base_row, block, finalise,
    with_fields,
)
from ..field_map import num, rupees_in


DASHBOARD_KEY = "d2"
TITLE = "Stock-Out & Cover Risk"

GAP_COLS = [C_SR, C_TALLY, C_RM, C_SPEC, C_STOCK, C_DAILY, C_COVER, C_LEAD,
            {"key": "gap", "label": "Gap (days)", "numeric": True},
            C_CATEGORY, C_TOORDER]


def compute(rows):
    n = len(rows)

    # The measurable population — both a lead time AND a consumption rate.
    measurable = []
    for r in rows:
        d = r["data"]
        ltd, dc, csd = (num(d.get("lead_time_days")), num(d.get("daily_consumption")),
                        num(d.get("current_stock_days")))
        if ltd is not None and ltd > 0 and dc is not None and dc > 0:
            measurable.append({"row": r, "ltd": ltd, "dc": dc, "csd": csd})

    def gap_row(m):
        r, ltd, csd = m["row"], m["ltd"], m["csd"]
        return dict(
            with_fields(r, "current_stock_days", "lead_time_days",
                        "to_be_ordered_qty", "daily_consumption", "current_stock_kg",
                        "rate"),
            gap=round(ltd - (csd if csd is not None else 0), 2),
        )

    cover_short = [m for m in measurable if m["csd"] is not None and m["csd"] < m["ltd"]]
    severe      = [m for m in cover_short if m["csd"] < m["ltd"] / 2]
    def value_of(m):
        d = m["row"]["data"]
        return (num(d.get("to_be_ordered_qty")) or 0) * (num(d.get("rate")) or 0)

    value_exposed = sum(value_of(m) for m in cover_short)

    cover_short_rows = sorted([gap_row(m) for m in cover_short],
                              key=lambda x: x["gap"], reverse=True)

    tiles = {
        "cover_short": {
            "label": "Stock will finish before material comes",
            "value": len(cover_short),
            "sub": f"of {len(measurable)} measurable  ·  will run out before material arrives",
            "kind": "critical",
        },
        "severely_exposed": {
            "label": "Too late even if ordered today",
            "value": len(severe),
            "sub": "Less than half the lead time is covered — expediting won't save these",
            "kind": "critical",
        },
        "value_exposed": {
            "label": "Money needed to cover shortage",
            "value": rupees_in(value_exposed),
            "sub": "To be ordered × Rate across cover-short rows",
            "kind": "warn",
            "indicative": True,
        },
        "lines_measurable": {
            "label": "Material we can check (rest no data available)",
            "value": f"{len(measurable)} of {n}",
            "sub": "Only these carry BOTH a lead time and a daily consumption — this board is silent about the rest",
            "kind": "info",
        },
    }

    tile_rows = {
        "cover_short":      block(GAP_COLS, cover_short_rows),
        "severely_exposed": block(GAP_COLS, sorted([gap_row(m) for m in severe],
                                                   key=lambda x: x["gap"], reverse=True)),
        "value_exposed":    block(
            add_inventory([C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_TOORDER, C_RATE, C_VALUE]),
            sorted([dict(gap_row(m), value=value_of(m)) for m in cover_short],
                   key=lambda x: x["value"], reverse=True),
        ),
        "lines_measurable": block(
            [C_SR, C_TALLY, C_RM, C_SPEC, C_LEAD, C_DAILY, C_COVER, C_STOCK],
            [gap_row(m) for m in measurable],
        ),
    }

    return finalise(tiles, tile_rows)
