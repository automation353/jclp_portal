"""Recompute all Seven-Controls modules against the current dashboard
snapshot. Read-only against purchase_dashboards — never fetches, never
writes there.

    python manage.py compute_purchase_controls
"""

from django.core.management.base import BaseCommand

from purchase_dashboards.models import PurchaseDashSnapshot
from purchase_controls.computations import compute_all


class Command(BaseCommand):
    help = "Recompute The Seven Purchase Controls (built ones) against the current snapshot."

    def handle(self, **options):
        snap = (
            PurchaseDashSnapshot.objects
            .filter(is_current=True)
            .order_by("-fetched_at")
            .first()
        )
        if snap is None:
            self.stderr.write(
                "[fail] no current snapshot — run fetch_combined_sheet first "
                "(purchase_dashboards' own command; unaffected by this app)."
            )
            raise SystemExit(1)
        results = compute_all(snap)
        self.stdout.write(f"[ok] recomputed {len(results)} control(s) on snapshot #{snap.id}")
