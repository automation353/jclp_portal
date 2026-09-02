"""Google Sheet sync for S&OP uploads — Django → n8n webhook → Google Sheets.

Each of the 5 S&OP data types has its own n8n workflow and webhook URL,
following the same pattern as the Purchase module's separate webhooks.

Large files (31K+ rows) are sent in chunks to avoid n8n payload limits.
First chunk clears the sheet tab; subsequent chunks append.

Environment variables (one per data type):
  JCLP_SOP_DPR_WEBHOOK            — Stock Ledger / DPR
  JCLP_SOP_FORECAST_WEBHOOK       — Forecast vs Sales
  JCLP_SOP_OPENING_STOCK_WEBHOOK  — Opening Stock / Valuation
  JCLP_SOP_GREEN_LEVEL_WEBHOOK    — Green Level Quantities
  JCLP_SOP_SALES_REGISTER_WEBHOOK — Sales Invoice Register
"""

import logging
import os

import requests

log = logging.getLogger(__name__)

# Max rows per webhook POST — keeps payload under n8n/Cloudflare limits
CHUNK_SIZE = 2000

# ── table_key → (env var, Google Sheet tab name) ──────────────────
TABLE_CONFIG = {
    "sop_dpr": {
        "env": "JCLP_SOP_DPR_WEBHOOK",
        "tab": "DPR",
    },
    "sop_forecast": {
        "env": "JCLP_SOP_FORECAST_WEBHOOK",
        "tab": "Forecast",
    },
    "sop_opening_stock": {
        "env": "JCLP_SOP_OPENING_STOCK_WEBHOOK",
        "tab": "Opening Stock",
    },
    "sop_green_level": {
        "env": "JCLP_SOP_GREEN_LEVEL_WEBHOOK",
        "tab": "Green Level",
    },
    "sop_sales_register": {
        "env": "JCLP_SOP_SALES_REGISTER_WEBHOOK",
        "tab": "Sales Register",
    },
    "sop_append1": {
        "env": "JCLP_SOP_APPEND1_WEBHOOK",
        "tab": "Append1",
    },
}

# Backwards-compat: keep TAB_NAMES dict for anything that imports it
TAB_NAMES = {k: v["tab"] for k, v in TABLE_CONFIG.items()}


def _get_webhook(table_key):
    """Get the webhook URL for a specific table_key."""
    cfg = TABLE_CONFIG.get(table_key)
    if not cfg:
        return None
    return os.environ.get(cfg["env"], "").strip()


# ── Apps Script web app URL (generates summary tabs + Append1) ──
APPS_SCRIPT_URL_ENV = "JCLP_SOP_APPS_SCRIPT_URL"


def _post(url, payload, label="sop sheet sync"):
    """POST JSON to an n8n webhook."""
    if not url:
        return {"attempted": False, "reason": "webhook not configured"}

    try:
        resp = requests.post(url, json=payload, timeout=300)
        if 200 <= resp.status_code < 300:
            return {"attempted": True, "ok": True, "http_status": resp.status_code}
        return {
            "attempted": True, "ok": False,
            "http_status": resp.status_code,
            "body_preview": (resp.text or "")[:300],
        }
    except Exception as exc:
        log.exception("%s failed: %s", label, exc)
        return {"attempted": True, "ok": False, "error": str(exc)}


def sync_sop_upload(batch):
    """Push a completed S&OP upload to the Google Sheet via n8n.

    Each table_key has its own webhook. Large datasets are sent in chunks
    of CHUNK_SIZE rows. The first chunk includes action='replace' (clear
    tab + write), subsequent chunks use action='append' (append only).
    """
    table_key = batch.table_key
    url = _get_webhook(table_key)
    cfg = TABLE_CONFIG.get(table_key)

    if not url:
        env_name = cfg["env"] if cfg else "JCLP_SOP_*_WEBHOOK"
        log.info("S&OP sheet sync skipped for %s — %s not set", table_key, env_name)
        return {
            "attempted": False,
            "reason": f"{env_name} not configured",
        }

    tab_name = cfg["tab"]

    rows = list(batch.rows.order_by("sr_no").values_list("data", flat=True))
    if not rows:
        return {"attempted": False, "reason": "no rows to sync"}

    # Derive headers from the first row's keys
    headers = list(rows[0].keys())

    meta = {
        "batch_id": batch.pk,
        "uploaded_at": (
            batch.uploaded_at.isoformat() if batch.uploaded_at else ""
        ),
        "uploader": (
            batch.uploader.get_username() if batch.uploader else "system"
        ),
        "original_filename": batch.original_filename,
        "source": "sop_portal",
    }

    total_rows = len(rows)
    chunks = [rows[i:i + CHUNK_SIZE] for i in range(0, total_rows, CHUNK_SIZE)]

    log.info(
        "S&OP sheet sync: %d rows in %d chunk(s) to %s (table_key=%s, tab=%s)",
        total_rows, len(chunks), url, table_key, tab_name,
    )

    results = []
    for idx, chunk in enumerate(chunks):
        payload = {
            "report_key": table_key,
            "tab_name": tab_name,
            "headers": headers,
            "rows": chunk,
            "row_count": len(chunk),
            "total_rows": total_rows,
            "chunk_index": idx,
            "total_chunks": len(chunks),
            "action": "replace" if idx == 0 else "append",
            "_meta": meta,
        }

        result = _post(url, payload, label=f"sop sync ({tab_name} chunk {idx + 1}/{len(chunks)})")
        results.append(result)

        if not result.get("ok"):
            log.warning(
                "S&OP sheet sync chunk %d/%d failed for %s: %s",
                idx + 1, len(chunks), tab_name, result,
            )
            # Stop sending further chunks if one fails
            break

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "attempted": True,
        "ok": ok_count == len(chunks),
        "chunks_sent": len(results),
        "chunks_ok": ok_count,
        "total_chunks": len(chunks),
        "total_rows": total_rows,
    }


def _resolve_append1_url():
    """Return a working webhook URL for writing the Append1 tab.

    Tries the dedicated sop_append1 webhook first.  If it is not configured,
    falls back to any other S&OP webhook that IS configured — all n8n S&OP
    workflows point to the same Google Sheet and honour ``tab_name`` from the
    payload, so any working webhook can write any tab.
    """
    url = _get_webhook("sop_append1")
    if url:
        return url

    # Fallback: pick the first configured source-file webhook
    for key in ("sop_dpr", "sop_forecast", "sop_opening_stock",
                "sop_green_level", "sop_sales_register"):
        url = _get_webhook(key)
        if url:
            log.info("Append1 sync: using fallback webhook %s", key)
            return url
    return None


def sync_append1(rows, headers, key_order):
    """Push computed Append1 rows to the Google Sheet via Apps Script.

    POSTs ``action: "replaceAppend1"`` with the full header list and row
    dicts directly to the Apps Script web-app endpoint.  Apps Script clears
    the Append1 tab and writes the exact rows Django sends — no
    intermediate n8n workflow, no duplicate-producing server-side compute.
    """
    url = os.environ.get(APPS_SCRIPT_URL_ENV, "").strip()
    if not url:
        log.info("Append1 sheet sync skipped — %s not set", APPS_SCRIPT_URL_ENV)
        return {"attempted": False, "reason": f"{APPS_SCRIPT_URL_ENV} not configured"}

    # Convert dicts to ordered rows matching the header sequence
    sheet_rows = []
    for row in rows:
        sheet_rows.append({h: row.get(k, "") for h, k in zip(headers, key_order)})

    if not sheet_rows:
        return {"attempted": False, "reason": "no rows to sync"}

    payload = {
        "action": "replaceAppend1",
        "headers": list(headers),
        "rows": sheet_rows,
    }

    log.info(
        "Append1 sheet sync: %d rows → Apps Script (%s)",
        len(sheet_rows), url,
    )

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300,
            allow_redirects=True,
        )
        if 200 <= resp.status_code < 300:
            body = resp.text[:500]
            log.info("Append1 sync OK: %s", body)
            return {
                "attempted": True, "ok": True,
                "total_rows": len(sheet_rows),
                "response": body,
            }
        log.warning("Append1 sync HTTP %d: %s", resp.status_code, resp.text[:300])
        return {
            "attempted": True, "ok": False,
            "http_status": resp.status_code,
            "body_preview": resp.text[:300],
        }
    except Exception as exc:
        log.exception("Append1 sync failed: %s", exc)
        return {"attempted": True, "ok": False, "error": str(exc)}


def trigger_compute_append1():
    """Ask Apps Script to recompute the Append1 tab from all sheet sources.

    POST {"action": "computeAppend1"} → Apps Script recalculates the
    full Append1 reconciliation from all 7+ source tabs (DPR, Forecast,
    Opening Stock, Green Level, Sales Register, Trading Items, Actual
    Demand, ASP) and writes the result to the Append1 tab.
    """
    url = os.environ.get(APPS_SCRIPT_URL_ENV, "").strip()
    if not url:
        log.info("computeAppend1 skipped — %s not set", APPS_SCRIPT_URL_ENV)
        return {"attempted": False, "reason": f"{APPS_SCRIPT_URL_ENV} not configured"}

    log.info("S&OP computeAppend1: calling Apps Script at %s", url)
    try:
        resp = requests.post(
            url,
            json={"action": "computeAppend1"},
            headers={"Content-Type": "application/json"},
            timeout=300,
            allow_redirects=True,
        )
        if 200 <= resp.status_code < 300:
            body = resp.text[:500]
            log.info("S&OP computeAppend1 OK: %s", body)
            return {"attempted": True, "ok": True, "response": body}
        log.warning("computeAppend1 HTTP %d: %s", resp.status_code, resp.text[:300])
        return {
            "attempted": True, "ok": False,
            "http_status": resp.status_code,
            "body_preview": resp.text[:300],
        }
    except Exception as exc:
        log.exception("computeAppend1 failed: %s", exc)
        return {"attempted": True, "ok": False, "error": str(exc)}


def pull_append1_snapshot(sheet_id=None, snapshot_path=None):
    """Fetch the Append1 tab from Google Sheet and save as local CSV.

    Used after Apps Script recomputes Append1 — pulls the fresh data
    back so the dashboard serves up-to-date numbers without a manual
    snapshot replacement.

    Returns {"ok": True, "rows": N} on success.
    """
    import ssl
    import urllib.request

    sheet_id = sheet_id or os.environ.get(
        "JCLP_SOP_SHEET_ID",
        "1cORrogedEjG1ej5pursnTsdAGtsUwvxL7a06zosqYe8",
    )
    if not snapshot_path:
        snapshot_path = os.path.join(
            os.path.dirname(__file__), "append1_snapshot.csv"
        )

    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&sheet=Append1"
    )
    log.info("Pulling Append1 from Google Sheet %s", sheet_id)

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (JCPL-portal)"}
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = resp.read()

        text = data.decode("utf-8", errors="replace")
        lines = text.strip().split("\n")
        if len(lines) < 50:
            msg = f"Too few rows ({len(lines)}), skipping snapshot update"
            log.warning("pull_append1_snapshot: %s", msg)
            return {"ok": False, "reason": msg}

        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(text)

        log.info(
            "Append1 snapshot updated: %d data rows → %s",
            len(lines) - 1, snapshot_path,
        )
        return {"ok": True, "rows": len(lines) - 1, "path": snapshot_path}

    except Exception as exc:
        log.exception("pull_append1_snapshot failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def trigger_full_refresh():
    """Call the Apps Script web app to regenerate summary tabs only.

    POST {"action": "summaryOnly"} → runs generateSummaryTabs() inside
    Apps Script.  Append1 is NOT recomputed here — use
    trigger_compute_append1() for that.
    """
    url = os.environ.get(APPS_SCRIPT_URL_ENV, "").strip()
    if not url:
        log.info("S&OP fullRefresh skipped — %s not set", APPS_SCRIPT_URL_ENV)
        return {"attempted": False, "reason": f"{APPS_SCRIPT_URL_ENV} not configured"}

    log.info("S&OP summaryOnly: calling Apps Script at %s", url)
    try:
        resp = requests.post(
            url,
            json={"action": "summaryOnly"},
            headers={"Content-Type": "application/json"},
            timeout=300,
            allow_redirects=True,
        )
        if 200 <= resp.status_code < 300:
            body = resp.text[:500]
            log.info("S&OP summaryOnly OK: %s", body)
            return {"attempted": True, "ok": True, "response": body}
        log.warning("S&OP summaryOnly HTTP %d: %s", resp.status_code, resp.text[:300])
        return {
            "attempted": True, "ok": False,
            "http_status": resp.status_code,
            "body_preview": resp.text[:300],
        }
    except Exception as exc:
        log.exception("S&OP summaryOnly failed: %s", exc)
        return {"attempted": True, "ok": False, "error": str(exc)}
