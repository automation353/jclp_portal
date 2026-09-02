from django.contrib import admin

from .models import PPCForecastUpload


@admin.register(PPCForecastUpload)
class PPCForecastUploadAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploader", "uploaded_at", "notes")
    readonly_fields = ("uploaded_at",)
