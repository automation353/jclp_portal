"""REST endpoints for L4 R3SS plan upload + compute.

  POST /api/ppc-data/r3ss/upload/      upload R3 SS.xlsx (plan + summary)
  POST /api/ppc-data/r3ss/compute/     run R3SS day-wise spread engine
  GET  /api/ppc-data/r3ss/current/     get current R3SS plan rows
  GET  /api/ppc-data/r3ss/summary/     R3SS summary tiles
  GET  /api/ppc-data/r3ss/day/<date>/  plan for a specific date
  GET  /api/ppc-data/r3ss/control/     acceptance tests (spec §7)
  GET  /api/ppc-data/r3ss/map/         _MAP calendar metadata

Rule 1: One Plan Table. R3SS is stored once. Every screen reads from it.
"""

import logging

from django.db import transaction
from django.utils import timezone
from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from .api import _store_file
from .models import PPCDataRow, PPCUploadBatch
from .parsers.r3ss_file import parse as parse_r3ss, parse_summary
from .serializers import PPCUploadBatchSerializer

log = logging.getLogger(__name__)


def expand_masters_from_r3ss(plan_rows, user=None):
    """Expand family_hierarchy and item_master with items from R3SS upload.

    Merges new items into existing masters, preserving existing data
    for items that already have entries. Returns a summary dict.
    """
    r3ss_items = {}
    for row in plan_rows:
        ic = str(row.get("item_code") or "").strip().upper()
        if not ic:
            continue
        if ic not in r3ss_items:
            r3ss_items[ic] = row

    if not r3ss_items:
        return {"expanded": False, "reason": "No items with item_code found"}

    # Load existing family_hierarchy
    existing_fh = {}
    fh_batch = PPCUploadBatch.objects.filter(
        table_key="family_hierarchy", is_current=True,
    ).first()
    if fh_batch:
        for data in PPCDataRow.objects.filter(batch=fh_batch).values_list("data", flat=True):
            ic = str(data.get("item_code") or "").strip().upper()
            if ic:
                existing_fh[ic] = data

    # Load existing item_master
    existing_im = {}
    im_batch = PPCUploadBatch.objects.filter(
        table_key="item_master", is_current=True,
    ).first()
    if im_batch:
        for data in PPCDataRow.objects.filter(batch=im_batch).values_list("data", flat=True):
            ic = str(data.get("item_code") or "").strip().upper()
            if ic:
                existing_im[ic] = data

    # Merge: keep existing data, add new items from R3SS
    merged_fh = dict(existing_fh)
    new_fh = 0
    for ic, r in r3ss_items.items():
        if ic in merged_fh:
            continue
        family = str(r.get("family") or "").strip()
        if not family:
            continue
        merged_fh[ic] = {
            "item_code": ic,
            "description": r.get("description", ""),
            "jolly_size": r.get("jolly_size", ""),
            "jolly_code": r.get("jolly_code", ""),
            "family": family,
            "product_group": r.get("product_group", ""),
            "section": r.get("section", ""),
            "customer_category": r.get("customer_category", ""),
            "sub_group": "",
            "item_type": "FG",
        }
        new_fh += 1

    merged_im = dict(existing_im)
    new_im = 0
    for ic, r in r3ss_items.items():
        if ic in merged_im:
            continue
        merged_im[ic] = {
            "item_code": ic,
            "description": r.get("description", ""),
            "item_type": "FG",
            "category": r.get("category", ""),
            "group": "",
            "hsn": "",
            "site": r.get("plant", "JCPL-1"),
            "status": "Active",
            "uom": "NOS",
            "sub_group": "",
            "product_group": r.get("product_group", ""),
        }
        new_im += 1

    if new_fh == 0 and new_im == 0:
        return {"expanded": False, "reason": "All items already in masters",
                "family_hierarchy": len(existing_fh), "item_master": len(existing_im)}

    with transaction.atomic():
        if new_fh > 0:
            PPCUploadBatch.objects.filter(
                table_key="family_hierarchy", is_current=True,
            ).update(is_current=False)
            b = PPCUploadBatch.objects.create(
                uploader=user,
                source_file="",
                original_filename="family_hierarchy (R3SS expanded)",
                file_type="derived",
                level="L0",
                table_key="family_hierarchy",
                row_count=len(merged_fh),
                is_current=True,
                notes=f"Auto-expanded from R3SS: +{new_fh} new → {len(merged_fh)} total",
            )
            PPCDataRow.objects.bulk_create([
                PPCDataRow(batch=b, sr_no=i + 1, data=row)
                for i, row in enumerate(
                    sorted(merged_fh.values(), key=lambda x: x.get("item_code", ""))
                )
            ], batch_size=500)

        if new_im > 0:
            PPCUploadBatch.objects.filter(
                table_key="item_master", is_current=True,
            ).update(is_current=False)
            b = PPCUploadBatch.objects.create(
                uploader=user,
                source_file="",
                original_filename="item_master (R3SS expanded)",
                file_type="derived",
                level="L0",
                table_key="item_master",
                row_count=len(merged_im),
                is_current=True,
                notes=f"Auto-expanded from R3SS: +{new_im} new → {len(merged_im)} total",
            )
            PPCDataRow.objects.bulk_create([
                PPCDataRow(batch=b, sr_no=i + 1, data=row)
                for i, row in enumerate(
                    sorted(merged_im.values(), key=lambda x: x.get("item_code", ""))
                )
            ], batch_size=500)

    log.info("R3SS master expansion: family_hierarchy +%d→%d, item_master +%d→%d",
             new_fh, len(merged_fh), new_im, len(merged_im))

    return {
        "expanded": True,
        "family_hierarchy": {"total": len(merged_fh), "new": new_fh},
        "item_master": {"total": len(merged_im), "new": new_im},
    }


@api_view(["POST"])
@parser_classes([MultiPartParser])
def r3ss_upload(request):
    """Upload R3 SS.xlsx. Parses both sheets:
      - "All" → r3ss_plan (dynamic date columns)
      - "Sheet1" → r3ss_summary (fixed columns)

    Form data:
      file   — the R3 SS.xlsx file
      notes  — optional notes
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response(
            {"detail": "No file attached."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stored_path, original_name = _store_file(uploaded)
    notes = str(request.data.get("notes", ""))[:500]

    # Parse plan (All sheet)
    try:
        plan_rows = parse_r3ss(stored_path)
    except Exception as exc:
        log.exception("R3SS plan parse failed: %s", exc)
        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="plan",
            level="L4",
            table_key="r3ss_plan",
            row_count=0,
            is_current=False,
            parse_error=str(exc),
            notes=notes,
        )
        return Response(
            PPCUploadBatchSerializer(batch).data,
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Parse summary (Sheet1) — non-fatal if missing
    summary_rows = []
    try:
        summary_rows = parse_summary(stored_path)
    except Exception as exc:
        log.warning("R3SS summary parse skipped: %s", exc)

    # Detect plan month from the parsed data
    plan_month = None
    if plan_rows and plan_rows[0].get("_plan_month"):
        plan_month = plan_rows[0]["_plan_month"]

    # Count date columns and mismatches
    date_count = 0
    mismatch_count = 0
    for r in plan_rows:
        if r.get("days"):
            date_count = max(date_count, len(r["days"]))
        if r.get("_day_sum_mismatch"):
            mismatch_count += 1

    # Store plan rows
    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key="r3ss_plan", is_current=True,
        ).update(is_current=False)

        plan_batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="plan",
            level="L4",
            table_key="r3ss_plan",
            row_count=len(plan_rows),
            is_current=True,
            notes=notes,
        )

        PPCDataRow.objects.bulk_create([
            PPCDataRow(
                batch=plan_batch, sr_no=i + 1,
                table_key="r3ss_plan", data=row,
            )
            for i, row in enumerate(plan_rows)
        ], batch_size=500)

    # Store summary rows (if any)
    summary_batch = None
    if summary_rows:
        with transaction.atomic():
            PPCUploadBatch.objects.filter(
                table_key="r3ss_summary", is_current=True,
            ).update(is_current=False)

            summary_batch = PPCUploadBatch.objects.create(
                uploader=request.user,
                source_file=stored_path,
                original_filename=original_name,
                file_type="plan",
                level="L4",
                table_key="r3ss_summary",
                row_count=len(summary_rows),
                is_current=True,
                notes=notes,
            )

            PPCDataRow.objects.bulk_create([
                PPCDataRow(
                    batch=summary_batch, sr_no=i + 1,
                    table_key="r3ss_summary", data=row,
                )
                for i, row in enumerate(summary_rows)
            ], batch_size=500)

    # Auto-expand master tables (family_hierarchy, item_master) with
    # any new items found in the uploaded R3SS file.
    master_result = expand_masters_from_r3ss(plan_rows, user=request.user)

    notify(
        f"R3SS uploaded — {original_name}",
        f"{request.user.get_username()} uploaded R3SS plan: "
        f"{len(plan_rows)} items, {date_count} day columns"
        f"{f', month {plan_month}' if plan_month else ''}. "
        f"{mismatch_count} day-sum mismatches."
        f"{f' Summary: {len(summary_rows)} rows.' if summary_rows else ''}"
        f"{f' Masters expanded: {master_result}' if master_result.get('expanded') else ''}",
    )

    return Response({
        "plan_batch_id": plan_batch.pk,
        "summary_batch_id": summary_batch.pk if summary_batch else None,
        "plan_rows": len(plan_rows),
        "summary_rows": len(summary_rows),
        "plan_month": plan_month,
        "date_columns": date_count,
        "day_sum_mismatches": mismatch_count,
        "masters_expanded": master_result,
        "sample_row": plan_rows[0] if plan_rows else None,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def r3ss_current(request):
    """Get current R3SS plan rows.

    Query params:
      ?search=xyz     — filter by item code / description
      ?section=SSWD   — filter by section
      ?limit=500      — max rows (default 500, max 5000)
      ?fields=compact — return only key fields (omit days dict)
    """
    batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_plan", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if batch is None:
        return Response(
            {"detail": "No R3SS plan loaded yet."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        limit = max(1, min(5000, int(request.GET.get("limit", 500))))
    except (ValueError, TypeError):
        limit = 500

    rows_qs = batch.rows.all()
    total = rows_qs.count()

    search = request.GET.get("search", "").strip()
    if search:
        rows_qs = rows_qs.filter(data__icontains=search)

    compact = request.GET.get("fields") == "compact"

    rows = list(rows_qs[:limit].values_list("sr_no", "data"))

    # For compact mode, strip the "days" dict
    result_rows = []
    for sr, data in rows:
        if compact:
            d = {k: v for k, v in data.items() if k not in ("days", "_day_sum_mismatch", "_plan_month")}
        else:
            d = data
        result_rows.append({"sr_no": sr, "data": d})

    # Detect plan month from first row
    plan_month = None
    if rows:
        plan_month = rows[0][1].get("_plan_month")

    return Response({
        "table_key": "r3ss_plan",
        "batch_id": batch.id,
        "uploaded_at": batch.uploaded_at.isoformat(),
        "uploader": str(batch.uploader) if batch.uploader else None,
        "row_count": total,
        "plan_month": plan_month,
        "rows": result_rows,
        "truncated": total > limit,
    })


@api_view(["GET"])
def r3ss_from_sheet(request):
    """Read the computed R3SS tab straight from the Google Sheet.

    The R3SS tab is built in-sheet by Apps Script. Nothing is stored in
    Django — this returns whatever is currently in the sheet.

    Optional ?search=xyz filters rows by any field value (case-insensitive).
    """
    from .r3ss_sheet_reader import read_r3ss_rows

    try:
        result = read_r3ss_rows()
    except Exception as exc:
        log.exception("R3SS sheet read failed")
        return Response(
            {"detail": f"Could not read R3SS tab from Google Sheet: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    rows = result["rows"]
    search = request.GET.get("search", "").strip().lower()
    if search:
        rows = [
            r for r in rows
            if any(search in str(v).lower() for v in r["data"].values())
        ]

    return Response({
        "table_key": "r3ss_plan",
        "source": "google_sheet",
        "row_count": len(rows),
        "plan_month": result["plan_month"],
        "rows": rows,
        "truncated": False,
    })


@api_view(["POST"])
@parser_classes([JSONParser, MultiPartParser])
def r3ss_recompute_sheet(request):
    """Recompute the R3SS tab in-sheet, then return the fresh rows.

    Flow: trigger Apps Script computeR3SS (rebuilds the R3SS tab from the 6
    source tabs), then re-read the tab. The old dashboard data is fully
    replaced by whatever the sheet now holds.
    """
    from .r3ss_sheet_reader import read_r3ss_rows, trigger_recompute

    force = bool(request.data.get("force"))
    compute = trigger_recompute(force=force)
    if not compute.get("ok"):
        if compute.get("skipped"):
            # Guard tripped — some source tabs are still empty. Old R3SS data
            # is left untouched in the sheet; tell the user what to finish.
            return Response(
                {"detail": compute.get("reason")
                    or "Waiting for all source tabs to be uploaded.",
                 "skipped": True,
                 "empty_tabs": compute.get("empty_tabs", []),
                 "compute": compute},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"detail": "R3SS recompute failed in Apps Script.",
             "compute": compute},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        result = read_r3ss_rows()
    except Exception as exc:
        log.exception("R3SS sheet read after recompute failed")
        return Response(
            {"detail": f"Recomputed, but reading the sheet failed: {exc}",
             "compute": compute},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    notify(
        "R3SS recomputed from Google Sheet",
        f"{request.user.get_username()} recomputed R3SS — "
        f"{result['row_count']} rows now in the sheet.",
    )

    return Response({
        "table_key": "r3ss_plan",
        "source": "google_sheet",
        "compute": compute,
        "row_count": result["row_count"],
        "plan_month": result["plan_month"],
        "rows": result["rows"],
        "truncated": False,
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
def r3ss_summary(request):
    """R3SS summary tiles — plan overview."""
    from .field_maps.helpers import num0

    plan_batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_plan", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )

    if plan_batch is None:
        return Response({
            "loaded": False,
            "total_parts": 0,
            "plan_month": None,
            "date_columns": 0,
            "sections": [],
        })

    rows = list(plan_batch.rows.values_list("data", flat=True))

    # Collect stats
    plan_month = rows[0].get("_plan_month") if rows else None
    date_count = max((len(r.get("days", {})) for r in rows), default=0)
    mismatch_count = sum(1 for r in rows if r.get("_day_sum_mismatch"))

    # Section breakdown
    sections = {}
    for r in rows:
        sec = str(r.get("section", "Unknown")).strip() or "Unknown"
        if sec not in sections:
            sections[sec] = {"section": sec, "items": 0, "total_plan": 0}
        sections[sec]["items"] += 1
        sections[sec]["total_plan"] += num0(r.get("total_plan"))

    # Total plan qty
    total_plan = sum(num0(r.get("total_plan")) for r in rows)
    total_demand = sum(num0(r.get("total_demand")) for r in rows)

    return Response({
        "loaded": True,
        "batch_id": plan_batch.id,
        "uploaded_at": plan_batch.uploaded_at.isoformat(),
        "plan_month": plan_month,
        "total_parts": len(rows),
        "date_columns": date_count,
        "day_sum_mismatches": mismatch_count,
        "total_plan": total_plan,
        "total_demand": total_demand,
        "sections": sorted(sections.values(), key=lambda s: -s["total_plan"]),
    })


@api_view(["GET"])
def r3ss_day(request, date):
    """Get plan quantities for a specific date.

    Returns one row per item that has a non-zero plan on that date.

    URL: /api/ppc-data/r3ss/day/2026-08-15/
    Query params:
      ?section=SSWD  — filter by section
      ?limit=500     — max rows
    """
    batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_plan", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if batch is None:
        return Response(
            {"detail": "No R3SS plan loaded."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        limit = max(1, min(5000, int(request.GET.get("limit", 500))))
    except (ValueError, TypeError):
        limit = 500

    section = request.GET.get("section", "").strip()

    # Filter rows that have this date in their "days" dict
    all_rows = batch.rows.values_list("sr_no", "data")
    result = []
    for sr, data in all_rows:
        days = data.get("days", {})
        qty = days.get(date)
        if qty is None or qty == 0:
            continue
        if section and str(data.get("section", "")).strip().lower() != section.lower():
            continue
        result.append({
            "sr_no": sr,
            "item_code": data.get("item_code"),
            "description": data.get("description"),
            "section": data.get("section"),
            "product_group": data.get("product_group"),
            "mto_mts": data.get("mto_mts"),
            "plan_qty": qty,
            "total_plan": data.get("total_plan"),
        })
        if len(result) >= limit:
            break

    return Response({
        "date": date,
        "section_filter": section or None,
        "items": result,
        "count": len(result),
    })


# ── R3SS compute engine endpoint ───────────────────────────────


@api_view(["POST"])
@parser_classes([JSONParser, MultiPartParser])
def r3ss_compute(request):
    """Run the R3SS day-wise spread engine for a given month.

    Spec §5.3: spreads week buckets (W1-W5) from MPS into individual
    working days, respecting EBQ and lead time, then runs §7 acceptance tests.

    Requires MPS computed first.

    JSON body:
      {"month": "2026-09"}
    """
    month = (request.data.get("month") or "").strip()
    if not month or len(month) != 7:
        month = timezone.now().strftime("%Y-%m")

    from .compute_r3ss import compute_r3ss

    try:
        result = compute_r3ss(month, user=request.user)
    except Exception as exc:
        log.exception("R3SS compute failed for month=%s", month)
        return Response(
            {"detail": f"R3SS compute failed: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if result.get("ok"):
        ctrl = result.get("control", {})
        notify(
            f"R3SS computed — {month}",
            f"{request.user.get_username()} ran R3SS compute for {month}: "
            f"{result['items_computed']} items, "
            f"{result['working_days']} working days, "
            f"total plan = {result['total_plan']:,.0f}. "
            f"Tests: {ctrl.get('passed', 0)} pass, "
            f"{ctrl.get('failed', 0)} fail, "
            f"{ctrl.get('skipped', 0)} skip.",
        )
        return Response(result, status=status.HTTP_201_CREATED)
    else:
        return Response(result, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def r3ss_control(request):
    """R3SS acceptance tests — CONTROL tab (spec §7).

    Returns the 10 acceptance test results from the last compute run.
    """
    batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_control", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if batch is None:
        return Response(
            {"detail": "No CONTROL results yet. Run r3ss/compute/ first."},
            status=status.HTTP_404_NOT_FOUND,
        )

    tests = list(batch.rows.order_by("sr_no").values_list("data", flat=True))

    passed = sum(1 for t in tests if t.get("status") == "PASS")
    failed = sum(1 for t in tests if t.get("status") == "FAIL")
    skipped = sum(1 for t in tests if t.get("status") == "SKIP")

    return Response({
        "batch_id": batch.id,
        "computed_at": batch.uploaded_at.isoformat(),
        "total_tests": len(tests),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "gate": "PASS" if failed == 0 else "FAIL",
        "tests": tests,
    })


@api_view(["GET"])
def r3ss_map(request):
    """R3SS _MAP — calendar metadata for the plan month.

    Returns dates, week numbers, working day flags, and shifts
    for the current plan's day columns.
    """
    batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_map", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if batch is None:
        return Response(
            {"detail": "No _MAP data yet. Run r3ss/compute/ first."},
            status=status.HTTP_404_NOT_FOUND,
        )

    map_data = batch.rows.first()
    if map_data is None:
        return Response(
            {"detail": "_MAP batch is empty."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        "batch_id": batch.id,
        "computed_at": batch.uploaded_at.isoformat(),
        "map": map_data.data,
    })
