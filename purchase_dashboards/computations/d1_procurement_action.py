"""Dashboard 1 — Procurement Action Board.

Brief §Dashboard 1. Six headline counters, each drilling to its own row
list. The "items needing order" tile carries the full action queue with
STOCK-OUT / CRITICAL / WATCH status and a suggested action per line.
"""

from ..drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_GROUP, C_LEAD, C_RATE, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, C_TOORDER, C_VALUE, IDENTITY_COLS, add_inventory,
    base_row, block, finalise, with_fields,
)
from ..field_map import is_present_code, num, rupees_in, txt


DASHBOARD_KEY = "d1"
TITLE = "Procurement Action Board"


def _status(d):
    cs, csd, ltd = (num(d.get("current_stock_kg")),
                    num(d.get("current_stock_days")),
                    num(d.get("lead_time_days")))
    if cs is not None and cs == 0:
        return "STOCK-OUT"
    if csd is not None and ltd is not None and ltd > 0 and csd < ltd:
        return "CRITICAL"
    return "WATCH"


SUGGESTED = {
    "STOCK-OUT": "Emergency PO or substitute — check WIP first",
    "CRITICAL":  "Raise PO today; confirm lead time with vendor",
    "WATCH":     "Include in next weekly PO cycle",
    "COVERED":   "PO already placed — track delivery, no new order needed",
}

QUEUE_COLS = [
    C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_STOCK, C_DAILY, C_COVER, C_LEAD,
    {"key": "lead_warning", "label": "Lead > Stock?", "pill": True},
    C_TOORDER,
    {"key": "open_po", "label": "Open PO (kg)", "numeric": True},
    {"key": "net_order", "label": "Net order (kg)", "numeric": True},
    C_VALUE,
    {"key": "status", "label": "Status", "pill": True},
    {"key": "suggested_action", "label": "Suggested action"},
    {"key": "owner", "label": "Owner"},
]


def compute(rows):
    n = len(rows)
    to_order = [r for r in rows if (num(r["data"].get("to_be_ordered_qty")) or 0) > 0]

    def order_value(r):
        d = r["data"]
        return (num(d.get("to_be_ordered_qty")) or 0) * (num(d.get("rate")) or 0)

    # --- action queue (the ITEMS NEEDING ORDER drill) -----------------------
    # #2: net off open POs — order = requirement - open_po (floor at 0)
    # When net_order = 0 the open PO already covers the full requirement,
    # so status becomes COVERED and the item moves out of the action queue
    # into its own "covered_by_po" bucket.
    queue = []
    covered = []
    for r in to_order:
        d = r["data"]
        ltd = num(d.get("lead_time_days")) or 0
        csd = num(d.get("current_stock_days")) or 0
        toq = num(d.get("to_be_ordered_qty")) or 0
        open_po = num(d.get("po_pending_live")) or 0
        net = max(0, toq - open_po)

        # If open PO fully covers the requirement, no new order needed
        if net == 0 and open_po > 0:
            st = "COVERED"
        else:
            st = _status(d)

        row = dict(
            with_fields(r, "current_stock_kg", "daily_consumption",
                        "current_stock_days", "lead_time_days",
                        "to_be_ordered_qty", "rate"),
            open_po=round(open_po, 2),
            net_order=round(net, 2),
            value=net * (num(d.get("rate")) or 0),   # value uses net, not gross
            lead_warning="YES" if ltd > csd else "",
            status=st,
            suggested_action=SUGGESTED[st],
            owner="",
        )
        if st == "COVERED":
            covered.append(row)
        else:
            queue.append(row)

    queue.sort(key=lambda x: (x["current_stock_days"]
                              if x["current_stock_days"] is not None else 10**9))
    covered.sort(key=lambda x: x.get("open_po") or 0, reverse=True)

    # Headline values now use the net (after PO) amounts from the action queue
    order_value_all = sum(q["value"] for q in queue)
    order_value_coded = sum(q["value"] for q in queue
                            if is_present_code(q.get("rm_code")))

    # --- BELOW RED LEVEL (includes hard stock-outs) -------------------------
    # #3: Harsh/Rajeev 27-Aug-2026 — merge "Hard Stock Out" into this tile.
    # A row qualifies when:
    #   a) it has a red level > 0 AND stock < red level   (classic BRL)
    #   b) stock == 0 AND it needs ordering               (hard stock-out)
    # Group (b) rows get red_level = 0 so the drill table stays consistent.
    below_red = []
    below_red_srs = set()           # track sr_no to avoid double-counting
    for r in rows:
        d = r["data"]
        cs = num(d.get("current_stock_kg"))
        rl = num(d.get("red_level"))

        # (a) Classic below-red-level
        if rl is not None and rl > 0 and cs is not None and cs < rl:
            below_red.append(dict(
                with_fields(r, "current_stock_kg", "daily_consumption",
                            "current_stock_days", "lead_time_days",
                            "red_level", "yellow_level", "green_level"),
                shortfall=round(rl - cs, 2),
            ))
            below_red_srs.add(r["sr_no"])

    # (b) Hard stock-outs not already counted above
    for r in to_order:
        if r["sr_no"] in below_red_srs:
            continue
        if num(r["data"].get("current_stock_kg")) == 0:
            toq = num(r["data"].get("to_be_ordered_qty")) or 0
            below_red.append(dict(
                with_fields(r, "current_stock_kg", "daily_consumption",
                            "current_stock_days", "lead_time_days",
                            "red_level", "yellow_level", "green_level"),
                shortfall=round(toq, 2),   # entire requirement is the shortfall
            ))
    below_red.sort(key=lambda x: x["shortfall"], reverse=True)

    hard_stockout_count = sum(
        1 for r in to_order if num(r["data"].get("current_stock_kg")) == 0
    )

    # --- NO DELIVERY DATE (within the requirement population) --------------
    no_delivery = [
        dict(with_fields(r, "to_be_ordered_qty", "current_stock_kg",
                        "daily_consumption", "current_stock_days",
                        "lead_time_days"),
             value=order_value(r))
        for r in to_order if not txt(r["data"].get("expected_arrival"))
    ]

    tiles = {
        "items_needing_order": {
            "label": "Material to be purchased",
            "value": len(queue),
            "sub": (
                f"{len(queue)} need a new PO  ·  "
                f"{len(covered)} already covered by open PO"
            ),
            "kind": "critical",
        },
        "order_value_at_stake": {
            "label": "Money needed to buy material",
            "value": rupees_in(order_value_all),
            "sub": f"including uncoded rows  ·  coded only: {rupees_in(order_value_coded)}  ·  Rate = avg from TCS iON stock statement",
            "kind": "warn",
            "indicative": True,
        },
        "covered_by_po": {
            "label": "Already covered by open PO",
            "value": len(covered),
            "sub": "Requirement fully met by existing purchase order — no new PO needed, track delivery",
            "kind": "score" if covered else "info",
        },
        "below_red_level": {
            "label": "Stock below safety level (red level)",
            "value": len(below_red),
            "sub": f"Including {hard_stockout_count} hard stock-out(s) at zero stock",
            "kind": "critical",
        },
        "no_delivery_date": {
            "label": "Delivery date not known",
            "value": len(no_delivery),
            "sub": f"of {len(to_order)} needing order  ·  Expected Arrival is blank",
            "kind": "critical",
        },
    }

    tile_rows = {
        "items_needing_order": block(QUEUE_COLS, queue),
        "covered_by_po": block(QUEUE_COLS, covered),
        "order_value_at_stake": block(
            add_inventory([C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_TOORDER, C_RATE, C_VALUE]),
            sorted(queue, key=lambda x: x["value"], reverse=True),
        ),
        "below_red_level": block(
            add_inventory([C_SR, C_TALLY, C_RM, C_SPEC, C_STOCK,
             {"key": "red_level",    "label": "Red level",    "numeric": True},
             {"key": "yellow_level", "label": "Yellow level", "numeric": True},
             {"key": "green_level",  "label": "Green level",  "numeric": True},
             {"key": "shortfall",    "label": "Shortfall (kg)", "numeric": True}]),
            below_red,
        ),
        "no_delivery_date": block(
            add_inventory(IDENTITY_COLS + [C_TOORDER, C_STOCK, C_LEAD, C_VALUE]),
            no_delivery,
        ),
    }

    return finalise(tiles, tile_rows)
