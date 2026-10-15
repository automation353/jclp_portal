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
    """RM Quantity output — the COMPLETE total (direct RM + CP→RM roll-up),
    served from Django's local compute (not the sheet's direct-only pivot)."""
    from .rm_sourcing import _cached_tab, read_rm_quantity
    rows = _cached_tab("RM QTY")
    if rows is None:
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
    """CP + packing requirement (Quantity Sheet) — from Django's local compute."""
    import os
    from .rm_sourcing import _cached_tab, read_quantity_sheet
    rows = _cached_tab("Quantity Sheet")
    if rows is None:
        rows = read_quantity_sheet()
    sid = os.environ.get("JCLP_RMCP_SHEET_ID", "").strip()
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else ""
    return Response({"row_count": len(rows), "rows": rows, "sheet_url": sheet_url})


@api_view(["GET"])
def data_quality(request):
    """Rule 19 — item code ↔ description check over the cached BOM (read-only)."""
    from .rm_sourcing import check_data_quality
    return Response(check_data_quality())


# The RMCP Google Sheet tabs a per-rule dashboard may read (read-only).
_RMCP_TABS = {"BOM", "Plan", "CP Req", "RM Req", "RM QTY",
              "Quantity Sheet", "Against Demand RM"}


@api_view(["GET"])
def sheet_tab(request):
    """Serve one RMCP tab for a per-rule dashboard. Computed tabs come from
    Django's local compute (COMPLETE, with the roll-up); BOM falls back to the
    Google Sheet."""
    import os
    from .rm_sourcing import _read_tab, _cached_tab
    tab = (request.GET.get("tab") or "").strip()
    if tab not in _RMCP_TABS:
        return Response({"ok": False, "error": f"unknown tab: {tab}"})
    rows = _cached_tab(tab)
    if rows is None:
        rows = _read_tab(tab)
    sid = os.environ.get("JCLP_RMCP_SHEET_ID", "").strip()
    url = f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else ""
    return Response({"ok": True, "tab": tab, "row_count": len(rows),
                     "rows": rows, "sheet_url": url})


@api_view(["GET"])
def rm_usage(request):
    """Which FGs consume a given RM (?rm=<code>)."""
    from .rm_sourcing import read_rm_usage
    rm = request.GET.get("rm", "").strip()
    rows = read_rm_usage(rm)
    return Response({"rm": rm, "row_count": len(rows), "rows": rows})
