"""Parser for MpsSS.xlsm — Schedule Form sheet.

Source: MpsSS.xlsm → Schedule Form
Table key: mps_schedule_form
Provides: W1-W5, Additional Demand, Total Plan for R3SS
"""

import logging

from openpyxl import load_workbook

log = logging.getLogger(__name__)

TABLE_KEY = "mps_schedule_form"

_SHEET_CANDIDATES = ["Schedule Form", "ScheduleForm", "Sheet1"]

# Column positions (0-indexed) in Schedule Form
_COL_FAMILY = 0
_COL_CUSTOMER = 1
_COL_JOLLY_SIZE = 4
_COL_W1 = 13       # N
_COL_W2 = 14       # O
_COL_W3 = 15       # P
_COL_W4 = 16       # Q
_COL_W5 = 17       # R
_COL_ERP = 23      # X
_COL_MTO_MTS = 24  # Y
_COL_ADDITIONAL = 32  # AG — Total Additional Demand


def _find_sheet(wb):
    for cand in _SHEET_CANDIDATES:
        for sn in wb.sheetnames:
            if cand.lower() == sn.lower().strip():
                return sn
    return wb.sheetnames[0]


def _num(v):
    if v is None:
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _txt(v):
    return str(v).strip() if v is not None else ""


def parse(file_path):
    wb = load_workbook(file_path, data_only=True, read_only=True)
    ws = wb[_find_sheet(wb)]

    # Verify header at row 3 (index 2)
    header_found = False
    data_start = 6  # default: row 6 (index 5)
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= 6:
            break
        cells = list(row)
        if len(cells) > _COL_ERP:
            val = _txt(cells[_COL_ERP]).upper()
            if "ERP" in val and "CODE" in val or "ERP" in val and "PART" in val:
                header_found = True
                data_start = i + 3  # skip header + 2 summary rows
                break

    if not header_found:
        data_start = 5

    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < data_start - 1:
            continue
        cells = list(row)
        if len(cells) <= _COL_ERP:
            continue

        erp = _txt(cells[_COL_ERP])
        if not erp:
            continue

        w1 = _num(cells[_COL_W1]) if len(cells) > _COL_W1 else 0.0
        w2 = _num(cells[_COL_W2]) if len(cells) > _COL_W2 else 0.0
        w3 = _num(cells[_COL_W3]) if len(cells) > _COL_W3 else 0.0
        w4 = _num(cells[_COL_W4]) if len(cells) > _COL_W4 else 0.0
        w5 = _num(cells[_COL_W5]) if len(cells) > _COL_W5 else 0.0
        additional = _num(cells[_COL_ADDITIONAL]) if len(cells) > _COL_ADDITIONAL else 0.0

        rows.append({
            "erp_code": erp,
            "family": _txt(cells[_COL_FAMILY]),
            "customer": _txt(cells[_COL_CUSTOMER]),
            "jolly_code": _txt(cells[_COL_JOLLY_SIZE]) if len(cells) > _COL_JOLLY_SIZE else "",
            "mto_mts": _txt(cells[_COL_MTO_MTS]) if len(cells) > _COL_MTO_MTS else "",
            "w1": w1,
            "w2": w2,
            "w3": w3,
            "w4": w4,
            "w5": w5,
            "total_plan": w1 + w2 + w3 + w4 + w5,
            "additional_demand": additional,
        })

    wb.close()
    log.info("Parsed %d rows from mps_schedule_form %s", len(rows), file_path)
    return rows
