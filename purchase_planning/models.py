"""Purchase Planning (Purchase module) — data model.

Mirrors ``ppc_forecast`` almost exactly: one row per uploaded file. File
on disk, DB row for metadata, no parsing yet. Structuring this alongside
the other upload apps so parsing can be layered on later without a
schema change.
"""

from django.conf import settings
from django.db import models


class PurchasePlanningUpload(models.Model):
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_planning_uploads",
    )
    original_filename = models.CharField(max_length=255)
    stored_path = models.CharField(max_length=500)
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
