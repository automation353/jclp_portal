"""Parser for Machine Loading data.xlsx → machine_master table (W1.7).

Level: L0
"""

import logging

from ..field_maps.machine_master import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def parse(file_path, sheet_name=None):
    """Parse machine master from machine loading data file."""
    rows = extract_rows(file_path, sheet_name, FIELD_MAP)
    log.info("Parsed %d machine rows from %s", len(rows), file_path)
    return rows
