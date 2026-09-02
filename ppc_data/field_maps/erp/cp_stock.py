"""ERP Report #4 — CP Stock Statement (daily).

75 columns in ERP, ~42 needed. Same structure as RM/PM stock.
Critical for: Purchase Dashboard CP, material explosion.
"""

TABLE_KEY = "erp_cp_stock"
REPORT_NUMBER = 4
FREQUENCY = "daily"

FIELD_MAP = {
    "item_code":            "Item Code",
    "description":          "Item Description",
    "site":                 "Site",
    "location":             "Location",
    "opening":              "Opening",
    "receipt":              "Receipt",
    "issued":               "Issued",
    "closing":              "Closing",
    "uom":                  "UOM",
    "safety_stock":         "Safety Stock",
    "reorder_qty":          "Reorder Qty",
    "lead_time_days":       "Lead Time Days",
    "daily_consumption":    "Daily Consumption",
    "green_level":          "Green Level",
    "yellow_level":         "Yellow Level",
    "red_level":            "Red Level",
    "current_stock_kg":     "Current Stock in Kg",
    "current_stock_days":   "Current Stock Days",
    "to_be_ordered_qty":    "To Be Ordered Qty",
    "rate":                 "Rate",
    "amount":               "Amount",
    "category":             "Category",
    "group":                "Group",
    "item_type":            "Item Type",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
