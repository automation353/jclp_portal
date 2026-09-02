"""ERP Report #6 — Packing Material Stock Statement (daily).

Same structure as CP/RM stock.
Critical for: Purchase Dashboard PM.
"""

TABLE_KEY = "erp_pm_stock"
REPORT_NUMBER = 6
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
    "item_type":            "Item Type",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
