"""Purchase Control Dashboards — data model.

Three tables:

* PurchaseDashSnapshot — one row per successful fetch of the Combined tab.
* PurchaseDashRow — one row per data line in that snapshot; fields kept as
  JSON keyed by our stable field keys (see field_map.py) so the sheet can
  gain/lose columns without a schema migration.
* PurchaseDashResult — one row per (snapshot, dashboard); holds the
  pre-computed tile values + drill-through rows.
"""

from django.db import models


class PurchaseDashSnapshot(models.Model):
    """One successful pull of the Combined tab."""

    fetched_at = models.DateTimeField(auto_now_add=True)
    sheet_id = models.CharField(max_length=100)
    gid = models.CharField(max_length=32)
    row_count = models.PositiveIntegerField(default=0)
    is_current = models.BooleanField(default=True)
    fetch_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"snapshot #{self.pk} @ {self.fetched_at:%Y-%m-%d %H:%M} ({self.row_count} rows)"


class PurchaseDashRow(models.Model):
    """One item line as pulled from the Combined tab. Stored keyed by our
    stable field keys so downstream computations never touch a column
    letter or a sheet-side header string directly."""

    snapshot = models.ForeignKey(
        PurchaseDashSnapshot, on_delete=models.CASCADE, related_name="rows"
    )
    sr_no = models.PositiveIntegerField(null=True, blank=True)
    data = models.JSONField()

    class Meta:
        indexes = [models.Index(fields=["snapshot", "sr_no"])]
        ordering = ["sr_no"]


class PurchaseDashResult(models.Model):
    """Cached compute output for one dashboard against one snapshot."""

    snapshot = models.ForeignKey(
        PurchaseDashSnapshot, on_delete=models.CASCADE, related_name="results"
    )
    dashboard_key = models.CharField(max_length=20)  # 'd1' … 'd9'
    tiles = models.JSONField()               # {tile_key: {...}}
    # Per-tile drill-through: {tile_key: {"columns": [...], "rows": [...]}}.
    # Served lazily by the per-tile endpoint so the summary payload stays small.
    tile_rows = models.JSONField(default=dict)
    detail_rows = models.JSONField(default=list)  # legacy single list — unused
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "dashboard_key"], name="uniq_snap_dash",
            ),
        ]
        ordering = ["dashboard_key"]
