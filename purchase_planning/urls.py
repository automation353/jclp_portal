from django.urls import path

from . import api

urlpatterns = [
    path("uploads/", api.list_uploads, name="purchase_planning_list_uploads"),
    path("uploads/new/", api.upload, name="purchase_planning_upload"),
]
