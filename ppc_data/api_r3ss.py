"""REST endpoints for L4 R3SS plan upload.

  POST /api/ppc-data/r3ss/upload/      upload R3 SS.xlsx (plan + summary)
  GET  /api/ppc-data/r3ss/current/     get current R3SS plan rows
  GET  /api/ppc-data/r3ss/summary/     R3SS summary tiles
  GET  /api/ppc-data/r3ss/day/<date>/  plan for a specific date

Rule 1: One Plan Table. R3SS is stored once. Every screen reads from it.
"""

import logging

from django.db import transaction
from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .api import _store_file
from .models import PPCDataRow, PPCUploadBatch
from .parsers.r3ss_file import parse as parse_r3ss, parse_summary
from .serializers import PPCUploadBatchSerializer

log = logging.getLogger(__name__)


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

    notify(
        f"R3SS uploaded — {original_name}",
        f"{request.user.get_username()} uploaded R3SS plan: "
        f"{len(plan_rows)} items, {date_count} day columns"
        f"{f', month {plan_month}' if plan_month else ''}. "
        f"{mismatch_count} day-sum mismatches."
        f"{f' Summary: {len(summary_rows)} rows.' if summary_rows else ''}",
    )

    return Response({
        "plan_batch_id": plan_batch.pk,
        "summary_batch_id": summary_batch.pk if summary_batch else None,
        "plan_rows": len(plan_rows),
        "summary_rows": len(summary_rows),
        "plan_month": plan_month,
        "date_columns": date_count,
        "day_sum_mismatches": mismatch_count,
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
