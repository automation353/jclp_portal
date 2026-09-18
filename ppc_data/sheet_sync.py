"""Google Sheet sync — push PPC pipeline outputs to n8n → Google Sheets.

This module pushes key outputs from the PPC pipeline to n8n webhooks,
which then write the data to the Google Sheets that the team reads daily.

Four target sheets:
  1. PPC Planning Sheet (CP Req, RM Req, Quantity) — existing, via ppc app
  2. PPC Pipeline Sheet — BOM explosion, shortages, adherence, scorecard
  3. TCS ION Sheet — ERP data uploaded manually from the portal
  4. PPC Data Sheet — ALL master, demand, MPS, R3SS uploads (database mirror)

The sync is optional — pipeline outputs always live in Django first.
The sheet sync is a secondary output for team visibility during transition.

Environment variables:
  JCLP_PPC_PIPELINE_WEBHOOK — n8n webhook URL for pipeline outputs
  JCLP_PPC_SHEET_WEBHOOK    — n8n webhook URL for RM CP Packing (existing)
  JCLP_TCS_ION_WEBHOOK      — n8n webhook URL for TCS ION ERP data
  JCLP_PPC_DATA_WEBHOOK     — n8n webhook URL for master/plan data
"""

import datetime
import logging
import os

import requests

from .field_maps.helpers import num0

log = logging.getLogger(__name__)


def _pipeline_webhook():
    return os.environ.get("JCLP_PPC_PIPELINE_WEBHOOK", "").strip()


def _ppc_sheet_webhook():
    return os.environ.get("JCLP_PPC_SHEET_WEBHOOK", "").strip()


def _post_to_webhook(url, payload, label="sheet sync", retries=3, backoff=5):
    """POST JSON to an n8n webhook with retry on 502/503. Returns result dict."""
    if not url:
        return {"attempted": False, "reason": "webhook not configured"}

    import time as _time
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=180)
            if 200 <= resp.status_code < 300:
                return {"attempted": True, "ok": True, "http_status": resp.status_code}
            if resp.status_code in (502, 503) and attempt < retries:
                log.warning("%s got %d, retry %d/%d in %ds",
                            label, resp.status_code, attempt, retries, backoff)
                _time.sleep(backoff * attempt)
                continue
            return {
                "attempted": True, "ok": False,
                "http_status": resp.status_code,
                "body_preview": (resp.text or "")[:300],
            }
        except Exception as exc:
            if attempt < retries:
                log.warning("%s error, retry %d/%d: %s", label, attempt, retries, exc)
                _time.sleep(backoff * attempt)
                continue
            log.exception("%s failed: %s", label, exc)
            return {"attempted": True, "ok": False, "error": str(exc)}


# ── ERP _LOAD_LOG → Sheet ────────────────────────────────────────


def sync_erp_load_log(batch, *, sync_result=None, rows_rejected=0):
    """Append one row to the _LOAD_LOG tab in the TCS ION Google Sheet.

    Called after every ERP upload — whether it succeeded or failed.
    The _LOAD_LOG tab is append-only: the n8n workflow must NOT clear it.

    The payload uses `append_only: true` so the n8n Switch node can route
    this to an append-without-clear branch.
    """
    from django.utils import timezone

    url = _tcs_ion_webhook()
    if not url:
        return {"attempted": False, "reason": "JCLP_TCS_ION_WEBHOOK not set"}

    ok = bool(sync_result and sync_result.get("ok"))
    load_status = "OK" if ok else "FAILED"
    if batch.parse_error:
        load_status = "PARSE_ERROR"

    log_row = {
        "Report Key": batch.table_key,
        "Tab Name": _ERP_TAB_NAMES.get(batch.table_key, batch.table_key),
        "Source File": batch.original_filename,
        "Rows Received": batch.row_count + rows_rejected,
        "Rows Accepted": batch.row_count,
        "Rows Rejected": rows_rejected,
        "Load Timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ERP Timestamp": (batch.notes or "").replace("ERP pull at ", ""),
        "Status": load_status,
        "Batch ID": batch.pk,
        "Uploader": str(batch.uploader) if batch.uploader else "system",
    }

    payload = {
        "report_key": "_load_log",
        "tab_name": "_LOAD_LOG",
        "append_only": True,
        "headers": list(log_row.keys()),
        "rows": [log_row],
        "row_count": 1,
        "_meta": {
            "batch_id": batch.pk,
            "source": "ppc_data_portal",
        },
    }

    return _post_to_webhook(url, payload, "ERP _LOAD_LOG sync")


# ── BOM Explosion → Sheet ────────────────────────────────────────


def sync_bom_to_sheet(release):
    """Push BOM explosion results to Google Sheets via n8n.

    Sends three tabs worth of data:
      - bom_components: all components with day-wise requirements
      - shortages: components with insufficient stock
      - summary: overview tiles
    """
    from .models import PPCDataRow, PPCUploadBatch

    url = _pipeline_webhook()
    if not url:
        return {"attempted": False, "reason": "JCLP_PPC_PIPELINE_WEBHOOK not set"}

    # Load BOM requirement
    bom_batch = (
        PPCUploadBatch.objects
        .filter(
            table_key="bom_requirement",
            notes__contains=f"release_id={release.pk}",
        )
        .order_by("-uploaded_at")
        .first()
    )
    if not bom_batch:
        return {"attempted": False, "reason": "no BOM explosion found"}

    bom_rows = list(bom_batch.rows.values_list("data", flat=True))

    # Load shortages
    alloc_batch = (
        PPCUploadBatch.objects
        .filter(
            table_key="material_shortage",
            notes__contains=f"release_id={release.pk}",
        )
        .order_by("-uploaded_at")
        .first()
    )

    shortage_rows = []
    if alloc_batch:
        shortage_rows = [
            r for r in alloc_batch.rows.values_list("data", flat=True)
            if r.get("has_shortage")
        ]

    # Flatten BOM rows for sheet (no nested dicts)
    flat_bom = []
    for r in bom_rows:
        row = {
            "Component": r.get("component_item", ""),
            "Type": r.get("component_type", ""),
            "UOM": r.get("uom", ""),
            "Total Requirement": r.get("total_requirement", 0),
        }
        # Add day columns as flat keys
        for d, q in sorted(r.get("days", {}).items()):
            row[d] = q
        flat_bom.append(row)

    # Flatten shortage rows
    flat_short = []
    for r in shortage_rows:
        flat_short.append({
            "Component": r.get("component_item", ""),
            "Type": r.get("component_type", ""),
            "Stock": r.get("available_stock", 0),
            "Required": r.get("total_requirement", 0),
            "Allocated": r.get("total_allocated", 0),
            "Shortage": r.get("total_shortage", 0),
        })

    payload = {
        "type": "bom_explosion",
        "plan_month": release.plan_month,
        "release_number": release.release_number,
        "bom_components": {
            "rows": flat_bom,
            "row_count": len(flat_bom),
        },
        "shortages": {
            "rows": flat_short,
            "row_count": len(flat_short),
        },
        "_meta": {
            "release_id": release.pk,
            "source": "ppc_data_pipeline",
        },
    }

    return _post_to_webhook(url, payload, "BOM sheet sync")


# ── Adherence / Scorecard → Sheet ────────────────────────────────


def sync_scorecard_to_sheet(release):
    """Push adherence scorecard to Google Sheets via n8n."""
    from django.db.models import Sum

    from .models import PPCDataRow, PPCProductionEntry, PPCRejectionEntry

    url = _pipeline_webhook()
    if not url:
        return {"attempted": False, "reason": "JCLP_PPC_PIPELINE_WEBHOOK not set"}

    # Plan data
    plan_rows = list(
        PPCDataRow.objects
        .filter(batch=release.snapshot_batch)
        .values_list("data", flat=True)
    )

    from collections import defaultdict
    section_plan = defaultdict(float)
    for r in plan_rows:
        sec = (r.get("section") or "Unknown").upper()
        section_plan[sec] += num0(r.get("total_plan"))

    total_planned = sum(section_plan.values())

    # Actual production
    section_actual = defaultdict(float)
    for e in PPCProductionEntry.objects.filter(release=release):
        section_actual[e.section.upper()] += e.produced_qty

    total_actual = sum(section_actual.values())

    # Rejections
    total_rejected = (
        PPCRejectionEntry.objects
        .filter(
            date__gte=f"{release.plan_month}-01",
            date__lte=f"{release.plan_month}-31",
        )
        .aggregate(total=Sum("rejected_qty"))["total"]
    ) or 0

    # Build section rows for sheet
    sections = []
    for sec in sorted(section_plan):
        p = section_plan[sec]
        a = section_actual.get(sec, 0)
        adh = (a / p * 100) if p > 0 else 0
        sections.append({
            "Section": sec,
            "Planned": round(p, 1),
            "Actual": round(a, 1),
            "Adherence %": round(adh, 1),
            "Gap": round(p - a, 1),
        })

    overall_adh = (total_actual / total_planned * 100) if total_planned > 0 else 0
    rej_pct = (total_rejected / total_actual * 100) if total_actual > 0 else 0

    payload = {
        "type": "scorecard",
        "plan_month": release.plan_month,
        "release_number": release.release_number,
        "overall": {
            "Planned": round(total_planned, 1),
            "Actual": round(total_actual, 1),
            "Adherence %": round(overall_adh, 1),
            "Backlog": round(max(0, total_planned - total_actual), 1),
            "Rejected": round(total_rejected, 1),
            "Rejection %": round(rej_pct, 1),
        },
        "sections": {
            "rows": sections,
            "row_count": len(sections),
        },
        "_meta": {
            "release_id": release.pk,
            "source": "ppc_data_pipeline",
        },
    }

    return _post_to_webhook(url, payload, "Scorecard sheet sync")


# ── RM CP Packing → existing PPC Sheet ───────────────────────────


def sync_material_to_ppc_sheet(release):
    """Push BOM explosion output in the same format as the old RM CP Packing
    upload, so the existing PPC Planning Google Sheet stays populated.

    This bridges L7 (new pipeline) → existing Google Sheet (transition).
    Uses the same webhook as ppc/api.py (JCLP_PPC_SHEET_WEBHOOK).
    """
    from .models import PPCDataRow, PPCUploadBatch

    url = _ppc_sheet_webhook()
    if not url:
        return {"attempted": False, "reason": "JCLP_PPC_SHEET_WEBHOOK not set"}

    # Load BOM requirement rows
    bom_batch = (
        PPCUploadBatch.objects
        .filter(
            table_key="bom_requirement",
            notes__contains=f"release_id={release.pk}",
        )
        .order_by("-uploaded_at")
        .first()
    )
    if not bom_batch:
        return {"attempted": False, "reason": "no BOM explosion found"}

    bom_rows = list(bom_batch.rows.values_list("data", flat=True))

    # Split into CP Req, RM Req, and Quantity Sheet
    cp_rows = []
    rm_rows = []
    qty_rows = []

    for r in bom_rows:
        comp_type = (r.get("component_type") or "RM").upper()
        flat = {
            "BOM Code": "",  # Not available from BOM explosion
            "Item Code": r.get("component_item", ""),
            "BOM Qty": "",
            "Qty in Nos": "",
            "Qty (Base UOM)": r.get("total_requirement", 0),
            "UOM": r.get("uom", ""),
            "Part Description": "",
        }

        if comp_type == "CP":
            cp_rows.append(flat)
        elif comp_type in ("RM", ""):
            rm_rows.append(flat)
        else:
            # PM and others go to quantity sheet
            qty_rows.append({
                "Item Code": r.get("component_item", ""),
                "Description": "",
                "UOM": r.get("uom", ""),
                "Qty (Base UOM)": r.get("total_requirement", 0),
                "qty per kg": "",
                "Qty in nos (ERP)": "",
                "Reqd Qty": r.get("total_requirement", 0),
                "Qty in nos (Correction)": "",
            })

    payload = {
        "filename": f"BOM Explosion — {release.plan_month}#{release.release_number}",
        "cp_req": {"row_count": len(cp_rows), "headers": list(cp_rows[0].keys()) if cp_rows else [], "rows": cp_rows},
        "rm_req": {"row_count": len(rm_rows), "headers": list(rm_rows[0].keys()) if rm_rows else [], "rows": rm_rows},
        "quantity_sheet": {"row_count": len(qty_rows), "headers": list(qty_rows[0].keys()) if qty_rows else [], "rows": qty_rows},
        "_meta": {
            "original_filename": f"BOM Explosion {release.plan_month}",
            "uploader": "ppc_data_pipeline",
            "notes": f"Auto-generated from release #{release.release_number}",
        },
    }

    return _post_to_webhook(url, payload, "RM CP Packing sheet sync")


# ── TCS ION ERP data → Google Sheet ─────────────────────────────

# Human-readable tab name for each ERP report key
_ERP_TAB_NAMES = {
    "erp_item_master":      "Item Master",
    "erp_bom":              "BOM",
    "erp_fg_stock":         "FG Stock",
    "erp_fg_stock_open":    "FG Stock Open",
    "erp_cp_stock":         "CP Stock",
    "erp_rm_stock":         "RM Stock",
    "erp_pm_stock":         "PM Stock",
    "erp_consumables":      "Consumables",
    "erp_prod_fg":          "Production FG",
    "erp_prod_semi":        "Production Semi",
    "erp_dispatch":         "Dispatch",
    "erp_forecast":         "Forecast",
    "erp_sales_orders":     "Sales Orders",
    "erp_pending_po":       "Pending PO",
    "erp_pending_pr":       "Pending PR",
    "erp_material_issue":   "Material Issue",
    "erp_item_cost":        "Item Cost",
    "erp_fg_ageing":        "FG Ageing",
}


def _tcs_ion_webhook():
    return os.environ.get("JCLP_TCS_ION_WEBHOOK", "").strip()


def sync_erp_to_sheet(batch):
    """Push a just-uploaded ERP batch to the TCS ION Google Sheet.

    Called after a successful ERP file upload. The n8n workflow receives
    the report_key + flat rows, clears the matching tab, and writes fresh data.

    Non-blocking: failures are logged but never break the upload API.
    """
    url = _tcs_ion_webhook()
    if not url:
        return {"attempted": False, "reason": "JCLP_TCS_ION_WEBHOOK not set"}

    table_key = batch.table_key
    tab_name = _ERP_TAB_NAMES.get(table_key)
    if not tab_name:
        return {"attempted": False, "reason": f"no tab mapping for {table_key}"}

    # Load rows and convert to header-keyed dicts for the sheet
    from .field_maps.erp import get_erp_field_map
    from .models import PPCDataRow

    field_map = get_erp_field_map(table_key)
    rows_raw = list(
        PPCDataRow.objects
        .filter(batch=batch)
        .order_by("sr_no")
        .values_list("data", flat=True)
    )

    # Re-key from internal names back to human-readable Excel headers
    flat_rows = []
    if field_map:
        headers = list(field_map.values())
        for r in rows_raw:
            row = {}
            for internal_key, header in field_map.items():
                val = r.get(internal_key, "")
                row[header] = val
            flat_rows.append(row)
    else:
        headers = list(rows_raw[0].keys()) if rows_raw else []
        flat_rows = rows_raw

    payload = {
        "report_key": table_key,
        "tab_name": tab_name,
        "headers": headers,
        "rows": flat_rows,
        "row_count": len(flat_rows),
        "_meta": {
            "batch_id": batch.pk,
            "uploaded_at": batch.uploaded_at.isoformat() if batch.uploaded_at else "",
            "uploader": str(batch.uploader) if batch.uploader else "system",
            "original_filename": batch.original_filename,
            "source": "ppc_data_portal",
        },
    }

    return _post_to_webhook(url, payload, f"TCS ION sync ({tab_name})")


# ── L0 Masters → MASTERS Google Sheet (spec §1, sheet #2) ─────
#
# Spec §1: "One workbook per stage." L0 masters go to the MASTERS sheet,
# with tabs named W1_01 through W1_17. L2/L3/L4 data stays in PPC Data.

_MASTER_TAB_NAMES = {
    "item_master":         "W1_01",    # Item master
    "family_hierarchy":    "W1_02",    # Product group & family hierarchy
    "site_plant_section":  "W1_03",    # Site, plant, section, line
    "route_master":        "W1_04",    # Route master (process per family)
    "operation_stage_map": "W1_05",    # Operation → stage map
    "capacity_ppp":        "W1_06",    # Capacity & PPP master
    "machine_master":      "W1_07",    # Machine master
    "batch_ebq":           "W1_08",    # Batch size & EBQ
    "lead_time":           "W1_09",    # Lead time master
    "working_calendar":    "W1_10",    # Working-day calendar
    "bom_master":          "W1_11",    # BOM master
    "part_engineering":    "W1_12",    # Part engineering attributes
    "customer_part":       "W1_13",    # Customer & customer-part
    "stock_policy":        "W1_14",    # Stock policy (green levels)
    "packing_spec":        "W1_15",    # Packing specification
    "rate_asp":            "W1_16",    # Rate & ASP
    "reason_codes":        "W1_17",    # Reason codes
}


def _ppc_masters_webhook():
    return os.environ.get("JCLP_PPC_MASTERS_WEBHOOK", "").strip()


def sync_master_to_sheet(batch):
    """Push a just-uploaded L0 master batch to the MASTERS Google Sheet.

    The MASTERS sheet has tabs W1_01–W1_17, one per spec master table.
    The n8n workflow receives the table_key + flat rows, clears the
    matching tab, and writes fresh data.

    Falls back to the PPC Data sheet if MASTERS webhook isn't configured
    yet (transition period).

    Non-blocking: failures are logged but never break the upload API.
    """
    table_key = batch.table_key
    tab_name = _MASTER_TAB_NAMES.get(table_key)
    if not tab_name:
        return {"attempted": False, "reason": f"not an L0 master: {table_key}"}

    # Try MASTERS webhook first; fall back to PPC Data during transition
    url = _ppc_masters_webhook()
    target_sheet = "MASTERS"
    if not url:
        url = _ppc_data_webhook()
        target_sheet = "PPC Data (fallback)"
        if not url:
            return {"attempted": False, "reason": "neither MASTERS nor DATA webhook set"}

    from .field_maps import REGISTRY
    from .models import PPCDataRow

    reg_entry = REGISTRY.get(table_key)
    field_map = reg_entry["field_map"] if reg_entry else None

    rows_raw = list(
        PPCDataRow.objects
        .filter(batch=batch)
        .order_by("sr_no")
        .values_list("data", flat=True)
    )

    # Re-key from internal names back to human-readable Excel headers
    flat_rows = []
    if field_map:
        headers = list(field_map.values())
        for r in rows_raw:
            row = {}
            for internal_key, header in field_map.items():
                val = r.get(internal_key, "")
                row[header] = val
            flat_rows.append(row)
    else:
        headers = list(rows_raw[0].keys()) if rows_raw else []
        flat_rows = rows_raw

    # Human-readable display name for logging
    display_name = _DATA_TAB_NAMES.get(table_key, table_key)

    payload = {
        "report_key": table_key,
        "tab_name": tab_name,
        "headers": headers,
        "rows": flat_rows,
        "row_count": len(flat_rows),
        "_meta": {
            "batch_id": batch.pk,
            "uploaded_at": batch.uploaded_at.isoformat() if batch.uploaded_at else "",
            "uploader": str(batch.uploader) if batch.uploader else "system",
            "original_filename": batch.original_filename,
            "source": "ppc_data_portal",
            "display_name": display_name,
        },
    }

    return _post_to_webhook(url, payload, f"MASTERS sync ({tab_name} / {display_name})")


# ── L2+ Plan data → PPC Data Google Sheet ─────────────────────

# Human-readable tab name for each table_key.
# L0 masters now go to the MASTERS sheet above. This dict is kept
# complete for backward compatibility (display names, fallback routing).
_DATA_TAB_NAMES = {
    # L0 masters — display names (used by sync_master_to_sheet for logging)
    "item_master":        "Item Master",
    "family_hierarchy":   "Family Hierarchy",
    "route_master":       "Route Master",
    "operation_stage_map": "Stage Map",
    "capacity_ppp":       "Capacity PPP",
    "machine_master":     "Machine Master",
    "batch_ebq":          "Batch EBQ",
    "lead_time":          "Lead Time",
    "bom_master":         "BOM Master",
    "part_engineering":   "Part Engineering",
    "customer_part":      "Customer Part",
    "stock_policy":       "Stock Policy",
    "packing_spec":       "Packing Spec",
    "rate_asp":           "Rate ASP",
    # L2 demand
    "demand_freeze":      "Demand Freeze",
    "demand_history":     "Demand History",
    # L3 MPS
    "mps_schedule":       "MPS Schedule",
    "mps_history":        "MPS History",
    "planning_calendar":  "CAL_WEEKS",
    # L4 R3SS
    "r3ss_plan":          "R3SS",
    "r3ss_summary":       "R3SS Summary",
    "r3ss_map":           "MAP",
    "r3ss_control":       "CONTROL",
    # L4 R3SS import tabs
    "r3ss_imp_master":    "_IMP_MASTER",
    "r3ss_imp_demand":    "_IMP_DEMAND",
    "r3ss_imp_fg":        "_IMP_FG",
    "r3ss_imp_fg_open":   "_IMP_FG_OPEN",
    "r3ss_imp_production":"_IMP_DJR",
    "r3ss_imp_dispatch":  "_IMP_INVOICE",
    # R3SS source files (uploaded monthly) — tab names match source file names
    "fg_stock_statement": "FG",
    "dpr_production":     "DPR all Plant",
    "fg_dispatch":        "FG Issue qty",
    "mps_schedule_form":  "Master",
    # L6 Release
    "release_rows":       "RELEASE_SNAPSHOT",
}


def _ppc_data_webhook():
    return os.environ.get("JCLP_PPC_DATA_WEBHOOK", "").strip()


_R3SS_SOURCE_KEYS = frozenset({
    "fg_stock_statement", "dpr_production", "fg_dispatch", "mps_schedule_form",
    "demand_freeze",
})


def sync_upload_to_sheet(batch):
    """Push a just-uploaded batch to the appropriate Google Sheet.

    Routing:
      - L0 masters → MASTERS sheet (W1_XX tabs) via sync_master_to_sheet()
      - R3SS source files → R3SS sheet via ppc-r3ss webhook
      - L2/L3/L4 data → PPC Data sheet via ppc-data webhook

    Non-blocking: failures are logged but never break the upload API.
    """
    table_key = batch.table_key

    # Route L0 masters to the MASTERS sheet
    if table_key in _MASTER_TAB_NAMES:
        return sync_master_to_sheet(batch)

    # Route R3SS source files to the R3SS sheet
    if table_key in _R3SS_SOURCE_KEYS:
        url = _r3ss_webhook()
        if not url:
            url = _ppc_data_webhook()
        if not url:
            return {"attempted": False, "reason": "neither R3SS nor DATA webhook set"}
    else:
        url = _ppc_data_webhook()
        if not url:
            return {"attempted": False, "reason": "JCLP_PPC_DATA_WEBHOOK not set"}

    tab_name = _DATA_TAB_NAMES.get(table_key)
    if not tab_name:
        return {"attempted": False, "reason": f"no tab mapping for {table_key}"}

    from .field_maps import REGISTRY
    from .models import PPCDataRow

    reg_entry = REGISTRY.get(table_key)
    field_map = reg_entry["field_map"] if reg_entry else None

    rows_raw = list(
        PPCDataRow.objects
        .filter(batch=batch)
        .order_by("sr_no")
        .values_list("data", flat=True)
    )

    # R3SS source tabs: send raw snake_case keys (Apps Script expects them)
    # Non-R3SS tabs: re-key to human-readable Excel headers for browsing
    flat_rows = []
    if table_key in _R3SS_SOURCE_KEYS:
        headers = list(rows_raw[0].keys()) if rows_raw else []
        flat_rows = rows_raw
    elif field_map:
        headers = list(field_map.values())
        for r in rows_raw:
            row = {}
            for internal_key, header in field_map.items():
                val = r.get(internal_key, "")
                row[header] = val
            if table_key == "r3ss_plan" and "days" in r:
                for day_key, day_val in sorted(r["days"].items()):
                    row[day_key] = day_val
                if "days" not in field_map:
                    row.pop("days", None)
            flat_rows.append(row)
        if table_key == "r3ss_plan" and rows_raw:
            first_days = rows_raw[0].get("days", {})
            headers = headers + sorted(first_days.keys())
    else:
        headers = list(rows_raw[0].keys()) if rows_raw else []
        flat_rows = rows_raw

    meta = {
        "batch_id": batch.pk,
        "uploaded_at": batch.uploaded_at.isoformat() if batch.uploaded_at else "",
        "uploader": str(batch.uploader) if batch.uploader else "system",
        "original_filename": batch.original_filename,
        "source": "ppc_data_portal",
    }

    UPLOAD_CHUNK = 1000
    if len(flat_rows) <= UPLOAD_CHUNK:
        payload = {
            "action": "write_tab",
            "report_key": table_key,
            "tab_name": tab_name,
            "headers": headers,
            "rows": flat_rows,
            "row_count": len(flat_rows),
            "_meta": meta,
        }
        return _post_to_webhook(url, payload, f"PPC data sync ({tab_name})")

    total_chunks = (len(flat_rows) + UPLOAD_CHUNK - 1) // UPLOAD_CHUNK
    result = {}
    for ci in range(total_chunks):
        chunk = flat_rows[ci * UPLOAD_CHUNK : (ci + 1) * UPLOAD_CHUNK]
        payload = {
            "action": "write_tab",
            "report_key": table_key,
            "tab_name": tab_name,
            "headers": headers,
            "rows": chunk,
            "row_count": len(chunk),
            "chunk_index": ci,
            "total_chunks": total_chunks,
            "append": ci > 0,
            "_meta": meta,
        }
        label = f"PPC data sync ({tab_name} chunk {ci+1}/{total_chunks})"
        result = _post_to_webhook(url, payload, label)
        if not result.get("ok"):
            log.error("%s chunk %d failed: %s", tab_name, ci, result)
            break
    return result


# ── Raw Excel → n8n passthrough (no Django parsing) ─────────
# For R3SS source files, read raw sheets and POST directly to n8n.
# n8n handles routing; Apps Script writes to the Google Sheet.

_RAW_SHEET_CONFIG = {
    "demand_freeze": {
        "sheets": ["Initial Demand", "Additional W1", "Additional W2",
                    "Reduced Demand"],
        "tab_name": "Demand Freeze",
    },
    "mps_schedule_form": {
        "sheets": ["Schedule Form"],
        "tab_name": "Master",
    },
    "fg_stock_statement": {
        # First two sheets ("main report", "Search Criteria") are empty/meta;
        # the real data is the "Stock Statment Valuation Report" sheet, which is
        # a dynamic/pivot sheet — needs read_only=False to materialise values.
        "sheets": ["Stock Statment Valuation Report"],
        "tab_name": "FG",
        "read_only": False,
    },
    "dpr_production": {
        "sheets": ["Pivot1"],
        "tab_name": "DPR all Plant",
        "read_only": False,
    },
    "fg_dispatch": {
        "sheets": ["Pivot1"],
        "tab_name": "FG Issue qty",
        "read_only": False,
    },
    "monitoring": {
        # Special-cased in sync_raw_to_sheet: builds one "Monitoring" tab with
        # item_code + green_level (per ERP) + ebq (per family, applied to all
        # items in the family).
        "sheets": ["Raw Data", "Family Group"],
        "tab_name": "Monitoring",
    },
}


def _read_raw_sheets(file_path, sheet_names=None, read_only=True):
    """Read raw cell values from an Excel file.

    Returns list of dicts: [{sheet, headers, rows}].
    Each row is a dict keyed by header name.
    Use read_only=False for pivot tables.
    """
    from openpyxl import load_workbook

    wb = load_workbook(file_path, data_only=True, read_only=read_only)
    results = []

    targets = sheet_names if sheet_names else [wb.sheetnames[0]]
    for sn in targets:
        # Find matching sheet (case-insensitive partial match)
        matched = None
        for actual in wb.sheetnames:
            if sn.lower().strip() in actual.lower().strip():
                matched = actual
                break
        if not matched:
            log.warning("Sheet '%s' not found in %s, skipping", sn, file_path)
            continue

        ws = wb[matched]
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            continue

        # Find header row (row with the MOST non-empty cells in first 10 rows)
        header_idx = 0
        best_count = 0
        for i, row in enumerate(all_rows[:10]):
            non_empty = sum(1 for c in row if c is not None and str(c).strip())
            if non_empty > best_count:
                best_count = non_empty
                header_idx = i

        raw_headers = all_rows[header_idx]
        headers = []
        for h in raw_headers:
            s = str(h).strip() if h is not None else ""
            headers.append(s)

        rows = []
        for i in range(header_idx + 1, len(all_rows)):
            vals = all_rows[i]
            has_data = False
            row = {}
            for j, hdr in enumerate(headers):
                if not hdr:
                    continue
                v = vals[j] if j < len(vals) else None
                if v is not None and str(v).strip():
                    has_data = True
                if isinstance(v, (datetime.datetime, datetime.date)):
                    v = v.isoformat()
                row[hdr] = v if v is not None else ""
            if has_data:
                rows.append(row)

        results.append({
            "sheet": matched,
            "headers": [h for h in headers if h],
            "rows": rows,
        })

    wb.close()
    return results


def _build_demand_rows(file_path):
    """Normalise the irregular forecast workbook into one clean row per ERP code.

    The forecast file has 4 differently-shaped sheets (Initial Demand,
    Additional W1/W2, Reduced Demand) with title rows, merged cells and summary
    rows — a dumb cell-merge scrambles the columns. We use the forecast parser
    to pull {item_code, qty, txn_type} and aggregate to fixed columns so the
    Demand Freeze tab is always aligned. The R3SS math still lives in Apps
    Script; this only makes the demand tab readable.
    """
    from .parsers import forecast_demand

    parsed = forecast_demand.parse(file_path)
    agg = {}
    for r in parsed:
        ic = str(r.get("item_code") or "").strip().upper()
        if not ic:
            continue
        a = agg.setdefault(ic, {"initial": 0.0, "additional": 0.0, "reduced": 0.0})
        qty = 0.0
        try:
            qty = float(r.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        t = (r.get("txn_type") or "").upper()
        if t == "INITIAL":
            a["initial"] += qty
        elif t == "ADDITION":
            a["additional"] += qty
        elif t == "REDUCTION":
            a["reduced"] += qty

    rows = []
    for ic in sorted(agg):
        a = agg[ic]
        rows.append({
            "item_code": ic,
            "initial": round(a["initial"], 2),
            "additional": round(a["additional"], 2),
            "reduced": round(a["reduced"], 2),
            "total": round(a["initial"] + a["additional"] - a["reduced"], 2),
        })
    return rows


def _build_monitoring_rows(file_path):
    """Build one clean Monitoring row per ERP code: item_code, green_level, ebq.

    Green Level is per ERP code (Monitoring "Raw Data" sheet). EBQ is per family
    (Monitoring "Family Group" sheet); each item inherits its family's EBQ.
    """
    from openpyxl import load_workbook

    wb = load_workbook(file_path, data_only=True, read_only=True)

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    # ── Family -> EBQ from "Family Group" ──
    fam_ebq = {}
    if "Family Group" in wb.sheetnames:
        rows = list(wb["Family Group"].iter_rows(values_only=True))
        # header row = the one containing "Family" and "EBQ"
        hi = 0
        for i, r in enumerate(rows[:8]):
            cells = [str(c).strip().lower() if c is not None else "" for c in r]
            if "family" in cells and "ebq" in cells:
                hi = i
                break
        hdr = [str(c).strip() if c is not None else "" for c in rows[hi]]
        fam_i = next((j for j, h in enumerate(hdr) if h.lower() == "family"), None)
        ebq_i = next((j for j, h in enumerate(hdr) if h.lower() == "ebq"), None)
        if fam_i is not None and ebq_i is not None:
            for r in rows[hi + 1:]:
                fam = str(r[fam_i]).strip().upper() if fam_i < len(r) and r[fam_i] is not None else ""
                if fam and fam not in fam_ebq:
                    fam_ebq[fam] = _num(r[ebq_i]) if ebq_i < len(r) else 0.0

    # ── ERP code -> green level (+ family) from "Raw Data" ──
    out = {}
    if "Raw Data" in wb.sheetnames:
        rows = list(wb["Raw Data"].iter_rows(values_only=True))
        hi = 0
        for i, r in enumerate(rows[:8]):
            if any(c and "green level" in str(c).lower() for c in r):
                hi = i
                break
        hdr = [str(c).strip() if c is not None else "" for c in rows[hi]]
        def col(name):
            return next((j for j, h in enumerate(hdr) if h.lower() == name.lower()), None)
        erp_i = col("ERP Code")
        gl_i = col("Green Level")
        fam_i = col("Family")
        if erp_i is not None:
            for r in rows[hi + 1:]:
                ic = str(r[erp_i]).strip().upper() if erp_i < len(r) and r[erp_i] is not None else ""
                if not ic or ic == "0" or ic in out:
                    continue
                gl = _num(r[gl_i]) if gl_i is not None and gl_i < len(r) else 0.0
                fam = str(r[fam_i]).strip().upper() if fam_i is not None and fam_i < len(r) and r[fam_i] is not None else ""
                out[ic] = {
                    "item_code": ic,
                    "green_level": round(gl, 2),
                    "ebq": round(fam_ebq.get(fam, 0.0), 2),
                }
    wb.close()
    return [out[k] for k in sorted(out)]


def sync_raw_to_sheet(file_path, table_key, original_filename, uploader="system"):
    """Read raw Excel file and POST directly to n8n → Apps Script.

    Most R3SS source files are a straight raw passthrough. Two exceptions are
    normalised first: the forecast file (demand_freeze) and Monitoring
    (green level + EBQ), whose sheets are too irregular to pass through raw.
    Returns {ok, sheets_sent, total_rows} or error dict.
    """
    config = _RAW_SHEET_CONFIG.get(table_key)
    if not config:
        return {"ok": False, "error": f"no raw config for {table_key}"}

    url = _r3ss_webhook()
    if not url:
        url = _ppc_data_webhook()
    if not url:
        return {"ok": False, "error": "no webhook configured"}

    # ── Demand / Monitoring: normalise to fixed aligned columns ──
    _NORMALISED = {
        "demand_freeze": (_build_demand_rows,
                          ["item_code", "initial", "additional", "reduced", "total"]),
        "monitoring": (_build_monitoring_rows,
                       ["item_code", "green_level", "ebq"]),
    }
    if table_key in _NORMALISED:
        builder, headers = _NORMALISED[table_key]
        try:
            all_rows = builder(file_path)
        except Exception as exc:
            log.exception("Normalise failed for %s (%s)", table_key, file_path)
            return {"ok": False, "error": str(exc)}
        payload = {
            "action": "write_tab",
            "report_key": table_key,
            "tab_name": config["tab_name"],
            "headers": headers,
            "rows": all_rows,
            "row_count": len(all_rows),
            "_meta": {
                "source": "ppc_portal_demand_norm",
                "original_filename": original_filename,
                "uploader": uploader,
            },
        }
        result = _post_to_webhook(url, payload, f"demand {config['tab_name']}")
        return {
            "ok": result.get("ok", False),
            "sheets_sent": 1,
            "total_rows": len(all_rows),
            "tab_name": config["tab_name"],
            "result": result,
        }

    try:
        sheet_data = _read_raw_sheets(
            file_path, config["sheets"],
            read_only=config.get("read_only", True),
        )
    except Exception as exc:
        log.exception("Raw sheet read failed for %s", file_path)
        return {"ok": False, "error": str(exc)}

    if not sheet_data:
        return {"ok": False, "error": "no sheets read from file"}

    # Merge all sheets into one payload for the tab. Backfill every row with the
    # full header set so n8n's auto-map writes consistent, aligned columns
    # (heterogeneous keys are what corrupted the tab before).
    all_rows = []
    all_headers = set()
    for sd in sheet_data:
        all_headers.update(sd["headers"])
    all_headers.add("_source_sheet")
    headers = sorted(all_headers)

    for sd in sheet_data:
        sheet_name = sd["sheet"]
        for r in sd["rows"]:
            row = {h: r.get(h, "") for h in headers}
            row["_source_sheet"] = sheet_name
            all_rows.append(row)

    payload = {
        "action": "write_tab",
        "report_key": table_key,
        "tab_name": config["tab_name"],
        "headers": headers,
        "rows": all_rows,
        "row_count": len(all_rows),
        "_meta": {
            "source": "ppc_portal_raw",
            "original_filename": original_filename,
            "uploader": uploader,
        },
    }
    result = _post_to_webhook(url, payload, f"raw {config['tab_name']}")

    return {
        "ok": result.get("ok", False),
        "sheets_sent": len(sheet_data),
        "total_rows": len(all_rows),
        "tab_name": config["tab_name"],
        "result": result,
    }


# ── L4 R3SS source-tab sync (6 source tabs only) ──────────────
# R3SS, MAP, CONTROL, and Dashboard are computed by Apps Script
# inside the Google Sheet after these 6 tabs are written.


def _r3ss_webhook():
    return os.environ.get("JCLP_PPC_R3SS_WEBHOOK", "").strip()


def sync_r3ss_to_sheet(month):
    """Push the 6 R3SS source tabs to the Google Sheet via n8n.

    Pauses 2s between tabs to avoid n8n 502 rate limits.

    Source tabs (written by n8n, consumed by Apps Script):
      - Master — joined master view
      - Demand Freeze — demand transaction log
      - FG — current FG stock
      - FG Open — month-open FG snapshot
      - DPR all Plant — production entries this month
      - FG Issue qty — dispatch data

    Computed tabs (built by Apps Script after source tabs land):
      - R3SS, MAP, CONTROL, Dashboard

    Uses JCLP_PPC_R3SS_WEBHOOK; falls back to JCLP_PPC_DATA_WEBHOOK.
    """
    url = _r3ss_webhook()
    if not url:
        url = _ppc_data_webhook()
        if not url:
            return {"attempted": False, "reason": "neither R3SS nor DATA webhook set"}

    from .compute_r3ss import (
        build_imp_demand,
        build_imp_dispatch,
        build_imp_fg,
        build_imp_fg_open,
        build_imp_master,
        build_imp_production,
    )

    import time as _time
    results = {}

    # ── Source tab builders (name, builder function, extra args) ──
    tab_builders = [
        ("Master",        "r3ss_imp_master",    lambda: build_imp_master()),
        ("Demand Freeze", "r3ss_imp_demand",    lambda: build_imp_demand(month)),
        ("FG",            "r3ss_imp_fg",        lambda: build_imp_fg()),
        ("FG Open",       "r3ss_imp_fg_open",   lambda: build_imp_fg_open()),
        ("DPR all Plant", "r3ss_imp_production",lambda: build_imp_production(month)),
        ("FG Issue qty",  "r3ss_imp_dispatch",  lambda: build_imp_dispatch()),
    ]

    CHUNK_SIZE = 1000

    for tab_name, report_key, builder in tab_builders:
        try:
            rows = builder()
            if not rows:
                continue

            headers = list(rows[0].keys())
            total_chunks = (len(rows) + CHUNK_SIZE - 1) // CHUNK_SIZE

            for ci in range(total_chunks):
                chunk = rows[ci * CHUNK_SIZE : (ci + 1) * CHUNK_SIZE]
                payload = {
                    "action": "write_tab",
                    "report_key": report_key,
                    "tab_name": tab_name,
                    "headers": headers,
                    "rows": chunk,
                    "row_count": len(chunk),
                    "chunk_index": ci,
                    "total_chunks": total_chunks,
                    "append": ci > 0,
                    "_meta": {"month": month, "source": "ppc_data_portal"},
                }
                label = f"R3SS {tab_name} chunk {ci+1}/{total_chunks}"
                result = _post_to_webhook(url, payload, label)
                if not result.get("ok"):
                    log.error("R3SS %s chunk %d failed: %s", tab_name, ci, result)
                    break

            results[tab_name] = result
        except Exception as exc:
            log.exception("R3SS %s sync failed", tab_name)
            results[tab_name] = {"ok": False, "error": str(exc)}

        _time.sleep(1)

    # ── Trigger R3SS computation in Apps Script ──
    all_ok = all(
        r.get("ok") for r in results.values() if isinstance(r, dict)
    )
    if all_ok and results:
        try:
            compute_payload = {"action": "compute", "month": month}
            results["_compute"] = _post_to_webhook(
                url, compute_payload, "R3SS compute trigger"
            )
        except Exception as exc:
            log.exception("R3SS compute trigger failed")
            results["_compute"] = {"ok": False, "error": str(exc)}

    return results


# ── L2 Demand → DEMAND Google Sheet (spec §3.2) ──────────────
#
# Three tabs: DEMAND_TXN (append-only), DEMAND_PART (rollup), TREND_6M
# DEMAND_TXN is append-only — n8n must NOT clear it before writing.
# DEMAND_PART and TREND_6M are clear-and-replace on each sync.

def _ppc_demand_webhook():
    return os.environ.get("JCLP_PPC_DEMAND_WEBHOOK", "").strip()


def sync_demand_txn_to_sheet(month):
    """Push the DEMAND_TXN append-only transaction log for a month.

    Spec §3.2: "DEMAND_TXN — append-only, one row per demand event.
    TXN_ID, ERP_PART_CODE, TXN_TYPE (INITIAL | ADDITION | REDUCTION),
    QTY, TXN_DATE, WEEK_NO, CUSTOMER, SOURCE_DOC, ENTERED_BY.
    INITIAL rows are written once at month open from FORECAST plus open
    sales orders, then locked."

    This collects all freeze + transaction records for the month and
    pushes them as a flat transaction log.
    """
    url = _ppc_demand_webhook()
    if not url:
        url = _ppc_data_webhook()
        if not url:
            return {"attempted": False, "reason": "neither DEMAND nor DATA webhook set"}

    from .models import PPCDemandFreeze, PPCDemandTransaction

    # Build INITIAL rows from the freeze table
    freezes = PPCDemandFreeze.objects.filter(month=month).select_related("frozen_by")
    txn_rows = []

    for f in freezes:
        txn_rows.append({
            "TXN_ID": f"INIT-{f.pk}",
            "ERP Part Code": f.item_code,
            "TXN Type": "INITIAL",
            "Qty": f.initial_qty,
            "TXN Date": f.frozen_at.strftime("%Y-%m-%d") if f.frozen_at else "",
            "Week": "",
            "Customer": "",
            "Source Doc": "",
            "Entered By": str(f.frozen_by) if f.frozen_by else "system",
            "Month": f.month,
        })

    # Build ADDITION / REDUCTION rows from transactions
    txns = (
        PPCDemandTransaction.objects
        .filter(freeze__month=month)
        .select_related("freeze", "created_by")
        .order_by("created_at")
    )
    for t in txns:
        txn_type = "ADDITION" if t.tx_type == "add" else "REDUCTION"
        txn_rows.append({
            "TXN_ID": f"TXN-{t.pk}",
            "ERP Part Code": t.freeze.item_code,
            "TXN Type": txn_type,
            "Qty": t.qty,
            "TXN Date": t.created_at.strftime("%Y-%m-%d") if t.created_at else "",
            "Week": t.week,
            "Customer": "",
            "Source Doc": t.reason[:100] if t.reason else "",
            "Entered By": str(t.created_by) if t.created_by else "system",
            "Month": t.freeze.month,
        })

    if not txn_rows:
        return {"attempted": False, "reason": f"no demand data for month {month}"}

    headers = list(txn_rows[0].keys())

    payload = {
        "report_key": "demand_txn",
        "tab_name": "DEMAND_TXN",
        "append_only": True,
        "headers": headers,
        "rows": txn_rows,
        "row_count": len(txn_rows),
        "_meta": {
            "month": month,
            "source": "ppc_data_portal",
            "initial_count": freezes.count(),
            "transaction_count": txns.count(),
        },
    }

    return _post_to_webhook(url, payload, f"DEMAND_TXN sync ({month})")


def sync_demand_part_to_sheet(month):
    """Push the DEMAND_PART rollup tab for a month.

    Spec §3.2: "DEMAND_PART — one row per part: initial, additions,
    reductions, total."

    Clear-and-replace on each sync.
    """
    url = _ppc_demand_webhook()
    if not url:
        url = _ppc_data_webhook()
        if not url:
            return {"attempted": False, "reason": "neither DEMAND nor DATA webhook set"}

    from django.db.models import Sum

    from .models import PPCDemandFreeze

    freezes = (
        PPCDemandFreeze.objects
        .filter(month=month)
        .prefetch_related("transactions")
    )

    rows = []
    for f in freezes:
        agg = f.transactions.values("tx_type").annotate(total=Sum("qty"))
        adds = sum(a["total"] for a in agg if a["tx_type"] == "add")
        reds = sum(a["total"] for a in agg if a["tx_type"] == "reduce")
        effective = f.initial_qty + adds - reds

        rows.append({
            "ERP Part Code": f.item_code,
            "Month": f.month,
            "Initial Qty": f.initial_qty,
            "Additions": adds,
            "Reductions": reds,
            "Effective Demand": effective,
            "TXN Count": f.transactions.count(),
            "Frozen At": f.frozen_at.strftime("%Y-%m-%d %H:%M") if f.frozen_at else "",
        })

    if not rows:
        return {"attempted": False, "reason": f"no demand data for month {month}"}

    headers = list(rows[0].keys())

    payload = {
        "report_key": "demand_part",
        "tab_name": "DEMAND_PART",
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
        "_meta": {"month": month, "source": "ppc_data_portal"},
    }

    return _post_to_webhook(url, payload, f"DEMAND_PART sync ({month})")


def sync_trend_6m_to_sheet():
    """Push the TREND_6M tab — 6-month demand/dispatch history per part.

    Spec §3.2: "TREND_6M — per part: demand for each of the last 6 months,
    max, min, average, trend. Built from INVOICE and FORECAST history,
    NOT from the plan."

    Data sources: erp_dispatch (INVOICE) and erp_forecast (FORECAST)
    from ERP landing. Falls back to demand_history if ERP data is
    not yet loaded.

    Clear-and-replace on each sync.
    """
    from django.utils import timezone

    url = _ppc_demand_webhook()
    if not url:
        url = _ppc_data_webhook()
        if not url:
            return {"attempted": False, "reason": "neither DEMAND nor DATA webhook set"}

    from .models import PPCDataRow, PPCUploadBatch

    now = timezone.now()

    # Try ERP dispatch (invoice) data first
    dispatch_batch = (
        PPCUploadBatch.objects
        .filter(table_key="erp_dispatch", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    forecast_batch = (
        PPCUploadBatch.objects
        .filter(table_key="erp_forecast", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )

    # Fall back to demand_history if ERP data not available
    history_batch = None
    if not dispatch_batch and not forecast_batch:
        history_batch = (
            PPCUploadBatch.objects
            .filter(table_key="demand_history", is_current=True)
            .order_by("-uploaded_at")
            .first()
        )
        if not history_batch:
            return {"attempted": False, "reason": "no dispatch, forecast, or history data"}

    # Build part-level 6-month trend data
    # Compute the last 6 month labels
    month_labels = []
    for i in range(6, 0, -1):
        # Go back i months from current
        m = now.month - i
        y = now.year
        while m < 1:
            m += 12
            y -= 1
        month_labels.append(f"{y:04d}-{m:02d}")

    # Strategy: collect per-part monthly totals from whatever source we have
    part_months = {}  # item_code -> {month -> {dispatch: n, forecast: n}}

    if history_batch:
        # Use demand_history (dispatch trends file)
        hist_rows = list(
            PPCDataRow.objects
            .filter(batch=history_batch)
            .values_list("data", flat=True)
        )
        for r in hist_rows:
            ic = str(r.get("item_code", "")).strip()
            m = str(r.get("month", "")).strip()[:7]  # YYYY-MM
            if not ic or not m:
                continue
            entry = part_months.setdefault(ic, {})
            me = entry.setdefault(m, {"dispatch": 0, "forecast": 0})
            me["dispatch"] += num0(r.get("dispatch_qty"))
            me["forecast"] += num0(r.get("demand_qty"))
    else:
        # Use ERP dispatch + forecast
        if dispatch_batch:
            disp_rows = list(
                PPCDataRow.objects
                .filter(batch=dispatch_batch)
                .values_list("data", flat=True)
            )
            for r in disp_rows:
                ic = str(r.get("item_code", "")).strip()
                # Try to extract month from date fields
                date_str = str(r.get("invoice_date") or r.get("date") or "").strip()
                m = date_str[:7] if len(date_str) >= 7 else ""
                if not ic or not m:
                    continue
                entry = part_months.setdefault(ic, {})
                me = entry.setdefault(m, {"dispatch": 0, "forecast": 0})
                me["dispatch"] += num0(r.get("qty") or r.get("dispatch_qty"))

        if forecast_batch:
            fc_rows = list(
                PPCDataRow.objects
                .filter(batch=forecast_batch)
                .values_list("data", flat=True)
            )
            for r in fc_rows:
                ic = str(r.get("item_code", "")).strip()
                date_str = str(r.get("from_date") or r.get("date") or "").strip()
                m = date_str[:7] if len(date_str) >= 7 else ""
                if not ic or not m:
                    continue
                entry = part_months.setdefault(ic, {})
                me = entry.setdefault(m, {"dispatch": 0, "forecast": 0})
                me["forecast"] += num0(r.get("forecast_qty") or r.get("qty"))

    if not part_months:
        return {"attempted": False, "reason": "no part-level demand/dispatch data found"}

    # Build trend rows
    trend_rows = []
    for ic in sorted(part_months.keys()):
        months_data = part_months[ic]
        row = {"ERP Part Code": ic}

        values = []
        for ml in month_labels:
            md = months_data.get(ml, {"dispatch": 0, "forecast": 0})
            qty = md["dispatch"] or md["forecast"]  # prefer dispatch
            row[ml] = qty
            values.append(qty)

        nonzero = [v for v in values if v > 0]
        row["Max"] = max(values) if values else 0
        row["Min"] = min(nonzero) if nonzero else 0
        row["Avg"] = round(sum(values) / len(values), 1) if values else 0

        # Simple trend: last 3 months vs first 3 months
        first_half = sum(values[:3])
        second_half = sum(values[3:])
        if first_half > 0:
            trend_pct = round((second_half - first_half) / first_half * 100, 1)
        else:
            trend_pct = 0
        row["Trend %"] = trend_pct
        row["Trend"] = "↑" if trend_pct > 5 else ("↓" if trend_pct < -5 else "→")

        trend_rows.append(row)

    headers = ["ERP Part Code"] + month_labels + ["Max", "Min", "Avg", "Trend %", "Trend"]

    payload = {
        "report_key": "trend_6m",
        "tab_name": "TREND_6M",
        "headers": headers,
        "rows": trend_rows,
        "row_count": len(trend_rows),
        "_meta": {
            "months": month_labels,
            "source": "ppc_data_portal",
            "data_sources": {
                "dispatch": dispatch_batch.pk if dispatch_batch else None,
                "forecast": forecast_batch.pk if forecast_batch else None,
                "history": history_batch.pk if history_batch else None,
            },
        },
    }

    return _post_to_webhook(url, payload, "TREND_6M sync")


def sync_demand_sheet(month):
    """Sync all three DEMAND tabs for a month.

    Convenience function that calls all three sync functions.
    Returns a dict with results for each tab.
    """
    results = {}
    results["demand_txn"] = sync_demand_txn_to_sheet(month)
    results["demand_part"] = sync_demand_part_to_sheet(month)
    results["trend_6m"] = sync_trend_6m_to_sheet()
    return results
