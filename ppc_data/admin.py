from django.contrib import admin

from .models import PPCComputeResult, PPCDataRow, PPCUploadBatch


@admin.register(PPCUploadBatch)
class PPCUploadBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id", "table_key", "level", "file_type",
        "original_filename", "uploader", "uploaded_at",
        "row_count", "is_current",
    )
    list_filter = ("table_key", "level", "is_current")
    readonly_fields = ("uploaded_at",)
    search_fields = ("table_key", "original_filename")


@admin.register(PPCDataRow)
class PPCDataRowAdmin(admin.ModelAdmin):
    list_display = ("id", "table_key", "sr_no", "batch")
    list_filter = ("table_key",)
    raw_id_fields = ("batch",)


@admin.register(PPCComputeResult)
class PPCComputeResultAdmin(admin.ModelAdmin):
    list_display = ("id", "compute_key", "batch", "computed_at")
    list_filter = ("compute_key",)
    raw_id_fields = ("batch",)
