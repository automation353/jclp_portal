"""ERP Report #9 — Production Booked Semi-finished (daily).

Semi-finished items with DJR number.
Critical for: WIP in MPS, semi-finish tracking.
"""

TABLE_KEY = "erp_prod_semi"
REPORT_NUMBER = 9
FREQUENCY = "daily"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Item Description",
    "site":             "Site",
    "production_date":  "Production Date",
    "qty":              "Qty",
    "uom":              "UOM",
    "batch_no":         "Batch No",
    "djr_no":           "DJR No",
    "parent_item":      "Parent Item",
    "section":          "Section",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
