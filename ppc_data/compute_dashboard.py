"""L10 Dashboard compute engine — five consolidated dashboards + feedback loops.

Phase 10 deliverables:
  1. Plan vs Capacity    — product_group × date, with shortfall reason breakdown
  2. Adherence           — % planned / packed / dispatched vs frozen demand,
                           split OEM / Market / Fleetguard / Export
  3. Stock Levels        — FG, CP, RM, PM items in red / yellow / green / blue
  4. Shortage Board      — material short inside lead time, blocked plan dates
  5. OEE                 — Availability × Performance × Quality by section/line

Also:
  - Opening balance derivation (Phase 10 gate)
  - Feedback loops: yield% → MPS, backlog → DEMAND

Data sources follow the same _load_current_rows / PPCDataRow pattern used by
compute_mps, compute_r3ss, and compute_feasibility.
"""

import logging
from collections import defaultdict
from datetime import date

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .field_maps.helpers import num0, txt
from .models import (
    PPCCapacityFlag,
    PPCComputeResult,
    PPCDataRow,
    PPCDemandFreeze,
    PPCFeasibilityRun,
    PPCProductionEntry,
    PPCRejectionEntry,
    PPCRelease,
    PPCUploadBatch,
)

log = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────


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


def _build_lookup(rows, key_field, upper=True):
    """Build a dict mapping key_field value -> row (first match wins)."""
    lookup = {}
    for r in rows:
        k = txt(r.get(key_field))
        if upper:
            k = k.upper()
        if k and k not in lookup:
            lookup[k] = r
    return lookup


def _build_sum_lookup(rows, key_field, val_field, upper=True):
    """Sum val_field grouped by key_field."""
    lookup = defaultdict(float)
    for r in rows:
        k = txt(r.get(key_field))
        if upper:
            k = k.upper()
        if k:
            lookup[k] += num0(r.get(val_field))
    return dict(lookup)


def _parse_month(month):
    """Parse 'YYYY-MM' into (year, mo) ints.  Returns (None, None) on bad input."""
    try:
        year, mo = int(month[:4]), int(month[5:7])
        return year, mo
    except (ValueError, IndexError, TypeError):
        return None, None


def _month_date_range(month):
    """Return (first_day, last_day) as date objects for a 'YYYY-MM' string."""
    year, mo = _parse_month(month)
    if year is None:
        return None, None
    first_day = date(year, mo, 1)
    # Last day: move to the next month, subtract one day
    if mo == 12:
        last_day = date(year + 1, 1, 1)
    else:
        last_day = date(year, mo + 1, 1)
    from datetime import timedelta
    last_day = last_day - timedelta(days=1)
    return first_day, last_day


def _active_release(month):
    """Return the latest active PPCRelease for a month, or None."""
    return (
        PPCRelease.objects
        .filter(plan_month=month, status="active")
        .order_by("-released_at")
        .first()
    )


def _category_bucket(raw_category):
    """Normalise a customer_category / item_type value into one of the four
    standard buckets used by the adherence dashboard."""
    c = (raw_category or "").strip().upper()
    if "OEM" in c:
        return "OEM"
    if "FLEET" in c or "FG" == c:
        return "FLEETGUARD"
    if "EXPORT" in c or "EXP" in c:
        return "EXPORT"
    # Default bucket for MTS, MTO, aftermarket, etc.
    return "MARKET"


# ═══════════════════════════════════════════════════════════════
# Dashboard 1 — Plan vs Capacity
# ═══════════════════════════════════════════════════════════════


def compute_plan_vs_capacity(month):
    """Plan vs capacity by product_group by date.

    Loads from PPCCapacityFlag (feasibility flags already raised) plus
    the r3ss_plan day-wise rows and the capacity_ppp master.

    Returns dict with product_groups list, each with dates and overload info.
    """
    year, mo = _parse_month(month)
    if year is None:
        return {"ok": False, "reason": f"Invalid month format: {month}",
                "product_groups": []}

    # Load capacity master ── capacity_ppp (W1.6)
    cap_rows = _load_current_rows("capacity_ppp")
    cap_by_group = {}
    for r in cap_rows:
        pg = txt(r.get("product_group")).upper()
        if not pg:
            continue
        cap = num0(r.get("capacity_8h"))
        section = txt(r.get("section"))
        shifts = num0(r.get("shifts")) or 2.0
        daily_cap = cap * shifts
        if pg in cap_by_group:
            cap_by_group[pg]["daily_capacity"] += daily_cap
            cap_by_group[pg]["sections"].add(section)
        else:
            cap_by_group[pg] = {
                "daily_capacity": daily_cap,
                "sections": {section},
            }

    # Load r3ss plan rows (day-wise) ── current batch
    plan_rows = _load_current_rows("r3ss_plan")

    # Aggregate plan by product_group x date
    plan_by_pg_date = defaultdict(lambda: defaultdict(float))
    for r in plan_rows:
        pg = txt(r.get("product_group")).upper()
        if not pg:
            continue
        days = r.get("days") or {}
        for d, qty in days.items():
            if num0(qty) > 0:
                plan_by_pg_date[pg][d] += num0(qty)

    # Load feasibility flags for reason breakdowns
    latest_feas = (
        PPCFeasibilityRun.objects
        .filter(plan_month=month)
        .order_by("-started_at")
        .first()
    )
    flags_by_pg_date = defaultdict(list)
    if latest_feas:
        for flag in latest_feas.flags.filter(flag_type="capacity"):
            pg = (flag.product_group or "").upper()
            d = flag.date.isoformat() if flag.date else ""
            if pg and d:
                flags_by_pg_date[(pg, d)].append({
                    "reason_code": flag.reason_code or "",
                    "reason_text": flag.reason_text or "",
                    "resolved": flag.resolved,
                    "overload_pct": round(flag.overload_pct, 1),
                })

    # Build output
    product_groups = []
    all_pgs = sorted(set(list(cap_by_group.keys()) + list(plan_by_pg_date.keys())))
    for pg in all_pgs:
        cap_info = cap_by_group.get(pg, {})
        daily_cap = cap_info.get("daily_capacity", 0.0)
        sections = sorted(cap_info.get("sections", set()))
        dates_data = []
        for d in sorted(plan_by_pg_date.get(pg, {}).keys()):
            planned = plan_by_pg_date[pg][d]
            shortfall = max(0.0, planned - daily_cap)
            util_pct = (planned / daily_cap * 100) if daily_cap > 0 else 0.0
            flags = flags_by_pg_date.get((pg, d), [])
            dates_data.append({
                "date": d,
                "planned": round(planned, 1),
                "capacity": round(daily_cap, 1),
                "shortfall": round(shortfall, 1),
                "utilization_pct": round(util_pct, 1),
                "overloaded": shortfall > 0,
                "flags": flags,
            })
        overloaded_days = sum(1 for dd in dates_data if dd["overloaded"])
        product_groups.append({
            "product_group": pg,
            "sections": sections,
            "daily_capacity": round(daily_cap, 1),
            "dates": dates_data,
            "total_planned": round(
                sum(dd["planned"] for dd in dates_data), 1),
            "total_shortfall": round(
                sum(dd["shortfall"] for dd in dates_data), 1),
            "overloaded_days": overloaded_days,
        })

    return {
        "ok": True,
        "month": month,
        "product_groups": product_groups,
        "summary": {
            "groups_count": len(product_groups),
            "groups_overloaded": sum(
                1 for pg in product_groups if pg["overloaded_days"] > 0),
        },
    }


# ═══════════════════════════════════════════════════════════════
# Dashboard 2 — Adherence
# ═══════════════════════════════════════════════════════════════


def compute_adherence_dashboard(month):
    """Adherence split by category (OEM / Market / Fleetguard / Export).

    Measures % planned, % packed (produced), % dispatched against the
    frozen initial demand.

    Returns dict with categories breakdown and by_date breakdown.
    """
    year, mo = _parse_month(month)
    if year is None:
        return {"ok": False, "reason": f"Invalid month format: {month}",
                "categories": [], "by_date": []}

    first_day, last_day = _month_date_range(month)

    # 1. Frozen initial demand per item
    freezes = PPCDemandFreeze.objects.filter(month=month)
    demand_by_item = {}
    for f in freezes:
        ic = f.item_code.strip().upper()
        demand_by_item[ic] = f.initial_qty

    if not demand_by_item:
        return {"ok": False, "reason": f"No frozen demand for {month}.",
                "categories": [], "by_date": []}

    # 2. Latest release → plan quantities
    release = _active_release(month)
    plan_by_item = defaultdict(float)
    if release and release.snapshot_batch:
        snap_rows = list(
            PPCDataRow.objects
            .filter(batch=release.snapshot_batch)
            .values_list("data", flat=True)
        )
        for r in snap_rows:
            ic = txt(r.get("item_code")).upper()
            if ic:
                plan_by_item[ic] += num0(r.get("total_plan"))
    else:
        # Fallback: current r3ss_plan
        plan_rows = _load_current_rows("r3ss_plan")
        for r in plan_rows:
            ic = txt(r.get("item_code")).upper()
            if ic:
                plan_by_item[ic] += num0(r.get("total_plan"))

    # 3. Production (packed) per item this month
    prod_qs = (
        PPCProductionEntry.objects
        .filter(date__gte=first_day, date__lte=last_day)
        .values("item_code")
        .annotate(total=Sum("produced_qty"))
    )
    produced_by_item = {}
    for e in prod_qs:
        ic = e["item_code"].strip().upper()
        produced_by_item[ic] = e["total"] or 0.0

    # 4. Dispatch per item this month
    dispatch_rows = _load_current_rows("erp_dispatch")
    dispatched_by_item = defaultdict(float)
    for r in dispatch_rows:
        ic = txt(r.get("item_code")).upper()
        qty = num0(r.get("qty")) or num0(r.get("closing"))
        if ic:
            dispatched_by_item[ic] += qty

    # 5. Category assignment per item (from family_hierarchy)
    family_rows = _load_current_rows("family_hierarchy")
    family_lookup = _build_lookup(family_rows, "item_code")

    # 6. Build category aggregates
    cat_totals = defaultdict(lambda: {
        "demand": 0.0, "planned": 0.0, "produced": 0.0, "dispatched": 0.0,
        "item_count": 0,
    })

    for ic, initial_demand in demand_by_item.items():
        fam = family_lookup.get(ic, {})
        raw_cat = txt(fam.get("customer_category") or fam.get("item_type"))
        bucket = _category_bucket(raw_cat)

        cat_totals[bucket]["demand"] += initial_demand
        cat_totals[bucket]["planned"] += plan_by_item.get(ic, 0.0)
        cat_totals[bucket]["produced"] += produced_by_item.get(ic, 0.0)
        cat_totals[bucket]["dispatched"] += dispatched_by_item.get(ic, 0.0)
        cat_totals[bucket]["item_count"] += 1

    categories = []
    for cat in ["OEM", "MARKET", "FLEETGUARD", "EXPORT"]:
        t = cat_totals.get(cat, {
            "demand": 0.0, "planned": 0.0, "produced": 0.0,
            "dispatched": 0.0, "item_count": 0,
        })
        dem = t["demand"]
        categories.append({
            "category": cat,
            "item_count": t["item_count"],
            "demand": round(dem, 1),
            "planned": round(t["planned"], 1),
            "produced": round(t["produced"], 1),
            "dispatched": round(t["dispatched"], 1),
            "planned_pct": round(t["planned"] / dem * 100, 1) if dem > 0 else 0.0,
            "produced_pct": round(t["produced"] / dem * 100, 1) if dem > 0 else 0.0,
            "dispatched_pct": round(t["dispatched"] / dem * 100, 1) if dem > 0 else 0.0,
        })

    # 7. Daily production breakdown (for trend chart)
    daily_prod = (
        PPCProductionEntry.objects
        .filter(date__gte=first_day, date__lte=last_day)
        .values("date")
        .annotate(total=Sum("produced_qty"))
        .order_by("date")
    )
    by_date = []
    cumulative = 0.0
    total_demand_all = sum(demand_by_item.values())
    for entry in daily_prod:
        cumulative += entry["total"] or 0.0
        by_date.append({
            "date": entry["date"].isoformat(),
            "daily_produced": round(entry["total"] or 0.0, 1),
            "cumulative_produced": round(cumulative, 1),
            "cumulative_pct": round(
                cumulative / total_demand_all * 100, 1
            ) if total_demand_all > 0 else 0.0,
        })

    # 8. Grand totals
    grand_demand = sum(c["demand"] for c in categories)
    grand_planned = sum(c["planned"] for c in categories)
    grand_produced = sum(c["produced"] for c in categories)
    grand_dispatched = sum(c["dispatched"] for c in categories)

    return {
        "ok": True,
        "month": month,
        "categories": categories,
        "by_date": by_date,
        "totals": {
            "demand": round(grand_demand, 1),
            "planned": round(grand_planned, 1),
            "produced": round(grand_produced, 1),
            "dispatched": round(grand_dispatched, 1),
            "planned_pct": round(
                grand_planned / grand_demand * 100, 1
            ) if grand_demand > 0 else 0.0,
            "produced_pct": round(
                grand_produced / grand_demand * 100, 1
            ) if grand_demand > 0 else 0.0,
            "dispatched_pct": round(
                grand_dispatched / grand_demand * 100, 1
            ) if grand_demand > 0 else 0.0,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Dashboard 3 — Stock Levels
# ═══════════════════════════════════════════════════════════════


def _classify_stock_level(stock_qty, green_level):
    """Classify a stock quantity into a colour band.

    blue   = stock > 2x green   (excess)
    green  = stock >= green      (healthy)
    yellow = stock >= 0.5x green (caution)
    red    = stock < 0.5x green  (critical)

    If green_level is zero or missing, default to yellow (unknown policy).
    """
    if green_level <= 0:
        # No policy defined — treat any positive stock as yellow, zero as red
        return "yellow" if stock_qty > 0 else "red"
    if stock_qty > 2 * green_level:
        return "blue"
    if stock_qty >= green_level:
        return "green"
    if stock_qty >= 0.5 * green_level:
        return "yellow"
    return "red"


def compute_stock_levels():
    """Stock levels — count items in red / yellow / green / blue.

    Loads from erp_fg_stock, erp_cp_stock, erp_rm_stock, erp_pm_stock
    and stock_policy (green_level).

    Returns dict with fg / cp / rm / pm counts per level.
    """
    # Load stock policy for green_level thresholds
    policy_rows = _load_current_rows("stock_policy")
    policy_lookup = _build_lookup(policy_rows, "item_code")

    stock_tables = {
        "fg": "erp_fg_stock",
        "cp": "erp_cp_stock",
        "rm": "erp_rm_stock",
        "pm": "erp_pm_stock",
    }

    result = {}

    for stock_type, table_key in stock_tables.items():
        rows = _load_current_rows(table_key)

        # Aggregate by item_code (some tables have multiple location rows)
        agg = defaultdict(float)
        for r in rows:
            ic = txt(r.get("item_code")).upper()
            qty = num0(r.get("closing")) or num0(r.get("qty")) or num0(r.get("stock"))
            if ic:
                agg[ic] += qty

        counts = {"red": 0, "yellow": 0, "green": 0, "blue": 0}
        items_detail = {"red": [], "yellow": [], "green": [], "blue": []}

        for ic, qty in sorted(agg.items()):
            pol = policy_lookup.get(ic, {})
            green_level = num0(pol.get("green_level") or pol.get("blue_level"))
            level = _classify_stock_level(qty, green_level)
            counts[level] += 1
            # Keep first 50 items per level for drill-down
            if len(items_detail[level]) < 50:
                items_detail[level].append({
                    "item_code": ic,
                    "stock": round(qty, 1),
                    "green_level": round(green_level, 1),
                })

        total_items = sum(counts.values())
        result[stock_type] = {
            "total_items": total_items,
            "counts": counts,
            "pct": {
                lvl: round(cnt / total_items * 100, 1) if total_items > 0 else 0.0
                for lvl, cnt in counts.items()
            },
            "items": items_detail,
        }

    return {
        "ok": True,
        "fg": result.get("fg", {}),
        "cp": result.get("cp", {}),
        "rm": result.get("rm", {}),
        "pm": result.get("pm", {}),
        "summary": {
            stock_type: data.get("counts", {})
            for stock_type, data in result.items()
        },
    }


# ═══════════════════════════════════════════════════════════════
# Dashboard 4 — Shortage Board
# ═══════════════════════════════════════════════════════════════


def compute_shortage_board(month):
    """Material shortages inside lead time.

    Loads from material_shortage batch (uploaded or computed) and
    lead_time master. Cross-references against r3ss_plan to identify
    which plan dates are blocked.

    Returns list of shortage items with blocked dates.
    """
    year, mo = _parse_month(month)
    if year is None:
        return {"ok": False, "reason": f"Invalid month format: {month}",
                "shortages": []}

    first_day, last_day = _month_date_range(month)

    # Load material shortage data
    shortage_rows = _load_current_rows("material_shortage")

    # Load lead time master
    lt_rows = _load_current_rows("lead_time")
    lt_lookup = _build_lookup(lt_rows, "part_code")
    # Also index by item_code / sku
    for r in lt_rows:
        ic = txt(r.get("sku")).upper()
        if ic and ic not in lt_lookup:
            lt_lookup[ic] = r
        ic2 = txt(r.get("item_code")).upper()
        if ic2 and ic2 not in lt_lookup:
            lt_lookup[ic2] = r

    # Load r3ss plan for blocked-date cross-reference
    plan_rows = _load_current_rows("r3ss_plan")
    # Build item -> list of plan dates
    plan_dates_by_item = defaultdict(list)
    for r in plan_rows:
        ic = txt(r.get("item_code")).upper()
        days = r.get("days") or {}
        for d, qty in days.items():
            if num0(qty) > 0:
                plan_dates_by_item[ic].append(d)

    # Also build parent -> child mapping from BOM
    bom_rows = _load_current_rows("bom_master")
    parent_by_child = defaultdict(set)
    for r in bom_rows:
        parent = txt(r.get("parent_item")).upper()
        child = txt(r.get("child_item") or r.get("component")).upper()
        if parent and child:
            parent_by_child[child].add(parent)

    shortages = []
    for r in shortage_rows:
        ic = txt(r.get("item_code") or r.get("material_code")).upper()
        if not ic:
            continue

        short_qty = num0(r.get("short_qty") or r.get("shortage"))
        if short_qty <= 0:
            continue

        required_date = txt(r.get("required_date") or r.get("need_date"))
        supplier = txt(r.get("supplier") or r.get("vendor"))
        po_number = txt(r.get("po_number") or r.get("po"))
        expected_date = txt(r.get("expected_date") or r.get("eta"))
        description = txt(r.get("description"))

        # Lead time for this material
        lt_row = lt_lookup.get(ic, {})
        proc_lt = num0(lt_row.get("proc_lt") or lt_row.get("max_lt"))

        # Check if inside lead time (shortage cannot be resolved in time)
        inside_lt = False
        if required_date and proc_lt > 0:
            try:
                req_dt = date.fromisoformat(required_date[:10])
                days_remaining = (req_dt - date.today()).days
                inside_lt = days_remaining < proc_lt
            except (ValueError, TypeError):
                pass

        # Find blocked plan dates (parent items that use this material)
        blocked_dates = []
        parents = parent_by_child.get(ic, set())
        for parent_ic in parents:
            for d in sorted(plan_dates_by_item.get(parent_ic, [])):
                blocked_dates.append({
                    "date": d,
                    "parent_item": parent_ic,
                })
        # Also check if the shortage item itself has plan dates
        for d in sorted(plan_dates_by_item.get(ic, [])):
            blocked_dates.append({
                "date": d,
                "parent_item": ic,
            })

        shortages.append({
            "item_code": ic,
            "description": description,
            "short_qty": round(short_qty, 1),
            "required_date": required_date,
            "expected_date": expected_date,
            "supplier": supplier,
            "po_number": po_number,
            "procurement_lt": round(proc_lt, 0),
            "inside_lead_time": inside_lt,
            "blocked_dates": blocked_dates[:30],
            "blocked_count": len(blocked_dates),
        })

    # Sort: inside-lead-time items first, then by short_qty descending
    shortages.sort(key=lambda s: (not s["inside_lead_time"], -s["short_qty"]))

    inside_lt_count = sum(1 for s in shortages if s["inside_lead_time"])

    return {
        "ok": True,
        "month": month,
        "shortages": shortages,
        "summary": {
            "total_shortages": len(shortages),
            "inside_lead_time": inside_lt_count,
            "outside_lead_time": len(shortages) - inside_lt_count,
            "total_blocked_dates": sum(
                s["blocked_count"] for s in shortages),
        },
    }


# ═══════════════════════════════════════════════════════════════
# Dashboard 5 — OEE
# ═══════════════════════════════════════════════════════════════


def compute_oee(month):
    """OEE by section and line.

    OEE = Availability x Performance x Quality

    Availability = (planned_time - downtime) / planned_time
    Performance  = actual_output / (planned_time x ideal_rate)
    Quality      = (actual - rejected) / actual

    Loads from PPCProductionEntry + PPCRejectionEntry + capacity_ppp.

    Returns dict with sections list.
    """
    year, mo = _parse_month(month)
    if year is None:
        return {"ok": False, "reason": f"Invalid month format: {month}",
                "sections": []}

    first_day, last_day = _month_date_range(month)

    # Load capacity master for planned time and ideal rate
    cap_rows = _load_current_rows("capacity_ppp")
    # Build section -> {capacity_8h, shifts, ideal_rate}
    cap_by_section = {}
    for r in cap_rows:
        sec = txt(r.get("section")).upper()
        if not sec:
            continue
        cap_8h = num0(r.get("capacity_8h"))
        shifts = num0(r.get("shifts")) or 2.0
        ideal_rate = num0(r.get("ideal_rate") or r.get("rated_capacity"))
        if sec in cap_by_section:
            cap_by_section[sec]["capacity_8h"] += cap_8h
            cap_by_section[sec]["ideal_rate"] += ideal_rate
        else:
            cap_by_section[sec] = {
                "capacity_8h": cap_8h,
                "shifts": shifts,
                "ideal_rate": ideal_rate,
            }

    # Load working calendar to count planned working days
    cal_rows = _load_current_rows("working_calendar")
    working_dates = set()
    for r in cal_rows:
        d = r.get("date", "")
        is_w = r.get("is_working")
        if d and str(is_w).strip().lower() in ("1", "true", "yes", "y"):
            try:
                ds = d.isoformat()[:10] if hasattr(d, "isoformat") else str(d)[:10]
                working_dates.add(ds)
            except Exception:
                pass

    # If no calendar loaded, estimate from Mon-Sat
    if not working_dates and first_day:
        d = first_day
        from datetime import timedelta
        while d <= last_day:
            if d.weekday() != 6:  # Not Sunday
                working_dates.add(d.isoformat())
            d += timedelta(days=1)

    working_days_count = len(working_dates)

    # Load downtime data (if available)
    downtime_rows = _load_current_rows("downtime_log")
    downtime_by_section = defaultdict(float)
    for r in downtime_rows:
        sec = txt(r.get("section")).upper()
        hrs = num0(r.get("downtime_hours") or r.get("hours"))
        if sec:
            downtime_by_section[sec] += hrs

    # Production totals by section
    prod_qs = (
        PPCProductionEntry.objects
        .filter(date__gte=first_day, date__lte=last_day)
        .values("section")
        .annotate(total=Sum("produced_qty"))
    )
    actual_by_section = {}
    for e in prod_qs:
        sec = (e["section"] or "").strip().upper()
        actual_by_section[sec] = e["total"] or 0.0

    # Rejection totals by section
    rej_qs = (
        PPCRejectionEntry.objects
        .filter(date__gte=first_day, date__lte=last_day)
        .values("section")
        .annotate(total=Sum("rejected_qty"))
    )
    rejected_by_section = {}
    for e in rej_qs:
        sec = (e["section"] or "").strip().upper()
        rejected_by_section[sec] = e["total"] or 0.0

    # Build per-section OEE
    all_sections = sorted(
        set(list(cap_by_section.keys()) +
            list(actual_by_section.keys()))
    )

    sections = []
    for sec in all_sections:
        cap = cap_by_section.get(sec, {})
        cap_8h = cap.get("capacity_8h", 0.0)
        shifts = cap.get("shifts", 2.0)
        ideal_rate = cap.get("ideal_rate", 0.0)

        # Planned time = working_days x shifts x 8 hours
        planned_time_hrs = working_days_count * shifts * 8.0
        downtime_hrs = downtime_by_section.get(sec, 0.0)

        actual_output = actual_by_section.get(sec, 0.0)
        rejected = rejected_by_section.get(sec, 0.0)

        # Availability
        if planned_time_hrs > 0:
            available_time_hrs = planned_time_hrs - downtime_hrs
            availability = available_time_hrs / planned_time_hrs
        else:
            availability = 0.0

        # Performance
        # ideal_rate is units per 8h shift; ideal output = ideal_rate x shifts x working_days
        ideal_output = ideal_rate * shifts * working_days_count if ideal_rate > 0 else 0.0
        # Alternative: use capacity_8h x shifts x working_days
        if ideal_output <= 0:
            ideal_output = cap_8h * shifts * working_days_count
        performance = (actual_output / ideal_output) if ideal_output > 0 else 0.0

        # Quality
        if actual_output > 0:
            quality = (actual_output - rejected) / actual_output
        else:
            quality = 0.0 if rejected > 0 else 1.0

        # OEE
        oee = availability * performance * quality

        sections.append({
            "section": sec,
            "planned_time_hrs": round(planned_time_hrs, 1),
            "downtime_hrs": round(downtime_hrs, 1),
            "availability": round(max(0.0, min(1.0, availability)), 4),
            "availability_pct": round(
                max(0.0, min(100.0, availability * 100)), 1),
            "actual_output": round(actual_output, 1),
            "ideal_output": round(ideal_output, 1),
            "performance": round(max(0.0, performance), 4),
            "performance_pct": round(max(0.0, performance * 100), 1),
            "rejected": round(rejected, 1),
            "quality": round(max(0.0, min(1.0, quality)), 4),
            "quality_pct": round(
                max(0.0, min(100.0, quality * 100)), 1),
            "oee": round(max(0.0, oee), 4),
            "oee_pct": round(max(0.0, oee * 100), 1),
        })

    # Grand average (weighted by actual_output)
    total_actual = sum(s["actual_output"] for s in sections)
    if total_actual > 0:
        weighted_oee = sum(
            s["oee"] * s["actual_output"] for s in sections
        ) / total_actual
    else:
        weighted_oee = 0.0

    return {
        "ok": True,
        "month": month,
        "working_days": working_days_count,
        "sections": sections,
        "overall_oee_pct": round(weighted_oee * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════
# Opening balance derivation (Phase 10 gate)
# ═══════════════════════════════════════════════════════════════


def derive_opening_balance(month):
    """Derive opening balance for the next cycle.

    Phase 10 gate: "opening balance for the next cycle is derived, not typed."

    opening_next = erp_fg_stock closing (current month)
    closing_wip  = erp_prod_semi closing (current month)

    Returns dict with items list.
    """
    # FG closing stock → becomes next month's opening
    fg_rows = _load_current_rows("erp_fg_stock")
    fg_agg = defaultdict(float)
    for r in fg_rows:
        ic = txt(r.get("item_code")).upper()
        closing = num0(r.get("closing"))
        if ic:
            fg_agg[ic] += closing

    # WIP closing → becomes next month's opening WIP
    wip_rows = _load_current_rows("erp_prod_semi")
    wip_agg = defaultdict(float)
    for r in wip_rows:
        ic = txt(r.get("item_code")).upper()
        closing = num0(r.get("closing")) or num0(r.get("receipt"))
        if ic:
            wip_agg[ic] += closing

    # Item descriptions for context
    family_rows = _load_current_rows("family_hierarchy")
    family_lookup = _build_lookup(family_rows, "item_code")

    item_rows = _load_current_rows("item_master")
    item_lookup = _build_lookup(item_rows, "item_code")

    # Build items list
    all_items = sorted(set(list(fg_agg.keys()) + list(wip_agg.keys())))
    items = []
    for ic in all_items:
        fg_closing = fg_agg.get(ic, 0.0)
        wip_closing = wip_agg.get(ic, 0.0)
        fam = family_lookup.get(ic, {})
        item = item_lookup.get(ic, {})

        items.append({
            "item_code": ic,
            "description": txt(item.get("description") or
                               fam.get("description")),
            "family": txt(fam.get("family")),
            "product_group": txt(fam.get("product_group")),
            "fg_closing": round(fg_closing, 2),
            "wip_closing": round(wip_closing, 2),
            "next_opening_fg": round(fg_closing, 2),
            "next_opening_wip": round(wip_closing, 2),
        })

    # Compute next month label
    year, mo = _parse_month(month)
    if year is not None:
        if mo == 12:
            next_month = f"{year + 1}-01"
        else:
            next_month = f"{year}-{mo + 1:02d}"
    else:
        next_month = "unknown"

    return {
        "ok": True,
        "current_month": month,
        "next_month": next_month,
        "items": items,
        "summary": {
            "total_items": len(items),
            "items_with_fg": sum(1 for i in items if i["fg_closing"] > 0),
            "items_with_wip": sum(1 for i in items if i["wip_closing"] > 0),
            "total_fg_closing": round(sum(i["fg_closing"] for i in items), 1),
            "total_wip_closing": round(sum(i["wip_closing"] for i in items), 1),
        },
    }


# ═══════════════════════════════════════════════════════════════
# Feedback loop 1 — Yield factor → MPS
# ═══════════════════════════════════════════════════════════════


def compute_yield_factor(month):
    """Rejection% per family -> yield factor for next MPS.

    yield_factor = 1 - (rejected / produced)
    Used by compute_mps to inflate net requirement:
        adjusted_demand = demand / yield_factor

    Returns dict with families list.
    """
    year, mo = _parse_month(month)
    if year is None:
        return {"ok": False, "reason": f"Invalid month format: {month}",
                "families": []}

    first_day, last_day = _month_date_range(month)

    # Family lookup for each item_code
    family_rows = _load_current_rows("family_hierarchy")
    family_lookup = _build_lookup(family_rows, "item_code")

    # Production by item
    prod_qs = (
        PPCProductionEntry.objects
        .filter(date__gte=first_day, date__lte=last_day)
        .values("item_code")
        .annotate(total=Sum("produced_qty"))
    )
    produced_by_item = {}
    for e in prod_qs:
        ic = e["item_code"].strip().upper()
        produced_by_item[ic] = e["total"] or 0.0

    # Rejection by item
    rej_qs = (
        PPCRejectionEntry.objects
        .filter(date__gte=first_day, date__lte=last_day)
        .values("item_code")
        .annotate(total=Sum("rejected_qty"))
    )
    rejected_by_item = {}
    for e in rej_qs:
        ic = e["item_code"].strip().upper()
        rejected_by_item[ic] = e["total"] or 0.0

    # Aggregate by family
    family_prod = defaultdict(float)
    family_rej = defaultdict(float)
    all_items = sorted(
        set(list(produced_by_item.keys()) + list(rejected_by_item.keys()))
    )
    for ic in all_items:
        fam = family_lookup.get(ic, {})
        family_name = txt(fam.get("family")).upper() or "UNKNOWN"
        family_prod[family_name] += produced_by_item.get(ic, 0.0)
        family_rej[family_name] += rejected_by_item.get(ic, 0.0)

    families = []
    for fam_name in sorted(family_prod.keys()):
        produced = family_prod[fam_name]
        rejected = family_rej.get(fam_name, 0.0)

        if produced > 0:
            rejection_pct = rejected / produced * 100
            yield_factor = 1.0 - (rejected / produced)
        else:
            rejection_pct = 0.0
            yield_factor = 1.0  # No production, assume no yield loss

        # Clamp yield factor to a sane range (at least 50%)
        yield_factor = max(0.5, min(1.0, yield_factor))

        families.append({
            "family": fam_name,
            "produced": round(produced, 1),
            "rejected": round(rejected, 1),
            "rejection_pct": round(rejection_pct, 2),
            "yield_factor": round(yield_factor, 4),
        })

    return {
        "ok": True,
        "month": month,
        "families": families,
        "summary": {
            "families_count": len(families),
            "total_produced": round(sum(f["produced"] for f in families), 1),
            "total_rejected": round(sum(f["rejected"] for f in families), 1),
            "avg_yield": round(
                sum(f["yield_factor"] for f in families) / len(families), 4
            ) if families else 1.0,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Feedback loop 2 — Backlog → DEMAND
# ═══════════════════════════════════════════════════════════════


def compute_backlog_demand(month):
    """Unmet plan -> backlog additions for next demand cycle.

    backlog = max(0, planned - actual) per item.
    These become additional demand in the next month's freeze.

    Returns dict with items list.
    """
    year, mo = _parse_month(month)
    if year is None:
        return {"ok": False, "reason": f"Invalid month format: {month}",
                "items": []}

    first_day, last_day = _month_date_range(month)

    # Planned per item (from r3ss_plan or release snapshot)
    release = _active_release(month)
    plan_by_item = defaultdict(float)
    if release and release.snapshot_batch:
        snap_rows = list(
            PPCDataRow.objects
            .filter(batch=release.snapshot_batch)
            .values_list("data", flat=True)
        )
        for r in snap_rows:
            ic = txt(r.get("item_code")).upper()
            if ic:
                plan_by_item[ic] += num0(r.get("total_plan"))
    else:
        plan_rows = _load_current_rows("r3ss_plan")
        for r in plan_rows:
            ic = txt(r.get("item_code")).upper()
            if ic:
                plan_by_item[ic] += num0(r.get("total_plan"))

    # Actual production per item
    prod_qs = (
        PPCProductionEntry.objects
        .filter(date__gte=first_day, date__lte=last_day)
        .values("item_code")
        .annotate(total=Sum("produced_qty"))
    )
    actual_by_item = {}
    for e in prod_qs:
        ic = e["item_code"].strip().upper()
        actual_by_item[ic] = e["total"] or 0.0

    # Family/description lookups
    family_rows = _load_current_rows("family_hierarchy")
    family_lookup = _build_lookup(family_rows, "item_code")
    item_rows = _load_current_rows("item_master")
    item_lookup = _build_lookup(item_rows, "item_code")

    # Compute backlogs
    items = []
    for ic in sorted(plan_by_item.keys()):
        planned = plan_by_item[ic]
        actual = actual_by_item.get(ic, 0.0)
        backlog = max(0.0, planned - actual)

        if backlog <= 0:
            continue

        fam = family_lookup.get(ic, {})
        item = item_lookup.get(ic, {})

        items.append({
            "item_code": ic,
            "description": txt(item.get("description") or
                               fam.get("description")),
            "family": txt(fam.get("family")),
            "product_group": txt(fam.get("product_group")),
            "category": _category_bucket(
                txt(fam.get("customer_category") or fam.get("item_type"))),
            "planned": round(planned, 1),
            "actual": round(actual, 1),
            "backlog": round(backlog, 1),
            "completion_pct": round(
                actual / planned * 100, 1) if planned > 0 else 0.0,
        })

    # Sort by backlog descending
    items.sort(key=lambda i: -i["backlog"])

    # Compute next month label
    if mo == 12:
        next_month = f"{year + 1}-01"
    else:
        next_month = f"{year}-{mo + 1:02d}"

    total_backlog = sum(i["backlog"] for i in items)
    total_planned = sum(plan_by_item.values())

    return {
        "ok": True,
        "month": month,
        "next_month": next_month,
        "items": items,
        "summary": {
            "items_with_backlog": len(items),
            "total_backlog": round(total_backlog, 1),
            "total_planned": round(total_planned, 1),
            "backlog_pct": round(
                total_backlog / total_planned * 100, 1
            ) if total_planned > 0 else 0.0,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Main orchestrator
# ═══════════════════════════════════════════════════════════════


def _store_result(batch, key, data):
    """Upsert a PPCComputeResult row for the given batch + key."""
    obj, created = PPCComputeResult.objects.update_or_create(
        batch=batch,
        compute_key=key,
        defaults={
            "tiles": data.get("summary", data.get("totals", {})),
            "tile_rows": data,
        },
    )
    return obj, created


def refresh_dashboard(month, user=None):
    """Main orchestrator — runs all dashboards and stores each in PPCComputeResult.

    PPCComputeResult has:
        batch (FK PPCUploadBatch), compute_key (CharField),
        tiles (JSONField), tile_rows (JSONField), computed_at (auto).

    Store each dashboard under key like 'dashboard_capacity_2026-09', etc.

    Returns summary dict with counts/status for each.
    """
    log.info("Dashboard refresh starting for month=%s", month)
    started = timezone.now()

    year, mo = _parse_month(month)
    if year is None:
        return {"ok": False, "reason": f"Invalid month format: {month}"}

    # Create a batch to anchor the compute results
    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key="dashboard_compute", is_current=True,
        ).update(is_current=False)

        batch = PPCUploadBatch.objects.create(
            uploader=user,
            source_file="",
            original_filename=f"Dashboard Compute ({month})",
            file_type="computed",
            level="L10",
            table_key="dashboard_compute",
            row_count=0,
            is_current=True,
            notes=f"Dashboard refresh at {started.isoformat()} for {month}",
        )

    results = {}
    errors = []

    # Dashboard 1: Plan vs Capacity
    try:
        d1 = compute_plan_vs_capacity(month)
        _store_result(batch, f"dashboard_capacity_{month}", d1)
        results["plan_vs_capacity"] = {
            "ok": d1.get("ok", False),
            "groups": len(d1.get("product_groups", [])),
        }
    except Exception as exc:
        log.exception("Dashboard 1 (plan_vs_capacity) failed")
        errors.append(f"plan_vs_capacity: {exc}")
        results["plan_vs_capacity"] = {"ok": False, "error": str(exc)}

    # Dashboard 2: Adherence
    try:
        d2 = compute_adherence_dashboard(month)
        _store_result(batch, f"dashboard_adherence_{month}", d2)
        results["adherence"] = {
            "ok": d2.get("ok", False),
            "categories": len(d2.get("categories", [])),
        }
    except Exception as exc:
        log.exception("Dashboard 2 (adherence) failed")
        errors.append(f"adherence: {exc}")
        results["adherence"] = {"ok": False, "error": str(exc)}

    # Dashboard 3: Stock Levels
    try:
        d3 = compute_stock_levels()
        _store_result(batch, f"dashboard_stock_{month}", d3)
        results["stock_levels"] = {
            "ok": d3.get("ok", False),
            "fg_items": d3.get("fg", {}).get("total_items", 0),
            "rm_items": d3.get("rm", {}).get("total_items", 0),
        }
    except Exception as exc:
        log.exception("Dashboard 3 (stock_levels) failed")
        errors.append(f"stock_levels: {exc}")
        results["stock_levels"] = {"ok": False, "error": str(exc)}

    # Dashboard 4: Shortage Board
    try:
        d4 = compute_shortage_board(month)
        _store_result(batch, f"dashboard_shortage_{month}", d4)
        results["shortage_board"] = {
            "ok": d4.get("ok", False),
            "shortages": len(d4.get("shortages", [])),
        }
    except Exception as exc:
        log.exception("Dashboard 4 (shortage_board) failed")
        errors.append(f"shortage_board: {exc}")
        results["shortage_board"] = {"ok": False, "error": str(exc)}

    # Dashboard 5: OEE
    try:
        d5 = compute_oee(month)
        _store_result(batch, f"dashboard_oee_{month}", d5)
        results["oee"] = {
            "ok": d5.get("ok", False),
            "sections": len(d5.get("sections", [])),
            "overall_oee_pct": d5.get("overall_oee_pct", 0.0),
        }
    except Exception as exc:
        log.exception("Dashboard 5 (oee) failed")
        errors.append(f"oee: {exc}")
        results["oee"] = {"ok": False, "error": str(exc)}

    # Opening balance derivation (Phase 10 gate)
    try:
        d6 = derive_opening_balance(month)
        _store_result(batch, f"opening_balance_{month}", d6)
        results["opening_balance"] = {
            "ok": d6.get("ok", False),
            "items": len(d6.get("items", [])),
            "next_month": d6.get("next_month"),
        }
    except Exception as exc:
        log.exception("Opening balance derivation failed")
        errors.append(f"opening_balance: {exc}")
        results["opening_balance"] = {"ok": False, "error": str(exc)}

    # Feedback: Yield factor
    try:
        d7 = compute_yield_factor(month)
        _store_result(batch, f"yield_factor_{month}", d7)
        results["yield_factor"] = {
            "ok": d7.get("ok", False),
            "families": len(d7.get("families", [])),
        }
    except Exception as exc:
        log.exception("Yield factor compute failed")
        errors.append(f"yield_factor: {exc}")
        results["yield_factor"] = {"ok": False, "error": str(exc)}

    # Feedback: Backlog demand
    try:
        d8 = compute_backlog_demand(month)
        _store_result(batch, f"backlog_demand_{month}", d8)
        results["backlog_demand"] = {
            "ok": d8.get("ok", False),
            "items_with_backlog": len(d8.get("items", [])),
        }
    except Exception as exc:
        log.exception("Backlog demand compute failed")
        errors.append(f"backlog_demand: {exc}")
        results["backlog_demand"] = {"ok": False, "error": str(exc)}

    # Update batch row count
    result_count = PPCComputeResult.objects.filter(batch=batch).count()
    batch.row_count = result_count
    batch.save(update_fields=["row_count"])

    elapsed = (timezone.now() - started).total_seconds()
    ok_count = sum(1 for r in results.values() if r.get("ok"))
    log.info(
        "Dashboard refresh done: %d/%d ok, %d errors, %.1fs",
        ok_count, len(results), len(errors), elapsed,
    )

    return {
        "ok": len(errors) == 0,
        "month": month,
        "batch_id": batch.pk,
        "dashboards": results,
        "ok_count": ok_count,
        "total_count": len(results),
        "errors": errors,
        "elapsed_seconds": round(elapsed, 2),
    }
