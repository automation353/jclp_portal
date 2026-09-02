"""Field map for the Machine Master table (W1.7).

Source file: Machine Loading data.xlsx
Level: L0
"""

TABLE_KEY = "machine_master"

FIELD_MAP = {
    "machine_code":         "Machine Code",
    "machine_name":         "Machine Name",
    "line":                 "Line",
    "section":              "Section",
    "plant":                "Plant",
    "spm":                  "SPM",
    "capacity_shift":       "Capacity / Shift",
    "alternate_machine":    "Alternate Machine",
    "atmc_group":           "ATMC Group",
    "active":               "Active",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
