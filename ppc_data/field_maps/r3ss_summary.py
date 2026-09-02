"""Field map for R3SS summary (L4).

Source: R3 SS.xlsx → "Sheet1" (summary).
FG stock level count summary by family (R/Y/G/B).
Simple fixed-column parse — no dynamic date columns.
"""

TABLE_KEY = "r3ss_summary"

FIELD_MAP = {
    "family":            "Family",
    "product_group":     "Product Group",
    "section":           "Section",
    "total_items":       "Total Items",
    "red_count":         "Red",
    "yellow_count":      "Yellow",
    "green_count":       "Green",
    "blue_count":        "Blue",
    "red_value":         "Red Value",
    "yellow_value":      "Yellow Value",
    "green_value":       "Green Value",
    "blue_value":        "Blue Value",
    "total_value":       "Total Value",
    "plant":             "Plant",
}
