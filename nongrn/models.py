from django.conf import settings
from django.db import models


class ManualGRN(models.Model):
    """Rows of the editable 'Manual GRN' sheet (Invoice Number | GRN Date).

    Combine!HZ uses XLOOKUP(Invoice No,'Manual GRN'!A:A,'Manual GRN'!B:B) when the
    ERP has no Goods Received Date for the invoice.
    """

    invoice_no = models.CharField("Invoice Number", max_length=64, unique=True)
    grn_date = models.DateField("GRN Date")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["id"]
        verbose_name = "Manual GRN"
        verbose_name_plural = "Manual GRN"

    def __str__(self):
        return f"{self.invoice_no} → {self.grn_date:%d-%m-%Y}"


class RefreshRun(models.Model):
    """One 'Refresh All' (Power Query) run."""

    RUNNING, OK, FAILED = "running", "ok", "failed"
    STATUS_CHOICES = [(RUNNING, "Running"), (OK, "Success"), (FAILED, "Failed")]

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=RUNNING)
    message = models.TextField(blank=True)
    row_counts = models.JSONField(default=dict, blank=True)
    files = models.JSONField(default=dict, blank=True)
    triggered_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Refresh {self.started_at:%d-%m-%Y %H:%M} ({self.status})"

    @property
    def duration_text(self):
        if not self.finished_at:
            return ""
        secs = int((self.finished_at - self.started_at).total_seconds())
        return f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"


class ActivityLog(models.Model):
    """What the Sources page shows as its activity log: every upload and every Refresh All.

    Kept apart from RefreshRun so 'Clear logs' never touches the portal's refresh state.
    """

    UPLOAD, REFRESH = "upload", "refresh"
    KIND_CHOICES = [(UPLOAD, "Upload"), (REFRESH, "Refresh All")]
    OK, FAILED = "ok", "failed"
    STATUS_CHOICES = [(OK, "Success"), (FAILED, "Failed")]

    at = models.DateTimeField(db_index=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    user = models.CharField(max_length=150, blank=True)
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    source = models.CharField(max_length=100, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    link = models.URLField(max_length=500, blank=True)
    duration = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.at:%d-%m-%Y %H:%M} ({self.status})"

    @property
    def reason(self):
        """Refresh All: why it ran ('after upload X.xlsx'), empty for a manual run."""
        return self.title.split(" – ", 1)[1] if " – " in self.title else ""

    @property
    def duration_text(self):
        if self.duration is None:
            return ""
        secs = int(round(self.duration))
        return f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"
