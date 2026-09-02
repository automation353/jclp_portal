"""Field map for R3SS plan upload (L4).

Source: R3 SS.xlsx → "All" sheet.
One row per part × one column per calendar day.

The R3SS has ~30 FIXED columns on the left (mapped below) plus dynamic
date columns on the right (one per working day of the month). The parser
detects date columns automatically — they are NOT listed in FIELD_MAP.

Rule 1: One Plan Table. R3SS is stored once. Every screen reads from it.
"""

TABLE_KEY = "r3ss_plan"

# Fixed columns — stable keys on the left, Excel headers on the right.
# Day columns are auto-detected by the parser and stored as a nested
# "days" dict: {"2026-08-01": 50, "2026-08-02": 75, ...}
FIELD_MAP = {
    "item_code":         "Item Code",
    "description":       "Description",
    "jolly_code":        "Jolly Code",
    "jolly_size":        "Jolly Size",
    "green_level":       "Green Level",
    "opening_balance":   "Opening Bal. Qty",
    "fg_stock":          "F.G. Stock",
    "pack":              "Pack",
    "disp":              "Disp",
    "to_plan":           "To Plan",
    "total_plan_hw":     "Total Plan HW",
    "total_plan_mit":    "Total Plan MIT",
    "total_plan":        "Total Plan",
    "difference":        "Difference",
    "initial_demand":    "Initial Demand",
    "additional_demand": "Additional Demand",
    "total_demand":      "Total Demand",
    "w1":                "W1",
    "w2":                "W2",
    "w3":                "W3",
    "w4":                "W4",
    "w5":                "W5",
    "cutting":           "Cutting",
    "section":           "Section",
    "mto_mts":           "MTO / MTS",
    "product_group":     "Product Group",
    "family":            "Family",
    "asp":               "ASP",
    "backlog":           "Backlog",
    "plant":             "Plant",
    "category":          "Category",
    "priority":          "Priority",
}
