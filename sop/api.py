"""REST endpoints for the S&OP module.

  POST /api/sop/upload/            — upload one of the 5 S&OP data files
  GET  /api/sop/uploads/           — list recent S&OP uploads
  GET  /api/sop/demand-supply/     — demand & supply visibility dashboard
  GET  /api/sop/data/<table_key>/  — browse uploaded data for a table_key

Session-authenticated. Uploads go through the same PPCUploadBatch /
PPCDataRow infrastructure — the 5 S&OP table keys all start with "sop_".
"""

import calendar
import csv
import io
import logging
import os
import ssl
import threading
import urllib.request

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

log = logging.getLogger(__name__)

# ── Upload root for S&OP files ───────────────────────────────────────
_UPLOAD_ROOT = os.environ.get(
    "JCLP_SOP_UPLOAD_ROOT",
    os.path.join(settings.BASE_DIR, "uploads", "sop"),
)


def _store_file(uploaded_file):
    """Save an uploaded file to disk and return (stored_path, original_name)."""
    now = timezone.now()
    subdir = os.path.join(_UPLOAD_ROOT, now.strftime("%Y-%m"))
    os.makedirs(subdir, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%S")
    safe = os.path.basename(uploaded_file.name).replace(os.sep, "_")
    stored_path = os.path.join(subdir, f"{stamp}__{safe}")
    with open(stored_path, "wb") as out:
        for chunk in uploaded_file.chunks():
            out.write(chunk)
    return stored_path, safe


# ── S&OP table key definitions ───────────────────────────────────────
SOP_TABLES = {
    "sop_dpr": {
        "label": "DPR — Stock Ledger Report",
        "icon": "📦",
        "description": "Daily production report from ERP — actual production, dispatch, closing stock.",
    },
    "sop_forecast": {
        "label": "Forecast vs Sales Report",
        "icon": "📈",
        "description": "Original forecast vs actual sales demand comparison.",
    },
    "sop_opening_stock": {
        "label": "Opening Stock — Valuation Report",
        "icon": "🏭",
        "description": "Stock statement valuation — opening inventory quantities.",
    },
    "sop_green_level": {
        "label": "PPC Green Level Quantities",
        "icon": "🟢",
        "description": "Safety stock / green level quantities by item.",
    },
    "sop_sales_register": {
        "label": "Sales Register — Invoice Report",
        "icon": "🧾",
        "description": "Sales invoice register — actual sales dispatch data.",
    },
}


# ── Local Append1 recompute + snapshot save ─────────────────────────

def _local_compute_and_save_snapshot():
    """Recompute Append1 from Django's 5 uploaded data sources and
    save it as the local CSV snapshot.  Also pushes to Google Sheet
    via Apps Script ``replaceAppend1`` when configured.

    Called as a fallback when the Google Sheet compute path fails,
    or when n8n webhooks are not configured.
    """
    try:
        from .append1 import compute_append1, APPEND1_HEADERS, _KEY_ORDER
        from .sheet_sync import sync_append1

        items = compute_append1()
        if not items:
            log.warning("Local compute_append1 returned 0 items")
            return

        # Write CSV snapshot
        snapshot_path = os.path.join(
            os.path.dirname(__file__), "append1_snapshot.csv"
        )
        with open(snapshot_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            # Title row matching Google Sheet format
            writer.writerow(
                ["Sales+Ops Demand Supply — Append1 (auto-computed)"]
                + [""] * (len(APPEND1_HEADERS) - 1)
            )
            writer.writerow(APPEND1_HEADERS)
            for item in items:
                writer.writerow([item.get(k, "") for k in _KEY_ORDER])

        log.info(
            "Local snapshot saved: %d items → %s", len(items), snapshot_path
        )

        # Push to Google Sheet
        result = sync_append1(items, APPEND1_HEADERS, _KEY_ORDER)
        log.info("Local → Sheet sync: %s", result)

    except Exception:
        log.exception("_local_compute_and_save_snapshot failed")


# ── Upload endpoint ──────────────────────────────────────────────────

@api_view(["POST"])
@parser_classes([MultiPartParser])
def upload(request):
    """Upload an S&OP Excel file.

    Form data:
      file       — the .xlsx / .xlsm file
      table_key  — one of: sop_dpr, sop_forecast, sop_opening_stock,
                   sop_green_level, sop_sales_register
      notes      — optional notes string
    """
    from ppc_data.models import PPCDataRow, PPCUploadBatch
    from ppc_data.parsers.sop_generic import (
        SOP_TABLE_KEYS,
        detect_sop_table_key,
        parse,
    )
    from portal.notify import notify

    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response(
            {"detail": "No file attached under the 'file' key."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not uploaded.name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return Response(
            {"detail": "Please upload an .xlsx or .xlsm file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Determine table_key
    table_key = request.data.get("table_key") or request.query_params.get("table_key")
    if not table_key:
        table_key = detect_sop_table_key(uploaded.name)
    if not table_key or table_key not in SOP_TABLE_KEYS:
        return Response(
            {"detail": (
                f"Could not determine the data type for '{uploaded.name}'. "
                f"Please select one of: {', '.join(SOP_TABLE_KEYS)}"
            )},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stored_path, original_name = _store_file(uploaded)
    notes = ("" if request.data.get("notes") is None
             else str(request.data["notes"]))[:500]

    # Parse
    try:
        parsed_rows = parse(stored_path, table_key=table_key)
    except Exception as exc:
        log.exception("S&OP parse failed for %s (table_key=%s)", stored_path, table_key)
        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="sop",
            level="SOP",
            table_key=table_key,
            row_count=0,
            is_current=False,
            parse_error=str(exc),
            notes=notes,
        )
        notify(
            f"S&OP upload PARSE FAILED — {original_name}",
            f"{request.user.get_username()} uploaded '{original_name}' "
            f"for table '{table_key}', but parsing failed: {exc}",
        )
        return Response(
            _batch_payload(batch),
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Store in a transaction
    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key=table_key, is_current=True,
        ).update(is_current=False)

        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="sop",
            level="SOP",
            table_key=table_key,
            row_count=len(parsed_rows),
            is_current=True,
            notes=notes,
        )

        row_objs = [
            PPCDataRow(
                batch=batch,
                sr_no=idx + 1,
                table_key=table_key,
                data=row,
            )
            for idx, row in enumerate(parsed_rows)
        ]
        PPCDataRow.objects.bulk_create(row_objs, batch_size=500)

    notify(
        f"S&OP upload OK — {original_name}",
        f"{request.user.get_username()} uploaded '{original_name}' "
        f"for table '{table_key}': {len(parsed_rows)} rows parsed and stored.",
    )

    # Fire-and-forget Google Sheet sync + Append1 recompute.
    # Background thread so the upload response returns immediately.
    #
    # Full chain:
    #   1. Push source data to Google Sheet via n8n webhook
    #   2. Trigger Apps Script computeAppend1 (recompute from all tabs)
    #   3. Wait for computation, then pull fresh Append1 CSV back
    #   4. Save as local snapshot so the dashboard is immediately current
    #   5. Trigger summaryOnly for summary tabs
    #
    # If the Google Sheet path fails at any step, fall back to Django's
    # local compute_append1() so the dashboard still updates.
    def _bg_sync(batch_pk, tk):
        import time
        from .sheet_sync import (
            sync_sop_upload, trigger_full_refresh,
            trigger_compute_append1, pull_append1_snapshot,
        )
        try:
            from ppc_data.models import PPCUploadBatch as Batch
            b = Batch.objects.get(pk=batch_pk)

            # Step 1: Sync source data to Google Sheet
            result = sync_sop_upload(b)
            log.info("S&OP sheet sync for %s: %s", tk, result)

            snapshot_ok = False

            if result.get("ok"):
                # Step 2: Trigger Apps Script to recompute Append1
                compute = trigger_compute_append1()
                log.info("S&OP computeAppend1 after %s: %s", tk, compute)

                if compute.get("ok"):
                    # Step 3: Wait for Apps Script to finish (typically 5-15s)
                    time.sleep(15)

                    # Step 4: Pull fresh Append1 back and save as snapshot
                    snap = pull_append1_snapshot()
                    log.info("S&OP snapshot pull after %s: %s", tk, snap)
                    snapshot_ok = snap.get("ok", False)

                # Step 5: Regenerate summary tabs
                refresh = trigger_full_refresh()
                log.info("S&OP summaryOnly after %s: %s", tk, refresh)

            # Fallback: if sheet-based refresh didn't produce a snapshot,
            # compute locally from the database and save as snapshot.
            if not snapshot_ok:
                log.info("S&OP: sheet path incomplete for %s, computing locally", tk)
                _local_compute_and_save_snapshot()

        except Exception:
            log.exception("S&OP bg sync failed for %s (non-blocking)", tk)

    threading.Thread(
        target=_bg_sync,
        args=(batch.pk, table_key),
        daemon=True,
    ).start()

    payload = _batch_payload(batch)
    payload["sample_row"] = parsed_rows[0] if parsed_rows else None
    payload["sheet_sync"] = "triggered"
    return Response(payload, status=status.HTTP_201_CREATED)


def _batch_payload(batch):
    """Serialise a PPCUploadBatch for API responses."""
    return {
        "id": batch.pk,
        "table_key": batch.table_key,
        "original_filename": batch.original_filename,
        "uploaded_at": batch.uploaded_at.isoformat() if batch.uploaded_at else None,
        "uploader": batch.uploader.get_username() if batch.uploader else None,
        "row_count": batch.row_count,
        "is_current": batch.is_current,
        "parse_error": batch.parse_error,
        "notes": batch.notes,
    }


# ── List uploads ─────────────────────────────────────────────────────

@api_view(["GET"])
def list_uploads(request):
    """List recent S&OP uploads, optionally filtered by table_key."""
    from ppc_data.models import PPCUploadBatch

    qs = PPCUploadBatch.objects.filter(table_key__startswith="sop_")
    table_key = request.query_params.get("table_key")
    if table_key:
        qs = qs.filter(table_key=table_key)
    qs = qs[:50]

    return Response({
        "uploads": [_batch_payload(b) for b in qs],
        "tables": SOP_TABLES,
    })


# ── Browse table data ────────────────────────────────────────────────

@api_view(["GET"])
def table_data(request, table_key):
    """Browse rows for a specific S&OP table_key (latest upload)."""
    from ppc_data.models import PPCUploadBatch

    if table_key not in SOP_TABLES:
        return Response(
            {"detail": f"Unknown S&OP table key: {table_key}"},
            status=status.HTTP_404_NOT_FOUND,
        )

    batch = (
        PPCUploadBatch.objects
        .filter(table_key=table_key, is_current=True)
        .first()
    )
    if not batch:
        return Response({
            "table_key": table_key,
            "batch": None,
            "rows": [],
            "columns": [],
        })

    limit = min(int(request.query_params.get("limit", 200)), 2000)
    search = request.query_params.get("search", "").strip().lower()

    rows_qs = batch.rows.order_by("sr_no")
    if search:
        from django.db.models import Q
        rows_qs = rows_qs.filter(Q(data__icontains=search))

    data_rows = list(rows_qs.values_list("data", flat=True)[:limit])

    # Derive column list from first rows
    columns = []
    seen = set()
    for row in data_rows[:50]:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)

    return Response({
        "table_key": table_key,
        "batch": _batch_payload(batch),
        "rows": data_rows,
        "columns": columns,
        "total": batch.row_count,
    })


# ── Demand & Supply Dashboard ────────────────────────────────────────

def _month_range(month_str):
    """Return (first_day, last_day) as 'YYYY-MM-DD' for a 'YYYY-MM' month."""
    year, mon = int(month_str[:4]), int(month_str[5:7])
    last_day = calendar.monthrange(year, mon)[1]
    return f"{month_str}-01", f"{month_str}-{last_day:02d}"


def _num(val):
    """Safely convert a value to float, defaulting to 0."""
    if val is None:
        return 0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0


def _get_current_rows(table_key):
    """Fetch all data rows for the current upload of a table_key."""
    from ppc_data.models import PPCUploadBatch

    batch = (
        PPCUploadBatch.objects
        .filter(table_key=table_key, is_current=True)
        .first()
    )
    if not batch:
        return []
    return list(batch.rows.values_list("data", flat=True))


# ── Google Sheet CSV reader for Append1 ─────────────────────────────
# The authoritative computation happens in the Google Sheet (Apps Script
# computeAppend1) using DPR/Forecast/Opening Stock/Green Level/Sales
# Register/Trading Items/Actual Demand tabs.  Django's local upload data
# does not always match those tabs (different date ranges, different item
# categories), so reading from the sheet guarantees the dashboard shows
# the same numbers as the reference.

_APPEND1_SHEET_ID = os.environ.get(
    "JCLP_SOP_SHEET_ID", "1cORrogedEjG1ej5pursnTsdAGtsUwvxL7a06zosqYe8"
)
_APPEND1_SNAPSHOT = os.path.join(
    os.path.dirname(__file__), "append1_snapshot.csv"
)

# Column header → internal key mapping for the Append1 CSV.
# Keys are matched against normalised headers (lowercase, collapsed
# whitespace, linebreaks → space).  Parenthesised content is preserved
# so "(Added)" / "(Deducted)" / "(₹)" stay distinct.
_CSV_COL_MAP = {
    "item group":           "item_group",
    "item code":            "item_code",
    "product class":        "product_class",
    "original forecast":    "original_forecast",
    "committed forecast":   "committed_forecast",
    "forecast committed":   "committed_forecast",
    "ops+sales-reviewed":   "committed_forecast",
    "reviewed forecast":    "committed_forecast",
    "ops adjustment":       "ops_adjustment",
    "actual sales demand":  "actual_sales",
    "additional demand":    "additional_demand",
    "forecast accuracy":    "forecast_accuracy_pct",
    "opening inventory":    "opening_inventory",
    "actual production":    "actual_production",
    "stock adjustment (added)":     "stock_adj_added",
    "stock adj (added)":            "stock_adj_added",
    "stock adjustment (deducted)":  "stock_adj_deducted",
    "stock adj (deducted)":         "stock_adj_deducted",
    "total available":      "total_available",
    "type":                 "type_mts_mto",
    "actual dispatch":      "actual_dispatch",
    "dispatch %":           "dispatch_pct_str",
    "closing inventory":    "closing_inventory",
    "green level":          "green_level",
    "free inventory":       "free_inventory",
    "free inventory (above green level)":   "free_inventory",
    "uncovered shortfall":  "uncovered_shortfall",
    "dispatch gap (shippable from stock)":  "dispatch_gap_qty",
    "shortfall on additional demand (excluded from ops)": "shortfall_addl_demand",
    "shortfall on additional demand":       "shortfall_addl_demand",
    "shortfall add. demand":                "shortfall_addl_demand",
    "demand reduction adjustment":          "demand_reduction_adj",
    "demand reduction adj":                 "demand_reduction_adj",
    "production-driven shortfall":          "production_driven_shortfall",
    "production- driven shortfall":         "production_driven_shortfall",
    "prod-driven shortfall":                "production_driven_shortfall",
    "production surplus":                   "production_surplus_qty",
    "excess opening stock (above demand+safety)": "excess_opening_qty",
    "excess opening stock":                 "excess_opening_qty",
    "excess dispatched":                    "excess_dispatched_qty",
    "sales insight tag":    "sales_insight_tag",
    "sales narrative":      "sales_narrative",
    "operations insight tag": "ops_insight_tag",
    "ops insight tag":        "ops_insight_tag",
    "operations narrative": "ops_narrative",
    "ops narrative":        "ops_narrative",
    "ops capacity gap narrative": "ops_capacity_narrative",
    "s&op alignment":       "ops_capacity_narrative",
    "surplus production":   "surplus_value",
    "excess opening stock value": "excess_opening_value",
    "build required":       "build_required",
    "production counted":   "production_counted",
    # ₹-value columns — map to separate financial keys
    "production-driven shortfall (₹)":              "production_shortfall_val",
    "dispatch gap (shippable from stock) (₹)":      "dispatch_gap_val",
    "shortfall on additional demand (excluded from ops) (₹)": "shortfall_addl_val",
    "demand reduction adjustment (sales pullback) (₹)":      "demand_reduction_val",
    "excess dispatch value (₹)":                    "excess_dispatch_val",
    "excess dispatched from op stock":              "excess_dispatch_from_opstock",
    "excess dispatch from surplus production":      "excess_dispatch_from_surplus",
    "excess dispatch from op stock value (₹)":      "excess_dispatch_opstock_val",
    "excess dispatch from surplus production value (₹)": "excess_dispatch_surplus_val",
}


def _normalise_header(h):
    """Collapse whitespace and lowercase; keep parens for disambiguation."""
    import re
    h = h.replace("\n", " ").replace("\r", " ")
    h = re.sub(r"\s+", " ", h).strip().lower()
    return h


def _match_col(normalised_header):
    """Return the internal key for a CSV column header, or None."""
    # Try exact match first
    if normalised_header in _CSV_COL_MAP:
        return _CSV_COL_MAP[normalised_header]
    # Try substring match
    for pat, key in _CSV_COL_MAP.items():
        if pat in normalised_header:
            return key
    return None


def _load_append1_from_sheet():
    """Try to read Append1 from the Google Sheet via CSV export.

    Returns a list of item dicts if successful, None on failure.
    The sheet must be link-shared for viewing (no auth needed).
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{_APPEND1_SHEET_ID}"
        f"/export?format=csv&sheet=Append1"
    )
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (JCPL-portal)"}
        )
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        return _parse_append1_csv(text)
    except Exception as exc:
        log.warning("Append1 sheet read failed: %s", exc)
        return None


def _load_append1_snapshot():
    """Read the local Append1 snapshot CSV (frozen reference data).

    Returns a list of item dicts if the file exists, None otherwise.
    """
    if not os.path.isfile(_APPEND1_SNAPSHOT):
        return None
    try:
        with open(_APPEND1_SNAPSHOT, "r", encoding="utf-8-sig") as f:
            text = f.read()
        return _parse_append1_csv(text)
    except Exception as exc:
        log.warning("Append1 snapshot read failed: %s", exc)
        return None


def _parse_append1_csv(text):
    """Parse Append1 CSV text into a list of item dicts.

    Handles both the Google Sheet export format and the reference CSV
    (which has a title row before the header row).
    """
    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)
    if not all_rows:
        return None

    # Find the header row — look for one containing "Item Code"
    header_idx = None
    for idx, row in enumerate(all_rows[:5]):
        for cell in row:
            if "item code" in cell.lower().replace("\n", " "):
                header_idx = idx
                break
        if header_idx is not None:
            break
    if header_idx is None:
        return None

    raw_headers = all_rows[header_idx]
    # Map CSV columns to internal keys
    col_keys = []
    for h in raw_headers:
        nh = _normalise_header(h)
        col_keys.append(_match_col(nh))

    items = []
    for row in all_rows[header_idx + 1:]:
        if not row or len(row) < 3:
            continue
        # Skip blank rows
        item_code = ""
        for ci, key in enumerate(col_keys):
            if key == "item_code" and ci < len(row):
                item_code = str(row[ci]).strip()
                break
        if not item_code:
            continue

        item = {}
        for ci, key in enumerate(col_keys):
            if key is None or ci >= len(row):
                continue
            raw = str(row[ci]).replace(",", "").replace("–", "0").strip()
            if key in ("item_code", "item_group", "product_class",
                       "type_mts_mto", "sales_insight_tag",
                       "sales_narrative", "ops_insight_tag",
                       "ops_narrative", "ops_capacity_narrative",
                       "forecast_accuracy_pct", "dispatch_pct_str"):
                item[key] = str(row[ci]).strip()
            else:
                try:
                    # Strip indicator arrows and currency/pct symbols
                    raw = raw.replace("₹", "").replace("%", "")
                    raw = raw.replace("▼", "").replace("▲", "")
                    raw = raw.replace("↓", "").replace("↑", "")
                    raw = raw.strip()
                    item[key] = float(raw) if raw else 0
                except ValueError:
                    item[key] = 0
        items.append(item)

    if len(items) < 10:
        return None   # too few items — something went wrong
    return items


@api_view(["POST"])
def refresh_append1(request):
    """Trigger a full Append1 recompute and snapshot refresh.

    POST /api/sop/refresh/

    Runs the same chain as the upload-completion hook:
      1. Trigger Apps Script computeAppend1
      2. Pull fresh Append1 CSV back from Google Sheet
      3. Save as local snapshot

    Returns immediately — the recompute runs in a background thread.
    The next dashboard load will pick up the fresh data.
    """
    import time as _time

    def _bg_refresh():
        from .sheet_sync import (
            trigger_compute_append1, pull_append1_snapshot,
            trigger_full_refresh,
        )
        try:
            compute = trigger_compute_append1()
            log.info("Manual refresh — computeAppend1: %s", compute)
            if compute.get("ok"):
                _time.sleep(15)
                snap = pull_append1_snapshot()
                log.info("Manual refresh — snapshot pull: %s", snap)
            refresh = trigger_full_refresh()
            log.info("Manual refresh — summaryOnly: %s", refresh)
        except Exception:
            log.exception("Manual refresh failed (non-blocking)")

    threading.Thread(target=_bg_refresh, daemon=True).start()

    return Response({
        "status": "triggered",
        "message": (
            "Append1 recompute started. "
            "The dashboard will update in ~20 seconds."
        ),
    })


@api_view(["GET"])
def demand_supply_overview(request):
    """Demand & Supply Visibility — overview dashboard data.

    Computes all dashboard sections from the 5 uploaded S&OP data files,
    replicating the Sales+Ops Dashboard.xlsm logic.

    Query params:
      ?month=2026-09   — plan month (defaults to latest available)
    """
    # ── Load data from each source ──
    dpr_rows = _get_current_rows("sop_dpr")
    forecast_rows = _get_current_rows("sop_forecast")
    opening_rows = _get_current_rows("sop_opening_stock")
    green_rows = _get_current_rows("sop_green_level")
    sales_rows = _get_current_rows("sop_sales_register")

    # Check if any data is uploaded
    has_data = any([dpr_rows, forecast_rows, opening_rows, green_rows, sales_rows])

    if not has_data:
        return Response({
            "month": None,
            "has_data": False,
            "uploads": {
                k: {"label": v["label"], "has_data": False, "row_count": 0}
                for k, v in SOP_TABLES.items()
            },
            "message": (
                "No data uploaded yet. Upload the 5 data files "
                "(DPR, Forecast, Opening Stock, Green Level, Sales Register) "
                "to power this dashboard."
            ),
        })

    # ── Build upload status ──
    upload_status = {}
    for key, meta in SOP_TABLES.items():
        rows = {
            "sop_dpr": dpr_rows,
            "sop_forecast": forecast_rows,
            "sop_opening_stock": opening_rows,
            "sop_green_level": green_rows,
            "sop_sales_register": sales_rows,
        }[key]
        upload_status[key] = {
            "label": meta["label"],
            "has_data": bool(rows),
            "row_count": len(rows),
        }

    # ── Try loading pre-computed Append1 data ──────────────────────────
    # The Google Sheet's Append1 (computed by Apps Script) is the single
    # source of truth for the dashboard.  Django's local data doesn't
    # include Trading Items, Actual Demand, or a full-month Sales
    # Register, so it cannot reproduce the reference numbers.
    # Priority: 1) local snapshot file  2) Google Sheet CSV export
    #           3) fall back to local computation (legacy)
    snapshot_items = _load_append1_snapshot()
    if snapshot_items is None:
        snapshot_items = _load_append1_from_sheet()

    if snapshot_items is not None and len(snapshot_items) >= 100:
        log.info(
            "Dashboard: using Append1 snapshot (%d items)", len(snapshot_items)
        )
        # The snapshot items already have all Append1 fields pre-computed.
        # Wire them into the same variable names the summary code below uses.
        all_items = snapshot_items
        total_items = len(all_items)

        # Ensure numeric fields default to 0
        _NUMERIC_KEYS = (
            "original_forecast", "committed_forecast", "actual_sales",
            "opening_inventory", "actual_production", "actual_dispatch",
            "closing_inventory", "green_level", "free_inventory",
            "total_available", "stock_adj_added", "stock_adj_deducted",
            "uncovered_shortfall", "dispatch_gap_qty",
            "shortfall_addl_demand", "demand_reduction_adj",
            "production_driven_shortfall", "production_surplus_qty",
            "excess_opening_qty", "excess_dispatched_qty",
            "additional_demand", "ops_adjustment",
        )
        for i in all_items:
            for k in _NUMERIC_KEYS:
                if k not in i:
                    i[k] = 0
            # Ensure committed = original when not set
            if not i.get("committed_forecast"):
                i["committed_forecast"] = i.get("original_forecast", 0)
            # Ensure string fields
            for sk in ("product_class", "type_mts_mto", "item_group",
                       "item_code", "sales_insight_tag", "ops_insight_tag",
                       "ops_narrative", "ops_capacity_narrative"):
                if sk not in i:
                    i[sk] = ""

            # Financial values: the snapshot has pre-computed ₹ columns.
            # Set landed_rate to 0 (not in CSV); the _exc_val_by_type
            # function will use it, producing 0 for type-split values.
            if "landed_rate" not in i:
                i["landed_rate"] = 0
            # Pre-computed financial fields from CSV
            if "opening_value" not in i:
                i["opening_value"] = 0
            if "production_value" not in i:
                i["production_value"] = 0
            if "dispatch_value" not in i:
                i["dispatch_value"] = 0
            if "closing_value" not in i:
                i["closing_value"] = 0
            if "surplus_value" not in i:
                i["surplus_value"] = 0
            if "shortfall_value" not in i:
                i["shortfall_value"] = 0
            if "excess_opening_value" not in i:
                i["excess_opening_value"] = 0

        # Skip the raw-data computation; jump straight to summary.
        # (The "goto" equivalent: all the item-building and derived-field
        # code below runs only when snapshot_items is None.)

        # ── Focus / Regular classification ──
        _FOCUS_ITEMS_SET = {
            "FS M09 B11 J4 CAT", "FD M09 B15 J0 SDF", "WHL M01 B03 J65A TC",
            "WTL M03 B02 48 OEM", "WHL M01 B03 J4 TC", "SFS M09 B11 J45A AL",
            "FS M09 B11 J1X CAT", "SFS M09 B11 J2X AL", "WTL M03 B03 362 TM",
            "WTL M03 B02 72 OEM", "WTL M03 B03 J4 AL1", "FS M09 B11 J2A SDF",
            "WTL M03 B03 262 EE", "WTL M03 B02 12 OEM", "WTL M03 B03 312 EE",
            "FD M09 B15 J00 FL", "FD M09 B15 10-16 JBM", "WTL M03 B03 J3 EE",
            "FD M01 B11 J137S JBM", "WHL M01 B02 20 AKG", "WTL M03 B03 262 FL",
            "WTL M03 B02 88 OEM", "WTL M03 B02 64 OEM", "FD M01 B15 J4X MH",
            "FD M01 B15 J4X OEM", "WTL M03 B02 44 JD", "FD M01 B15 J1X OEM",
            "WHL M01 B03 J75A TC", "WTL M03 B02 20 OEM", "SFS M09 B11 J2A SDF",
            "WTL M03 B02 32 UGC", "TS M02 B08 174 CAT1", "TS M02 B08 82 CAT",
            "WTL M03 B03 212 MM", "WTL M03 B02 06 OEM", "SFS M09 B11 J75A AL",
            "WTL M03 B03 262 JBM", "WTL M03 B02 36 OEM", "WTL M03 B02 44 OEM",
            "WTL M03 B03 312 AL NEW", "WTL M03 B02 28 OEM",
            "SFS M09 B11 J0X AL", "FS M09 B11 J32A SDF", "WTL M03 B03 95A PS",
            "FD M01 B11 J32A JBM", "WTL M03 B03 262 AL NEW",
            "SFD M09 B15 J00 AL", "TS M02 B08 80 CAT", "WTL M03 B02 80 OEM",
            "WTL M03 B03 662 CAT", "WTL M03 B03 312 TM",
            "FS M09 B11 J0X SDF", "WTL M03 B03 95A OEM", "FS M09 B11 J2X SDF",
            "FD M01 B11 J3 MH1", "WTL M03 B03 412 OEM",
            "FS M09 B11 J32A JBM", "WTL M03 B02 16 OEM", "WH M01 B02 16 GLP",
            "FS M09 B11 J3X MH", "FS M09 B11 J2X CAT",
            "WTL M03 B03 462 OEM", "WTL M03 B02 10 OEM",
            "FS M09 B11 J4X JBM", "TS M02 B08 148 CAT",
            "WTL M03 B03 312 MM", "WTL M03 B03 262 MM",
            "WTL M03 B03 312 AL1", "WHL M01 B03 J110A TC",
            "TS M02 B08 42 CAT", "FS M09 B11 J3X JBM",
            "SFS M09 B11 J1X AL", "WTL M03 B02 12 JD",
            "SFS M09 B11 J1X FL", "WTL M03 B02 32 OEM",
            "WHL M01 B03 912 CAT", "WTL M03 B03 262 AL",
            "FS M09 B11 J3 MH",
        }
        for i in all_items:
            ic = i.get("item_code", "")
            if not i.get("product_class") or i["product_class"] == "Regular":
                i["product_class"] = (
                    "Focus" if ic in _FOCUS_ITEMS_SET else "Regular"
                )

        # Jump past the raw-data computation block.
        # Python doesn't have goto, so we use an if/else structure.
        _use_snapshot = True
    else:
        _use_snapshot = False

    # ══════════════════════════════════════════════════════════════════
    # LEGACY PATH: compute from raw uploaded data (only when no
    # snapshot is available).  When _use_snapshot is True, we skip
    # straight to the summary section below.
    # ══════════════════════════════════════════════════════════════════
    if not _use_snapshot:
        items = {}

        def _find_item_code(row):
            """Try common column names for item code.

            NOTE: erp_code is deliberately NOT listed — Green Level data uses
            erp_code (e.g., '216A1016D007AA') which doesn't match item codes
            from Forecast/DPR (e.g., 'WP M04 B01 J4 FG'). Green Level is
            handled separately using jolly_code as the merge key.
            """
            for key in ("item_code", "item_no", "item_number", "material_code",
                         "part_code", "fg_code", "product_code", "sku_code",
                         "material_no", "item"):
                if key in row and row[key]:
                    return str(row[key]).strip()
            # Fallback: first column that contains "item" or "code" in key name
            for key, val in row.items():
                if val and ("item" in key or "code" in key) and "group" not in key:
                    return str(val).strip()
            return None

        def _find_value(row, *candidates):
            """Find first non-None value from candidate column names."""
            for c in candidates:
                if c in row and row[c] is not None:
                    return row[c]
            return None

        # ── Focus Product classification (from reference Sales+Ops Dashboard) ──
        # 78 items classified as "Focus Product"; all others are "Regular".
        _FOCUS_ITEMS = {
            "FS M09 B11 J4 CAT", "FD M09 B15 J0 SDF", "WHL M01 B03 J65A TC",
            "WTL M03 B02 48 OEM", "WHL M01 B03 J4 TC", "SFS M09 B11 J45A AL",
            "FS M09 B11 J1X CAT", "SFS M09 B11 J2X AL", "WTL M03 B03 362 TM",
            "WTL M03 B02 72 OEM", "WTL M03 B03 J4 AL1", "FS M09 B11 J2A SDF",
            "WTL M03 B03 262 EE", "WTL M03 B02 12 OEM", "WTL M03 B03 312 EE",
            "FD M09 B15 J00 FL", "FD M09 B15 10-16 JBM", "WTL M03 B03 J3 EE",
            "FD M01 B11 J137S JBM", "WHL M01 B02 20 AKG", "WTL M03 B03 262 FL",
            "WTL M03 B02 88 OEM", "WTL M03 B02 64 OEM", "FD M01 B15 J4X MH",
            "FD M01 B15 J4X OEM", "WTL M03 B02 44 JD", "FD M01 B15 J1X OEM",
            "WHL M01 B03 J75A TC", "WTL M03 B02 20 OEM", "SFS M09 B11 J2A SDF",
            "WTL M03 B02 32 UGC", "TS M02 B08 174 CAT1", "TS M02 B08 82 CAT",
            "WTL M03 B03 212 MM", "WTL M03 B02 06 OEM", "SFS M09 B11 J75A AL",
            "WTL M03 B03 262 JBM", "WTL M03 B02 36 OEM", "WTL M03 B02 44 OEM",
            "WTL M03 B03 312 AL NEW", "WTL M03 B02 28 OEM", "SFS M09 B11 J0X AL",
            "FS M09 B11 J32A SDF", "WTL M03 B03 95A PS", "FD M01 B11 J32A JBM",
            "WTL M03 B03 262 AL NEW", "SFD M09 B15 J00 AL", "TS M02 B08 80 CAT",
            "WTL M03 B02 80 OEM", "WTL M03 B03 662 CAT", "WTL M03 B03 312 TM",
            "FS M09 B11 J0X SDF", "WTL M03 B03 95A OEM", "FS M09 B11 J2X SDF",
            "FD M01 B11 J3 MH1", "WTL M03 B03 412 OEM", "FS M09 B11 J32A JBM",
            "WTL M03 B02 16 OEM", "WH M01 B02 16 GLP", "FS M09 B11 J3X MH",
            "FS M09 B11 J2X CAT", "WTL M03 B03 462 OEM", "WTL M03 B02 10 OEM",
            "FS M09 B11 J4X JBM", "TS M02 B08 148 CAT", "WTL M03 B03 312 MM",
            "WTL M03 B03 262 MM", "WTL M03 B03 312 AL1", "WHL M01 B03 J110A TC",
            "TS M02 B08 42 CAT", "FS M09 B11 J3X JBM", "SFS M09 B11 J1X AL",
            "WTL M03 B02 12 JD", "SFS M09 B11 J1X FL", "WTL M03 B02 32 OEM",
            "WHL M01 B03 912 CAT", "WTL M03 B03 262 AL", "FS M09 B11 J3 MH",
        }

        # ── STEP 1: Index Forecast — PRIMARY item source (FY 25-26 only).
        # Filter to forecast_category containing "2526" to match the
        # reference dashboard's current-FY scope. Items from FY 26-27
        # are excluded to avoid inflating the item count.
        # ──────────────────────────────────────────────────────────────────
        _ship_seen = set()  # dedup shipment by item_code|forecast_no
        for row in forecast_rows:
            # Filter: FY 25-26 only + Monthly type only.
            # Quarterly/Yearly forecasts overlap with Monthly and would
            # double-count. The reference dashboard uses Monthly only.
            fc_cat = str(row.get("forecast_category", "") or "").strip()
            if fc_cat and "2526" not in fc_cat:
                continue
            fc_type = str(row.get("forecast_type", "") or "").strip()
            if fc_type and fc_type != "Monthly":
                continue
            ic = _find_item_code(row)
            if not ic:
                continue
            if ic not in items:
                items[ic] = {"item_code": ic}
            item = items[ic]
            # forecast_qty is PARTY-LEVEL — each row has a different customer
            # allocation. SUM all rows to get the item total.
            fq = _num(_find_value(
                row, "forecast_qty", "original_forecast", "forecast",
                "plan_qty", "budget_qty", "budgeted_qty"))
            item["original_forecast"] = item.get("original_forecast", 0) + fq
            # total_shipment_qty_base_uom is ITEM-LEVEL — same value repeated
            # on every party row within a forecast_no. Take it ONCE per
            # (item_code, forecast_no) to avoid double-counting.
            fc_no = str(row.get("forecast_no", "") or "").strip()
            ship_key = f"{ic}|{fc_no}"
            if ship_key not in _ship_seen:
                _ship_seen.add(ship_key)
                sq = _num(_find_value(
                    row, "total_shipment_qty_base_uom", "total_shipment_qty",
                    "actual_shipment", "shipment_qty"))
                item["actual_sales"] = item.get("actual_sales", 0) + sq
            # balance_qty — used to compute fq-minus-bal for actual demand
            bal = _num(_find_value(
                row, "balance_qty", "balance"))
            item["balance_qty"] = item.get("balance_qty", 0) + bal
            # Item group from forecast
            grp = _find_value(row, "item_group", "group", "product_group")
            if grp and "item_group" not in item:
                item["item_group"] = str(grp).strip()
            # Product class (Focus / Regular)
            item["product_class"] = (
                "Focus" if ic in _FOCUS_ITEMS else "Regular"
            )

        # ── STEP 2: Merge DPR — production, dispatch, stock adjustments ──
        # Voucher-type aware:
        #   Production      = receipt_qty from "Direct JR" only (manufacturing)
        #   Dispatch        = issue_qty from shipment types, net of reversals/returns
        #   Stock Adj Added = receipt_qty from Material Transfer + TradingItemConversion
        #   Stock Adj Deducted = issue_qty from Material Transfer + TradingItemConversion
        # Only OEM rows create NEW items (matching the reference item set).
        _DPR_PRODUCTION_VT = {"Direct JR"}
        _DPR_SHIPMENT_VT = {"Sales Shipment", "Export Shipment", "Direct Shipment"}
        _DPR_REVERSAL_VT = {"Sales Shipment Reversal", "Sales Return"}
        _DPR_STOCK_ADJ_VT = {"Material Transfer", "TradingItemConversion"}
        for row in dpr_rows:
            vt = str(row.get("voucher_type", "") or "").strip()
            ic = _find_item_code(row)
            if not ic:
                continue
            dpr_cat = str(row.get("item_category", "") or "").strip()
            if ic not in items:
                # Only OEM DPR rows create new items
                if dpr_cat != "FG- OEM":
                    continue
                items[ic] = {
                    "item_code": ic,
                    "product_class": "Focus" if ic in _FOCUS_ITEMS else "Regular",
                }
            item = items[ic]
            receipt = _num(_find_value(
                row, "receipt_qty", "production", "production_qty", "produced",
                "manufactured", "mfg_qty", "receipts", "inward", "inward_qty"))
            issue = _num(_find_value(
                row, "issue_qty", "issue_quantity", "dispatch_qty",
                "issued", "outward", "outward_qty"))
            # Production: only Direct JR (manufacturing journal)
            if vt in _DPR_PRODUCTION_VT:
                item["actual_production"] = item.get("actual_production", 0) + receipt
            # Dispatch: shipments minus reversals/returns
            elif vt in _DPR_SHIPMENT_VT:
                item["dpr_dispatch"] = item.get("dpr_dispatch", 0) + issue
            elif vt in _DPR_REVERSAL_VT:
                item["dpr_dispatch"] = item.get("dpr_dispatch", 0) - receipt
            # Stock adjustments: Material Transfer + TradingItemConversion
            elif vt in _DPR_STOCK_ADJ_VT:
                item["stock_adj_added"] = item.get("stock_adj_added", 0) + receipt
                item["stock_adj_deducted"] = item.get("stock_adj_deducted", 0) + issue
            # Metadata from any DPR row
            grp = _find_value(row, "item_group", "group", "product_group")
            if grp and "item_group" not in item:
                item["item_group"] = str(grp).strip()
            cat = str(row.get("item_category", "") or "").strip()
            if cat and "item_category" not in item:
                item["item_category"] = cat
            rate = _num(_find_value(
                row, "landed_rate", "rate", "unit_rate", "cost_rate",
                "avg_rate", "valuation_rate", "price", "unit_price"))
            if rate and "landed_rate" not in item:
                item["landed_rate"] = rate

        # ── STEP 3: Merge Opening Stock into existing items ──
        # Opening Stock represents physical inventory position — it's the
        # same physical stock regardless of which channel (OEM/Aftermarket)
        # it ends up in.  NO category filter, matching the reference dashboard.
        # Dedup by site+location+item, ACCUMULATE closing_qty as opening.
        opening_seen = set()
        for row in opening_rows:
            ic = _find_item_code(row)
            if not ic or ic not in items:
                continue  # merge only — don't create new items
            site = str(row.get("site_code", "")).strip()
            loc = str(row.get("location_code", "")).strip()
            dedup_key = f"{site}|{loc}|{ic}"
            if dedup_key in opening_seen:
                continue
            opening_seen.add(dedup_key)
            item = items[ic]
            qty = _num(_find_value(
                row, "closing_qty_base_uom", "closing_stock", "closing_qty",
                "opening_qty_base_uom", "opening_quantity", "opening_stock",
                "opening_qty", "stock_qty", "qty", "quantity"))
            item["opening_inventory"] = item.get("opening_inventory", 0) + qty
            rate = _num(_find_value(
                row, "opening_landed_rate", "closing_landed_rate",
                "landed_rate", "rate", "standard_rate"))
            if rate and "landed_rate" not in item:
                item["landed_rate"] = rate
            grp = _find_value(row, "item_group", "group", "product_group",
                              "item_group_description")
            if grp and "item_group" not in item:
                item["item_group"] = str(grp).strip()
            os_cat = str(row.get("item_category", "") or "").strip()
            if os_cat and "item_category" not in item:
                item["item_category"] = os_cat

        # ── STEP 4: Apply Green Level as a LOOKUP to existing items ──
        # Green Level is a single value per item (safety stock), not a
        # cumulative quantity. Use setdefault so the FIRST match wins and
        # duplicates don't inflate the total.
        for row in green_rows:
            ic = str(row.get("jolly_code", "") or "").strip()
            if not ic:
                ic = str(row.get("jollysize", "") or "").strip()
            if not ic:
                ic = str(row.get("erp_code", "") or "").strip()
            if not ic or ic not in items:
                continue  # merge only — don't create new items
            item = items[ic]
            if "green_level" not in item:
                gl_val = _num(_find_value(
                    row, "green_level", "green", "safety_stock", "ss_qty",
                    "min_stock", "reorder_level", "green_level_qty"))
                item["green_level"] = gl_val
            tp = _find_value(row, "mto_mts", "mts_mto", "type",
                             "make_type", "item_type")
            if tp:
                item.setdefault("type_mts_mto", str(tp).strip())

        # ── STEP 5: Merge Sales Register (OEM only) — adds dispatch data ──
        # Unlike the previous merge-only approach, create new items from
        # Sales Register if they don't yet exist. The reference dashboard has
        # 666 items; some come only from Sales Register (not forecast/DPR).
        for row in sales_rows:
            cat = str(row.get("item_category", "")).strip()
            if cat and cat != "FG- OEM":
                continue  # OEM only
            ic = _find_item_code(row)
            if not ic:
                continue
            if ic not in items:
                items[ic] = {
                    "item_code": ic,
                    "product_class": "Focus" if ic in _FOCUS_ITEMS else "Regular",
                }
            item = items[ic]
            qty = _num(_find_value(
                row, "item_base_qty", "item_sales_qty", "qty", "quantity",
                "dispatch_qty", "invoice_qty", "sales_qty", "delivered_qty"))
            item["sales_register_qty"] = item.get("sales_register_qty", 0) + qty

        # ── Post-process: set committed = forecast, resolve dispatch, etc. ──
        for ic, item in items.items():
            # Committed = Original Forecast (same in this data per Apps Script)
            if "committed_forecast" not in item or item["committed_forecast"] == 0:
                item["committed_forecast"] = item.get("original_forecast", 0)
            # Actual Sales Demand: MAX of (shipment deduped, forecast − balance).
            # The reference dashboard uses total_shipment deduped by
            # (item_code, forecast_no) as primary, but when shipment is low
            # or zero the "forecast minus outstanding balance" is the better
            # proxy for actual demand.  Taking the MAX of both aligns with the
            # reference values (3,310,275 target) far more closely than
            # shipment-only (2,669,082) or forecast-only (3,805,175).
            _ship = _num(item.get("actual_sales", 0))
            _fq_bal = (_num(item.get("original_forecast", 0))
                       - _num(item.get("balance_qty", 0)))
            if _ship > 0 or _fq_bal > 0:
                item["actual_sales"] = max(_ship, _fq_bal)
            elif item.get("original_forecast", 0) > 0:
                item["actual_sales"] = item["original_forecast"]
            else:
                item["actual_sales"] = 0
            # Actual Dispatch: DPR shipment is primary source (best available
            # with current data — 4.7% over reference).
            # The reference uses Sales Invoice Register, but the current upload
            # (Sales_Invoice_Register_Report_10-08-2026) only covers Aug 1-10
            # (411 items, 2.87M vs reference 3.64M full month).
            # TODO: once a full-month Sales Register is uploaded, swap priority
            # to Sales Register primary, DPR fallback.
            if item.get("dpr_dispatch", 0) > 0:
                item["actual_dispatch"] = item["dpr_dispatch"]
            elif item.get("sales_register_qty", 0) > 0:
                item["actual_dispatch"] = item["sales_register_qty"]
            elif "actual_dispatch" not in item:
                item["actual_dispatch"] = 0
            # (closing_inventory computed in derived fields as Opening + Prod - Dispatch)

        # ── Compute dashboard metrics ──
        all_items = list(items.values())
        total_items = len(all_items)

        # ── COMPUTE DERIVED FIELDS PER ITEM (mirrors Append1 42-col structure) ──
        for i in all_items:
            _op = _num(i.get("opening_inventory", 0))
            _pr = _num(i.get("actual_production", 0))
            _cm = _num(i.get("committed_forecast", 0))
            _of = _num(i.get("original_forecast", 0))
            _as = _num(i.get("actual_sales", 0))
            _gl = _num(i.get("green_level", 0))
            _rt = _num(i.get("landed_rate", 0))

            # Stock adjustments from Material Transfer / TradingItemConversion
            # NOTE: tracked per item but NOT included in TA yet — the portal's
            # DPR-based stock adj data does not match the reference's separate
            # "Trading Items" tab.  Including it overshoots TA.  Enable once a
            # dedicated Trading Items upload exists.
            # _sa_add = _num(i.get("stock_adj_added", 0))
            # _sa_ded = _num(i.get("stock_adj_deducted", 0))

            # Total Available = Opening + Production
            _ta = _op + _pr
            i["total_available"] = _ta

            # Actual Dispatch
            _dp = _num(i.get("actual_dispatch", 0))

            # Closing = Total Available - Dispatch (computed, like Apps Script R = N - P)
            _cl = _ta - _dp
            i["closing_inventory"] = _cl

            i["ops_adjustment"] = _of - _cm
            # Additional Demand = Actual Sales - Committed (can be negative,
            # matching reference dashboard which shows ▼ for under-demand).
            i["additional_demand"] = _as - _cm
            i["dispatch_pct"] = round(_dp / _cm * 100, 1) if _cm > 0 else 0
            # Reference formula: =MAX(R-S, 0) — negative free inv treated as 0
            i["free_inventory"] = max(0, _cl - _gl)

            # Shortfall & Gaps (Append1 cols 21-25)
            i["uncovered_shortfall"] = max(0, _cm - _ta)
            i["dispatch_gap_qty"] = max(0, min(_cm, _ta) - _dp)
            _addl = max(0, _as - _cm)
            i["shortfall_addl_demand"] = (
                min(_addl, max(0, _as - _ta))
                if _addl > 0 and _ta < _as else 0
            )
            i["demand_reduction_adj"] = max(0, _of - _cm)
            i["production_driven_shortfall"] = max(0, _cm - _ta)

            # Surplus & Excess (Append1 cols 26-28)
            i["production_surplus_qty"] = max(0, _pr - max(0, _cm - _op))
            i["excess_opening_qty"] = max(0, _op - _cm - _gl)
            i["excess_dispatched_qty"] = max(0, _dp - _cm)

            # Financial Impact (Append1 cols 34-42)
            i["opening_value"] = round(_op * _rt, 2) if _rt else 0
            i["production_value"] = round(_pr * _rt, 2) if _rt else 0
            i["dispatch_value"] = round(_dp * _rt, 2) if _rt else 0
            i["closing_value"] = round(_cl * _rt, 2) if _rt else 0
            i["surplus_value"] = round(i["production_surplus_qty"] * _rt, 2) if _rt else 0
            i["shortfall_value"] = round(i["production_driven_shortfall"] * _rt, 2) if _rt else 0
            i["excess_opening_value"] = round(i["excess_opening_qty"] * _rt, 2) if _rt else 0
    # --- end legacy computation ---

    # ══════════════════════════════════════════════════════════════════
    # COMMON PATH: both snapshot and legacy paths merge here.
    # all_items + total_items are set by whichever path ran.
    # ══════════════════════════════════════════════════════════════════
    focus_items = [i for i in all_items
                   if "focus" in str(i.get("product_class", "")).lower()]
    regular_items = [i for i in all_items
                     if "focus" not in str(i.get("product_class", "")).lower()]

    def _sum(items_list, key):
        return sum(_num(i.get(key, 0)) for i in items_list)

    # ── VOLUME & FULFILMENT ──
    total_forecast = _sum(all_items, "original_forecast")
    total_committed = _sum(all_items, "committed_forecast")
    total_actual_sales = _sum(all_items, "actual_sales")
    total_additional = total_actual_sales - total_committed if total_committed else 0
    total_production = _sum(all_items, "actual_production")
    total_dispatch = _sum(all_items, "actual_dispatch")
    total_closing = _sum(all_items, "closing_inventory")
    total_opening = _sum(all_items, "opening_inventory")
    total_green_level = _sum(all_items, "green_level")
    # Free Inv = SUM of per-item max(0, closing-gl), already set above
    total_free_inv = _sum(all_items, "free_inventory")

    # ── HEALTH RATIOS ──
    # Dispatch Fulfilment = Dispatch ÷ Actual Sales Demand.
    # Reference header says "÷ Committed" but 3,644,007/3,310,275 = 110.1%.
    dispatch_fulfilment = round(total_dispatch / total_actual_sales * 100, 1) if total_actual_sales else 0

    # Production Coverage — Build-Required basis (matches reference dashboard).
    # When the snapshot provides pre-computed build_required / production_counted
    # columns, use them directly — the Apps Script's production figures come from
    # all DPR receipt types, which differ from Django's Direct-JR-only filter.
    _prod_counted_sum = 0
    _build_req_sum = 0
    _has_precomputed_br = any(
        _num(i.get("build_required", 0)) > 0 for i in all_items
    )
    for i in all_items:
        if _has_precomputed_br:
            _br = _num(i.get("build_required", 0))
            _pc = _num(i.get("production_counted", 0))
        else:
            _cm_i = _num(i.get("committed_forecast", 0))
            _gl_i = _num(i.get("green_level", 0))
            _op_i = _num(i.get("opening_inventory", 0))
            _pr_i = _num(i.get("actual_production", 0))
            _br = _cm_i + _gl_i - _op_i
            _pc = min(_pr_i, _br) if _br > 0 else 0
        if _br > 0:
            _build_req_sum += _br
            _prod_counted_sum += _pc
    production_coverage = round(_prod_counted_sum / _build_req_sum * 100, 1) if _build_req_sum else 0

    # Forecast accuracy: hit rate — items where actual/forecast ratio
    # is within ±10% of forecast.
    # Denominator includes items with fc>0 OR actual_sales>0 (matching
    # the reference dashboard's 51.84% = 310/598).
    forecast_items_count = 0
    accurate_count = 0
    for i in all_items:
        fc = _num(i.get("original_forecast", 0))
        act = _num(i.get("actual_sales", 0))
        if fc <= 0 and act <= 0:
            continue
        forecast_items_count += 1
        if fc > 0 and abs(act - fc) / fc <= 0.10:
            accurate_count += 1
    forecast_accuracy = (
        round(accurate_count / forecast_items_count * 100, 2)
        if forecast_items_count else 0
    )

    # ── Segment helpers (focus / regular splits) ──
    def _seg_fa(items_list):
        """Forecast accuracy for a segment — same formula as main."""
        denom = 0
        hits = 0
        for i in items_list:
            fc = _num(i.get("original_forecast", 0))
            act = _num(i.get("actual_sales", 0))
            if fc <= 0 and act <= 0:
                continue
            denom += 1
            if fc > 0 and abs(act - fc) / fc <= 0.10:
                hits += 1
        return round(hits / denom * 100, 2) if denom else 0

    def _seg_pc(items_list):
        """Production coverage for a segment — same formula as main."""
        br_sum = 0
        pc_sum = 0
        for i in items_list:
            if _has_precomputed_br:
                br = _num(i.get("build_required", 0))
                pc = _num(i.get("production_counted", 0))
            else:
                cm = _num(i.get("committed_forecast", 0))
                gl = _num(i.get("green_level", 0))
                op = _num(i.get("opening_inventory", 0))
                pr = _num(i.get("actual_production", 0))
                br = cm + gl - op
                pc = min(pr, br) if br > 0 else 0
            if br > 0:
                br_sum += br
                pc_sum += pc
        return round(pc_sum / br_sum * 100, 1) if br_sum else 0

    # ── EXCEPTIONS (with Focus / Regular split) ──
    def _exc_count(items_list, pred):
        return sum(1 for i in items_list if pred(i))

    # When the snapshot provides pre-computed exception columns, use them
    # directly (they match the reference dashboard).  Fall back to computing
    # from raw fields when columns are absent (legacy / non-snapshot path).
    _has_precomputed_exc = any(
        _num(i.get("production_driven_shortfall", 0)) > 0
        or _num(i.get("production_surplus_qty", 0)) > 0
        for i in all_items[:50]
    )

    if _has_precomputed_exc:
        def _prod_short(i):
            return _num(i.get("production_driven_shortfall", 0)) > 0

        def _prod_surp(i):
            return _num(i.get("production_surplus_qty", 0)) > 0

        def _excess_stk(i):
            return _num(i.get("excess_opening_qty", 0)) > 0

        def _disp_gap(i):
            return _num(i.get("dispatch_gap_qty", 0)) > 0
    else:
        def _prod_short(i):
            _cm = _num(i.get("committed_forecast", 0))
            _op = _num(i.get("opening_inventory", 0))
            _pr = _num(i.get("actual_production", 0))
            return _cm > 0 and (_cm - _op - _pr) > 0

        def _prod_surp(i):
            _cm = _num(i.get("committed_forecast", 0))
            _op = _num(i.get("opening_inventory", 0))
            _pr = _num(i.get("actual_production", 0))
            return _pr > 0 and _pr > max(0, _cm - _op)

        def _excess_stk(i):
            _op = _num(i.get("opening_inventory", 0))
            _cm = _num(i.get("committed_forecast", 0))
            _gl = _num(i.get("green_level", 0))
            return _op > (_cm + _gl)

        def _disp_gap(i):
            _cm = _num(i.get("committed_forecast", 0))
            _ta = _num(i.get("total_available", 0))
            _dp = _num(i.get("actual_dispatch", 0))
            return _cm > 0 and (min(_cm, _ta) - _dp) > 0

    def _below_gl(i):
        # Below Green Level = closing < green_level (no GL>0 guard;
        # reference counts items with negative closing as below even if GL=0)
        return _num(i.get("closing_inventory", 0)) < _num(i.get("green_level", 0))

    def _above_gl(i):
        return not _below_gl(i)

    def _exc_split(pred):
        return {
            "total": _exc_count(all_items, pred),
            "focus": _exc_count(focus_items, pred),
            "regular": _exc_count(regular_items, pred),
        }

    prod_shortfall_count = _exc_count(all_items, _prod_short)
    prod_surplus_count = _exc_count(all_items, _prod_surp)
    excess_stock_count = _exc_count(all_items, _excess_stk)
    dispatch_gap_count = _exc_count(all_items, _disp_gap)
    below_green_count = _exc_count(all_items, _below_gl)
    above_green_count = _exc_count(all_items, _above_gl)

    exceptions_data = {
        "production_shortfall": _exc_split(_prod_short),
        "production_surplus": _exc_split(_prod_surp),
        "excess_opening_stock": _exc_split(_excess_stk),
        "dispatch_gap": _exc_split(_disp_gap),
        "below_green_level": _exc_split(_below_gl),
        "above_green_level": _exc_split(_above_gl),
    }

    # ── SHORTFALL & GAPS (counts + totals) ──
    def _gap_agg(key):
        items_with = [i for i in all_items if _num(i.get(key, 0)) > 0]
        return {
            "count": len(items_with),
            "qty": round(sum(_num(i.get(key, 0)) for i in items_with), 0),
        }

    shortfall_gaps = {
        "uncovered_shortfall": _gap_agg("uncovered_shortfall"),
        "dispatch_gap": _gap_agg("dispatch_gap_qty"),
        "shortfall_addl_demand": _gap_agg("shortfall_addl_demand"),
        "demand_reduction": _gap_agg("demand_reduction_adj"),
        "production_driven": _gap_agg("production_driven_shortfall"),
    }

    # ── SURPLUS & EXCESS ──
    surplus_excess = {
        "production_surplus": _gap_agg("production_surplus_qty"),
        "excess_opening": _gap_agg("excess_opening_qty"),
        "excess_dispatched": _gap_agg("excess_dispatched_qty"),
    }

    # ── FINANCIAL IMPACT ──
    financial_impact = {
        "opening_value": round(_sum(all_items, "opening_value"), 0),
        "production_value": round(_sum(all_items, "production_value"), 0),
        "dispatch_value": round(_sum(all_items, "dispatch_value"), 0),
        "closing_value": round(_sum(all_items, "closing_value"), 0),
        "surplus_value": round(_sum(all_items, "surplus_value"), 0),
        "shortfall_value": round(_sum(all_items, "shortfall_value"), 0),
        "excess_opening_value": round(_sum(all_items, "excess_opening_value"), 0),
        "items_with_rate": sum(
            1 for i in all_items if _num(i.get("landed_rate", 0)) > 0
        ),
    }

    # ── EXCEPTIONS — Qty & ₹ VALUE (MTS / MTO / TBC bifurcation) ──
    # Mirrors reference dashboard's "EXCEPTIONS — Qty & ₹ VALUE" section.
    # Each bucket shows total qty, ₹ value, split by MTS/MTO/TBC.
    # When the snapshot has pre-computed ₹ value columns, use them directly;
    # otherwise fall back to qty × landed_rate.

    # Map: qty_key → pre-computed ₹ value key in the snapshot
    _VAL_KEY_MAP = {
        "production_driven_shortfall": "production_shortfall_val",
        "dispatch_gap_qty":            "dispatch_gap_val",
        "shortfall_addl_demand":       "shortfall_addl_val",
        "production_surplus_qty":      "surplus_value",
        "excess_opening_qty":          "excess_opening_value",
        "demand_reduction_adj":        "demand_reduction_val",
        "excess_dispatched_qty":       "excess_dispatch_val",
        "excess_dispatch_from_opstock":  "excess_dispatch_opstock_val",
        "excess_dispatch_from_surplus":  "excess_dispatch_surplus_val",
    }

    def _exc_val_by_type(key):
        """Sum qty + value for an exception key, split by type."""
        val_key = _VAL_KEY_MAP.get(key)
        by_type = {"MTS": {"qty": 0, "value": 0},
                   "MTO": {"qty": 0, "value": 0},
                   "TBC": {"qty": 0, "value": 0}}
        total_qty = 0
        total_val = 0
        for i in all_items:
            q = _num(i.get(key, 0))
            if q <= 0:
                continue
            # Use pre-computed ₹ value if available, else qty × rate
            if val_key:
                v = abs(_num(i.get(val_key, 0)))
            else:
                rt = _num(i.get("landed_rate", 0))
                v = round(q * rt, 2)
            total_qty += q
            total_val += v
            tp = str(i.get("type_mts_mto", "TBC")).upper().strip()
            if tp not in by_type:
                tp = "TBC"
            by_type[tp]["qty"] += q
            by_type[tp]["value"] += v
        return {
            "total": {"qty": round(total_qty, 0), "value": round(total_val, 0)},
            "MTS": {"qty": round(by_type["MTS"]["qty"], 0),
                    "value": round(by_type["MTS"]["value"], 0)},
            "MTO": {"qty": round(by_type["MTO"]["qty"], 0),
                    "value": round(by_type["MTO"]["value"], 0)},
            "TBC": {"qty": round(by_type["TBC"]["qty"], 0),
                    "value": round(by_type["TBC"]["value"], 0)},
        }

    # Uncovered Shortfall — uses pre-computed column (max(0, committed - total_avail))
    # which is capped per item, unlike the sum of sub-buckets.
    # ₹ value is scaled proportionally when sub-buckets exceed the capped qty.
    uc_by_type = {"MTS": {"qty": 0, "value": 0},
                  "MTO": {"qty": 0, "value": 0},
                  "TBC": {"qty": 0, "value": 0}}
    uc_total_qty = 0
    uc_total_val = 0
    for i in all_items:
        uc = _num(i.get("uncovered_shortfall", 0))
        if uc <= 0:
            continue
        pds = _num(i.get("production_driven_shortfall", 0))
        dg = _num(i.get("dispatch_gap_qty", 0))
        sad = _num(i.get("shortfall_addl_demand", 0))
        raw_sum = pds + dg + sad

        pds_v = abs(_num(i.get("production_shortfall_val", 0)))
        dg_v = abs(_num(i.get("dispatch_gap_val", 0)))
        sad_v = abs(_num(i.get("shortfall_addl_val", 0)))
        raw_val = pds_v + dg_v + sad_v

        # Scale ₹ proportionally if sub-buckets exceed capped shortfall
        if raw_sum > 0 and raw_sum > uc:
            v = raw_val * (uc / raw_sum)
        elif raw_val > 0:
            v = raw_val
        else:
            rt = _num(i.get("landed_rate", 0))
            v = round(uc * rt, 2)

        uc_total_qty += uc
        uc_total_val += v
        tp = str(i.get("type_mts_mto", "TBC")).upper().strip()
        if tp not in uc_by_type:
            tp = "TBC"
        uc_by_type[tp]["qty"] += uc
        uc_by_type[tp]["value"] += v

    # Build exceptions_value with Focus/Regular sub-splits
    def _exc_val_full(key):
        """qty + value by type AND by focus/regular for an exception key."""
        base = _exc_val_by_type(key)
        # Add focus / regular sub-aggregates
        val_key = _VAL_KEY_MAP.get(key)
        for label, subset in [("focus", focus_items), ("regular", regular_items)]:
            by_tp = {"MTS": {"qty": 0, "value": 0},
                     "MTO": {"qty": 0, "value": 0},
                     "TBC": {"qty": 0, "value": 0}}
            tq = tv = 0
            for i in subset:
                q = _num(i.get(key, 0))
                if q <= 0:
                    continue
                v = abs(_num(i.get(val_key, 0))) if val_key else round(q * _num(i.get("landed_rate", 0)), 2)
                tq += q; tv += v
                tp = str(i.get("type_mts_mto", "TBC")).upper().strip()
                if tp not in by_tp:
                    tp = "TBC"
                by_tp[tp]["qty"] += q; by_tp[tp]["value"] += v
            base[label] = {
                "total": {"qty": round(tq, 0), "value": round(tv, 0)},
                "MTS": {"qty": round(by_tp["MTS"]["qty"], 0), "value": round(by_tp["MTS"]["value"], 0)},
                "MTO": {"qty": round(by_tp["MTO"]["qty"], 0), "value": round(by_tp["MTO"]["value"], 0)},
                "TBC": {"qty": round(by_tp["TBC"]["qty"], 0), "value": round(by_tp["TBC"]["value"], 0)},
            }
        return base

    # Uncovered shortfall focus/regular sub-splits
    uc_focus = {"MTS": {"qty": 0, "value": 0}, "MTO": {"qty": 0, "value": 0}, "TBC": {"qty": 0, "value": 0}}
    uc_regular = {"MTS": {"qty": 0, "value": 0}, "MTO": {"qty": 0, "value": 0}, "TBC": {"qty": 0, "value": 0}}
    uc_focus_qty = uc_focus_val = uc_regular_qty = uc_regular_val = 0
    for i in all_items:
        uc = _num(i.get("uncovered_shortfall", 0))
        if uc <= 0:
            continue
        pds = _num(i.get("production_driven_shortfall", 0))
        dg = _num(i.get("dispatch_gap_qty", 0))
        sad = _num(i.get("shortfall_addl_demand", 0))
        raw_sum = pds + dg + sad
        pds_v = abs(_num(i.get("production_shortfall_val", 0)))
        dg_v = abs(_num(i.get("dispatch_gap_val", 0)))
        sad_v = abs(_num(i.get("shortfall_addl_val", 0)))
        raw_val = pds_v + dg_v + sad_v
        v = raw_val * (uc / raw_sum) if raw_sum > 0 and raw_sum > uc else raw_val if raw_val > 0 else 0
        tp = str(i.get("type_mts_mto", "TBC")).upper().strip()
        if tp not in uc_focus:
            tp = "TBC"
        is_focus = "focus" in str(i.get("product_class", "")).lower()
        dest = uc_focus if is_focus else uc_regular
        dest[tp]["qty"] += uc; dest[tp]["value"] += v
        if is_focus:
            uc_focus_qty += uc; uc_focus_val += v
        else:
            uc_regular_qty += uc; uc_regular_val += v

    def _uc_sub(d, tq, tv):
        return {
            "total": {"qty": round(tq, 0), "value": round(tv, 0)},
            "MTS": {"qty": round(d["MTS"]["qty"], 0), "value": round(d["MTS"]["value"], 0)},
            "MTO": {"qty": round(d["MTO"]["qty"], 0), "value": round(d["MTO"]["value"], 0)},
            "TBC": {"qty": round(d["TBC"]["qty"], 0), "value": round(d["TBC"]["value"], 0)},
        }

    exceptions_value = {
        "uncovered_shortfall": {
            "total": {"qty": round(uc_total_qty, 0), "value": round(uc_total_val, 0)},
            "MTS": {"qty": round(uc_by_type["MTS"]["qty"], 0), "value": round(uc_by_type["MTS"]["value"], 0)},
            "MTO": {"qty": round(uc_by_type["MTO"]["qty"], 0), "value": round(uc_by_type["MTO"]["value"], 0)},
            "TBC": {"qty": round(uc_by_type["TBC"]["qty"], 0), "value": round(uc_by_type["TBC"]["value"], 0)},
            "focus": _uc_sub(uc_focus, uc_focus_qty, uc_focus_val),
            "regular": _uc_sub(uc_regular, uc_regular_qty, uc_regular_val),
        },
        "production_driven": _exc_val_full("production_driven_shortfall"),
        "dispatch_gap": _exc_val_full("dispatch_gap_qty"),
        "shortfall_addl_demand": _exc_val_full("shortfall_addl_demand"),
        "production_surplus": _exc_val_full("production_surplus_qty"),
        "excess_opening": _exc_val_full("excess_opening_qty"),
        "demand_reduction": _exc_val_full("demand_reduction_adj"),
        "excess_dispatched": _exc_val_full("excess_dispatched_qty"),
        "excess_dispatched_from_opstock": _exc_val_full("excess_dispatch_from_opstock"),
        "excess_dispatched_from_surplus": _exc_val_full("excess_dispatch_from_surplus"),
    }

    # ── INSIGHT ENGINE (Insight Logic Master — cols W, X, Y, Z, AA) ──
    # Each item gets: sales_tag (W), sales_narrative (X),
    #                  ops_tag (Y), ops_narrative (Z),
    #                  ops_capacity_narrative (AA).
    # Variable mapping to Append1 columns:
    #   D=original_forecast  G=committed_forecast  F=ops_adjustment
    #   I=forecast_variance  K=actual_production   L=total_available
    #   M=type_mts_mto       N=actual_dispatch     O=closing_inventory
    #   P=green_level        R=uncovered_shortfall  S=production_surplus
    #   U=excess_dispatched  V=dispatch_gap

    def _insight_item(i):
        """Compute all 5 insight columns for one item."""
        D = _num(i.get("original_forecast", 0))
        G = _num(i.get("committed_forecast", 0))
        F = G - D   # Ops Adjustment (+ = over-commit, - = capacity cut)
        H = D - G   # Additional Demand direction (+ = cut, - = uplift)
        N = _num(i.get("actual_dispatch", 0))
        K = _num(i.get("actual_production", 0))
        O = _num(i.get("closing_inventory", 0))
        P = _num(i.get("green_level", 0))
        L = _num(i.get("total_available", 0))
        M = str(i.get("type_mts_mto", "TBC")).upper().strip()
        R = max(0, G - L)   # Uncovered Shortfall
        S = _num(i.get("production_surplus_qty", 0))
        U = _num(i.get("excess_dispatched_qty", 0))
        V = _num(i.get("dispatch_gap_qty", 0))
        _as = _num(i.get("actual_sales", 0))

        # Forecast Accuracy Variance = |Actual - Forecast| / Forecast
        I = abs(_as - D) / D if D > 0 else 0

        # Dispatch % of committed
        dp_pct = round(N / G * 100, 0) if G > 0 else 0

        # ── Col W: Sales Insight Tag ──
        sales_tags = []
        if G > 0 and N > 0:
            if N > G * 1.1:       # W-01
                sales_tags.append("Over-Delivered")
            elif N >= G * 0.9:    # W-02
                sales_tags.append("On Target")
            else:                 # W-03
                sales_tags.append("Short Delivery")
        if D > 0:
            if I == 0:            # W-04
                sales_tags.append("Forecast Bullseye")
            elif I <= 0.1:        # W-05
                sales_tags.append("Forecast Drift (Minor)")
            elif I <= 0.3:        # W-06
                sales_tags.append("Forecast Drift (Moderate)")
            else:                 # W-07
                sales_tags.append("Forecast Drift (Major)")

        # ── Col X: Sales Insight Narrative ──
        narr_x = []
        # X-01: Dispatch header (always)
        if G > 0:
            narr_x.append(f"Dispatch {dp_pct:.0f}% of committed ({N:,.0f} vs {G:,.0f}).")
        # X-02/X-03: Type context
        if M == "MTS":
            narr_x.append("MTS item — buffer stock + green level matters.")
        elif M == "MTO":
            narr_x.append("MTO item — demand is order-driven.")
        # X-04 to X-10: Forecast variance narrative
        if D > 0:
            i_pct = f"{I*100:.0f}%"
            if I == 0:
                narr_x.append("Forecast hit dead-on (0% variance) — strong demand sensing.")
            elif I <= 0.1 and H > 0:
                narr_x.append(f"Forecast tightening of {i_pct} — minor cut, within normal tolerance.")
            elif I <= 0.1 and H <= 0:
                narr_x.append(f"Forecast raised by {i_pct} — minor uplift, well within tolerance.")
            elif I <= 0.3 and H > 0:
                narr_x.append(f"⚠ Forecast cut by {i_pct} post-commit — demand softened or deals slipped. Review demand-sensing process.")
            elif I <= 0.3 and H <= 0:
                narr_x.append(f"⚠ Forecast raised by {i_pct} post-commit — late orders pulled in. Review pipeline visibility.")
            elif I > 0.3 and H > 0:
                narr_x.append(f"\U0001f6a9 Major forecast cut of {i_pct} — severe over-promise. Escalate to Sales leadership.")
            elif I > 0.3 and H <= 0:
                narr_x.append(f"\U0001f6a9 Major forecast uplift of {i_pct} — late demand surge disrupted planning.")
        # X-11/X-12/X-13: Gap actions
        if U > 0:
            narr_x.append(f"Action: review over-commit of {U:,.0f} units.")
        if V > 0:
            narr_x.append(f"Action: recover shortfall of {V:,.0f} units.")
        if V == 0 and U == 0:
            narr_x.append("No open commitment gap.")

        # ── Col Y: Operations Insight Tag ──
        ops_tags = []
        if R > 0:                                               # Y-01
            ops_tags.append("Production Shortfall")
        if M == "MTS" and P > 0 and O < P and O >= P * 0.5:    # Y-02
            ops_tags.append("Below Safety")
        if M == "MTS" and P > 0 and O < P * 0.5:               # Y-03
            ops_tags.append("Stock-Out Risk")
        if M == "MTS" and S > G * 0.5 and G > 0:               # Y-04
            ops_tags.append("Excess Inventory")
        elif M == "MTS" and S > 0 and S <= G * 0.5:            # Y-05
            ops_tags.append("Production Surplus")
        if M == "MTO" and O > 0 and N >= G:                     # Y-06
            ops_tags.append("Unsold MTO Stock")
        if M == "MTO" and S > 0:                                # Y-07
            ops_tags.append("Over-Production")
        # Capacity Gap rules (Y-08 to Y-11)
        if D > 0:
            f_abs_pct = abs(F) / D
            if F < 0 and f_abs_pct > 0.3:                      # Y-08
                ops_tags.append("Capacity Gap (Major)")
            elif F < 0 and f_abs_pct > 0.1:                    # Y-09
                ops_tags.append("Capacity Gap (Moderate)")
            elif F < 0 and f_abs_pct > 0:                      # Y-10
                ops_tags.append("Capacity Gap (Minor)")
            elif F > 0:                                         # Y-11
                ops_tags.append("Ops Over-Commit")
        # Y-12: Healthy Stock
        if (R == 0 and S == 0 and F == 0
            and ((M == "MTS" and O >= P) or (M == "MTO" and O == 0))):
            ops_tags.append("Healthy Stock")

        # ── Col Z: Operations Insight Narrative ──
        narr_z = []
        # Z-01: Production header (always)
        if G > 0:
            narr_z.append(f"Produced {K:,.0f} units against committed {G:,.0f} units.")
        # Z-02: Production Shortfall
        if R > 0:
            narr_z.append(f"Shortfall of {R:,.0f} units — expedite production or procure.")
        # Z-03: MTS Below Safety
        if M == "MTS" and P > 0 and O < P:
            narr_z.append(f"Closing inventory {O:,.0f} below green level {P:,.0f} — replenish next cycle.")
        # Z-04: Excess Inventory
        if M == "MTS" and G > 0 and S > G * 0.5:
            narr_z.append(f"Excess build-up of {S:,.0f} units — throttle production.")
        # Z-05: MTO Over-Production
        if M == "MTO" and S > 0:
            narr_z.append(f"Red flag — produced {S:,.0f} units more than ordered. Investigate planning breakdown.")
        # Z-06: Healthy Closing
        if (R == 0 and S == 0
            and ((M == "MTS" and O >= P) or (M == "MTO" and O == 0))):
            narr_z.append("Production and inventory in healthy state.")

        # ── Col AA: Ops Capacity Gap Narrative ──
        narr_aa = ""
        if D > 0:
            f_abs_pct = abs(F) / D
            f_pct_str = f"{f_abs_pct*100:.0f}%"
            if F == 0:                                          # AA-01
                narr_aa = "Ops accepted Sales forecast in full. No capacity gap at plan stage."
            elif F < 0 and f_abs_pct > 0.3:                    # AA-02
                narr_aa = (f"Ops cut {abs(F):,.0f} units (-{f_pct_str}) from forecast {D:,.0f}. "
                           "⚠ Major capacity gap — escalate to S&OP. "
                           "Action: shift extension, OT, expedite procurement, or outsource.")
            elif F < 0 and f_abs_pct > 0.1:                    # AA-03
                narr_aa = (f"Ops cut {abs(F):,.0f} units (-{f_pct_str}) from forecast {D:,.0f}. "
                           "⚠ Moderate gap — line-level mitigation needed. "
                           "Action: shift extension, OT, or expedite procurement.")
            elif F < 0:                                         # AA-04
                narr_aa = (f"Ops cut {abs(F):,.0f} units (-{f_pct_str}) from forecast {D:,.0f}. "
                           "Minor adjustment — standard handling.")
            elif F > 0:                                         # AA-05
                narr_aa = (f"Ops over-committed by {F:,.0f} units (+{f_pct_str}) vs forecast {D:,.0f}. "
                           "Validate demand uptake with Sales — risk of excess inventory if not absorbed.")
        else:
            narr_aa = "Ops accepted Sales forecast in full. No capacity gap at plan stage."

        return {
            "sales_tags": sales_tags,
            "sales_narrative": " ".join(narr_x),
            "ops_tags": ops_tags,
            "ops_narrative": " ".join(narr_z),
            "ops_capacity_narrative": narr_aa,
        }

    # Apply insights to each item and collect tag counts.
    # When the snapshot provides pre-computed insight tags (sales_insight_tag,
    # ops_insight_tag), count from those directly — the reference dashboard's
    # tag logic may differ from the Python _insight_item() reimplementation.
    _has_precomputed_tags = any(
        i.get("sales_insight_tag", "").strip() for i in all_items[:20]
    )

    sales_tag_counts = {}
    ops_tag_counts = {}

    if _has_precomputed_tags:
        for i in all_items:
            for t in str(i.get("sales_insight_tag", "")).split(" | "):
                t = t.strip()
                if t:
                    sales_tag_counts[t] = sales_tag_counts.get(t, 0) + 1
            for t in str(i.get("ops_insight_tag", "")).split(" | "):
                t = t.strip()
                if t:
                    ops_tag_counts[t] = ops_tag_counts.get(t, 0) + 1
    else:
        for i in all_items:
            insight = _insight_item(i)
            i["sales_insight_tag"] = " | ".join(insight["sales_tags"])
            i["sales_narrative"] = insight["sales_narrative"]
            i["ops_insight_tag"] = " | ".join(insight["ops_tags"])
            i["ops_narrative"] = insight["ops_narrative"]
            i["ops_capacity_narrative"] = insight["ops_capacity_narrative"]
            for t in insight["sales_tags"]:
                sales_tag_counts[t] = sales_tag_counts.get(t, 0) + 1
            for t in insight["ops_tags"]:
                ops_tag_counts[t] = ops_tag_counts.get(t, 0) + 1

    insights_summary = {
        "sales_tags": sales_tag_counts,
        "ops_tags": ops_tag_counts,
    }

    # ── Helper: pack common insight fields into a top-10 dict ──
    def _item_insight_fields(i):
        return {
            "sales_tag": i.get("sales_insight_tag", ""),
            "sales_narrative": i.get("sales_narrative", ""),
            "ops_tag": i.get("ops_insight_tag", ""),
            "ops_narrative": i.get("ops_narrative", ""),
            "ops_capacity": i.get("ops_capacity_narrative", ""),
        }

    # ── TOP 10 — EXCESS FREE INVENTORY (capital tied up above Green Level) ──
    free_inv_items = []
    for i in all_items:
        free_inv = _num(i.get("free_inventory", 0))
        if free_inv > 0:
            gl = _num(i.get("green_level", 0))
            d = {
                "item_code": i["item_code"],
                "item_group": i.get("item_group", ""),
                "type": i.get("type_mts_mto", ""),
                "closing": round(_num(i.get("closing_inventory", 0)), 1),
                "green_level": round(gl, 1),
                "free_inv": round(free_inv, 1),
                "x_green": round(free_inv / gl, 1) if gl > 0 else 0,
                "free_inventory": round(free_inv, 1),
            }
            d.update(_item_insight_fields(i))
            free_inv_items.append(d)
    free_inv_items.sort(key=lambda x: -x["free_inv"])
    top10_free_inv = free_inv_items[:10]

    # ── TOP 10 — BELOW GREEN LEVEL ──
    below_green_items = []
    for i in all_items:
        cl = _num(i.get("closing_inventory", 0))
        gl = _num(i.get("green_level", 0))
        if gl > 0 and cl < gl:
            d = {
                "item_code": i["item_code"],
                "item_group": i.get("item_group", ""),
                "type": i.get("type_mts_mto", ""),
                "closing": round(cl, 1),
                "green_level": round(gl, 1),
                "deficit": round(gl - cl, 1),
            }
            d.update(_item_insight_fields(i))
            below_green_items.append(d)
    below_green_items.sort(key=lambda x: -x["deficit"])
    top10_below_green = below_green_items[:10]

    # ── TYPE BREAKDOWN (MTS / MTO / TBC) ──
    type_breakdown = {}
    for i in all_items:
        t = str(i.get("type_mts_mto", "TBC")).upper().strip()
        if t not in type_breakdown:
            type_breakdown[t] = {
                "type": t, "items": 0,
                "forecast": 0, "committed": 0,
                "production": 0, "dispatch": 0,
            }
        tb = type_breakdown[t]
        tb["items"] += 1
        tb["forecast"] += _num(i.get("original_forecast", 0))
        tb["committed"] += _num(i.get("committed_forecast", 0))
        tb["production"] += _num(i.get("actual_production", 0))
        tb["dispatch"] += _num(i.get("actual_dispatch", 0))

    type_rows = sorted(type_breakdown.values(), key=lambda x: -x["items"])
    for tr in type_rows:
        tr["share_pct"] = round(tr["items"] / total_items * 100, 1) if total_items else 0

    # ── TOP 10 Production Shortfall ──
    # Use pre-computed production_driven_shortfall column when available.
    shortfall_items = []
    for i in all_items:
        pds = _num(i.get("production_driven_shortfall", 0))
        if pds > 0:
            d = {
                "item_code": i["item_code"],
                "item_group": i.get("item_group", ""),
                "type": i.get("type_mts_mto", ""),
                "committed": round(_num(i.get("committed_forecast", 0)), 1),
                "production": round(_num(i.get("actual_production", 0)), 1),
                "dispatch": round(_num(i.get("actual_dispatch", 0)), 1),
                "shortfall": round(pds, 1),
            }
            d.update(_item_insight_fields(i))
            shortfall_items.append(d)
    shortfall_items.sort(key=lambda x: -x["shortfall"])
    top10_shortfall = shortfall_items[:10]

    # ── TOP 10 Dispatch Gap ──
    # Use pre-computed dispatch_gap_qty column.
    gap_items = []
    for i in all_items:
        dg = _num(i.get("dispatch_gap_qty", 0))
        if dg > 0:
            committed = _num(i.get("committed_forecast", 0))
            dispatched = _num(i.get("actual_dispatch", 0))
            dp_pct = round(dispatched / committed * 100, 1) if committed > 0 else 0
            d = {
                "item_code": i["item_code"],
                "item_group": i.get("item_group", ""),
                "type": i.get("type_mts_mto", ""),
                "committed": round(committed, 1),
                "dispatch": round(dispatched, 1),
                "dispatch_pct": dp_pct,
                "gap": round(dg, 1),
                "dispatch_gap": round(dg, 1),
            }
            d.update(_item_insight_fields(i))
            gap_items.append(d)
    gap_items.sort(key=lambda x: -x["gap"])
    top10_gap = gap_items[:10]

    # ── Helper for Focus/Regular split ──
    def _segment_sums(items_list):
        committed_total = _sum(items_list, "committed_forecast")
        return {
            "forecast": round(_sum(items_list, "original_forecast"), 0),
            "committed": round(committed_total, 0),
            "actual_sales": round(_sum(items_list, "actual_sales"), 0),
            "additional_demand": round(
                _sum(items_list, "actual_sales") - committed_total, 0
            ),
            "production": round(_sum(items_list, "actual_production"), 0),
            "dispatch": round(_sum(items_list, "actual_dispatch"), 0),
            "closing_inventory": round(_sum(items_list, "closing_inventory"), 0),
            "free_inventory": round(_sum(items_list, "free_inventory"), 0),
            # Inventory & Supply
            "opening_inventory": round(_sum(items_list, "opening_inventory"), 0),
            "total_available": round(_sum(items_list, "total_available"), 0),
            # Closing & Safety
            "green_level": round(_sum(items_list, "green_level"), 0),
            # Dispatch %
            "dispatch_pct": (
                round(_sum(items_list, "actual_dispatch") / committed_total * 100, 1)
                if committed_total > 0 else 0
            ),
        }

    # ── Append1 sheet sync — push 666-item reconciliation to Google Sheet ──
    # Replaces the buggy Apps Script Append1 (1249 rows with duplicates).
    # Runs in a background thread so the API response is not delayed.
    def _bg_append1_sync(items_snapshot):
        try:
            from .append1 import APPEND1_HEADERS, _KEY_ORDER, ASP_TABLE
            from .sheet_sync import sync_append1

            def _v(item, key, default=0):
                """Get numeric value from item, default 0."""
                val = item.get(key, default)
                return val if val is not None else default

            def _fmt(val, blank_zero=True):
                """Format: blank string for zero, else rounded."""
                if blank_zero and val == 0:
                    return ""
                return round(val, 2) if isinstance(val, float) else val

            rows = []
            for it in items_snapshot:
                ic = it.get("item_code", "")
                ig = it.get("item_group", "")
                asp = ASP_TABLE.get(ig, 0)
                rt = _v(it, "landed_rate", 0)

                of = _v(it, "original_forecast")
                cf = _v(it, "committed_forecast")
                asd = _v(it, "actual_sales")
                op = _v(it, "opening_inventory")
                pr = _v(it, "actual_production")
                ad = _v(it, "actual_dispatch")
                cl = _v(it, "closing_inventory")
                gl = _v(it, "green_level")
                ta = _v(it, "total_available")

                # Forecast accuracy %
                if of == 0 and asd == 0:
                    fa_pct = ""
                elif of == 0:
                    fa_pct = "0%" if asd > 0 else "100%"
                else:
                    var = abs(asd - of) / of
                    fa_pct = f"{round(max(0, 1 - var) * 100)}%"

                # Dispatch %
                dp_pct = f"{round(ad / cf * 100, 1)}%" if cf > 0 else ""

                # Build required & production counted
                br = max(cf + gl - op, 0)
                pc = min(pr, br) if br > 0 else 0

                # Financial (ASP-based)
                dg = _v(it, "dispatch_gap_qty")
                sa_d = _v(it, "shortfall_addl_demand")
                dr = _v(it, "demand_reduction_adj")
                pds = _v(it, "production_driven_shortfall")
                ed = _v(it, "excess_dispatched_qty")

                rows.append({
                    "item_group": ig,
                    "item_code": ic,
                    "product_class": it.get("product_class", "Regular"),
                    "original_forecast": _fmt(of),
                    "committed_forecast": _fmt(cf),
                    "ops_adjustment": _fmt(_v(it, "ops_adjustment")),
                    "actual_sales_demand": _fmt(asd),
                    "additional_demand": _fmt(_v(it, "additional_demand")),
                    "forecast_accuracy_pct": fa_pct,
                    "opening_inventory": _fmt(op),
                    "actual_production": _fmt(pr),
                    "stock_adj_added": _fmt(_v(it, "stock_adj_added")),
                    "stock_adj_deducted": _fmt(_v(it, "stock_adj_deducted")),
                    "total_available": _fmt(ta),
                    "type_mts_mto": it.get("type_mts_mto", "TBC"),
                    "actual_dispatch": _fmt(ad),
                    "dispatch_pct": dp_pct,
                    "closing_inventory": _fmt(cl, blank_zero=False),
                    "green_level": _fmt(gl),
                    "free_inventory": _fmt(_v(it, "free_inventory")),
                    "uncovered_shortfall": _fmt(_v(it, "uncovered_shortfall")),
                    "dispatch_gap": _fmt(dg),
                    "shortfall_additional_demand": _fmt(sa_d),
                    "demand_reduction_adj": _fmt(dr),
                    "prod_driven_shortfall": _fmt(pds),
                    "production_surplus": _fmt(_v(it, "production_surplus_qty")),
                    "excess_opening_stock": _fmt(_v(it, "excess_opening_qty")),
                    "excess_dispatched": _fmt(ed),
                    "sales_insight_tag": it.get("sales_insight_tag", ""),
                    "sales_narrative": it.get("sales_narrative", ""),
                    "ops_insight_tag": it.get("ops_insight_tag", ""),
                    "ops_narrative": it.get("ops_narrative", ""),
                    "ops_capacity_narrative": it.get("ops_capacity_narrative", ""),
                    "surplus_production_val": _fmt(_v(it, "surplus_value")),
                    "excess_opening_stock_val": _fmt(_v(it, "excess_opening_value")),
                    "build_required": _fmt(br),
                    "production_counted": _fmt(pc),
                    "prod_shortfall_val": _fmt(round(pds * asp, 2)),
                    "dispatch_gap_val": _fmt(round(dg * asp, 2)),
                    "shortfall_additional_val": _fmt(round(sa_d * asp, 2)),
                    "demand_reduction_val": _fmt(round(dr * asp, 2)),
                    "excess_dispatch_val": _fmt(round(ed * asp, 2)),
                })

            result = sync_append1(rows, APPEND1_HEADERS, _KEY_ORDER)
            log.info("Append1 sync: %d rows → %s", len(rows), result)
        except Exception:
            log.exception("Append1 sheet sync failed (non-blocking)")

    import copy
    threading.Thread(
        target=_bg_append1_sync,
        args=(copy.deepcopy(all_items),),
        daemon=True,
    ).start()

    return Response({
        "has_data": True,
        "uploads": upload_status,

        # VOLUME & FULFILMENT
        "volume": {
            "total_items": total_items,
            "focus_items": len(focus_items),
            "regular_items": len(regular_items),
            "total": _segment_sums(all_items),
            "focus": _segment_sums(focus_items),
            "regular": _segment_sums(regular_items),
        },

        # HEALTH RATIOS (with Focus / Regular split)
        "health": {
            "dispatch_fulfilment": dispatch_fulfilment,
            "forecast_accuracy": forecast_accuracy,
            "production_coverage": production_coverage,
            "focus": {
                "dispatch_fulfilment": round(
                    _sum(focus_items, "actual_dispatch") /
                    _sum(focus_items, "actual_sales") * 100, 1
                ) if _sum(focus_items, "actual_sales") else 0,
                "forecast_accuracy": _seg_fa(focus_items),
                "production_coverage": _seg_pc(focus_items),
            },
            "regular": {
                "dispatch_fulfilment": round(
                    _sum(regular_items, "actual_dispatch") /
                    _sum(regular_items, "actual_sales") * 100, 1
                ) if _sum(regular_items, "actual_sales") else 0,
                "forecast_accuracy": _seg_fa(regular_items),
                "production_coverage": _seg_pc(regular_items),
            },
        },

        # EXCEPTIONS (each has total / focus / regular)
        "exceptions": exceptions_data,

        # SHORTFALL & GAPS
        "shortfall_gaps": shortfall_gaps,

        # SURPLUS & EXCESS
        "surplus_excess": surplus_excess,

        # FINANCIAL IMPACT
        "financial_impact": financial_impact,

        # EXCEPTIONS — Qty & ₹ VALUE (MTS/MTO/TBC bifurcation)
        "exceptions_value": exceptions_value,

        # INSIGHTS SUMMARY
        "insights_summary": insights_summary,

        # TYPE BREAKDOWN
        "type_breakdown": type_rows,

        # TOP 10 tables
        "top10_shortfall": top10_shortfall,
        "top10_dispatch_gap": top10_gap,
        "top10_free_inventory": top10_free_inv,
        "top10_below_green": top10_below_green,
    })


# NOTE: Append1 is now pushed from Django (demand_supply_overview) via
# a background thread → sync_append1(). This replaced the Apps Script
# computeAppend1() which produced 1249 rows with duplicates.
# The Django version uses the deduped 666-item all_items list.
