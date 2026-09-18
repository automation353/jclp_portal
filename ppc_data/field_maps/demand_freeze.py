"""Field map for the Demand Freeze upload (L2).

Source: Forecast file — all sheets (Initial Demand, Additional W*, Reduced Demand).
Each row carries a txn_type: INITIAL / ADDITION / REDUCTION.
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
    "qty":              "Qty",
    "txn_type":         "Txn Type",         # INITIAL / ADDITION / REDUCTION
    "week":             "Week",             # sheet name for additions (W1, W2…)
    "uom":              "UOM",
    "customer":         "Customer",
    "plant":            "Plant",
}
