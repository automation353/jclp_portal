"""The Seven Purchase Controls — data model.

A wholly separate app from purchase_dashboards. It *reads* the existing
PurchaseDashSnapshot/PurchaseDashRow tables (never writes to them) and keeps
its own result + history tables, so nothing here can alter the nine
dashboards' behaviour, migrations or data.

Two tables:

* ControlResult — one row per (snapshot, control_key); the cached tile +
  drill-through payload, same shape as PurchaseDashResult so the API layer
  and frontend can reuse the exact same rendering code.
* ControlRunHistory — brief §Stage 9 "Archive": append-only verdict counts
  per run, so every control shows a trend from day one, and any past
  verdict can be re-examined later. Never updated in place, only appended.
"""

from django.db import models

from purchase_dashboards.models import PurchaseDashSnapshot


class ControlResult(models.Model):
    """Cached compute output for one control against one snapshot."""

    snapshot = models.ForeignKey(
        PurchaseDashSnapshot, on_delete=models.CASCADE, related_name="control_results"
    )
    control_key = models.CharField(max_length=20)  # 'c3', 'c4', 'c6', 'c7'
    tiles = models.JSONField()
    tile_rows = models.JSONField(default=dict)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "control_key"], name="uniq_snap_control",
            ),
        ]
        ordering = ["control_key"]

    def __str__(self):
        return f"{self.control_key} @ snapshot #{self.snapshot_id}"


class ControlRunHistory(models.Model):
    """Append-only verdict-count trend, one row per (control, run).

    Brief §Non-negotiables: "Without this a control shows a level but never
    a trend, and no verdict can be re-examined later." Never updated once
    written — a new run always appends a new row, even against the same
    snapshot (idempotent re-runs simply repeat the same counts).
    """

    control_key = models.CharField(max_length=20)
    snapshot = models.ForeignKey(
        PurchaseDashSnapshot, on_delete=models.CASCADE, related_name="control_history"
    )
    run_at = models.DateTimeField(auto_now_add=True)
    verdict_counts = models.JSONField(default=dict)  # {"CLEAR": 34, "STOP — DEAD ITEM": 12, ...}
    population = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-run_at"]
        indexes = [models.Index(fields=["control_key", "-run_at"])]

    def __str__(self):
        return f"{self.control_key} history @ {self.run_at:%Y-%m-%d %H:%M}"


class RequirementAge(models.Model):
    """When each requirement was FIRST seen — the clock Control 2 needs.

    Nothing in JCPL records this today, so the automation has to create it.
    Spec §Control 2 hazard: "The age register must not be resettable. If a
    requirement disappears for one day because of a lookup failure and
    returns the next, a naive design stamps it as new and the age resets to
    zero. That converts a 40-day failure into a fresh requirement, and it
    will happen." So:

    * one row per item key, created the first time that item is seen
      carrying a requirement;
    * ``first_seen`` is written once and NEVER updated — every write path
      uses get_or_create and only ever touches ``last_seen``;
    * rows are never deleted, so a requirement that lapses and returns
      keeps its original date.

    ``item_key`` is the Item Code where the row has one, else the Item Name
    (the same precedence the PO join uses), so the clock survives a row
    moving position in the sheet.
    """

    item_key = models.CharField(max_length=120, unique=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    # Diagnostics only — never used to compute age.
    last_seen = models.DateTimeField(auto_now=True)
    times_seen = models.PositiveIntegerField(default=1)
    first_qty = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["first_seen"]
        indexes = [models.Index(fields=["item_key"])]

    def __str__(self):
        return f"{self.item_key} first seen {self.first_seen:%Y-%m-%d}"


class POSnapshot(models.Model):
    """One successful pull of the `po` tab.

    Control 5 is the only control that is inherently PO-LINE level: an
    advance is aged from its own PO date, owed to its own vendor, for its own
    amount. Aggregating to item level (the way combined!AQ:AX does for
    Control 1) would destroy exactly the detail this control exists to show,
    so the PO lines are stored in their own right.

    Same guard as the combined fetch: a pull that yields no usable lines is
    recorded but never promoted to current, so a bad export cannot blank the
    board.
    """

    fetched_at = models.DateTimeField(auto_now_add=True)
    sheet_id = models.CharField(max_length=100)
    gid = models.CharField(max_length=32)
    line_count = models.PositiveIntegerField(default=0)
    is_current = models.BooleanField(default=True)
    fetch_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"PO snapshot #{self.pk} @ {self.fetched_at:%Y-%m-%d %H:%M} ({self.line_count} lines)"


class POLine(models.Model):
    """One purchase-order line, keyed by stable field names like
    PurchaseDashRow so the sheet can gain or lose columns without a
    migration."""

    snapshot = models.ForeignKey(
        POSnapshot, on_delete=models.CASCADE, related_name="lines"
    )
    po_number = models.CharField(max_length=64, blank=True)
    item_code = models.CharField(max_length=120, blank=True)
    data = models.JSONField()

    class Meta:
        indexes = [
            models.Index(fields=["snapshot", "item_code"]),
            models.Index(fields=["snapshot", "po_number"]),
        ]
