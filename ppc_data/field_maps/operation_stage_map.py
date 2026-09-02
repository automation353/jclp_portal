"""Field map for the Operation Stage Map table (W1.5).

Source file: In process-Rejection.xlsx
Sheets: "Stage List" (77 ops) + "Process Sheet"
Level: L0
"""

TABLE_KEY = "operation_stage_map"

FIELD_MAP = {
    "op_name":      "Operation Name",
    "stage":        "Stage",            # 1 / 2 / 3
    "family":       "Family",
    "section":      "Section",
    "op_seq":       "Operation Seq",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
