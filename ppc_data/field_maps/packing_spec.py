"""Field map for the Packing Spec table (W1.15).

Source: Must be built new (only 50 rows exist vs 1,067 packing items).
No source file yet — will be managed through admin or API.
Level: L0
"""

TABLE_KEY = "packing_spec"

FIELD_MAP = {
    "jolly_code":       "Jolly Code",
    "packing_item":     "Packing Item Code",
    "item_type":        "Type",             # box / bag / label / tag
    "qty_per_pack":     "Qty Per Pack",
    "pack_size":        "Pack Size",
    "customer_variant": "Customer Variant",
    "description":      "Description",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
