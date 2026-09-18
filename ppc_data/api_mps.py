"""REST endpoints for L3 MPS uploads + compute.

  POST /api/ppc-data/mps/upload/       upload MPS schedule / history / calendar
  POST /api/ppc-data/mps/compute/      run MPS NET_REQUIREMENT engine
  GET  /api/ppc-data/mps/current/      get current MPS schedule rows
  GET  /api/ppc-data/mps/summary/      MPS summary tiles (items, total plan qty)
  GET  /api/ppc-data/mps/gate/         MPS gate check (demand frozen + items computed)

The MPS Schedule Form is the central output of L3. It consumes:
  - L0 masters (item, BOM, capacity, EBQ, lead time)
  - L1 ERP feeds (FG stock, WIP, sales orders)
  - L2 frozen demand + transactions

The compute engine (compute_mps.py) implements spec §3.3:
  NET_REQUIREMENT = MAX(0, TOTAL_DEMAND + SAFETY_STOCK − FG − WIP − PRODUCED_MTD)
  NET_REQUIREMENT = ROUNDUP(NET_REQUIREMENT / EBQ) × EBQ
  Then bucketed into W1-W5 by lead time and calendar.

Week buckets (W1-W5) are stored in the JSON data of each PPCDataRow.
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
from .parsers import PARSERS
from .serializers import PPCUploadBatchSerializer

log = logging.getLogger(__name__)

# Table keys handled by the MPS upload screen
_MPS_TABLES = {
    "mps_schedule":      {"label": "MPS Schedule Form",  "level": "L3"},
    "mps_history":       {"label": "MPS History Data",   "level": "L3"},
    "planning_calendar": {"label": "Planning Calendar",  "level": "L3"},
    "demand_history":    {"label": "Demand History",     "level": "L2"},
}


def _detect_mps_table(filename):
    """Auto-detect MPS table from filename."""
    fn = filename.lower()
    if "mps" in fn and ("schedule" in fn or "ss" in fn):
        return "mps_schedule"
    if "dispatch" in fn and "trend" in fn:
        return "demand_history"
    if "mps" in fn and ("demand" in fn or "dispatch" in fn or "history" in fn):
        return "mps_history"
    if "calendar" in fn or "monday" in fn:
        return "planning_calendar"
    # Default for MpsSS.xlsm files
    if "mps" in fn:
        return "mps_schedule"
    return None


@api_view(["POST"])
@parser_classes([MultiPartParser])
def mps_upload(request):
    """Upload MPS-related files (schedule, history, calendar).

    Form data:
      file       — the xlsx/xlsm file
      table_key  — explicit table (optional, auto-detected from filename)
      notes      — optional notes
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response(
            {"detail": "No file attached."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    table_key = request.data.get("table_key", "").strip()
    if not table_key:
        table_key = _detect_mps_table(uploaded.name)
    if not table_key:
        return Response(
            {"detail": (
                f"Could not detect MPS table from '{uploaded.name}'. "
                f"Pass table_key (one of: {', '.join(_MPS_TABLES.keys())})."
            )},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if table_key not in PARSERS:
        return Response(
            {"detail": f"No parser for table_key='{table_key}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    info = _MPS_TABLES.get(table_key, {"label": table_key, "level": "L3"})
    stored_path, original_name = _store_file(uploaded)
    notes = str(request.data.get("notes", ""))[:500]

    parser_mod = PARSERS[table_key]
    try:
        parsed_rows = parser_mod.parse(stored_path)
    except Exception as exc:
        log.exception("MPS parse failed for %s", table_key)
        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="plan",
            level=info["level"],
            table_key=table_key,
            row_count=0,
            is_current=False,
            parse_error=str(exc),
            notes=notes,
        )
        return Response(
            PPCUploadBatchSerializer(batch).data,
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key=table_key, is_current=True,
        ).update(is_current=False)

        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type="plan",
            level=info["level"],
            table_key=table_key,
            row_count=len(parsed_rows),
            is_current=True,
            notes=notes,
        )

        PPCDataRow.objects.bulk_create([
            PPCDataRow(
                batch=batch, sr_no=i + 1,
                table_key=table_key, data=row,
            )
            for i, row in enumerate(parsed_rows)
        ], batch_size=500)

    notify(
        f"MPS upload OK — {info['label']}",
        f"{request.user.get_username()} uploaded '{original_name}' "
        f"({table_key}): {len(parsed_rows)} rows.",
    )

    payload = PPCUploadBatchSerializer(batch).data
    payload["sample_row"] = parsed_rows[0] if parsed_rows else None
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@parser_classes([JSONParser, MultiPartParser])
def mps_compute(request):
    """Run the MPS NET_REQUIREMENT engine for a given month.

    Spec §3.3: computes net requirement per item from demand, stock,
    WIP, safety stock, and EBQ, then buckets into W1-W5.

    JSON body:
      {"month": "2026-09"}

    Requires:
      - Frozen demand for the month (L2)
      - FG stock data (L1 ERP)
      - Masters loaded (L0): family_hierarchy, batch_ebq, lead_time, stock_policy
    """
    month = (request.data.get("month") or "").strip()
    if not month or len(month) != 7:
        # Default to current month
        month = timezone.now().strftime("%Y-%m")

    from .compute_mps import compute_mps

    try:
        result = compute_mps(month, user=request.user)
    except Exception as exc:
        log.exception("MPS compute failed for month=%s", month)
        return Response(
            {"detail": f"MPS compute failed: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if result.get("ok"):
        notify(
            f"MPS computed — {month}",
            f"{request.user.get_username()} ran MPS compute for {month}: "
            f"{result['items_computed']} items, "
            f"net req = {result['total_net_requirement']:,.0f}, "
            f"{result['gate_failures']} gate failures.",
        )
        return Response(result, status=status.HTTP_201_CREATED)
    else:
        return Response(result, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def mps_gate(request):
    """MPS gate check — are all prerequisites met for the plan?

    Checks:
      1. Demand is frozen for the month
      2. MPS schedule has been computed
      3. W1+W2+W3+W4+W5 = NET_REQUIREMENT for every part (zero gate failures)
    """
    from .field_maps.helpers import num0

    month = request.GET.get("month", "").strip()
    if not month:
        month = timezone.now().strftime("%Y-%m")

    checks = []

    # Check 1: demand frozen
    from .models import PPCDemandFreeze
    demand_count = PPCDemandFreeze.objects.filter(month=month).count()
    checks.append({
        "check": "demand_frozen",
        "status": "PASS" if demand_count > 0 else "BLOCKED",
        "detail": f"{demand_count} items frozen for {month}",
    })

    # Check 2: MPS computed
    batch = (
        PPCUploadBatch.objects
        .filter(table_key="mps_schedule", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    has_mps = batch is not None
    checks.append({
        "check": "mps_computed",
        "status": "PASS" if has_mps else "BLOCKED",
        "detail": (
            f"Batch #{batch.id}, {batch.row_count} items"
            if has_mps else "No MPS schedule computed yet"
        ),
    })

    # Check 3: week bucket gate (W1+...+W5 = NET_REQ for all parts)
    gate_failures = 0
    if has_mps:
        rows = list(batch.rows.values_list("data", flat=True))
        for r in rows:
            net_req = num0(r.get("net_requirement"))
            w_sum = sum(num0(r.get(f"w{i}_qty")) for i in range(1, 6))
            if abs(w_sum - net_req) > 0.01:
                gate_failures += 1

        checks.append({
            "check": "week_bucket_gate",
            "status": "PASS" if gate_failures == 0 else "FAIL",
            "detail": (
                "All items: W1+W2+W3+W4+W5 = NET_REQUIREMENT"
                if gate_failures == 0
                else f"{gate_failures} items fail: W1+...+W5 ≠ NET_REQUIREMENT"
            ),
        })

    all_pass = all(c["status"] == "PASS" for c in checks)

    return Response({
        "month": month,
        "gate": "PASS" if all_pass else "BLOCKED",
        "checks": checks,
    })


@api_view(["GET"])
def mps_current(request):
    """Get current MPS schedule rows.

    Query params:
      ?search=xyz   — filter by item code / description
      ?limit=500    — max rows
      ?section=HW1  — filter by section
      ?category=MTO — filter MTO/MTS
    """
    batch = (
        PPCUploadBatch.objects
        .filter(table_key="mps_schedule", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if batch is None:
        return Response(
            {"detail": "No MPS schedule loaded yet."},
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

    # Section filter (G19 fix — was documented but not implemented)
    section = request.GET.get("section", "").strip()
    if section:
        rows_qs = rows_qs.filter(data__section__icontains=section)

    # Category filter (MTO/MTS)
    category = request.GET.get("category", "").strip()
    if category:
        rows_qs = rows_qs.filter(data__category__icontains=category)

    rows = list(rows_qs[:limit].values_list("sr_no", "data"))

    return Response({
        "table_key": "mps_schedule",
        "batch_id": batch.id,
        "uploaded_at": batch.uploaded_at.isoformat(),
        "uploader": str(batch.uploader) if batch.uploader else None,
        "row_count": total,
        "rows": [{"sr_no": sr, "data": d} for sr, d in rows],
        "truncated": total > limit,
    })


@api_view(["GET"])
def mps_summary(request):
    """MPS summary — tile data for the hub screen."""
    from .field_maps.helpers import num0

    batch = (
        PPCUploadBatch.objects
        .filter(table_key="mps_schedule", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )

    if batch is None:
        return Response({
            "loaded": False,
            "total_items": 0,
            "total_plan_qty": 0,
            "mto_items": 0,
            "mts_items": 0,
        })

    rows = list(batch.rows.values_list("data", flat=True))

    total_plan = sum(num0(r.get("total_plan")) for r in rows)
    mto = sum(1 for r in rows if str(r.get("category", "")).upper().startswith("MTO"))
    mts = sum(1 for r in rows if str(r.get("category", "")).upper().startswith("MTS"))

    return Response({
        "loaded": True,
        "batch_id": batch.id,
        "uploaded_at": batch.uploaded_at.isoformat(),
        "total_items": len(rows),
        "total_plan_qty": total_plan,
        "mto_items": mto,
        "mts_items": mts,
    })
