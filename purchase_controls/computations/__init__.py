"""Registry of control computation modules — deliberately separate from
purchase_dashboards.computations.DASHBOARDS. Nothing here is imported by,
or imports from, that registry; the two run side by side.

Every module exposes:
    CONTROL_KEY    — short id, e.g. 'c3'
    TITLE          — display title
    JCPL_WORDING   — the mockup's own wording for this control
    compute(rows)  — pure function; rows is
                     [{'sr_no': int|None, 'data': {stable_key: raw_str}}, ...]
                     returns {'tiles': {...}, 'tile_rows': {...}}

All seven controls are now registered. Controls 1 and 2 joined on 24 Aug
2026 once the `po` tab was joined into combined and the requirement-age
register was created; Control 5 joined the same day, running on advance
PAYMENT TERMS from the PO register. Control 5 is explicitly partial — it can
size advance exposure but cannot confirm payment, because no vendor ledger
exists. Its own board states that limit.

A module may declare compute(rows) or compute(rows, meta) — meta carries the
age-register summary. The signature is inspected rather than assumed, so
adding a module never forces the others to change.
"""

import inspect

from . import (
    c1_already_on_order,
    c2_did_anyone_order,
    c3_dead_stock_challenge,
    c4_cover_vs_lead_time,
    c5_advance_recovery,
    c6_item_code_validity,
    c7_real_zero_or_failed_lookup,
)


CONTROLS = {
    c1_already_on_order.CONTROL_KEY:          c1_already_on_order,
    c2_did_anyone_order.CONTROL_KEY:          c2_did_anyone_order,
    c3_dead_stock_challenge.CONTROL_KEY:      c3_dead_stock_challenge,
    c4_cover_vs_lead_time.CONTROL_KEY:        c4_cover_vs_lead_time,
    c5_advance_recovery.CONTROL_KEY:          c5_advance_recovery,
    c6_item_code_validity.CONTROL_KEY:        c6_item_code_validity,
    c7_real_zero_or_failed_lookup.CONTROL_KEY: c7_real_zero_or_failed_lookup,
}


def _verdict_counts(tiles):
    """A rough per-run verdict-count summary for the HISTORY trend — every
    tile that isn't a static note/ratio contributes its row_count under its
    own label. Brief §Stage 9: archive counts, not full rows."""
    counts = {}
    for key, tile in tiles.items():
        if tile.get("drillable"):
            counts[key] = tile.get("row_count", 0)
    return counts


def compute_all(snapshot):
    """Run every registered control against a snapshot, cache the results
    in ControlResult rows, and append one ControlRunHistory row per control.
    Idempotent on ControlResult (update_or_create); History is append-only
    by design — re-running the same snapshot simply repeats the same counts,
    which is the correct behaviour for a trend line, not a defect."""
    from portal.notify import notify

    from ..models import ControlResult, ControlRunHistory

    from ..age_register import stamp_and_enrich

    from purchase_dashboards.computations import dedup_rows

    rows = dedup_rows([
        {"sr_no": r.sr_no, "data": dict(r.data)}
        for r in snapshot.rows.all().order_by("sr_no")
    ])
    # Stamp the requirement-age register once per run, then hand every module
    # rows that already carry their age. Keeps the modules pure.
    rows, age_meta = stamp_and_enrich(rows)

    # Control 5 is PO-line level, so it needs the PO snapshot rather than the
    # combined rows. Loaded once and passed through meta; absent snapshot just
    # means Control 5 reports its feed as blocked.
    from ..models import POLine, POSnapshot
    po_snap = POSnapshot.objects.filter(is_current=True).order_by("-fetched_at").first()
    age_meta["po_lines"] = (
        [{"data": l.data} for l in POLine.objects.filter(snapshot=po_snap)]
        if po_snap else []
    )
    age_meta["po_snapshot_id"] = po_snap.id if po_snap else None

    written = []
    for key, module in CONTROLS.items():
        takes_meta = len(inspect.signature(module.compute).parameters) > 1
        result = module.compute(rows, age_meta) if takes_meta else module.compute(rows)
        obj, _ = ControlResult.objects.update_or_create(
            snapshot=snapshot,
            control_key=key,
            defaults={
                "tiles": result["tiles"],
                "tile_rows": result.get("tile_rows", {}),
            },
        )
        written.append(obj)
        ControlRunHistory.objects.create(
            control_key=key,
            snapshot=snapshot,
            verdict_counts=_verdict_counts(result["tiles"]),
            population=len(rows),
        )
    notify(
        f"Controls recomputed — snapshot #{snapshot.id}",
        f"Recomputed {len(written)} control(s) ({', '.join(CONTROLS.keys())}) against "
        f"snapshot #{snapshot.id} ({len(rows)} rows).",
    )
    return written
