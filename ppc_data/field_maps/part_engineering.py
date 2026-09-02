"""Field map for the Part Engineering table (W1.12).

Source file: MpsSS.xlsm + T-Bolt BOM master
T-Bolt BOM master (63 columns) is the richest source.
Level: L0
"""

TABLE_KEY = "part_engineering"

FIELD_MAP = {
    "jolly_code":       "Jolly Code",
    "jolly_size":       "Jolly Size",
    "description":      "Description",
    "open_dia":         "Open Dia",
    "close_dia":        "Close Dia",
    "cut_length":       "Cut Length",
    "teeth":            "Teeth",
    "strokes":          "Strokes",
    "strip_weight":     "Strip Weight",
    "rm_size":          "RM Size",
    "rm_part_code":     "RM Part Code",
    "semi_code":        "Semi Finished Code",
    "wire_dia":         "Wire Dia",
    "family":           "Family",
    "section":          "Section",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
