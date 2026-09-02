from django.urls import path

from . import api

urlpatterns = [
    path("", api.summary, name="purchase_dashboards_summary"),
    # Per-tile drill-through — must precede the catch-all detail route.
    path("<slug:dashboard_key>/tiles/<slug:tile_key>/",
         api.tile_rows, name="purchase_dashboards_tile_rows"),
    path("<slug:dashboard_key>/", api.dashboard_detail, name="purchase_dashboards_detail"),
]
