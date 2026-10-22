"""
Python replica of the workbook's Power Query queries ("Data > Refresh All").

    MDA            = MDA folder files (34 cols)  + MDA FY 25-26 file
    SR FY 25-26    = CF 25-26 register, filtered, GRN date pulled from MDA,
                     kept only if GRN after previous FY end (or still blank)
    SR FY 26-27    = Non GRN folder files (233 cols), filtered + SR FY 25-26
                     -> this is the table that sits on the "Combine" sheet

Each query is reproduced step by step, in the same order, so the row set and
row order match what Excel loads into the sheets.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
from python_calamine import CalamineWorkbook

from .schema import (MDA_COLUMNS, MDA_PREV_TYPES, MDA_TYPES, SR_COLUMNS, SR_CURRENT_TYPES,
                     SR_PREV_TYPES)

SR_SHEET = "Sales Invoice Register Report"
MDA_SHEET = "Material Dispatch Acknowledgeme"
PARTY_ACCOUNTS = ("JCPL-Non Auto OEMS", "JCPL-OEM")
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".xlsb"}


class SourceError(Exception):
    pass


# --------------------------------------------------------------------------
# Excel.Workbook + Table.PromoteHeaders
# --------------------------------------------------------------------------
def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    wb = CalamineWorkbook.from_path(str(path))
    if sheet not in wb.sheet_names:
        raise SourceError(f"{path.name}: sheet '{sheet}' not found (has {wb.sheet_names})")
    rows = wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
    if not rows:
        return pd.DataFrame()
    header = [str(h).strip() if h not in (None, "") else f"Column{i + 1}" for i, h in enumerate(rows[0])]
    # Power Query turns empty cells into null; fully blank rows are dropped
    body = [[None if v == "" else v for v in r] for r in rows[1:]]
    body = [r for r in body if any(v is not None for v in r)]
    return pd.DataFrame(body, columns=header, dtype=object)


def folder_files(folder: Path) -> list[Path]:
    """Folder.Files + "Filtered Hidden Files" (also skips Office lock files)."""
    if not folder.exists():
        raise SourceError(f"Source folder not found: {folder}")
    files = [
        p for p in sorted(folder.rglob("*"))
        if p.is_file() and p.suffix.lower() in EXCEL_SUFFIXES and not p.name.startswith(("~$", "."))
    ]
    if not files:
        raise SourceError(f"No Excel files in {folder}")
    return files


def combine_folder(folder: Path, sheet: str) -> pd.DataFrame:
    frames = []
    for f in folder_files(folder):
        df = read_sheet(f, sheet)
        df.insert(0, "Source.Name", f.name)
        frames.append(df)
    return pd.concat(frames, ignore_index=True, sort=False)


# --------------------------------------------------------------------------
# type helpers (Table.TransformColumnTypes)
# --------------------------------------------------------------------------
def to_date(series: pd.Series) -> pd.Series:
    def conv(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return pd.NaT
        if isinstance(v, dt.datetime):
            return pd.Timestamp(v.date())
        if isinstance(v, dt.date):
            return pd.Timestamp(v)
        if isinstance(v, (int, float)):  # Excel serial
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
        s = str(v).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                return pd.Timestamp(dt.datetime.strptime(s, fmt).date())
            except ValueError:
                continue
        return pd.NaT

    return pd.to_datetime(series.map(conv))


EXCEL_EPOCH = dt.datetime(1899, 12, 30)
_DT_FORMATS = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S",
               "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y")


def _is_null(v) -> bool:
    return v is None or v is pd.NaT or (isinstance(v, float) and v != v)


def _serial(v) -> float | None:
    if isinstance(v, dt.time):
        # calamine yields 00:00 for date-formatted serials below 1; the ERP export
        # writes -1 there (Excel shows it as -1 after the Int64 step)
        return -1.0 if v == dt.time(0) else (v.hour * 3600 + v.minute * 60 + v.second) / 86400
    if isinstance(v, dt.datetime):
        return (v - EXCEL_EPOCH).total_seconds() / 86400
    if isinstance(v, dt.date):
        return float((v - EXCEL_EPOCH.date()).days)
    return None


def _parse_dt(s: str) -> dt.datetime | None:
    s = s.strip()
    for fmt in _DT_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _as_number(v):
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return None if v != v else float(v)
    s = _serial(v)
    if s is not None:
        return s
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").strip())
        except ValueError:
            d = _parse_dt(v)
            return _serial(d) if d else None
    return None


def _to_int(v):
    n = _as_number(v)
    return None if n is None else int(round(n))     # Int64.From rounds to even


def _to_number(v):
    return _as_number(v)


def _to_text(v):
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, dt.datetime):
        return v.strftime("%d-%m-%Y %H:%M:%S")
    if isinstance(v, dt.date):
        return v.strftime("%d-%m-%Y")
    return str(v)


def _to_datetime(v):
    if isinstance(v, dt.time):
        return EXCEL_EPOCH + dt.timedelta(days=_serial(v))
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)):
        return EXCEL_EPOCH + dt.timedelta(days=float(v))
    if isinstance(v, str):
        return _parse_dt(v)
    return None


def _to_date(v):
    d = _to_datetime(v)
    return d.date() if d else None


_CONVERTERS = {"int": _to_int, "number": _to_number, "text": _to_text,
               "date": _to_date, "datetime": _to_datetime}


def apply_types(df: pd.DataFrame, types: dict[str, str]) -> pd.DataFrame:
    """Table.TransformColumnTypes – values that fail to convert become null."""
    df = df.copy()
    for col, kind in types.items():
        conv = _CONVERTERS.get(kind)
        if conv is None or col not in df:
            continue
        values = df[col].tolist()
        if kind == "text" and all(v is None or isinstance(v, str) for v in values):
            continue
        df[col] = pd.Series([None if _is_null(v) else conv(v) for v in values], index=df.index, dtype=object)
    return df


def select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Table.SelectColumns – missing columns come through as null."""
    return df.reindex(columns=columns).astype(object).where(lambda d: d.notna(), None)


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------
def query_mda_fy_prev(path_or_folder: Path) -> pd.DataFrame:
    """shared #"MDA FY 25-26" """
    files = folder_files(path_or_folder) if path_or_folder.is_dir() else [path_or_folder]
    df = pd.concat([read_sheet(f, MDA_SHEET) for f in files], ignore_index=True, sort=False)
    return apply_types(df, MDA_PREV_TYPES)                       # Changed Type


def query_mda(folder: Path, mda_prev: pd.DataFrame) -> pd.DataFrame:
    """shared MDA"""
    df = combine_folder(folder, MDA_SHEET)
    df = apply_types(df, MDA_TYPES)                              # Changed Type
    df = select_columns(df, MDA_COLUMNS)                         # Removed Other Columns
    df = apply_types(df, {"Customer GRN Date": "date"})          # Changed Type1
    return pd.concat([df, mda_prev], ignore_index=True, sort=False)   # Appended Query


def query_sr_prev(path_or_folder: Path, mda: pd.DataFrame, fy_start: dt.date) -> pd.DataFrame:
    """shared #"SR FY 25-26" """
    files = folder_files(path_or_folder) if path_or_folder.is_dir() else [path_or_folder]
    df = pd.concat([read_sheet(f, SR_SHEET) for f in files], ignore_index=True, sort=False)
    df = apply_types(df, SR_PREV_TYPES)                          # Changed Type
    # Filtered Rows
    df = df[
        (df["Invoice Type"] != "Service")
        & (df["Invoice Status"] == "Exported To GL")
        & (df["Party A/C Description"].isin(PARTY_ACCOUNTS))
    ]
    # Renamed Columns  Goods Received Date -> Goods Received Date1
    df = df.rename(columns={"Goods Received Date": "Goods Received Date1"})
    # Merged Queries (left outer on Invoice No = Sales Invoice No) + Expanded MDA
    right = mda[["Sales Invoice No", "Customer GRN Date"]].rename(
        columns={"Sales Invoice No": "__mda_key", "Customer GRN Date": "Goods Received Date"})
    right["__mda_pos"] = range(len(right))
    df = df.reset_index(drop=True).copy()
    df["__left_pos"] = range(len(df))
    df = df.merge(right, how="left", left_on="Invoice No", right_on="__mda_key", sort=False)
    # Power Query emits matched rows in MDA-table order, unmatched rows last
    df["__mda_pos"] = df["__mda_pos"].fillna(float("inf"))
    df = df.sort_values(["__mda_pos", "__left_pos"], kind="stable")
    df = df.drop(columns=["__mda_key", "__mda_pos", "__left_pos"])
    df = apply_types(df, {"Goods Received Date": "date"})        # Changed Type2
    df = select_columns(df, SR_COLUMNS)                          # Reordered + Removed Other Columns
    df["Invoice Date"] = to_date(df["Invoice Date"])
    df["Goods Received Date"] = to_date(df["Goods Received Date"])   # Changed Type1
    # Filtered Rows1: GRN after previous FY end, or no GRN
    cutoff = pd.Timestamp(fy_start) - pd.Timedelta(days=1)
    df = df[(df["Goods Received Date"] > cutoff) | df["Goods Received Date"].isna()]
    return df.reset_index(drop=True)


def query_sr_current(folder: Path, sr_prev: pd.DataFrame) -> pd.DataFrame:
    """shared #"SR FY 26-27"  (the table on the Combine sheet)"""
    df = combine_folder(folder, SR_SHEET)
    df = apply_types(df, SR_CURRENT_TYPES)                       # Changed Type
    df = select_columns(df, SR_COLUMNS)                          # Removed Other Columns
    df = df[df["Party A/C Description"].isin(PARTY_ACCOUNTS)]    # Filtered Rows
    df["Invoice Date"] = to_date(df["Invoice Date"])             # Changed Type1
    df["Goods Received Date"] = to_date(df["Goods Received Date"])
    df = df[                                                     # Filtered Rows1
        (df["Invoice Status"] == "Exported To GL")
        & (df["Invoice Type"].isin(["Sales ( Commercial )", "SEZ Sale"]))
    ]
    return pd.concat([df, sr_prev], ignore_index=True, sort=False)   # Appended Query


def refresh_all(sources: dict[str, Path], fy_start: dt.date) -> dict[str, pd.DataFrame]:
    """Runs every query in dependency order. Returns the loaded tables."""
    mda_prev = query_mda_fy_prev(Path(sources["mda_prev"]))
    mda = query_mda(Path(sources["mda_current"]), mda_prev)
    sr_prev = query_sr_prev(Path(sources["sr_prev"]), mda, fy_start)
    sr_current = query_sr_current(Path(sources["sr_current"]), sr_prev)
    return {
        "sr_current": sr_current,   # Combine  (SR_FY_26_27)
        "sr_prev": sr_prev,         # SR FY 25-26 (hidden sheet)
        "mda_prev": mda_prev,       # MDA FY 25-26 (hidden sheet)
        "mda": mda,                 # MDA FY 26-27 sheet (query "MDA")
    }
