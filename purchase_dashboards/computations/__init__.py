"""Registry of dashboard computation modules.

Every module exposes:
    DASHBOARD_KEY  — short id, e.g. 'd8'
    TITLE          — display title
    compute(rows)  — pure function; rows is
                     [{'sr_no': int|None, 'data': {stable_key: raw_str}}, ...]
                     returns {'tiles': {...}, 'detail_rows': [...]}
"""

import logging
from collections import defaultdict

from . import (
    d1_procurement_action,
    d2_stockout_risk,
    d3_reorder_rag,
    d4_valuation,
    d5_slow_moving,
    d6_buffer_capital,
    d7_coverage_ageing,
    d8_data_trust,
    d9_signal_conflict,
    d10_delivery_pipeline,
)

log = logging.getLogger(__name__)


DASHBOARDS = {
    # Group C — build order 1 (trust; everything else rests on it)
    d8_data_trust.DASHBOARD_KEY:      d8_data_trust,
    d9_signal_conflict.DASHBOARD_KEY: d9_signal_conflict,
    # Group A — build order 2 (act today)
    d1_procurement_action.DASHBOARD_KEY: d1_procurement_action,
    d2_stockout_risk.DASHBOARD_KEY:      d2_stockout_risk,
    d3_reorder_rag.DASHBOARD_KEY:        d3_reorder_rag,
    # Group B — build order 3 (capital)
    d4_valuation.DASHBOARD_KEY:      d4_valuation,
    d5_slow_moving.DASHBOARD_KEY:    d5_slow_moving,
    d6_buffer_capital.DASHBOARD_KEY: d6_buffer_capital,
    d7_coverage_ageing.DASHBOARD_KEY: d7_coverage_ageing,
    # Group A+ — build order 4 (delivery tracking, #13)
    d10_delivery_pipeline.DASHBOARD_KEY: d10_delivery_pipeline,
}


def dedup_rows(rows):
    """Remove phantom duplicate rows that inflate demand / order counts.

    The Combined tab sometimes carries two rows for the same tally_code:
    one with a real RM code and stock, one with rm_code = "0" and zero
    stock.  The phantom row's ``to_be_ordered_qty`` equals the full MPS
    demand (ignoring existing stock), which causes every dashboard to
    double-count that item's requirement and order value.

    Strategy:
      - Group rows by ``tally_code``.
      - When a coded row (real RM code) and a phantom (rm_code = 0)
        coexist for the same tally_code, drop the phantom.
      - Skip un-groupable rows (blank tally_code, "Item Code Required").
      - If all duplicates are coded or all are phantom, keep all — we
        can't resolve, and no data is lost.
    """
    from ..field_map import is_present_code

    SKIP_CODES = {"", "item code required"}

    by_tally = defaultdict(list)
    ungrouped = []

    for r in rows:
        tc = (r["data"].get("tally_code") or "").strip()
        if tc.lower() in SKIP_CODES:
            ungrouped.append(r)
        else:
            by_tally[tc].append(r)

    result = list(ungrouped)
    dropped = 0

    for tc, group in by_tally.items():
        if len(group) == 1:
            result.append(group[0])
            continue

        coded = [r for r in group
                 if is_present_code(r["data"].get("rm_code"))]
        phantom = [r for r in group
                   if not is_present_code(r["data"].get("rm_code"))]

        if coded and phantom:
            # Keep coded rows only; phantom duplicates are noise.
            result.extend(coded)
            dropped += len(phantom)
        else:
            # Can't resolve — keep all.
            result.extend(group)

    if dropped:
        log.info(
            "Dedup: dropped %d phantom duplicate row(s) "
            "(tally_code collision with rm_code=0)",
            dropped,
        )

    result.sort(key=lambda r: r["sr_no"] or 0)
    return result


def compute_all(snapshot):
    """Run every registered dashboard against a snapshot, cache the
    results in PurchaseDashResult rows. Idempotent per (snapshot, dashboard)."""
    from portal.notify import notify

    from ..models import PurchaseDashResult

    rows = dedup_rows([
        {"sr_no": r.sr_no, "data": r.data}
        for r in snapshot.rows.all().order_by("sr_no")
    ])
    written = []
    for key, module in DASHBOARDS.items():
        result = module.compute(rows)
        obj, _ = PurchaseDashResult.objects.update_or_create(
            snapshot=snapshot,
            dashboard_key=key,
            defaults={
                "tiles": result["tiles"],
                "tile_rows": result.get("tile_rows", {}),
                "detail_rows": result.get("detail_rows", []),
            },
        )
        written.append(obj)
    notify(
        f"Dashboards recomputed — snapshot #{snapshot.id}",
        f"Recomputed {len(written)} dashboard(s) against snapshot #{snapshot.id} "
        f"({snapshot.row_count} rows).",
    )
    return written
