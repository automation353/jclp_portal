from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # JSON API for the React portal (frontend/).
    path("api/", include("portal.urls")),
    path("api/mto-mts/", include("mto_mts.urls")),
    path("api/ppc/", include("ppc.urls")),
    path("api/ppc-forecast/", include("ppc_forecast.urls")),
    path("api/purchase-planning/", include("purchase_planning.urls")),
    path("api/purchase-dashboards/", include("purchase_dashboards.urls")),
    path("api/purchase-controls/", include("purchase_controls.urls")),
    path("api/ppc-data/", include("ppc_data.urls")),
    path("api/sop/", include("sop.urls")),
    path("api/admin-panel/", include("accounts.api_urls")),
    # Server-rendered pages. Team Accounts and Login Activity still live here
    # until they're ported into the React portal.
    path("accounts/", include("accounts.urls")),
    path("", include("dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
