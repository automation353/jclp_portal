from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "nongrn"


def _p(route, view, name):
    """Register a nongrn view, gating it behind the portal login when
    NONGRN_REQUIRE_LOGIN is on. Auth stays contained to this app — the portal's
    global middleware is untouched, so no other module is affected."""
    if settings.NONGRN_REQUIRE_LOGIN:
        view = login_required(view)
    return path(route, view, name=name)


urlpatterns = [
    _p("", views.home, "home"),
    _p("sheet/report/", views.report, "report"),
    _p("sheet/dashboard/", views.dashboard, "dashboard"),
    _p("sheet/manual-grn/", views.manual_grn, "manual_grn"),
    _p("sheet/<slug:key>/", views.grid, "grid"),
    _p("api/sheet/<slug:key>/", views.grid_data, "grid_data"),
    _p("api/manual-grn/", views.manual_grn_api, "manual_grn_api"),
    _p("api/manual-grn/lookup/", views.manual_grn_lookup, "manual_grn_lookup"),
    _p("api/manual-grn/import/", views.manual_grn_import, "manual_grn_import"),
    _p("export/<slug:key>.<str:fmt>", views.export_sheet, "export"),
    _p("sources/", views.sources, "sources"),
    _p("sources/clear-logs/", views.clear_logs, "clear_logs"),
    _p("download/non-grn-age.xlsx", views.download_age_workbook, "download_age"),
    _p("refresh/", views.refresh, "refresh"),
    _p("refresh/status/", views.refresh_status, "refresh_status"),
]
