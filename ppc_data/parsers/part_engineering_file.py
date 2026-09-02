"""Parser for T-Bolt BOM master / MpsSS → part_engineering table (W1.12).

Source: T-Bolt BOM master (63 columns, richest source).
Level: L0
"""

import logging

from ..field_maps.part_engineering import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def parse(file_path, sheet_name=None):
    """Parse part engineering data from T-Bolt BOM master or similar."""
    rows = extract_rows(file_path, sheet_name, FIELD_MAP)
    log.info("Parsed %d part engineering rows from %s", len(rows), file_path)
    return rows
