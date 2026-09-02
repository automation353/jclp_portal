"""ERP Report #10 — FG Issue / Dispatch (daily).

Sales invoice qty by item.
Critical for: R3SS pack/disp, dispatch trends.
BLOCKED by Decision #6 (what filters = "dispatch"?).
"""

TABLE_KEY = "erp_dispatch"
REPORT_NUMBER = 10
FREQUENCY = "daily"

FIELD_MAP = {
    "item_code":            "Item Code",
    "description":          "Item Description",
    "customer_code":        "Customer Code",
    "customer_name":        "Customer Name",
    "invoice_no":           "Invoice No",
    "invoice_date":         "Invoice Date",
    "qty":                  "Qty",
    "uom":                  "UOM",
    "rate":                 "Rate",
    "amount":               "Amount",
    "party_group":          "Party Group",
    "transaction_category": "Transaction Category",
    "dispatch_location":    "Dispatch Location",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
