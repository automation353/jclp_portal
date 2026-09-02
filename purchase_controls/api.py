"""REST endpoints for The Seven Purchase Controls.

  GET /api/purchase-controls/                       → summary: every
                                                        registered control's
                                                        tiles (small payload)
  GET /api/purchase-controls/<key>/tiles/<tile>/     → per-tile drill-through

Mirrors purchase_dashboards/api.py exactly, on its own models — see that
file's docstring for the shape rationale. Session-authenticated. Serves
whatever the current PurchaseDashSnapshot's control results hold; if none
exist yet, returns a friendly empty payload rather than a 500.
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from portal.plain_language import annotate_columns, annotate_tiles, verdict_map
from purchase_dashboards.models import PurchaseDashSnapshot

from .computations import CONTROLS
from .models import ControlResult


def _current_snapshot():
    return (
        PurchaseDashSnapshot.objects
        .filter(is_current=True)
        .order_by("-fetched_at")
        .first()
    )


def _snapshot_summary(snap):
    if snap is None:
        return None
    return {
        "id": snap.id,
        "fetched_at": snap.fetched_at.isoformat(),
        "row_count": snap.row_count,
        "sheet_id": snap.sheet_id,
        "gid": snap.gid,
        "fetch_error": snap.fetch_error,
    }


def _control_meta():
    return [
        {"key": mod.CONTROL_KEY, "title": mod.TITLE, "jcpl_wording": mod.JCPL_WORDING}
        for mod in CONTROLS.values()
    ]


@api_view(["GET"])
def summary(request):
    snap = _current_snapshot()
    payload = {
        "snapshot": _snapshot_summary(snap),
        "controls": _control_meta(),
        "results": [],
    }
    if snap:
        for res in ControlResult.objects.filter(snapshot=snap):
            payload["results"].append({
                "control_key": res.control_key,
                # Same contract as purchase_dashboards: technical wording kept,
                # plain-English wording added alongside.
                "tiles": annotate_tiles(res.control_key, res.tiles),
                "computed_at": res.computed_at.isoformat(),
            })
    return Response(payload)


@api_view(["GET"])
def tile_rows(request, control_key, tile_key):
    """Drill-through rows for one tile on one control. Same contract as
    purchase_dashboards' per-tile endpoint — capped by ?limit=, true total
    always reported so the UI can say "showing 200 of 1042" rather than
    silently truncating."""
    snap = _current_snapshot()
    if snap is None:
        return Response({"detail": "No snapshot yet."}, status=status.HTTP_404_NOT_FOUND)
    try:
        res = ControlResult.objects.get(snapshot=snap, control_key=control_key)
    except ControlResult.DoesNotExist:
        return Response(
            {"detail": f"Control '{control_key}' has no result for this snapshot."},
            status=status.HTTP_404_NOT_FOUND,
        )

    entry = (res.tile_rows or {}).get(tile_key)
    if entry is None:
        return Response(
            {"detail": f"Tile '{tile_key}' has no drill-through rows."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        limit = max(1, min(2000, int(request.GET.get("limit", 2000))))
    except (TypeError, ValueError):
        limit = 2000

    all_rows = entry.get("rows", [])
    tile = res.tiles.get(tile_key) or {}
    plain_tile = annotate_tiles(control_key, {tile_key: tile}).get(tile_key, {})
    payload = {
        "control_key": control_key,
        "tile_key": tile_key,
        "label": tile.get("label", tile_key),
        "plain_label": plain_tile.get("plain_label") or tile.get("label", tile_key),
        "columns": annotate_columns(entry.get("columns", [])),
        "verdict_plain": verdict_map(entry.get("columns", [])),
        "rows": all_rows[:limit],
        "row_count": len(all_rows),
        "truncated": len(all_rows) > limit,
        "snapshot": _snapshot_summary(snap),
    }
    if entry.get("subtotals"):
        payload["subtotals"] = entry["subtotals"]
    return Response(payload)
