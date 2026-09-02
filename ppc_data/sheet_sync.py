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

import logging
import os

import requests

from .field_maps.helpers import num0

log = logging.getLogger(__name__)


def _pipeline_webhook():
    return os.environ.get("JCLP_PPC_PIPELINE_WEBHOOK", "").strip()


def _ppc_sheet_webhook():
    return os.environ.get("JCLP_PPC_SHEET_WEBHOOK", "").strip()


def _post_to_webhook(url, payload, label="sheet sync"):
    """POST JSON to an n8n webhook. Returns result dict."""
    if not url:
        return {"attempted": False, "reason": "webhook not configured"}

    try:
        resp = requests.post(url, json=payload, timeout=180)
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
    "erp_item_master":    "Item Master",
    "erp_bom":            "BOM",
    "erp_fg_stock":       "FG Stock",
    "erp_cp_stock":       "CP Stock",
    "erp_rm_stock":       "RM Stock",
    "erp_pm_stock":       "PM Stock",
    "erp_consumables":    "Consumables",
    "erp_prod_fg":        "Production FG",
    "erp_prod_semi":      "Production Semi",
    "erp_dispatch":       "Dispatch",
    "erp_forecast":       "Forecast",
    "erp_sales_orders":   "Sales Orders",
    "erp_pending_po":     "Pending PO",
    "erp_pending_pr":     "Pending PR",
    "erp_material_issue": "Material Issue",
    "erp_item_cost":      "Item Cost",
    "erp_fg_ageing":      "FG Ageing",
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


# ── Master / Plan data → PPC Data Google Sheet ────────────────

# Human-readable tab name for each non-ERP table_key.
# Only table_keys that come from file uploads are included (not UI-form
# or compute-generated tables like site_plant_section, working_calendar,
# reason_codes, planning_calendar).
_DATA_TAB_NAMES = {
    # L0 masters (file-uploaded)
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
    # L4 R3SS
    "r3ss_plan":          "R3SS Plan",
    "r3ss_summary":       "R3SS Summary",
}


def _ppc_data_webhook():
    return os.environ.get("JCLP_PPC_DATA_WEBHOOK", "").strip()


def sync_upload_to_sheet(batch):
    """Push a just-uploaded master/plan batch to the PPC Data Google Sheet.

    Called after a successful non-ERP file upload. The n8n workflow receives
    the table_key + flat rows, clears the matching tab, and writes fresh data.

    Non-blocking: failures are logged but never break the upload API.
    """
    url = _ppc_data_webhook()
    if not url:
        return {"attempted": False, "reason": "JCLP_PPC_DATA_WEBHOOK not set"}

    table_key = batch.table_key
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

    # Re-key from internal names back to human-readable Excel headers
    flat_rows = []
    if field_map:
        headers = list(field_map.values())
        for r in rows_raw:
            row = {}
            for internal_key, header in field_map.items():
                val = r.get(internal_key, "")
                row[header] = val
            # R3SS plan has dynamic date columns stored under "days" dict
            if table_key == "r3ss_plan" and "days" in r:
                for day_key, day_val in sorted(r["days"].items()):
                    row[day_key] = day_val
                if "days" not in field_map:
                    # Remove the "days" key from regular columns if present
                    row.pop("days", None)
            flat_rows.append(row)
        # For R3SS, add date columns to headers
        if table_key == "r3ss_plan" and rows_raw:
            first_days = rows_raw[0].get("days", {})
            headers = headers + sorted(first_days.keys())
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

    return _post_to_webhook(url, payload, f"PPC data sync ({tab_name})")
