"""Field map for the Demand Freeze upload (L2).

Source: Forecast file → "Initial Demand" sheet.
One row per item per month. Once frozen, the initial_qty becomes
immutable (Rule 3).
"""

TABLE_KEY = "demand_freeze"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Item Description",
    "family":           "Family",
    "product_group":    "Product Group",
    "category":         "Category",         # MTO / MTS
    "month":            "Month",            # YYYY-MM
    "initial_qty":      "Demand Qty",
    "uom":              "UOM",
    "customer":         "Customer",
    "plant":            "Plant",
}
