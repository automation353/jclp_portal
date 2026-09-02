"""Parser for Green Level RM/CP/Packing .xlsx → stock_policy table (W1.14).

Three separate files (RM, CP, Packing) merged into one table.
Each file has the same column structure — the parser auto-detects
item_type from the filename.
BLOCKED by Decision #2 (ERP vs portal ownership).
Level: L0
"""

import logging
import os

from ..field_maps.stock_policy import FIELD_MAP, TABLE_KEY
from .base import extract_rows

log = logging.getLogger(__name__)

TABLE_KEY = TABLE_KEY  # noqa: F841


def _detect_item_type(filename):
    """Detect RM / CP / PM from filename."""
    fn = filename.lower()
    if "rm" in fn or "raw" in fn:
        return "RM"
    if "cp" in fn or "component" in fn:
        return "CP"
    if "pack" in fn or "pm" in fn:
        return "PM"
    return ""


def parse(file_path, sheet_name=None):
    """Parse green level / stock policy file.

    Auto-detects item_type from filename and injects it into every row
    if the column is missing from the source.
    """
    rows = extract_rows(file_path, sheet_name, FIELD_MAP)

    # Inject item_type if not in the data
    item_type = _detect_item_type(os.path.basename(file_path))
    if item_type:
        for row in rows:
            row.setdefault("item_type", item_type)

    log.info(
        "Parsed %d stock policy rows (%s) from %s",
        len(rows), item_type or "unknown type", file_path,
    )
    return rows
