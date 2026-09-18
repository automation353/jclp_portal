"""S&OP (Sales & Operations Planning) — data models.

This module provides demand-supply visibility dashboards and S&OP
analytics by reading data from the PPC Data Pipeline (ppc_data) and
ERP uploads. No separate uploads here — it's a read-only analytics
layer over existing data.
"""

from django.conf import settings
from django.db import models


class SopMonthlySnapshot(models.Model):
    """Archived S&OP dashboard for one calendar month.

    Stores the Append1 CSV and computed dashboard JSON as they were
    on the last day of the month.  Each month gets exactly one row;
    the latest upload during the month keeps overwriting it until the
    month ends — then the row is frozen.

    Only the final reconciliation output is stored, never the 5 raw
    source files.
    """

    year_month = models.CharField(
        max_length=7,
        unique=True,
        help_text='YYYY-MM format, e.g. "2026-09"',
    )
    append1_csv = models.TextField(
        help_text="Full Append1 CSV text (46-column reconciliation)",
    )
    dashboard_json = models.JSONField(
        help_text="Complete demand_supply_overview API response",
    )
    item_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of items in this snapshot",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    frozen = models.BooleanField(
        default=False,
        help_text="True once the month has ended — no more updates",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-year_month"]
        verbose_name = "S&OP Monthly Snapshot"
        verbose_name_plural = "S&OP Monthly Snapshots"

    def __str__(self):
        status = "🔒" if self.frozen else "📝"
        return f"{status} {self.year_month} — {self.item_count} items"
