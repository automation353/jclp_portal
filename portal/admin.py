from django.contrib import admin

from .models import RawMaterial


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "on_hand", "reorder_level", "reorder_qty", "status", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)

    @admin.display(description="Buy?")
    def status(self, obj):
        return obj.status
