"""Field map for the Lead Time table (W1.9).

Source file: Lead Time Data.xlsx, Sheet "Sheet2" (1,684 rows)
WARNING: Last updated May 2023 — must be revalidated by PPC.
Level: L0
"""

TABLE_KEY = "lead_time"

FIELD_MAP = {
    "sku":          "SKU",
    "part_code":    "Part Code",
    "description":  "Description",
    "family":       "Family",
    "category":     "Category",         # fast / slow
    "min_lt":       "Min Lead Time",
    "max_lt":       "Max Lead Time",
    "mfg_lt":       "Mfg Lead Time",
    "uom":          "UOM",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
