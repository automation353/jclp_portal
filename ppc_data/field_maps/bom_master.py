"""Field map for the BOM Master table (W1.11).

Source file: BOM_Item_Template.xlsx
Sheet: "BOM_ItemDetails"
Rows: ~37,149
Level: L0

Planning keys off BOM Code, not Item Code.
"""

TABLE_KEY = "bom_master"

FIELD_MAP = {
    "bom_code":         "BOM Code",
    "parent_item":      "Item Code",
    "component":        "Component",
    "component_desc":   "Component Description",
    "bom_qty":          "BOM Qty",
    "uom":              "BOM UOM",
    "scrap_pct":        "Scrap%",
    "drawing_rev":      "Drawing Revision",
    "co_product_flag":  "Co-Product",
    "bom_type":         "BOM Type",
    "effective_from":   "Effective From",
    "effective_to":     "Effective To",
    "status":           "Status",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
