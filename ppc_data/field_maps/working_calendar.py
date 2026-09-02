"""Field map for the Working Calendar table (W1.10).

Source: UI form (must be maintained 1 year ahead)
No file parser — managed through admin or API.
Weeks are PPC weeks (not ISO calendar weeks).
Level: L0
"""

TABLE_KEY = "working_calendar"

FIELD_MAP = {
    "date":             "Date",
    "day_of_week":      "Day of Week",
    "is_working":       "Is Working",
    "shift_pattern":    "Shift Pattern",
    "week_bucket":      "Week Bucket",      # W1-W5
    "month":            "Month",
    "fy":               "FY",
    "holiday_reason":   "Holiday Reason",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
