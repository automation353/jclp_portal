"""Field map for the Route Master table (W1.4).

Source file: Process File.xlsx
NOTE: Sheet is a matrix (one column block per family).
Parser must transpose matrix → rows.
Level: L0
"""

TABLE_KEY = "route_master"

FIELD_MAP = {
    "family":           "Family",
    "op_seq":           "Operation Seq",
    "op_name":          "Operation Name",
    "machine_line":     "Machine / Line",
    "is_semi_output":   "Is Semi Output",
    "cycle_time":       "Cycle Time",
    "setup_time":       "Setup Time",
    "section":          "Section",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
