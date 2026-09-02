from django.contrib import admin

from .models import PPCUpload


@admin.register(PPCUpload)
class PPCUploadAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploader", "uploaded_at", "notes")
    readonly_fields = ("uploaded_at",)
