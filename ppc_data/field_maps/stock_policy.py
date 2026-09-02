"""Field map for the Stock Policy / Green Levels table (W1.14).

Source files: Green Level RM.xlsx, Green Level CP.xlsx,
             Green Level Packing.xlsx — merged into one table.
BLOCKED by Decision #2 (ERP vs portal ownership).
Level: L0
"""

TABLE_KEY = "stock_policy"

FIELD_MAP = {
    "item_code":            "Item Code",
    "description":          "Description",
    "plant":                "Plant",
    "item_type":            "Item Type",        # RM / CP / PM
    "blue_level":           "Blue Level",
    "green_level":          "Green Level",
    "yellow_level":         "Yellow Level",
    "red_level":            "Red Level",
    "reorder_qty":          "Reorder Qty",
    "safety_stock":         "Safety Stock",
    "daily_consumption":    "Daily Consumption",
    "lt_consumption":       "Lead Time Consumption",
    "monthly_avg":          "Monthly Avg",
    "policy_owner":         "Policy Owner",
    "last_reviewed":        "Last Reviewed",
}

HEADER_TO_KEY = {v: k for k, v in FIELD_MAP.items()}
