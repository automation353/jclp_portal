"""Dashboard 9 — Signal Conflict Board.

Brief §Dashboard 9. Every place where two live columns give contradictory
instructions about the same item. Never resolve a conflict here — every
drill row shows BOTH values side by side so the reader chooses.
"""

from ..drill import (
    C_COVER, C_COVBAND, C_DAILY, C_LEAD, C_MPS, C_REORDER, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, C_TILLDATE, C_TOORDER, IDENTITY_COLS, add_inventory,
    base_row, block, finalise, inv_fields, with_fields,
)
from ..field_map import num, txt


DASHBOARD_KEY = "d9"
TITLE = "Signal Conflict"


def compute(rows):
    n = len(rows)

    # --- TWO ORDER QUANTITIES DISAGREE -------------------------------------
    disagree = []
    for r in rows:
        d = r["data"]
        rq, toq = num(d.get("reorder_qty")), num(d.get("to_be_ordered_qty"))
        if rq is None or toq is None or abs(rq - toq) <= 1:
            continue
        disagree.append(dict(
            base_row(r), **inv_fields(r), reorder_qty=rq,
            to_be_ordered_qty=toq, diff=round(toq - rq, 2),
        ))
    disagree.sort(key=lambda x: abs(x["diff"]), reverse=True)

    # --- BROKEN LEAD-TIME CONSUMPTION --------------------------------------
    broken_ltc = []
    for r in rows:
        d = r["data"]
        ltc, dc = num(d.get("lead_time_consumption")), num(d.get("daily_consumption"))
        if not ((ltc in (None, 0)) and dc is not None and dc > 0):
            continue
        ltd = num(d.get("lead_time_days")) or 0
        _row = dict(base_row(r), **inv_fields(r))
        _row.update(daily_consumption=dc, lead_time_days=ltd,
                    imported_ltc=0, computed_ltc=round(dc * ltd, 2))
        broken_ltc.append(_row)

    # --- HIGH INVENTORY BUT SHORT COVER ------------------------------------
    high_short = [
        with_fields(r, "current_stock_kg", "daily_consumption",
                    "current_stock_days", "lead_time_days",
                    "till_date_inventory", "inventory_coverage")
        for r in rows
        if txt(r["data"].get("till_date_inventory")).upper() == "HIGH INVENTORY"
        and txt(r["data"].get("inventory_coverage")) == "0 to 15"
    ]

    # --- ORDERING A DEAD ITEM ----------------------------------------------
    ordering_dead = [
        with_fields(r, "to_be_ordered_qty", "current_stock_kg",
                    "daily_consumption", "current_stock_days", "lead_time_days")
        for r in rows
        if (num(r["data"].get("to_be_ordered_qty")) or 0) > 0
        and txt(r["data"].get("category")) in ("Non Moving", "Slow Moving")
    ]

    # --- ORDERING WITHOUT DEMAND -------------------------------------------
    ordering_no_demand = [
        with_fields(r, "to_be_ordered_qty", "mps_demand", "current_stock_kg",
                    "daily_consumption", "current_stock_days", "lead_time_days")
        for r in rows
        if (num(r["data"].get("to_be_ordered_qty")) or 0) > 0
        and num(r["data"].get("mps_demand")) in (None, 0)
    ]

    # --- RAG SUPPRESSED -----------------------------------------------------
    rag_suppressed = []
    for r in rows:
        d = r["data"]
        cs, rl, yl = (num(d.get("current_stock_kg")), num(d.get("red_level")),
                      num(d.get("yellow_level")))
        if not (cs is not None and rl is not None and rl > 0 and cs < rl
                and yl is not None and yl < 500):
            continue
        _rrow = dict(base_row(r), **inv_fields(r))
        _rrow.update(current_stock_kg=cs, red_level=rl, yellow_level=yl,
                     note="excluded by the sheet's RL Count because Yellow < 500")
        rag_suppressed.append(_rrow)

    tiles = {
        "two_order_qty_disagree": {
            "label": "Two order quantities disagree",
            "value": len(disagree),
            "sub": "Reorder Qty vs To be ordered Qty differ by >1 kg",
            "kind": "critical",
            "explain": "The buyer could order either value; the sheet does not say which. See Decision 9.",
        },
        "broken_ltc": {
            "label": "Broken lead-time consumption",
            "value": len(broken_ltc),
            "sub": "Lead Time Consumption is 0 while Daily Consumption > 0",
            "kind": "warn",
            "explain": "Silently drops the Reorder Qty to zero on these lines. See Decision 4.",
        },
        "high_but_short": {
            "label": "High inventory but short cover",
            "value": len(high_short),
            "sub": "'HIGH INVENTORY' text AND '0 to 15' band on the same row",
            "kind": "warn",
        },
        "ordering_dead": {
            "label": "Ordering a dead item",
            "value": len(ordering_dead),
            "sub": "Requirement raised on Non-Moving or Slow-Moving material",
            "kind": "warn",
        },
        "ordering_no_demand": {
            "label": "Ordering without demand",
            "value": len(ordering_no_demand),
            "sub": "Requirement > 0 but MPS Demand = 0",
            "kind": "info",
        },
        "rag_suppressed": {
            "label": "RAG suppressed by the 500 rule",
            "value": len(rag_suppressed),
            "sub": "Genuine red-band breaches the sheet's RL Count hides",
            "kind": "warn",
            "explain": "See Decision 3.",
        },
    }

    tile_rows = {
        "two_order_qty_disagree": block(
            add_inventory([C_SR, C_TALLY, C_RM, C_SPEC, C_REORDER, C_TOORDER,
             {"key": "diff", "label": "Difference", "numeric": True}]),
            disagree,
        ),
        "broken_ltc": block(
            add_inventory([C_SR, C_TALLY, C_RM, C_SPEC, C_DAILY, C_LEAD,
             {"key": "imported_ltc", "label": "Imported LTC", "numeric": True},
             {"key": "computed_ltc", "label": "Computed LTC", "numeric": True}]),
            broken_ltc,
        ),
        "high_but_short": block(
            add_inventory([C_SR, C_TALLY, C_RM, C_SPEC, C_TILLDATE, C_COVBAND, C_STOCK, C_DAILY]),
            high_short,
        ),
        "ordering_dead": block(
            add_inventory(IDENTITY_COLS + [C_TOORDER, C_STOCK]),
            ordering_dead,
        ),
        "ordering_no_demand": block(
            add_inventory(IDENTITY_COLS + [C_TOORDER, C_MPS, C_STOCK]),
            ordering_no_demand,
        ),
        "rag_suppressed": block(
            add_inventory([C_SR, C_TALLY, C_RM, C_SPEC, C_STOCK,
             {"key": "red_level", "label": "Red level", "numeric": True},
             {"key": "yellow_level", "label": "Yellow level", "numeric": True},
             {"key": "note", "label": "Why hidden"}]),
            rag_suppressed,
        ),
    }

    return finalise(tiles, tile_rows)
