from django.urls import path

from . import api

urlpatterns = [
    path("upload/", api.upload, name="sop-upload"),
    path("uploads/", api.list_uploads, name="sop-uploads"),
    path("demand-supply/", api.demand_supply_overview, name="sop-demand-supply"),
    path("refresh/", api.refresh_append1, name="sop-refresh"),
    path("data/<str:table_key>/", api.table_data, name="sop-table-data"),
    path("append1-csv/", api.download_current_csv, name="sop-append1-csv"),
    path("dashboard-excel/", api.download_dashboard_excel, name="sop-dashboard-excel"),

    # Monthly snapshots
    path("snapshots/", api.snapshot_list, name="sop-snapshots"),
    path(
        "snapshots/<str:year_month>/csv/",
        api.snapshot_csv_download,
        name="sop-snapshot-csv",
    ),
]
