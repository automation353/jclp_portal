"""L5 Feasibility compute engine.

Rule 5: capacity is a gate — plan cannot release without passing.

Three checks:
  1. Capacity check — day × product_group plan vs W1.6 capacity
  2. Machine loading — day × machine utilization via W1.4 route + W1.7 machines
  3. EBQ qualification — family plan vs W1.8 minimum batch
"""

import logging
from collections import defaultdict
from datetime import date as dt_date

from django.utils import timezone

from .field_maps.helpers import num0, txt
from .models import (
    PPCCapacityFlag,
    PPCDataRow,
    PPCFeasibilityRun,
    PPCUploadBatch,
)

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


# ── 1. Capacity check ───────────────────────────────────────────


def _capacity_check(run, plan_rows):
    """Compare day-wise plan qty (by product_group) against capacity master.

    capacity_ppp (W1.6) has capacity_8h per product_group per section.
    We aggregate R3SS day quantities by product_group, then compare.
    """
    # Load capacity master
    cap_rows = _load_current_rows("capacity_ppp")
    if not cap_rows:
        log.warning("Feasibility: no capacity_ppp data loaded — skipping capacity check")
        return 0

    # Build capacity lookup: (product_group) → daily capacity
    # Use capacity_8h as the per-shift daily capacity
    cap_by_group = {}
    for r in cap_rows:
        pg = txt(r.get("product_group")).upper()
        if not pg:
            continue
        cap = num0(r.get("capacity_8h"))
        sec = txt(r.get("section"))
        key = pg
        if key in cap_by_group:
            cap_by_group[key]["capacity"] += cap
            cap_by_group[key]["sections"].add(sec)
        else:
            cap_by_group[key] = {"capacity": cap, "sections": {sec}}

    # Aggregate plan by product_group × date
    plan_by_group_date = defaultdict(lambda: defaultdict(float))
    for r in plan_rows:
        pg = txt(r.get("product_group")).upper()
        if not pg:
            continue
        days = r.get("days", {})
        for d, qty in days.items():
            if qty and num0(qty) > 0:
                plan_by_group_date[pg][d] += num0(qty)

    # Compare and flag overloads
    flags_created = 0
    for pg, dates in plan_by_group_date.items():
        cap_info = cap_by_group.get(pg)
        if not cap_info or cap_info["capacity"] <= 0:
            # No capacity data for this group — flag as unknown
            for d, planned in dates.items():
                if planned > 0:
                    PPCCapacityFlag.objects.create(
                        run=run,
                        flag_type="capacity",
                        date=d,
                        product_group=pg,
                        section=", ".join(cap_info["sections"]) if cap_info else "",
                        planned_qty=planned,
                        capacity_qty=0,
                        overload_pct=100,
                        detail={"note": "No capacity data for this product group"},
                    )
                    flags_created += 1
            continue

        daily_cap = cap_info["capacity"]
        sections = ", ".join(cap_info["sections"])

        for d, planned in sorted(dates.items()):
            if planned > daily_cap:
                overload = ((planned - daily_cap) / daily_cap) * 100
                PPCCapacityFlag.objects.create(
                    run=run,
                    flag_type="capacity",
                    date=d,
                    product_group=pg,
                    section=sections,
                    planned_qty=planned,
                    capacity_qty=daily_cap,
                    overload_pct=round(overload, 1),
                    detail={"daily_capacity": daily_cap},
                )
                flags_created += 1

    return flags_created


# ── 2. Machine loading ──────────────────────────────────────────


def _machine_loading(run, plan_rows):
    """Map plan to machines via route master → flag overloaded machines.

    route_master (W1.4): family → operations → machine_line + cycle_time
    machine_master (W1.7): machine_code → capacity_shift
    """
    route_rows = _load_current_rows("route_master")
    machine_rows = _load_current_rows("machine_master")

    if not route_rows:
        log.warning("Feasibility: no route_master loaded — skipping machine check")
        return 0
    if not machine_rows:
        log.warning("Feasibility: no machine_master loaded — skipping machine check")
        return 0

    # Build route lookup: family → [(machine_line, cycle_time_minutes)]
    route_by_family = defaultdict(list)
    for r in route_rows:
        fam = txt(r.get("family")).upper()
        mach = txt(r.get("machine_line"))
        ct = num0(r.get("cycle_time"))
        if fam and mach:
            route_by_family[fam].append((mach, ct))

    # Build machine capacity lookup: machine_code → capacity_shift (qty per shift)
    mach_capacity = {}
    for r in machine_rows:
        mc = txt(r.get("machine_code"))
        cap = num0(r.get("capacity_shift"))
        active = txt(r.get("active")).lower()
        if mc and active != "no":
            mach_capacity[mc] = cap

    # Aggregate machine loading by machine × date
    # For each plan item: find family → route → machines → load = qty / capacity_shift
    machine_load = defaultdict(lambda: defaultdict(float))  # machine → date → total_qty

    for r in plan_rows:
        fam = txt(r.get("family")).upper()
        if fam not in route_by_family:
            continue
        days = r.get("days", {})
        for d, qty in days.items():
            q = num0(qty)
            if q <= 0:
                continue
            for mach, _ct in route_by_family[fam]:
                machine_load[mach][d] += q

    # Flag overloaded machines
    flags_created = 0
    for mach, dates in machine_load.items():
        cap = mach_capacity.get(mach, 0)
        if cap <= 0:
            continue

        for d, loaded_qty in sorted(dates.items()):
            utilization = (loaded_qty / cap) * 100
            if utilization > 100:
                overload = utilization - 100
                PPCCapacityFlag.objects.create(
                    run=run,
                    flag_type="machine",
                    date=d,
                    product_group="",
                    section="",
                    item_code="",
                    planned_qty=loaded_qty,
                    capacity_qty=cap,
                    overload_pct=round(overload, 1),
                    detail={
                        "machine_code": mach,
                        "utilization_pct": round(utilization, 1),
                    },
                )
                flags_created += 1

    return flags_created


# ── 3. EBQ qualification ────────────────────────────────────────


def _ebq_check(run, plan_rows):
    """Check if planned quantities meet minimum EBQ (W1.8).

    batch_ebq has ebq_qty per product_group × family.
    Flag families where total_plan < ebq_qty.
    """
    ebq_rows = _load_current_rows("batch_ebq")
    if not ebq_rows:
        log.warning("Feasibility: no batch_ebq loaded — skipping EBQ check")
        return 0

    # Build EBQ lookup: (product_group, family) → ebq_qty
    ebq_lookup = {}
    for r in ebq_rows:
        pg = txt(r.get("product_group")).upper()
        fam = txt(r.get("family")).upper()
        ebq = num0(r.get("ebq_qty"))
        if pg and ebq > 0:
            ebq_lookup[(pg, fam)] = ebq

    # Aggregate plan by product_group × family
    plan_by_gf = defaultdict(float)
    items_by_gf = defaultdict(list)
    for r in plan_rows:
        pg = txt(r.get("product_group")).upper()
        fam = txt(r.get("family")).upper()
        tp = num0(r.get("total_plan"))
        if pg:
            plan_by_gf[(pg, fam)] += tp
            items_by_gf[(pg, fam)].append(txt(r.get("item_code")))

    # Flag under-EBQ batches
    flags_created = 0
    for (pg, fam), total in plan_by_gf.items():
        ebq = ebq_lookup.get((pg, fam))
        if ebq is None:
            continue
        if total < ebq:
            underload = ((ebq - total) / ebq) * 100
            sample_items = items_by_gf[(pg, fam)][:5]
            PPCCapacityFlag.objects.create(
                run=run,
                flag_type="ebq",
                date=None,
                product_group=pg,
                section="",
                item_code=", ".join(sample_items),
                planned_qty=total,
                capacity_qty=ebq,
                overload_pct=round(-underload, 1),  # negative = under
                detail={
                    "family": fam,
                    "ebq_qty": ebq,
                    "planned_total": total,
                    "sample_items": sample_items,
                },
            )
            flags_created += 1

    return flags_created


# ── Main entry point ─────────────────────────────────────────────


def run_feasibility(plan_batch_id):
    """Run all three feasibility checks on a plan batch.

    Returns the PPCFeasibilityRun instance with summary.
    """
    plan_batch = PPCUploadBatch.objects.get(pk=plan_batch_id)
    plan_rows = list(plan_batch.rows.values_list("data", flat=True))

    if not plan_rows:
        raise ValueError("Plan batch has no rows")

    # Detect plan month
    plan_month = plan_rows[0].get("_plan_month", "unknown")

    # Create the run
    run = PPCFeasibilityRun.objects.create(
        plan_batch=plan_batch,
        plan_month=plan_month,
        status="running",
    )

    try:
        cap_flags = _capacity_check(run, plan_rows)
        mach_flags = _machine_loading(run, plan_rows)
        ebq_flags = _ebq_check(run, plan_rows)

        total_flags = cap_flags + mach_flags + ebq_flags

        run.summary = {
            "capacity_flags": cap_flags,
            "machine_flags": mach_flags,
            "ebq_flags": ebq_flags,
            "total_flags": total_flags,
            "plan_items": len(plan_rows),
            "plan_month": plan_month,
        }
        run.completed_at = timezone.now()

        if total_flags > 0:
            run.status = "flagged"
        else:
            run.status = "approved"
            run.approved_at = timezone.now()

        run.save()

    except Exception:
        run.status = "rejected"
        run.save()
        raise

    return run
