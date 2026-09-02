"""Parser for Monitoring.xlsx → batch_ebq table (W1.8).

Sheets: "EBQ" + "Batch Qty" — combined into one table.
Level: L0
"""

import logging

from openpyxl import load_workbook

from ..field_maps.batch_ebq import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def parse(file_path, sheet_name=None):
    """Parse EBQ / batch data from Monitoring.xlsx.

    Tries sheets in order: "EBQ", "Batch Qty", then any sheet
    containing "ebq" or "batch" in the name.
    """
    wb = load_workbook(file_path, read_only=True, data_only=True)
    sheets = wb.sheetnames
    wb.close()

    all_rows = []

    # Try to find and parse EBQ sheet
    for name in sheets:
        nl = name.lower()
        if "ebq" in nl or "batch" in nl:
            try:
                rows = extract_rows(file_path, name, FIELD_MAP)
                all_rows.extend(rows)
                log.info("Parsed %d rows from sheet %r", len(rows), name)
            except ValueError as e:
                log.info("Skipping sheet %r: %s", name, e)

    # If nothing found, try first sheet
    if not all_rows:
        all_rows = extract_rows(file_path, None, FIELD_MAP)

    log.info("Parsed %d total EBQ/batch rows from %s", len(all_rows), file_path)
    return all_rows
