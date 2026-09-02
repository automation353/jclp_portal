"""Dashboard 3 — Reorder Level (RAG) Board.

Brief §Dashboard 3. Red / Yellow / Green / Blue distribution of every
ACTIVE stocked line, each band drilling to its own rows. Bands are
recomputed from Current Stock against the level columns — the sheet's own
RL/YL/GL/BL counters are displayed alongside, never used as the source.
"""

from ..drill import (
    C_COVER, C_DAILY, C_GROUP, C_LEAD, C_RATE, C_RM, C_SPEC, C_SR, C_STOCK,
    C_TALLY, C_VALUE, block, finalise, with_fields,
)
from ..field_map import num, rupees_in


DASHBOARD_KEY = "d3"
TITLE = "Reorder Level (RAG)"

BAND_COLS = [C_SR, C_TALLY, C_RM, C_SPEC, C_STOCK, C_DAILY, C_COVER, C_LEAD,
             {"key": "red_level",    "label": "Red level",    "numeric": True},
             {"key": "yellow_level", "label": "Yellow level", "numeric": True},
             {"key": "green_level",  "label": "Green level",  "numeric": True},
             C_VALUE]


def compute(rows):
    active = [r for r in rows if (num(r["data"].get("green_level")) or 0) > 0]

    red, yellow, green, blue, suppressed = [], [], [], [], []

    for r in active:
        d = r["data"]
        cs = num(d.get("current_stock_kg"))
        if cs is None:
            continue
        rl = num(d.get("red_level")) or 0
        yl = num(d.get("yellow_level")) or 0
        gl = num(d.get("green_level")) or 0
        row = dict(
            with_fields(r, "current_stock_kg", "daily_consumption",
                        "current_stock_days", "lead_time_days",
                        "red_level", "yellow_level",
                        "green_level", "rate"),
            value=cs * (num(d.get("rate")) or 0),
        )
        if cs < rl:
            row["shortfall"] = round(rl - cs, 2)
            red.append(row)
            if yl < 500:
                suppressed.append(dict(
                    row, note="excluded by the sheet's RL Count because Yellow < 500"))
        elif cs < yl:
            yellow.append(row)
        elif cs < gl:
            green.append(row)
        else:
            row["excess"] = round(cs - gl, 2)
            blue.append(row)

    red.sort(key=lambda x: x.get("shortfall", 0), reverse=True)
    blue.sort(key=lambda x: x.get("excess", 0), reverse=True)

    def val(bucket):
        return sum(x["value"] for x in bucket)

    sheet_red    = sum(1 for r in rows if (num(r["data"].get("rl_count")) or 0) == 1)
    sheet_yellow = sum(1 for r in rows if (num(r["data"].get("yl_count")) or 0) == 1)
    sheet_green  = sum(1 for r in rows if (num(r["data"].get("gl_count")) or 0) == 1)
    sheet_blue   = sum(1 for r in rows if (num(r["data"].get("bl_count")) or 0) == 1)

    tiles = {
        "red": {
            "label": "Red — buy immediately",
            "value": len(red),
            "sub": f"{rupees_in(val(red))}  ·  sheet counter: {sheet_red}",
            "kind": "critical", "indicative": True,
        },
        "yellow": {
            "label": "Yellow — watch, buy soon",
            "value": len(yellow),
            "sub": f"{rupees_in(val(yellow))}  ·  sheet counter: {sheet_yellow}",
            "kind": "warn", "indicative": True,
        },
        "green": {
            "label": "Green — stock is enough",
            "value": len(green),
            "sub": f"{rupees_in(val(green))}  ·  sheet counter: {sheet_green}",
            "kind": "score", "indicative": True,
        },
        "blue": {
            "label": "Blue — extra stock, money blocked",
            "value": len(blue),
            "sub": f"{rupees_in(val(blue))}  ·  sheet counter: {sheet_blue}  ·  overstock, not safety",
            "kind": "info", "indicative": True,
        },
        "active_lines": {
            "label": "Material having fixed level",
            "value": len(active),
            "sub": f"Green Level > 0  ·  R+Y+G+B = {len(red)+len(yellow)+len(green)+len(blue)}",
            "kind": "info",
        },
        "suppressed": {
            "label": "Hidden red items — check manually",
            "value": len(suppressed),
            "sub": "Genuine red-band breaches the sheet's RL Count hides  ·  Decision 3",
            "kind": "warn",
        },
    }

    tile_rows = {
        "red": block(BAND_COLS + [{"key": "shortfall", "label": "Shortfall (kg)",
                                   "numeric": True}], red),
        "yellow": block(BAND_COLS, yellow),
        "green":  block(BAND_COLS, green),
        "blue":   block(BAND_COLS + [{"key": "excess", "label": "Excess over green (kg)",
                                      "numeric": True}], blue),
        "active_lines": block(BAND_COLS, red + yellow + green + blue),
        "suppressed": block(
            BAND_COLS + [{"key": "note", "label": "Why hidden"}], suppressed),
    }

    return finalise(tiles, tile_rows)
