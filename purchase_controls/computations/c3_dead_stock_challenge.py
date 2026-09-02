"""Control 3 — "Are we buying something we are already drowning in?"

Spec §Control 3. Buildable now, in full, from the RM sheet alone.
Population: the requirement lines only — rows where [To be ordered Qty] > 0.
A line can trip more than one rule at once; every tripped rule is reported,
not just the first (spec §4, "Note on this table").

Hazard carried onto the board unresolved, per spec §7:
  "HIGH INVENTORY contradicts itself" / the classification may be stale —
  see the `notes` tile.
"""

from purchase_dashboards.drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_GROUP, C_LEAD, C_MPS, C_RATE, C_RM,
    C_SPEC, C_SR, C_STOCK, C_TALLY, C_TOORDER, C_VALUE,
    block, finalise, with_fields,
)
from purchase_dashboards.field_map import num, rupees_in, txt

CONTROL_KEY = "c3"
TITLE = "Control 3 — Buying what we're drowning in?"
JCPL_WORDING = (
    "Column X says order more. But column V says HIGH INVENTORY, or the "
    "item is marked Slow / Non Moving."
)

LINE_COLS = [
    C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP, C_STOCK, C_DAILY, C_COVER, C_LEAD, C_TOORDER,
    C_RATE, C_VALUE,
    {"key": "rules_tripped", "label": "Rules tripped"},
    {"key": "verdict", "label": "Verdict", "pill": "verdict"},
]


def compute(rows):
    n = len(rows)
    to_order = [r for r in rows if (num(r["data"].get("to_be_ordered_qty")) or 0) > 0]

    def d(r): return r["data"]
    def cat(r): return txt(d(r).get("category"))
    def stock(r): return num(d(r).get("current_stock_kg")) or 0
    def green(r): return num(d(r).get("green_level")) or 0
    def rate(r): return num(d(r).get("rate")) or 0
    def order_qty(r): return num(d(r).get("to_be_ordered_qty")) or 0
    def value(r): return order_qty(r) * rate(r)
    def mps(r): return num(d(r).get("mps_demand")) or 0

    # brief's HI test: [Till Date inventory] literally reading "HIGH
    # INVENTORY". That column mixes dates and this label; until 21 Aug 2026 the
    # gviz CSV endpoint typed it as a date and dropped every text value, so this
    # test could never fire. fetcher.py now uses the plain CSV export, which
    # preserves both.
    def is_high_inventory(r):
        return "HIGH INVENTORY" in txt(d(r).get("till_date_inventory")).upper()

    def line(r):
        flags = []
        if cat(r) == "Non Moving":
            flags.append("Non Moving")
        if cat(r) == "Slow Moving":
            flags.append("Slow Moving")
        if is_high_inventory(r):
            flags.append("HIGH INVENTORY")
        if mps(r) == 0:
            flags.append("no customer pull")
        if green(r) > 0 and stock(r) > green(r):
            flags.append("above buffer")

        dead = cat(r) == "Non Moving"
        slow = cat(r) == "Slow Moving"
        hi = is_high_inventory(r)
        if dead and hi:
            verdict = "STOP — DOUBLE FLAG"
        elif dead:
            verdict = "STOP — DEAD ITEM"
        elif hi:
            verdict = "STOP — ALREADY OVER-STOCKED"
        elif slow:
            verdict = "CHALLENGE"
        else:
            verdict = "CLEAR"

        return dict(
            with_fields(r, "current_stock_kg", "to_be_ordered_qty", "rate",
                        "green_level", "mps_demand",
                        "daily_consumption", "current_stock_days",
                        "lead_time_days"),
            value=value(r),
            rules_tripped=", ".join(flags) if flags else "—",
            severity=len(flags),
            verdict=verdict,
        )

    lines = [line(r) for r in to_order]

    non_slow_moving = [x for x in lines if x["verdict"] in
                       ("STOP — DEAD ITEM", "STOP — DOUBLE FLAG") or "Slow Moving" in x["rules_tripped"]]
    high_inventory = [x for x in lines if "HIGH INVENTORY" in x["rules_tripped"]]
    double_flag = [x for x in lines if x["verdict"] == "STOP — DOUBLE FLAG"]
    flagged = [x for x in lines if x["verdict"] != "CLEAR"]
    clear = [x for x in lines if x["verdict"] == "CLEAR"]
    no_pull = [x for x in lines if "no customer pull" in x["rules_tripped"]]
    above_buffer = [x for x in lines if "above buffer" in x["rules_tripped"]]

    flagged_value = sum(x["value"] for x in flagged)
    flagged_sorted = sorted(flagged, key=lambda x: x["value"], reverse=True)

    tiles = {
        "requirement_population": {
            "label": "Requirement lines entering this control",
            "value": len(to_order),
            "sub": "Rows where To be ordered Qty > 0 — the same population as Control 1/2/4",
            "kind": "info",
            "brief_target": 57,
        },
        "flagged_union": {
            "label": "Flagged — do not raise blind",
            "value": len(flagged),
            "sub": f"{rupees_in(flagged_value)} of {len(to_order)} requirement lines · Non/Slow Moving OR HIGH INVENTORY, de-duplicated",
            "kind": "critical",
            "brief_target": 23,
        },
        "non_slow_moving": {
            "label": "Non / Slow Moving",
            "value": len(non_slow_moving),
            "sub": "Category says the material isn't turning",
            "kind": "warn",
            "brief_target": 19,
        },
        "high_inventory": {
            "label": "HIGH INVENTORY flag",
            "value": len(high_inventory),
            "sub": "Till Date inventory literally reads HIGH INVENTORY — stock already exceeds twice the stocking level",
            "kind": "warn",
            "brief_target": 7,
        },
        "double_flag": {
            "label": "Double flag",
            "value": len(double_flag),
            "sub": "Both tests fail at once — escalate rather than merely challenge",
            "kind": "critical",
            "brief_target": 3,
        },
        "no_customer_pull": {
            "label": "No customer pull",
            "value": len(no_pull),
            "sub": "MPS Demand = 0 — buffer top-up only; permitted, must stay visible as such",
            "kind": "info",
            "brief_target": 17,
        },
        "above_buffer": {
            "label": "Above buffer already",
            "value": len(above_buffer),
            "sub": "Current stock already exceeds Green Level policy",
            "kind": "info",
        },
        "clear": {
            "label": "Clear to proceed",
            "value": len(clear),
            "sub": f"of {len(to_order)} — trips none of the tests above",
            "kind": "score",
        },
        "notes": {
            "label": "Open questions & hazards",
            "value": "4 items",
            "sub": (
                "① The HIGH INVENTORY test was returning 0 until 21 Aug 2026 — not because the "
                "data was absent, but because the sheet's CSV transport typed that column as a date "
                "and silently blanked every text value in it. Fixed at source; the count is now real. "
                "② Category's last recalculation date is not known — flag any STOP verdict as "
                "resting on a classification of unstated age. "
                "③ Open Q9: should STOP block the requisition, or only warn with a recorded reason? "
                "④ Open Q10: who signs off an order against a Non Moving item?"
            ),
            "kind": "info",
        },
    }

    tile_rows = {
        "requirement_population": block(LINE_COLS, sorted(lines, key=lambda x: x["value"], reverse=True)),
        "flagged_union": block(LINE_COLS, flagged_sorted),
        "non_slow_moving": block(LINE_COLS, sorted(non_slow_moving, key=lambda x: x["value"], reverse=True)),
        "high_inventory": block(LINE_COLS, sorted(high_inventory, key=lambda x: x["value"], reverse=True)),
        "double_flag": block(LINE_COLS, double_flag),
        "no_customer_pull": block(LINE_COLS, no_pull),
        "above_buffer": block(LINE_COLS, above_buffer),
        "clear": block(LINE_COLS, clear),
        # notes is a static text tile — no row list.
    }

    return finalise(tiles, tile_rows)
