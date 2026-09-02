"""PO Data (Purchase module) — data model.

Same shape as ``ppc``: one row per uploaded file. File to disk, metadata
in DB, no parsing state persisted here (parsing happens on the fly inside
the API endpoint before forwarding to n8n).
"""

from django.conf import settings
from django.db import models


class POUpload(models.Model):
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="po_uploads",
    )
    original_filename = models.CharField(max_length=255)
    stored_path = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_at:%Y-%m-%d %H:%M})"
