"""ERP Report #2 — BOM Master (on-change).

Refreshes W1.11. Validate new BOMs have all components in item master.
"""

TABLE_KEY = "erp_bom"
REPORT_NUMBER = 2
FREQUENCY = "on_change"

FIELD_MAP = {
    "bom_code":         "BOM Code",
    "parent_item":      "Item Code",
    "component":        "Component",
    "component_desc":   "Component Description",
    "bom_qty":          "BOM Qty",
    "uom":              "BOM UOM",
    "scrap_pct":        "Scrap%",
    "status":           "Status",
    "effective_from":   "Effective From",
    "effective_to":     "Effective To",
    "modified_date":    "Modified Date",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
