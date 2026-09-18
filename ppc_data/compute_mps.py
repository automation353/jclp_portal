"""L3 MPS compute engine — NET_REQUIREMENT + week bucketing.

Spec §3.3:
    NET_REQUIREMENT = MAX(0, TOTAL_DEMAND + SAFETY_STOCK − FG − WIP − PRODUCED_MTD)
    NET_REQUIREMENT = ROUNDUP(NET_REQUIREMENT / EBQ) × EBQ     ← lot sizing

    Then bucket into W1…W5 against the week the demand is required in,
    pulled forward by MFG_LEAD_TIME.

    Gate: W1 + W2 + W3 + W4 + W5 = NET_REQUIREMENT for every part.

Data sources:
    TOTAL_DEMAND  ← PPCDemandFreeze + PPCDemandTransaction (L2)
    FG            ← erp_fg_stock (L1 ERP landing)
    WIP           ← erp_prod_semi (L1 ERP landing)
    PRODUCED_MTD  ← PPCProductionEntry (L8) or erp_prod_fg (L1)
    SAFETY_STOCK  ← stock_policy master (W1.14)
    EBQ           ← batch_ebq master (W1.08)
    MFG_LEAD_TIME ← lead_time master (W1.09)
    AVG_DEMAND    ← demand_history / TREND_6M
    Calendar      ← planning_calendar (W1.10)
    Identity      ← family_hierarchy (W1.02) + item_master (W1.01)
"""

import logging
import math
from collections import defaultdict

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .field_maps.helpers import num0, txt
from .models import (
    PPCDataRow,
    PPCDemandFreeze,
    PPCDemandTransaction,
    PPCProductionEntry,
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
    """Build a dict mapping key_field value → row (first match wins)."""
    lookup = {}
    for r in rows:
        k = txt(r.get(key_field))
        if upper:
            k = k.upper()
        if k and k not in lookup:
            lookup[k] = r
    return lookup


def _build_group_lookup(rows, key_field, upper=True):
    """Build a dict mapping key_field value → [all matching rows]."""
    lookup = defaultdict(list)
    for r in rows:
        k = txt(r.get(key_field))
        if upper:
            k = k.upper()
        if k:
            lookup[k].append(r)
    return lookup


def _roundup_to_ebq(net_req, ebq):
    """Round net requirement UP to the nearest EBQ multiple."""
    if ebq <= 0 or net_req <= 0:
        return max(0.0, net_req)
    return math.ceil(net_req / ebq) * ebq


# ── Demand aggregation ──────────────────────────────────────────


def _aggregate_demand(month):
    """Build item_code → effective demand from the demand freeze system.

    Returns dict: {item_code_upper: {initial, additions, reductions, total}}
    """
    freezes = PPCDemandFreeze.objects.filter(month=month).select_related()
    demand = {}

    for f in freezes:
        ic = f.item_code.strip().upper()
        agg = f.transactions.aggregate(
            adds=Sum("qty", filter=Q(tx_type="add")),
            reds=Sum("qty", filter=Q(tx_type="reduce")),
        )
        adds = agg["adds"] or 0.0
        reds = agg["reds"] or 0.0
        total = f.initial_qty + adds - reds

        demand[ic] = {
            "initial": f.initial_qty,
            "additions": adds,
            "reductions": reds,
            "total": max(0.0, total),
        }

    return demand


def _aggregate_produced_mtd(month):
    """Sum of production entries this month per item_code.

    Falls back to erp_prod_fg data if no PPCProductionEntry records exist.
    """
    # Parse month string "YYYY-MM" into date range
    try:
        year, mo = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        return {}

    from datetime import date
    first_day = date(year, mo, 1)
    today = date.today()

    # Try PPCProductionEntry first (manual shop-floor entries)
    entries = (
        PPCProductionEntry.objects
        .filter(date__gte=first_day, date__lte=today)
        .values("item_code")
        .annotate(total=Sum("produced_qty"))
    )

    produced = {}
    for e in entries:
        ic = e["item_code"].strip().upper()
        produced[ic] = e["total"] or 0.0

    if produced:
        return produced

    # Fallback: erp_prod_fg (ERP production FG report)
    prod_rows = _load_current_rows("erp_prod_fg")
    for r in prod_rows:
        ic = txt(r.get("item_code")).upper()
        qty = num0(r.get("closing")) or num0(r.get("receipt")) or 0.0
        if ic and qty:
            produced[ic] = produced.get(ic, 0.0) + qty

    return produced


# ── Stock lookups ───────────────────────────────────────────────


def _build_fg_stock_lookup():
    """item_code → closing FG stock from erp_fg_stock."""
    rows = _load_current_rows("erp_fg_stock")
    lookup = {}
    for r in rows:
        ic = txt(r.get("item_code")).upper()
        closing = num0(r.get("closing"))
        if ic:
            # Sum across locations/batches
            lookup[ic] = lookup.get(ic, 0.0) + closing
    return lookup


def _build_wip_lookup():
    """item_code → WIP from erp_prod_semi."""
    rows = _load_current_rows("erp_prod_semi")
    lookup = {}
    for r in rows:
        ic = txt(r.get("item_code")).upper()
        # WIP = closing balance of semi-finished
        wip = num0(r.get("closing")) or num0(r.get("receipt")) or 0.0
        if ic:
            lookup[ic] = lookup.get(ic, 0.0) + wip
    return lookup


# ── Week bucketing ──────────────────────────────────────────────


def _load_week_calendar():
    """Load planning calendar and return list of (week_label, start_date) pairs.

    Returns up to 5 weeks for the current planning cycle.
    """
    rows = _load_current_rows("planning_calendar")
    if not rows:
        return []

    weeks = []
    for r in rows:
        for wn in range(1, 6):
            wk_start = r.get(f"w{wn}_start")
            if wk_start:
                weeks.append((f"W{wn}", wk_start))

    # Deduplicate and sort
    seen = set()
    unique = []
    for label, start in weeks:
        if label not in seen:
            seen.add(label)
            unique.append((label, start))
    return unique[:5]


def _bucket_into_weeks(net_req, ebq, lead_time_days, weeks):
    """Spread net requirement across W1-W5.

    Simple heuristic: fill from W1 (earliest) forward, respecting EBQ.
    Lead time shifts: a part with lead time L that needs to start by
    week N should be bucketed into week max(1, N - lead_time_weeks).

    For now, fill greedily from W1 forward since we lack per-week demand
    breakdown at L3. The spec gate is W1+W2+W3+W4+W5 = NET_REQUIREMENT.
    """
    buckets = {"w1_qty": 0.0, "w2_qty": 0.0, "w3_qty": 0.0,
               "w4_qty": 0.0, "w5_qty": 0.0}

    if net_req <= 0 or not weeks:
        return buckets

    # Convert lead time to weeks (rough: 6 working days per week)
    lt_weeks = max(0, int(lead_time_days / 6)) if lead_time_days > 0 else 0

    # Number of available weeks after lead time offset
    num_weeks = max(1, min(5, 5 - lt_weeks))

    # Distribute evenly across available weeks, in EBQ lots
    if ebq > 0:
        lots = math.ceil(net_req / ebq)
        lots_per_week = max(1, lots // num_weeks)
        remainder_lots = lots - (lots_per_week * num_weeks)
    else:
        lots_per_week = 0
        remainder_lots = 0
        ebq = 1  # avoid division by zero

    remaining = net_req
    for i in range(5):
        wk_key = f"w{i + 1}_qty"
        if i < (5 - num_weeks):
            # Before the lead-time window — skip
            buckets[wk_key] = 0.0
            continue

        if remaining <= 0:
            buckets[wk_key] = 0.0
            continue

        # Allocate lots_per_week, plus one extra lot to absorb remainder
        week_lots = lots_per_week
        if remainder_lots > 0:
            week_lots += 1
            remainder_lots -= 1

        week_qty = min(remaining, week_lots * ebq)
        buckets[wk_key] = week_qty
        remaining -= week_qty

    # Any rounding residual goes into the last non-zero bucket
    if remaining > 0:
        for i in range(4, -1, -1):
            wk_key = f"w{i + 1}_qty"
            if buckets[wk_key] > 0 or i == 4:
                buckets[wk_key] += remaining
                break

    return buckets


# ── Main compute ────────────────────────────────────────────────


def compute_mps(month, user=None):
    """Run the MPS computation for a given month.

    1. Load all source data
    2. For each item with frozen demand, compute NET_REQUIREMENT
    3. Bucket into W1-W5
    4. Store as mps_schedule rows (PPCDataRow)
    5. Sync to Google Sheet

    Returns: dict with summary + diagnostics
    """
    log.info("MPS compute starting for month=%s", month)
    started = timezone.now()

    # ── 1. Load all source data ──

    # Demand
    demand = _aggregate_demand(month)
    if not demand:
        return {
            "ok": False,
            "reason": f"No frozen demand for {month}. Freeze demand first.",
            "items_computed": 0,
        }

    # Masters
    family_rows = _load_current_rows("family_hierarchy")
    family_lookup = _build_lookup(family_rows, "item_code")

    item_rows = _load_current_rows("item_master")
    item_lookup = _build_lookup(item_rows, "item_code")

    ebq_rows = _load_current_rows("batch_ebq")
    # EBQ is per family, not per item
    ebq_by_family = _build_lookup(ebq_rows, "family")

    lt_rows = _load_current_rows("lead_time")
    # lead_time is per part_code
    lt_lookup = _build_lookup(lt_rows, "part_code")
    # Also try by item_code (some maps use "sku" as the key)
    for r in lt_rows:
        ic = txt(r.get("sku")).upper()
        if ic and ic not in lt_lookup:
            lt_lookup[ic] = r

    policy_rows = _load_current_rows("stock_policy")
    policy_lookup = _build_lookup(policy_rows, "item_code")

    capacity_rows = _load_current_rows("capacity_ppp")
    cap_by_family = _build_lookup(capacity_rows, "family")

    # Trend data
    history_rows = _load_current_rows("demand_history")
    history_lookup = _build_lookup(history_rows, "item_code")

    # Stock
    fg_stock = _build_fg_stock_lookup()
    wip = _build_wip_lookup()
    produced_mtd = _aggregate_produced_mtd(month)

    # Calendar
    weeks = _load_week_calendar()

    # ── 2. Compute per item ──

    mps_rows = []
    warnings = []
    gate_failures = []

    for item_code, dem in sorted(demand.items()):
        total_demand = dem["total"]

        # Identity
        fam_row = family_lookup.get(item_code, {})
        item_row = item_lookup.get(item_code, {})
        family = txt(fam_row.get("family")).upper()
        product_group = txt(fam_row.get("product_group"))
        section = txt(fam_row.get("section"))
        category = txt(fam_row.get("customer_category") or
                       fam_row.get("item_type") or "MTS")
        description = txt(item_row.get("description") or
                         fam_row.get("description"))

        # Policy lookups (by item_code, then by family)
        policy = policy_lookup.get(item_code, {})
        safety_stock = num0(policy.get("safety_stock") or
                           policy.get("green_level"))

        # EBQ (by family)
        ebq_row = ebq_by_family.get(family, {})
        ebq = num0(ebq_row.get("ebq_qty"))
        if ebq <= 0:
            ebq = 1.0  # default: no batching

        # Lead time
        lt_row = lt_lookup.get(item_code, {})
        mfg_lead_time = num0(lt_row.get("mfg_lt") or lt_row.get("max_lt"))

        # Stock
        fg = fg_stock.get(item_code, 0.0)
        item_wip = wip.get(item_code, 0.0)
        prod_mtd = produced_mtd.get(item_code, 0.0)

        # Trend
        hist = history_lookup.get(item_code, {})
        avg_month_demand = num0(hist.get("monthly_avg") or
                                hist.get("demand_qty"))

        # ATMC group
        atmc = txt(ebq_row.get("atmc_feasible") or
                   fam_row.get("atmc_group") or "")

        # Capacity / PPP
        cap_row = cap_by_family.get(family, {})
        priority = txt(cap_row.get("priority") or "")

        # ── NET REQUIREMENT (spec §3.3) ──
        raw_net = total_demand + safety_stock - fg - item_wip - prod_mtd
        net_req_raw = max(0.0, raw_net)
        net_requirement = _roundup_to_ebq(net_req_raw, ebq)

        # PAB = FG + WIP + produced_mtd - total_demand + net_requirement
        pab = fg + item_wip + prod_mtd - total_demand + net_requirement

        # ── WEEK BUCKETING ──
        buckets = _bucket_into_weeks(net_requirement, ebq, mfg_lead_time, weeks)
        total_plan = sum(buckets.values())

        # Gate check: W1+W2+W3+W4+W5 must equal NET_REQUIREMENT
        if abs(total_plan - net_requirement) > 0.01:
            gate_failures.append({
                "item_code": item_code,
                "net_requirement": net_requirement,
                "total_plan": total_plan,
                "delta": total_plan - net_requirement,
            })

        # Build MPS row
        mps_row = {
            "item_code": item_code,
            "description": description,
            "family": family,
            "product_group": product_group,
            "section": section,
            "category": category.upper(),
            "atmc_group": atmc,
            "priority": priority,
            "avg_month_demand": round(avg_month_demand, 2),
            "month_demand": round(total_demand, 2),
            "net_requirement": round(net_requirement, 2),
            "fg_stock": round(fg, 2),
            "wip": round(item_wip, 2),
            "safety_stock": round(safety_stock, 2),
            "pab": round(pab, 2),
            "ebq": round(ebq, 2),
            "batch_qty": round(ebq, 2),
            "mfg_lead_time": round(mfg_lead_time, 2),
            "w1_qty": round(buckets["w1_qty"], 2),
            "w2_qty": round(buckets["w2_qty"], 2),
            "w3_qty": round(buckets["w3_qty"], 2),
            "w4_qty": round(buckets["w4_qty"], 2),
            "w5_qty": round(buckets["w5_qty"], 2),
            "total_plan": round(total_plan, 2),
            "plant": txt(item_row.get("site") or fam_row.get("plant") or ""),
            "uom": txt(item_row.get("uom") or "NOS"),
            "rate": num0(hist.get("rate")),
            "amount": round(net_requirement * num0(hist.get("rate")), 2),
        }
        mps_rows.append(mps_row)

    if not mps_rows:
        return {
            "ok": False,
            "reason": "No items matched demand + masters. Check data.",
            "items_computed": 0,
        }

    # ── 3. Store as mps_schedule batch ──

    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key="mps_schedule", is_current=True,
        ).update(is_current=False)

        batch = PPCUploadBatch.objects.create(
            uploader=user,
            source_file="",
            original_filename=f"MPS Compute ({month})",
            file_type="computed",
            level="L3",
            table_key="mps_schedule",
            row_count=len(mps_rows),
            is_current=True,
            notes=f"Auto-computed at {started.isoformat()} for {month}",
        )

        PPCDataRow.objects.bulk_create([
            PPCDataRow(
                batch=batch, sr_no=i + 1,
                table_key="mps_schedule", data=row,
            )
            for i, row in enumerate(mps_rows)
        ], batch_size=500)

    elapsed = (timezone.now() - started).total_seconds()
    log.info(
        "MPS compute done: %d items, %d gate failures, %.1fs",
        len(mps_rows), len(gate_failures), elapsed,
    )

    # ── 4. Sync to Google Sheet (fire-and-forget) ──
    sheet_sync_result = None
    try:
        from .sheet_sync import sync_upload_to_sheet
        sheet_sync_result = sync_upload_to_sheet(batch)
    except Exception:
        log.exception("MPS sheet sync failed (non-blocking)")

    # ── Summary ──
    total_net_req = sum(r["net_requirement"] for r in mps_rows)
    total_plan_qty = sum(r["total_plan"] for r in mps_rows)
    mto_count = sum(1 for r in mps_rows if "MTO" in r["category"])
    mts_count = sum(1 for r in mps_rows if "MTS" in r["category"])

    return {
        "ok": True,
        "month": month,
        "batch_id": batch.pk,
        "items_computed": len(mps_rows),
        "total_net_requirement": round(total_net_req, 2),
        "total_plan_qty": round(total_plan_qty, 2),
        "mto_items": mto_count,
        "mts_items": mts_count,
        "gate_failures": len(gate_failures),
        "gate_failure_detail": gate_failures[:20],
        "warnings": warnings[:20],
        "elapsed_seconds": round(elapsed, 2),
        "sheet_sync": sheet_sync_result,
        "sources": {
            "demand_items": len(demand),
            "fg_stock_items": len(fg_stock),
            "wip_items": len(wip),
            "produced_mtd_items": len(produced_mtd),
            "family_hierarchy": len(family_rows),
            "batch_ebq": len(ebq_rows),
            "lead_time": len(lt_rows),
            "stock_policy": len(policy_rows),
        },
    }
