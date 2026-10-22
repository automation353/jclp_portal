from django.contrib import admin

from .models import ActivityLog, ManualGRN, RefreshRun


@admin.register(ManualGRN)
class ManualGRNAdmin(admin.ModelAdmin):
    list_display = ("invoice_no", "grn_date", "updated_by", "updated_at")
    search_fields = ("invoice_no",)


@admin.register(RefreshRun)
class RefreshRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "finished_at", "status", "triggered_by")
    readonly_fields = ("started_at", "finished_at", "status", "message", "row_counts", "files", "triggered_by")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("at", "kind", "status", "user", "title")
    list_filter = ("kind", "status")
