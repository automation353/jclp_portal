"""REST endpoints for L2 Demand Freeze.

  POST /api/ppc-data/demand/freeze/         upload & freeze initial demand
  POST /api/ppc-data/demand/transaction/    upload additions / reductions
  GET  /api/ppc-data/demand/current/        effective demand (frozen + txns)
  GET  /api/ppc-data/demand/history/        list all freezes & transactions

Rule 3: initial demand is immutable once frozen. Changes are dated
transactions that accrue on top.
"""

import logging

from django.db import transaction
from django.db.models import Sum
from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .api import _store_file
from .field_maps.helpers import num0
from .models import PPCDataRow, PPCDemandFreeze, PPCDemandTransaction, PPCUploadBatch
from .parsers.forecast_demand import parse as parse_demand, parse_transactions

log = logging.getLogger(__name__)


@api_view(["POST"])
@parser_classes([MultiPartParser])
def demand_freeze(request):
    """Upload a forecast file and freeze the initial demand.

    Parses the "Initial Demand" sheet and creates PPCDemandFreeze records.
    If a freeze already exists for an item+month, it is NOT overwritten
    (Rule 3). The endpoint reports which items were frozen and which
    were skipped.

    Form data:
      file     — the forecast xlsx
      month    — YYYY-MM (required, specifies the planning month)
      notes    — optional notes
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response(
            {"detail": "No file attached under the 'file' key."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    month = request.data.get("month", "").strip()
    if not month or len(month) != 7 or month[4] != "-":
        return Response(
            {"detail": "Provide 'month' in YYYY-MM format (e.g. 2026-09)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stored_path, original_name = _store_file(uploaded)
    notes = str(request.data.get("notes", ""))[:500]

    # Parse the initial demand sheet
    try:
        parsed_rows = parse_demand(stored_path)
    except Exception as exc:
        log.exception("Demand freeze parse failed: %s", exc)
        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="demand",
            level="L2",
            table_key="demand_freeze",
            row_count=0,
            is_current=False,
            parse_error=str(exc),
            notes=notes,
        )
        return Response(
            {"detail": f"Parse failed: {exc}", "batch_id": batch.pk},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if not parsed_rows:
        return Response(
            {"detail": "No demand rows found in the file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create batch + store raw rows for browsing
    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key="demand_freeze", is_current=True,
        ).update(is_current=False)

        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="demand",
            level="L2",
            table_key="demand_freeze",
            row_count=len(parsed_rows),
            is_current=True,
            notes=notes,
        )

        PPCDataRow.objects.bulk_create([
            PPCDataRow(
                batch=batch, sr_no=i + 1,
                table_key="demand_freeze", data=row,
            )
            for i, row in enumerate(parsed_rows)
        ], batch_size=500)

    # Freeze: create PPCDemandFreeze records (skip already-frozen)
    frozen_count = 0
    skipped_count = 0

    for row in parsed_rows:
        item_code = str(row.get("item_code", "")).strip()
        if not item_code:
            continue

        qty = num0(row.get("initial_qty") or row.get("demand_qty"))
        if qty == 0 and not row.get("initial_qty"):
            continue

        row_month = str(row.get("month", "")).strip() or month

        _, created = PPCDemandFreeze.objects.get_or_create(
            item_code=item_code,
            month=row_month,
            defaults={
                "initial_qty": qty,
                "frozen_by": request.user,
                "batch": batch,
            },
        )
        if created:
            frozen_count += 1
        else:
            skipped_count += 1

    notify(
        f"Demand frozen — {original_name}",
        f"{request.user.get_username()} froze demand for {month}: "
        f"{frozen_count} items frozen, {skipped_count} already existed.",
    )

    return Response({
        "batch_id": batch.pk,
        "month": month,
        "total_rows": len(parsed_rows),
        "frozen": frozen_count,
        "skipped_already_frozen": skipped_count,
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@parser_classes([MultiPartParser])
def demand_transaction(request):
    """Upload demand additions or reductions.

    Parses "Additional W1", "Additional W2", "Reduced Demand" sheets.
    Each row becomes a PPCDemandTransaction linked to the matching
    PPCDemandFreeze. Items without a freeze are reported as warnings.

    Form data:
      file     — the forecast xlsx (with addition/reduction sheets)
      month    — YYYY-MM (required)
      notes    — optional
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response(
            {"detail": "No file attached."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    month = request.data.get("month", "").strip()
    if not month or len(month) != 7:
        return Response(
            {"detail": "Provide 'month' in YYYY-MM format."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stored_path, original_name = _store_file(uploaded)
    notes = str(request.data.get("notes", ""))[:500]

    try:
        txn_rows = parse_transactions(stored_path)
    except Exception as exc:
        log.exception("Demand transaction parse failed: %s", exc)
        return Response(
            {"detail": f"Parse failed: {exc}"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if not txn_rows:
        return Response(
            {"detail": "No addition/reduction rows found in the file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Store raw rows for browsing
    with transaction.atomic():
        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="demand",
            level="L2",
            table_key="demand_transaction",
            row_count=len(txn_rows),
            is_current=True,
            notes=notes,
        )

        PPCDataRow.objects.bulk_create([
            PPCDataRow(
                batch=batch, sr_no=i + 1,
                table_key="demand_transaction", data=row,
            )
            for i, row in enumerate(txn_rows)
        ], batch_size=500)

    # Create PPCDemandTransaction records
    created_count = 0
    no_freeze_count = 0

    for row in txn_rows:
        item_code = str(row.get("item_code", "")).strip()
        if not item_code:
            continue

        row_month = str(row.get("month", "")).strip() or month
        qty = num0(row.get("qty"))
        if qty == 0:
            continue

        tx_type = row.get("tx_type", "add")

        try:
            freeze = PPCDemandFreeze.objects.get(
                item_code=item_code, month=row_month,
            )
        except PPCDemandFreeze.DoesNotExist:
            no_freeze_count += 1
            continue

        PPCDemandTransaction.objects.create(
            freeze=freeze,
            tx_type=tx_type,
            qty=abs(qty),
            week=str(row.get("week", "")).strip(),
            reason=str(row.get("reason", "")).strip()[:200],
            created_by=request.user,
            batch=batch,
        )
        created_count += 1

    notify(
        f"Demand transactions — {original_name}",
        f"{request.user.get_username()} uploaded demand changes for {month}: "
        f"{created_count} transactions, {no_freeze_count} items had no freeze.",
    )

    return Response({
        "batch_id": batch.pk,
        "month": month,
        "total_rows": len(txn_rows),
        "transactions_created": created_count,
        "no_freeze_warnings": no_freeze_count,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def demand_current(request):
    """Get effective demand for a month.

    Query params:
      ?month=2026-09   — required
      ?search=xyz      — filter by item code
      ?limit=500       — max rows (default 500, max 5000)

    Returns each frozen item with:
      initial_qty, additions, reductions, effective_qty
    """
    month = request.GET.get("month", "").strip()
    if not month:
        # Default to the latest frozen month
        latest = PPCDemandFreeze.objects.order_by("-month").first()
        if latest:
            month = latest.month
        else:
            return Response(
                {"detail": "No demand frozen yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

    freezes = PPCDemandFreeze.objects.filter(month=month)

    search = request.GET.get("search", "").strip()
    if search:
        freezes = freezes.filter(item_code__icontains=search)

    try:
        limit = max(1, min(5000, int(request.GET.get("limit", 500))))
    except (ValueError, TypeError):
        limit = 500

    total = freezes.count()
    freezes = freezes[:limit]

    items = []
    for f in freezes:
        agg = f.transactions.values("tx_type").annotate(total=Sum("qty"))
        adds = sum(a["total"] for a in agg if a["tx_type"] == "add")
        reds = sum(a["total"] for a in agg if a["tx_type"] == "reduce")
        effective = f.initial_qty + adds - reds

        items.append({
            "item_code": f.item_code,
            "month": f.month,
            "initial_qty": f.initial_qty,
            "additions": adds,
            "reductions": reds,
            "effective_qty": effective,
            "frozen_at": f.frozen_at.isoformat(),
            "frozen_by": str(f.frozen_by) if f.frozen_by else None,
            "transaction_count": f.transactions.count(),
        })

    return Response({
        "month": month,
        "total_items": total,
        "items": items,
        "truncated": total > limit,
    })


@api_view(["GET"])
def demand_months(request):
    """List all months that have frozen demand, with summary counts."""
    months = (
        PPCDemandFreeze.objects
        .values("month")
        .annotate(
            item_count=Sum(1),
            total_initial=Sum("initial_qty"),
        )
        .order_by("-month")
    )

    result = []
    for m in months:
        month_str = m["month"]
        freeze_count = PPCDemandFreeze.objects.filter(month=month_str).count()

        # Count transactions for this month
        tx_count = PPCDemandTransaction.objects.filter(
            freeze__month=month_str,
        ).count()

        result.append({
            "month": month_str,
            "frozen_items": freeze_count,
            "transaction_count": tx_count,
        })

    return Response({"months": result})
