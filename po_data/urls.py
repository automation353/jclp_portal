from django.urls import path

from . import api

urlpatterns = [
    path("uploads/", api.list_uploads, name="po_data_list_uploads"),
    path("uploads/new/", api.upload, name="po_data_upload"),
]
