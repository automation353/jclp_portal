"""REST endpoints for PPC dashboards (Phase 10).

  GET  /api/ppc-data/dashboard/capacity/      plan vs capacity by product group
  GET  /api/ppc-data/dashboard/adherence/     adherence split by category
  GET  /api/ppc-data/dashboard/stock/         stock levels (red/yellow/green/blue)
  GET  /api/ppc-data/dashboard/shortages/     shortage board
  GET  /api/ppc-data/dashboard/oee/           OEE by section
  GET  /api/ppc-data/dashboard/opening/       opening balance for next cycle
  POST /api/ppc-data/dashboard/refresh/       refresh all dashboards
  GET  /api/ppc-data/dashboard/summary/       all-in-one summary tiles

Spec §6: "Every dashboard reads R3SS!PLAN and ACTUALS — never the source
workbooks. Build these first, because they are what makes the module
visibly better than the spreadsheets."
"""

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import PPCComputeResult, PPCUploadBatch

log = logging.getLogger(__name__)


def _get_month(request):
    """Extract month from query param or default to current."""
    month = request.GET.get("month", "").strip() or request.data.get("month", "").strip()
    if not month or len(month) != 7:
        month = timezone.now().strftime("%Y-%m")
    return month


def _cached_or_compute(compute_key, compute_fn, *args):
    """Try to load from PPCComputeResult cache; fall back to computing fresh."""
    # Try cache first (within last 30 minutes)
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=30)
    cached = (
        PPCComputeResult.objects
        .filter(compute_key=compute_key, computed_at__gte=cutoff)
        .order_by("-computed_at")
        .first()
    )
    if cached:
        return cached.tiles, True  # (data, from_cache)

    # Compute fresh
    try:
        result = compute_fn(*args)
    except Exception as exc:
        log.exception("Dashboard compute failed for %s", compute_key)
        return {"error": str(exc)}, False

    # Store in cache — need a batch to attach to
    batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_plan", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if batch:
        PPCComputeResult.objects.update_or_create(
            batch=batch,
            compute_key=compute_key,
            defaults={"tiles": result, "tile_rows": {}},
        )

    return result, False


@api_view(["GET"])
def dashboard_capacity(request):
    """Plan vs capacity by product group by date."""
    month = _get_month(request)
    from .compute_dashboard import compute_plan_vs_capacity
    data, cached = _cached_or_compute(f"capacity_{month}", compute_plan_vs_capacity, month)
    return Response({"month": month, "cached": cached, "data": data})


@api_view(["GET"])
def dashboard_adherence(request):
    """Adherence split by category (OEM/Market/Fleetguard/Export)."""
    month = _get_month(request)
    from .compute_dashboard import compute_adherence_dashboard
    data, cached = _cached_or_compute(f"adherence_{month}", compute_adherence_dashboard, month)
    return Response({"month": month, "cached": cached, "data": data})


@api_view(["GET"])
def dashboard_stock(request):
    """Stock levels — items in red/yellow/green/blue."""
    from .compute_dashboard import compute_stock_levels
    data, cached = _cached_or_compute("stock_levels", compute_stock_levels)
    return Response({"cached": cached, "data": data})


@api_view(["GET"])
def dashboard_shortages(request):
    """Shortage board — material short inside lead time."""
    month = _get_month(request)
    from .compute_dashboard import compute_shortage_board
    data, cached = _cached_or_compute(f"shortages_{month}", compute_shortage_board, month)
    return Response({"month": month, "cached": cached, "data": data})


@api_view(["GET"])
def dashboard_oee(request):
    """OEE by section and line."""
    month = _get_month(request)
    from .compute_dashboard import compute_oee
    data, cached = _cached_or_compute(f"oee_{month}", compute_oee, month)
    return Response({"month": month, "cached": cached, "data": data})


@api_view(["GET"])
def dashboard_opening(request):
    """Opening balance for next cycle — Phase 10 gate."""
    month = _get_month(request)
    from .compute_dashboard import derive_opening_balance
    data, cached = _cached_or_compute(f"opening_{month}", derive_opening_balance, month)
    return Response({"month": month, "cached": cached, "data": data})


@api_view(["POST"])
@parser_classes([JSONParser])
def dashboard_refresh(request):
    """Refresh all dashboards for a month."""
    month = _get_month(request)
    from .compute_dashboard import refresh_dashboard

    try:
        result = refresh_dashboard(month, user=request.user)
    except Exception as exc:
        log.exception("Dashboard refresh failed for month=%s", month)
        return Response(
            {"detail": f"Dashboard refresh failed: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    from portal.notify import notify
    notify(
        f"Dashboards refreshed — {month}",
        f"{request.user.get_username()} refreshed dashboards for {month}.",
    )

    return Response(result, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def dashboard_summary(request):
    """All-in-one summary tiles for the hub screen."""
    month = _get_month(request)

    # Load cached results for all dashboards
    keys = [
        f"capacity_{month}", f"adherence_{month}", "stock_levels",
        f"shortages_{month}", f"oee_{month}", f"opening_{month}",
    ]

    tiles = {}
    for key in keys:
        cached = (
            PPCComputeResult.objects
            .filter(compute_key=key)
            .order_by("-computed_at")
            .first()
        )
        short_key = key.replace(f"_{month}", "")
        if cached:
            data = cached.tiles
            # Extract headline number from each dashboard
            if "capacity" in key:
                tiles[short_key] = {
                    "overloaded_groups": data.get("overloaded_groups", 0),
                    "total_groups": data.get("total_groups", 0),
                    "computed_at": cached.computed_at.isoformat(),
                }
            elif "adherence" in key:
                tiles[short_key] = {
                    "overall_adherence_pct": data.get("overall_adherence_pct", 0),
                    "total_planned": data.get("total_planned", 0),
                    "total_actual": data.get("total_actual", 0),
                    "computed_at": cached.computed_at.isoformat(),
                }
            elif "stock" in key:
                tiles[short_key] = {
                    "fg": data.get("fg", {}),
                    "total_items": data.get("total_items", 0),
                    "computed_at": cached.computed_at.isoformat(),
                }
            elif "shortages" in key:
                tiles[short_key] = {
                    "shortage_count": data.get("shortage_count", 0),
                    "critical_count": data.get("critical_count", 0),
                    "computed_at": cached.computed_at.isoformat(),
                }
            elif "oee" in key:
                tiles[short_key] = {
                    "overall_oee": data.get("overall_oee", 0),
                    "sections_count": data.get("sections_count", 0),
                    "computed_at": cached.computed_at.isoformat(),
                }
            elif "opening" in key:
                tiles[short_key] = {
                    "items_derived": data.get("items_derived", 0),
                    "computed_at": cached.computed_at.isoformat(),
                }
        else:
            tiles[short_key] = {"status": "not computed"}

    return Response({
        "month": month,
        "dashboards": tiles,
    })


# ── Parallel-run comparison (Phase 11, test 10) ──────────────


@api_view(["GET"])
def parallel_run_compare(request):
    """Compare portal-computed plan vs uploaded R3 SS.xlsx.

    Phase 11 gate: test 10 — "within an explained variance."

    Requires both:
      - A computed R3SS plan (from r3ss/compute/)
      - An uploaded R3 SS.xlsx (from r3ss/upload/)

    Compares total_plan per item and reports variance.
    """
    from .field_maps.helpers import num0

    # Load computed plan
    computed_batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_plan", is_current=True, file_type="computed")
        .order_by("-uploaded_at")
        .first()
    )
    # Load uploaded plan (from Excel)
    uploaded_batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_plan", file_type="plan")
        .order_by("-uploaded_at")
        .first()
    )

    if not computed_batch:
        return Response(
            {"detail": "No computed R3SS plan found. Run r3ss/compute/ first."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if not uploaded_batch:
        return Response(
            {"detail": "No uploaded R3 SS.xlsx found. Upload the Excel plan first."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Build lookup: item_code → total_plan for each
    computed_rows = list(computed_batch.rows.values_list("data", flat=True))
    uploaded_rows = list(uploaded_batch.rows.values_list("data", flat=True))

    computed_lookup = {}
    for r in computed_rows:
        ic = (r.get("item_code") or "").strip().upper()
        if ic:
            computed_lookup[ic] = num0(r.get("total_plan"))

    uploaded_lookup = {}
    for r in uploaded_rows:
        ic = (r.get("item_code") or "").strip().upper()
        if ic:
            uploaded_lookup[ic] = num0(r.get("total_plan"))

    # Compare
    all_items = sorted(set(computed_lookup.keys()) | set(uploaded_lookup.keys()))

    variances = []
    total_computed = 0
    total_uploaded = 0
    exact_matches = 0
    within_1pct = 0

    for ic in all_items:
        cv = computed_lookup.get(ic, 0)
        uv = uploaded_lookup.get(ic, 0)
        total_computed += cv
        total_uploaded += uv

        diff = cv - uv
        pct = (abs(diff) / uv * 100) if uv > 0 else (100 if cv > 0 else 0)

        if diff == 0:
            exact_matches += 1
        if pct <= 1:
            within_1pct += 1

        if abs(diff) > 0.01:
            variances.append({
                "item_code": ic,
                "portal": round(cv, 2),
                "excel": round(uv, 2),
                "difference": round(diff, 2),
                "variance_pct": round(pct, 2),
            })

    # Sort by absolute variance descending
    variances.sort(key=lambda v: abs(v["difference"]), reverse=True)

    overall_diff = total_computed - total_uploaded
    overall_pct = (abs(overall_diff) / total_uploaded * 100) if total_uploaded > 0 else 0

    result = {
        "computed_batch_id": computed_batch.pk,
        "uploaded_batch_id": uploaded_batch.pk,
        "computed_at": computed_batch.uploaded_at.isoformat(),
        "uploaded_at": uploaded_batch.uploaded_at.isoformat(),
        "total_items_portal": len(computed_lookup),
        "total_items_excel": len(uploaded_lookup),
        "total_plan_portal": round(total_computed, 2),
        "total_plan_excel": round(total_uploaded, 2),
        "overall_difference": round(overall_diff, 2),
        "overall_variance_pct": round(overall_pct, 2),
        "exact_matches": exact_matches,
        "within_1_pct": within_1pct,
        "items_with_variance": len(variances),
        "gate": "PASS" if overall_pct < 5 else "REVIEW",
        "top_variances": variances[:50],
    }

    return Response(result)
