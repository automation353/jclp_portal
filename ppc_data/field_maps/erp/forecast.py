"""ERP Report #11 — Sales Forecast (monthly).

Forecast number + from/to dates. Feeds demand freeze (L2).
"""

TABLE_KEY = "erp_forecast"
REPORT_NUMBER = 11
FREQUENCY = "monthly"

FIELD_MAP = {
    "forecast_no":      "Forecast No",
    "item_code":        "Item Code",
    "description":      "Item Description",
    "from_date":        "From Date",
    "to_date":          "To Date",
    "forecast_qty":     "Forecast Qty",
    "uom":              "UOM",
    "customer_code":    "Customer Code",
    "customer_name":    "Customer Name",
    "mto_mts":          "MTO / MTS",
    "status":           "Status",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
