from pathlib import Path

from django.conf import settings
from django.utils import timezone

from . import services
from .models import RefreshRun


# Changes whenever a portal CSS/JS file changes, so browsers never keep a stale copy
_STATIC = Path(__file__).parent / "static" / "nongrn"
ASSET_VERSION = str(int(max((p.stat().st_mtime for p in _STATIC.rglob("*") if p.is_file()), default=0)))


def portal(request):
    if not request.resolver_match or request.resolver_match.app_name != "nongrn":
        return {"asset_version": ASSET_VERSION}
    return {
        "sheets": services.sheet_definitions(),
        "fy_label": services.fiscal_year().label,
        "asset_version": ASSET_VERSION,
        "last_refresh": RefreshRun.objects.filter(status=RefreshRun.OK).first(),
        "refresh_running": services.refresh_running(),
        "require_login": settings.NONGRN_REQUIRE_LOGIN,
        **source_status(),
    }


def source_status():
    """Sidebar 'Today's data' card: one segment per source folder."""
    out = []
    listing = services.source_listing()
    # top-bar pill: the daily files (Non GRN, MDA) – green only when both were uploaded today
    today = timezone.localdate()
    daily = [{"label": s["label"], "at": s["latest"]["modified"] if s["latest"] else None,
              "today": bool(s["latest"] and s["latest"]["modified"].date() == today)}
             for s in listing if s["daily"]]
    for s in listing:
        if s["age_days"] == 0:
            state, note = "ok", "updated today"
        elif s["latest"] is None:
            state, note = "bad", "no file"
        else:
            state = "warn" if s["daily"] else "idle"
            note = f"updated {s['age_days']} day{'s' if s['age_days'] != 1 else ''} ago"
        out.append({"label": s["label"], "state": state, "note": note, "daily": s["daily"]})
    return {"daily_uploads": daily, "daily_all_today": bool(daily) and all(d["today"] for d in daily),
            "daily_done": sum(d["today"] for d in daily),
            "today_key": today.strftime("%Y%m%d"),
            "daily_last": max((d["at"] for d in daily if d["at"]), default=None),
            "src_status": out, "src_today": sum(s["state"] == "ok" for s in out),
            "daily_pending": any(s["daily"] and s["state"] != "ok" for s in out)}
