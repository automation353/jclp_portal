"""MTO/MTS aggregation + compute — done in Django, not in the Apps Script.

Why this lives in Django
------------------------
The two Sales Register files are ~57k invoice lines together. Pushing them into
the Google Sheet in 20+ append chunks was dropping rows — the "Sales Register
FY 25-26" tab landed with ~15k of ~40k rows, which starved the in-sheet
compute and left MTO_MTS short (~1,211 items instead of ~1,563).

So we aggregate here instead: each register file is read once (at upload time),
collapsed to per-item monthly buckets, and cached as JSON. On Recompute we merge
the cached aggregates, look up EBQ from the sheet, apply the MTS/MTO decision,
and write just the two compact result tabs ("EBQ Calc", "MTO_MTS", ~1,563 rows
each) straight to the sheet via the Apps Script write_tab endpoint in a single,
reliable call.

The decision logic mirrors the reference "MTO_MTS Details v3" file exactly:
  * MTS Key       = Item Group | Item Code | Party A/C Description
  * Status date   = Goods Received Date for OEM (party == "JCPL-OEM"),
                    otherwise Invoice Date
  * Movement qty  = signed Item Base Qty, bucketed by YYYY-MM of the status date
  * System Status = MTO for any Export party; otherwise MTS when there was
                    movement in every one of the last 6 months, or the 6-month
                    qty >= EBQ; otherwise MTO
  * EBQ value     = Monitoring EBQ, mapped jolly Item Code -> ERP (Master) -> EBQ
"""

import csv
import datetime
import io
import json
import logging
import fcntl
import os
import re
import threading
import time

import requests

log = logging.getLogger(__name__)

# One JSON aggregate per register kind lives here.
STATE_DIR = os.path.join(os.path.dirname(__file__), "mto_mts_state")

# Register columns the aggregation needs (matched by header name, any position).
_COL_ITEM_GROUP = "Item Group"
_COL_ITEM_CODE = "Item Code"            # jolly code in this ERP export
_COL_PARTY = "Party A/C Description"
_COL_CUSTOMER_NAME = "Customer Name"
_COL_GRN_DATE = "Goods Received Date"
_COL_INV_DATE = "Invoice Date"
# The reference EBQ Calc sums Item Sales Qty (not Item Base Qty).
_COL_SALES_QTY = "Item Sales Qty"
_COL_BASE_QTY = "Item Base Qty"

_OEM_PARTY = "JCPL-OEM"
# The reference's MTS-Key party uses this exact exception (see Consolidated col
# [33] / MTS Party): when the customer is Supreme Metal Works (Sale), the party
# component of the key becomes this literal instead of Party A/C Description.
_SUPREME = "Supreme Metal Works (Sale)"


def _mts_party(party, customer_name):
    return _SUPREME if str(customer_name).strip() == _SUPREME else party


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _sheet_id():
    return os.environ.get("JCLP_PPC_R3SS_SHEET_ID", "").strip()


def _apps_script_url():
    return os.environ.get("JCLP_PPC_R3SS_APPS_SCRIPT_URL", "").strip()


# Heavy sheet writes (SR/FY/Consolidated) run in a background thread so uploads
# don't block on ~10-15 min of Apps Script writes. A cross-process file lock
# serializes them so two uploads never write the same tab at once.
_SHEET_LOCK_PATH = os.path.join(STATE_DIR, ".sheet_write.lock")


class _FileLock:
    def __init__(self, path):
        self.path = path
        self.fh = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.fh = open(self.path, "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
            self.fh.close()
        except Exception:
            pass


def _spawn(fn, *args, **kwargs):
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return t


def _num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _ym(v):
    """'YYYY-MM' from a datetime/date or an ISO-ish string; '' if unparseable."""
    if v is None or v == "":
        return ""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return f"{v.year:04d}-{v.month:02d}"
    m = re.match(r"^(\d{4})-(\d{2})", str(v).strip())
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def _seg_from_party(party):
    """Revised Segment = party with a leading 'JCPL-' stripped."""
    return re.sub(r"^JCPL-\s*", "", party, flags=re.IGNORECASE).strip()


def _next_month(y, mo):
    return (y + 1, 1) if mo == 12 else (y, mo + 1)


def _prev_ym(ym):
    """'YYYY-MM' of the month before ym."""
    y, mo = int(ym[:4]), int(ym[5:7])
    return f"{y-1:04d}-12" if mo == 1 else f"{y:04d}-{mo-1:02d}"


def _month_span(start_ym, end_ym):
    """Continuous list of 'YYYY-MM' from start_ym through end_ym inclusive."""
    y, mo = int(start_ym[:4]), int(start_ym[5:7])
    ey, em = int(end_ym[:4]), int(end_ym[5:7])
    out = []
    while (y, mo) <= (ey, em):
        out.append(f"{y:04d}-{mo:02d}")
        y, mo = _next_month(y, mo)
    return out


# ----------------------------------------------------------------------------
# 1) ingest — read one register file and cache its per-item monthly aggregate
# ----------------------------------------------------------------------------
def _read_register(file_path):
    """Load the register's report sheet once; return (columns, rows).

    `columns` is the trimmed Sales-Register column set present in the file (in
    a stable order); `rows` is a list of dicts keyed by those columns. Datetimes
    are converted to ISO strings so the rows are JSON-safe for the sheet write
    and still parseable by _ym().

    read_only cannot stream this ERP export (its stored dimension is wrong and
    truncates to a single cell), so we load the workbook fully.
    """
    import warnings

    from openpyxl import load_workbook
    from .sheet_sync import _SALES_REGISTER_COLUMNS

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(file_path, data_only=True, read_only=False)
    try:
        ws = None
        for name in wb.sheetnames:
            if "sales invoice register report" in name.lower():
                ws = wb[name]
                break
        if ws is None:
            ws = wb[wb.sheetnames[-1]]

        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            return [], []
        idx = {}
        for j, h in enumerate(header):
            name = str(h).strip() if h is not None else ""
            if name and name not in idx:
                idx[name] = j

        need = [_COL_ITEM_GROUP, _COL_ITEM_CODE, _COL_PARTY,
                _COL_GRN_DATE, _COL_INV_DATE, _COL_BASE_QTY]
        missing = [c for c in need if c not in idx]
        if missing:
            raise ValueError(f"register missing columns: {missing}")

        columns = [c for c in _SALES_REGISTER_COLUMNS if c in idx]
        rows = []
        for vals in rows_iter:
            if vals is None:
                continue
            row = {}
            any_data = False
            for c in columns:
                j = idx[c]
                v = vals[j] if j < len(vals) else None
                if isinstance(v, (datetime.datetime, datetime.date)):
                    v = v.isoformat()
                if v is None:
                    v = ""
                else:
                    any_data = True
                row[c] = v
            if any_data:
                rows.append(row)
        return columns, rows
    finally:
        wb.close()


def _aggregate_rows(rows):
    """Collapse register rows into {mts_key: {ig,ic,seg,party,base,months}}.

    Mirrors the reference Consolidated → EBQ Calc chain:
      * MTS Key   = Item Group | Item Code | MTS Party (Supreme exception)
      * Status    = Goods Received Date for OEM else Invoice Date
      * month qty = signed Item Sales Qty (the column the reference SUMIFS)
    """
    items = {}
    line_count = 0
    for r in rows:
        ic = str(r.get(_COL_ITEM_CODE, "")).strip()
        if not ic:
            continue
        ig = str(r.get(_COL_ITEM_GROUP, "")).strip()
        party = str(r.get(_COL_PARTY, "")).strip()
        mparty = _mts_party(party, r.get(_COL_CUSTOMER_NAME, ""))
        seg = _seg_from_party(mparty)
        if ig.lower() == "scrap" or seg.lower() == "scrap":
            continue
        line_count += 1
        key = f"{ig}|{ic}|{mparty}"
        is_oem = party.upper() == _OEM_PARTY
        ym = _ym(r.get(_COL_GRN_DATE) if is_oem else r.get(_COL_INV_DATE))
        qty = _num(r.get(_COL_SALES_QTY))
        base = ("GRN Qty (Goods Received Date)" if is_oem
                else "Dispatch Qty (Invoice Date)")
        it = items.get(key)
        if it is None:
            it = {"ig": ig, "ic": ic, "seg": seg, "party": mparty,
                  "base": base, "months": {}}
            items[key] = it
        if ym:
            it["months"][ym] = it["months"].get(ym, 0.0) + qty
    return items, line_count


def _tab_data_count(tab_name, timeout=40):
    """Data-row count of a tab (excludes the header), via gviz. None on error."""
    try:
        rows = _fetch_csv_tq(tab_name, "select count(A)", timeout=timeout)
    except Exception:
        return None
    try:
        return int(str(rows[-1][0]).strip())
    except (ValueError, IndexError):
        return None


def _fetch_csv_tq(tab_name, tq, timeout=40):
    sid = _sheet_id()
    url = (f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
           f"?tqx=out:csv&sheet={requests.utils.quote(tab_name)}"
           f"&tq={requests.utils.quote(tq)}")
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return list(csv.reader(io.StringIO(resp.text)))


def _post_write_tab(tab_name, headers, rows, append, timeout=300):
    """One write_tab POST straight to Apps Script. Returns True on ok."""
    url = _apps_script_url()
    payload = {"action": "write_tab", "tab_name": tab_name, "headers": headers,
               "rows": rows, "row_count": len(rows), "append": bool(append)}
    try:
        resp = requests.post(url, json=payload, timeout=timeout,
                             allow_redirects=True)
        body = resp.json() if resp.text else {}
    except Exception as exc:
        log.warning("write_tab %s POST error: %s", tab_name, exc)
        return False
    return 200 <= resp.status_code < 300 and bool(body.get("ok"))


def _write_rows_chunked(tab_name, headers, rows, chunk=5000, timeout=300,
                        max_stalls=8):
    """Write raw rows to a sheet tab reliably, direct to Apps Script.

    Chunk 0 clears the tab and writes the header + first chunk (append=false —
    idempotent, so it's safe to retry). Later chunks append. After any failed
    POST we re-read the tab's real row count and resume from exactly there, so a
    lost response never truncates the tab or double-writes rows. This is what the
    old n8n chunked path could not guarantee.
    """
    url = _apps_script_url()
    if not url:
        return {"ok": False, "error": "JCLP_PPC_R3SS_APPS_SCRIPT_URL not set"}
    total = len(rows)

    # Chunk 0: clear + header + first slice. Retry (idempotent clear).
    first = rows[:chunk]
    ok0 = False
    for _ in range(max_stalls):
        if _post_write_tab(tab_name, headers, first, append=False, timeout=timeout):
            ok0 = True
            break
        time.sleep(3)
    if not ok0:
        return {"ok": False, "stage": "clear+header", "written": 0}

    written = len(first)
    stalls = 0
    while written < total:
        part = rows[written:written + chunk]
        if _post_write_tab(tab_name, headers, part, append=True, timeout=timeout):
            written += len(part)
            stalls = 0
            continue
        # Lost/failed response — resync from the real sheet count and resume.
        stalls += 1
        time.sleep(3)
        cnt = _tab_data_count(tab_name)
        if cnt is not None and 0 <= cnt <= total:
            written = cnt
        if stalls >= max_stalls:
            return {"ok": False, "stage": "append", "written": written,
                    "expected": total}

    final = _tab_data_count(tab_name)
    ok = final is None or final >= total  # trust the writes if count unreadable
    return {"ok": ok, "rows_written": written, "sheet_count": final,
            "expected": total}


def ingest_register(file_path, kind, original_filename="", uploader="system"):
    """Read a register file and cache its aggregate as <kind>.json.

    kind is 'current' (SR 26-27) or 'fy' (Sales Register FY 25-26).
    Returns a small summary dict.
    """
    if kind not in ("current", "fy"):
        return {"ok": False, "error": f"unknown register kind '{kind}'"}
    os.makedirs(STATE_DIR, exist_ok=True)

    # Read the file once → raw trimmed rows (for the sheet tab) + aggregate.
    columns, rows = _read_register(file_path)
    items, line_count = _aggregate_rows(rows)

    state = {
        "kind": kind,
        "source_file": os.path.basename(file_path),
        "original_filename": original_filename,
        "uploader": uploader,
        "ingested_at": datetime.datetime.utcnow().isoformat() + "Z",
        "line_count": line_count,
        "item_count": len(items),
        "items": items,
    }
    path = os.path.join(STATE_DIR, f"{kind}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, path)

    # Persist the raw rows too, so the Consolidated rebuild can merge both
    # registers without re-reading the (large) source files.
    rows_path = os.path.join(STATE_DIR, f"{kind}_rows.json")
    tmp2 = rows_path + ".tmp"
    with open(tmp2, "w") as fh:
        json.dump({"columns": columns, "rows": rows}, fh)
    os.replace(tmp2, rows_path)

    # The raw tabs (SR/FY ~16-40k rows + the merged Consolidated ~57k) take
    # ~10-15 min of Apps Script writes — far too long to block the upload
    # request. Write them in the background; the aggregate above already makes
    # MTO/MTS ready, so a Recompute reflects this upload immediately.
    tab = "Sales Register FY 25-26" if kind == "fy" else "SR 26-27"
    _spawn(_bg_write_raw_tabs, kind, columns, rows)

    log.info("MTO/MTS ingest %s: %d raw rows, %d agg lines, %d items -> %s "
             "(SR/FY + Consolidated writing in background)",
             kind, len(rows), line_count, len(items), path)
    return {"ok": True, "kind": kind, "line_count": line_count,
            "item_count": len(items), "raw_rows": len(rows),
            "source_file": state["source_file"],
            "sheet_tab": tab,
            "sheet_write": {"status": "writing in background (~10-15 min)"}}


def _load_raw_rows(kind):
    path = os.path.join(STATE_DIR, f"{kind}_rows.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


# Consolidated computed columns appended after the register columns (matches the
# reference Consolidated tab's derived columns).
CONSOL_COMPUTED = ["Financial Year", "MTS Party", "MTS Key",
                   "Status Date", "Status Month"]


def build_consolidated():
    """Merge both registers' raw rows into the reference-style Consolidated grid.

    Returns (headers, rows) or None if no register has been ingested yet. Each
    row carries the register columns plus the computed columns:
      Financial Year, MTS Party, MTS Key, Status Date, Status Month.
    """
    parts = [p for p in (_load_raw_rows("fy"), _load_raw_rows("current")) if p]
    if not parts:
        return None
    # Column order: union of register columns (first part wins order) + computed.
    columns = []
    for p in parts:
        for c in p["columns"]:
            if c not in columns:
                columns.append(c)
    headers = columns + CONSOL_COMPUTED

    out = []
    for p in parts:
        for r in p["rows"]:
            ic = str(r.get(_COL_ITEM_CODE, "")).strip()
            if not ic:
                continue
            ig = str(r.get(_COL_ITEM_GROUP, "")).strip()
            party = str(r.get(_COL_PARTY, "")).strip()
            mparty = _mts_party(party, r.get(_COL_CUSTOMER_NAME, ""))
            is_oem = party.upper() == _OEM_PARTY
            status_date = r.get(_COL_GRN_DATE) if is_oem else r.get(_COL_INV_DATE)
            status_date = status_date if status_date else ""
            ym = _ym(status_date)
            inv = str(r.get(_COL_INV_DATE) or "")
            fy = inv[:4] if len(inv) >= 4 and inv[:4].isdigit() else ""
            row = dict(r)
            row["Financial Year"] = fy
            row["MTS Party"] = mparty
            row["MTS Key"] = f"{ig}|{ic}|{mparty}"
            row["Status Date"] = str(status_date)[:10] if status_date else ""
            row["Status Month"] = (ym + "-01") if ym else ""
            out.append(row)
    return headers, out


def _load_state(kind):
    path = os.path.join(STATE_DIR, f"{kind}.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def _merge_states():
    """Merge current + fy aggregates: sum months per key, union identity."""
    merged = {}
    sources = {}
    for kind in ("fy", "current"):   # current second so its identity wins ties
        st = _load_state(kind)
        if not st:
            continue
        sources[kind] = {
            "source_file": st.get("source_file"),
            "line_count": st.get("line_count"),
            "item_count": st.get("item_count"),
            "ingested_at": st.get("ingested_at"),
        }
        for key, it in st["items"].items():
            m = merged.get(key)
            if m is None:
                m = {"ig": it["ig"], "ic": it["ic"], "seg": it["seg"],
                     "party": it["party"], "base": it["base"], "months": {}}
                merged[key] = m
            else:
                # keep the most descriptive identity we have
                m["ig"] = m["ig"] or it["ig"]
                m["seg"] = m["seg"] or it["seg"]
                m["base"] = it["base"] or m["base"]
            for ym, q in it["months"].items():
                m["months"][ym] = m["months"].get(ym, 0.0) + q
    return merged, sources


# ----------------------------------------------------------------------------
# 2) EBQ lookup — jolly Item Code -> ERP (Master) -> EBQ (Monitoring)
# ----------------------------------------------------------------------------
def _fetch_csv(tab_name, timeout=60):
    sid = _sheet_id()
    if not sid:
        raise RuntimeError("JCLP_PPC_R3SS_SHEET_ID not configured")
    url = (
        f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
        f"?tqx=out:csv&sheet={requests.utils.quote(tab_name)}"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return list(csv.reader(io.StringIO(resp.text)))


def _col_index(headers, *candidates):
    norm = [h.strip().lower() for h in headers]
    for cand in candidates:
        c = cand.strip().lower()
        if c in norm:
            return norm.index(c)
    return -1


def _build_ebq_map():
    """Return (ebq_for(jolly_code) -> float, stats dict)."""
    jolly_to_erp = {}
    try:
        master = _fetch_csv("Master")
    except Exception as exc:
        log.warning("EBQ: could not read Master tab: %s", exc)
        master = []
    if master:
        h = master[0]
        j_col = _col_index(h, "Jolly Code", "FG Item Code", "Item Code")
        e_col = _col_index(h, "ERP Part Code")
        if j_col >= 0 and e_col >= 0:
            for r in master[1:]:
                if j_col < len(r) and e_col < len(r):
                    j = str(r[j_col]).strip().upper()
                    e = str(r[e_col]).strip().upper()
                    if j and j not in jolly_to_erp:
                        jolly_to_erp[j] = e

    erp_ebq = {}
    try:
        mon = _fetch_csv("Monitoring")
    except Exception as exc:
        log.warning("EBQ: could not read Monitoring tab: %s", exc)
        mon = []
    if mon:
        h = mon[0]
        e_col = _col_index(h, "item_code", "ERP Part Code", "Item Name")
        b_col = _col_index(h, "ebq", "EBQ")
        if e_col >= 0 and b_col >= 0:
            for r in mon[1:]:
                if e_col < len(r) and b_col < len(r):
                    e = str(r[e_col]).strip().upper()
                    if e:
                        erp_ebq[e] = _num(r[b_col])

    def ebq_for(jolly):
        erp = jolly_to_erp.get(str(jolly).strip().upper())
        return _num(erp_ebq.get(erp)) if erp else 0.0

    stats = {"master_jolly_codes": len(jolly_to_erp),
             "monitoring_ebq_codes": len(erp_ebq)}
    return ebq_for, stats


def _load_existing_overrides():
    """Carry manual overrides across recomputes: MTS Key -> override fields."""
    out = {}
    try:
        rows = _fetch_csv("MTO_MTS")
    except Exception:
        return out
    if not rows:
        return out
    h = rows[0]
    k = _col_index(h, "MTS Key")
    ov = _col_index(h, "Override Status (MTS/MTO)")
    rs = _col_index(h, "Reason for Change")
    cb = _col_index(h, "Changed By")
    cd = _col_index(h, "Change Date")
    if k < 0 or ov < 0:
        return out
    for r in rows[1:]:
        if k >= len(r):
            continue
        key = r[k]
        val = r[ov].strip() if ov < len(r) and r[ov] else ""
        if key and val:
            out[key] = {
                "override": val,
                "reason": r[rs] if 0 <= rs < len(r) else "",
                "changed_by": r[cb] if 0 <= cb < len(r) else "",
                "change_date": r[cd] if 0 <= cd < len(r) else "",
            }
    return out


# ----------------------------------------------------------------------------
# 3) build the EBQ Calc + MTO_MTS grids
# ----------------------------------------------------------------------------
EBQ_CALC_FIXED = ["Item Group", "Item Code", "Revised Segment",
                  "Party A/C Description", "MTS Key", "Base Data", "EBQ"]
# MTO_MTS layout mirrors the reference "MTO_MTS Details V3" exactly:
#   ID + [per-month status] + [Status, Note] + decision/override block + MTS Key.
MTO_MTS_ID = ["Item Group", "Item Code", "Revised Segment",
              "Party A/C Description"]
MTO_MTS_MID = ["Status", "Note"]           # after the month columns
MTO_MTS_TAIL = ["Movement Months (Last 6M)", "Qty (Last 6M)", "EBQ",
                "No-Movement Months (Last 6M)", "System Status",
                "Override Status (MTS/MTO)", "Reason for Change",
                "Changed By", "Change Date", "Final Status",
                "Override Check", "MTS Key"]


def build_grids():
    merged, sources = _merge_states()
    if not merged:
        return None
    ebq_for, ebq_stats = _build_ebq_map()
    overrides = _load_existing_overrides()

    month_set = set()
    for it in merged.values():
        month_set.update(it["months"].keys())
    today = datetime.date.today()
    now_ym = f"{today.year:04d}-{today.month:02d}"
    data_months = sorted(month_set)
    start_ym = data_months[0] if data_months else now_ym
    last_data = data_months[-1] if data_months else now_ym
    # Display months: earliest data month → current calendar month (so the
    # current month is a visible column even when it has no sales yet), extended
    # if data somehow runs ahead of the clock.
    end_ym = max(now_ym, last_data)
    all_months = _month_span(start_ym, end_ym)

    # Decision window (matches the reference exactly): the last 6 *complete*
    # months, i.e. ending at the month BEFORE the current calendar month, and
    # never past the last month that actually has data. The current/partial
    # month is shown but excluded from the MTS/MTO decision.
    window_end = min(_prev_ym(now_ym), last_data)
    win_start = window_end
    for _ in range(5):
        win_start = _prev_ym(win_start)
    window_months = _month_span(win_start, window_end)   # 6 months, inclusive

    def _decide(months, win, ebq, is_export):
        """Reference rule over a 6-month window `win`.

        MTS if movement (qty>0) in all 6 months, OR in exactly 5 of 6 with EBQ>0
        and 6-month qty >= EBQ. Export parties are forced to MTO (business rule
        added on top of the reference). Returns (status, moves, window_qty).
        """
        moves = 0
        qtyw = 0.0
        for m in win:
            q = months.get(m, 0.0)
            qtyw += q
            if q > 0:
                moves += 1
        if is_export:
            return "MTO", moves, qtyw
        if moves == 6 or (moves == 5 and ebq > 0 and qtyw >= ebq):
            return "MTS", moves, qtyw
        return "MTO", moves, qtyw

    def status_at(months, i, ebq, is_export):
        # Per-month column = decision over the 6 complete months BEFORE month i
        # (so month i itself, like the current month, is never in its own window).
        if i < 6:
            return ""
        win = all_months[i - 6:i]
        return _decide(months, win, ebq, is_export)[0]

    ebq_headers = EBQ_CALC_FIXED + all_months
    mto_headers = MTO_MTS_ID + all_months + MTO_MTS_MID + MTO_MTS_TAIL
    ebq_rows, mto_rows = [], []
    counts = {"MTS": 0, "MTO": 0}

    for key in sorted(merged.keys()):
        it = merged[key]
        months = it["months"]
        ebq = ebq_for(it["ic"])
        is_export = "EXPORT" in it["party"].upper()

        er = {"Item Group": it["ig"], "Item Code": it["ic"],
              "Revised Segment": it["seg"], "Party A/C Description": it["party"],
              "MTS Key": key, "Base Data": it["base"], "EBQ": ebq}
        for m in all_months:
            er[m] = round(months.get(m, 0.0))
        ebq_rows.append(er)

        row = {"Item Group": it["ig"], "Item Code": it["ic"],
               "Revised Segment": it["seg"],
               "Party A/C Description": it["party"], "MTS Key": key}
        monthly_status = []
        for i, m in enumerate(all_months):
            s = status_at(months, i, ebq, is_export)
            row[m] = s
            if s:
                monthly_status.append(s)

        # 3-way "Status" across the per-month cells (reference COUNTIF logic):
        # Consistent MTS if no month is MTO, Consistent MTO if no month is MTS,
        # else Fluctuating.
        if monthly_status.count("MTO") == 0:
            status3 = "Consistent MTS"
        elif monthly_status.count("MTS") == 0:
            status3 = "Consistent MTO"
        else:
            status3 = "Fluctuating Status"

        sysst, move_months, qty6 = _decide(months, window_months, ebq, is_export)
        no_move = 6 - move_months

        ovr = overrides.get(key, {})
        override_val = ovr.get("override", "")
        reason = ovr.get("reason", "")
        final = override_val if override_val in ("MTS", "MTO") else sysst
        # Override Check (reference validation helper).
        if not override_val:
            override_check = "No Change"
        elif not str(reason).strip():
            override_check = "Reason Required"
        else:
            override_check = "Changed"
        counts[final] = counts.get(final, 0) + 1

        row.update({
            "Status": status3,
            "Note": "",
            "Movement Months (Last 6M)": move_months,
            "Qty (Last 6M)": round(qty6),
            "EBQ": ebq,
            "No-Movement Months (Last 6M)": no_move,
            "System Status": sysst,
            "Override Status (MTS/MTO)": override_val,
            "Reason for Change": reason,
            "Changed By": ovr.get("changed_by", ""),
            "Change Date": ovr.get("change_date", ""),
            "Final Status": final,
            "Override Check": override_check,
            "MTS Key": key,
        })
        mto_rows.append(row)

    summary = {
        "items": len(mto_rows),
        "months": len(all_months),
        "month_range": [all_months[0], all_months[-1]] if all_months else [],
        "decision_window": window_months,
        "last_data_month": last_data,
        "final_counts": counts,
        "ebq_stats": ebq_stats,
        "overrides_carried": len(overrides),
        "sources": sources,
    }
    return {
        "ebq_headers": ebq_headers, "ebq_rows": ebq_rows,
        "mto_headers": mto_headers, "mto_rows": mto_rows,
        "summary": summary,
    }


# ----------------------------------------------------------------------------
# 4) write a tab straight to the Apps Script (single reliable call)
# ----------------------------------------------------------------------------
def _write_tab_direct(tab_name, headers, rows, timeout=300, attempts=3):
    """Single-shot write_tab (clears + writes) with retry + count verify.

    append=false means the call is idempotent, so retrying is safe. A lost/
    non-JSON response can still mean the write succeeded, so after a bad response
    we verify by the tab's real row count before declaring failure.
    """
    url = _apps_script_url()
    if not url:
        return {"ok": False, "error": "JCLP_PPC_R3SS_APPS_SCRIPT_URL not set"}
    payload = {"action": "write_tab", "tab_name": tab_name,
               "headers": headers, "rows": rows, "row_count": len(rows)}
    last = {}
    for i in range(attempts):
        try:
            resp = requests.post(url, json=payload, timeout=timeout,
                                 allow_redirects=True)
            body = resp.json() if resp.text else {}
            if 200 <= resp.status_code < 300 and body.get("ok"):
                return {"ok": True, "rows_written": body.get("rows_written")}
            last = {"http_status": resp.status_code, "body": str(body)[:150]}
        except Exception as exc:
            last = {"error": str(exc)}
        time.sleep(2)
        cnt = _tab_data_count(tab_name)   # write may have landed despite a lost reply
        if cnt is not None and cnt >= len(rows):
            return {"ok": True, "rows_written": cnt, "note": "verified by count"}
    return {"ok": False, **last}


def compute_and_write():
    """Rebuild EBQ Calc + MTO_MTS from the cached aggregates and write them.

    These are small (~1.5k rows) so they write fast and synchronously — this is
    what a Recompute runs. The heavy raw tabs (SR/FY + Consolidated) are written
    in the background at upload time (see ingest_register), because they only
    change when a register changes and are far too large (~57k rows) to write
    inside a request. The R3SS MTO/MTS column is patched by the Apps Script
    computeMtoMts() hook the recompute triggers right after this.

    Returns {"ok": bool, "summary": {...}, "writes": {...}} — never raises.
    """
    try:
        grids = build_grids()
    except Exception as exc:
        log.exception("MTO/MTS build failed")
        return {"ok": False, "error": str(exc)}
    if not grids:
        return {"ok": False, "skipped": True,
                "reason": "No Sales Register uploaded yet — upload SR 26-27 "
                          "and Sales Register FY 25-26 first."}

    w_ebq = _write_tab_direct("EBQ Calc", grids["ebq_headers"], grids["ebq_rows"])
    w_mto = _write_tab_direct("MTO_MTS", grids["mto_headers"], grids["mto_rows"])
    return {
        "ok": bool(w_ebq.get("ok") and w_mto.get("ok")),
        "summary": grids["summary"],
        "writes": {"EBQ Calc": w_ebq, "MTO_MTS": w_mto},
    }


def _bg_write_raw_tabs(kind, columns, rows):
    """Background job: write this register's raw tab, then rebuild + write the
    merged Consolidated tab. Serialized across processes by a file lock so two
    uploads never write the same tab at once."""
    try:
        with _FileLock(_SHEET_LOCK_PATH):
            tab = "Sales Register FY 25-26" if kind == "fy" else "SR 26-27"
            r1 = _write_rows_chunked(tab, columns, rows)
            log.info("bg raw tab %s: %s", tab, r1)
            consol = build_consolidated()
            if consol:
                headers, crows = consol
                r2 = _write_rows_chunked("Consolidated", headers, crows)
                log.info("bg Consolidated: %s", r2)
    except Exception:
        log.exception("bg raw-tab write failed for %s", kind)
