"""PPC (Production Planning & Control) — data model.

Same shape as ``ppc_forecast`` and ``purchase_planning``: one row per
uploaded file. File to disk, metadata in DB, no parsing yet.
"""

from django.conf import settings
from django.db import models


class PPCUpload(models.Model):
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ppc_uploads",
    )
    original_filename = models.CharField(max_length=255)
    stored_path = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=500, blank=True)
    # Retention policy (portal.enforce_upload_retention): past the 2 most
    # recent uploads, the raw file is deleted — its data already reached
    # the Google Sheet via _forward_to_sheet. Record itself is never touched.
    file_removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_at:%Y-%m-%d %H:%M})"
