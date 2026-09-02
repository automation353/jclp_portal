"""ERP Report #14 — Pending Purchase Requisitions (daily).

PR follow-up at L7.
"""

TABLE_KEY = "erp_pending_pr"
REPORT_NUMBER = 14
FREQUENCY = "daily"

FIELD_MAP = {
    "pr_no":            "PR No",
    "pr_date":          "PR Date",
    "item_code":        "Item Code",
    "description":      "Item Description",
    "pr_qty":           "PR Qty",
    "approved_qty":     "Approved Qty",
    "po_qty":           "PO Qty",
    "pending_qty":      "Pending Qty",
    "uom":              "UOM",
    "requester":        "Requester",
    "status":           "Status",
    "item_type":        "Item Type",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
