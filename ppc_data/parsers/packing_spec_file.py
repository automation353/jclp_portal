"""Parser for Packing Spec → packing_spec table (W1.15).

Spec §3.1: "Only 50 rows exist vs 1,067 live packing items.
Must be built from scratch, not migrated."

This parser handles bulk xlsx uploads for packing spec data.
The file can have any sheet name — it auto-detects the header row.
Expects columns matching the packing_spec field map:
  Jolly Code, Packing Item Code, Type, Qty Per Pack,
  Pack Size, Customer Variant, Description

Level: L0
"""

import logging

from openpyxl import load_workbook

from ..field_maps.packing_spec import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def parse(file_path, sheet_name=None):
    """Parse packing spec xlsx file.

    Accepts any sheet name — tries "Packing Spec", "Sheet1", then first.
    """
    if not sheet_name:
        wb = load_workbook(file_path, read_only=True, data_only=True)
        sheets = wb.sheetnames
        wb.close()
        # Prefer named sheets, fall back to first
        for candidate in ("Packing Spec", "Packing", "Sheet1"):
            if candidate in sheets:
                sheet_name = candidate
                break

    rows = extract_rows(file_path, sheet_name, FIELD_MAP)
    log.info("Parsed %d packing spec rows from %s", len(rows), file_path)
    return rows
