"""Field map for demand / dispatch history uploads (L2).

Source: Dispatch Trends.xlsx — sheets: Demand, Dispatch, Packing,
Planning, Data, Sheet4, Master Data.
~5,000 rows. Per-part monthly demand/packing/dispatch from 2021.
"""

TABLE_KEY = "demand_history"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Description",
    "family":           "Family",
    "product_group":    "Product Group",
    "category":         "MTO/MTS",
    "customer":         "Customer",
    "month":            "Month",
    "demand_qty":       "Demand",
    "dispatch_qty":     "Dispatch",
    "packing_qty":      "Packing",
    "rfd_qty":          "RFD",
    "excess_qty":       "Excess",
    "rate":             "Rate",
    "value":            "Value",
    "trend_6m":         "6M Trend",
    "plant":            "Plant",
}
