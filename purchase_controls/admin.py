from django.contrib import admin

from .models import ControlResult, ControlRunHistory, RequirementAge


@admin.register(ControlResult)
class ControlResultAdmin(admin.ModelAdmin):
    list_display = ("control_key", "snapshot", "computed_at")
    list_filter = ("control_key",)
    ordering = ("-computed_at",)


@admin.register(ControlRunHistory)
class ControlRunHistoryAdmin(admin.ModelAdmin):
    list_display = ("control_key", "snapshot", "population", "run_at")
    list_filter = ("control_key",)
    ordering = ("-run_at",)


@admin.register(RequirementAge)
class RequirementAgeAdmin(admin.ModelAdmin):
    """Read-mostly on purpose: first_seen is the clock Control 2 depends on,
    and editing it would rewrite history."""
    list_display = ("item_key", "first_seen", "last_seen", "times_seen", "first_qty")
    search_fields = ("item_key",)
    readonly_fields = ("first_seen", "last_seen", "times_seen")
    ordering = ("first_seen",)
