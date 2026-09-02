"""Mapping from stable field keys to the actual header labels on the
Combined tab.

Every computation reads by stable key — never by sheet header string or
column letter. When Rasika renames a column, we change one string here
and every dashboard follows.

Brief §"How to work through this document" rule 2:
    "Write every formula against the row-2 label, not the column letter."
"""

# stable_key -> sheet header string (as it appears in the Combined tab)
FIELD_MAP = {
    "sr_no":                 "Sr No.",
    "location":              "Location",
    # ⚠ sheet labels differ from brief labels: the brief calls these
    # "RM Code" / "Tally Code", the sheet calls them "Item Name" / "Item Code".
    "rm_code":               "Item Name",
    "tally_code":            "Item Code",
    "rm_specification":      "RM Specification",
    "grade":                 "Grade",
    "component_item":        "Component Item",
    "levels":                "Levels",
    "lead_time_days":        "Lead Time (Days)",
    "daily_consumption":     "Daily Consumption",
    "lead_time_consumption": "Lead Time Consumption",
    "reorder_qty":           "Reorder Qty",
    "mps_demand":            "MPS Demand",
    "green_level":           "Green Level",
    "yellow_level":          "Yellow Level",
    "red_level":             "Red Level",
    "opening":               "Opening",
    "receipt":               "Receipt",
    "issued":                "Issued",
    "current_stock_kg":      "Current Stock in Kg",
    "current_stock_days":    "Current Stock (Days)",
    "till_date_inventory":   "Till Date inventory",
    "inventory_coverage":    "Inventory Coverage",
    "to_be_ordered_qty":     "To be ordered Qty",
    "mis":                   "MIS",
    "expected_arrival":      "Expected Arrival date",
    "rate":                  "Rate",
    "amount":                "Amount",
    "rl_count":              "RL Count",
    "yl_count":              "YL Count",
    "gl_count":              "GL Count",
    "bl_count":              "BL Count",
    "category":              "Category",
    "gl_value":              "GL Value",
    "slow_moving":           "Slow Moving",
    "excel_stock":           "Excel Stock",
    "difference":            "Difference",
    "inventory_type":        "Inventory Type",
    "group":                 "Group",
    "section":               "Section",
    "hardness":              "Hardness",
    "combined_grade":        "Combined Grade",
    # --- PO join (added 24 Aug 2026) -------------------------------------
    # Sourced from the `po` tab via formulas in combined!AQ:AX. Joined on
    # Item Code, falling back to Item Name — po_match_on records which key
    # actually matched, so a verdict can always be traced to its join.
    # These stay blank until those columns exist; every consumer treats a
    # blank as "no PO information", never as zero.
    "po_match_on":           "PO Match On",
    "po_pending_live":       "PO Pending Live",
    "po_pending_overdue":    "PO Pending Overdue",
    "po_received":           "PO Received",
    "po_earliest_due":       "PO Earliest Due",
    "po_days_late":          "PO Days Late",
    "po_numbers":            "PO Numbers",
    "po_vendors":            "PO Vendors",
}


# --- Helpers used by every computation --------------------------------------


def num(v):
    """Coerce a cell into a float; return None on missing / unparseable
    values rather than 0. Brief §rule 4: "Never IFERROR(...,0)."
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except (ValueError, TypeError):
        return None


def num0(v):
    """Coerce like num() but return 0.0 for missing — use this only in
    places where the brief explicitly treats blank as zero, e.g. counting
    "silent zero rows" where every stock field really is zero-or-blank."""
    n = num(v)
    return 0.0 if n is None else n


def txt(v):
    """Trimmed string of a cell, empty string on None."""
    if v is None:
        return ""
    return str(v).strip()


def is_present_code(v):
    """A field is a "real code" if it's non-empty AND not literally '0'.
    Used for the RM-Code and Tally-Code presence tests."""
    s = txt(v)
    return bool(s) and s != "0"


def rupees_in(n):
    """Format a rupee amount in Indian lakh/crore convention for display."""
    if n is None:
        return "—"
    if abs(n) >= 1_00_00_000:
        return f"₹{n/1_00_00_000:,.2f} Cr"
    if abs(n) >= 1_00_000:
        return f"₹{n/1_00_000:,.2f} L"
    return f"₹{n:,.0f}"
