from django.urls import path

from . import api

urlpatterns = [
    path("uploads/", api.list_uploads, name="ppc_forecast_list_uploads"),
    path("uploads/new/", api.upload, name="ppc_forecast_upload"),
]
