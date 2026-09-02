from .data import get_accessible_modules


def sidebar_modules(request):
    """Makes the accessible department entries available in every template
    (sidebar) — all 7 for a Super Admin, only the assigned one for an Admin."""
    return {"modules": get_accessible_modules(getattr(request, "user", None))}
