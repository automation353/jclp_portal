"""MTO / MTS Monthly Status — data model.

One `MtoMtsUpload` per xlsx file uploaded by Operations. Its rows become
`MtoMtsItem`s (one per stock item), and each historical monthly cell becomes
an `MtoMtsCell`.

Every editable field change is captured as an `MtoMtsChange` (append-only
audit log). Each change fans out to every user in either department as
`MtoMtsNotification`s — that's what powers the in-app bell.
"""

from django.conf import settings
from django.db import models


class MtoMtsUpload(models.Model):
    """One uploaded xlsx source file. Original is stored on disk, never edited."""

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"   # subprocess running
        ACTIVE = "active", "Active"                # ready for review
        LOCKED = "locked", "Locked"                # cycle finalised — no edits
        FAILED = "failed", "Failed"                # parse/insert error
        SUPERSEDED = "superseded", "Superseded"    # replaced by a newer active file

    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mto_mts_uploads",
    )
    original_filename = models.CharField(max_length=255)
    stored_path = models.CharField(max_length=500)  # absolute path on disk
    month_label = models.CharField(max_length=32, blank=True)  # e.g. "August 2026"
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # When the monthly cycle ends and this file becomes read-only. Computed
    # at upload time; a scheduled command flips status → LOCKED when reached.
    lock_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    # Retention policy (portal.enforce_upload_retention): once this upload
    # falls past the 2 most recent, the raw file is deleted from disk — the
    # parsed data already lives in MtoMtsItem, so nothing is lost. This
    # timestamp is set when that happens; stored_path still points at the
    # (now-gone) file so the record itself is never touched.
    file_removed_at = models.DateTimeField(null=True, blank=True)
    validation_notes = models.TextField(
        blank=True,
        help_text="Any parsing warnings/exceptions — see Section 3/5 of the brief.",
    )

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_at:%Y-%m-%d %H:%M})"


class MtoMtsItem(models.Model):
    """One stock item within one upload."""

    upload = models.ForeignKey(
        MtoMtsUpload, on_delete=models.CASCADE, related_name="items"
    )
    item_group = models.CharField(max_length=200)
    item_code = models.CharField(max_length=100)

    # Shared editable value for the "current month" (the last month with data
    # in the source file). Both Operations and OEM Sales write to the same
    # field — last save wins, and the change log records who did it.
    current_month_status = models.CharField(max_length=8, blank=True)

    # Which team last touched current_month_status — drives the on-screen
    # colour + inline (S) / (O) tag (Change instructions 11 + 12).
    last_edited_by_dept = models.CharField(max_length=100, blank=True)

    # Segment slicer support (Change instruction 15). Populated from a
    # "Segment" column in the source xlsx if present; otherwise blank.
    segment = models.CharField(max_length=64, blank=True)

    # Account/customer category from the sheet's "Item A/C Description"
    # column (added by Rasika after the 11-Aug review). Drives the Account
    # dropdown filter beside the segment slicer.
    account_description = models.CharField(max_length=128, blank=True)

    # Per-department comment fields — each department keeps their own notes.
    sales_reason = models.CharField(max_length=500, blank=True)
    ops_reason = models.CharField(max_length=500, blank=True)

    # Kept in the schema for Phase 3/4 (column-locking, conflict detection)
    # but unused in Phase 1's shared-cell UX above.
    sales_status = models.CharField(max_length=8, blank=True)
    ops_status = models.CharField(max_length=8, blank=True)

    # Filled by Phase 2 (classification engine). Kept here so the schema
    # doesn't need another migration when we get there.
    system_suggested = models.CharField(max_length=8, blank=True)
    trend_tag = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["upload", "item_code"])]
        ordering = ["item_group", "item_code"]

    def __str__(self):
        return f"{self.item_code} ({self.item_group})"


class MtoMtsCell(models.Model):
    """One historical monthly cell — read-only after ingest."""

    item = models.ForeignKey(
        MtoMtsItem, on_delete=models.CASCADE, related_name="cells"
    )
    month_label = models.CharField(max_length=32)      # verbatim header text
    month_index = models.PositiveIntegerField()         # 0-based left→right
    value = models.CharField(max_length=8, blank=True)  # "MTS" | "MTO" | ""

    class Meta:
        ordering = ["month_index"]
        indexes = [models.Index(fields=["item", "month_index"])]


class MtoMtsChange(models.Model):
    """One row per edit. Append-only audit trail (Section 5 of the brief)."""

    class Field(models.TextChoices):
        CURRENT_MONTH_STATUS = "current_month_status", "Current month status"
        SALES_REASON = "sales_reason", "Sales reason"
        OPS_REASON = "ops_reason", "Operations reason"
        SALES_STATUS = "sales_status", "Sales status"
        OPS_STATUS = "ops_status", "Operations status"

    item = models.ForeignKey(
        MtoMtsItem, on_delete=models.CASCADE, related_name="changes"
    )
    field = models.CharField(max_length=32, choices=Field.choices)
    old_value = models.CharField(max_length=500, blank=True)
    new_value = models.CharField(max_length=500, blank=True)
    # Short reason/comment supplied by the reviewer at the moment of change
    # (Change instruction 8). Free text; not required by the DB but usually
    # requested by the UI when a status flip happens.
    comment = models.CharField(max_length=500, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mto_mts_changes",
    )
    # Snapshot the department name at write-time — if the user is later moved
    # to a different department, the log still reads correctly.
    department = models.CharField(max_length=100, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        indexes = [models.Index(fields=["item", "changed_at"])]


class MtoMtsEmailLog(models.Model):
    """One row per email actually dispatched by the module.

    Kept as its own table so the audit trail satisfies Section 5 of the
    brief — "every email must be recorded with what happened, which item
    or upload it relates to, and the exact date and time". Never edited
    after write.
    """

    class Kind(models.TextChoices):
        PUBLICATION = "publication", "Publication"     # Stage E
        CHANGE = "change", "Change"                    # Stages F/G fan-out

    upload = models.ForeignKey(
        MtoMtsUpload,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="emails",
    )
    change = models.ForeignKey(
        "MtoMtsChange",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="emails",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    subject = models.CharField(max_length=255)
    recipients = models.TextField(
        help_text="Comma-separated list of To: addresses this email went to."
    )
    body_preview = models.TextField(
        blank=True,
        help_text="First few lines of the body, for the audit UI.",
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    delivered = models.BooleanField(
        default=True,
        help_text="False if the SMTP send raised — the log still records the attempt.",
    )

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.kind}: {self.subject} → {self.recipients[:60]}"


class MtoMtsNotification(models.Model):
    """One notification per (change × recipient). Drives the top-bar bell."""

    change = models.ForeignKey(
        MtoMtsChange, on_delete=models.CASCADE, related_name="notifications"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mto_mts_notifications",
    )
    seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "seen_at"])]
