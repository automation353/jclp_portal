"""ERP Report #13 — Pending POs CP/RM (daily).

Pending purchase order qty, supplier, date.
Critical for: Purchase Dashboard, shortage flags.
"""

TABLE_KEY = "erp_pending_po"
REPORT_NUMBER = 13
FREQUENCY = "daily"

FIELD_MAP = {
    "po_no":            "PO No",
    "po_date":          "PO Date",
    "item_code":        "Item Code",
    "description":      "Item Description",
    "supplier_code":    "Supplier Code",
    "supplier_name":    "Supplier Name",
    "po_qty":           "PO Qty",
    "received_qty":     "Received Qty",
    "pending_qty":      "Pending Qty",
    "due_date":         "Due Date",
    "uom":              "UOM",
    "rate":             "Rate",
    "amount":           "Amount",
    "status":           "Status",
    "item_type":        "Item Type",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
