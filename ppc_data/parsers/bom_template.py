"""Parser for BOM_Item_Template.xlsx → bom_master table.

Source: BOM_Item_Template.xlsx (exported from ERP)
Sheet: "BOM_ItemDetails"
Expected rows: ~37,149
Level: L0
"""

import logging

from ..field_maps.bom_master import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def parse(file_path, sheet_name="BOM_ItemDetails"):
    """Parse BOM template xlsx. Falls back to first sheet if
    BOM_ItemDetails not found."""
    try:
        rows = extract_rows(file_path, sheet_name, FIELD_MAP)
    except ValueError:
        log.info("Sheet %r not found, trying first sheet", sheet_name)
        rows = extract_rows(file_path, None, FIELD_MAP)

    log.info("Parsed %d BOM rows from %s", len(rows), file_path)
    return rows
