"""Parser for Product Group Mapping.xlsx → item_master table.

Source: Product Group Mapping.xlsx (exported from ERP)
Sheet: "Sheet0" (or first sheet — auto-detected)
Expected rows: ~4,822
Level: L0

This is the FIRST parser built — the reference for all others.
"""

import logging

from ..field_maps.item_master import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

# Re-export so the parsers registry can read it
TABLE_KEY = TABLE_KEY  # noqa: F841


def parse(file_path, sheet_name=None):
    """Parse Product Group Mapping xlsx and return a list of dicts
    keyed by stable field keys.

    Args:
        file_path: path to the uploaded .xlsx file.
        sheet_name: optional sheet name override (default: first sheet
                    or "Sheet0" if it exists).

    Returns:
        list[dict] — each dict keyed by item_master FIELD_MAP keys.
    """
    rows = extract_rows(file_path, sheet_name, FIELD_MAP)
    log.info(
        "Parsed %d rows from Product Group Mapping (%s)",
        len(rows), file_path,
    )
    return rows
