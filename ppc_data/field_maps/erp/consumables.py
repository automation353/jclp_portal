"""ERP Report #7 — Consumables Stock (weekly).

Not needed for plan — load after everything else works.
"""

TABLE_KEY = "erp_consumables"
REPORT_NUMBER = 7
FREQUENCY = "weekly"

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
    "category":         "Category",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
