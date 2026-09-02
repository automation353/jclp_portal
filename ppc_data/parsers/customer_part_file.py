"""Parser for R3 SS.xlsx / SO Tracking → customer_part table (W1.13).

MTO/MTS is per customer-part combination, not per part alone.
Level: L0
"""

import logging

from ..field_maps.customer_part import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def parse(file_path, sheet_name=None):
    """Parse customer-part mapping."""
    rows = extract_rows(file_path, sheet_name, FIELD_MAP)
    log.info("Parsed %d customer-part rows from %s", len(rows), file_path)
    return rows
