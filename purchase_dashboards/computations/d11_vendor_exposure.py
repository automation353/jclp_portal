"""Dashboard 11 — Vendor & PO Exposure Board.

Brief §Dashboard 11.  Every material that has a purchase order — grouped
by vendor to show financial exposure, overdue concentration, and recovery
risk.  All figures are PO-based exposure; confirmed advance payments
require Tally data (not yet connected).

Precursor to the full Advance Payment dashboard described in
docs/DASHBOARD-10-TALLY-FEED-SPEC.docx — that board will extend this
one once Tally read-access is available.
"""

from collections import defaultdict

from ..drill import (
    C_CATEGORY, C_GROUP, C_LEAD, C_RATE, C_RM, C_SPEC, C_SR,
    C_STOCK, C_TALLY, C_TOORDER, C_VALUE, block, finalise, with_fields,
)
from ..field_map import num, rupees_in, txt


DASHBOARD_KEY = "d11"
TITLE = "Vendor & PO Exposure"


# ── Column specs unique to this board ─────────────────────────────────────

C_VENDOR   = {"key": "vendor",           "label": "Vendor"}
C_PO       = {"key": "po_numbers",       "label": "PO No."}
C_POLIVE   = {"key": "po_live",          "label": "PO live (kg)",    "numeric": True}
C_POOVER   = {"key": "po_overdue",       "label": "PO overdue (kg)", "numeric": True}
C_POREC    = {"key": "po_received",      "label": "Received (kg)",   "numeric": True}
C_PODUE    = {"key": "po_earliest_due",  "label": "Earliest due"}
C_POLATE   = {"key": "po_days_late",     "label": "Days late",       "numeric": True}

# Item-level drill columns (used by most tiles)
ITEM_COLS = [
    C_SR, C_TALLY, C_RM, C_SPEC, C_CATEGORY,
    C_VENDOR, C_PO,
    C_POLIVE, C_POOVER, C_POREC,
    C_PODUE, C_POLATE,
    C_RATE, C_VALUE,
]

# Vendor summary columns (used by vendor-grouping tiles)
VENDOR_COLS = [
    C_VENDOR,
    {"key": "item_count",     "label": "Items",            "numeric": True},
    {"key": "po_live",        "label": "Live value (₹)",   "numeric": True, "rupees": True},
    {"key": "po_overdue",     "label": "Overdue value (₹)","numeric": True, "rupees": True},
    {"key": "total_exposure", "label": "Total exposure",   "numeric": True, "rupees": True},
    {"key": "pct",            "label": "% share",          "numeric": True},
    {"key": "worst_late",     "label": "Worst late (days)","numeric": True},
]


def _item_row(r):
    """Build one drill row for an item that has PO data."""
    d = r["data"]
    live = num(d.get("po_pending_live")) or 0
    overdue = num(d.get("po_pending_overdue")) or 0
    rate = num(d.get("rate")) or 0
    return dict(
        with_fields(r, "current_stock_kg", "lead_time_days",
                    "to_be_ordered_qty", "rate"),
        vendor=txt(d.get("po_vendors")),
        po_numbers=txt(d.get("po_numbers")),
        po_live=live,
        po_overdue=overdue,
        po_received=num(d.get("po_received")) or 0,
        po_earliest_due=txt(d.get("po_earliest_due")),
        po_days_late=num(d.get("po_days_late")) or 0,
        value=(live + overdue) * rate,
    )


def _vendor_summaries(po_rows):
    """Aggregate item rows into per-vendor summaries.

    When an item lists multiple comma-separated vendors, its exposure is
    split equally among them — an approximation, but honest about the
    ambiguity rather than counting the same value for every vendor.
    """
    buckets = defaultdict(lambda: {
        "items": 0, "live_val": 0.0, "overdue_val": 0.0, "worst_late": 0,
    })

    for r in po_rows:
        d = r["data"]
        rate = num(d.get("rate")) or 0
        live = num(d.get("po_pending_live")) or 0
        overdue = num(d.get("po_pending_overdue")) or 0
        days_late = num(d.get("po_days_late")) or 0

        vendors = [v.strip() for v in (d.get("po_vendors") or "").split(",")
                   if v.strip()]
        if not vendors:
            vendors = ["(unknown)"]
        share = 1.0 / len(vendors)

        for v in vendors:
            b = buckets[v]
            b["items"] += 1
            b["live_val"] += live * rate * share
            b["overdue_val"] += overdue * rate * share
            if days_late > b["worst_late"]:
                b["worst_late"] = int(days_late)

    grand = sum(b["live_val"] + b["overdue_val"] for b in buckets.values()) or 1
    rows = []
    for name, b in buckets.items():
        total = b["live_val"] + b["overdue_val"]
        rows.append({
            "vendor": name,
            "item_count": b["items"],
            "po_live": round(b["live_val"], 2),
            "po_overdue": round(b["overdue_val"], 2),
            "total_exposure": round(total, 2),
            "pct": round(total / grand * 100, 1),
            "worst_late": b["worst_late"],
        })
    return sorted(rows, key=lambda x: x["total_exposure"], reverse=True)


def compute(rows):
    """Main entry — receives all deduped snapshot rows."""

    def d(r):
        return r["data"]

    def has_po(r):
        return bool((d(r).get("po_numbers") or "").strip())

    # ── Population: items with at least one PO ────────────────────────────
    po_rows = [r for r in rows if has_po(r)]
    if not po_rows:
        # No PO data at all — return empty board
        tiles = {
            "total_exposure": {
                "label": "Total PO exposure",
                "value": "—", "sub": "No PO data in this snapshot",
                "kind": "info",
            },
        }
        return finalise(tiles, {})

    item_rows = [_item_row(r) for r in po_rows]

    # ── Aggregate values ──────────────────────────────────────────────────
    total_live_val = sum(
        (num(d(r).get("po_pending_live")) or 0) * (num(d(r).get("rate")) or 0)
        for r in po_rows
    )
    total_overdue_val = sum(
        (num(d(r).get("po_pending_overdue")) or 0) * (num(d(r).get("rate")) or 0)
        for r in po_rows
    )
    total_exposure = total_live_val + total_overdue_val

    # Vendor summaries
    vendor_rows = _vendor_summaries(po_rows)
    vendors_with_overdue = [v for v in vendor_rows if v["po_overdue"] > 0]
    top_vendor = vendor_rows[0] if vendor_rows else None

    # Long overdue: items >30 days late
    long_overdue = [ir for ir in item_rows if (ir.get("po_days_late") or 0) > 30]
    long_overdue.sort(key=lambda x: x["po_days_late"], reverse=True)

    # PO raised but nothing received yet
    no_receipt = [ir for ir in item_rows if ir.get("po_received", 0) == 0]
    no_receipt_val = sum(ir["value"] for ir in no_receipt)
    no_receipt.sort(key=lambda x: x["value"], reverse=True)

    # ── Tiles ─────────────────────────────────────────────────────────────

    tiles = {
        "total_exposure": {
            "label": "Total PO exposure",
            "value": rupees_in(total_exposure),
            "sub": (
                f"{len(po_rows)} items across {len(vendor_rows)} vendors  ·  "
                f"live {rupees_in(total_live_val)}  ·  overdue {rupees_in(total_overdue_val)}"
            ),
            "kind": "warn",
            "indicative": True,
        },
        "overdue_value": {
            "label": "Overdue delivery value",
            "value": rupees_in(total_overdue_val),
            "sub": (
                f"Material past its promised date — "
                f"{round(total_overdue_val / total_exposure * 100) if total_exposure else 0}% of total exposure"
            ),
            "kind": "critical" if total_overdue_val > 0 else "info",
            "indicative": True,
        },
        "vendors_overdue": {
            "label": "Vendors with overdue material",
            "value": len(vendors_with_overdue),
            "sub": f"of {len(vendor_rows)} total vendors  ·  at least one item past due date",
            "kind": "critical" if vendors_with_overdue else "info",
        },
        "top_vendor": {
            "label": "Highest single-vendor exposure",
            "value": rupees_in(top_vendor["total_exposure"]) if top_vendor else "—",
            "sub": (
                f"{top_vendor['vendor']}  ·  "
                f"{top_vendor['pct']}% of total  ·  "
                f"{top_vendor['item_count']} items"
            ) if top_vendor else "No vendors",
            "kind": "warn" if top_vendor and top_vendor["pct"] > 30 else "info",
        },
        "long_overdue": {
            "label": "Long overdue (>30 days late)",
            "value": len(long_overdue),
            "sub": "Delivery promised over a month ago — recovery risk",
            "kind": "critical" if long_overdue else "info",
        },
        "no_receipt": {
            "label": "PO raised — nothing received",
            "value": len(no_receipt),
            "sub": f"Exposure {rupees_in(no_receipt_val)}  ·  PO on record but zero received quantity",
            "kind": "warn" if no_receipt else "info",
        },
    }

    # ── Drill rows ────────────────────────────────────────────────────────

    tile_rows = {
        "total_exposure": block(
            ITEM_COLS,
            sorted(item_rows, key=lambda x: x["value"], reverse=True),
        ),
        "overdue_value": block(
            ITEM_COLS,
            sorted(
                [ir for ir in item_rows if (ir.get("po_overdue") or 0) > 0],
                key=lambda x: x["po_overdue"] * (x.get("rate") or 0),
                reverse=True,
            ),
        ),
        "vendors_overdue": block(VENDOR_COLS, vendors_with_overdue),
        "top_vendor":      block(VENDOR_COLS, vendor_rows),
        "long_overdue":    block(ITEM_COLS, long_overdue),
        "no_receipt":      block(ITEM_COLS, no_receipt),
    }

    return finalise(tiles, tile_rows)
