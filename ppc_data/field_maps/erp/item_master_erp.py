"""ERP Report #1 — Item Master (on-change).

Refreshes W1.1. Cross-check new items against family hierarchy.
"""

TABLE_KEY = "erp_item_master"
REPORT_NUMBER = 1
FREQUENCY = "on_change"

FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Item Description",
    "item_type":        "Item Type",
    "category":         "Item Category",
    "group":            "Item Group",
    "hsn":              "HSN Code",
    "site":             "Site",
    "status":           "Status",
    "uom":              "UOM",
    "sub_group":        "Sub Group",
    "created_date":     "Created Date",
    "modified_date":    "Modified Date",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
