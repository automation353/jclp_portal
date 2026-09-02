from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LoginEvent, User


@admin.register(User)
class JCPLUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "role", "department", "is_active", "last_login")
    list_filter = ("role", "department", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("JCPL access", {"fields": ("role", "department")}),
    )


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "timestamp", "ip_address")
    list_filter = ("event_type", "user")
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        return False  # written only by the login/logout signal handlers

    def has_change_permission(self, request, obj=None):
        return False  # audit trail — view/delete only, never edit
