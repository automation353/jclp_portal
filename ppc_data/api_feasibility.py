"""REST endpoints for L5 Feasibility and L6 Release.

  POST /api/ppc-data/feasibility/run/         run feasibility check on current plan
  GET  /api/ppc-data/feasibility/status/       latest feasibility run status + flags
  POST /api/ppc-data/feasibility/resolve/      resolve a capacity flag (enter reason)
  POST /api/ppc-data/feasibility/approve/      approve plan (all flags must be resolved)

  POST /api/ppc-data/release/create/           create immutable release from approved plan
  GET  /api/ppc-data/release/list/             list releases for a month
  GET  /api/ppc-data/release/<id>/             release detail
  POST /api/ppc-data/release/<id>/recall/      recall a release

Rule 5: capacity is a gate — plan cannot release without passing.
"""

import logging

from django.db import transaction
from django.utils import timezone
from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import (
    PPCCapacityFlag,
    PPCDataRow,
    PPCFeasibilityRun,
    PPCRelease,
    PPCUploadBatch,
)

log = logging.getLogger(__name__)


# ── L5 Feasibility ──────────────────────────────────────────────


@api_view(["POST"])
def feasibility_run(request):
    """Run feasibility checks on the current R3SS plan.

    Creates a new PPCFeasibilityRun and populates PPCCapacityFlag rows.
    """
    from .compute_feasibility import run_feasibility

    plan_batch = (
        PPCUploadBatch.objects
        .filter(table_key="r3ss_plan", is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if plan_batch is None:
        return Response(
            {"detail": "No R3SS plan loaded. Upload R3 SS.xlsx first."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        run = run_feasibility(plan_batch.pk)
    except Exception as exc:
        log.exception("Feasibility run failed: %s", exc)
        return Response(
            {"detail": f"Feasibility check failed: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    notify(
        f"Feasibility check — {run.plan_month}",
        f"{request.user.get_username()} ran feasibility: {run.summary.get('total_flags', 0)} flags. "
        f"Status: {run.status}.",
    )

    return Response(_run_to_dict(run), status=status.HTTP_201_CREATED)


@api_view(["GET"])
def feasibility_status(request):
    """Get the latest feasibility run and its flags.

    Query params:
      ?plan_month=2026-08  — filter by month (optional)
    """
    qs = PPCFeasibilityRun.objects.all()
    month = request.GET.get("plan_month", "").strip()
    if month:
        qs = qs.filter(plan_month=month)

    run = qs.order_by("-started_at").first()
    if run is None:
        return Response({"loaded": False, "run": None, "flags": []})

    flags = list(run.flags.all().values(
        "id", "flag_type", "date", "product_group", "section",
        "item_code", "planned_qty", "capacity_qty", "overload_pct",
        "detail", "reason_code", "reason_text", "resolved",
        "resolved_by__username", "resolved_at",
    ))

    return Response({
        "loaded": True,
        "run": _run_to_dict(run),
        "flags": flags,
    })


@api_view(["POST"])
def feasibility_resolve(request):
    """Resolve a capacity flag by entering a reason code.

    POST body:
      flag_id      — ID of the PPCCapacityFlag
      reason_code  — reason code string
      reason_text  — optional explanation
    """
    flag_id = request.data.get("flag_id")
    reason_code = request.data.get("reason_code", "").strip()
    reason_text = request.data.get("reason_text", "").strip()

    if not flag_id:
        return Response({"detail": "flag_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not reason_code:
        return Response({"detail": "reason_code is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        flag = PPCCapacityFlag.objects.get(pk=flag_id)
    except PPCCapacityFlag.DoesNotExist:
        return Response({"detail": "Flag not found."}, status=status.HTTP_404_NOT_FOUND)

    flag.reason_code = reason_code
    flag.reason_text = reason_text
    flag.resolved = True
    flag.resolved_by = request.user
    flag.resolved_at = timezone.now()
    flag.save()

    # Check if all flags in the run are now resolved
    run = flag.run
    unresolved = run.flags.filter(resolved=False).count()

    return Response({
        "flag_id": flag.id,
        "resolved": True,
        "unresolved_remaining": unresolved,
        "run_status": run.status,
    })


@api_view(["POST"])
def feasibility_approve(request):
    """Approve a feasibility run. All flags must be resolved first.

    POST body:
      run_id  — ID of the PPCFeasibilityRun
    """
    run_id = request.data.get("run_id")
    if not run_id:
        return Response({"detail": "run_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        run = PPCFeasibilityRun.objects.get(pk=run_id)
    except PPCFeasibilityRun.DoesNotExist:
        return Response({"detail": "Run not found."}, status=status.HTTP_404_NOT_FOUND)

    if run.status == "approved":
        return Response({"detail": "Already approved."})

    unresolved = run.flags.filter(resolved=False).count()
    if unresolved > 0:
        return Response(
            {"detail": f"{unresolved} unresolved flags remain. Resolve all before approving."},
            status=status.HTTP_409_CONFLICT,
        )

    run.status = "approved"
    run.approved_by = request.user
    run.approved_at = timezone.now()
    run.save()

    notify(
        f"Plan APPROVED — {run.plan_month}",
        f"{request.user.get_username()} approved the plan for {run.plan_month}. "
        f"Ready for release.",
    )

    return Response(_run_to_dict(run))


# ── L6 Release ──────────────────────────────────────────────────


@api_view(["POST"])
def release_create(request):
    """Create an immutable release from an approved feasibility run.

    POST body:
      run_id  — ID of the approved PPCFeasibilityRun
    """
    run_id = request.data.get("run_id")
    if not run_id:
        return Response({"detail": "run_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        run = PPCFeasibilityRun.objects.get(pk=run_id)
    except PPCFeasibilityRun.DoesNotExist:
        return Response({"detail": "Run not found."}, status=status.HTTP_404_NOT_FOUND)

    if run.status != "approved":
        return Response(
            {"detail": f"Run is '{run.status}', not approved. Cannot release."},
            status=status.HTTP_409_CONFLICT,
        )

    # Get next release number for this month
    last = (
        PPCRelease.objects
        .filter(plan_month=run.plan_month)
        .order_by("-release_number")
        .first()
    )
    next_num = (last.release_number + 1) if last else 1

    plan_batch = run.plan_batch
    plan_rows = list(plan_batch.rows.values_list("data", flat=True))

    # Build summary
    from .field_maps.helpers import num0 as n0
    from collections import defaultdict
    sections = defaultdict(lambda: {"items": 0, "total_plan": 0})
    dates_seen = set()
    for r in plan_rows:
        sec = r.get("section", "Unknown")
        sections[sec]["items"] += 1
        sections[sec]["total_plan"] += n0(r.get("total_plan"))
        for d in r.get("days", {}):
            dates_seen.add(d)

    summary = {
        "total_items": len(plan_rows),
        "total_plan": sum(s["total_plan"] for s in sections.values()),
        "sections": dict(sections),
        "date_range": [min(dates_seen), max(dates_seen)] if dates_seen else [],
    }

    with transaction.atomic():
        # Create snapshot batch for release rows
        snapshot_batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file="",
            original_filename=f"Release {run.plan_month}#{next_num}",
            file_type="release",
            level="L6",
            table_key="release_rows",
            row_count=len(plan_rows),
            is_current=True,
            notes=f"Snapshot from approved plan batch #{plan_batch.pk}",
        )

        # Copy plan rows as release snapshot
        PPCDataRow.objects.bulk_create([
            PPCDataRow(
                batch=snapshot_batch,
                sr_no=i + 1,
                table_key="release_rows",
                data=row,
            )
            for i, row in enumerate(plan_rows)
        ], batch_size=500)

        release = PPCRelease.objects.create(
            plan_month=run.plan_month,
            release_number=next_num,
            feasibility_run=run,
            source_batch=plan_batch,
            snapshot_batch=snapshot_batch,
            released_by=request.user,
            status="active",
            row_count=len(plan_rows),
            summary=summary,
        )

    notify(
        f"Plan RELEASED — {run.plan_month}#{next_num}",
        f"{request.user.get_username()} released the plan for {run.plan_month} "
        f"(release #{next_num}): {len(plan_rows)} items.",
    )

    return Response({
        "release_id": release.pk,
        "plan_month": release.plan_month,
        "release_number": release.release_number,
        "status": release.status,
        "row_count": release.row_count,
        "summary": release.summary,
        "released_at": release.released_at.isoformat(),
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def release_list(request):
    """List releases, optionally filtered by month.

    Query params:
      ?plan_month=2026-08
    """
    qs = PPCRelease.objects.all()
    month = request.GET.get("plan_month", "").strip()
    if month:
        qs = qs.filter(plan_month=month)

    releases = []
    for r in qs[:50]:
        releases.append({
            "id": r.pk,
            "plan_month": r.plan_month,
            "release_number": r.release_number,
            "status": r.status,
            "row_count": r.row_count,
            "released_by": str(r.released_by) if r.released_by else None,
            "released_at": r.released_at.isoformat(),
            "summary": r.summary,
        })

    return Response({"releases": releases})


@api_view(["GET"])
def release_detail(request, release_id):
    """Get release detail including snapshot rows.

    Query params:
      ?limit=500  — max rows
      ?search=xyz — filter by item code / description
    """
    try:
        release = PPCRelease.objects.get(pk=release_id)
    except PPCRelease.DoesNotExist:
        return Response({"detail": "Release not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        limit = max(1, min(5000, int(request.GET.get("limit", 500))))
    except (ValueError, TypeError):
        limit = 500

    rows_qs = PPCDataRow.objects.filter(batch=release.snapshot_batch)
    search = request.GET.get("search", "").strip()
    if search:
        rows_qs = rows_qs.filter(data__icontains=search)

    rows = [
        {"sr_no": sr, "data": {k: v for k, v in d.items() if k not in ("_day_sum_mismatch", "_plan_month")}}
        for sr, d in rows_qs[:limit].values_list("sr_no", "data")
    ]

    return Response({
        "release": {
            "id": release.pk,
            "plan_month": release.plan_month,
            "release_number": release.release_number,
            "status": release.status,
            "row_count": release.row_count,
            "released_by": str(release.released_by) if release.released_by else None,
            "released_at": release.released_at.isoformat(),
            "summary": release.summary,
        },
        "rows": rows,
        "truncated": release.row_count > limit,
    })


@api_view(["POST"])
def release_recall(request, release_id):
    """Recall (soft-cancel) a release. The snapshot stays for audit.

    POST body:
      reason  — recall reason (required)
    """
    try:
        release = PPCRelease.objects.get(pk=release_id)
    except PPCRelease.DoesNotExist:
        return Response({"detail": "Release not found."}, status=status.HTTP_404_NOT_FOUND)

    if release.status == "recalled":
        return Response({"detail": "Already recalled."})

    reason = request.data.get("reason", "").strip()
    if not reason:
        return Response({"detail": "reason is required."}, status=status.HTTP_400_BAD_REQUEST)

    release.status = "recalled"
    release.recalled_by = request.user
    release.recalled_at = timezone.now()
    release.recall_reason = reason
    release.save()

    notify(
        f"Release RECALLED — {release.plan_month}#{release.release_number}",
        f"{request.user.get_username()} recalled release #{release.release_number}: {reason}",
    )

    return Response({
        "release_id": release.pk,
        "status": "recalled",
        "recall_reason": reason,
    })


# ── Helpers ──────────────────────────────────────────────────────


def _run_to_dict(run):
    return {
        "id": run.pk,
        "plan_month": run.plan_month,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "approved_by": str(run.approved_by) if run.approved_by else None,
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "summary": run.summary,
        "plan_batch_id": run.plan_batch_id,
    }
