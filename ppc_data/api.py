"""REST endpoints for the PPC Data Pipeline.

  POST /api/ppc-data/upload/          upload an xlsx, auto-detect table type
  GET  /api/ppc-data/uploads/         list recent upload batches
  GET  /api/ppc-data/table/<key>/     retrieve current rows for a table
  POST /api/ppc-data/erp-landing/     receive ERP report JSON from n8n

Same pattern as purchase_dashboards: upload → parse → store rows with
stable field keys → serve via REST. The xlsx parsing uses openpyxl
(already available from the ppc app).
"""

import logging
import os

from django.db import transaction
from django.utils import timezone
from portal.notify import notify
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from .field_maps.erp import ERP_REGISTRY, get_erp_field_map
from .models import PPCDataRow, PPCUploadBatch
from .parsers import PARSERS
from .serializers import PPCUploadBatchSerializer

log = logging.getLogger(__name__)

UPLOAD_ROOT_DEFAULT = "/root/jclp_automation_portal/jcpl/uploads/ppc_data"


def _upload_root():
    return os.environ.get("JCLP_PPC_DATA_UPLOAD_ROOT", UPLOAD_ROOT_DEFAULT)


def _store_file(uploaded_file):
    """Save uploaded file to disk, return (stored_path, original_name)."""
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


def _detect_table_key(filename, sheet_names=None):
    """Auto-detect which table_key a file maps to from its filename.
    Returns table_key string or None.

    Rules are checked top-to-bottom; first match wins.
    """
    fn = filename.lower()

    # W1.1 — Product Group Mapping.xlsx → item_master
    if "product" in fn and "group" in fn and "mapping" in fn:
        return "item_master"
    # W1.11 — BOM_Item_Template.xlsx → bom_master
    if "bom" in fn and ("template" in fn or "item" in fn):
        return "bom_master"
    # W1.2 — Monitoring.xlsx (Family Group sheet) → family_hierarchy
    if "monitoring" in fn:
        return "family_hierarchy"
    # W1.4 — Process File.xlsx → route_master
    if "process" in fn and "file" in fn:
        return "route_master"
    # W1.5 — In process-Rejection.xlsx → operation_stage_map
    if "rejection" in fn or ("process" in fn and "reject" in fn):
        return "operation_stage_map"
    # W1.6 — Production Targets.xlsx → capacity_ppp
    if "production" in fn and "target" in fn:
        return "capacity_ppp"
    # W1.7 — Machine Loading data.xlsx → machine_master
    if "machine" in fn and "loading" in fn:
        return "machine_master"
    # W1.9 — Lead Time Data.xlsx → lead_time
    if "lead" in fn and "time" in fn:
        return "lead_time"
    # W1.12 — T-Bolt BOM master → part_engineering
    if "t-bolt" in fn or "tbolt" in fn or "part" in fn and "engineering" in fn:
        return "part_engineering"
    # W1.13 — SO Tracking Master → customer_part
    if "so" in fn and "tracking" in fn:
        return "customer_part"
    # W1.14 — Green Level RM/CP/Packing → stock_policy
    if "green" in fn and "level" in fn:
        return "stock_policy"
    # W1.16 — ASP for FG.xlsx → rate_asp
    if "asp" in fn:
        return "rate_asp"
    # W1.8 — (if "ebq" or "batch" in fn from Monitoring)
    if "ebq" in fn or ("batch" in fn and "qty" in fn):
        return "batch_ebq"
    # L2 — Dispatch Trends.xlsx → demand_history
    if "dispatch" in fn and "trend" in fn:
        return "demand_history"
    # L2 — Forecast / demand → demand_freeze (generic pattern, but not ERP exports)
    if "forecast" in fn and "erp" not in fn:
        return "demand_freeze"
    # L3 — MpsSS.xlsm → mps_schedule
    if "mps" in fn and ("schedule" in fn or "ss" in fn):
        return "mps_schedule"
    # L4 — R3 SS.xlsx / R3SS.xlsx → r3ss_plan
    if "r3" in fn and "ss" in fn:
        return "r3ss_plan"
    if "r3ss" in fn:
        return "r3ss_plan"

    # ── L1 — ERP report auto-detect (manual upload) ──
    # Stock files
    if "fg" in fn and "stock" in fn:
        return "erp_fg_stock"
    if "cp" in fn and "stock" in fn:
        return "erp_cp_stock"
    if "rm" in fn and "stock" in fn:
        return "erp_rm_stock"
    if "pm" in fn and "stock" in fn:
        return "erp_pm_stock"
    if "consumable" in fn:
        return "erp_consumables"
    # Production
    if "prod" in fn and "semi" in fn:
        return "erp_prod_semi"
    if "prod" in fn and "fg" in fn:
        return "erp_prod_fg"
    # Orders & procurement
    if "sales" in fn and "order" in fn:
        return "erp_sales_orders"
    # PR before PO — "po" is a substring of "report", so check PR first
    if "pending" in fn and ("_pr" in fn or " pr" in fn or fn.startswith("pr")):
        return "erp_pending_pr"
    if "pending" in fn and ("_po" in fn or " po" in fn or fn.startswith("po")):
        return "erp_pending_po"
    # Material / cost
    if "material" in fn and "issue" in fn:
        return "erp_material_issue"
    if "item" in fn and "cost" in fn:
        return "erp_item_cost"
    # BOM from ERP (distinct from BOM template master)
    if "bom" in fn and "erp" in fn:
        return "erp_bom"
    # Item master from ERP (distinct from product group mapping)
    if "item" in fn and "master" in fn and "erp" in fn:
        return "erp_item_master"
    # Dispatch from ERP
    if "dispatch" in fn and "erp" in fn:
        return "erp_dispatch"
    # FG ageing
    if "fg" in fn and "age" in fn:
        return "erp_fg_ageing"
    # Forecast from ERP
    if "forecast" in fn and "erp" in fn:
        return "erp_forecast"

    return None


@api_view(["POST"])
@parser_classes([MultiPartParser])
def upload(request):
    """Upload an xlsx file. Auto-detects table type from filename,
    parses it, and stores rows in the database.

    Query params:
      ?table_key=item_master   — force a specific table key (overrides auto-detect)

    Form data:
      file      — the xlsx file
      notes     — optional notes string
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response(
            {"detail": "No file attached under the 'file' key."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not uploaded.name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return Response(
            {"detail": "Please upload an .xlsx or .xlsm file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Detect or accept explicit table_key
    table_key = request.query_params.get("table_key") or request.data.get("table_key")
    if not table_key:
        table_key = _detect_table_key(uploaded.name)
    if not table_key:
        return Response(
            {"detail": (
                f"Could not auto-detect table type from filename "
                f"'{uploaded.name}'. Pass ?table_key=item_master (or the "
                f"correct key) to specify manually."
            )},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if table_key not in PARSERS:
        return Response(
            {"detail": (
                f"No parser registered for table_key='{table_key}'. "
                f"Available: {', '.join(sorted(PARSERS.keys()))}"
            )},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stored_path, original_name = _store_file(uploaded)
    notes = (
        "" if request.data.get("notes") is None
        else str(request.data["notes"])
    )[:500]

    # Determine file_type and level
    is_erp = table_key.startswith("erp_")
    file_type = "erp" if is_erp else "master"
    level = "L1" if is_erp else "L0"

    # Parse
    parser_mod = PARSERS[table_key]
    try:
        parsed_rows = parser_mod.parse(stored_path)
    except Exception as exc:
        log.exception("PPC parse failed for %s (table_key=%s)", stored_path, table_key)
        # Create a batch record with the error
        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type=file_type,
            level=level,
            table_key=table_key,
            row_count=0,
            is_current=False,
            parse_error=str(exc),
            notes=notes,
        )
        notify(
            f"PPC upload PARSE FAILED — {original_name}",
            f"{request.user.get_username()} uploaded '{original_name}' "
            f"for table '{table_key}', but parsing failed: {exc}",
        )
        return Response(
            PPCUploadBatchSerializer(batch).data,
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Store in a transaction: demote old batches, create new one with rows
    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key=table_key, is_current=True,
        ).update(is_current=False)

        batch = PPCUploadBatch.objects.create(
            uploader=request.user,
            source_file=stored_path,
            original_filename=original_name,
            file_type=file_type,
            level=level,
            table_key=table_key,
            row_count=len(parsed_rows),
            is_current=True,
            notes=notes,
        )

        row_objs = [
            PPCDataRow(
                batch=batch,
                sr_no=idx + 1,
                table_key=table_key,
                data=row,
            )
            for idx, row in enumerate(parsed_rows)
        ]
        PPCDataRow.objects.bulk_create(row_objs, batch_size=500)

    notify(
        f"PPC upload OK — {original_name}",
        f"{request.user.get_username()} uploaded '{original_name}' "
        f"for table '{table_key}': {len(parsed_rows)} rows parsed and stored.",
    )

    # Fire-and-forget sheet sync — every upload goes to a Google Sheet
    if is_erp:
        try:
            from .sheet_sync import sync_erp_to_sheet
            sync_result = sync_erp_to_sheet(batch)
            log.info("ERP sheet sync for %s: %s", table_key, sync_result)
        except Exception:
            log.exception("ERP sheet sync failed for %s (non-blocking)", table_key)
    else:
        try:
            from .sheet_sync import sync_upload_to_sheet
            sync_result = sync_upload_to_sheet(batch)
            log.info("Data sheet sync for %s: %s", table_key, sync_result)
        except Exception:
            log.exception("Data sheet sync failed for %s (non-blocking)", table_key)

    payload = PPCUploadBatchSerializer(batch).data
    payload["sample_row"] = parsed_rows[0] if parsed_rows else None
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def list_uploads(request):
    """List recent upload batches, optionally filtered by table_key."""
    qs = PPCUploadBatch.objects.all()
    table_key = request.query_params.get("table_key")
    if table_key:
        qs = qs.filter(table_key=table_key)
    qs = qs[:50]
    return Response({
        "uploads": PPCUploadBatchSerializer(qs, many=True).data,
        "available_parsers": sorted(PARSERS.keys()),
    })


@api_view(["GET"])
def table_data(request, table_key):
    """Retrieve current rows for a table.

    Query params:
      ?limit=200    — max rows to return (default 200, max 5000)
      ?search=xyz   — search across all data values (simple contains)
    """
    batch = (
        PPCUploadBatch.objects
        .filter(table_key=table_key, is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if batch is None:
        return Response(
            {"detail": f"No data loaded for table '{table_key}' yet."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        limit = max(1, min(5000, int(request.GET.get("limit", 200))))
    except (TypeError, ValueError):
        limit = 200

    rows_qs = batch.rows.all()
    total = rows_qs.count()

    # Simple search: filter rows where any data value contains the term
    search = request.GET.get("search", "").strip()
    if search:
        # JSONField search — works in SQLite and PostgreSQL
        rows_qs = rows_qs.filter(data__icontains=search)

    rows = list(rows_qs[:limit].values_list("sr_no", "data"))

    return Response({
        "table_key": table_key,
        "batch_id": batch.id,
        "uploaded_at": batch.uploaded_at.isoformat(),
        "uploader": str(batch.uploader) if batch.uploader else None,
        "row_count": total,
        "rows": [{"sr_no": sr, "data": d} for sr, d in rows],
        "truncated": total > limit,
    })


def _rekey_erp_row(raw_row, field_map):
    """Re-key an ERP row from raw header strings to stable field keys.

    If the row already uses stable keys (matching field_map keys), pass
    it through unchanged. This handles both cases:
    - n8n sends raw ERP headers: {"Item Code": "JC-001", ...}
    - n8n sends pre-mapped keys: {"item_code": "JC-001", ...}
    """
    if not field_map:
        return raw_row

    # Build reverse map: header -> stable key
    header_to_key = {v.strip(): k for k, v in field_map.items()}
    stable_keys = set(field_map.keys())

    rekeyed = {}
    for raw_key, value in raw_row.items():
        stripped = raw_key.strip()
        if stripped in stable_keys:
            # Already a stable key
            rekeyed[stripped] = value
        elif stripped in header_to_key:
            # Raw header → convert to stable key
            rekeyed[header_to_key[stripped]] = value
        else:
            # Unknown column — keep as-is (don't lose data)
            rekeyed[stripped] = value
    return rekeyed


@api_view(["POST"])
@parser_classes([JSONParser])
def erp_landing(request):
    """Receive ERP report data from n8n.

    Expected JSON payload:
    {
        "report_key": "erp_fg_stock",
        "rows": [{"Item Code": "JC-001", ...}, ...],
        "meta": {"pulled_at": "2026-08-26T05:00:00", "report_name": "FG Stock"}
    }

    The endpoint re-keys rows from raw ERP headers to stable field keys
    using the matching ERP field map (if one exists). Unknown report_keys
    are accepted but stored without re-keying.
    """
    report_key = request.data.get("report_key")
    rows = request.data.get("rows", [])

    if not report_key:
        return Response(
            {"detail": "Missing 'report_key' in payload."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(rows, list):
        return Response(
            {"detail": "'rows' must be a list of objects."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    meta = request.data.get("meta", {})

    # Re-key rows if a field map exists for this report
    field_map = get_erp_field_map(report_key)
    rekeyed_rows = [_rekey_erp_row(r, field_map) for r in rows]

    with transaction.atomic():
        PPCUploadBatch.objects.filter(
            table_key=report_key, is_current=True,
        ).update(is_current=False)

        batch = PPCUploadBatch.objects.create(
            uploader=None,  # system pull
            source_file="",
            original_filename=meta.get("report_name", report_key),
            file_type="erp",
            level="L1",
            table_key=report_key,
            row_count=len(rekeyed_rows),
            is_current=True,
            notes=f"ERP pull at {meta.get('pulled_at', 'unknown')}",
        )

        row_objs = [
            PPCDataRow(
                batch=batch, sr_no=idx + 1,
                table_key=report_key, data=row,
            )
            for idx, row in enumerate(rekeyed_rows)
        ]
        PPCDataRow.objects.bulk_create(row_objs, batch_size=500)

    log.info("ERP landing: %s — %d rows stored (batch #%d)", report_key, len(rekeyed_rows), batch.id)

    return Response({
        "report_key": report_key,
        "batch_id": batch.id,
        "row_count": len(rekeyed_rows),
        "rekeyed": field_map is not None,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def feed_status(request):
    """Status board for all ERP feeds + master uploads.

    Returns the latest batch for every known table_key — when it was
    last pulled, how many rows, and whether it errored.
    """
    from django.db.models import Max

    # Get the latest current batch per table_key
    latest_batches = (
        PPCUploadBatch.objects
        .filter(is_current=True)
        .values("table_key")
        .annotate(last_upload=Max("uploaded_at"))
    )
    # Fetch actual batch objects
    batch_map = {}
    for entry in latest_batches:
        batch = (
            PPCUploadBatch.objects
            .filter(table_key=entry["table_key"], is_current=True)
            .order_by("-uploaded_at")
            .first()
        )
        if batch:
            batch_map[entry["table_key"]] = {
                "batch_id": batch.id,
                "uploaded_at": batch.uploaded_at.isoformat(),
                "row_count": batch.row_count,
                "original_filename": batch.original_filename,
                "file_type": batch.file_type,
                "level": batch.level,
                "parse_error": batch.parse_error,
                "uploader": str(batch.uploader) if batch.uploader else None,
            }

    # Build ERP feed status
    erp_feeds = []
    for key, info in sorted(ERP_REGISTRY.items(), key=lambda x: x[1]["report_number"]):
        feed = {
            "report_key": key,
            "report_number": info["report_number"],
            "frequency": info["frequency"],
            "field_count": len(info["field_map"]),
        }
        if key in batch_map:
            feed.update(batch_map[key])
            feed["status"] = "error" if batch_map[key]["parse_error"] else "ok"
        else:
            feed["status"] = "never_pulled"
        erp_feeds.append(feed)

    # Build master upload status
    master_status = []
    from .field_maps import REGISTRY as MASTER_REGISTRY
    for key in sorted(MASTER_REGISTRY.keys()):
        entry = {"table_key": key, "field_count": len(MASTER_REGISTRY[key]["field_map"])}
        if key in batch_map:
            entry.update(batch_map[key])
            entry["status"] = "error" if batch_map[key]["parse_error"] else "ok"
        else:
            entry["status"] = "empty"
        master_status.append(entry)

    return Response({
        "erp_feeds": erp_feeds,
        "master_tables": master_status,
        "summary": {
            "erp_total": len(erp_feeds),
            "erp_active": sum(1 for f in erp_feeds if f["status"] == "ok"),
            "master_total": len(master_status),
            "master_loaded": sum(1 for m in master_status if m["status"] == "ok"),
        },
    })
