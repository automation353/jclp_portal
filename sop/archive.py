"""S&OP Monthly Snapshot archiving.

Saves / retrieves monthly dashboard snapshots.  Only the final
Append1 CSV + computed dashboard JSON are stored — never the 5 raw
source files.

Rules:
  • During a month, every successful Append1 update upserts the
    current month's snapshot (latest upload always wins).
  • Once the month ends, the snapshot is frozen — no more updates.
  • Each new month starts with an empty dashboard; old data does NOT
    carry forward.
"""

import json
import logging
import os
from datetime import datetime

from django.utils import timezone

log = logging.getLogger(__name__)


def _current_year_month():
    """Return current month as 'YYYY-MM'."""
    return timezone.now().strftime("%Y-%m")


def _csv_year_month():
    """Return the year-month of the current append1_snapshot.csv file.

    Uses the file's modification time to determine which month the
    data belongs to.  Returns None if the file doesn't exist.
    """
    csv_path = os.path.join(os.path.dirname(__file__), "append1_snapshot.csv")
    if not os.path.isfile(csv_path):
        return None
    mtime = os.path.getmtime(csv_path)
    return datetime.fromtimestamp(mtime).strftime("%Y-%m")


def is_current_month_fresh():
    """Check if the dashboard has data uploaded for the current month.

    Returns (has_data: bool, csv_month: str or None).
    """
    csv_month = _csv_year_month()
    current = _current_year_month()
    if csv_month is None:
        return False, None
    return csv_month == current, csv_month


def save_monthly_snapshot(user=None):
    """Save/update the current month's snapshot from live dashboard data.

    Reads the current append1_snapshot.csv, calls the dashboard
    computation, and stores both in the DB.

    Called automatically after every successful Append1 update.
    Won't overwrite a frozen (past-month) snapshot.

    Returns the snapshot instance, or None on failure.
    """
    from sop.models import SopMonthlySnapshot

    csv_path = os.path.join(os.path.dirname(__file__), "append1_snapshot.csv")
    if not os.path.isfile(csv_path):
        log.warning("save_monthly_snapshot: no CSV file found")
        return None

    # Read CSV text
    with open(csv_path, "r", encoding="utf-8") as f:
        csv_text = f.read()

    if not csv_text.strip():
        log.warning("save_monthly_snapshot: CSV file is empty")
        return None

    # Determine which month this data belongs to (from file mtime)
    csv_month = _csv_year_month()
    if not csv_month:
        return None

    # Don't overwrite frozen snapshots
    existing = SopMonthlySnapshot.objects.filter(year_month=csv_month).first()
    if existing and existing.frozen:
        log.info(
            "save_monthly_snapshot: %s is frozen, skipping", csv_month
        )
        return existing

    # Compute dashboard JSON by calling the API logic internally
    dashboard_data = _compute_dashboard_json()
    if dashboard_data is None:
        log.warning("save_monthly_snapshot: dashboard computation failed")
        return None

    item_count = (
        dashboard_data.get("volume", {}).get("total_items", 0)
    )

    # Upsert
    snapshot, created = SopMonthlySnapshot.objects.update_or_create(
        year_month=csv_month,
        defaults={
            "append1_csv": csv_text,
            "dashboard_json": dashboard_data,
            "item_count": item_count,
            "created_by": user,
        },
    )

    action = "created" if created else "updated"
    log.info(
        "Monthly snapshot %s for %s — %d items",
        action, csv_month, item_count,
    )
    return snapshot


def freeze_past_months():
    """Mark all snapshots from previous months as frozen.

    Called periodically (e.g. on the 1st of each month) to lock
    past data.  Idempotent — safe to call repeatedly.
    """
    from sop.models import SopMonthlySnapshot

    current = _current_year_month()
    updated = SopMonthlySnapshot.objects.filter(
        frozen=False,
        year_month__lt=current,
    ).update(frozen=True)

    if updated:
        log.info("Froze %d past-month snapshot(s)", updated)
    return updated


def list_snapshots():
    """Return all available monthly snapshots (metadata only)."""
    from sop.models import SopMonthlySnapshot

    return list(
        SopMonthlySnapshot.objects.values(
            "year_month", "item_count", "frozen",
            "created_at", "updated_at",
        ).order_by("-year_month")
    )


def get_snapshot(year_month):
    """Retrieve a specific month's snapshot, or None."""
    from sop.models import SopMonthlySnapshot

    return SopMonthlySnapshot.objects.filter(
        year_month=year_month
    ).first()


def _compute_dashboard_json():
    """Call the dashboard computation and return the response dict.

    Uses Django's RequestFactory to invoke demand_supply_overview
    internally, then extracts the JSON.
    """
    try:
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        from rest_framework.renderers import JSONRenderer

        from sop.api import demand_supply_overview

        User = get_user_model()
        user = User.objects.first()
        if not user:
            log.warning("_compute_dashboard_json: no user in DB")
            return None

        rf = RequestFactory()
        req = rf.get("/api/sop/demand-supply/")
        req.user = user

        resp = demand_supply_overview(req)
        resp.accepted_renderer = JSONRenderer()
        resp.accepted_media_type = "application/json"
        resp.renderer_context = {"request": req}
        resp.render()

        return json.loads(resp.content)

    except Exception as exc:
        log.exception("_compute_dashboard_json failed: %s", exc)
        return None
