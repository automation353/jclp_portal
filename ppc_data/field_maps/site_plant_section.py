"""Field map for the Site / Plant / Section table (W1.3).

Source: UI form (editable grid, ~30 rows)
No file parser — managed through admin or API.
Level: L0
"""

TABLE_KEY = "site_plant_section"

FIELD_MAP = {
    "plant":        "Plant",            # HW1 / HW2 / MIT / Harisiddhi / Terrace
    "section":      "Section",
    "line_code":    "Line Code",
    "line_name":    "Line Name",
    "shifts":       "Shifts",
    "active_from":  "Active From",
    "active_to":    "Active To",
    "active":       "Active",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
