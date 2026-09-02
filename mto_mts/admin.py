from django.contrib import admin

from .models import (
    MtoMtsChange,
    MtoMtsCell,
    MtoMtsEmailLog,
    MtoMtsItem,
    MtoMtsNotification,
    MtoMtsUpload,
)


@admin.register(MtoMtsUpload)
class MtoMtsUploadAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploader", "month_label", "status", "uploaded_at")
    list_filter = ("status",)


@admin.register(MtoMtsItem)
class MtoMtsItemAdmin(admin.ModelAdmin):
    list_display = ("item_code", "item_group", "sales_status", "ops_status", "upload")
    list_filter = ("upload", "sales_status", "ops_status")
    search_fields = ("item_code", "item_group")


@admin.register(MtoMtsChange)
class MtoMtsChangeAdmin(admin.ModelAdmin):
    list_display = ("changed_at", "item", "field", "old_value", "new_value", "changed_by")
    list_filter = ("field", "department")
    readonly_fields = tuple(f.name for f in MtoMtsChange._meta.fields)


@admin.register(MtoMtsEmailLog)
class MtoMtsEmailLogAdmin(admin.ModelAdmin):
    list_display = ("sent_at", "kind", "subject", "recipients", "delivered")
    list_filter = ("kind", "delivered")
    readonly_fields = tuple(f.name for f in MtoMtsEmailLog._meta.fields)


admin.site.register(MtoMtsCell)
admin.site.register(MtoMtsNotification)
