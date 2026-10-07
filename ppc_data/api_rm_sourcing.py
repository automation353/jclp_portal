"""RM Sourcing (RMCP) API — recompute the RM requirement and read it back.

Isolated from the R3SS/MTO-MTS endpoints.
"""

import logging

from rest_framework.decorators import api_view
from rest_framework.response import Response

log = logging.getLogger(__name__)


@api_view(["POST"])
def rm_recompute(request):
    """Re-explode the cached BOM against the current R3SS plan."""
    from .rm_sourcing import compute_rm
    try:
        result = compute_rm()
    except Exception as exc:
        log.exception("RM recompute failed")
        return Response({"ok": False, "error": str(exc)})
    return Response(result)


@api_view(["GET"])
def rm_quantity(request):
    """Return the RM Quantity output (how much RM is needed)."""
    from .rm_sourcing import read_rm_quantity
    rows = read_rm_quantity()
    return Response({"row_count": len(rows), "rows": rows})


@api_view(["GET"])
def rm_by_bom(request):
    """Product-centric view: each FG (BOM Code) → its RM needs (expandable)."""
    import os
    from .rm_sourcing import read_rm_by_bom
    rows = read_rm_by_bom()
    sid = os.environ.get("JCLP_RMCP_SHEET_ID", "").strip()
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else ""
    return Response({"row_count": len(rows), "rows": rows, "sheet_url": sheet_url})


@api_view(["GET"])
def cp_req(request):
    """CP + packing requirement (Quantity Sheet tab)."""
    import os
    from .rm_sourcing import read_quantity_sheet
    rows = read_quantity_sheet()
    sid = os.environ.get("JCLP_RMCP_SHEET_ID", "").strip()
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else ""
    return Response({"row_count": len(rows), "rows": rows, "sheet_url": sheet_url})


@api_view(["GET"])
def data_quality(request):
    """Rule 19 — item code ↔ description check over the cached BOM (read-only)."""
    from .rm_sourcing import check_data_quality
    return Response(check_data_quality())


@api_view(["GET"])
def rm_usage(request):
    """Which FGs consume a given RM (?rm=<code>)."""
    from .rm_sourcing import read_rm_usage
    rm = request.GET.get("rm", "").strip()
    rows = read_rm_usage(rm)
    return Response({"rm": rm, "row_count": len(rows), "rows": rows})
