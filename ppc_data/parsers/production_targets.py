"""Parser for Production Targets.xlsx → capacity_ppp table (W1.6).

PPC must reconcile three sources before upload — this parser accepts
the reconciled file.
Level: L0
"""

import logging

from ..field_maps.capacity_ppp import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def parse(file_path, sheet_name=None):
    """Parse capacity / PPP targets."""
    rows = extract_rows(file_path, sheet_name, FIELD_MAP)
    log.info("Parsed %d capacity rows from %s", len(rows), file_path)
    return rows
