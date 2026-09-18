"""ERP Report #3b — FG Stock Opening Balance (month-open snapshot).

Same fields as erp_fg_stock, but frozen on day 1 of each month.
Once written, it must not be overwritten until the next month opens.

Spec §2.2: "The FG stock statement taken on day 1 of the month is kept
as a separate landing tab, FG_STOCK_OPEN. Opening balance must not move
when today's stock moves."
"""

TABLE_KEY = "erp_fg_stock_open"
REPORT_NUMBER = 3  # same report, frozen snapshot
FREQUENCY = "monthly_open"

# Same fields as erp_fg_stock — it's the same report, just frozen
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
