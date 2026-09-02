"""Field map for the Family Hierarchy table (W1.2).

Sources: Product Group Mapping.xlsx + Monitoring.xlsx!Family Group
Merged into one table. Most reused lookup in the system.
Level: L0
"""

TABLE_KEY = "family_hierarchy"

FIELD_MAP = {
    "item_code":            "Item Code",
    "description":          "Item Description",
    "jolly_size":           "Jolly Size",
    "jolly_code":           "Jolly Code",
    "family":               "Family",
    "product_group":        "Product Group",
    "section":              "Section",
    "customer_category":    "Customer Category",
    "sub_group":            "Sub Group",
    "item_type":            "Item Type",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
