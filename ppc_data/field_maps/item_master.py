"""Field map for the Item Master table (W1.1).

Source file: Product Group Mapping.xlsx
Sheet: "Sheet0" (or first sheet)
Rows: ~4,822
Level: L0 (foundation master)

This is the spine — every other table references item_code.
"""

TABLE_KEY = "item_master"

# stable_key -> Excel column header string
FIELD_MAP = {
    "item_code":        "Item Code",
    "description":      "Item Description",
    "item_type":        "Item Type",        # FG / Semi / RM / CP / PM
    "category":         "Item Category",
    "group":            "Item Group",
    "hsn":              "HSN Code",
    "site":             "Site",
    "status":           "Status",           # Active / Inactive
    "uom":              "UOM",
    "sub_group":        "Sub Group",
    "product_group":    "Product Group",
}

# Reverse map for the parser: Excel header -> stable key
HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
