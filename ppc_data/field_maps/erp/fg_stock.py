"""ERP Report #3 — FG Stock Statement (daily).

Critical for: R3SS opening balance, MPS.
Frequency: Daily at 05:00 AM.
"""

TABLE_KEY = "erp_fg_stock"
REPORT_NUMBER = 3
FREQUENCY = "daily"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Item Description",
    "site":             "Site",
    "location":         "Location",
    "opening":          "Opening",
    "receipt":          "Receipt",
    "issued":           "Issued",
    "closing":          "Closing",
    "uom":              "UOM",
    "batch_no":         "Batch No",
    "item_type":        "Item Type",
    "item_category":    "Item Category",
    "item_group":       "Item Group",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
