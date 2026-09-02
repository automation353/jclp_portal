"""Pull the `po` tab into its own snapshot for Control 5.

    python manage.py fetch_po_tab

Read-only against everything else — never touches the combined snapshot,
the dashboards, or any existing command.
"""

from django.core.management.base import BaseCommand

from purchase_controls.po_fetcher import fetch_and_persist


class Command(BaseCommand):
    help = "Fetch the po tab and store it as a PO snapshot (Control 5)."

    def handle(self, **options):
        snap = fetch_and_persist()
        if not snap.is_current:
            self.stderr.write(f"[fail] PO fetch rejected: {snap.fetch_error}")
            raise SystemExit(1)
        self.stdout.write(
            f"[ok] PO snapshot #{snap.id} — {snap.line_count} lines"
        )
