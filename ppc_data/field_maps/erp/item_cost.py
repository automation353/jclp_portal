"""ERP Report #16 — Item Cost (monthly).

Valuation of plan and ready-for-dispatch.
"""

TABLE_KEY = "erp_item_cost"
REPORT_NUMBER = 16
FREQUENCY = "monthly"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Item Description",
    "standard_cost":    "Standard Cost",
    "actual_cost":      "Actual Cost",
    "landed_cost":      "Landed Cost",
    "uom":              "UOM",
    "cost_date":        "Cost Date",
    "item_type":        "Item Type",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
