"""Parser for Process File.xlsx → route_master table (W1.4).

The sheet is a MATRIX: one column block per family. Each block has
columns like Operation Seq, Operation Name, Machine/Line. The parser
must transpose this matrix into rows.

If the sheet is already in row format (one row per operation per
family), we use the standard extract_rows instead.
Level: L0
"""

import logging

from openpyxl import load_workbook

from ..field_maps.route_master import FIELD_MAP, TABLE_KEY
from .base import clean_cell, detect_header_row, extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def _try_row_format(file_path, sheet_name):
    """Try parsing as standard row-per-record format first."""
    try:
        rows = extract_rows(file_path, sheet_name, FIELD_MAP)
        if len(rows) > 5:
            return rows
    except (ValueError, Exception):
        pass
    return None


def _parse_matrix(file_path, sheet_name):
    """Parse the matrix format: one column block per family.

    Scans the header row for repeating patterns (Operation Seq,
    Operation Name, Machine/Line) and transposes each block into rows.
    """
    wb = load_workbook(file_path, data_only=True, read_only=True)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    # Read all rows into memory (matrix files are usually small)
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not all_rows:
        return []

    # Find the header row (usually row 0 or 1)
    header_row = None
    header_idx = 0
    op_keywords = {"operation", "op seq", "op name", "machine", "line"}

    for idx, row in enumerate(all_rows[:5]):
        cells = [str(c).strip().lower() for c in row if c]
        if any(kw in " ".join(cells) for kw in op_keywords):
            header_row = row
            header_idx = idx
            break

    if header_row is None:
        log.warning("Could not find header row in matrix format")
        return []

    # Detect column blocks: look for "Family" or family names in a row
    # above the header, or in the header itself
    family_row = all_rows[max(0, header_idx - 1)] if header_idx > 0 else header_row

    # Build operation rows from data below header
    rows = []
    current_family = ""

    for data_row in all_rows[header_idx + 1:]:
        record = {}
        any_value = False

        for col_idx, cell in enumerate(data_row):
            v = clean_cell(cell)
            if v is None:
                continue

            # Try to map by header
            if col_idx < len(header_row) and header_row[col_idx]:
                header = str(header_row[col_idx]).strip()
                # Match against known field map values
                for key, label in FIELD_MAP.items():
                    if label.lower() in header.lower() or header.lower() in label.lower():
                        record[key] = v
                        any_value = True
                        break

            # Check family row for family name
            if col_idx < len(family_row) and family_row[col_idx]:
                fam = str(family_row[col_idx]).strip()
                if fam and fam != str(header_row[col_idx] or "").strip():
                    current_family = fam

        if any_value:
            if "family" not in record and current_family:
                record["family"] = current_family
            rows.append(record)

    return rows


def parse(file_path, sheet_name=None):
    """Parse Process File. Tries row format first, falls back to
    matrix transpose."""
    # Try standard row format first
    rows = _try_row_format(file_path, sheet_name)
    if rows:
        log.info("Parsed %d route rows (row format) from %s", len(rows), file_path)
        return rows

    # Fall back to matrix format
    rows = _parse_matrix(file_path, sheet_name)
    log.info("Parsed %d route rows (matrix format) from %s", len(rows), file_path)
    return rows
