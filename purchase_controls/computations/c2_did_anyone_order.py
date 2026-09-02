"""Control 2 — "We need it, but did anyone actually order it?"

Spec §Control 2. Control 1 asks whether an order already exists so JCPL does
not buy twice. This one asks the opposite question: the requirement is real
and nobody disputed it — has anyone actually raised the order? Control 1
prevents waste; Control 2 prevents a stoppage.

It also puts a CLOCK on every unactioned requirement. "A requirement three
days old is a queue; the same requirement thirty days old is a failure, and
only a clock distinguishes them." That clock is the RequirementAge register
(see ../age_register.py) — it did not exist anywhere in JCPL before.

Two spec hazards are handled explicitly:

* The register never resets. first_seen is written once; a requirement that
  lapses for a day and returns keeps its original date.
* A blank [Expected Arrival date] is NOT evidence. It is blank on all 392
  rows and proves only that nobody typed in it. Every verdict here comes
  from the PO join, never from that column.
"""

from purchase_dashboards.drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_LEAD, C_RATE, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, C_TOORDER, C_VALUE,
    block, finalise, with_fields,
)
from purchase_dashboards.field_map import num, rupees_in, txt

CONTROL_KEY = "c2"
TITLE = "Control 2 — Did anyone actually order it?"
JCPL_WORDING = (
    "Column X says we need this item. Now check: is there a PO? Is there a "
    "delivery date in column Z?"
)

# Spec §Open Question 5: 2 days / 7 days are PROPOSED, not given.
QUEUE_DAYS = 2
UNACTIONED_DAYS = 7
TOLERANCE = 0.05

LINE_COLS = [
    C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_TOORDER, C_STOCK, C_DAILY, C_COVER, C_LEAD, C_RATE, C_VALUE,
    {"key": "first_seen", "label": "First seen"},
    {"key": "age_days", "label": "Age (days)", "numeric": True},
    {"key": "po_outstanding", "label": "Outstanding on PO", "numeric": True},
    {"key": "po_earliest_due", "label": "Promised"},
    {"key": "po_numbers", "label": "PO number(s)"},
    {"key": "verdict", "label": "Verdict", "pill": "verdict"},
    {"key": "action", "label": "Action"},
]

ACTIONS = {
    "NEW — IN QUEUE":         "No action — normal working time",
    "UNACTIONED":             "Buyer to raise, or record a reason",
    "OVERDUE ACTION":         "Escalate to plant head — nobody has picked this up",
    "CRITICAL — TIME LOST":   "Delay now exceeds the supplier's own lead time",
    "ORDERED AND COMMITTED":  "Ordered with a date — write it back into Expected Arrival",
    "ORDERED, NO COMMITMENT": "PO raised but no date from the vendor — chase for one",
    "PART ORDERED":           "Balance is still unactioned — treat it as a fresh requirement",
}


def compute(rows, meta=None):
    n = len(rows)
    meta = meta or {}

    def d(r): return r["data"]
    def order_qty(r): return num(d(r).get("to_be_ordered_qty")) or 0
    def rate(r): return num(d(r).get("rate")) or 0

    to_order = [r for r in rows if order_qty(r) > 0]

    register_days = meta.get("register_age_days", 0)
    # Spec §6: on the first run every requirement stamps as new, so ages
    # only become meaningful from the second week onward. Say so, loudly.
    ages_meaningful = register_days >= 7

    def line(r):
        R = order_qty(r)
        L = num(d(r).get("lead_time_days")) or 0
        age = num(d(r).get("requirement_age_days"))
        matched = bool(txt(d(r).get("po_match_on")))
        live = num(d(r).get("po_pending_live")) or 0
        over = num(d(r).get("po_pending_overdue")) or 0
        outstanding = live + over
        # A promised date exists if the PO carries one at all — either still
        # live (po_earliest_due) or already passed (po_days_late).
        has_date = bool(txt(d(r).get("po_earliest_due"))) or num(d(r).get("po_days_late")) is not None

        if matched:
            if outstanding < R * (1 - TOLERANCE):
                verdict = "PART ORDERED"
            elif has_date:
                verdict = "ORDERED AND COMMITTED"
            else:
                verdict = "ORDERED, NO COMMITMENT"
        else:
            a = age if age is not None else 0
            if L > 0 and a > L:
                verdict = "CRITICAL — TIME LOST"
            elif a > UNACTIONED_DAYS:
                verdict = "OVERDUE ACTION"
            elif a > QUEUE_DAYS:
                verdict = "UNACTIONED"
            else:
                verdict = "NEW — IN QUEUE"

        return dict(
            with_fields(r, "to_be_ordered_qty", "lead_time_days", "rate",
                       "current_stock_kg", "daily_consumption",
                       "current_stock_days"),
            value=R * rate(r),
            first_seen=txt(d(r).get("requirement_first_seen")),
            age_days=age,
            po_outstanding=round(outstanding, 2),
            po_earliest_due=txt(d(r).get("po_earliest_due")),
            po_numbers=txt(d(r).get("po_numbers")),
            verdict=verdict,
            action=ACTIONS.get(verdict, ""),
        )

    lines = [line(r) for r in to_order]

    def by(*v): return [x for x in lines if x["verdict"] in v]
    ordered = by("ORDERED AND COMMITTED", "ORDERED, NO COMMITMENT", "PART ORDERED")
    unactioned_all = by("NEW — IN QUEUE", "UNACTIONED", "OVERDUE ACTION", "CRITICAL — TIME LOST")

    total_value = sum(x["value"] for x in lines)
    unactioned_value = sum(x["value"] for x in unactioned_all)
    reconciles = len(ordered) + len(unactioned_all) == len(to_order)

    tiles = {
        "register_status": {
            "label": "Requirement-age register",
            "value": f"{meta.get('register_size', 0)} items tracked",
            "sub": (
                f"Clock started {meta.get('register_started') or '—'} "
                f"({register_days} days ago)  ·  {meta.get('created_this_run', 0)} stamped this run. "
                + ("Ages are meaningful."
                   if ages_meaningful else
                   "WARNING: the register is less than a week old, so every age below is "
                   "capped by how long the register has existed — not by how long the "
                   "requirement has really been sitting. Ages become meaningful from the "
                   "second week onward.")
            ),
            "kind": "score" if ages_meaningful else "warn",
        },
        "requirement_population": {
            "label": "Requirement lines entering this control",
            "value": len(to_order),
            "sub": f"of {n} rows  ·  same population as Controls 1, 3 and 4",
            "kind": "info",
            "brief_target": 57,
        },
        "not_ordered": {
            "label": "NOT ordered at all",
            "value": len(unactioned_all),
            "sub": f"{rupees_in(unactioned_value)} of requirement with no purchase order behind it",
            "kind": "critical",
        },
        "new_in_queue": {
            "label": "NEW — IN QUEUE",
            "value": len(by("NEW — IN QUEUE")),
            "sub": f"Seen {QUEUE_DAYS} days ago or less — normal working time, no action",
            "kind": "info",
        },
        "unactioned": {
            "label": "UNACTIONED",
            "value": len(by("UNACTIONED")),
            "sub": f"{QUEUE_DAYS+1}–{UNACTIONED_DAYS} days old with no PO — buyer to raise or record a reason",
            "kind": "warn",
        },
        "overdue_action": {
            "label": "OVERDUE ACTION",
            "value": len(by("OVERDUE ACTION")),
            "sub": f"More than {UNACTIONED_DAYS} days old and still nobody has raised it — escalate",
            "kind": "critical",
        },
        "critical_time_lost": {
            "label": "CRITICAL — TIME LOST",
            "value": len(by("CRITICAL — TIME LOST")),
            "sub": "The delay now exceeds the supplier's own lead time. Stock-out is arithmetic, not risk.",
            "kind": "critical",
        },
        "ordered_committed": {
            "label": "ORDERED AND COMMITTED",
            "value": len(by("ORDERED AND COMMITTED")),
            "sub": "PO exists and carries a date — this is what should populate Expected Arrival date",
            "kind": "score",
        },
        "ordered_no_commitment": {
            "label": "ORDERED, NO COMMITMENT",
            "value": len(by("ORDERED, NO COMMITMENT")),
            "sub": "PO raised but the vendor has given no date — chase for one",
            "kind": "warn",
        },
        "part_ordered": {
            "label": "PART ORDERED",
            "value": len(by("PART ORDERED")),
            "sub": "Outstanding PO quantity is less than the requirement — the balance is still unactioned",
            "kind": "warn",
        },
        "reconciliation": {
            "label": "Population reconciliation",
            "value": f"{len(ordered)} + {len(unactioned_all)} = {len(to_order)}",
            "sub": ("Ordered plus unactioned equals the requirement population exactly — "
                    "the spec's own test."
                    if reconciles else
                    "DOES NOT RECONCILE — every line must land in exactly one verdict."),
            "kind": "score" if reconciles else "critical",
        },
        "notes": {
            "label": "Open questions & hazards",
            "value": "4 items",
            "sub": (
                "① [Expected Arrival date] is blank on all 392 rows. That proves only that "
                "nobody typed in it — every verdict here comes from the PO join, never from "
                "that column. "
                "② The register never resets: first_seen is written once and a requirement "
                "that lapses and returns keeps its original date. "
                "③ Open Q5: confirm the 2-day / 7-day / lead-time thresholds — they are "
                "proposed, not given. "
                "④ Open Q6: should the promised date be written back into [Expected Arrival "
                "date], or into a separate column so the original stays untouched?"
            ),
            "kind": "info",
        },
    }

    def srt(b): return sorted(b, key=lambda x: (x["age_days"] or 0), reverse=True)
    tile_rows = {
        "requirement_population": block(LINE_COLS, srt(lines)),
        "not_ordered": block(LINE_COLS, srt(unactioned_all)),
        "new_in_queue": block(LINE_COLS, srt(by("NEW — IN QUEUE"))),
        "unactioned": block(LINE_COLS, srt(by("UNACTIONED"))),
        "overdue_action": block(LINE_COLS, srt(by("OVERDUE ACTION"))),
        "critical_time_lost": block(LINE_COLS, srt(by("CRITICAL — TIME LOST"))),
        "ordered_committed": block(LINE_COLS, srt(by("ORDERED AND COMMITTED"))),
        "ordered_no_commitment": block(LINE_COLS, srt(by("ORDERED, NO COMMITMENT"))),
        "part_ordered": block(LINE_COLS, srt(by("PART ORDERED"))),
        # register_status / reconciliation / notes are static.
    }
    return finalise(tiles, tile_rows)
