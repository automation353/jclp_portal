"""Read the computed R3SS tab straight from the Google Sheet.

The R3SS tab is built inside the Google Sheet by Apps Script (from the 6
source tabs). The dashboard reads it directly from here — nothing is stored
in Django. This is a READ-ONLY export (gviz CSV), never a write.
"""

import csv
import io
import logging
import os
import re

import requests

log = logging.getLogger(__name__)


def _sheet_id():
    return os.environ.get("JCLP_PPC_R3SS_SHEET_ID", "").strip()


def _apps_script_url():
    return os.environ.get("JCLP_PPC_R3SS_APPS_SCRIPT_URL", "").strip()


# Merged title-cell prefixes that Google prepends to the first column of a
# banded header. Stripped before matching.
_TITLE_PREFIXES = [
    "production execution plan w/o scrap factor",
    "production execution plan with scrap factor",
    "production execution plan",
    "daily production plan",
    "weekly plan",
    "demand qty",
]

# Normalised sheet header -> dashboard field key.
_EXACT_MAP = {
    "family": "family",
    "customer": "category",
    "cust part no": "description",
    "jollysize": "jolly_size",
    "jolly size": "jolly_size",
    "no of teeth": "teeth",
    "no of strokes": "strokes",
    "erp code": "item_code",
    "jolly code": "jolly_code",
    "mto/ mts": "mto_mts",
    "mto/mts": "mto_mts",
    "green level": "green_level",
    "opening balance": "opening_balance",
    "fg": "fg_stock",
    "pack": "pack",
    "disp": "disp",
    "to plan": "to_plan",
    "total plan (hw + mit)": "total_plan",
    "total plan": "total_plan",
    "difference": "difference",
    "initial": "initial_demand",
    "additional": "additional_demand",
    "total": "total_demand",
    "week1": "w1",
    "week2": "w2",
    "week3": "w3",
    "week4": "w4",
    "week5": "w5",
    "cutting": "cutting",
    "colour": "colour",
    "color": "colour",
    "section": "section",
    "product group": "product_group",
    "stamping": "stamping",
    "atmc group": "atmc_group",
    "atmc grp": "atmc_group",
    "plant": "plant",
    "strip weight": "strip_weight",
    "asp": "asp",
    "ebq": "ebq",
    "red level": "red_level",
    "blue level": "blue_level",
    # The sheet names the colour-band thresholds RL / GL / BL, not
    # "Red/Green/Blue Level" — map them so the dashboard shows the values.
    "rl": "red_level",
    "bl": "blue_level",
}

_DATE_RE = re.compile(r"(\d{1,2})\s*[-/]\s*(\d{1,2})")


def _jolly_key(code):
    """Normalise a jolly code for MTO/MTS matching: trim, collapse internal
    whitespace, uppercase — so 'TS M05  B06' and 'TS M05 B06' link to the same
    part (guards the linkage against stray double-spaces in either source)."""
    return re.sub(r"\s+", " ", str(code or "").strip()).upper()


def _norm(header):
    """Lowercase, collapse whitespace/newlines, strip merged title prefixes."""
    h = (header or "").replace("\n", " ").replace("\r", " ")
    h = re.sub(r"\s+", " ", h).strip().lower()
    for pref in _TITLE_PREFIXES:
        if h.startswith(pref):
            h = h[len(pref):].strip()
            break
    return h


def _resolve_year(months, now_month, now_year):
    """Pick the plan year for each distinct month seen in the day headers."""
    year_for = {}
    for m in months:
        # A month far ahead of the current one belongs to the previous year
        # (e.g. December headers seen in January).
        if m > now_month + 2:
            year_for[m] = now_year - 1
        else:
            year_for[m] = now_year
    return year_for


def _load_mto_mts_live(timeout=60):
    """Build {jolly Item Code (upper) -> 'MTS'/'MTO'} from the MTO_MTS tab.

    The MTO_MTS tab is computed in Django (see mto_mts_compute) and keyed by
    MTS Key = Item Group|Item Code|Party, so one jolly code can appear under
    several customer segments. We collapse them to one value per part code with
    an MTS-if-any-segment-is-MTS rule (an item stocked for any customer is MTS).

    Returns {} if the tab is missing/empty — callers then leave the existing
    value untouched rather than blanking every row to NA.
    """
    sid = _sheet_id()
    if not sid:
        return {}
    url = (
        f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
        f"?tqx=out:csv&headers=1&sheet={requests.utils.quote('MTO_MTS')}"
    )
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("Could not read MTO_MTS tab for live status: %s", exc)
        return {}

    rows = list(csv.reader(io.StringIO(resp.text)))
    if not rows:
        return {}
    norm = [h.strip().lower() for h in rows[0]]
    try:
        ic = norm.index("item code")
        fs = norm.index("final status")
    except ValueError:
        log.warning("MTO_MTS tab missing Item Code / Final Status columns")
        return {}

    live = {}
    for r in rows[1:]:
        if ic >= len(r):
            continue
        code = _jolly_key(r[ic])
        if not code:
            continue
        status = (r[fs] or "").strip().upper() if fs < len(r) else ""
        if status not in ("MTS", "MTO"):
            continue
        # MTS wins over MTO for the same part code.
        if live.get(code) == "MTS":
            continue
        live[code] = status
    return live


def read_r3ss_rows(tab_name="R3SS", timeout=30):
    """Fetch the R3SS tab as a CSV export and map it to dashboard rows.

    Returns {"rows": [{"sr_no", "data"}], "row_count", "plan_month"}.
    Raises on network/parse failure.
    """
    from django.utils import timezone

    sid = _sheet_id()
    if not sid:
        raise RuntimeError("JCLP_PPC_R3SS_SHEET_ID not configured")

    # Use the /export CSV endpoint, NOT gviz: gviz returns a broken/truncated
    # response for this tab (a handful of rows, no header), while /export
    # returns the full sheet reliably.
    url = (
        f"https://docs.google.com/spreadsheets/d/{sid}/export"
        f"?format=csv&sheet={requests.utils.quote(tab_name)}"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    reader = csv.reader(io.StringIO(resp.text))
    all_rows = list(reader)
    if not all_rows:
        return {"rows": [], "row_count": 0, "plan_month": None}

    # Find the real header row: the tab has blank + banner rows above it, so
    # pick the row with the most known header labels (scan the top of the tab).
    hdr_idx, best = 0, 0
    for i, r in enumerate(all_rows[:12]):
        n = sum(1 for c in r if _norm(c) in _EXACT_MAP)
        if n > best:
            best, hdr_idx = n, i
    headers = all_rows[hdr_idx]

    # Classify each column: a dashboard field, a day column, or ignored.
    col_field = {}   # col_idx -> field key
    col_day = {}     # col_idx -> (month, day)
    day_months = []

    for idx, raw in enumerate(headers):
        norm = _norm(raw)
        if norm in _EXACT_MAP:
            col_field[idx] = _EXACT_MAP[norm]
            continue
        m = _DATE_RE.search(raw or "")
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                col_day[idx] = (month, day)
                day_months.append(month)

    now = timezone.now()
    plan_month = None
    year_for = {}
    if day_months:
        dominant = max(set(day_months), key=day_months.count)
        year_for = _resolve_year(set(day_months), now.month, now.year)
        plan_month = f"{year_for[dominant]:04d}-{dominant:02d}"

    out_rows = []
    sr = 0
    for r in all_rows[hdr_idx + 1:]:
        item_code = ""
        for idx, key in col_field.items():
            if key == "item_code" and idx < len(r):
                item_code = (r[idx] or "").strip()
                break
        if not item_code:
            continue

        data = {}
        for idx, key in col_field.items():
            val = r[idx].strip() if idx < len(r) and r[idx] is not None else ""
            data[key] = val

        days = {}
        for idx, (month, day) in col_day.items():
            val = r[idx].strip() if idx < len(r) and r[idx] is not None else ""
            if val in ("", "0"):
                continue
            yr = year_for.get(month, now.year)
            iso = f"{yr:04d}-{month:02d}-{day:02d}"
            days[iso] = val

        data["days"] = days
        if plan_month:
            data["_plan_month"] = plan_month

        sr += 1
        out_rows.append({"sr_no": sr, "data": data})

    # Overlay the computed recent MTO/MTS status (from the MTO_MTS tab), matched
    # by jolly code. Items with no recent sales show NA. If the MTO_MTS tab isn't
    # present yet, leave whatever the R3SS tab already had.
    live = _load_mto_mts_live()
    if live:
        for row in out_rows:
            d = row["data"]
            jolly = _jolly_key(d.get("jolly_code"))
            d["mto_mts"] = live.get(jolly, "NA")

    return {"rows": out_rows, "row_count": len(out_rows), "plan_month": plan_month}


def trigger_recompute(timeout=540, force=False):
    """Ask the Apps Script to rebuild the R3SS tab from the 6 source tabs.

    force=True clears the whole R3SS tab and rewrites it (drops stale rows);
    otherwise the Apps Script upserts by ERP code.
    Returns {"ok": bool, ...}. Never raises.
    """
    import time as _time

    url = _apps_script_url()
    if not url:
        return {"ok": False, "error": "JCLP_PPC_R3SS_APPS_SCRIPT_URL not set"}

    last = {"ok": False, "error": "no attempt"}
    for attempt in range(1, 3):  # try twice — the first may hit a transient
        try:
            resp = requests.post(
                url, json={"action": "computeR3SS", "force": bool(force)},
                timeout=timeout, allow_redirects=True,
            )
            http_ok = 200 <= resp.status_code < 300
            # Apps Script always returns HTTP 200 — the real status is in the
            # JSON body (ok / skipped / busy / reason).
            body = {}
            try:
                body = resp.json()
            except Exception:
                body = {}
            last = {
                "ok": http_ok and bool(body.get("ok", http_ok)),
                "skipped": bool(body.get("skipped")),
                "busy": bool(body.get("busy")),
                "reason": body.get("reason", ""),
                "empty_tabs": body.get("empty_tabs", []),
                "http_status": resp.status_code,
                "body_preview": (resp.text or "")[:300],
            }
        except Exception as exc:
            log.exception("R3SS Apps Script recompute failed (attempt %d)", attempt)
            last = {"ok": False, "error": str(exc)}

        # Success or a definitive "waiting for tabs" skip — don't retry.
        if last.get("ok") or last.get("skipped"):
            return last
        if attempt < 2:
            _time.sleep(5)  # transient/concurrent collision — back off and retry
    return last
