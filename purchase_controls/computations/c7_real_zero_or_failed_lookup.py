"""Control 7 — "Is that zero a real zero, or a failed search?"

Spec §Control 7. The control that decides whether any of the other six can
be believed. Every RM stock lookup is wrapped in IFERROR(...,0) upstream —
when a lookup finds nothing, the formula returns zero, which then reads
exactly like empty stock. A "quad-zero" row (Opening, Receipt, Issued AND
Current Stock all zero at once) is the signature of a failed search, not
necessarily an empty bin.

Until the TCS iON stock summary feed exists, spec §4 is explicit: every
quad-zero row must carry the verdict UNCONFIRMED, split only by whether it
is even resolvable in principle (has a real, joinable Tally Code) or
routes straight to Control 6 as a master-data failure.

Rows where Current Stock is zero but Opening/Receipt/Issued show real
movement are GENUINE RUN-DOWN — real, and explicitly NOT suspicious;
flagging them would be the rule being too broad (spec §6).
"""

from purchase_dashboards.drill import (
    C_CATEGORY, C_COVER, C_DAILY, C_GROUP, C_LEAD, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, C_TOORDER, block, finalise, with_fields,
)
from purchase_dashboards.field_map import is_present_code, num, num0, txt

CONTROL_KEY = "c7"
TITLE = "Control 7 — Real zero, or a failed search?"
JCPL_WORDING = (
    "When the sheet shows 0 stock, ask: is stock genuinely nil, or did the "
    "lookup simply not find the code?"
)

PLACEHOLDERS = {"item code required", "tbd", "n/a", "na"}

STOCK_COLS = [
    C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP,
    {"key": "opening", "label": "Opening", "numeric": True},
    {"key": "receipt", "label": "Receipt", "numeric": True},
    {"key": "issued",  "label": "Issued",  "numeric": True},
    C_STOCK, C_DAILY, C_COVER, C_LEAD, C_TOORDER,
    {"key": "verdict", "label": "Verdict", "pill": "verdict"},
]


def _has_real_code(v):
    return is_present_code(v) and txt(v).lower() not in PLACEHOLDERS


def compute(rows):
    n = len(rows)

    def d(r): return r["data"]
    def is_quad_zero(r):
        return (num0(d(r).get("opening")) == 0 and num0(d(r).get("receipt")) == 0
                and num0(d(r).get("issued")) == 0 and num0(d(r).get("current_stock_kg")) == 0)

    quad_zero = [r for r in rows if is_quad_zero(r)]
    # Genuine run-down: closing balance is nil but real movement happened —
    # this is a true stock event, not a lookup failure, and must not be
    # counted among the quad-zero suspects (it fails is_quad_zero by
    # definition since at least one of Opening/Receipt/Issued is non-zero).
    genuine_run_down = [
        r for r in rows
        if num0(d(r).get("current_stock_kg")) == 0 and not is_quad_zero(r)
    ]

    def verdict_of(r):
        if _has_real_code(d(r).get("tally_code")):
            return "UNCONFIRMED"
        return "UNRESOLVABLE — MASTER DATA"

    def line(r):
        return dict(
            with_fields(r, "opening", "receipt", "issued", "current_stock_kg",
                       "to_be_ordered_qty", "daily_consumption",
                       "current_stock_days", "lead_time_days"),
            verdict=verdict_of(r),
        )

    quad_lines = [line(r) for r in quad_zero]
    unresolvable = [x for x in quad_lines if x["verdict"] == "UNRESOLVABLE — MASTER DATA"]
    unconfirmed = [x for x in quad_lines if x["verdict"] == "UNCONFIRMED"]
    quad_with_requirement = [x for x in quad_lines if (x.get("to_be_ordered_qty") or 0) > 0]

    confirmed_count = n - len(quad_zero)
    confirmed_pct = round(100 * confirmed_count / n, 1) if n else 0

    tiles = {
        "confirmed_pct": {
            "label": "Confirmed-rows share",
            "value": f"{confirmed_pct}%",
            "sub": f"{confirmed_count} of {n} rows are NOT quad-zero — every control reading the other {len(quad_zero)} is unverified until the stock feed lands",
            "kind": "score" if confirmed_pct >= 60 else "critical",
            "brief_target": "125 of 416 — 30%",
        },
        "quad_zero": {
            "label": "Quad-zero rows",
            "value": len(quad_zero),
            "sub": f"of {n} — Opening, Receipt, Issued and Current Stock all zero at once",
            "kind": "critical",
            "brief_target": 291,
        },
        "unconfirmed_resolvable": {
            "label": "Resolvable once the feed lands",
            "value": len(unconfirmed),
            "sub": "Carry a real Tally Code — the stock summary feed will settle these",
            "kind": "warn",
            "brief_target": 213,
        },
        "unresolvable_master_data": {
            "label": "Unresolvable — master data",
            "value": len(unresolvable),
            "sub": "No feed can fix these; route to Control 6 for a code correction first",
            "kind": "critical",
            "brief_target": 78,
        },
        "quad_zero_with_requirement": {
            "label": "Quad-zero AND a live requirement",
            "value": len(quad_with_requirement),
            "sub": "JCPL may be about to order material it already holds — the highest-priority rows on this board",
            "kind": "critical",
            "brief_target": 23,
        },
        "genuine_run_down": {
            "label": "Genuine run-down (not suspicious)",
            "value": len(genuine_run_down),
            "sub": "Current Stock nil but real movement in Opening/Receipt/Issued — a real event, explicitly excluded from the quad-zero suspects",
            "kind": "info",
            "brief_target": 3,
        },
        "notes": {
            "label": "Open questions & hazards",
            "value": "3 items",
            "sub": (
                "① This control gates the other six — until the confirmed share is materially above "
                "today's figure, every other board is reporting on partly-unverified data. "
                "② Open Q21: can the stock summary export include nil-balance items? Without them this "
                "control cannot tell a real zero from a missing code. "
                "③ Open Q22: which godowns should this board cover — Harisiddhi only, or all locations?"
            ),
            "kind": "info",
        },
    }

    tile_rows = {
        "quad_zero": block(STOCK_COLS, sorted(quad_lines, key=lambda x: x["sr_no"] or 0)),
        "unconfirmed_resolvable": block(STOCK_COLS, unconfirmed),
        "unresolvable_master_data": block(STOCK_COLS, unresolvable),
        "quad_zero_with_requirement": block(STOCK_COLS, quad_with_requirement),
        "genuine_run_down": block(
            STOCK_COLS,
            [dict(with_fields(r, "opening", "receipt", "issued", "current_stock_kg",
                              "to_be_ordered_qty", "daily_consumption",
                              "current_stock_days", "lead_time_days"),
                  verdict="GENUINE RUN-DOWN")
             for r in genuine_run_down],
        ),
        # confirmed_pct / notes are static — no row list.
    }

    return finalise(tiles, tile_rows)
