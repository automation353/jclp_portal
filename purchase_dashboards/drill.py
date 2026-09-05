"""Helpers for building per-tile drill-through row lists.

Every computation module returns, alongside its ``tiles`` dict, a
``tile_rows`` dict of the same keys:

    tile_rows = {
        "silent_zero": {
            "columns": [{"key": "rm_code", "label": "RM Code"}, ...],
            "rows":    [{"rm_code": "...", ...}, ...],
        },
        ...
    }

``finalise()`` then stamps ``row_count`` and ``drillable`` onto each tile so
the frontend can render the "▸ N rows" affordance without fetching anything.

Tiles with no entry in ``tile_rows`` are marked ``drillable: False`` — that's
the escape hatch for pure aggregates (ratios, two-sided comparisons) where a
row list would be meaningless.
"""

from .field_map import num, txt


# ── Reusable column specs ───────────────────────────────────────────────────
# Keys here must match the keys the row-builders below emit.

C_SR       = {"key": "sr_no",              "label": "Sr No",        "numeric": True}
C_TALLY    = {"key": "tally_code",         "label": "Item Code"}
C_RM       = {"key": "rm_code",            "label": "RM Code"}
C_SPEC     = {"key": "rm_specification",   "label": "Specification"}
C_GROUP    = {"key": "group",              "label": "Group"}
C_CATEGORY = {"key": "category",           "label": "Category"}
C_ITYPE    = {"key": "inventory_type",     "label": "Type"}
C_STOCK    = {"key": "current_stock_kg",   "label": "Stock (kg)",   "numeric": True}
C_COVER    = {"key": "current_stock_days", "label": "Cover (days)", "numeric": True}
C_LEAD     = {"key": "lead_time_days",     "label": "Lead time",    "numeric": True}
C_DAILY    = {"key": "daily_consumption",  "label": "Daily cons.",  "numeric": True}
C_TOORDER  = {"key": "to_be_ordered_qty",  "label": "To order",     "numeric": True}
C_REORDER  = {"key": "reorder_qty",        "label": "Reorder Qty",  "numeric": True}
C_MPS      = {"key": "mps_demand",         "label": "MPS Demand",   "numeric": True}
C_RATE     = {"key": "rate",               "label": "Rate",         "numeric": True}
C_VALUE    = {"key": "value",              "label": "Value",        "numeric": True, "rupees": True}
C_GREEN    = {"key": "green_level",        "label": "Green level",  "numeric": True}
C_YELLOW   = {"key": "yellow_level",       "label": "Yellow level", "numeric": True}
C_RED      = {"key": "red_level",          "label": "Red level",    "numeric": True}
C_LEVELS   = {"key": "levels",             "label": "Levels",       "numeric": True}
C_COVBAND  = {"key": "inventory_coverage", "label": "Coverage band"}
C_TILLDATE = {"key": "till_date_inventory","label": "Till-date inventory"}
C_NOTE     = {"key": "note",               "label": "Note"}

# The four inventory-context columns added to every material-level tile.
INVENTORY_COLS = (C_STOCK, C_DAILY, C_COVER, C_LEAD)

# The field keys that with_fields() needs for the inventory columns.
INVENTORY_FIELDS = ("current_stock_kg", "daily_consumption",
                    "current_stock_days", "lead_time_days")

# The column set used by most "here are the affected item lines" tiles.
IDENTITY_COLS = [C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY, C_GROUP]


def base_row(r):
    """The identity fields every drill row carries, so tables are comparable
    across tiles."""
    d = r["data"]
    return {
        "sr_no": r["sr_no"],
        "rm_code": txt(d.get("rm_code")),
        "tally_code": txt(d.get("tally_code")),
        "rm_specification": txt(d.get("rm_specification")),
        "category": txt(d.get("category")),
        "group": txt(d.get("group")),
        "inventory_type": txt(d.get("inventory_type")),
    }


def with_fields(r, *field_keys, **extra):
    """base_row plus the named numeric/text fields from the snapshot row,
    plus any computed extras passed as kwargs."""
    out = base_row(r)
    d = r["data"]
    for key in field_keys:
        out[key] = num(d.get(key)) if key not in (
            "inventory_coverage", "till_date_inventory",
        ) else txt(d.get(key))
    out.update(extra)
    return out


def add_inventory(cols):
    """Append any of the four inventory columns not already in *cols*."""
    keys = {c["key"] for c in cols if isinstance(c, dict)}
    return cols + [c for c in INVENTORY_COLS if c["key"] not in keys]


def inv_fields(r):
    """Extract the four inventory field values from a snapshot row."""
    d = r["data"]
    return {k: num(d.get(k)) for k in INVENTORY_FIELDS}


def block(columns, rows):
    """One tile_rows entry, with auto-computed subtotals for numeric columns.

    Row numbers are re-assigned sequentially (1, 2, 3 …) so drill-down
    tables read as a clean numbered list rather than carrying the original
    sheet row numbers which are non-contiguous and confusing.  Rows are
    shallow-copied so renumbering one block never leaks into another that
    shares the same dict references.
    """
    rows = [{**r, "sr_no": i} for i, r in enumerate(rows, 1)]
    subtotals = _subtotals(columns, rows) if len(rows) > 1 else None
    entry = {"columns": columns, "rows": rows}
    if subtotals:
        entry["subtotals"] = subtotals
    return entry


# Columns where a sum is meaningful. Everything else (sr_no, lead_time,
# cover days, ratios) would produce a nonsensical total.
_SUMMABLE = {
    "current_stock_kg", "daily_consumption", "to_be_ordered_qty",
    "reorder_qty", "mps_demand", "value", "shortfall", "gap",
    "excess_kg", "delta_kg", "lines", "green_level", "red_level",
    "yellow_level", "open_po", "net_order", "balance_to_raise",
    "po_live", "po_overdue",
    "po_pending_live", "po_pending_overdue", "po_received",
}


def _subtotals(columns, rows):
    """Sum additive numeric columns across *rows*. Returns a dict of
    {key: total} for columns that are both numeric and in the summable set."""
    numeric_keys = {c["key"] for c in columns
                    if isinstance(c, dict) and c.get("numeric")
                    and c["key"] in _SUMMABLE}
    if not numeric_keys:
        return None
    totals = {}
    for key in numeric_keys:
        s = sum((r.get(key) or 0) for r in rows if isinstance(r.get(key), (int, float)))
        if s:
            totals[key] = round(s, 2)
    return totals if totals else None


def finalise(tiles, tile_rows):
    """Stamp row_count + drillable onto each tile and return the payload the
    computation modules hand back."""
    for key, tile in tiles.items():
        entry = tile_rows.get(key)
        if entry is None:
            tile["drillable"] = False
        else:
            tile["drillable"] = True
            tile["row_count"] = len(entry["rows"])
    return {"tiles": tiles, "tile_rows": tile_rows}
