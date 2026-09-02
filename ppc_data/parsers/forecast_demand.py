"""Parser for the forecast demand file — Initial Demand sheet (L2).

Source: Forecast file uploaded by PPC.
The "Initial Demand" sheet contains one row per item per month.
This parser extracts rows for the demand freeze.

Also handles "Additional W*" and "Reduced Demand" sheets as
demand transactions when present.
"""

import logging

from openpyxl import load_workbook

from ..field_maps.demand_freeze import FIELD_MAP
from .base import clean_cell, detect_header_row

TABLE_KEY = "demand_freeze"

log = logging.getLogger(__name__)

# Sheets that carry the initial demand data
_INITIAL_SHEETS = ["Initial Demand", "Demand", "Forecast", "Sheet1"]

# Sheets that carry additions/reductions
_TX_SHEETS_ADD = ["Additional", "Addition"]
_TX_SHEETS_REDUCE = ["Reduced Demand", "Reduction"]


def _find_sheet(wb, candidates):
    """Find the first sheet whose name contains one of the candidates."""
    for sn in wb.sheetnames:
        sn_lower = sn.lower().strip()
        for cand in candidates:
            if cand.lower() in sn_lower:
                return sn
    return None


def parse(file_path):
    """Parse the Initial Demand sheet. Returns list of dicts keyed by
    stable field keys from the demand_freeze field map.
    """
    wb = load_workbook(file_path, data_only=True, read_only=True)

    # Find the initial demand sheet
    sheet_name = _find_sheet(wb, _INITIAL_SHEETS)
    if sheet_name is None:
        # Fall back to first sheet
        sheet_name = wb.sheetnames[0]
        log.warning("No demand sheet found, using first sheet: %s", sheet_name)

    ws = wb[sheet_name]

    # Build reverse map
    header_to_key = {v.strip(): k for k, v in FIELD_MAP.items()}
    known_headers = list(header_to_key.keys())

    header_row_idx, col_map = detect_header_row(ws, known_headers)

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
        # Must have at least item_code and a qty
        if any_value and record.get("item_code"):
            rows.append(record)

    wb.close()
    log.info("Parsed %d demand rows from %s!%s", len(rows), file_path, sheet_name)
    return rows


def parse_transactions(file_path):
    """Parse addition/reduction sheets. Returns list of dicts with an
    extra 'tx_type' key ('add' or 'reduce').
    """
    from ..field_maps.demand_transaction import FIELD_MAP as TX_MAP

    wb = load_workbook(file_path, data_only=True, read_only=True)
    tx_header_to_key = {v.strip(): k for k, v in TX_MAP.items()}
    known_headers = list(tx_header_to_key.keys())

    all_txns = []

    for sn in wb.sheetnames:
        sn_lower = sn.lower().strip()

        tx_type = None
        for cand in _TX_SHEETS_ADD:
            if cand.lower() in sn_lower:
                tx_type = "add"
                break
        if tx_type is None:
            for cand in _TX_SHEETS_REDUCE:
                if cand.lower() in sn_lower:
                    tx_type = "reduce"
                    break
        if tx_type is None:
            continue

        ws = wb[sn]
        try:
            header_row_idx, col_map = detect_header_row(ws, known_headers)
        except ValueError:
            log.warning("Skipping sheet %s — no matching headers", sn)
            continue

        col_to_key = {}
        for col_idx, header_str in col_map.items():
            key = tx_header_to_key.get(header_str.strip())
            if key:
                col_to_key[col_idx] = key

        for row_idx, raw_row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx <= header_row_idx:
                continue
            record = {"tx_type": tx_type}
            any_value = False
            for col_idx, key in col_to_key.items():
                v = clean_cell(raw_row[col_idx]) if col_idx < len(raw_row) else None
                if v is not None:
                    record[key] = v
                    any_value = True
            # Default week from sheet name
            if not record.get("week"):
                record["week"] = sn.strip()
            if any_value and record.get("item_code"):
                all_txns.append(record)

    wb.close()
    log.info("Parsed %d demand transactions from %s", len(all_txns), file_path)
    return all_txns
