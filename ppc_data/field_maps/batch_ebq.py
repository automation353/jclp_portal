"""Field map for the Batch / EBQ table (W1.8).

Source file: Monitoring.xlsx sheets "EBQ" + "Batch Qty"
Level: L0
"""

TABLE_KEY = "batch_ebq"

FIELD_MAP = {
    "product_group":    "Product Group",
    "family":           "Family",
    "ebq_qty":          "EBQ Qty",
    "batch_size":       "Batch Size",
    "num_batches":      "No of Batches",
    "atmc_feasible":    "ATMC Feasible",
    "section":          "Section",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
