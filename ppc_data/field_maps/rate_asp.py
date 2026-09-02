"""Field map for the Rate / ASP table (W1.16).

Source file: ASP for FG.xlsx, Sheet "Sheet1"
Rows: ~1,837
Simple key-value load.
Level: L0
"""

TABLE_KEY = "rate_asp"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Description",
    "asp":              "ASP",
    "standard_rate":    "Standard Rate",
    "landed_rate":      "Landed Rate",
    "uom":              "UOM",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
