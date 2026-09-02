"""Control 1 — "Is it already on order?"

Spec §Control 1. Nets each requirement line against what is already open with
the supplier and returns one of five verdicts, plus an OVERDUE COVER overlay.

Two rules from the spec drive everything here and are easy to get wrong:

* Coverage is counted from LIVE pending only. An overdue purchase order is
  reported loudly and nets off nothing — "an order that was due three weeks
  ago and has not arrived is not protection, it is a chase item".
* Where one Item Code sits on several requirement rows, the pending quantity
  is allocated PRO-RATA to requirement, never copied to both. Otherwise one
  PO covering 1,000 kg appears to cover two separate 1,000 kg requirements.

Input comes from combined!AQ:AX (see docs/po-integration/), which joins the
`po` tab on Item Code with Item Name as fallback. If those columns are not
present yet, the control says so on its own board rather than reporting a
confident "nothing is on order".
"""

from purchase_dashboards.drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_LEAD, C_RATE, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, C_TOORDER, C_VALUE,
    block, finalise, with_fields,
)
from purchase_dashboards.field_map import num, rupees_in, txt

CONTROL_KEY = "c1"
TITLE = "Control 1 — Is it already on order?"
JCPL_WORDING = (
    "Column X says we need this item. Now look at the open PO list. Is this "
    "same item already ordered and not yet delivered?"
)

# Spec §4: tolerance proposed at 5% of R (Open Question 1 — not yet closed).
TOLERANCE = 0.05

PLACEHOLDERS = {"item code required", "tbd", "n/a", "na"}

LINE_COLS = [
    C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_TOORDER, C_RATE, C_VALUE,
    C_STOCK, C_DAILY, C_COVER, C_LEAD,
    {"key": "po_live", "label": "On order (live)", "numeric": True},
    {"key": "po_overdue", "label": "Overdue", "numeric": True},
    {"key": "po_earliest_due", "label": "Promised"},
    {"key": "po_days_late", "label": "Days late", "numeric": True},
    {"key": "balance_to_raise", "label": "Still to raise", "numeric": True},
    {"key": "po_numbers", "label": "PO number(s)"},
    {"key": "po_vendors", "label": "Vendor(s)"},
    {"key": "verdict", "label": "Verdict", "pill": "verdict"},
    {"key": "action", "label": "Action"},
]

ACTIONS = {
    "NOT ON ORDER":    "Raise PO for the full requirement",
    "PARTLY COVERED":  "Raise PO for the balance only",
    "ALREADY COVERED": "Do not raise — chase the existing PO",
    "OVER-ORDERED":    "Investigate — a duplicate PO may already exist",
    "UNVERIFIABLE":    "Cannot be checked — fix the item master",
}


def _has_real_code(v):
    s = txt(v)
    return bool(s) and s != "0" and s.lower() not in PLACEHOLDERS


def compute(rows):
    n = len(rows)

    def d(r): return r["data"]
    def order_qty(r): return num(d(r).get("to_be_ordered_qty")) or 0
    def rate(r): return num(d(r).get("rate")) or 0

    to_order = [r for r in rows if order_qty(r) > 0]

    # --- is the PO feed actually present? --------------------------------
    # Spec §Non-negotiables: "unchecked is not the same as passed". If the
    # combined tab carries no PO columns at all we must not report a
    # confident "nothing on order" for every line.
    feed_present = any(
        txt(d(r).get("po_match_on")) or num(d(r).get("po_pending_live")) is not None
        or num(d(r).get("po_pending_overdue")) is not None
        for r in rows
    )

    # --- pro-rata allocation across duplicated match keys ---------------
    # Group the requirement rows by whatever key actually matched a PO, then
    # split that item's pending quantity in proportion to each row's need.
    demand_by_key = {}
    for r in to_order:
        key = txt(d(r).get("po_match_on")) and (
            txt(d(r).get("tally_code")) if txt(d(r).get("po_match_on")) == "Item Code"
            else txt(d(r).get("rm_code"))
        )
        if not key:
            continue
        demand_by_key[key] = demand_by_key.get(key, 0.0) + order_qty(r)

    def allocated(r, field):
        """This row's share of the item's pending quantity."""
        total_pending = num(d(r).get(field)) or 0
        if total_pending <= 0:
            return 0.0
        match = txt(d(r).get("po_match_on"))
        key = (txt(d(r).get("tally_code")) if match == "Item Code"
               else txt(d(r).get("rm_code")) if match else "")
        total_demand = demand_by_key.get(key, 0.0)
        if total_demand <= 0:
            return total_pending
        return total_pending * (order_qty(r) / total_demand)

    shared_keys = {k for k, _ in demand_by_key.items()
                   if sum(1 for r in to_order
                          if (txt(d(r).get("tally_code")) if txt(d(r).get("po_match_on")) == "Item Code"
                              else txt(d(r).get("rm_code"))) == k) > 1}

    def line(r):
        R = order_qty(r)
        live = allocated(r, "po_pending_live")
        over = allocated(r, "po_pending_overdue")
        tol = R * TOLERANCE

        if not _has_real_code(d(r).get("tally_code")) and not _has_real_code(d(r).get("rm_code")):
            verdict = "UNVERIFIABLE"
        elif not feed_present:
            # Spec §6: before the feed exists every line reads NOT ON ORDER
            # with the reason 'no PO source available' — never a blank.
            verdict = "NOT ON ORDER"
        elif live <= 0:
            verdict = "NOT ON ORDER"
        elif live < R - tol:
            verdict = "PARTLY COVERED"
        elif live <= R + tol:
            verdict = "ALREADY COVERED"
        else:
            verdict = "OVER-ORDERED"

        balance = max(0.0, R - live) if verdict in ("NOT ON ORDER", "PARTLY COVERED") else 0.0
        return dict(
            with_fields(r, "to_be_ordered_qty", "rate",
                       "current_stock_kg", "daily_consumption",
                       "current_stock_days", "lead_time_days"),
            value=R * rate(r),
            po_live=round(live, 2),
            po_overdue=round(over, 2),
            po_earliest_due=txt(d(r).get("po_earliest_due")),
            po_days_late=num(d(r).get("po_days_late")),
            po_numbers=txt(d(r).get("po_numbers")),
            po_vendors=txt(d(r).get("po_vendors")),
            balance_to_raise=round(balance, 2),
            verdict=verdict,
            action=("no PO source available" if not feed_present
                    else ACTIONS.get(verdict, "")),
            shared_key=bool(
                (txt(d(r).get("tally_code")) if txt(d(r).get("po_match_on")) == "Item Code"
                 else txt(d(r).get("rm_code"))) in shared_keys),
        )

    lines = [line(r) for r in to_order]

    def by(v): return [x for x in lines if x["verdict"] == v]
    not_on = by("NOT ON ORDER")
    partly = by("PARTLY COVERED")
    covered = by("ALREADY COVERED")
    over_ord = by("OVER-ORDERED")
    unver = by("UNVERIFIABLE")
    overdue_overlay = [x for x in lines if (x["po_overdue"] or 0) > 0]
    shared = [x for x in lines if x["shared_key"]]

    total_value = sum(x["value"] for x in lines)
    bucket_sum = sum(sum(x["value"] for x in b)
                     for b in (not_on, partly, covered, over_ord, unver))
    reconciles = abs(total_value - bucket_sum) < 0.01
    balance_total = sum(x["balance_to_raise"] for x in lines)

    tiles = {
        "feed_status": {
            "label": "PO feed status",
            "value": "CONNECTED" if feed_present else "NOT CONNECTED",
            "sub": ("Reading PO Pending Live / Overdue from the combined tab, joined on "
                    "Item Code with Item Name as fallback."
                    if feed_present else
                    "combined!AQ:AX carry no PO data yet — every line below reads NOT ON "
                    "ORDER with the reason 'no PO source available'. That is the spec's "
                    "required behaviour, NOT a verified result."),
            "kind": "score" if feed_present else "critical",
        },
        "requirement_population": {
            "label": "Requirement lines entering this control",
            "value": len(to_order),
            "sub": f"of {n} rows  ·  same population as Controls 2, 3 and 4",
            "kind": "info",
            "brief_target": 57,
        },
        "not_on_order": {
            "label": "NOT ON ORDER",
            "value": len(not_on),
            "sub": "Nothing live is covering this requirement — raise the PO",
            "kind": "critical",
        },
        "partly_covered": {
            "label": "PARTLY COVERED",
            "value": len(partly),
            "sub": f"Live cover falls short — {rupees_in(balance_total)} of balance still to raise",
            "kind": "warn",
        },
        "already_covered": {
            "label": "ALREADY COVERED",
            "value": len(covered),
            "sub": f"Live pending matches the requirement within {int(TOLERANCE*100)}% — do not raise again",
            "kind": "score",
        },
        "over_ordered": {
            "label": "OVER-ORDERED",
            "value": len(over_ord),
            "sub": "Live pending exceeds the requirement — a duplicate PO may already exist",
            "kind": "critical",
        },
        "overdue_cover": {
            "label": "OVERDUE COVER (overlay)",
            "value": len(overdue_overlay),
            "sub": "Material is on order but already past its promised date. It suppresses "
                   "nothing — this is the chase list.",
            "kind": "critical",
        },
        "unverifiable": {
            "label": "UNVERIFIABLE",
            "value": len(unver),
            "sub": "No usable item code, so no join is possible — master-data fix (Control 6)",
            "kind": "warn",
            "brief_target": 0,
        },
        "value_reconciliation": {
            "label": "Value reconciliation",
            "value": rupees_in(total_value),
            "sub": (f"Verdict buckets sum to {rupees_in(bucket_sum)} — "
                    + ("they reconcile exactly, which is the spec's own test."
                       if reconciles else
                       "THEY DO NOT RECONCILE — every rupee must land in exactly one bucket.")),
            "kind": "score" if reconciles else "critical",
            "indicative": True,
        },
        "shared_codes": {
            "label": "Lines sharing an item code",
            "value": len(shared),
            "sub": "Pending quantity is split PRO-RATA across these, never copied to both — "
                   "otherwise one PO would appear to cover two separate requirements",
            "kind": "info",
        },
        "notes": {
            "label": "Open questions & hazards",
            "value": "3 items",
            "sub": (
                "① Every PO line in the source reads status 'Approved' — there is no Closed, "
                "Cancelled or Short-closed value anywhere, so a cancelled PO CANNOT be detected. "
                "The spec is explicit that one must never suppress a live requirement. "
                "② Open Q1: is 5% the right tolerance, or should coverage be exact? "
                "③ Open Q2: should a PO count as overdue the day after its due date, or "
                "after a grace period? Today there is no grace."
            ),
            "kind": "info",
        },
    }

    def srt(b): return sorted(b, key=lambda x: x["value"], reverse=True)
    tile_rows = {
        "requirement_population": block(LINE_COLS, srt(lines)),
        "not_on_order": block(LINE_COLS, srt(not_on)),
        "partly_covered": block(LINE_COLS, srt(partly)),
        "already_covered": block(LINE_COLS, srt(covered)),
        "over_ordered": block(LINE_COLS, srt(over_ord)),
        "overdue_cover": block(LINE_COLS, sorted(
            overdue_overlay, key=lambda x: (x["po_days_late"] or 0), reverse=True)),
        "unverifiable": block(LINE_COLS, unver),
        "value_reconciliation": block(LINE_COLS, srt(lines)),
        "shared_codes": block(LINE_COLS, srt(shared)),
        # feed_status / notes are static — no row list.
    }
    return finalise(tiles, tile_rows)
