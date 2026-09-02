"""ERP Report #15 — Material Issue / GIN (daily).

Goods inward, material issue against requisitions.
Critical for: RM day book, requisition closure.
"""

TABLE_KEY = "erp_material_issue"
REPORT_NUMBER = 15
FREQUENCY = "daily"

FIELD_MAP = {
    "issue_no":         "Issue No",
    "issue_date":       "Issue Date",
    "item_code":        "Item Code",
    "description":      "Item Description",
    "qty":              "Qty",
    "uom":              "UOM",
    "requisition_no":   "Requisition No",
    "from_location":    "From Location",
    "to_location":      "To Location",
    "batch_no":         "Batch No",
    "site":             "Site",
    "item_type":        "Item Type",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
