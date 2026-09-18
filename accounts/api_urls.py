"""URL patterns for the Super Admin panel API (mounted at /api/admin-panel/)."""

from django.urls import path

from . import api_views

urlpatterns = [
    path("stats/", api_views.admin_stats, name="admin_stats"),
    path("modules/", api_views.module_list, name="admin_modules"),
    path("users/", api_views.UserListCreateView.as_view(), name="admin_users"),
    path("users/<int:pk>/", api_views.UserDetailView.as_view(), name="admin_user_detail"),
    path("users/<int:pk>/toggle/", api_views.user_toggle_active, name="admin_user_toggle"),
    path("activity/", api_views.ActivityListView.as_view(), name="admin_activity"),
]
