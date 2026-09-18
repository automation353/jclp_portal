"""REST endpoints for L8 Execution & Feedback.

  POST /api/ppc-data/production/entry/          daily production entry
  GET  /api/ppc-data/production/entries/         list entries (filterable)
  GET  /api/ppc-data/production/adherence/       plan vs actual adherence
  POST /api/ppc-data/production/rejection/       rejection entry
  GET  /api/ppc-data/production/rejections/      list rejections
  GET  /api/ppc-data/production/scorecard/       PPC scorecard summary

L8 feeds back into the next cycle:
  - Adherence % = actual / planned × 100
  - Rejection % feeds into MPS yield factor
  - Unmade quantity becomes backlog demand
"""

import logging
from collections import defaultdict
from datetime import datetime

from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .field_maps.helpers import num0
from .models import (
    PPCDataRow,
    PPCProductionEntry,
    PPCRejectionEntry,
    PPCRelease,
)

log = logging.getLogger(__name__)


# ── Production Entry ─────────────────────────────────────────────


@api_view(["POST"])
def production_entry(request):
    """Create or update a production entry.

    POST body:
      date         — YYYY-MM-DD
      item_code    — item code
      section      — production section
      produced_qty — quantity produced
      shift        — shift label (optional, default "general")
      notes        — optional notes
    """
    date_str = request.data.get("date")
    item_code = request.data.get("item_code", "").strip()
    section = request.data.get("section", "").strip()
    produced_qty = request.data.get("produced_qty")
    shift = request.data.get("shift", "general").strip() or "general"
    notes = request.data.get("notes", "").strip()

    if not date_str or not item_code or not section or produced_qty is None:
        return Response(
            {"detail": "date, item_code, section, and produced_qty are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        qty = float(produced_qty)
    except (ValueError, TypeError):
        return Response({"detail": "produced_qty must be a number."}, status=status.HTTP_400_BAD_REQUEST)

    # Find active release for context
    release = PPCRelease.objects.filter(status="active").order_by("-released_at").first()

    entry, created = PPCProductionEntry.objects.update_or_create(
        date=date_str,
        item_code=item_code.upper(),
        section=section.upper(),
        shift=shift,
        defaults={
            "produced_qty": qty,
            "release": release,
            "entered_by": request.user,
            "notes": notes,
        },
    )

    return Response({
        "id": entry.pk,
        "date": str(entry.date),
        "item_code": entry.item_code,
        "section": entry.section,
        "shift": entry.shift,
        "produced_qty": entry.produced_qty,
        "created": created,
    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(["POST"])
def production_bulk_entry(request):
    """Bulk create/update production entries.

    POST body:
      entries — list of {date, item_code, section, produced_qty, shift?, notes?}
    """
    entries_data = request.data.get("entries", [])
    if not isinstance(entries_data, list) or not entries_data:
        return Response({"detail": "entries list is required."}, status=status.HTTP_400_BAD_REQUEST)

    release = PPCRelease.objects.filter(status="active").order_by("-released_at").first()
    created_count = 0
    updated_count = 0
    errors = []

    for i, e in enumerate(entries_data):
        try:
            _, created = PPCProductionEntry.objects.update_or_create(
                date=e["date"],
                item_code=e["item_code"].strip().upper(),
                section=e["section"].strip().upper(),
                shift=e.get("shift", "general").strip() or "general",
                defaults={
                    "produced_qty": float(e["produced_qty"]),
                    "release": release,
                    "entered_by": request.user,
                    "notes": e.get("notes", ""),
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
        except Exception as exc:
            errors.append({"index": i, "error": str(exc)})

    return Response({
        "created": created_count,
        "updated": updated_count,
        "errors": errors,
        "total": len(entries_data),
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def production_entries(request):
    """List production entries, filterable.

    Query params:
      ?date=2026-08-15      — specific date
      ?section=SSWD          — filter by section
      ?item_code=JC-001      — filter by item
      ?date_from=2026-08-01  — date range start
      ?date_to=2026-08-31    — date range end
      ?limit=500
    """
    qs = PPCProductionEntry.objects.all()

    date = request.GET.get("date")
    if date:
        qs = qs.filter(date=date)

    section = request.GET.get("section", "").strip()
    if section:
        qs = qs.filter(section__iexact=section)

    item = request.GET.get("item_code", "").strip()
    if item:
        qs = qs.filter(item_code__icontains=item)

    date_from = request.GET.get("date_from")
    if date_from:
        qs = qs.filter(date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        qs = qs.filter(date__lte=date_to)

    try:
        limit = max(1, min(5000, int(request.GET.get("limit", 500))))
    except (ValueError, TypeError):
        limit = 500

    entries = []
    for e in qs[:limit]:
        entries.append({
            "id": e.pk,
            "date": str(e.date),
            "item_code": e.item_code,
            "section": e.section,
            "shift": e.shift,
            "produced_qty": e.produced_qty,
            "entered_by": str(e.entered_by) if e.entered_by else None,
            "entered_at": e.entered_at.isoformat(),
            "notes": e.notes,
        })

    return Response({
        "count": qs.count(),
        "entries": entries,
        "truncated": qs.count() > limit,
    })


# ── Adherence ────────────────────────────────────────────────────


@api_view(["GET"])
def production_adherence(request):
    """Plan vs actual adherence report.

    Compares released plan quantities against actual production entries.
    Returns adherence % per section, per date, per item.

    Query params:
      ?release_id=123      — specific release (or latest active)
      ?section=SSWD         — filter by section
      ?date_from=2026-08-01
      ?date_to=2026-08-31
      ?group_by=section     — section / date / item (default: section)
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

    group_by = request.GET.get("group_by", "section").strip()
    section_filter = request.GET.get("section", "").strip()
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    # Load planned quantities from release
    plan_rows = list(
        PPCDataRow.objects
        .filter(batch=release.snapshot_batch)
        .values_list("data", flat=True)
    )

    # Build planned map: (item_code, date) → planned_qty; (section, date) → planned_qty
    plan_by_item_date = defaultdict(float)
    plan_by_section_date = defaultdict(float)
    plan_by_section = defaultdict(float)
    plan_by_date = defaultdict(float)

    for r in plan_rows:
        item = (r.get("item_code") or "").upper()
        sec = (r.get("section") or "Unknown").upper()
        days = r.get("days", {})

        if section_filter and sec != section_filter.upper():
            continue

        for d, qty in days.items():
            q = num0(qty)
            if q <= 0:
                continue
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue

            plan_by_item_date[(item, d)] += q
            plan_by_section_date[(sec, d)] += q
            plan_by_section[sec] += q
            plan_by_date[d] += q

    # Load actual production
    prod_qs = PPCProductionEntry.objects.all()
    if section_filter:
        prod_qs = prod_qs.filter(section__iexact=section_filter)
    if date_from:
        prod_qs = prod_qs.filter(date__gte=date_from)
    if date_to:
        prod_qs = prod_qs.filter(date__lte=date_to)

    actual_by_item_date = defaultdict(float)
    actual_by_section_date = defaultdict(float)
    actual_by_section = defaultdict(float)
    actual_by_date = defaultdict(float)

    for e in prod_qs:
        item = e.item_code.upper()
        sec = e.section.upper()
        d = str(e.date)
        q = e.produced_qty

        actual_by_item_date[(item, d)] += q
        actual_by_section_date[(sec, d)] += q
        actual_by_section[sec] += q
        actual_by_date[d] += q

    # Build adherence rows based on group_by
    rows = []

    if group_by == "section":
        for sec in sorted(plan_by_section):
            planned = plan_by_section[sec]
            actual = actual_by_section.get(sec, 0)
            pct = (actual / planned * 100) if planned > 0 else 0
            rows.append({
                "section": sec,
                "planned": round(planned, 1),
                "actual": round(actual, 1),
                "adherence_pct": round(pct, 1),
                "gap": round(planned - actual, 1),
            })

    elif group_by == "date":
        for d in sorted(plan_by_date):
            planned = plan_by_date[d]
            actual = actual_by_date.get(d, 0)
            pct = (actual / planned * 100) if planned > 0 else 0
            rows.append({
                "date": d,
                "planned": round(planned, 1),
                "actual": round(actual, 1),
                "adherence_pct": round(pct, 1),
                "gap": round(planned - actual, 1),
            })

    elif group_by == "item":
        # Aggregate by item across all dates
        plan_by_item = defaultdict(float)
        actual_by_item = defaultdict(float)
        for (item, d), q in plan_by_item_date.items():
            plan_by_item[item] += q
        for (item, d), q in actual_by_item_date.items():
            actual_by_item[item] += q

        for item in sorted(plan_by_item):
            planned = plan_by_item[item]
            actual = actual_by_item.get(item, 0)
            pct = (actual / planned * 100) if planned > 0 else 0
            rows.append({
                "item_code": item,
                "planned": round(planned, 1),
                "actual": round(actual, 1),
                "adherence_pct": round(pct, 1),
                "gap": round(planned - actual, 1),
            })

    # Overall summary
    total_planned = sum(plan_by_section.values())
    total_actual = sum(actual_by_section.values())
    overall_pct = (total_actual / total_planned * 100) if total_planned > 0 else 0

    return Response({
        "release_id": release.pk,
        "plan_month": release.plan_month,
        "release_number": release.release_number,
        "group_by": group_by,
        "overall": {
            "planned": round(total_planned, 1),
            "actual": round(total_actual, 1),
            "adherence_pct": round(overall_pct, 1),
            "gap": round(total_planned - total_actual, 1),
        },
        "rows": rows,
    })


# ── Rejection Entry ──────────────────────────────────────────────


@api_view(["POST"])
def rejection_entry(request):
    """Create a rejection entry.

    POST body:
      date         — YYYY-MM-DD
      item_code    — item code
      section      — section
      stage        — operation stage (from W1.5)
      rejected_qty — quantity rejected
      reason_code  — reason code (from W1.17)
      reason_text  — optional explanation
      notes        — optional notes
    """
    required = ["date", "item_code", "section", "stage", "rejected_qty", "reason_code"]
    missing = [f for f in required if not request.data.get(f)]
    if missing:
        return Response(
            {"detail": f"Missing fields: {', '.join(missing)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        qty = float(request.data["rejected_qty"])
    except (ValueError, TypeError):
        return Response({"detail": "rejected_qty must be a number."}, status=status.HTTP_400_BAD_REQUEST)

    entry = PPCRejectionEntry.objects.create(
        date=request.data["date"],
        item_code=request.data["item_code"].strip().upper(),
        section=request.data["section"].strip().upper(),
        stage=request.data["stage"].strip(),
        rejected_qty=qty,
        reason_code=request.data["reason_code"].strip(),
        reason_text=request.data.get("reason_text", "").strip(),
        entered_by=request.user,
        notes=request.data.get("notes", "").strip(),
    )

    return Response({
        "id": entry.pk,
        "date": str(entry.date),
        "item_code": entry.item_code,
        "section": entry.section,
        "stage": entry.stage,
        "rejected_qty": entry.rejected_qty,
        "reason_code": entry.reason_code,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def rejection_list(request):
    """List rejections, filterable.

    Query params:
      ?date=2026-08-15
      ?section=SSWD
      ?item_code=JC-001
      ?date_from=2026-08-01
      ?date_to=2026-08-31
      ?limit=500
    """
    qs = PPCRejectionEntry.objects.all()

    date = request.GET.get("date")
    if date:
        qs = qs.filter(date=date)
    section = request.GET.get("section", "").strip()
    if section:
        qs = qs.filter(section__iexact=section)
    item = request.GET.get("item_code", "").strip()
    if item:
        qs = qs.filter(item_code__icontains=item)
    date_from = request.GET.get("date_from")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    date_to = request.GET.get("date_to")
    if date_to:
        qs = qs.filter(date__lte=date_to)

    try:
        limit = max(1, min(5000, int(request.GET.get("limit", 500))))
    except (ValueError, TypeError):
        limit = 500

    entries = []
    for e in qs[:limit]:
        entries.append({
            "id": e.pk,
            "date": str(e.date),
            "item_code": e.item_code,
            "section": e.section,
            "stage": e.stage,
            "rejected_qty": e.rejected_qty,
            "reason_code": e.reason_code,
            "reason_text": e.reason_text,
            "entered_by": str(e.entered_by) if e.entered_by else None,
            "entered_at": e.entered_at.isoformat(),
        })

    return Response({
        "count": qs.count(),
        "entries": entries,
    })


@api_view(["GET"])
def production_scorecard(request):
    """PPC scorecard summary — the core metric.

    Combines adherence, rejection %, and backlog into a single view.

    Query params:
      ?plan_month=2026-08
    """
    month = request.GET.get("plan_month", "").strip()

    release = None
    if month:
        release = PPCRelease.objects.filter(plan_month=month, status="active").order_by("-released_at").first()
    else:
        release = PPCRelease.objects.filter(status="active").order_by("-released_at").first()

    if release is None:
        return Response({"loaded": False})

    # Adherence
    plan_rows = list(
        PPCDataRow.objects
        .filter(batch=release.snapshot_batch)
        .values_list("data", flat=True)
    )
    total_planned = sum(num0(r.get("total_plan")) for r in plan_rows)

    total_actual = (
        PPCProductionEntry.objects
        .filter(release=release)
        .aggregate(total=Sum("produced_qty"))["total"]
    ) or 0

    adherence_pct = (total_actual / total_planned * 100) if total_planned > 0 else 0

    # Rejections
    total_rejected = (
        PPCRejectionEntry.objects
        .filter(
            date__gte=f"{release.plan_month}-01",
            date__lte=f"{release.plan_month}-31",
        )
        .aggregate(total=Sum("rejected_qty"))["total"]
    ) or 0

    rejection_pct = (total_rejected / total_actual * 100) if total_actual > 0 else 0

    # Backlog = planned - actual (positive means unmade)
    backlog = max(0, total_planned - total_actual)

    # Section breakdown
    section_plan = defaultdict(float)
    for r in plan_rows:
        sec = (r.get("section") or "Unknown").upper()
        section_plan[sec] += num0(r.get("total_plan"))

    section_actual = defaultdict(float)
    for e in PPCProductionEntry.objects.filter(release=release):
        section_actual[e.section.upper()] += e.produced_qty

    sections = []
    for sec in sorted(section_plan):
        p = section_plan[sec]
        a = section_actual.get(sec, 0)
        adh = (a / p * 100) if p > 0 else 0
        sections.append({
            "section": sec,
            "planned": round(p, 1),
            "actual": round(a, 1),
            "adherence_pct": round(adh, 1),
            "gap": round(p - a, 1),
        })

    # ── Sheet sync (fire-and-forget) ──
    sheet_sync_result = None
    if request.GET.get("sync_sheet") == "true":
        try:
            from .sheet_sync import sync_scorecard_to_sheet
            sheet_sync_result = sync_scorecard_to_sheet(release)
            log.info("Scorecard sheet sync: %s", sheet_sync_result)
        except Exception:
            log.exception("Scorecard sheet sync failed (non-blocking)")
            sheet_sync_result = {"attempted": True, "ok": False, "error": "exception"}

    resp = {
        "loaded": True,
        "release_id": release.pk,
        "plan_month": release.plan_month,
        "release_number": release.release_number,
        "overall": {
            "planned": round(total_planned, 1),
            "actual": round(total_actual, 1),
            "adherence_pct": round(adherence_pct, 1),
            "backlog": round(backlog, 1),
            "rejected": round(total_rejected, 1),
            "rejection_pct": round(rejection_pct, 1),
        },
        "sections": sections,
    }
    if sheet_sync_result is not None:
        resp["sheet_sync"] = sheet_sync_result

    return Response(resp)
