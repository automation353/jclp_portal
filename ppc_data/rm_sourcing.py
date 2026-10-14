"""RM Sourcing (RMCP) — BOM ingest.

Isolated from the R3SS / MTO-MTS pipeline. The only upload in v1 is the BOM
(from TCS iON, Plant P1). It is trimmed to the columns the explosion needs and
pushed to the RMCP Google Sheet's "BOM" tab through the RMCP n8n webhook
(→ Apps Script write_tab). Plan is read from the existing R3SS sheet; Stock /
Green Level come later (Purchase Dashboard).

Env:
  JCLP_RMCP_WEBHOOK          — n8n webhook for the RMCP pipeline
  JCLP_RMCP_APPS_SCRIPT_URL  — RMCP Apps Script /exec (used by later compute)
  JCLP_RMCP_SHEET_ID         — RMCP Google Sheet id (used by later compute)
"""

import csv
import datetime
import io
import json
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

STATE_DIR = os.path.join(os.path.dirname(__file__), "rm_sourcing_state")

BOM_TAB = "BOM"                       # source dump (only non-reference tab kept)
PLAN_TAB = "Plan"
CP_REQ_TAB = "CP Req"
RM_REQ_TAB = "RM Req"
RM_QTY_TAB = "RM QTY"
QTY_SHEET_TAB = "Quantity Sheet"
RM_QUANTITY_TAB = RM_QTY_TAB          # back-compat alias for read_rm_quantity

# Plan tab = the R3SS dashboard columns (per the process doc), in this order.
PLAN_HEADERS = ["Sr No.", "Family", "Customer", "Cust Part No", "JollySize",
                "ERP Code", "BOM Code", "Quantity"]
# CP Req columns match the reference exactly: A=BOM Code, B=Item Code,
# C=BOM Qty (per 1000), D=Qty in Nos (planned qty, VLOOKUP from Plan),
# E=Qty (Base UOM) = D×C/1000 (the requirement), F=UOM, G=Part Description.
CP_REQ_HEADERS = ["BOM Code", "Item Code", "BOM Qty", "Qty in Nos",
                  "Qty (Base UOM)", "UOM", "Part Description"]
# RM Req = line-level RM explosion, same columns as the reference RM Req /
# CP Req: one row per FG → RM with the planned qty and the RM requirement.
RM_REQ_HEADERS = ["BOM Code", "Item Code", "BOM Qty", "Qty in Nos",
                  "Qty (Base UOM)", "UOM", "Part Description"]
# RM QTY = the pivot handed to Purchase, matching the reference columns B–F.
# Qty = computed (BOM × plan); Reqd Qty = the PPC head's manual final quantity
# (preserved across recomputes, never overwritten by the automation); Qty +10%
# = Qty × 1.1 helper. No green level here — the reference carries green only in
# the "Against Demand" tabs, where Purchase nets it.
RM_QTY_HEADERS = ["Item Code", "Description", "Qty", "Reqd Qty (in kgs)", "Qty +10%"]
# Quantity Sheet = CP + packing, full reference columns. Qty (Base UOM) = our
# computed requirement (SUMIF). qty per kg comes from the CP team's external
# conversion sheet (not loaded yet) → blank; the two "Qty in nos" columns depend
# on it, so they stay blank until that feed exists. Reqd Qty = manual (preserved).
QTY_SHEET_HEADERS = ["Item Code", "Description", "UOM", "Qty (Base UOM)",
                     "qty per kg", "Qty in nos (ERP)", "Reqd Qty",
                     "Qty in nos (Correction)"]
AD_RM_TAB = "Against Demand RM"
AD_RM_HEADERS = ["Item Code", "Description", "Demand", "To Plan", "Stock",
                 "Green Level", "Procurement"]


def _num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _strip_p1(code):
    """BOM parent codes carry a 'P1' plant prefix; the R3SS plan is keyed by the
    jolly code without it (e.g. 'P1WP M04 B01 J6 3M' → 'WP M04 B01 J6 3M')."""
    c = str(code).strip()
    return c[2:].strip() if c[:2].upper() == "P1" else c


def _is_rm(code):
    """Raw-material item codes start with RM or R1 (RMSS strips, R1A* metals)."""
    c = str(code).strip().upper()
    return c.startswith("RM") or c.startswith("R1")
# RMCP "BOM" tab columns (match RMCP_AppsScript.gs).
BOM_HEADERS = ["BOM Code", "Item Code", "BOM Qty (per 1000)", "UOM",
               "Part Description"]

# Plant P1 only (the doc: P2/P3 double-count). In the TCS iON dump the P1 rows
# carry Site == "JCPL01"; filtering on it also drops the template's junk header/
# descriptor rows (their Site is blank or "Select"/"M").
P1_SITE = "JCPL01"

# Fuzzy source→target column mapping for the TCS iON BOM dump. Each target keeps
# the first source header whose lowercased name matches any of these needles.
_BOM_COL_MATCH = {
    "BOM Code": ["bom code", "parent item code", "parent code", "parent item"],
    "Item Code": ["item code", "child item", "component code", "part code"],
    "BOM Qty (per 1000)": ["bom qty", "bom quantity", "qty (per 1000)"],
    "UOM": ["bom uom", "uom", "unit of measure", "unit"],
    "Part Description": ["item description", "part description", "description"],
}
_SITE_NEEDLES = ["site"]


def _rmcp_webhook():
    return os.environ.get("JCLP_RMCP_WEBHOOK", "").strip()


def _rmcp_apps_url():
    return os.environ.get("JCLP_RMCP_APPS_SCRIPT_URL", "").strip()


def _rmcp_sheet_id():
    return os.environ.get("JCLP_RMCP_SHEET_ID", "").strip()


def _r3ss_sheet_id():
    return os.environ.get("JCLP_PPC_R3SS_SHEET_ID", "").strip()


def _read_master_schedule():
    """Read the MpsSS Schedule Form (the 'Master' tab in the R3SS sheet).

    Returns rows (dicts) that have an 'FG' (the BOM Code = P1-prefixed FG code,
    from Schedule Form col V), plus the other Plan columns. Master headers carry
    trailing spaces, so match is done on stripped, lowercased names.
    """
    sid = _r3ss_sheet_id()
    if not sid:
        return []
    url = (f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
           f"?tqx=out:csv&headers=1&sheet=Master")
    rows = list(csv.reader(io.StringIO(
        requests.get(url, timeout=60).text)))
    if not rows:
        return []
    norm = [h.strip().lower() for h in rows[0]]

    def col(name):
        n = name.strip().lower()
        return norm.index(n) if n in norm else -1

    idx = {
        "FG": col("FG"), "Jolly Code": col("Jolly Code"),
        "Family": col("Family"), "Customer": col("Customer"),
        "Cust Part No": col("Cust Part No"), "JollySize": col("JollySize"),
        "ERP Code": col("ERP Part Code"),
    }
    out = []
    for r in rows[1:]:
        def g(k):
            i = idx[k]
            return (r[i].strip() if i >= 0 and i < len(r) and r[i] else "")
        fg = g("FG")
        if not fg:
            continue
        out.append({k: g(k) for k in idx})
    return out


def _rmcp_tab_count(tab_name, timeout=40):
    """Data-row count of an RMCP tab (excludes header) via gviz. None on error."""
    sid = _rmcp_sheet_id()
    if not sid:
        return None
    url = (f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
           f"?tqx=out:csv&sheet={requests.utils.quote(tab_name)}"
           f"&tq={requests.utils.quote('select count(A)')}")
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return int(str(list(csv.reader(io.StringIO(resp.text)))[-1][0]).strip())
    except Exception:
        return None


def _rmcp_post_write(tab_name, headers, rows, append, timeout=300):
    url = _rmcp_apps_url()
    payload = {"action": "write_tab", "tab_name": tab_name, "headers": headers,
               "rows": rows, "row_count": len(rows), "append": bool(append)}
    try:
        resp = requests.post(url, json=payload, timeout=timeout, allow_redirects=True)
        body = resp.json() if resp.text else {}
    except Exception as exc:
        log.warning("RMCP write_tab %s POST error: %s", tab_name, exc)
        return False
    return 200 <= resp.status_code < 300 and bool(body.get("ok"))


def _write_tab_resumable(tab_name, headers, rows, chunk=5000, timeout=300,
                         max_stalls=8):
    """Write rows straight to the RMCP Apps Script, resumably.

    Chunk 0 clears + writes header (idempotent, safe to retry); later chunks
    append. After any failed POST we re-read the tab's real row count and resume
    from exactly there — so a lost response never truncates or double-writes.
    This is what the n8n path could not do for large (~38k-row) uploads.
    """
    if not _rmcp_apps_url():
        return {"ok": False, "error": "JCLP_RMCP_APPS_SCRIPT_URL not set"}
    total = len(rows)
    first = rows[:chunk]
    ok0 = False
    for _ in range(max_stalls):
        if _rmcp_post_write(tab_name, headers, first, append=False, timeout=timeout):
            ok0 = True
            break
        time.sleep(3)
    if not ok0:
        return {"ok": False, "stage": "clear+header", "written": 0}

    written = len(first)
    stalls = 0
    while written < total:
        part = rows[written:written + chunk]
        if _rmcp_post_write(tab_name, headers, part, append=True, timeout=timeout):
            written += len(part)
            stalls = 0
            continue
        stalls += 1
        time.sleep(3)
        cnt = _rmcp_tab_count(tab_name)
        if cnt is not None and 0 <= cnt <= total:
            written = cnt
        if stalls >= max_stalls:
            return {"ok": False, "stage": "append", "written": written,
                    "expected": total}

    final = _rmcp_tab_count(tab_name)
    ok = final is None or final >= total
    return {"ok": ok, "rows_written": written, "sheet_count": final,
            "expected": total}


def _read_bom(file_path):
    """Read the BOM dump, detect its header row, trim to BOM_HEADERS.

    Returns (matched_map, rows) where rows is a list of dicts keyed by
    BOM_HEADERS. read_only=False because these ERP exports mis-report their
    dimensions in streaming mode (same as the Sales Register).
    """
    import warnings

    from openpyxl import load_workbook

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(file_path, data_only=True, read_only=False)
    try:
        # Pick the sheet with the most rows (the dump), not a cover sheet.
        ws = max(wb.worksheets, key=lambda s: (s.max_row or 0) * (s.max_column or 0))
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return {}, []

        # Header row = the one that actually contains "BOM Code" + "Item Code".
        # (The TCS iON template has descriptor rows with MORE filled cells than
        # the real header, so "most non-empty" is unreliable here.)
        hi = None
        for i, r in enumerate(all_rows[:15]):
            low = [str(c).strip().lower() if c is not None else "" for c in r]
            if "bom code" in low and "item code" in low:
                hi = i
                break
        if hi is None:                       # fallback: most non-empty in first 10
            best = 0
            for i, r in enumerate(all_rows[:10]):
                ne = sum(1 for c in r if c is not None and str(c).strip())
                if ne > best:
                    best, hi = ne, i
        headers = [str(h).strip() if h is not None else "" for h in all_rows[hi]]
        norm = [h.lower() for h in headers]

        # Map each target column to a source index via the needles.
        col_idx = {}
        matched = {}
        for target, needles in _BOM_COL_MATCH.items():
            for j, name in enumerate(norm):
                if name and any(n in name for n in needles) and j not in col_idx.values():
                    col_idx[target] = j
                    matched[target] = headers[j]
                    break
        # Locate the Site column for the P1 filter.
        site_j = next((j for j, name in enumerate(norm)
                       if any(n == name for n in _SITE_NEEDLES)), None)

        rows = []
        for r in all_rows[hi + 1:]:
            # Plant P1 only — this also skips the template's junk/descriptor rows.
            if site_j is not None:
                site = str(r[site_j]).strip() if site_j < len(r) and r[site_j] is not None else ""
                if site != P1_SITE:
                    continue
            row = {}
            for target in BOM_HEADERS:
                j = col_idx.get(target)
                v = r[j] if (j is not None and j < len(r)) else None
                if isinstance(v, (datetime.datetime, datetime.date)):
                    v = v.isoformat()
                row[target] = v if v is not None else ""
            # A real BOM line needs at least a parent + item code.
            if str(row.get("BOM Code", "")).strip() and \
               str(row.get("Item Code", "")).strip():
                rows.append(row)
        return matched, rows
    finally:
        wb.close()


def ingest_bom(file_path, original_filename="", uploader="system", chunk=5000):
    """Read + trim the BOM (Plant P1) and write it to the RMCP 'BOM' tab.

    Writes straight to the RMCP Apps Script with a resumable chunked writer —
    n8n cloud errors out on the ~38k-row BOM, so the heavy write bypasses it
    (same fix used for the 40k-row FY register). Never raises.
    """
    if not _rmcp_apps_url():
        return {"ok": False, "error": "JCLP_RMCP_APPS_SCRIPT_URL not set."}
    try:
        matched, rows = _read_bom(file_path)
    except Exception as exc:
        log.exception("BOM read failed for %s", file_path)
        return {"ok": False, "error": str(exc)}
    if not rows:
        return {"ok": False, "error": "No P1 (JCPL01) BOM rows found — check the file.",
                "matched_columns": matched}

    # Cache the trimmed BOM so the explosion doesn't re-read the big file.
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = os.path.join(STATE_DIR, "bom.json.tmp")
    with open(tmp, "w") as fh:
        json.dump({"rows": rows, "matched": matched,
                   "ingested_at": datetime.datetime.utcnow().isoformat() + "Z"}, fh)
    os.replace(tmp, os.path.join(STATE_DIR, "bom.json"))

    write = _write_tab_resumable(BOM_TAB, BOM_HEADERS, rows, chunk=chunk)
    log.info("RMCP BOM ingest: %d P1 rows | matched %s | write %s",
             len(rows), matched, write)

    # Explode against the current R3SS plan → CP Required + RM Quantity.
    compute = compute_rm()
    return {"ok": bool(write.get("ok")), "total_rows": len(rows),
            "matched_columns": matched, "tab": BOM_TAB, "write": write,
            "compute": compute}


def _load_bom_cache():
    path = os.path.join(STATE_DIR, "bom.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def repush_bom(chunk=4000):
    """Re-write the cached BOM to the BOM tab (no file re-read). Used after a
    sheet reset."""
    cache = _load_bom_cache()
    if not cache:
        return {"ok": False, "error": "No BOM cached."}
    return _write_tab_resumable(BOM_TAB, BOM_HEADERS, cache["rows"], chunk=chunk)


def check_data_quality():
    """Rule 19 — one part number, one description. Read-only scan of the cached
    BOM: find item codes with a blank description and item codes that carry more
    than one distinct description (duplicates/conflicts). No writes, no recompute.
    """
    cache = _load_bom_cache()
    if not cache:
        return {"ok": False, "error": "No BOM cached — upload the BOM first."}
    rows = cache["rows"] if isinstance(cache, dict) else cache
    desc_by_code = {}          # Item Code -> set of distinct non-blank descriptions
    blank = set()
    for r in rows:
        code = (r.get("Item Code") or "").strip()
        if not code:
            continue
        desc = (r.get("Part Description") or "").replace(" ", " ").strip()
        if desc:
            desc_by_code.setdefault(code, set()).add(desc)
        else:
            blank.add(code)
    blank_only = sorted(c for c in blank if c not in desc_by_code)
    conflicting = sorted(c for c, ds in desc_by_code.items() if len(ds) > 1)
    return {
        "ok": True,
        "total_items": len(set(desc_by_code) | blank),
        "blank_desc_count": len(blank_only),
        "conflicting_desc_count": len(conflicting),
        "blank_desc": blank_only[:50],
        "conflicting_desc": [{"code": c, "descriptions": sorted(desc_by_code[c])}
                             for c in conflicting[:50]],
    }


def read_rm_by_bom():
    """Product-centric view (cached): each FG (BOM Code) → its RM needs."""
    path = os.path.join(STATE_DIR, "rm_by_bom.json")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return json.load(fh)


def read_rm_usage(rm_code, timeout=40):
    """Which FGs consume a given RM — the CP Req lines where Item Code == rm_code.
    Returns [{bom_code, planned_qty, requirement, description}], sorted desc."""
    sid = _rmcp_sheet_id()
    if not sid or not rm_code:
        return []
    code = rm_code.replace("'", "''")
    tq = (f"select A, D, E, G where B = '{code}' order by E desc")
    url = (f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
           f"?tqx=out:csv&sheet={requests.utils.quote(CP_REQ_TAB)}"
           f"&tq={requests.utils.quote(tq)}")
    try:
        rows = list(csv.reader(io.StringIO(requests.get(url, timeout=timeout).text)))
    except Exception as exc:
        log.warning("read RM usage failed: %s", exc)
        return []
    out = []
    for r in rows[1:]:
        if len(r) >= 4 and r[0].strip():
            out.append({"bom_code": r[0], "planned_qty": r[1],
                        "requirement": r[2], "description": r[3]})
    return out


def _read_tab(tab_name, timeout=40):
    """Read any RMCP tab → list of row dicts keyed by header."""
    sid = _rmcp_sheet_id()
    if not sid:
        return []
    url = (f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
           f"?tqx=out:csv&sheet={requests.utils.quote(tab_name)}")
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        rows = list(csv.reader(io.StringIO(resp.text)))
    except Exception as exc:
        log.warning("read %s failed: %s", tab_name, exc)
        return []
    if not rows:
        return []
    hdr = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        out.append({hdr[i]: (r[i] if i < len(r) else "")
                    for i in range(len(hdr)) if hdr[i]})
    return out


def read_quantity_sheet():
    """CP + packing requirement (Quantity Sheet tab)."""
    return _read_tab(QTY_SHEET_TAB)


def read_rm_quantity(timeout=40):
    """Read the RM Quantity tab from the RMCP sheet → list of row dicts."""
    sid = _rmcp_sheet_id()
    if not sid:
        return []
    url = (f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
           f"?tqx=out:csv&sheet={requests.utils.quote(RM_QUANTITY_TAB)}")
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        rows = list(csv.reader(io.StringIO(resp.text)))
    except Exception as exc:
        log.warning("read RM Quantity failed: %s", exc)
        return []
    if not rows:
        return []
    hdr = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        out.append({hdr[i]: (r[i] if i < len(r) else "") for i in range(len(hdr)) if hdr[i]})
    return out


def _read_plan(qty_field="to_plan"):
    """Build the plan from RM Sourcing's OWN Plan tab — no R3SS.

    The Plan tab (RMCP sheet) is RM Sourcing's plan input: one row per FG with
    a Quantity (the planned FG qty). The BOM explodes against BOM Code × Quantity.
    This module is self-contained: it reads only its own Plan tab + cached BOM.

    Demand / green / fg_info are R3SS-only enrichments and are NOT available in
    RM Sourcing data, so they come back empty.  Against Demand RM then shows the
    straight procurement requirement (= To Plan RM); Demand/Green stay blank.
    """
    plan_rows = _read_tab(PLAN_TAB)          # RM Sourcing's own Plan tab
    plan = {}                                # BOM Code (FG) → planned qty
    for r in plan_rows:
        key = str(r.get("BOM Code", "")).strip().upper()
        if not key:
            continue
        plan[key] = plan.get(key, 0.0) + _num(r.get("Quantity"))
    # Not available without R3SS — kept empty so downstream degrades gracefully.
    demand = {}
    green = {}
    fg_info = {}
    return plan, demand, green, plan_rows, fg_info


def compute_rm(qty_field="to_plan"):
    """Explode the cached BOM against the R3SS plan and fill the reference tabs:
    Plan, CP Req, RM Req, RM QTY, Quantity Sheet.

    requirement = plan[parent (P1-stripped → jolly)] × BOM qty ÷ 1000.
    RM children (RM*/R1*) → RM Req / RM QTY; other children (CP + packing) →
    Quantity Sheet. Writes to the RMCP sheet. Never raises.
    """
    cache = _load_bom_cache()
    if not cache:
        return {"ok": False, "error": "No BOM cached — upload the BOM first."}
    try:
        plan, demand, green, plan_rows, fg_info = _read_plan(qty_field)
    except Exception as exc:
        log.exception("RM compute: could not read R3SS plan")
        return {"ok": False, "error": f"Could not read R3SS plan: {exc}"}

    plan_by_code = {p["BOM Code"].strip().upper(): p for p in plan_rows}

    # ── Multi-level CP → RM index (Rule 21) ──────────────────────────────
    # A CP's own recipe lives in the SAME BOM, as a P1-prefixed parent of the
    # CP code (child "CPCAP516SS304" ↔ parent "P1CPCAP516SS304"). Index every
    # parent by its P1-stripped code so any part can be looked up, then resolve
    # a CP down to the RM it consumes — recursively, because a CP can be built
    # from another CP — memoised per code and guarded against cycles.
    bom_index = {}
    for _ln in cache["rows"]:
        _k = _strip_p1(str(_ln["BOM Code"]).strip()).upper()
        bom_index.setdefault(_k, []).append((
            str(_ln["Item Code"]).strip(),
            _num(_ln["BOM Qty (per 1000)"]),
            _ln.get("UOM", ""), _ln.get("Part Description", ""),
        ))

    _cp_rm_unit = {}   # CP code (upper) -> {rm_code: {"req": rm_per_1_cp, "desc", "uom"}}

    def _resolve_cp_to_rm(code, _stack=None, _depth=0):
        """RM consumed per ONE unit of `code`, exploding nested CPs to RM."""
        key = str(code).strip().upper()
        if key in _cp_rm_unit:
            return _cp_rm_unit[key]
        if _stack is None:
            _stack = set()
        out = {}
        if _depth > 12 or key in _stack:
            if key in _stack:
                log.warning("RMCP CP→RM cycle at %s — branch skipped", key)
            return out                      # don't cache a cycle-cut branch
        kids = bom_index.get(key)
        if kids:
            stack = _stack | {key}
            for _child, _q1000, _uom, _desc in kids:
                per = _q1000 / 1000.0        # per 1 unit of this part
                if _is_rm(_child):
                    e = out.setdefault(_child, {"req": 0.0, "desc": _desc, "uom": _uom})
                    e["req"] += per
                else:                        # nested CP → recurse
                    for rc, rv in _resolve_cp_to_rm(_child, stack, _depth + 1).items():
                        e = out.setdefault(rc, {"req": 0.0, "desc": rv["desc"], "uom": rv["uom"]})
                        e["req"] += per * rv["req"]
        _cp_rm_unit[key] = out
        return out

    cp_rows = []
    rm_via_cp_rows = []   # RM Req back-trace lines: FG → RM reached via a CP
    rm_agg = {}       # RM code -> {desc, uom, req(to_plan), demand(total), green}
    # RM reached VIA CPs (Rule 21), same three measures so it folds into RM QTY
    # and Against Demand RM without re-deriving: req(to_plan), demand, green.
    rm_cp_agg = {}    # RM code -> {desc, uom, req, demand, green}
    cp_agg = {}       # CP/packing code -> {desc, uom, req}
    by_bom = {}       # BOM Code (FG) -> its RM needs (product-centric view)
    matched_parents = set()
    for line in cache["rows"]:
        parent = line["BOM Code"]
        child = line["Item Code"]
        pkey = parent.strip().upper()
        # BOM dump parent code == Plan BOM Code (MpsSS FG), both P1-prefixed.
        planq = plan.get(pkey, 0.0)
        demandq = demand.get(pkey, 0.0)
        greenq = green.get(pkey, 0.0)
        if planq <= 0 and greenq <= 0 and demandq <= 0:
            continue                      # parent not planned / stocked / demanded
        matched_parents.add(pkey)
        qty = _num(line["BOM Qty (per 1000)"])
        req = planq * qty / 1000.0            # to_plan explosion  → CP Req / RM QTY
        dem = demandq * qty / 1000.0          # total-demand explosion
        green_req = greenq * qty / 1000.0     # RM green = roll up FG green via BOM
        desc = line.get("Part Description", "")
        uom = line.get("UOM", "")
        is_rm = _is_rm(child)
        if planq > 0:
            cp_rows.append({
                "BOM Code": parent, "Item Code": child,
                "BOM Qty": qty, "Qty in Nos": round(planq),
                "Qty (Base UOM)": round(req, 3), "UOM": uom,
                "Part Description": desc,
            })
            # Product-centric: this FG (BOM Code) → EVERY component it consumes
            # (RM + CP + packing), so the By Product view shows the whole BOM.
            bb = by_bom.get(pkey)
            if bb is None:
                pr = plan_by_code.get(pkey, {})
                fi = fg_info.get(pkey, {})
                bb = {"bom_code": parent, "family": pr.get("Family", ""),
                      "customer": pr.get("Customer", ""),
                      "erp_code": pr.get("ERP Code", ""),
                      "planned": round(planq),
                      # R23 — FG-level netting (from R3SS): demand, stock, green.
                      "fg_demand": round(fi.get("demand", 0.0)),
                      "fg_opening": round(fi.get("opening", 0.0)),
                      "fg_stock": round(fi.get("fg_stock", 0.0)),
                      "fg_green": round(fi.get("green", 0.0)),
                      "rm_demand": 0.0, "cp_demand": 0.0,
                      "rm_via_cp": 0.0,          # RM reached via this FG's CPs
                      "rm_count": 0, "cp_count": 0, "parts": [],
                      "_rm_via_cp_map": {}}
                by_bom[pkey] = bb
            if req > 0:
                bb["parts"].append({"code": child, "desc": desc, "uom": uom,
                                    "req": round(req, 2), "rm": is_rm,
                                    "bq": qty})   # BOM qty per 1000 (for the calc)
                if is_rm:
                    bb["rm_demand"] += req
                    bb["rm_count"] += 1
                else:
                    bb["cp_demand"] += req
                    bb["cp_count"] += 1
                    # Rule 21 — RM this CP consumes (exploded to RM, recursive)
                    for rc, rv in _resolve_cp_to_rm(child).items():
                        add = req * rv["req"]
                        if add <= 0:
                            continue
                        bb["rm_via_cp"] += add
                        vm = bb["_rm_via_cp_map"].setdefault(
                            rc, {"code": rc, "desc": rv["desc"], "uom": rv["uom"],
                                 "req": 0.0})
                        vm["req"] += add
                        # RM Req back-trace: FG → RM, tagged with the CP it came
                        # through, so RM Req foots to RM QTY (direct + via-CP).
                        rm_via_cp_rows.append({
                            "BOM Code": parent, "Item Code": rc,
                            "BOM Qty": "", "Qty in Nos": round(req),
                            "Qty (Base UOM)": round(add, 3), "UOM": rv["uom"],
                            "Part Description": "[via CP %s] %s" % (child, rv["desc"]),
                        })
        if is_rm:
            a = rm_agg.get(child)
            if a is None:
                a = {"desc": desc, "uom": uom, "req": 0.0, "demand": 0.0, "green": 0.0}
                rm_agg[child] = a
            a["req"] += req
            a["demand"] += dem
            a["green"] += green_req
        else:
            a = cp_agg.get(child)
            if a is None:
                a = {"desc": desc, "uom": uom, "req": 0.0}
                cp_agg[child] = a
            a["req"] += req
            # Rule 21 — global roll-up of RM reached via this CP requirement.
            # Explode the CP's to-plan / demand / green requirement to RM using
            # the per-unit recipe (rv["req"] = RM per 1 CP unit).
            for rc, rv in _resolve_cp_to_rm(child).items():
                per = rv["req"]
                if per <= 0:
                    continue
                a2 = rm_cp_agg.get(rc)
                if a2 is None:
                    a2 = {"desc": rv["desc"], "uom": rv["uom"],
                          "req": 0.0, "demand": 0.0, "green": 0.0}
                    rm_cp_agg[rc] = a2
                a2["req"] += req * per
                a2["demand"] += dem * per
                a2["green"] += green_req * per

    # RM Req = the line-level RM explosion (one row per FG → RM), with the same
    # columns as the reference RM Req / CP Req. The aggregated RM total per code
    # lives in RM QTY (reference does the same: RM Req is detail, RM QTY is the
    # SUMIF pivot). Our dump is single-level, so BOM Code is the FG parent.
    rm_req_rows = [r for r in cp_rows if _is_rm(r["Item Code"])]
    # Append the via-CP back-trace lines so RM Req (detail) foots to RM QTY
    # (direct + via-CP). These are tagged "[via CP <code>]" in the description.
    rm_req_rows = rm_req_rows + rm_via_cp_rows

    # ── Rule 21 — Total RM per code = direct (FG→RM) + via-CP (CP→RM) ─────
    # Merge on the UNION of RM codes: each code's direct and via-CP figures are
    # added once (they come from disjoint sources — FG-direct lines vs CP
    # explosions — so summing is aggregation, not double counting). RM codes
    # that only exist via CPs get a row of their own. RM Req (detail) stays the
    # FG-direct line-level explosion; back-tracing of via-CP RM is the By
    # Product view's "RM reached via CPs" list.
    rm_total = {}
    for c in (set(rm_agg) | set(rm_cp_agg)):
        d = rm_agg.get(c, {})
        v = rm_cp_agg.get(c, {})
        rm_total[c] = {
            "desc": d.get("desc") or v.get("desc", ""),
            "uom": d.get("uom") or v.get("uom", ""),
            "req": d.get("req", 0.0) + v.get("req", 0.0),
            "demand": d.get("demand", 0.0) + v.get("demand", 0.0),
            "green": d.get("green", 0.0) + v.get("green", 0.0),
            "via_cp": v.get("req", 0.0),   # transparency: how much came via CPs
        }

    # Preserve the PPC head's manual "Reqd Qty" (reference column E) across
    # recomputes: the automation fills only the computed Qty and the +10% helper,
    # and must never overwrite the manual final quantity (Step 10 of the process).
    prev_reqd = {}
    for row in read_rm_quantity():
        code = (row.get("Item Code") or row.get("RM Code") or "").strip()
        val = (row.get("Reqd Qty (in kgs)") or row.get("Reqd Qty") or "").strip()
        if code and val:
            prev_reqd[code] = val
    rm_qty_rows = [{"Item Code": c, "Description": a["desc"],
                    "Qty": round(a["req"], 2),
                    "Reqd Qty (in kgs)": prev_reqd.get(c, ""),
                    "Qty +10%": round(a["req"] * 1.1, 2)}
                   for c, a in sorted(rm_total.items())]
    # Preserve the two manual inputs on the Quantity Sheet across recomputes:
    #   qty per kg = pieces-per-kg conversion from the CP team (external),
    #   Reqd Qty   = PPC head's manual final.
    prev_qs_reqd, prev_qpk = {}, {}
    for row in read_quantity_sheet():
        code = (row.get("Item Code") or "").strip()
        if not code:
            continue
        if (row.get("Reqd Qty") or "").strip():
            prev_qs_reqd[code] = row["Reqd Qty"].strip()
        if (row.get("qty per kg") or "").strip():
            prev_qpk[code] = row["qty per kg"].strip()
    # Quantity Sheet is a HYBRID pivot: the Apps Script owns the live formulas for
    # Description, UOM, Qty (Base UOM) and the two "Qty in nos" columns (they
    # recalc in-sheet). Django sends only the keys and the two manual inputs
    # (qty per kg, Reqd Qty); the Django values below are a fallback the Apps
    # Script overrides with formulas. Logic (in the Apps Script):
    #   Qty (Base UOM)          = SUMIF(CP Req Item Code, CP Req Qty (Base UOM))
    #   Qty in nos (ERP)        = Qty (Base UOM) × qty per kg
    #   Qty in nos (Correction) = Reqd Qty       × qty per kg
    qty_sheet_rows = [{"Item Code": c, "Description": a["desc"], "UOM": a["uom"],
                       "Qty (Base UOM)": round(a["req"], 2),
                       "qty per kg": prev_qpk.get(c, ""),
                       "Qty in nos (ERP)": "",
                       "Reqd Qty": prev_qs_reqd.get(c, ""),
                       "Qty in nos (Correction)": ""}
                      for c, a in sorted(cp_agg.items())]
    # Against Demand RM (reference): Demand = total-demand explosion, To Plan =
    # to_plan explosion (= RM QTY Demand), Procurement = To Plan − Stock + Green×0.6.
    # Stock is pending (Purchase Dashboard) → blank, so Procurement = To Plan + Green×0.6.
    ad_rm_rows = [{"Item Code": c, "Description": a["desc"],
                   "Demand": round(a["demand"], 2), "To Plan": round(a["req"], 2),
                   "Stock": "", "Green Level": round(a["green"], 2),
                   "Procurement": round(a["req"] + a["green"] * 0.6, 2)}
                  for c, a in sorted(rm_total.items())]

    # Keep chunks small (~2000 rows) so each POST payload stays well under the
    # Apps Script /exec limit — wider tabs (CP Req = 7 cols) 404 at 5000/chunk.
    # CP Req uses a smaller chunk (1000): it is the largest tab and every append
    # to it triggers the live pivot SUMIFs to recalc, so lighter POSTs keep each
    # Apps Script call well under its timeout and avoid the non-JSON/504 retries.
    writes = {
        # Plan tab is RM Sourcing's INPUT now (read, not written) — leave it alone.
        CP_REQ_TAB: _write_tab_resumable(CP_REQ_TAB, CP_REQ_HEADERS, cp_rows, chunk=1000),
        RM_REQ_TAB: _write_tab_resumable(RM_REQ_TAB, RM_REQ_HEADERS, rm_req_rows, chunk=2000),
        RM_QTY_TAB: _write_tab_resumable(RM_QTY_TAB, RM_QTY_HEADERS, rm_qty_rows, chunk=2000),
        QTY_SHEET_TAB: _write_tab_resumable(QTY_SHEET_TAB, QTY_SHEET_HEADERS, qty_sheet_rows, chunk=2000),
        AD_RM_TAB: _write_tab_resumable(AD_RM_TAB, AD_RM_HEADERS, ad_rm_rows, chunk=2000),
    }
    # Cache the product-centric (by BOM Code) RM view for the dashboard.
    by_bom_list = sorted(by_bom.values(), key=lambda b: -b["rm_demand"])
    for b in by_bom_list:
        # Rule 21 — finalise the multi-level roll-up per FG:
        #   rm_demand  = RM used directly in the FG
        #   rm_via_cp  = RM used to make this FG's CPs (exploded to RM)
        #   rm_total   = total RM to procure for this FG
        via_map = b.pop("_rm_via_cp_map", {})
        b["rm_via_cp_parts"] = sorted(
            [{"code": v["code"], "desc": v["desc"], "uom": v["uom"],
              "req": round(v["req"], 2)} for v in via_map.values()],
            key=lambda x: -x["req"])
        b["rm_demand"] = round(b["rm_demand"], 2)
        b["cp_demand"] = round(b["cp_demand"], 2)
        b["rm_via_cp"] = round(b["rm_via_cp"], 2)
        b["rm_total"] = round(b["rm_demand"] + b["rm_via_cp"], 2)
        # RM parts first, then the rest, each by descending requirement.
        b["parts"].sort(key=lambda x: (0 if x["rm"] else 1, -x["req"]))
    try:
        with open(os.path.join(STATE_DIR, "rm_by_bom.json"), "w") as fh:
            json.dump(by_bom_list, fh)
    except Exception:
        log.exception("cache rm_by_bom failed")

    log.info("RM compute: %d planned parents, %d CP lines, %d RM lines, %d RM codes, %d CP/PKG | qty=%s",
             len(matched_parents), len(cp_rows), len(rm_req_rows),
             len(rm_qty_rows), len(qty_sheet_rows), qty_field)
    rm_direct_total = sum(a["req"] for a in rm_agg.values())
    rm_via_cp_total = sum(a["req"] for a in rm_cp_agg.values())
    return {"ok": all(w.get("ok") for w in writes.values()),
            "planned_parents": len(matched_parents),
            "cp_required_rows": len(cp_rows), "rm_req_lines": len(rm_req_rows),
            "rm_items": len(rm_qty_rows),
            "cp_pkg_items": len(qty_sheet_rows), "qty_field": qty_field,
            # Rule 21 multi-level roll-up (direct RM + RM via CPs = total RM)
            "rm_direct_total": round(rm_direct_total, 2),
            "rm_via_cp_total": round(rm_via_cp_total, 2),
            "rm_total": round(rm_direct_total + rm_via_cp_total, 2),
            "rm_via_cp_codes": len(rm_cp_agg),
            "writes": {k: (v.get("ok"), v.get("rows_written")) for k, v in writes.items()}}
