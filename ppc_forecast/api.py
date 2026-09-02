"""REST endpoints for the PPC Forecast module (S&OP department).

For Phase 1 there are two endpoints:

  POST /api/ppc-forecast/uploads/   accept an xlsx, save to disk, record it
  GET  /api/ppc-forecast/uploads/   list the last 30 uploads

Auth = session-authenticated user (project default). No department gate for
now — S&OP is cross-functional, so anyone signed in can post. Tighten if a
role rule appears later.
"""

import os

from django.utils import timezone
from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .models import PPCForecastUpload
from .serializers import PPCForecastUploadSerializer


UPLOAD_ROOT_DEFAULT = "/root/jclp_automation_portal/jcpl/uploads/ppc_forecast"


def _upload_root():
    return os.environ.get("JCLP_PPC_FORECAST_UPLOAD_ROOT", UPLOAD_ROOT_DEFAULT)


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
            "PPC Forecast upload rejected — no file",
            f"{request.user.get_username()} posted to the PPC Forecast upload "
            "endpoint with no file attached.",
        )
        return Response(
            {"detail": "No file attached under the 'file' key."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not uploaded.name.lower().endswith((".xlsx", ".xlsm", ".xls", ".csv")):
        notify(
            "PPC Forecast upload rejected — wrong file type",
            f"{request.user.get_username()} tried to upload '{uploaded.name}', "
            "which isn't an .xlsx/.xls/.csv file.",
        )
        return Response(
            {"detail": "Please upload an .xlsx, .xls, or .csv file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stored_path, original_name = _store_uploaded_file(uploaded)
    notes = ("" if request.data.get("notes") is None else str(request.data["notes"]))[:500]

    row = PPCForecastUpload.objects.create(
        uploader=request.user,
        original_filename=original_name,
        stored_path=stored_path,
        notes=notes,
    )
    notify(
        f"PPC Forecast upload OK — {original_name}",
        f"{request.user.get_username()} uploaded '{original_name}' "
        f"(upload #{row.id}).",
    )
    return Response(
        PPCForecastUploadSerializer(row).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def list_uploads(request):
    qs = PPCForecastUpload.objects.all()[:30]
    return Response(PPCForecastUploadSerializer(qs, many=True).data)
