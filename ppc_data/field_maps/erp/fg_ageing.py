"""ERP Report #17 — FG Ageing (monthly).

Slow-moving reporting. Not required for plan — load last.
"""

TABLE_KEY = "erp_fg_ageing"
REPORT_NUMBER = 17
FREQUENCY = "monthly"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Item Description",
    "site":             "Site",
    "stock_qty":        "Stock Qty",
    "stock_value":      "Stock Value",
    "last_movement":    "Last Movement Date",
    "ageing_days":      "Ageing Days",
    "ageing_bracket":   "Ageing Bracket",
    "uom":              "UOM",
    "item_group":       "Item Group",
    "category":         "Category",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
