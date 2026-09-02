"""Pull the Combined tab and (optionally) recompute all dashboards.

    python manage.py fetch_combined_sheet [--no-compute]
"""

import time
import traceback

from django.core.management.base import BaseCommand

from purchase_dashboards.computations import compute_all
from purchase_dashboards.fetcher import fetch_and_persist
from purchase_dashboards.models import PurchaseDashSnapshot


class Command(BaseCommand):
    help = "Fetch the Combined tab from Google Sheets and recompute dashboards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-compute", action="store_true",
            help="Fetch and store the snapshot but skip the compute step.",
        )

    def handle(self, no_compute, **options):
        t0 = time.time()
        try:
            snap = fetch_and_persist()
        except Exception as exc:
            # Record the failed attempt so the UI can show staleness.
            PurchaseDashSnapshot.objects.create(
                sheet_id="?", gid="?",
                row_count=0,
                is_current=False,
                fetch_error=f"{exc}\n\n{traceback.format_exc()}",
            )
            self.stderr.write(f"[fail] fetch failed: {exc}")
            raise SystemExit(1)

        fetch_s = time.time() - t0
        self.stdout.write(
            f"[ok] fetched snapshot #{snap.id}  rows={snap.row_count}  in {fetch_s:.2f}s"
        )

        if no_compute:
            return

        t0 = time.time()
        try:
            results = compute_all(snap)
        except Exception as exc:
            self.stderr.write(f"[warn] compute failed: {exc}\n{traceback.format_exc()}")
            return

        compute_s = time.time() - t0
        self.stdout.write(
            f"[ok] computed {len(results)} dashboard(s) in {compute_s:.2f}s"
        )
