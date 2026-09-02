"""Field map for the Customer-Part table (W1.13).

Source file: R3 SS.xlsx + SO Tracking Master
MTO/MTS is per customer-part combination, not per part alone.
Level: L0
"""

TABLE_KEY = "customer_part"

FIELD_MAP = {
    "customer_code":    "Customer Code",
    "customer_name":    "Customer Name",
    "customer_part_no": "Customer Part No",
    "jolly_code":       "Jolly Code",
    "jolly_size":       "Jolly Size",
    "erp_code":         "ERP Code",
    "mto_mts":          "MTO / MTS",
    "dispatch_location": "Dispatch Location",
    "description":      "Description",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
