from django.contrib import admin

from .models import POUpload


@admin.register(POUpload)
class POUploadAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploader", "uploaded_at", "notes")
    readonly_fields = ("uploaded_at",)
