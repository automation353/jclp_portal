"""Pull the Combined tab as CSV and persist it as a fresh snapshot.

The sheet is link-shared for viewing, so the CSV export URL works without
any Google authentication.
"""

import csv
import io
import os
import ssl
import urllib.request

from django.db import transaction

from portal.notify import notify

from .field_map import FIELD_MAP
from .models import PurchaseDashRow, PurchaseDashSnapshot


DEFAULT_SHEET_ID = "1euJuqvIv7wHvwPejgCMOztJNGwU0eyTvPUioYLZZ4fg"
DEFAULT_GID = "1942899352"  # "combined" tab


def _csv_url(sheet_id, gid):
    # Plain CSV export, NOT gviz/tq. gviz assigns each column a single type and
    # silently blanks any value that doesn't fit it — on the Combined tab that
    # cost us 168 "HIGH INVENTORY" values (column typed as date) and 119
    # "Excess Procured" values (column typed as number). Those blanks looked
    # exactly like genuinely empty cells, so Control 3's HIGH INVENTORY test
    # and Dashboard 9's high-inventory conflict could never fire. The export
    # endpoint returns the displayed text of every cell, whatever its type.
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )


def fetch_and_persist(sheet_id=None, gid=None) -> PurchaseDashSnapshot:
    sheet_id = sheet_id or os.environ.get("JCLP_PURCHASE_DASH_SHEET_ID", DEFAULT_SHEET_ID)
    gid = gid or os.environ.get("JCLP_PURCHASE_DASH_GID", DEFAULT_GID)

    url = _csv_url(sheet_id, gid)
    context = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JCPL-portal)"})
    with urllib.request.urlopen(req, timeout=30, context=context) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    all_rows = list(reader)
    # Keep only rows that carry a real Sr No — trailing blank rows drop out.
    data_rows = [r for r in all_rows if (r.get("Sr No.") or "").strip()]

    if not data_rows:
        # The tab's column layout has changed (no "Sr No." column found at
        # all) or it's genuinely empty. Record the attempt for diagnostics
        # but never let it become "current" — a dashboard silently going to
        # zero is worse than one that stays on stale-but-real data. The
        # last good snapshot is left completely untouched.
        reason = (
            "Fetched the sheet but found 0 rows carrying a 'Sr No.' "
            "value — the tab's column layout may have changed. "
            "Previous current snapshot left untouched."
        )
        rejected = PurchaseDashSnapshot.objects.create(
            sheet_id=sheet_id, gid=gid, row_count=0,
            is_current=False, fetch_error=reason,
        )
        notify(
            f"Combined-tab fetch rejected — snapshot #{rejected.id}",
            (
                f"The hourly fetch of the Purchase Combined tab (sheet {sheet_id}, "
                f"gid {gid}) at {rejected.fetched_at} was rejected and NOT promoted to "
                f"current.\n\nReason: {reason}\n\n"
                "The portal is still serving the last good snapshot — no dashboard or "
                "control went blank because of this. This email exists so a human finds "
                "out immediately instead of only noticing when a tile looks wrong.\n\n"
                "Likely cause: the 'combined' tab's column layout changed (a formula "
                "edit, a tab swap, etc.). Check the tab structure against "
                "purchase_dashboards/field_map.py's expected headers."
            ),
        )
        return rejected

    with transaction.atomic():
        PurchaseDashSnapshot.objects.filter(is_current=True).update(is_current=False)
        snap = PurchaseDashSnapshot.objects.create(
            sheet_id=sheet_id,
            gid=gid,
            row_count=len(data_rows),
            is_current=True,
        )
        bulk = []
        for row in data_rows:
            # Re-key every field: sheet-label → stable_key. Anything not in
            # the map is dropped on purpose (keeps snapshots slim + stable).
            keyed = {}
            for stable_key, sheet_col in FIELD_MAP.items():
                keyed[stable_key] = row.get(sheet_col, "")
            sr_raw = (row.get("Sr No.") or "").strip()
            try:
                sr_int = int(float(sr_raw))
            except (ValueError, TypeError):
                sr_int = None
            bulk.append(PurchaseDashRow(snapshot=snap, sr_no=sr_int, data=keyed))
        PurchaseDashRow.objects.bulk_create(bulk, batch_size=500)

    notify(
        f"Combined-tab fetch OK — snapshot #{snap.id}, {snap.row_count} rows",
        (
            f"Fetched sheet {sheet_id} (gid {gid}) at {snap.fetched_at} and promoted "
            f"snapshot #{snap.id} to current with {snap.row_count} rows. Dashboards "
            "and controls will pick this up on their next scheduled recompute."
        ),
    )
    return snap
