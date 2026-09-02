"""REST endpoints for L7 Material — BOM explosion and stock allocation.

  POST /api/ppc-data/material/explode/      run BOM explosion for a release
  POST /api/ppc-data/material/allocate/     run stock allocation for a release
  GET  /api/ppc-data/material/status/       latest material status for a release
  GET  /api/ppc-data/material/shortages/    shortage report

Decision #5: BOM explosion runs in DB only (exceeds Google Sheets' limits).
"""

import logging

from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import PPCDataRow, PPCRelease, PPCUploadBatch

log = logging.getLogger(__name__)


@api_view(["POST"])
def material_explode(request):
    """Run BOM explosion for a release.

    POST body:
      release_id  — ID of the active PPCRelease
    """
    from .compute_material import run_bom_explosion

    release_id = request.data.get("release_id")
    if not release_id:
        return Response({"detail": "release_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        summary = run_bom_explosion(release_id)
    except PPCRelease.DoesNotExist:
        return Response({"detail": "Release not found."}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        log.exception("BOM explosion failed: %s", exc)
        return Response({"detail": f"BOM explosion failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    notify(
        f"BOM Explosion — {summary['plan_month']}#{summary['release_number']}",
        f"{request.user.get_username()} ran BOM explosion: "
        f"{summary['unique_components']} components from {summary['fg_items_with_bom']} FG items. "
        f"{summary['fg_items_without_bom']} items had no BOM.",
    )

    # Push to Google Sheets via n8n (non-blocking — failures don't break the API)
    try:
        from .sheet_sync import sync_material_to_ppc_sheet
        release = PPCRelease.objects.get(pk=release_id)
        sheet_result = sync_material_to_ppc_sheet(release)
        summary["sheet_sync"] = sheet_result
    except Exception as exc:
        log.warning("Sheet sync after BOM explosion failed (non-fatal): %s", exc)
        summary["sheet_sync"] = {"attempted": False, "error": str(exc)}

    return Response(summary, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def material_allocate(request):
    """Run stock allocation for a release.

    POST body:
      release_id  — ID of the active PPCRelease
    """
    from .compute_material import run_stock_allocation

    release_id = request.data.get("release_id")
    if not release_id:
        return Response({"detail": "release_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        summary = run_stock_allocation(release_id)
    except PPCRelease.DoesNotExist:
        return Response({"detail": "Release not found."}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        log.exception("Stock allocation failed: %s", exc)
        return Response({"detail": f"Stock allocation failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    notify(
        f"Stock Allocation complete",
        f"{request.user.get_username()}: {summary['components_with_shortage']} components "
        f"have shortages out of {summary['total_components']}.",
    )

    # Push BOM + shortage data to Google Sheets (non-blocking)
    try:
        from .sheet_sync import sync_bom_to_sheet
        release = PPCRelease.objects.get(pk=release_id)
        sheet_result = sync_bom_to_sheet(release)
        summary["sheet_sync"] = sheet_result
    except Exception as exc:
        log.warning("Sheet sync after allocation failed (non-fatal): %s", exc)
        summary["sheet_sync"] = {"attempted": False, "error": str(exc)}

    return Response(summary, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def material_sheet_sync(request):
    """Manually trigger Google Sheet sync for a release's material data.

    POST body:
      release_id  — ID of the PPCRelease (or omit for latest active)
    """
    from .sheet_sync import sync_bom_to_sheet, sync_material_to_ppc_sheet

    release_id = request.data.get("release_id")
    if release_id:
        try:
            release = PPCRelease.objects.get(pk=release_id)
        except PPCRelease.DoesNotExist:
            return Response({"detail": "Release not found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        release = PPCRelease.objects.filter(status="active").order_by("-released_at").first()
        if release is None:
            return Response({"detail": "No active release."}, status=status.HTTP_404_NOT_FOUND)

    results = {
        "ppc_planning_sheet": sync_material_to_ppc_sheet(release),
        "pipeline_sheet": sync_bom_to_sheet(release),
    }

    return Response({
        "release_id": release.pk,
        "plan_month": release.plan_month,
        "sync_results": results,
    })


@api_view(["GET"])
def material_status(request):
    """Get latest material status for a release.

    Query params:
      ?release_id=123  — specific release (or latest active)
    """
    release_id = request.GET.get("release_id")

    if release_id:
        try:
            release = PPCRelease.objects.get(pk=release_id)
        except PPCRelease.DoesNotExist:
            return Response({"detail": "Release not found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        release = PPCRelease.objects.filter(status="active").order_by("-released_at").first()
        if release is None:
            return Response({"loaded": False, "bom": None, "allocation": None})

    # BOM explosion batch
    bom_batch = (
        PPCUploadBatch.objects
        .filter(table_key="bom_requirement", notes__contains=f"release_id={release.pk}")
        .order_by("-uploaded_at")
        .first()
    )

    # Stock allocation batch
    alloc_batch = (
        PPCUploadBatch.objects
        .filter(table_key="material_shortage", notes__contains=f"release_id={release.pk}")
        .order_by("-uploaded_at")
        .first()
    )

    bom_info = None
    if bom_batch:
        bom_info = {
            "batch_id": bom_batch.pk,
            "row_count": bom_batch.row_count,
            "uploaded_at": bom_batch.uploaded_at.isoformat(),
        }

    alloc_info = None
    if alloc_batch:
        alloc_info = {
            "batch_id": alloc_batch.pk,
            "row_count": alloc_batch.row_count,
            "uploaded_at": alloc_batch.uploaded_at.isoformat(),
        }

    return Response({
        "loaded": True,
        "release_id": release.pk,
        "plan_month": release.plan_month,
        "release_number": release.release_number,
        "bom": bom_info,
        "allocation": alloc_info,
    })


@api_view(["GET"])
def material_shortages(request):
    """Get shortage report — components with insufficient stock.

    Query params:
      ?release_id=123  — specific release (or latest active)
      ?type=RM         — filter by component type (RM/CP/PM)
      ?limit=500
      ?search=xyz
    """
    release_id = request.GET.get("release_id")

    if release_id:
        try:
            release = PPCRelease.objects.get(pk=release_id)
        except PPCRelease.DoesNotExist:
            return Response({"detail": "Release not found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        release = PPCRelease.objects.filter(status="active").order_by("-released_at").first()
        if release is None:
            return Response({"detail": "No active release."}, status=status.HTTP_404_NOT_FOUND)

    alloc_batch = (
        PPCUploadBatch.objects
        .filter(table_key="material_shortage", notes__contains=f"release_id={release.pk}")
        .order_by("-uploaded_at")
        .first()
    )
    if alloc_batch is None:
        return Response({"detail": "No stock allocation found. Run allocation first."}, status=status.HTTP_404_NOT_FOUND)

    try:
        limit = max(1, min(5000, int(request.GET.get("limit", 500))))
    except (ValueError, TypeError):
        limit = 500

    rows_qs = alloc_batch.rows.all()

    search = request.GET.get("search", "").strip()
    if search:
        rows_qs = rows_qs.filter(data__icontains=search)

    comp_type = request.GET.get("type", "").strip().upper()

    rows = []
    for sr, data in rows_qs.values_list("sr_no", "data"):
        if comp_type and data.get("component_type", "").upper() != comp_type:
            continue
        # Strip day-level detail for the list view
        row = {k: v for k, v in data.items() if k != "days"}
        rows.append({"sr_no": sr, "data": row})
        if len(rows) >= limit:
            break

    shortages_only = [r for r in rows if r["data"].get("has_shortage")]

    return Response({
        "release_id": release.pk,
        "plan_month": release.plan_month,
        "total_components": alloc_batch.row_count,
        "showing": len(rows),
        "shortages_count": len(shortages_only),
        "rows": rows,
    })
