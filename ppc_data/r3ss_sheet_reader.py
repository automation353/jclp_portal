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
    "plant": "plant",
    "strip weight": "strip_weight",
    "asp": "asp",
    "ebq": "ebq",
    "red level": "red_level",
    "blue level": "blue_level",
}

_DATE_RE = re.compile(r"(\d{1,2})\s*[-/]\s*(\d{1,2})")


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


def read_r3ss_rows(tab_name="R3SS", timeout=30):
    """Fetch the R3SS tab as a CSV export and map it to dashboard rows.

    Returns {"rows": [{"sr_no", "data"}], "row_count", "plan_month"}.
    Raises on network/parse failure.
    """
    from django.utils import timezone

    sid = _sheet_id()
    if not sid:
        raise RuntimeError("JCLP_PPC_R3SS_SHEET_ID not configured")

    url = (
        f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
        f"?tqx=out:csv&sheet={requests.utils.quote(tab_name)}"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    reader = csv.reader(io.StringIO(resp.text))
    all_rows = list(reader)
    if not all_rows:
        return {"rows": [], "row_count": 0, "plan_month": None}

    headers = all_rows[0]

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
    for r in all_rows[1:]:
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

    return {"rows": out_rows, "row_count": len(out_rows), "plan_month": plan_month}


def trigger_recompute(timeout=540, force=False):
    """Ask the Apps Script to rebuild the R3SS tab from the 6 source tabs.

    force=True clears the whole R3SS tab and rewrites it (drops stale rows);
    otherwise the Apps Script upserts by ERP code.
    Returns {"ok": bool, ...}. Never raises.
    """
    url = _apps_script_url()
    if not url:
        return {"ok": False, "error": "JCLP_PPC_R3SS_APPS_SCRIPT_URL not set"}
    try:
        resp = requests.post(
            url, json={"action": "computeR3SS", "force": bool(force)},
            timeout=timeout, allow_redirects=True,
        )
        http_ok = 200 <= resp.status_code < 300
        # Apps Script always returns HTTP 200 — the real status is in the JSON
        # body (ok / skipped / reason). Parse it so a "waiting for tabs" skip
        # is not mistaken for success.
        body = {}
        try:
            body = resp.json()
        except Exception:
            body = {}
        ok = http_ok and bool(body.get("ok", http_ok))
        return {
            "ok": ok,
            "skipped": bool(body.get("skipped")),
            "reason": body.get("reason", ""),
            "empty_tabs": body.get("empty_tabs", []),
            "http_status": resp.status_code,
            "body_preview": (resp.text or "")[:300],
        }
    except Exception as exc:
        log.exception("R3SS Apps Script recompute failed")
        return {"ok": False, "error": str(exc)}
