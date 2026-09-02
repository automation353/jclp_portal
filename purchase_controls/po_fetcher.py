"""Pull the `po` tab and persist it as a PO snapshot.

Deliberately separate from purchase_dashboards.fetcher: that one owns the
combined tab and the nine dashboards, and nothing here may disturb it. Same
two hard-won lessons apply though —

* use the plain CSV export, never gviz/tq. gviz types each column and
  silently blanks values that don't fit, which cost us 168 "HIGH INVENTORY"
  and 119 "Excess Procured" values on the combined tab;
* a fetch that yields no usable lines is recorded but NEVER promoted to
  current, so a bad export leaves the last good snapshot serving.
"""

import csv
import io
import os
import ssl
import urllib.request

from django.db import transaction

from portal.notify import notify

from .models import POLine, POSnapshot

DEFAULT_SHEET_ID = "1euJuqvIv7wHvwPejgCMOztJNGwU0eyTvPUioYLZZ4fg"
DEFAULT_GID = "1484826721"  # "po" tab

# stable_key -> `po` tab header. Only what the controls actually need; the
# other ~70 columns are dropped on purpose to keep snapshots slim.
PO_FIELD_MAP = {
    "po_number":        "Purchase Order No",
    "po_date":          "Purchase Order Date",
    "po_status":        "Purchase Order Status",
    "txn_category":     "Transaction Category",
    "vendor_code":      "Party Code",
    "vendor":           "Party Description",
    "credit_term":      "Credit Term",
    "item_code":        "Item Code",
    "item_name":        "Item Name",
    "item_description": "Item Description",
    "item_type":        "Item Type",
    "required_date":    "Item Required Date",
    "ordered_qty":      "Purchase Quantity",
    "base_qty":         "Base Quantity",
    "uom":              "Base UOM",
    "rate":             "Rate",
    "amount":           "Amount",
    "net_amount":       "Net Amount",
    "pending_amount":   "Pending Amount",
    "received_qty":     "Next Transaction Qty",
    "pending_qty":      "Next Transaction Pending Qty",
    "grn_qty":          "Weighment GRN Qty",
    "created_by":       "Created By",
    "po_version":       "Purchase Order Version",
}


def _csv_url(sheet_id, gid):
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )


def fetch_and_persist(sheet_id=None, gid=None) -> POSnapshot:
    sheet_id = sheet_id or os.environ.get("JCLP_PO_SHEET_ID", DEFAULT_SHEET_ID)
    gid = gid or os.environ.get("JCLP_PO_GID", DEFAULT_GID)

    req = urllib.request.Request(
        _csv_url(sheet_id, gid), headers={"User-Agent": "Mozilla/5.0 (JCPL-portal)"},
    )
    with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    rows = [r for r in csv.DictReader(io.StringIO(text))
            if (r.get("Purchase Order No") or "").strip()]

    if not rows:
        reason = (
            "Fetched the po tab but found 0 lines carrying a 'Purchase Order No' "
            "— the tab's column layout may have changed. Previous PO snapshot "
            "left untouched."
        )
        rejected = POSnapshot.objects.create(
            sheet_id=sheet_id, gid=gid, line_count=0,
            is_current=False, fetch_error=reason,
        )
        notify(f"PO-tab fetch rejected — snapshot #{rejected.id}", reason)
        return rejected

    with transaction.atomic():
        POSnapshot.objects.filter(is_current=True).update(is_current=False)
        snap = POSnapshot.objects.create(
            sheet_id=sheet_id, gid=gid, line_count=len(rows), is_current=True,
        )
        bulk = []
        for row in rows:
            keyed = {k: row.get(col, "") for k, col in PO_FIELD_MAP.items()}
            bulk.append(POLine(
                snapshot=snap,
                po_number=(keyed.get("po_number") or "")[:64],
                item_code=(keyed.get("item_code") or "")[:120],
                data=keyed,
            ))
        POLine.objects.bulk_create(bulk, batch_size=500)

    notify(
        f"PO-tab fetch OK — snapshot #{snap.id}, {snap.line_count} lines",
        f"Fetched the po tab ({sheet_id} gid {gid}) and promoted snapshot "
        f"#{snap.id} with {snap.line_count} PO lines. Control 5 reads this.",
    )
    return snap
