"""
Glue between Django and the calculation engine.

* Refresh All  -> engine.ingest (slow, reads the 4 source folders) -> data/tables.pkl
* Every page   -> get_workbook(as_on): recalculates the formula sheets from the
                  stored tables + current Manual GRN rows. Results are cached and
                  recomputed automatically when the tables, Manual GRN or date change.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings
from django.db.models import Count, Max
from django.utils import timezone

from .engine import calc, ingest, store, workbook as wb_writer
from .engine.schema import MDA_PREV_TYPES, MDA_TYPES, SR_COLUMNS, SR_CURRENT_TYPES, SR_PREV_TYPES
from .models import ActivityLog, ManualGRN, RefreshRun

_lock = threading.RLock()


def fiscal_year() -> calc.FiscalYear:
    return calc.FiscalYear(settings.NONGRN_FY_START_YEAR)


def fy_labels():
    fy = fiscal_year()
    prev = calc.FiscalYear(fy.start_year - 1)
    return {"cur": fy.label[3:], "prev": prev.label[3:]}


# ==========================================================================
# Stored Power Query tables
# ==========================================================================
_tables_cache: dict = {"version": None, "payload": None}


def get_tables() -> dict | None:
    data_dir = Path(settings.NONGRN_DATA_DIR)
    version = store.tables_version(data_dir)
    with _lock:
        if version is None:
            return None
        if _tables_cache["version"] != version:
            _tables_cache["payload"] = store.load_tables(data_dir)
            _tables_cache["version"] = version
            _display_cache.clear()
        return _tables_cache["payload"]


# ==========================================================================
# Manual GRN
# ==========================================================================
def manual_grn_state():
    agg = ManualGRN.objects.aggregate(n=Count("id"), m=Max("updated_at"))
    signature = (agg["n"], agg["m"].isoformat() if agg["m"] else None)
    return signature


def manual_grn_map() -> dict[str, dt.date]:
    # XLOOKUP returns the first match, rows are kept in sheet order (id)
    out: dict[str, dt.date] = {}
    for inv, d in ManualGRN.objects.order_by("id").values_list("invoice_no", "grn_date"):
        out.setdefault(inv, d)
    return out


# ==========================================================================
# Recalculated workbook
# ==========================================================================
@dataclass
class Workbook:
    as_on: dt.date
    fy: calc.FiscalYear
    tables: dict
    meta: dict
    ar: pd.DataFrame               # Combine!HZ:JX  (AR_Tax_Register___Detail_Report)
    snaps: list
    _report: dict | None = field(default=None, repr=False)
    _display: dict = field(default_factory=dict, repr=False)

    @property
    def report(self) -> dict:
        if self._report is None:
            self._report = calc.build_report(self.tables["sr_current"], self.ar, self.fy, self.as_on, self.snaps)
        return self._report


_wb_cache: "OrderedDict[tuple, Workbook]" = OrderedDict()


def get_workbook(as_on: dt.date) -> Workbook | None:
    payload = get_tables()
    if payload is None:
        return None
    key = (_tables_cache["version"], manual_grn_state(), as_on, settings.NONGRN_FY_START_YEAR)
    with _lock:
        if key in _wb_cache:
            _wb_cache.move_to_end(key)
            return _wb_cache[key]
    tables = payload["tables"]
    fy = fiscal_year()
    ar, snaps = calc.combine_formulas(tables["sr_current"], manual_grn_map(), fy, as_on)
    wb = Workbook(as_on=as_on, fy=fy, tables=tables, meta=payload["meta"], ar=ar, snaps=snaps)
    with _lock:
        _wb_cache[key] = wb
        while len(_wb_cache) > 6:
            _wb_cache.popitem(last=False)
    return wb


# ==========================================================================
# Sheet grids (Combine / SR FY 25-26 / MDA FY 25-26 / MDA FY 26-27)
# ==========================================================================
FORMULA_DOCS = {
    "Revised Billing Date": "=IF([Goods Received Date]<>\"\",[Goods Received Date],IFERROR(XLOOKUP([Invoice No],'Manual GRN'!A:A,'Manual GRN'!B:B),IF(OR([Receipt Status]=\"Received\",[Receipt Status]=\"Partially Received\"),[Invoice Date]+30,\"\")))",
    "Non GRN ": "=IF(HZ=\"\",DATE(FY end),HZ-1)",
    "_amt": "=IF(AND($C<=snapshot,$IA>=snapshot),$EB [Item Net Amount],0)",
    "_days": "=IF(AND($C<=snapshot,$IA>=snapshot),snapshot-$C+1,0)",
    "_bucket": "=LOOKUP(days,{0,1,16,31,61,91,181,366,999},{\"NA\",\"0-15 Days\",\"16-30 Days\",\"31-60 Days\",\"61-90 Days\",\"91-180 Days\",\"181-365 Days\",\"Above 1 Year\",\"Above 60 Days\"})",
    "Customer Code": "=[@[Customer Code]]",
    "Customer Name": "=[@[Customer Name]]",
    "Site": "=[@Site]",
    "Party Group": "=[@[Party Group Description]]",
    "Credit Term": "=[@[Credit Term]]",
    "Invoice No.": "=[@[Invoice No]]",
    "Inv Date": "=[@[Invoice Date]]",
    "Inv Month": "=IF($C=\"\",\"\",DATE(YEAR($C),MONTH($C),1))",
    "GRN Source": "=IF(GRN<>\"\",\"1. ERP GRN\",IF(found in 'Manual GRN',\"2. Manual GRN\",IF(OR(Received,Partially Received),\"3. Assumed Inv+30\",\"4. Not Received\")))",
    "Days to GRN": "=IF($HZ=\"\",\"\",$HZ-$C)",
    "Current Non-GRN Amt": "=IF(AND($C<=TODAY(),$IA>=TODAY()),$EB,0)",
    "Current Age Days": "=IF($JV<>0,TODAY()-$C+1,0)",
    "Current Bucket": "=LOOKUP($JW,{0,1,16,31,61,91,181,366},{\"NA\",\"1) 0-15 Days\",...,\"7) Above 1 Year\"})",
}

_KIND_TO_FMT = {"int": "int", "number": "num", "date": "date", "datetime": "datetime", "text": "text", "any": "auto"}


def _excel_col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def sheet_definitions():
    labels = fy_labels()
    return [
        {"key": "report", "title": "Report", "kind": "report"},
        {"key": "dashboard", "title": "Customer Dashboard", "kind": "dashboard"},
        {"key": "combine", "title": "Combine", "kind": "grid"},
        {"key": "sr-prev", "title": f"SR FY {labels['prev']}", "kind": "grid", "hidden": True},
        {"key": "mda-prev", "title": f"MDA FY {labels['prev']}", "kind": "grid", "hidden": True},
        {"key": "mda", "title": f"MDA FY {labels['cur']}", "kind": "grid"},
        {"key": "manual-grn", "title": "Manual GRN", "kind": "manual"},
    ]


def get_sheet_def(key):
    return next((s for s in sheet_definitions() if s["key"] == key), None)


def _fmt_for(series: pd.Series, kind: str | None) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if kind:
        return _KIND_TO_FMT.get(kind, "auto")
    return "auto"


def grid_frame(wb: Workbook, key: str):
    """Returns (DataFrame with positional columns, column metadata list)."""
    t = wb.tables
    if key == "combine":
        base, kinds = t["sr_current"], {**SR_CURRENT_TYPES, "Invoice Date": "date", "Goods Received Date": "date"}
        cols = []
        for i, c in enumerate(SR_COLUMNS):
            cols.append({"name": c, "group": "source", "fmt": _fmt_for(base[c], kinds.get(c)), "letter": _excel_col(i + 1)})
        amt, days = calc.month_amount_cols(wb.fy), [f"Column{13 + i}" for i in range(12)]
        bkt = calc.month_bucket_cols(wb.fy)
        for j, c in enumerate(wb.ar.columns):
            meta = {"name": c, "group": "formula", "letter": _excel_col(len(SR_COLUMNS) + j + 1)}
            if c in amt:
                i = amt.index(c)
                meta.update(fmt="num", formula=FORMULA_DOCS["_amt"], snap=wb.snaps[i].strftime("%d-%m-%Y") if wb.snaps[i] else "")
                meta["today"] = wb.snaps[i] == wb.as_on   # current month: row-1 date is today
            elif c in days:
                i = days.index(c)
                meta.update(fmt="int", formula=FORMULA_DOCS["_days"], snap=wb.snaps[i].strftime("%d-%m-%Y") if wb.snaps[i] else "")
                meta["today"] = wb.snaps[i] == wb.as_on
            elif c in bkt:
                meta.update(fmt="text", formula=FORMULA_DOCS["_bucket"])
            else:
                fmt = {"Revised Billing Date": "date", "Non GRN ": "date", "Inv Date": "date", "Inv Month": "mon",
                       "Days to GRN": "int", "Current Non-GRN Amt": "num", "Current Age Days": "int"}.get(c, "text")
                meta.update(fmt=fmt, formula=FORMULA_DOCS.get(c, ""))
            cols.append(meta)
        df = pd.concat([base.reset_index(drop=True), wb.ar.reset_index(drop=True)], axis=1, ignore_index=True)
        return df, cols
    if key == "sr-prev":
        base, kinds = t["sr_prev"], {**SR_PREV_TYPES, "Invoice Date": "date", "Goods Received Date": "date"}
    elif key == "mda-prev":
        base, kinds = t["mda_prev"], MDA_PREV_TYPES
    elif key == "mda":
        base, kinds = t["mda"], {**MDA_TYPES, "Customer GRN Date": "any"}
    else:
        raise KeyError(key)
    cols = [{"name": c, "group": "source", "fmt": _fmt_for(base[c], kinds.get(c)), "letter": _excel_col(i + 1)}
            for i, c in enumerate(base.columns)]
    df = base.reset_index(drop=True).copy()
    df.columns = range(len(df.columns))
    return df, cols


# ---- display strings (used for search / filters / sorting text) ----------
_display_cache: dict = {}
SEP = chr(1)  # column separator inside the search blob


def _display_value(v) -> str:
    if v is None or v is pd.NaT:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        return str(int(v)) if v.is_integer() else f"{v:.10g}"
    if isinstance(v, pd.Timestamp):
        return v.strftime("%d-%m-%Y")
    if isinstance(v, dt.datetime):
        return v.strftime("%d-%m-%Y %H:%M") if (v.hour or v.minute) else v.strftime("%d-%m-%Y")
    if isinstance(v, dt.date):
        return v.strftime("%d-%m-%Y")
    return str(v)


def display_series(s: pd.Series, fmt: str) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        f = "%b-%y" if fmt == "mon" else "%d-%m-%Y"
        return s.dt.strftime(f).fillna("")
    if pd.api.types.is_numeric_dtype(s):
        return s.map(_display_value)
    return pd.Series([_display_value(v) for v in s.tolist()], index=s.index, dtype=object)


def display_frame(wb: Workbook, key: str):
    """Cached string version of a grid + a per-row lowercase search blob.

    Combine depends on Manual GRN / as-on date so it is cached on the Workbook;
    the pure Power Query sheets only change on Refresh All.
    """
    with _lock:
        hit = wb._display.get(key)
    if hit:
        return hit
    df, cols = grid_frame(wb, key)
    if key == "combine":
        # source columns change only on Refresh All -> shared cache; formula columns per workbook
        n_src = len(SR_COLUMNS)
        base_key = ("combine-src", _tables_cache["version"])
        with _lock:
            base = _display_cache.get(base_key)
        if base is None:
            base = _strings(df, cols, range(n_src))
            with _lock:
                _display_cache[base_key] = base
        part = _strings(df, cols, range(n_src, len(cols)))
        disp = pd.concat([base[0], part[0]], axis=1)
        blob = base[1] + SEP + part[1]
    else:
        ck = (key, _tables_cache["version"])
        with _lock:
            cached = _display_cache.get(ck)
        if cached is None:
            cached = _strings(df, cols, range(len(cols)))
            with _lock:
                _display_cache[ck] = cached
        disp, blob = cached
    result = (df, cols, disp, blob)
    with _lock:
        wb._display[key] = result
    return result


def _strings(df, cols, idx):
    disp = pd.DataFrame({i: display_series(df[i], cols[i]["fmt"]) for i in idx})
    parts = [disp[i].astype(str) for i in idx]
    blob = parts[0].str.cat(parts[1:], sep=SEP).str.lower()
    return disp, blob


def _numeric_filter(raw: pd.Series, expr: str):
    import operator
    ops = [(">=", operator.ge), ("<=", operator.le), ("<>", operator.ne), (">", operator.gt),
           ("<", operator.lt), ("=", operator.eq)]
    for sym, fn in ops:
        if expr.startswith(sym):
            try:
                val = float(expr[len(sym):].replace(",", "").strip())
            except ValueError:
                return None
            nums = pd.to_numeric(raw, errors="coerce")
            return fn(nums, val).fillna(False)
    return None


def query_grid(wb: Workbook, key: str, *, q="", filters=None, sort=None, desc=False, page=1, size=100):
    df, cols, disp, blob = display_frame(wb, key)
    mask = pd.Series(True, index=df.index)
    if q:
        for term in q.lower().split():
            mask &= blob.str.contains(term, regex=False)
    for idx, expr in (filters or {}).items():
        expr = expr.strip()
        if not expr or idx >= len(cols):
            continue
        if expr == "(blank)":
            mask &= disp[idx] == ""
            continue
        if expr == "(nonblank)":
            mask &= disp[idx] != ""
            continue
        numeric = _numeric_filter(df[idx], expr)
        if numeric is not None:
            mask &= numeric
        else:
            mask &= disp[idx].str.lower().str.contains(expr.lower(), regex=False)
    rows = df.index[mask]
    if sort is not None and 0 <= sort < len(cols):
        col = df.loc[rows, sort]
        if cols[sort]["fmt"] in ("num", "int") or pd.api.types.is_numeric_dtype(col):
            keyser = pd.to_numeric(col, errors="coerce")
        elif pd.api.types.is_datetime64_any_dtype(col):
            keyser = col
        else:
            keyser = disp.loc[rows, sort].str.lower()
        rows = keyser.sort_values(ascending=not desc, na_position="last", kind="stable").index
    total = len(rows)
    page = max(1, page)
    start = (page - 1) * size
    sel = rows[start:start + size]
    out_rows = []
    for r in sel:
        vals = []
        for i, c in enumerate(cols):
            v = df.at[r, i]
            if c["fmt"] in ("num", "int", "auto") and isinstance(v, (int, float, np.integer, np.floating)) \
                    and not (isinstance(v, float) and v != v) and not isinstance(v, bool):
                vals.append(float(v) if c["fmt"] != "int" else int(v))
            else:
                vals.append(disp.at[r, i])
        out_rows.append({"n": int(r) + (3 if key == "combine" else 2), "v": vals})
    # column totals for numeric formula / amount columns over the filtered rows
    totals = {}
    for i, c in enumerate(cols):
        if c["fmt"] == "num":
            totals[i] = float(pd.to_numeric(df.loc[rows, i], errors="coerce").sum())
    return {"total": total, "page": page, "size": size, "rows": out_rows, "totals": totals,
            "all_rows": len(df)}


# ==========================================================================
# Refresh All (background job)
# ==========================================================================
_refresh_thread: threading.Thread | None = None


SOURCE_NAMES = {
    "sr_current": ("Non GRN", "Sales Invoice Register – current FY"),
    "sr_prev": ("Non GRN CF 25-26", "Sales Invoice Register – previous FY carry-forward"),
    "mda_current": ("MDA", "Material Dispatch Acknowledgement – current FY"),
    "mda_prev": ("MDA FY 25-26", "Material Dispatch Acknowledgement – previous FY"),
}
DAILY_SOURCES = ("sr_current", "mda_current")   # uploaded every day
SOURCE_ORDER = ("sr_current", "mda_current", "sr_prev", "mda_prev")   # Sources page order


def source_listing():
    out = []
    names = SOURCE_NAMES
    keys = sorted(settings.NONGRN_SOURCES, key=lambda k: SOURCE_ORDER.index(k) if k in SOURCE_ORDER else 99)
    for key in keys:
        path = settings.NONGRN_SOURCES[key]
        files = []
        if path.exists():
            for p in sorted(path.rglob("*")):
                if p.is_file() and not p.name.startswith(("~$", ".")):
                    st = p.stat()
                    files.append({"name": str(p.relative_to(path)), "size": st.st_size,
                                  "modified": dt.datetime.fromtimestamp(st.st_mtime),
                                  "excel": p.suffix.lower() in ingest.EXCEL_SUFFIXES})
        files.sort(key=lambda f: f["modified"], reverse=True)   # newest first = the file in use
        latest = next((f for f in files if f["excel"]), files[0] if files else None)
        age = (timezone.localdate() - latest["modified"].date()).days if latest else None
        out.append({"key": key, "label": names[key][0], "desc": names[key][1], "path": str(path),
                    "exists": path.exists(), "files": files, "latest": latest, "age_days": age,
                    "daily": key in DAILY_SOURCES})
    return out


def run_refresh(triggered_by: str = "") -> RefreshRun:
    """Runs synchronously (used by the management command and the thread)."""
    run = RefreshRun.objects.create(triggered_by=triggered_by)
    try:
        fy = fiscal_year()
        tables = ingest.refresh_all(settings.NONGRN_SOURCES, fy.start)
        files = {k: [f["name"] for f in s["files"] if f["excel"]] for k, s in
                 ((s["key"], s) for s in source_listing())}
        counts = {k: int(len(v)) for k, v in tables.items()}
        store.save_tables(Path(settings.NONGRN_DATA_DIR), tables,
                          {"run_id": run.pk, "files": files, "counts": counts,
                           "refreshed_at": timezone.localtime().isoformat()})
        run.status, run.row_counts, run.files = RefreshRun.OK, counts, files
        run.message = "Refreshed " + ", ".join(f"{k}: {v:,} rows" for k, v in counts.items())
        try:
            build_age_workbook(force=True)
            run.message += ". Non GRN Age.xlsx built."
        except Exception as exc:  # noqa: BLE001 – data refresh itself succeeded
            run.message += f". Non GRN Age.xlsx could not be built: {exc}"
    except Exception as exc:  # noqa: BLE001 – the run log must capture any failure
        run.status = RefreshRun.FAILED
        run.message = f"{exc}\n\n{traceback.format_exc()}"
    run.finished_at = timezone.now()
    run.save()
    log_refresh(run)
    return run


def log_refresh(run: RefreshRun):
    who, _, why = (run.triggered_by or "").partition(" (")
    ActivityLog.objects.create(
        at=run.started_at, kind=ActivityLog.REFRESH,
        status=ActivityLog.OK if run.status == RefreshRun.OK else ActivityLog.FAILED, user=who,
        title="Refresh All" + (f" – after {why.rstrip(')')}" if why else ""),
        detail=(run.message or "").split("\n\n")[0][:2000],
        duration=(run.finished_at - run.started_at).total_seconds())


def log_upload(ok: bool, user: str, file_name: str, source: str, detail: str,
               size: int | None = None, link: str = "", duration: float | None = None):
    ActivityLog.objects.create(
        at=timezone.now(), kind=ActivityLog.UPLOAD, status=ActivityLog.OK if ok else ActivityLog.FAILED,
        user=user, title=file_name, source=source, detail=detail[:2000], file_size=size,
        link=link or "", duration=duration)


_refresh_state = {"active": False, "again": None}


def start_refresh(triggered_by: str = "", queue: bool = False) -> bool:
    """Starts Refresh All in the background.

    If one is already running: returns False, or – with queue=True – schedules one more
    run right after it (so a just-uploaded file is always included) and returns True.
    """
    global _refresh_thread
    with _lock:
        if _refresh_state["active"]:
            if queue:
                _refresh_state["again"] = triggered_by
            return queue
        _refresh_state["active"] = True

        def target():
            from django.db import connection
            who = triggered_by
            try:
                while True:
                    run_refresh(who)
                    with _lock:
                        who = _refresh_state["again"]
                        _refresh_state["again"] = None
                        if who is None:
                            _refresh_state["active"] = False
                            return
            except BaseException:
                with _lock:
                    _refresh_state["active"] = False
                raise
            finally:
                connection.close()

        _refresh_thread = threading.Thread(target=target, name="nongrn-refresh", daemon=True)
        _refresh_thread.start()
        return True


def refresh_running() -> bool:
    return _refresh_state["active"]


# ==========================================================================
# n8n: uploaded source file -> Google Sheet in Drive
# ==========================================================================
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CHUNK = 16 * 1024 * 1024          # Google resumable uploads need multiples of 256 KB


class N8nError(Exception):
    pass


def _n8n_call(payload: dict) -> dict:
    """Small JSON request to the n8n webhook; returns its JSON reply or raises N8nError."""
    import requests

    try:
        resp = requests.post(settings.NONGRN_N8N_WEBHOOK_URL, json=payload,
                             headers={"X-NonGRN-Token": settings.NONGRN_N8N_TOKEN}, timeout=(30, 120))
    except requests.RequestException as exc:
        raise N8nError(f"Could not reach n8n: {exc}") from exc
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, list):          # n8n can wrap a single reply in a list
        body = body[0] if body and isinstance(body[0], dict) else None
    if resp.status_code == 404:
        raise N8nError("n8n webhook not found – is the workflow imported and active?")
    if not isinstance(body, dict):
        raise N8nError(f"n8n answered HTTP {resp.status_code} without a usable reply – check Executions in n8n")
    if not resp.ok or body.get("ok") is False:
        step = f" (step: {body['step']})" if body.get("step") else ""
        raise N8nError(f"{body.get('error') or body.get('message') or f'HTTP {resp.status_code}'}{step}")
    return body


def _upload_to_google(upload_url: str, path: Path) -> dict:
    """Sends the file to a Google Drive resumable-upload session in chunks.

    Returns the Drive file resource; raises N8nError with Google's message on failure.
    """
    import requests

    total = path.stat().st_size
    sent = 0
    with open(path, "rb") as fh:
        while True:
            fh.seek(sent)
            chunk = fh.read(CHUNK)
            end = sent + len(chunk) - 1
            last = end + 1 >= total
            for attempt in range(4):
                try:
                    resp = requests.put(upload_url, data=chunk, timeout=(30, 900 if last else 300), headers={
                        "Content-Length": str(len(chunk)), "Content-Range": f"bytes {sent}-{end}/{total}"})
                except requests.RequestException:
                    resp = None
                if resp is not None and resp.status_code in (200, 201, 308):
                    break
                if resp is not None and resp.status_code < 500 and resp.status_code != 429:
                    raise N8nError(_google_error(resp))
                # network / 5xx: ask Google how much it has, then resume from there
                try:
                    st = requests.put(upload_url, timeout=60, headers={
                        "Content-Length": "0", "Content-Range": f"bytes */{total}"})
                    if st.status_code in (200, 201):
                        return st.json()
                    if st.status_code == 308:
                        rng = st.headers.get("Range")
                        sent = int(rng.split("-")[1]) + 1 if rng else 0
                        resp = st
                        break
                except requests.RequestException:
                    pass
                time.sleep(2 * (attempt + 1))
            else:
                raise N8nError(_google_error(resp) if resp is not None else "Upload to Google Drive failed (network)")
            if resp.status_code in (200, 201):
                return resp.json()
            rng = resp.headers.get("Range")       # 308: next byte Google expects
            sent = int(rng.split("-")[1]) + 1 if rng else end + 1


def _google_error(resp) -> str:
    try:
        err = resp.json().get("error", {})
        return f"Google Drive: {err.get('message') or err} (HTTP {resp.status_code})"
    except ValueError:
        return f"Google Drive answered HTTP {resp.status_code}"


def push_to_n8n(path: Path, folder_name: str) -> dict:
    """Copies an uploaded Excel file to Google Drive as a Google Sheet, orchestrated by n8n.

    1. n8n (action=start) finds/creates the Drive sub-folder and opens a resumable upload
       session that converts to Google Sheets – the file itself never goes through n8n,
       because n8n Cloud rejects large webhook bodies.
    2. The portal uploads the file straight to Google in 16 MB chunks.
       If Google cannot convert it, the original .xlsx is uploaded instead.
    3. n8n (action=finish) moves every older file in that sub-folder to Drive Trash.

    Returns {"ok", "configured", "message", "link", "drive_removed"}.
    """
    if not settings.NONGRN_N8N_WEBHOOK_URL:
        return {"ok": True, "configured": False, "message": "n8n is not configured – file saved in the portal only.",
                "link": "", "drive_removed": []}
    size = path.stat().st_size
    start = {"action": "start", "folder": folder_name, "fileName": path.name, "size": size, "contentType": XLSX_MIME}
    note = ""
    try:
        session = _n8n_call({**start, "mode": "convert"})
        try:
            uploaded = _upload_to_google(session["uploadUrl"], path)
            result = ("Google Sheet updated" if session.get("updating") else "Google Sheet created")
        except N8nError as exc:
            # conversion refused (e.g. over the 10 M-cell Google Sheets limit) -> keep the exact .xlsx
            note = f"stored as .xlsx because Google could not convert it: {exc}"
            session = _n8n_call({**start, "mode": "raw"})
            uploaded = _upload_to_google(session["uploadUrl"], path)
            result = "Excel file stored in Drive"
        done = _n8n_call({"action": "finish", "folderId": session["folderId"], "fileId": uploaded["id"],
                          "fileName": path.name, "folder": folder_name})
    except N8nError as exc:
        return {"ok": False, "configured": True, "message": str(exc), "link": "", "drive_removed": []}
    if done.get("note"):
        note = "; ".join(filter(None, [note, done["note"]]))
    return {"ok": True, "configured": True, "message": result + (f" ({note})" if note else ""),
            "link": done.get("link") or f"https://drive.google.com/open?id={uploaded['id']}",
            "drive_removed": done.get("removed") or []}


def locked_files(folder: Path) -> list[str]:
    """Files in a source folder that another program (usually Excel) has open."""
    locked = []
    for p in folder.iterdir():
        if not p.is_file() or p.name.startswith("~$"):
            continue
        try:
            with open(p, "r+b"):
                pass
        except PermissionError:
            locked.append(p.name)
        except OSError:
            continue
    return locked


def archive_old_sources(folder: Path, keep: Path) -> list[str]:
    """Only the latest upload stays in a source folder (Power Query reads every file there).

    Older files are moved to NONGRN_ARCHIVE_DIR/<folder>/<timestamp>/ instead of being
    deleted, so a wrong upload can still be undone by moving a file back.
    """
    old = [p for p in folder.iterdir()
           if p.is_file() and p.resolve() != keep.resolve() and not p.name.startswith("~$")]
    if not old:
        return []
    dest = Path(settings.NONGRN_ARCHIVE_DIR) / folder.name / timezone.localtime().strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for p in old:
        try:
            p.replace(dest / p.name)
            moved.append(p.name)
        except OSError:  # e.g. the file is open in Excel – leave it, report nothing for it
            continue
    return moved



# ==========================================================================
# Non GRN Age.xlsx – the full workbook built from the portal data
# ==========================================================================
_build_lock = threading.Lock()


def age_workbook_path() -> Path:
    return Path(settings.NONGRN_DATA_DIR) / "Non GRN Age.xlsx"


def _age_key(as_on: dt.date) -> str:
    return json.dumps([store.tables_version(Path(settings.NONGRN_DATA_DIR)), manual_grn_state(), as_on.isoformat()])


def build_age_workbook(force: bool = False) -> Path:
    """Builds data/Non GRN Age.xlsx as of today (the workbook's TODAY()); cached until the
    data, the Manual GRN rows or the date change."""
    as_on = timezone.localdate()
    path = age_workbook_path()
    meta = path.with_suffix(".json")
    with _build_lock:
        key = _age_key(as_on)
        if not force and path.exists() and meta.exists() and meta.read_text() == key:
            return path
        wbk = get_workbook(as_on)
        if wbk is None:
            raise FileNotFoundError("No data loaded yet – run Refresh All first")
        rows = list(ManualGRN.objects.order_by("id").values_list("invoice_no", "grn_date"))
        wb_writer.build_workbook(Path(settings.NONGRN_TEMPLATE), path, wbk.tables, wbk.ar, wbk.snaps, wbk.fy,
                                 as_on, rows)
        meta.write_text(key)
        return path
