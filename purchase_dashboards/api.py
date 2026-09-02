"""REST endpoints for the Purchase Control Dashboards.

  GET /api/purchase-dashboards/          → current snapshot summary + every
                                            dashboard's tiles (small payload)
  GET /api/purchase-dashboards/<key>/    → one dashboard's tiles + full
                                            drill-through rows

Session-authenticated. Serves whatever the last successful snapshot has.
If no snapshot exists yet, returns a friendly empty payload.
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from portal.plain_language import annotate_columns, annotate_tiles, verdict_map

from .computations import DASHBOARDS
from .models import PurchaseDashResult, PurchaseDashSnapshot


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


def _dashboard_meta():
    """A stable list the frontend uses to render the dashboard cards even
    before any snapshot exists. Extended in Phases 2 + 3."""
    return [
        {
            "key": mod.DASHBOARD_KEY, "title": mod.TITLE,
            "group": _group_for(mod.DASHBOARD_KEY),
        }
        for mod in DASHBOARDS.values()
    ]


def _group_for(key):
    if key in ("d1", "d2", "d3"): return "A"
    if key in ("d4", "d5", "d6", "d7"): return "B"
    if key in ("d8", "d9"): return "C"
    return "?"


@api_view(["GET"])
def summary(request):
    snap = _current_snapshot()
    payload = {
        "snapshot": _snapshot_summary(snap),
        "dashboards": _dashboard_meta(),
        "results": [],
    }
    if snap:
        for res in snap.results.all():
            # Tiles only — each carries row_count + drillable so the card grid
            # can show the "N rows" affordance without shipping any rows.
            # Rows come from the per-tile endpoint on click.
            payload["results"].append({
                "dashboard_key": res.dashboard_key,
                # Technical label/sub are kept as-is; the plain-English wording
                # is added alongside so the UI can offer either view.
                "tiles": annotate_tiles(res.dashboard_key, res.tiles),
                "computed_at": res.computed_at.isoformat(),
            })
    return Response(payload)


@api_view(["GET"])
def tile_rows(request, dashboard_key, tile_key):
    """Drill-through rows for one tile on one dashboard.

    Returns the tile's own column spec alongside its rows, capped by
    ``?limit=`` (default 2000) with the true total reported so the UI can say
    "showing N of M" rather than silently truncating.
    """
    snap = _current_snapshot()
    if snap is None:
        return Response(
            {"detail": "No snapshot yet."}, status=status.HTTP_404_NOT_FOUND,
        )
    try:
        res = snap.results.get(dashboard_key=dashboard_key)
    except PurchaseDashResult.DoesNotExist:
        return Response(
            {"detail": f"Dashboard '{dashboard_key}' has no result for this snapshot."},
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
    plain_tile = annotate_tiles(dashboard_key, {tile_key: tile}).get(tile_key, {})
    payload = {
        "dashboard_key": dashboard_key,
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


@api_view(["GET"])
def dashboard_detail(request, dashboard_key):
    snap = _current_snapshot()
    if snap is None:
        return Response(
            {"detail": "No snapshot yet. Ask an admin to run the fetch command."},
            status=status.HTTP_404_NOT_FOUND,
        )
    try:
        res = snap.results.get(dashboard_key=dashboard_key)
    except PurchaseDashResult.DoesNotExist:
        return Response(
            {"detail": f"Dashboard '{dashboard_key}' has no result for this snapshot."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response({
        "snapshot": _snapshot_summary(snap),
        "dashboard_key": res.dashboard_key,
        "tiles": annotate_tiles(res.dashboard_key, res.tiles),
        "detail_rows": res.detail_rows,
        "computed_at": res.computed_at.isoformat(),
    })
