from django.contrib import admin

from .models import PurchasePlanningUpload


@admin.register(PurchasePlanningUpload)
class PurchasePlanningUploadAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploader", "uploaded_at", "notes")
    readonly_fields = ("uploaded_at",)
