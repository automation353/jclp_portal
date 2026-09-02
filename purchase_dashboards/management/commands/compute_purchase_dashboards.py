"""Recompute all dashboards against the current snapshot without fetching.

Useful after changing a computation module — no need to hit Google.

    python manage.py compute_purchase_dashboards
"""

from django.core.management.base import BaseCommand

from purchase_dashboards.computations import compute_all
from purchase_dashboards.models import PurchaseDashSnapshot


class Command(BaseCommand):
    help = "Recompute all Purchase Control Dashboards against the current snapshot."

    def handle(self, **options):
        snap = (
            PurchaseDashSnapshot.objects
            .filter(is_current=True)
            .order_by("-fetched_at")
            .first()
        )
        if snap is None:
            self.stderr.write("[fail] no current snapshot — run fetch_combined_sheet first.")
            raise SystemExit(1)
        results = compute_all(snap)
        self.stdout.write(f"[ok] recomputed {len(results)} dashboard(s) on snapshot #{snap.id}")
