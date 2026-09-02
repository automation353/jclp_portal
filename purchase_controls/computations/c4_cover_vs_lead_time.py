"""Control 4 — "Will we run out before the delivery arrives?"

Spec §Control 4. Buildable now from RM alone; sharper once the TCS iON PO
feed exists (that enhancement — PO-promised delivery date vs. projected
stock-out — is NOT CHECKABLE today; the feed does not exist, and this
control says so rather than staying silent about it).

Population: only rows carrying BOTH a lead time and a daily consumption
rate are "measurable" (spec §4). Every other row returns NOT ASSESSABLE —
this control is silent about them, and the board states that denominator.
"""

from purchase_dashboards.drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_LEAD, C_RATE, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, C_TOORDER, C_VALUE, add_inventory, block, finalise,
    with_fields,
)
from purchase_dashboards.field_map import num, rupees_in, txt

CONTROL_KEY = "c4"
TITLE = "Control 4 — Will we run out before delivery?"
JCPL_WORDING = (
    "Compare days of stock left (column U) against the supplier's lead "
    "time (column I). Is the stock going to finish first?"
)

GAP_COLS = [
    C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_STOCK, C_DAILY, C_COVER, C_LEAD,
    {"key": "gap", "label": "Gap (days)", "numeric": True},
    C_TOORDER, C_RATE, C_VALUE,
    {"key": "verdict", "label": "Verdict", "pill": "verdict"},
]


def compute(rows):
    n = len(rows)

    def d(r): return r["data"]
    def ltd(r): return num(d(r).get("lead_time_days"))
    def dc(r): return num(d(r).get("daily_consumption"))
    def csd(r): return num(d(r).get("current_stock_days"))
    def order_qty(r): return num(d(r).get("to_be_ordered_qty")) or 0
    def rate(r): return num(d(r).get("rate")) or 0
    def value(r): return order_qty(r) * rate(r)

    def is_measurable(r):
        return (ltd(r) or 0) > 0 and (dc(r) or 0) > 0

    measurable = [r for r in rows if is_measurable(r)]
    not_assessable = [r for r in rows if not is_measurable(r)]

    def verdict_of(r):
        u, l = csd(r) or 0, ltd(r)
        gap = l - u
        if u == 0:
            return "ALREADY OUT", gap
        if gap > 0 and u < l / 2:
            return "SEVERELY EXPOSED", gap
        if gap > 0:
            return "WILL RUN SHORT", gap
        return "COVERED", gap

    def gap_row(r):
        vd, gap = verdict_of(r)
        return dict(
            with_fields(r, "current_stock_days", "lead_time_days",
                        "to_be_ordered_qty", "daily_consumption", "current_stock_kg", "rate"),
            gap=round(gap, 2),
            value=value(r),
            verdict=vd,
        )

    measured_rows = [gap_row(r) for r in measurable]
    cover_short = [x for x in measured_rows if x["verdict"] != "COVERED"]
    severe = [x for x in measured_rows if x["verdict"] in ("ALREADY OUT", "SEVERELY EXPOSED")]
    already_out = [x for x in measured_rows if x["verdict"] == "ALREADY OUT"]
    covered = [x for x in measured_rows if x["verdict"] == "COVERED"]

    value_exposed = sum(x["value"] for x in cover_short)

    # The cross-check the spec calls "the most dangerous rows on the board":
    # cover-exposed lines that carry NO live requirement at all — nobody has
    # even raised a PO to start with, let alone one that's overdue.
    cover_short_no_requirement = [x for x in cover_short if (x.get("to_be_ordered_qty") or 0) == 0]

    worst = max(measured_rows, key=lambda x: x["gap"], default=None)

    tiles = {
        "lines_measurable": {
            "label": "Lines measurable",
            "value": f"{len(measurable)} of {n}",
            "sub": "Only rows carrying BOTH a lead time AND a daily consumption rate — this control is silent about the rest",
            "kind": "info",
            "brief_target": "36 of 416",
        },
        "not_assessable": {
            "label": "Not assessable",
            "value": len(not_assessable),
            "sub": "Missing lead time or daily consumption — reported as such, never as safe",
            "kind": "info",
        },
        "cover_short": {
            "label": "Cover shorter than lead time",
            "value": len(cover_short),
            "sub": f"of {len(measurable)} measurable — will run out before material can arrive",
            "kind": "critical",
            "brief_target": 21,
        },
        "severely_exposed": {
            "label": "Severely exposed",
            "value": len(severe),
            "sub": "Cover is under half the lead time — ordering alone will not save these; substitute, part-ship or reschedule",
            "kind": "critical",
            "brief_target": 11,
        },
        "already_out": {
            "label": "Already out",
            "value": len(already_out),
            "sub": "Zero days of cover with an active consumption rate — emergency response",
            "kind": "critical",
            "brief_target": 5,
        },
        "value_exposed": {
            "label": "Value exposed",
            "value": rupees_in(value_exposed),
            "sub": "To be ordered × Rate across cover-short rows",
            "kind": "warn",
            "indicative": True,
            "brief_target": "₹97.75 L",
        },
        "cover_short_no_requirement": {
            "label": "Exposed with NO requirement raised",
            "value": len(cover_short_no_requirement),
            "sub": "Cover-short today, and nobody has even raised a PO yet — the most dangerous rows on this board",
            "kind": "critical",
            "brief_target": 5,
        },
        "covered": {
            "label": "Covered",
            "value": len(covered),
            "sub": "Normal reorder path — no gap between cover and lead time",
            "kind": "score",
        },
        "po_enhancement": {
            "label": "PO-promised delivery vs. stock-out date",
            "value": "NOT CHECKABLE",
            "sub": "Enhancement blocked — no PO source available yet (same feed as Controls 1 and 2)",
            "kind": "info",
        },
        "worst_gap": {
            "label": "Worst gap",
            "value": f"{worst['gap']:.0f} days" if worst else "—",
            "sub": f"item {worst['rm_code']}" if worst else "no measurable lines",
            "kind": "warn",
        },
        "notes": {
            "label": "Open questions & hazards",
            "value": "3 items",
            "sub": (
                "① Daily Consumption is derived (Levels ÷ 15), not measured — every days-of-cover "
                "figure here rests on a planning assumption. "
                "② Lead Time Consumption reads zero on rows where Daily Consumption is above zero "
                "on 45 rows in the brief's source file — this can silently suppress Reorder Qty "
                "elsewhere even though it doesn't affect this control directly. "
                "③ Open Q13: what is the escalation route for ALREADY OUT, and within how long?"
            ),
            "kind": "info",
        },
    }

    tile_rows = {
        "lines_measurable": block(GAP_COLS, sorted(measured_rows, key=lambda x: x["gap"], reverse=True)),
        "cover_short": block(GAP_COLS, sorted(cover_short, key=lambda x: x["gap"], reverse=True)),
        "severely_exposed": block(GAP_COLS, sorted(severe, key=lambda x: x["gap"], reverse=True)),
        "already_out": block(GAP_COLS, already_out),
        "value_exposed": block(GAP_COLS, sorted(cover_short, key=lambda x: x["value"], reverse=True)),
        "cover_short_no_requirement": block(GAP_COLS, sorted(cover_short_no_requirement, key=lambda x: x["gap"], reverse=True)),
        "covered": block(GAP_COLS, covered),
        "not_assessable": block(
            add_inventory([C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_COVER, C_LEAD, C_DAILY]),
            [with_fields(r, "current_stock_days", "lead_time_days", "daily_consumption",
                         "current_stock_kg") for r in not_assessable],
        ),
        # po_enhancement / worst_gap / notes are static — no row list.
    }

    return finalise(tiles, tile_rows)
