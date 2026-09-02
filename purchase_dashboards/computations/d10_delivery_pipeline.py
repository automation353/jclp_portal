"""Dashboard 10 — Delivery Pipeline Board.

Brief §Dashboard 10. Every material that already has a purchase order
placed, regardless of whether a delivery date is known. The board
separates rows where a due date exists from rows where material is on
order but no date is promised — that second group is the action list.

Change #13 from the 27 Aug review: "New tab — items WITH delivery date."
"""

from datetime import date, timedelta

from ..drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_GROUP, C_LEAD, C_RATE, C_RM, C_SPEC,
    C_SR, C_STOCK, C_TALLY, C_TOORDER, C_VALUE, add_inventory, block,
    finalise, with_fields,
)
from ..field_map import num, rupees_in, txt


DASHBOARD_KEY = "d10"
TITLE = "Delivery Pipeline"


def _parse_date(val):
    """Parse a date that might be ISO string or Excel serial number."""
    if not val or not str(val).strip():
        return None
    val = str(val).strip()
    try:
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        pass
    try:
        serial = int(float(val))
        if 40000 < serial < 60000:
            return date(1899, 12, 30) + timedelta(days=serial)
    except (ValueError, TypeError):
        pass
    return None


PO_COLS = [
    C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP, C_STOCK, C_DAILY,
    C_COVER, C_LEAD,
    {"key": "po_numbers",          "label": "PO numbers"},
    {"key": "po_vendors",          "label": "Vendor(s)"},
    {"key": "po_pending_live",     "label": "PO live (kg)",    "numeric": True},
    {"key": "po_pending_overdue",  "label": "PO overdue (kg)", "numeric": True},
    {"key": "po_received",         "label": "Received (kg)",   "numeric": True},
    {"key": "po_earliest_due",     "label": "Earliest due"},
    {"key": "po_days_late",        "label": "Days late",       "numeric": True},
    C_TOORDER, C_RATE, C_VALUE,
]


def compute(rows):
    today = date.today()

    def d(r):
        return r["data"]

    def po_nums(r):
        return (d(r).get("po_numbers") or "").strip()

    def po_line(r):
        data = d(r)
        return dict(
            with_fields(r, "current_stock_kg", "daily_consumption",
                        "current_stock_days", "lead_time_days",
                        "to_be_ordered_qty", "rate"),
            po_numbers=txt(data.get("po_numbers")),
            po_vendors=txt(data.get("po_vendors")),
            po_pending_live=num(data.get("po_pending_live")) or 0,
            po_pending_overdue=num(data.get("po_pending_overdue")) or 0,
            po_received=num(data.get("po_received")) or 0,
            po_earliest_due=txt(data.get("po_earliest_due")),
            po_days_late=num(data.get("po_days_late")) or 0,
            value=(num(data.get("to_be_ordered_qty")) or 0) * (num(data.get("rate")) or 0),
        )

    # ── Main split: rows that have a PO vs those that don't ─────────────
    on_order = [r for r in rows if po_nums(r)]
    no_po    = [r for r in rows
                if not po_nums(r) and (num(d(r).get("to_be_ordered_qty")) or 0) > 0]

    # Sub-split on_order: dated vs undated
    dated   = []
    undated = []
    overdue = []
    for r in on_order:
        due = _parse_date(d(r).get("po_earliest_due"))
        late = num(d(r).get("po_days_late")) or 0
        po_overdue_kg = num(d(r).get("po_pending_overdue")) or 0

        if due:
            dated.append(r)
            if due < today:
                overdue.append(r)
        elif po_overdue_kg > 0:
            # No explicit date but overdue qty exists → overdue
            overdue.append(r)
            undated.append(r)
        else:
            undated.append(r)

    total_on_order_val = sum(
        (num(d(r).get("po_pending_live")) or 0)
        * (num(d(r).get("rate")) or 0)
        for r in on_order
    )
    total_overdue_val = sum(
        (num(d(r).get("po_pending_overdue")) or 0)
        * (num(d(r).get("rate")) or 0)
        for r in on_order
    )

    tiles = {
        "on_order": {
            "label": "Material already on order",
            "value": len(on_order),
            "sub": f"of {len(rows)} total  ·  PO value {rupees_in(total_on_order_val)}",
            "kind": "info",
        },
        "dated": {
            "label": "Delivery date known",
            "value": len(dated),
            "sub": f"of {len(on_order)} on order  ·  due date in the sheet",
            "kind": "score" if dated else "warn",
        },
        "undated": {
            "label": "On order — no delivery date",
            "value": len(undated),
            "sub": "PO raised but no due date recorded — follow up with vendor",
            "kind": "critical" if undated else "info",
        },
        "overdue": {
            "label": "Delivery overdue",
            "value": len(overdue),
            "sub": f"Overdue value {rupees_in(total_overdue_val)}",
            "kind": "critical" if overdue else "info",
        },
        "no_po_needs_order": {
            "label": "Needs order — no PO yet",
            "value": len(no_po),
            "sub": "To-be-ordered qty > 0 but no PO number on record",
            "kind": "critical" if no_po else "info",
        },
    }

    tile_rows = {
        "on_order": block(
            PO_COLS,
            sorted([po_line(r) for r in on_order],
                   key=lambda x: x["po_days_late"], reverse=True),
        ),
        "dated": block(
            PO_COLS,
            sorted([po_line(r) for r in dated],
                   key=lambda x: x["po_earliest_due"] or ""),
        ),
        "undated": block(
            PO_COLS,
            sorted([po_line(r) for r in undated],
                   key=lambda x: x["po_days_late"], reverse=True),
        ),
        "overdue": block(
            PO_COLS,
            sorted([po_line(r) for r in overdue],
                   key=lambda x: x["po_days_late"], reverse=True),
        ),
        "no_po_needs_order": block(
            [C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP,
             C_STOCK, C_DAILY, C_COVER, C_LEAD, C_TOORDER, C_RATE, C_VALUE],
            sorted([dict(with_fields(r, "current_stock_kg", "daily_consumption",
                                     "current_stock_days", "lead_time_days",
                                     "to_be_ordered_qty", "rate"),
                         value=(num(d(r).get("to_be_ordered_qty")) or 0)
                               * (num(d(r).get("rate")) or 0))
                    for r in no_po],
                   key=lambda x: x["value"], reverse=True),
        ),
    }

    return finalise(tiles, tile_rows)
