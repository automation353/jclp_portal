"""Shared helper functions for PPC field maps and computations.

Same helpers as purchase_dashboards.field_map (num, num0, txt) plus
PPC-specific utilities.
"""


def num(v):
    """Coerce a cell value to float; return None on missing/unparseable.
    Same as purchase_dashboards.field_map.num — never silently zero.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except (ValueError, TypeError):
        return None


def num0(v):
    """Coerce like num() but return 0.0 for missing — only use where
    blank genuinely means zero."""
    n = num(v)
    return 0.0 if n is None else n


def txt(v):
    """Trimmed string of a cell value, empty string on None."""
    if v is None:
        return ""
    return str(v).strip()


def rupees_in(n):
    """Format a rupee amount in Indian lakh/crore convention."""
    if n is None:
        return "—"
    if abs(n) >= 1_00_00_000:
        return f"₹{n / 1_00_00_000:,.2f} Cr"
    if abs(n) >= 1_00_000:
        return f"₹{n / 1_00_000:,.2f} L"
    return f"₹{n:,.0f}"
