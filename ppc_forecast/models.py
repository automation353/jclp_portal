"""PPC Forecast (S&OP module) — data model.

Minimal for now: one row per uploaded file. The file itself is written to
disk under ``jcpl/uploads/ppc_forecast/YYYY-MM/`` — the DB row remembers
the path, filename, timestamp, uploader, and an optional free-text note.

No parsing yet — that'll come once the file format is agreed. Structuring
this alongside ``mto_mts`` so the same processing pattern (upload row +
management-command parse) can be added later without a schema shuffle.
"""

from django.conf import settings
from django.db import models


class PPCForecastUpload(models.Model):
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ppc_forecast_uploads",
    )
    original_filename = models.CharField(max_length=255)
    stored_path = models.CharField(max_length=500)  # absolute path on disk
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=500, blank=True)
    # Retention policy (portal.enforce_upload_retention): past the 2 most
    # recent uploads, the raw file is deleted. No parsing exists yet for
    # this module, so the file IS the only copy of that upload's data —
    # confirmed as intentional. Record itself is never touched.
    file_removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_at:%Y-%m-%d %H:%M})"
