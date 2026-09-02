"""REST endpoints for the MTO / MTS Monthly Status module.

Auth: all endpoints require an authenticated session (project default).
Upload endpoint additionally requires the user's department to be Operations.
Edits are open to any signed-in user in Phase 1 — Phase 3 will restrict
column-level access.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .models import (
    MtoMtsChange,
    MtoMtsEmailLog,
    MtoMtsItem,
    MtoMtsNotification,
    MtoMtsUpload,
)
from .notifications import fan_out
from .serializers import (
    MtoMtsChangeSerializer,
    MtoMtsEmailLogSerializer,
    MtoMtsItemSerializer,
    MtoMtsNotificationSerializer,
    MtoMtsUploadSerializer,
)


UPLOAD_ROOT_DEFAULT = "/root/jclp_automation_portal/jcpl/uploads/mto_mts"
EDITABLE_FIELDS = {
    "current_month_status",  # shared inline edit in the month cell
    "sales_reason", "ops_reason",
    "sales_status", "ops_status",  # kept for Phase 3+ tools; UI hides for now
}
STATUS_FIELDS = {"current_month_status", "sales_status", "ops_status"}
ALLOWED_STATUSES = {"MTS", "MTO", ""}


def _upload_root():
    return os.environ.get("JCLP_MTO_MTS_UPLOAD_ROOT", UPLOAD_ROOT_DEFAULT)


def _store_uploaded_file(uploaded_file) -> tuple:
    now = timezone.now()
    subdir = os.path.join(_upload_root(), now.strftime("%Y-%m"))
    os.makedirs(subdir, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%S")
    safe = os.path.basename(uploaded_file.name).replace(os.sep, "_")
    stored_path = os.path.join(subdir, f"{stamp}__{safe}")
    with open(stored_path, "wb") as out:
        for chunk in uploaded_file.chunks():
            out.write(chunk)
    return stored_path, safe


# ------------------------------------------------------------ uploads


def _spawn_process_command(upload_id: int) -> None:
    """Fire-and-forget `manage.py process_mto_mts_upload <id>` in a detached
    subprocess. The HTTP request returns immediately; the client polls the
    upload's status field to know when parsing has finished."""
    manage_py = Path(settings.BASE_DIR) / "manage.py"
    log_path = Path(settings.BASE_DIR) / "logs" / "mto_mts_process.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "ab")
    subprocess.Popen(
        [sys.executable, str(manage_py), "process_mto_mts_upload", str(upload_id)],
        cwd=str(settings.BASE_DIR),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,   # survives if the Django worker recycles
        close_fds=True,
    )


@api_view(["POST"])
@parser_classes([MultiPartParser])
def upload_xlsx(request):
    # Only Operations (or Super Admin) may upload. OEM Sales can view but
    # never publish the source file — see brief Stages D–G.
    if request.user.department != "Operations" and not request.user.is_super_admin:
        notify(
            "MTO/MTS upload rejected — wrong department",
            f"{request.user.get_username()} (department: {request.user.department}) "
            "tried to upload the MTO/MTS file and was rejected — only Operations "
            "may upload it.",
        )
        return Response(
            {"detail": "Only Operations can upload the MTO/MTS file."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Don't accept a new upload while a previous one is still being parsed —
    # otherwise the two subprocesses race on the same tables.
    already_processing = MtoMtsUpload.objects.filter(
        status=MtoMtsUpload.Status.PROCESSING
    ).exists()
    if already_processing:
        notify(
            "MTO/MTS upload rejected — another upload still processing",
            f"{request.user.get_username()} tried to upload the MTO/MTS file while "
            "an earlier upload was still being processed.",
        )
        return Response(
            {"detail": "An earlier upload is still being processed. Wait a few "
                       "seconds and try again."},
            status=status.HTTP_409_CONFLICT,
        )

    uploaded = request.FILES.get("file")
    if not uploaded:
        notify(
            "MTO/MTS upload rejected — no file",
            f"{request.user.get_username()} posted to the MTO/MTS upload endpoint "
            "with no file attached.",
        )
        return Response(
            {"detail": "No file attached under the 'file' key."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not uploaded.name.lower().endswith((".xlsx", ".xlsm")):
        notify(
            "MTO/MTS upload rejected — wrong file type",
            f"{request.user.get_username()} tried to upload '{uploaded.name}', "
            "which isn't an .xlsx/.xlsm file.",
        )
        return Response(
            {"detail": "Please upload an .xlsx file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stored_path, original_name = _store_uploaded_file(uploaded)

    upload = MtoMtsUpload.objects.create(
        uploader=request.user,
        original_filename=original_name,
        stored_path=stored_path,
        status=MtoMtsUpload.Status.PROCESSING,
    )
    _spawn_process_command(upload.id)

    notify(
        f"MTO/MTS upload received — {original_name}",
        f"{request.user.get_username()} uploaded '{original_name}' "
        f"(upload #{upload.id}) — processing has started in the background.",
    )
    return Response(
        MtoMtsUploadSerializer(upload).data, status=status.HTTP_202_ACCEPTED
    )


@api_view(["GET"])
def list_uploads(request):
    qs = MtoMtsUpload.objects.all()[:20]
    return Response(MtoMtsUploadSerializer(qs, many=True).data)


def _serialize_upload_with_items(upload):
    """Full upload payload including items/cells. Used by both /current/
    and /uploads/<id>/ so both paths return the same shape."""
    if upload.status != MtoMtsUpload.Status.ACTIVE:
        # PROCESSING / FAILED / LOCKED / SUPERSEDED: no fresh items payload
        # — for LOCKED and SUPERSEDED the DB rows still exist but the UI
        # renders them as read-only anyway; return them so the table can
        # display the historical numbers.
        if upload.status in (
            MtoMtsUpload.Status.LOCKED,
            MtoMtsUpload.Status.SUPERSEDED,
        ):
            items = upload.items.prefetch_related("cells").all()
            return {
                "upload": MtoMtsUploadSerializer(upload).data,
                "month_labels": _month_labels(upload),
                "items": MtoMtsItemSerializer(items, many=True).data,
            }
        return {
            "upload": MtoMtsUploadSerializer(upload).data,
            "month_labels": [],
            "items": [],
        }

    items = upload.items.prefetch_related("cells").all()
    return {
        "upload": MtoMtsUploadSerializer(upload).data,
        "month_labels": _month_labels(upload),
        "items": MtoMtsItemSerializer(items, many=True).data,
    }


@api_view(["GET"])
def current_upload(request):
    """Return the freshest upload the user should see.

    Preference order:
      1. an ACTIVE upload — the current cycle
      2. a PROCESSING / FAILED upload — so the UI can keep the operator informed
      3. the newest LOCKED / SUPERSEDED upload — so Sales always has SOMETHING
         to look at (Change instruction 5 — "never a blank screen")

    Only 404s when nothing at all has ever been uploaded, and only reports
    ``current_month_missing=True`` when the freshest upload is not ACTIVE —
    so the UI can show the "Operations has not yet uploaded" banner while
    still displaying the last-run data underneath.
    """
    active = (
        MtoMtsUpload.objects
        .filter(status=MtoMtsUpload.Status.ACTIVE)
        .order_by("-uploaded_at")
        .first()
    )
    if active:
        payload = _serialize_upload_with_items(active)
        payload["current_month_missing"] = False
        return Response(payload)

    pending = (
        MtoMtsUpload.objects
        .filter(status__in=[
            MtoMtsUpload.Status.PROCESSING,
            MtoMtsUpload.Status.FAILED,
        ])
        .order_by("-uploaded_at")
        .first()
    )
    if pending:
        payload = _serialize_upload_with_items(pending)
        payload["current_month_missing"] = True
        return Response(payload)

    historical = (
        MtoMtsUpload.objects
        .filter(status__in=[
            MtoMtsUpload.Status.LOCKED,
            MtoMtsUpload.Status.SUPERSEDED,
        ])
        .order_by("-uploaded_at")
        .first()
    )
    if historical:
        payload = _serialize_upload_with_items(historical)
        payload["current_month_missing"] = True
        return Response(payload)

    return Response(
        {"detail": "No MTO/MTS file has been uploaded yet."},
        status=status.HTTP_404_NOT_FOUND,
    )


@api_view(["GET"])
def upload_detail(request, upload_id):
    """Fetch any single upload by id — used when Sales opens the month picker
    and asks for an older month's data (Change instruction 5)."""
    try:
        upload = MtoMtsUpload.objects.get(pk=upload_id)
    except MtoMtsUpload.DoesNotExist:
        return Response({"detail": "Upload not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_serialize_upload_with_items(upload))


def _month_labels(upload):
    """Union of every month_label across the upload's cells, ordered by index."""
    first_item = upload.items.first()
    if not first_item:
        return []
    return list(
        first_item.cells.order_by("month_index").values_list("month_label", flat=True)
    )


# ------------------------------------------------------------ item edits


@api_view(["PATCH"])
def edit_item(request, item_id):
    try:
        item = MtoMtsItem.objects.get(pk=item_id)
    except MtoMtsItem.DoesNotExist:
        return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)

    if item.upload.status != MtoMtsUpload.Status.ACTIVE:
        # Block editing of processing / locked / failed / superseded uploads.
        if item.upload.status == MtoMtsUpload.Status.LOCKED:
            msg = "This file is locked — the monthly review cycle is closed."
        else:
            msg = f"This file is {item.upload.status} — edits are not allowed."
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    # Optional per-edit reason (Change instruction 8). Applied to every field
    # touched in this PATCH — the whole edit is treated as one intent.
    raw_comment = request.data.get("comment")
    comment = ("" if raw_comment is None else str(raw_comment)).strip()[:500]

    changes_written = []
    portal_url = request.build_absolute_uri("/mto-mts")
    changed_current_month_status = False

    for field_name, new_value in request.data.items():
        if field_name == "comment":
            continue  # handled above, not a field on the item
        if field_name not in EDITABLE_FIELDS:
            continue
        new_value = ("" if new_value is None else str(new_value)).strip()
        if field_name in STATUS_FIELDS:
            up = new_value.upper()
            if up not in ALLOWED_STATUSES:
                return Response(
                    {"detail": f"'{field_name}' must be MTS, MTO or blank — got '{new_value}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_value = up
        if len(new_value) > 500:
            return Response(
                {"detail": f"'{field_name}' is longer than 500 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_value = getattr(item, field_name)

        # First-ever override of the current-month status: the reviewer's
        # visible "from" value is the sheet's last completed month, not the
        # empty DB column. Substitute so the change log matches what the
        # reviewer actually saw when they clicked.
        if field_name == "current_month_status" and not old_value:
            last_cell = (
                item.cells.exclude(value="").order_by("-month_index").first()
            )
            if last_cell:
                old_value = last_cell.value

        if old_value == new_value:
            continue

        setattr(item, field_name, new_value)
        change = MtoMtsChange(
            item=item,
            field=field_name,
            old_value=old_value or "",
            new_value=new_value or "",
            comment=comment,
            changed_by=request.user,
            department=request.user.department or "",
        )
        changes_written.append(change)
        if field_name == "current_month_status":
            changed_current_month_status = True

    if not changes_written:
        return Response(MtoMtsItemSerializer(item).data)

    # Change instructions 11 + 12 — stamp who last touched the current-month
    # status so the UI can colour the cell and show the (S) / (O) tag.
    save_fields = [c.field for c in changes_written]
    if changed_current_month_status:
        item.last_edited_by_dept = request.user.department or ""
        save_fields.append("last_edited_by_dept")

    with transaction.atomic():
        item.save(update_fields=save_fields)
        MtoMtsChange.objects.bulk_create(changes_written)

    for change in MtoMtsChange.objects.filter(
        item=item, changed_by=request.user
    ).order_by("-changed_at")[: len(changes_written)]:
        fan_out(change, portal_url=portal_url)

    return Response(MtoMtsItemSerializer(item).data)


# ------------------------------------------------------------ changes / notifications


@api_view(["GET"])
def list_changes(request):
    upload = (
        MtoMtsUpload.objects
        .filter(status=MtoMtsUpload.Status.ACTIVE)
        .order_by("-uploaded_at")
        .first()
    )
    if upload is None:
        return Response([])
    qs = MtoMtsChange.objects.filter(item__upload=upload).select_related(
        "item", "changed_by"
    )[:500]
    return Response(MtoMtsChangeSerializer(qs, many=True).data)


@api_view(["GET"])
def list_notifications(request):
    qs = (
        MtoMtsNotification.objects
        .filter(recipient=request.user)
        .select_related("change", "change__item", "change__changed_by")[:50]
    )
    unread = MtoMtsNotification.objects.filter(
        recipient=request.user, seen_at__isnull=True
    ).count()

    # Change instruction 3 — surface the latest ACTIVE upload alongside the
    # per-user notifications so the top-bar poller can pop an "upload" toast
    # for every user in either department (including the uploader) without
    # needing a separate schema for upload events.
    latest_active = (
        MtoMtsUpload.objects
        .filter(status=MtoMtsUpload.Status.ACTIVE)
        .order_by("-uploaded_at")
        .first()
    )
    latest_summary = None
    if latest_active:
        latest_summary = {
            "id": latest_active.id,
            "original_filename": latest_active.original_filename,
            "month_label": latest_active.month_label,
            "uploader_username": (
                latest_active.uploader.username if latest_active.uploader else ""
            ),
            "uploaded_at": latest_active.uploaded_at.isoformat(),
        }

    return Response({
        "unread_count": unread,
        "items": MtoMtsNotificationSerializer(qs, many=True).data,
        "latest_active_upload": latest_summary,
    })


@api_view(["POST"])
def mark_notifications_seen(request):
    MtoMtsNotification.objects.filter(
        recipient=request.user, seen_at__isnull=True
    ).update(seen_at=timezone.now())
    return Response({"detail": "Marked seen."})


# ------------------------------------------------------------ email log (Stage E audit)


@api_view(["GET"])
def list_emails(request):
    qs = MtoMtsEmailLog.objects.all()[:200]
    return Response(MtoMtsEmailLogSerializer(qs, many=True).data)
