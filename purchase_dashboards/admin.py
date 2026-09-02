from django.contrib import admin

from .models import PurchaseDashResult, PurchaseDashRow, PurchaseDashSnapshot


@admin.register(PurchaseDashSnapshot)
class PurchaseDashSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "fetched_at", "row_count", "is_current", "sheet_id", "gid")
    list_filter = ("is_current",)
    readonly_fields = ("fetched_at",)


@admin.register(PurchaseDashResult)
class PurchaseDashResultAdmin(admin.ModelAdmin):
    list_display = ("dashboard_key", "snapshot", "computed_at")
    list_filter = ("dashboard_key",)


admin.site.register(PurchaseDashRow)
