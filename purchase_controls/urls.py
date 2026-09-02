from django.urls import path

from . import api

urlpatterns = [
    path("", api.summary, name="purchase_controls_summary"),
    path("<slug:control_key>/tiles/<slug:tile_key>/",
         api.tile_rows, name="purchase_controls_tile_rows"),
]
