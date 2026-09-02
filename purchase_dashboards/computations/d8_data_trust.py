"""Dashboard 8 — Data Trust & Integrity Board.

Brief §Dashboard 8. Every other board rests on the RM sheet; this one
measures how much of it can be believed. Every tile drills to the exact
rows behind its number.
"""

from ..drill import (
    C_COVER, C_DAILY, C_GROUP, C_LEAD, C_MPS, C_RATE, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, IDENTITY_COLS, add_inventory, base_row, block, finalise,
    inv_fields, with_fields,
)
from ..field_map import is_present_code, num, num0, txt


DASHBOARD_KEY = "d8"
TITLE = "Data Trust & Integrity"

STOCK_COLS = [C_SR, C_TALLY, C_RM, C_SPEC,
              {"key": "opening", "label": "Opening", "numeric": True},
              {"key": "receipt", "label": "Receipt", "numeric": True},
              {"key": "issued",  "label": "Issued",  "numeric": True},
              C_STOCK]


def compute(rows):
    n = len(rows)

    # --- SILENT ZERO ROWS ---------------------------------------------------
    silent_zero = [
        r for r in rows
        if num0(r["data"].get("opening")) == 0
        and num0(r["data"].get("receipt")) == 0
        and num0(r["data"].get("issued")) == 0
        and num0(r["data"].get("current_stock_kg")) == 0
    ]

    # --- ROWS WITH NO RM CODE ----------------------------------------------
    no_rm_code = [r for r in rows if not is_present_code(r["data"].get("rm_code"))]

    # --- ROWS WITH NO TALLY CODE -------------------------------------------
    no_tally = [r for r in rows if not is_present_code(r["data"].get("tally_code"))]

    # --- LINES WITH NO RATE -------------------------------------------------
    no_rate = [r for r in rows if num(r["data"].get("rate")) in (None, 0, 0.0)]

    # --- NO DELIVERY COMMITMENT --------------------------------------------
    no_delivery = [r for r in rows if not txt(r["data"].get("expected_arrival"))]

    # --- NO SALES DEMAND SIGNAL --------------------------------------------
    no_mps = [r for r in rows if num(r["data"].get("mps_demand")) in (None, 0, 0.0)]

    # --- TRUST SCORE — and the rows that FAIL it ---------------------------
    silent_ids = {r["sr_no"] for r in silent_zero}

    def fails_trust(r):
        d = r["data"]
        return not (
            is_present_code(d.get("rm_code"))
            and is_present_code(d.get("tally_code"))
            and num(d.get("rate")) not in (None, 0)
            and r["sr_no"] not in silent_ids
        )

    failing = [r for r in rows if fails_trust(r)]
    trusted = n - len(failing)
    trust_pct = round(100 * trusted / n, 1) if n else 0

    def fail_reasons(r):
        d = r["data"]
        why = []
        if not is_present_code(d.get("rm_code")):    why.append("no RM Code")
        if not is_present_code(d.get("tally_code")): why.append("no Tally Code")
        if num(d.get("rate")) in (None, 0):          why.append("no Rate")
        if r["sr_no"] in silent_ids:                 why.append("silent zero")
        return ", ".join(why)

    tiles = {
        "trust_score": {
            "label": "Data Trust Score",
            "value": f"{trust_pct}%",
            "sub": f"{trusted} of {n} rows carry code, tally, rate, non-silent stock",
            "kind": "score" if trust_pct >= 60 else "critical",
        },
        "silent_zero": {
            "label": "Silent zero rows",
            "value": len(silent_zero),
            "sub": f"of {n}  ·  Opening + Receipt + Issued + Current Stock all zero",
            "kind": "warn",
        },
        "no_rm_code": {
            "label": "Rows with no RM Code",
            "value": len(no_rm_code),
            "sub": f"of {n}  ·  cannot be joined to any other system",
            "kind": "warn",
        },
        "no_tally_code": {
            "label": "Rows with no Tally Code",
            "value": len(no_tally),
            "sub": f"of {n}  ·  cannot be reconciled to the books",
            "kind": "warn",
        },
        "no_rate": {
            "label": "Lines with no Rate",
            "value": len(no_rate),
            "sub": f"of {n}  ·  silently undercounts every rupee tile in this pack",
            "kind": "critical",
        },
        "no_delivery_date": {
            "label": "No delivery commitment",
            "value": len(no_delivery),
            "sub": f"of {n}  ·  Expected Arrival date is blank",
            "kind": "critical",
        },
        "no_mps": {
            "label": "No sales demand signal",
            "value": len(no_mps),
            "sub": f"of {n}  ·  requirement driven by buffer top-up only",
            "kind": "info",
        },
    }

    tile_rows = {
        "trust_score": block(
            add_inventory(IDENTITY_COLS + [{"key": "fail_reasons", "label": "Fails because"}]),
            [dict(base_row(r), **inv_fields(r), fail_reasons=fail_reasons(r)) for r in failing],
        ),
        "silent_zero": block(
            add_inventory(STOCK_COLS),
            [with_fields(r, "opening", "receipt", "issued", "current_stock_kg",
                         "daily_consumption", "current_stock_days", "lead_time_days")
             for r in silent_zero],
        ),
        "no_rm_code": block(
            add_inventory([C_SR, C_TALLY, C_SPEC, C_GROUP, C_STOCK]),
            [with_fields(r, "current_stock_kg", "daily_consumption",
                         "current_stock_days", "lead_time_days")
             for r in no_rm_code],
        ),
        "no_tally_code": block(
            add_inventory([C_SR, C_RM, C_SPEC, C_GROUP, C_STOCK]),
            [with_fields(r, "current_stock_kg", "daily_consumption",
                         "current_stock_days", "lead_time_days")
             for r in no_tally],
        ),
        "no_rate": block(
            add_inventory(IDENTITY_COLS + [C_STOCK, C_RATE]),
            [with_fields(r, "current_stock_kg", "daily_consumption",
                         "current_stock_days", "lead_time_days", "rate")
             for r in no_rate],
        ),
        "no_delivery_date": block(
            add_inventory(IDENTITY_COLS + [C_STOCK,
                             {"key": "to_be_ordered_qty", "label": "To order", "numeric": True}]),
            [with_fields(r, "current_stock_kg", "daily_consumption",
                         "current_stock_days", "lead_time_days",
                         "to_be_ordered_qty")
             for r in no_delivery],
        ),
        "no_mps": block(
            add_inventory(IDENTITY_COLS + [C_MPS, C_STOCK, C_DAILY]),
            [with_fields(r, "mps_demand", "current_stock_kg", "daily_consumption",
                         "current_stock_days", "lead_time_days")
             for r in no_mps],
        ),
    }

    return finalise(tiles, tile_rows)
