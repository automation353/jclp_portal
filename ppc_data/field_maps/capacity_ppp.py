"""Field map for the Capacity / PPP table (W1.6).

Sources: Production Targets.xlsx + Monitoring.xlsx!Family Group
         + Dispatch Trends.xlsx!Master Data
PPC must reconcile the three sources before upload.
Level: L0
"""

TABLE_KEY = "capacity_ppp"

FIELD_MAP = {
    "family":               "Family",
    "product_group":        "Product Group",
    "section":              "Section",
    "capacity_8h":          "Capacity / Shift (8h)",
    "capacity_12h":         "Capacity / Shift (12h)",
    "monthly_capacity":     "Monthly Capacity",
    "manpower_shift":       "Manpower / Shift",
    "target_ppp_8h":        "Target PPP (8h)",
    "target_ppp_12h":       "Target PPP (12h)",
    "working_days":         "Working Days",
    "setups":               "Setups",
    "plant":                "Plant",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
