"""L7 Material compute engine — BOM explosion and stock allocation.

Released plan × BOM master = day-wise CP/RM/packing requirement.
Decision #5 resolved: this MUST run in the database — CP Req alone
exceeds Google Sheets' limits (~34.7M cells).

Two stages:
  1. BOM explosion — expand FG items into component requirements per day
  2. Stock allocation — allocate available stock, flag shortages
"""

import logging
from collections import defaultdict

from django.db import transaction

from .field_maps.helpers import num0, txt
from .models import PPCDataRow, PPCRelease, PPCUploadBatch

log = logging.getLogger(__name__)


def _load_current_rows(table_key):
    """Load data dicts from the current batch for a table_key."""
    batch = (
        PPCUploadBatch.objects
        .filter(table_key=table_key, is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if batch is None:
        return []
    return list(batch.rows.values_list("data", flat=True))


def run_bom_explosion(release_id):
    """Explode the released plan through BOM master.

    For each FG item × each date with non-zero plan:
      - Look up BOM components (from bom_master W1.11)
      - Multiply FG qty × component qty_per to get component requirement
      - Aggregate by component × date

    Stores results as PPCDataRow with table_key='bom_requirement'.
    Returns summary dict.
    """
    release = PPCRelease.objects.get(pk=release_id)
    if release.status != "active":
        raise ValueError(f"Release is '{release.status}', not active")

    # Load released plan rows
    plan_rows = list(
        PPCDataRow.objects
        .filter(batch=release.snapshot_batch)
        .values_list("data", flat=True)
    )
    if not plan_rows:
        raise ValueError("Release has no plan rows")

    # Load BOM master
    bom_rows = _load_current_rows("bom_master")
    if not bom_rows:
        raise ValueError("No BOM master loaded — upload W1.11 first")

    # Build BOM lookup: fg_item → [(component_item, component_type, qty_per, uom)]
    # bom_master fields: parent_item, component_item, component_type, qty_per, uom, scrap_pct
    bom_by_fg = defaultdict(list)
    for r in bom_rows:
        parent = txt(r.get("parent_item") or r.get("item_code")).upper()
        comp = txt(r.get("component_item") or r.get("component")).upper()
        comp_type = txt(r.get("component_type") or r.get("type"))  # RM, CP, PM
        qty_per = num0(r.get("bom_qty") or r.get("qty_per") or r.get("quantity"))
        scrap = num0(r.get("scrap_pct")) / 100 if r.get("scrap_pct") else 0
        uom = txt(r.get("uom"))

        if parent and comp and qty_per > 0:
            effective_qty = qty_per * (1 + scrap)
            bom_by_fg[parent].append({
                "component": comp,
                "type": comp_type or "RM",
                "qty_per": round(effective_qty, 6),
                "uom": uom,
            })

    # Explode: FG × date → component requirements
    # Structure: component → {date → required_qty}
    comp_req = defaultdict(lambda: defaultdict(float))
    comp_info = {}  # component → {type, uom}
    items_with_bom = 0
    items_without_bom = 0

    for r in plan_rows:
        item = txt(r.get("item_code")).upper()
        days = r.get("days", {})

        bom = bom_by_fg.get(item, [])
        if not bom:
            items_without_bom += 1
            continue

        items_with_bom += 1

        for d, qty in days.items():
            fg_qty = num0(qty)
            if fg_qty <= 0:
                continue

            for comp in bom:
                req = fg_qty * comp["qty_per"]
                comp_req[comp["component"]][d] += req
                if comp["component"] not in comp_info:
                    comp_info[comp["component"]] = {
                        "type": comp["type"],
                        "uom": comp["uom"],
                    }

    # Store as PPCDataRow batch
    result_rows = []
    for comp_code in sorted(comp_req.keys()):
        dates = comp_req[comp_code]
        info = comp_info[comp_code]
        total_req = sum(dates.values())

        result_rows.append({
            "component_item": comp_code,
            "component_type": info["type"],
            "uom": info["uom"],
            "total_requirement": round(total_req, 2),
            "days": {d: round(q, 2) for d, q in sorted(dates.items())},
        })

    with transaction.atomic():
        # Clean up old explosion for this release
        PPCUploadBatch.objects.filter(
            table_key="bom_requirement",
            notes__contains=f"release_id={release.pk}",
        ).delete()

        batch = PPCUploadBatch.objects.create(
            uploader=None,
            source_file="",
            original_filename=f"BOM Explosion — {release.plan_month}#{release.release_number}",
            file_type="compute",
            level="L7",
            table_key="bom_requirement",
            row_count=len(result_rows),
            is_current=True,
            notes=f"BOM explosion from release_id={release.pk}",
        )

        PPCDataRow.objects.bulk_create([
            PPCDataRow(
                batch=batch, sr_no=i + 1,
                table_key="bom_requirement", data=row,
            )
            for i, row in enumerate(result_rows)
        ], batch_size=500)

    summary = {
        "release_id": release.pk,
        "plan_month": release.plan_month,
        "release_number": release.release_number,
        "fg_items_with_bom": items_with_bom,
        "fg_items_without_bom": items_without_bom,
        "unique_components": len(result_rows),
        "total_requirement_rows": len(result_rows),
        "by_type": _count_by_type(result_rows),
        "batch_id": batch.pk,
    }

    log.info(
        "BOM explosion: %d FG items → %d components for release %s#%d",
        items_with_bom, len(result_rows),
        release.plan_month, release.release_number,
    )

    return summary


def run_stock_allocation(release_id):
    """Allocate available stock against BOM requirements.

    Reads the latest bom_requirement batch and current stock levels
    (erp_cp_stock, erp_rm_stock, erp_pm_stock). Allocates earliest
    dates first (FIFO by date). Flags shortages.

    Stores results as PPCDataRow with table_key='material_shortage'.
    """
    release = PPCRelease.objects.get(pk=release_id)

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
    if bom_batch is None:
        raise ValueError("No BOM explosion found for this release. Run explosion first.")

    bom_rows = list(bom_batch.rows.values_list("data", flat=True))

    # Load stock levels from ERP feeds
    stock_map = {}  # item_code → available_qty
    for stock_key in ("erp_cp_stock", "erp_rm_stock", "erp_pm_stock"):
        stock_rows = _load_current_rows(stock_key)
        for r in stock_rows:
            item = txt(r.get("item_code") or r.get("material_code")).upper()
            qty = num0(r.get("available_qty") or r.get("stock_qty") or r.get("closing_stock"))
            if item:
                stock_map[item] = stock_map.get(item, 0) + qty

    # Allocate stock FIFO by date
    shortage_rows = []
    for row in bom_rows:
        comp = row["component_item"]
        comp_type = row.get("component_type", "RM")
        available = stock_map.get(comp, 0)
        remaining = available
        days = row.get("days", {})

        day_status = {}
        for d in sorted(days.keys()):
            req = days[d]
            allocated = min(remaining, req)
            shortage = max(0, req - allocated)
            remaining -= allocated

            day_status[d] = {
                "required": round(req, 2),
                "allocated": round(allocated, 2),
                "shortage": round(shortage, 2),
            }

        total_req = sum(days.values())
        total_allocated = min(available, total_req)
        total_shortage = max(0, total_req - available)

        shortage_rows.append({
            "component_item": comp,
            "component_type": comp_type,
            "uom": row.get("uom", ""),
            "available_stock": round(available, 2),
            "total_requirement": round(total_req, 2),
            "total_allocated": round(total_allocated, 2),
            "total_shortage": round(total_shortage, 2),
            "has_shortage": total_shortage > 0,
            "days": day_status,
        })

    # Store
    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key="material_shortage",
            notes__contains=f"release_id={release.pk}",
        ).delete()

        batch = PPCUploadBatch.objects.create(
            uploader=None,
            source_file="",
            original_filename=f"Stock Allocation — {release.plan_month}#{release.release_number}",
            file_type="compute",
            level="L7",
            table_key="material_shortage",
            row_count=len(shortage_rows),
            is_current=True,
            notes=f"Stock allocation from release_id={release.pk}",
        )

        PPCDataRow.objects.bulk_create([
            PPCDataRow(
                batch=batch, sr_no=i + 1,
                table_key="material_shortage", data=row,
            )
            for i, row in enumerate(shortage_rows)
        ], batch_size=500)

    shortages = [r for r in shortage_rows if r["has_shortage"]]

    summary = {
        "release_id": release.pk,
        "total_components": len(shortage_rows),
        "components_with_shortage": len(shortages),
        "components_covered": len(shortage_rows) - len(shortages),
        "batch_id": batch.pk,
    }

    return summary


def _count_by_type(rows):
    """Count components by type (RM/CP/PM)."""
    counts = defaultdict(int)
    for r in rows:
        counts[r.get("component_type", "RM")] += 1
    return dict(counts)
