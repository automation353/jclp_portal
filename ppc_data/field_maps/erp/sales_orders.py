"""ERP Report #12 — Sales Orders (daily).

Open orders with delivery date, customer, quantity.
Critical for: MTO demand, SO tracking.
"""

TABLE_KEY = "erp_sales_orders"
REPORT_NUMBER = 12
FREQUENCY = "daily"

FIELD_MAP = {
    "order_no":         "Order No",
    "order_date":       "Order Date",
    "item_code":        "Item Code",
    "description":      "Item Description",
    "customer_code":    "Customer Code",
    "customer_name":    "Customer Name",
    "order_qty":        "Order Qty",
    "dispatched_qty":   "Dispatched Qty",
    "pending_qty":      "Pending Qty",
    "delivery_date":    "Delivery Date",
    "uom":              "UOM",
    "rate":             "Rate",
    "amount":           "Amount",
    "status":           "Status",
    "mto_mts":          "MTO / MTS",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
