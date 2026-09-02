"""Field map for the Reason Codes table (W1.17).

Source: UI form (controlled list — no free text allowed).
Shared across L5 (feasibility), L8 (downtime, rejection).
Level: L0
"""

TABLE_KEY = "reason_codes"

FIELD_MAP = {
    "code":         "Code",
    "text":         "Text",
    "category":     "Category",         # manpower / machine / tool / material / quality / planning
    "applies_to":   "Applies To",       # shortfall / downtime / rejection
    "active":       "Active",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
