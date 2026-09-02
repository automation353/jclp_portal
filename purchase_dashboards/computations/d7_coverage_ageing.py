"""Dashboard 7 — Inventory Coverage Ageing Board.

Brief §Dashboard 7. Distribution of the whole master across days-of-cover
bands. The "0 to 15" band is split into "genuinely short" and "not
measurable" because Current Stock (Days) returns zero whenever Daily
Consumption is zero — read naively the raw band claims JCPL is two weeks
from shutdown, and it says nothing of the kind.
"""

from ..drill import (
    C_CATEGORY, C_COVBAND, C_COVER, C_DAILY, C_GROUP, C_LEAD, C_RM, C_SPEC,
    C_SR, C_STOCK, C_TALLY, block, finalise, with_fields,
)
from ..field_map import num, txt


DASHBOARD_KEY = "d7"
TITLE = "Inventory Coverage Ageing"

OVER_120_LABELS = ("120 to 180", "180 to 365", "365 & Above")

BAND_COLS = [C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP, C_STOCK, C_DAILY,
             C_COVER, C_LEAD, C_COVBAND]


def compute(rows):
    def band(r): return txt(r["data"].get("inventory_coverage"))
    def dc(r):   return num(r["data"].get("daily_consumption")) or 0
    def line(r):
        return with_fields(r, "current_stock_kg", "daily_consumption",
                           "current_stock_days", "lead_time_days",
                           "inventory_coverage")

    band_15  = [r for r in rows if band(r) == "0 to 15"]
    band_30  = [r for r in rows if band(r) == "15 to 30"]
    band_60  = [r for r in rows if band(r) == "30 to 60"]
    band_120 = [r for r in rows if band(r) == "60 to 120"]
    over_120 = [r for r in rows if band(r) in OVER_120_LABELS]

    not_measurable  = [r for r in band_15 if dc(r) == 0]
    genuinely_short = [r for r in band_15 if dc(r) > 0]

    tiles = {
        "band_0_15_total": {
            "label": "Stock for less than 15 days", "value": len(band_15),
            "sub": "Face-value count · READ THE SPLIT BELOW before quoting this",
            "kind": "warn",
        },
        "genuinely_short": {
            "label": "Really short — daily use material", "value": len(genuinely_short),
            "sub": "In the tight band AND consumption > 0",
            "kind": "critical",
        },
        "not_measurable": {
            "label": "Cannot be judged — no usage data", "value": len(not_measurable),
            "sub": "In the tight band because consumption = 0, not because stock is short",
            "kind": "warn",
        },
        "band_30": {
            "label": "Stock for 15 to 30 days", "value": len(band_30),
            "sub": "Two to four weeks of cover", "kind": "info",
        },
        "band_60": {
            "label": "Stock for 1 to 2 months", "value": len(band_60),
            "sub": "One to two months of cover", "kind": "info",
        },
        "band_120": {
            "label": "Stock for 2 to 4 months", "value": len(band_120),
            "sub": "Two to four months of cover", "kind": "info",
        },
        "over_120": {
            "label": "Stock for more than 4 months", "value": len(over_120),
            "sub": "More than four months — candidates for dead-stock review",
            "kind": "warn",
        },
    }

    reason_col = {"key": "note", "label": "Why in this band"}

    tile_rows = {
        "band_0_15_total": block(BAND_COLS, [line(r) for r in band_15]),
        "genuinely_short": block(
            BAND_COLS + [reason_col],
            [dict(line(r), note="consumption > 0 — genuinely short of cover")
             for r in genuinely_short],
        ),
        "not_measurable": block(
            BAND_COLS + [reason_col],
            [dict(line(r), note="consumption is zero — 'short' is arithmetically wrong")
             for r in not_measurable],
        ),
        "band_30":  block(BAND_COLS, [line(r) for r in band_30]),
        "band_60":  block(BAND_COLS, [line(r) for r in band_60]),
        "band_120": block(BAND_COLS, [line(r) for r in band_120]),
        "over_120": block(BAND_COLS, [line(r) for r in over_120]),
    }

    return finalise(tiles, tile_rows)
