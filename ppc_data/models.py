"""PPC Data Pipeline — data models.

Three core tables (same pattern as purchase_dashboards):

* PPCUploadBatch — one row per upload or ERP pull. Tracks who uploaded,
  what file, which table it maps to, and how many rows were parsed.
* PPCDataRow — one row per data line. Fields are stored as JSON keyed by
  stable field keys (see field_maps/) so columns can change without a
  schema migration.
* PPCComputeResult — cached compute output for dashboards and checks
  (built in later phases).
"""

from django.conf import settings
from django.db import models


class PPCUploadBatch(models.Model):
    """One upload or ERP pull. Analogous to PurchaseDashSnapshot."""

    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ppc_data_uploads",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    source_file = models.CharField(max_length=300, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(
        max_length=20,
        help_text="master / demand / plan / erp / forecast",
    )
    level = models.CharField(
        max_length=4,
        help_text="L0, L1, L2, L3, L4, L5, L6, L7, L8",
    )
    table_key = models.CharField(
        max_length=40,
        help_text="item_master, bom_master, r3ss_plan, …",
    )
    row_count = models.PositiveIntegerField(default=0)
    is_current = models.BooleanField(
        default=False,
        help_text="Only the latest successful upload per table_key is current.",
    )
    parse_error = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # Retention policy (portal.enforce_upload_retention): past the 2 most
    # recent uploads *per table_key*, the raw file is deleted. The parsed
    # data already lives in PPCDataRow — only the xlsx goes.
    # DB record itself is never touched.
    file_removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["table_key", "-uploaded_at"])]
        ordering = ["-uploaded_at"]

    def __str__(self):
        return (
            f"batch #{self.pk} [{self.table_key}] "
            f"@ {self.uploaded_at:%Y-%m-%d %H:%M} ({self.row_count} rows)"
        )


class PPCDataRow(models.Model):
    """One data line from an upload or ERP pull. Analogous to
    PurchaseDashRow — data is stored as a JSONField keyed by stable
    field keys from the matching field_maps/ module."""

    batch = models.ForeignKey(
        PPCUploadBatch, on_delete=models.CASCADE, related_name="rows",
    )
    sr_no = models.PositiveIntegerField(default=0)
    table_key = models.CharField(max_length=40, db_index=True)
    data = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=["table_key", "batch"])]
        ordering = ["sr_no"]

    def __str__(self):
        return f"row #{self.sr_no} in batch {self.batch_id} [{self.table_key}]"


# ── L2 Demand Freeze ─────────────────────────────────────────────
# Rule 3: initial demand is frozen. Changes are dated transactions.


class PPCDemandFreeze(models.Model):
    """Frozen initial demand for one item in one month.

    Once created, initial_qty must not change — adherence is measured
    against it. Any demand change becomes a PPCDemandTransaction.
    """

    item_code = models.CharField(max_length=40)
    month = models.CharField(
        max_length=7,
        help_text="YYYY-MM format, e.g. 2026-09",
    )
    initial_qty = models.FloatField()
    frozen_at = models.DateTimeField(auto_now_add=True)
    frozen_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demand_freezes",
    )
    batch = models.ForeignKey(
        PPCUploadBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demand_freezes",
        help_text="The upload batch that created this freeze",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item_code", "month"],
                name="uniq_demand_freeze_item_month",
            ),
        ]
        indexes = [models.Index(fields=["month", "item_code"])]
        ordering = ["-month", "item_code"]

    def __str__(self):
        return f"{self.item_code} {self.month}: {self.initial_qty}"


class PPCDemandTransaction(models.Model):
    """Dated demand change — addition or reduction.

    These accrue on top of the frozen initial. The effective demand is:
        initial_qty + SUM(additions) - SUM(reductions)
    """

    TXTYPE_ADD = "add"
    TXTYPE_REDUCE = "reduce"
    TX_CHOICES = [
        (TXTYPE_ADD, "Addition"),
        (TXTYPE_REDUCE, "Reduction"),
    ]

    freeze = models.ForeignKey(
        PPCDemandFreeze,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    tx_type = models.CharField(max_length=8, choices=TX_CHOICES)
    qty = models.FloatField(help_text="Always positive; sign inferred from tx_type")
    week = models.CharField(
        max_length=10, blank=True,
        help_text="Week label: W1, W2, Additional, etc.",
    )
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demand_transactions",
    )
    batch = models.ForeignKey(
        PPCUploadBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demand_transactions",
    )

    class Meta:
        indexes = [models.Index(fields=["freeze", "-created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.tx_type == self.TXTYPE_ADD else "−"
        return f"{sign}{self.qty} on {self.freeze} ({self.week})"


class PPCComputeResult(models.Model):
    """Cached compute output. Analogous to PurchaseDashResult.
    Built in later phases — the table exists from day one so migrations
    are stable."""

    batch = models.ForeignKey(
        PPCUploadBatch, on_delete=models.CASCADE, related_name="results",
    )
    compute_key = models.CharField(max_length=40)
    tiles = models.JSONField(default=dict)
    tile_rows = models.JSONField(default=dict)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "compute_key"],
                name="uniq_ppc_batch_compute",
            ),
        ]
        ordering = ["compute_key"]

    def __str__(self):
        return f"{self.compute_key} for batch {self.batch_id}"


# ── L5 Feasibility Gate ─────────────────────────────────────────
# Rule 5: capacity is a gate — plan cannot release without passing.


class PPCFeasibilityRun(models.Model):
    """One feasibility check run against a plan batch.

    Status lifecycle:  pending → running → flagged → approved / rejected
    A plan with zero unresolved flags can be approved.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("flagged", "Flagged — has unresolved issues"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("superseded", "Superseded by a later run"),
    ]

    plan_batch = models.ForeignKey(
        PPCUploadBatch, on_delete=models.CASCADE,
        related_name="feasibility_runs",
    )
    plan_month = models.CharField(max_length=7, help_text="YYYY-MM")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(
        default=dict,
        help_text="Capacity flags, machine overloads, EBQ flags — counts and details",
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Feasibility #{self.pk} [{self.plan_month}] {self.status}"


class PPCCapacityFlag(models.Model):
    """One overload or qualification flag raised during a feasibility run.

    flag_type values:
      - capacity   — day × product_group planned > capacity (W1.6)
      - machine    — day × machine utilization > 100% (W1.7)
      - ebq        — item planned qty < minimum batch (W1.8)

    Each flag must be resolved (reason entered or plan adjusted) before
    the feasibility run can be approved.
    """

    FLAG_TYPE_CHOICES = [
        ("capacity", "Capacity overload"),
        ("machine", "Machine overload"),
        ("ebq", "Under-EBQ batch"),
        ("manpower", "Manpower overload"),
    ]

    run = models.ForeignKey(
        PPCFeasibilityRun, on_delete=models.CASCADE,
        related_name="flags",
    )
    flag_type = models.CharField(max_length=20, choices=FLAG_TYPE_CHOICES)
    date = models.DateField(null=True, blank=True, help_text="Day of overload (null for EBQ)")
    product_group = models.CharField(max_length=100, blank=True)
    section = models.CharField(max_length=100, blank=True)
    item_code = models.CharField(max_length=100, blank=True, help_text="Specific item (EBQ flags)")
    planned_qty = models.FloatField(default=0)
    capacity_qty = models.FloatField(default=0, help_text="Available capacity / EBQ minimum")
    overload_pct = models.FloatField(default=0, help_text="(planned - capacity) / capacity × 100")
    detail = models.JSONField(default=dict, help_text="Machine code, utilization breakdown, etc.")
    reason_code = models.CharField(max_length=100, blank=True)
    reason_text = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["run", "flag_type"])]
        ordering = ["flag_type", "date", "product_group"]

    def __str__(self):
        return f"{self.flag_type} flag: {self.product_group or self.item_code} ({self.overload_pct:+.0f}%)"


# ── L6 Release ──────────────────────────────────────────────────
# Immutable snapshot of the approved plan.


class PPCRelease(models.Model):
    """Immutable release snapshot of an approved plan.

    Decision #4 defaults: a release is immutable once created. It can be
    recalled (soft-cancel) but the original snapshot stays for audit.
    A recalled release is replaced by a new release — never edited.
    Release rows are stored as PPCDataRow with table_key='release_rows'.
    """

    STATUS_CHOICES = [
        ("active", "Active"),
        ("recalled", "Recalled"),
    ]

    plan_month = models.CharField(max_length=7)
    release_number = models.PositiveIntegerField(
        help_text="Sequential within a month (1, 2, 3…)",
    )
    lot_number = models.CharField(
        max_length=20, blank=True,
        help_text="Formal lot ID: JCPL-YYMM-NNN (e.g. JCPL-2609-001)",
    )
    feasibility_run = models.ForeignKey(
        PPCFeasibilityRun, on_delete=models.CASCADE,
        related_name="releases",
    )
    source_batch = models.ForeignKey(
        PPCUploadBatch, on_delete=models.CASCADE,
        related_name="releases",
    )
    snapshot_batch = models.ForeignKey(
        PPCUploadBatch, on_delete=models.CASCADE,
        related_name="release_snapshots",
        null=True, blank=True,
        help_text="Batch holding the release_rows snapshot",
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="+",
    )
    released_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    recalled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    recalled_at = models.DateTimeField(null=True, blank=True)
    recall_reason = models.TextField(blank=True)
    row_count = models.IntegerField(default=0)
    summary = models.JSONField(default=dict, help_text="total_plan, sections, date_range")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan_month", "release_number"],
                name="uniq_release_month_number",
            ),
        ]
        ordering = ["-released_at"]

    def __str__(self):
        return f"Release {self.plan_month}#{self.release_number} [{self.status}]"


# ── L8 Execution & Feedback ─────────────────────────────────────


class PPCProductionEntry(models.Model):
    """Daily production entry by section supervisors.

    One row = one item × date × section × shift.
    This is UI data entry, not file upload.
    """

    date = models.DateField()
    item_code = models.CharField(max_length=100)
    section = models.CharField(max_length=100)
    shift = models.CharField(max_length=20, blank=True, default="general")
    produced_qty = models.FloatField()
    release = models.ForeignKey(
        PPCRelease, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="production_entries",
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="+",
    )
    entered_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "item_code", "section", "shift"],
                name="uniq_production_entry",
            ),
        ]
        indexes = [
            models.Index(fields=["date", "section"]),
            models.Index(fields=["item_code", "date"]),
        ]
        ordering = ["-date", "section", "item_code"]

    def __str__(self):
        return f"{self.item_code} {self.date} {self.section}: {self.produced_qty}"


class PPCRejectionEntry(models.Model):
    """In-process rejection entry.

    Uses stages from operation_stage_map (W1.5) and reason codes
    from reason_codes (W1.17). Monthly rejection % feeds back into
    MPS as a yield factor for the next cycle.
    """

    date = models.DateField()
    item_code = models.CharField(max_length=100)
    section = models.CharField(max_length=100)
    stage = models.CharField(max_length=100, help_text="From operation_stage_map (W1.5)")
    rejected_qty = models.FloatField()
    reason_code = models.CharField(max_length=100)
    reason_text = models.TextField(blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="+",
    )
    entered_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["date", "section"]),
            models.Index(fields=["item_code", "date"]),
        ]
        ordering = ["-date", "section"]

    def __str__(self):
        return f"REJ {self.item_code} {self.date} {self.stage}: {self.rejected_qty}"
