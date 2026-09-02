"""REST endpoints for the Purchase Planning module.

  POST /api/purchase-planning/uploads/new/   accept an xlsx, save + record
  GET  /api/purchase-planning/uploads/       list the last 30 uploads

Session-authenticated user (project default). Open to any signed-in user
for now; tighten if a role rule appears later.
"""

import os

from django.utils import timezone
from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .models import PurchasePlanningUpload
from .serializers import PurchasePlanningUploadSerializer


UPLOAD_ROOT_DEFAULT = "/root/jclp_automation_portal/jcpl/uploads/purchase_planning"


def _upload_root():
    return os.environ.get(
        "JCLP_PURCHASE_PLANNING_UPLOAD_ROOT", UPLOAD_ROOT_DEFAULT
    )


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


@api_view(["POST"])
@parser_classes([MultiPartParser])
def upload(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        notify(
            "Purchase Planning upload rejected — no file",
            f"{request.user.get_username()} posted to the Purchase Planning "
            "upload endpoint with no file attached.",
        )
        return Response(
            {"detail": "No file attached under the 'file' key."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not uploaded.name.lower().endswith((".xlsx", ".xlsm", ".xls", ".csv")):
        notify(
            "Purchase Planning upload rejected — wrong file type",
            f"{request.user.get_username()} tried to upload '{uploaded.name}', "
            "which isn't an .xlsx/.xls/.csv file.",
        )
        return Response(
            {"detail": "Please upload an .xlsx, .xls, or .csv file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stored_path, original_name = _store_uploaded_file(uploaded)
    notes = ("" if request.data.get("notes") is None else str(request.data["notes"]))[:500]

    row = PurchasePlanningUpload.objects.create(
        uploader=request.user,
        original_filename=original_name,
        stored_path=stored_path,
        notes=notes,
    )
    notify(
        f"Purchase Planning upload OK — {original_name}",
        f"{request.user.get_username()} uploaded '{original_name}' "
        f"(upload #{row.id}).",
    )
    return Response(
        PurchasePlanningUploadSerializer(row).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def list_uploads(request):
    qs = PurchasePlanningUpload.objects.all()[:30]
    return Response(PurchasePlanningUploadSerializer(qs, many=True).data)
