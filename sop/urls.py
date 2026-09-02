from django.urls import path

from . import api

urlpatterns = [
    path("upload/", api.upload, name="sop-upload"),
    path("uploads/", api.list_uploads, name="sop-uploads"),
    path("demand-supply/", api.demand_supply_overview, name="sop-demand-supply"),
    path("refresh/", api.refresh_append1, name="sop-refresh"),
    path("data/<str:table_key>/", api.table_data, name="sop-table-data"),
]
