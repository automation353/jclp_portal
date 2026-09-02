"""Field map for demand additions/reductions (L2).

Source: Forecast file → "Additional W1", "Additional W2", "Reduced Demand"
sheets. Each row becomes a PPCDemandTransaction record.
"""

TABLE_KEY = "demand_transaction"

FIELD_MAP = {
    "item_code":    "Item Code",
    "description":  "Item Description",
    "family":       "Family",
    "month":        "Month",        # YYYY-MM
    "qty":          "Qty",
    "uom":          "UOM",
    "week":         "Week",         # W1, W2, Additional, etc.
    "reason":       "Reason",
    "customer":     "Customer",
}
