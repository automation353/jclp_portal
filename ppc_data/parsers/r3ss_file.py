"""Parser for R3 SS.xlsx — THE production plan (L4).

Source: R3 SS.xlsx
  "All" sheet → r3ss_plan  (dynamic date columns)
  "Sheet1"    → r3ss_summary (fixed columns)

The dynamic date column problem:
  R3SS has ~30 fixed columns on the left plus one column per working day
  of the month on the right. In August that might be 26 day columns; in
  February 20. The parser must:

  1. Read the header row and identify fixed vs date columns.
  2. Store fixed columns as flat keys.
  3. Store day columns as a nested "days" dict:
     {"days": {"2026-08-01": 50, "2026-08-02": 75, ...}}
  4. Validate: sum of day values ≈ total plan (flag mismatch).
"""

import logging
import re
from datetime import datetime

from openpyxl import load_workbook

from ..field_maps.r3ss_plan import FIELD_MAP as PLAN_FIELDS
from ..field_maps.r3ss_summary import FIELD_MAP as SUMMARY_FIELDS
from .base import clean_cell, detect_header_row

TABLE_KEY = "r3ss_plan"

log = logging.getLogger(__name__)

# Date patterns we might see in R3SS column headers.
# Examples: "1-Aug", "02-Aug", "1/8", "01/08/2026", "2026-08-01", "Aug-01"
_DATE_PATTERNS = [
    # "1-Aug", "01-Aug", "1-August"
    re.compile(
        r'^(\d{1,2})[-/\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*$',
        re.IGNORECASE,
    ),
    # "Aug-1", "Aug-01"
    re.compile(
        r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[-/\s](\d{1,2})$',
        re.IGNORECASE,
    ),
    # "01/08/2026", "1/8/2026", "01-08-2026"
    re.compile(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$'),
    # "2026-08-01"
    re.compile(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$'),
    # "01/08", "1/8" (no year — assume current context)
    re.compile(r'^(\d{1,2})[-/](\d{1,2})$'),
]

_MONTH_ABBR = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def _parse_date_header(header_str, hint_year=None):
    """Try to parse a column header as a date. Returns ISO date string
    (YYYY-MM-DD) or None.

    hint_year is used when the header doesn't include a year.
    """
    if header_str is None:
        return None

    s = str(header_str).strip()
    if not s:
        return None

    # If it's already a datetime object (openpyxl sometimes returns these)
    if hasattr(header_str, 'year') and hasattr(header_str, 'month'):
        try:
            return header_str.strftime('%Y-%m-%d')
        except Exception:
            pass

    year = hint_year or datetime.now().year

    # Pattern 1: "1-Aug", "02-Aug"
    m = _DATE_PATTERNS[0].match(s)
    if m:
        day = int(m.group(1))
        mon = _MONTH_ABBR.get(m.group(2)[:3].lower())
        if mon:
            return f"{year}-{mon:02d}-{day:02d}"

    # Pattern 2: "Aug-1", "Aug-01"
    m = _DATE_PATTERNS[1].match(s)
    if m:
        mon = _MONTH_ABBR.get(m.group(1)[:3].lower())
        day = int(m.group(2))
        if mon:
            return f"{year}-{mon:02d}-{day:02d}"

    # Pattern 3: "01/08/2026"
    m = _DATE_PATTERNS[2].match(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Indian format: DD/MM/YYYY
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"{y}-{mo:02d}-{d:02d}"

    # Pattern 4: "2026-08-01"
    m = _DATE_PATTERNS[3].match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"{y}-{mo:02d}-{d:02d}"

    # Pattern 5: "01/08" or "1/8" (DD/MM, no year)
    m = _DATE_PATTERNS[4].match(s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"{year}-{mo:02d}-{d:02d}"

    return None


def _detect_plan_month(date_headers):
    """Infer the plan month from detected date columns.
    Returns (year, month) tuple or None.
    """
    if not date_headers:
        return None
    # Most common month across all dates
    months = {}
    for iso in date_headers.values():
        ym = iso[:7]  # "YYYY-MM"
        months[ym] = months.get(ym, 0) + 1
    if months:
        return max(months, key=months.get)
    return None


def parse(file_path):
    """Parse R3SS!All sheet with dynamic date columns.
    Returns list of dicts with fixed keys + nested "days" dict.
    """
    wb = load_workbook(file_path, data_only=True, read_only=True)

    # Find the "All" sheet
    sheet_name = None
    for sn in wb.sheetnames:
        if sn.lower().strip() in ('all', 'r3ss', 'r3 ss', 'plan'):
            sheet_name = sn
            break
    if sheet_name is None:
        # Fall back to first sheet
        sheet_name = wb.sheetnames[0]
        log.warning("No 'All' sheet found in R3SS, using: %s", sheet_name)

    ws = wb[sheet_name]

    # Build reverse map for fixed columns
    header_to_key = {v.strip(): k for k, v in PLAN_FIELDS.items()}
    known_headers = list(header_to_key.keys())

    # Step 1: Find the header row
    header_row_idx, col_map = detect_header_row(ws, known_headers)

    # Step 2: Classify every column in the header row as fixed or date
    fixed_cols = {}   # col_idx -> stable_key
    date_cols = {}    # col_idx -> ISO date string

    # Read the full header row to get ALL columns
    header_row = None
    for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
        if row_idx == header_row_idx:
            header_row = row
            break

    if header_row is None:
        wb.close()
        raise ValueError("Could not read header row")

    # First, map known fixed columns
    for col_idx, header_str in col_map.items():
        key = header_to_key.get(header_str.strip())
        if key:
            fixed_cols[col_idx] = key

    # Now try to parse remaining columns as dates
    # Guess the year from fixed date columns or current year
    hint_year = datetime.now().year

    for col_idx, cell_val in enumerate(header_row):
        if col_idx in fixed_cols:
            continue
        iso = _parse_date_header(cell_val, hint_year)
        if iso:
            date_cols[col_idx] = iso

    # Refine year hint from detected dates (first date might have year)
    if date_cols:
        first_date = min(date_cols.values())
        hint_year = int(first_date[:4])
        # Re-detect dates with correct year for those without one
        for col_idx in list(date_cols.keys()):
            iso = _parse_date_header(header_row[col_idx], hint_year)
            if iso:
                date_cols[col_idx] = iso

    plan_month = _detect_plan_month(date_cols)

    log.info(
        "R3SS header: %d fixed cols, %d date cols, plan month: %s",
        len(fixed_cols), len(date_cols), plan_month,
    )

    # Step 3: Extract data rows
    rows = []
    mismatch_count = 0

    for row_idx, raw_row in enumerate(ws.iter_rows(values_only=True)):
        if row_idx <= header_row_idx:
            continue

        record = {}
        days = {}
        any_value = False

        # Fixed columns
        for col_idx, key in fixed_cols.items():
            v = clean_cell(raw_row[col_idx]) if col_idx < len(raw_row) else None
            if v is not None:
                record[key] = v
                any_value = True

        # Date columns → nested "days" dict
        for col_idx, iso_date in date_cols.items():
            v = clean_cell(raw_row[col_idx]) if col_idx < len(raw_row) else None
            if v is not None:
                # Coerce to number if possible
                try:
                    v = float(v) if not isinstance(v, (int, float)) else v
                except (ValueError, TypeError):
                    pass
                days[iso_date] = v

        if days:
            record["days"] = days

        # Must have item_code to be valid
        if not any_value or not record.get("item_code"):
            continue

        # Step 4: Validate — sum of days ≈ total_plan
        if days and record.get("total_plan") is not None:
            day_sum = sum(
                v for v in days.values()
                if isinstance(v, (int, float))
            )
            try:
                total = float(record["total_plan"])
                if total > 0 and abs(day_sum - total) > max(1, total * 0.02):
                    record["_day_sum_mismatch"] = {
                        "day_sum": day_sum,
                        "total_plan": total,
                        "diff": round(day_sum - total, 2),
                    }
                    mismatch_count += 1
            except (ValueError, TypeError):
                pass

        # Add plan month metadata
        if plan_month:
            record["_plan_month"] = plan_month

        rows.append(record)

    wb.close()

    if mismatch_count:
        log.warning(
            "R3SS: %d rows have day-sum ≠ total plan", mismatch_count
        )

    log.info(
        "Parsed %d R3SS plan rows from %s!%s (%d date cols, month=%s)",
        len(rows), file_path, sheet_name, len(date_cols), plan_month,
    )
    return rows


def parse_summary(file_path):
    """Parse R3SS!Sheet1 (summary). Simple fixed-column parse."""
    wb = load_workbook(file_path, data_only=True, read_only=True)

    sheet_name = None
    for sn in wb.sheetnames:
        sn_lower = sn.lower().strip()
        if sn_lower in ('sheet1', 'summary', 'stock summary'):
            sheet_name = sn
            break
    if sheet_name is None:
        # Try second sheet if it exists
        if len(wb.sheetnames) > 1:
            sheet_name = wb.sheetnames[1]
        else:
            wb.close()
            return []

    ws = wb[sheet_name]

    header_to_key = {v.strip(): k for k, v in SUMMARY_FIELDS.items()}
    known_headers = list(header_to_key.keys())

    try:
        header_row_idx, col_map = detect_header_row(ws, known_headers)
    except ValueError:
        wb.close()
        log.warning("No summary headers found in %s!%s", file_path, sheet_name)
        return []

    col_to_key = {}
    for col_idx, header_str in col_map.items():
        key = header_to_key.get(header_str.strip())
        if key:
            col_to_key[col_idx] = key

    rows = []
    for row_idx, raw_row in enumerate(ws.iter_rows(values_only=True)):
        if row_idx <= header_row_idx:
            continue
        record = {}
        any_value = False
        for col_idx, key in col_to_key.items():
            v = clean_cell(raw_row[col_idx]) if col_idx < len(raw_row) else None
            if v is not None:
                record[key] = v
                any_value = True
        if any_value:
            rows.append(record)

    wb.close()
    log.info("Parsed %d R3SS summary rows", len(rows))
    return rows
