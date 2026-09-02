"""Field map for MPS Schedule Form upload (L3).

Source: MpsSS.xlsm → "Schedule Form" sheet.
~1,500 rows, ~50 columns. THE master production schedule.
"""

TABLE_KEY = "mps_schedule"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Description",
    "family":           "Family",
    "product_group":    "Product Group",
    "section":          "Section",
    "category":         "MTO/MTS",
    "atmc_group":       "ATMC Group",
    "priority":         "Priority",
    # Demand
    "avg_month_demand": "Avg Month Demand",
    "month_demand":     "Month Demand",
    "net_requirement":  "Net Requirement",
    # Stock / WIP
    "fg_stock":         "FG Stock",
    "wip":              "WIP",
    "safety_stock":     "Safety Stock",
    "pab":              "PAB",          # Projected Available Balance
    # EBQ & batching
    "ebq":              "EBQ",
    "batch_qty":        "Batch Qty",
    # Week buckets
    "w1_qty":           "W1",
    "w2_qty":           "W2",
    "w3_qty":           "W3",
    "w4_qty":           "W4",
    "w5_qty":           "W5",
    "total_plan":       "Total Plan",
    # Lead time
    "mfg_lead_time":    "Mfg LT",
    # Valuation
    "rate":             "Rate",
    "amount":           "Amount",
    # UOM
    "uom":              "UOM",
    "plant":            "Plant",
}
