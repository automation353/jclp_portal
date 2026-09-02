"""ERP Report #8 — Production Booked FG (daily).

Day-wise FG produced qty per item (NOT month total).
Critical for: R3SS production, DPR, adherence.
"""

TABLE_KEY = "erp_prod_fg"
REPORT_NUMBER = 8
FREQUENCY = "daily"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Item Description",
    "site":             "Site",
    "production_date":  "Production Date",
    "qty":              "Qty",
    "uom":              "UOM",
    "batch_no":         "Batch No",
    "section":          "Section",
    "line":             "Line",
    "shift":            "Shift",
    "djr_no":           "DJR No",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
