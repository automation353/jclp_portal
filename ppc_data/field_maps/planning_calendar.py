"""Field map for the planning calendar (L3).

Source: MpsSS.xlsm → "Mondays of month" sheet.
~12 rows. Week-start dates, first/last day, forecasting months.
"""

TABLE_KEY = "planning_calendar"

FIELD_MAP = {
    "month":            "Month",
    "month_label":      "Month Label",
    "first_day":        "First Day",
    "last_day":         "Last Day",
    "w1_start":         "W1 Start",
    "w2_start":         "W2 Start",
    "w3_start":         "W3 Start",
    "w4_start":         "W4 Start",
    "w5_start":         "W5 Start",
    "working_days":     "Working Days",
    "today":            "Today",
    "forecasting":      "Forecasting",
}
