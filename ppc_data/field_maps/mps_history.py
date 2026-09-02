"""Field map for MPS history data (L3).

Source: MpsSS.xlsm → "Demand Data" + "Dispatch Data" sheets.
Monthly demand and dispatch history with rate, value, category.
~3,000 rows.
"""

TABLE_KEY = "mps_history"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Description",
    "family":           "Family",
    "product_group":    "Product Group",
    "category":         "MTO/MTS",
    "month":            "Month",
    "demand_qty":       "Demand Qty",
    "dispatch_qty":     "Dispatch Qty",
    "rate":             "Rate",
    "value":            "Value",
    "section":          "Section",
    "plant":            "Plant",
}
