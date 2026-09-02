from django.urls import path

from . import api

urlpatterns = [
    path("uploads/", api.list_uploads, name="mto_mts_list_uploads"),
    path("uploads/new/", api.upload_xlsx, name="mto_mts_upload_xlsx"),
    path("uploads/current/", api.current_upload, name="mto_mts_current_upload"),
    path("uploads/<int:upload_id>/", api.upload_detail, name="mto_mts_upload_detail"),
    path("items/<int:item_id>/", api.edit_item, name="mto_mts_edit_item"),
    path("changes/", api.list_changes, name="mto_mts_list_changes"),
    path("notifications/", api.list_notifications, name="mto_mts_list_notifications"),
    path("notifications/mark-seen/", api.mark_notifications_seen,
         name="mto_mts_mark_notifications_seen"),
    path("emails/", api.list_emails, name="mto_mts_list_emails"),
]
