from django.urls import path

from . import api

urlpatterns = [
    path("auth/csrf/", api.csrf, name="api_csrf"),
    path("auth/login/", api.login, name="api_login"),
    path("auth/logout/", api.logout, name="api_logout"),
    path("auth/me/", api.me, name="api_me"),
    path("departments/", api.departments, name="api_departments"),
    path("purchase/portals/", api.purchase_portals, name="api_purchase_portals"),
    path("purchase/raw-materials/", api.raw_materials, name="api_raw_materials"),
    path("purchase/ebq/", api.ebq, name="api_ebq"),
]
