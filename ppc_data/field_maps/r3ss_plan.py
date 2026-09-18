"""Field map for R3SS plan upload (L4).

Source: R3 SS.xlsx → "All" sheet.
One row per part × one column per calendar day.

The R3SS has ~30 FIXED columns on the left (mapped below) plus dynamic
date columns on the right (one per working day of the month). The parser
detects date columns automatically — they are NOT listed in FIELD_MAP.

Rule 1: One Plan Table. R3SS is stored once. Every screen reads from it.
"""

TABLE_KEY = "r3ss_plan"

# Fixed columns — stable keys on the left, R3SS Excel headers on the right.
# Column names match the R3SS Excel "All" sheet exactly (word-for-word).
# Day columns are auto-detected by the parser and stored as a nested
# "days" dict: {"2026-08-01": 50, "2026-08-02": 75, ...}
FIELD_MAP = {
    "family":            "Family",
    "category":          "Customer",
    "description":       "Cust Part No",
    "jolly_size":        "JollySize",
    "teeth":             "No of Teeth",
    "strokes":           "No of Strokes",
    "item_code":         "ERP Code",
    "jolly_code":        "Jolly Code",
    "mto_mts":           "MTO/ MTS",
    "green_level":       "Green Level",
    "opening_balance":   "Opening Balance",
    "fg_stock":          "FG",
    "pack":              "Pack",
    "disp":              "Disp",
    "to_plan":           "To Plan",
    "total_plan":        "Total Plan\n(HW + MIT)",
    "difference":        "Difference",
    "initial_demand":    "Initial",
    "additional_demand": "Additional",
    "total_demand":      "Total",
    "w1":                "Week1",
    "w2":                "Week2",
    "w3":                "Week3",
    "w4":                "Week4",
    "w5":                "Week5",
    "cutting":           "Cutting",
}

# Alternative Excel headers found in production R3SS files.
# The parser checks these when a column doesn't match FIELD_MAP values.
HEADER_ALIASES = {
    # Older/variant names → internal key
    "Item Code":             "item_code",
    "Description":           "description",
    "Jolly Size":            "jolly_size",
    "Stamping":              "strokes",
    "Opening Bal. Qty":      "opening_balance",
    "Opening Bal":           "opening_balance",
    "F.G. Stock":            "fg_stock",
    "F.G.":                  "fg_stock",
    "FG Stock":              "fg_stock",
    "Initial Demand":        "initial_demand",
    "Additional Demand":     "additional_demand",
    "Total Demand":          "total_demand",
    "MTO/MTS":               "mto_mts",
    "MTO / MTS":             "mto_mts",
    "Total Plan (HW+MIT)":   "total_plan",
    "Total Plan(HW+MIT)":    "total_plan",
    "Total Plan":            "total_plan",
    "W1":                    "w1",
    "W2":                    "w2",
    "W3":                    "w3",
    "W4":                    "w4",
    "W5":                    "w5",
    "Week 1":                "w1",
    "Week 2":                "w2",
    "Week 3":                "w3",
    "Week 4":                "w4",
    "Week 5":                "w5",
    "Category":              "category",
}
