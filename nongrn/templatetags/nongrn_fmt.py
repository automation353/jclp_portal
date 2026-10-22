"""Number formats used on the sheets (Indian digit grouping, ₹ Lakhs, %)."""
import datetime as dt
import math
from decimal import ROUND_HALF_UP, Decimal

from django import template

register = template.Library()


def _is_blank(v):
    return v is None or v == "" or (isinstance(v, float) and math.isnan(v))


def excel_round(value, decimals=0) -> Decimal:
    """ROUND() as Excel does it: half away from zero, on the 15-digit decimal value.

    Python's own rounding goes half-to-even on the binary value (90,240.50 -> 90,240),
    Excel shows 90,241.
    """
    d = Decimal(repr(float(value)))
    return d.quantize(Decimal(1).scaleb(-int(decimals)), rounding=ROUND_HALF_UP)


def _fixed(value, decimals):
    d = excel_round(value, decimals)
    return f"{d:.{int(decimals)}f}" if d != 0 else f"{0:.{int(decimals)}f}"


def indian(value, decimals=0):
    if _is_blank(value):
        return ""
    v = float(value)
    s = _fixed(abs(v), decimals)
    neg = v < 0 and float(s) != 0
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    out = whole + ("." + frac if frac else "")
    return f"({out})" if neg else out


@register.filter
def inr(value):
    """Rupees, no decimals: 1,23,45,678"""
    return indian(value, 0)


@register.filter
def inr2(value):
    return indian(value, 2)


@register.filter
def lakh(value):
    return indian(value, 2)


@register.filter
def pct(value, decimals=1):
    if _is_blank(value):
        return ""
    return _fixed(float(value) * 100, decimals) + "%"


@register.filter
def num1(value):
    if _is_blank(value):
        return ""
    v = float(value)
    whole, _, frac = _fixed(abs(v), 1).partition(".")
    return ("-" if v < 0 and float(whole + "." + frac) != 0 else "") + f"{int(whole):,}.{frac}"


@register.filter
def dmy(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%d-%m-%Y")
    return value


@register.filter
def zero_dash(value):
    """Shows '-' for exact zero (Excel accounting format)."""
    if _is_blank(value):
        return ""
    return "-" if float(value) == 0 else indian(value, 0)


@register.filter
def get(d, key):
    return d.get(key) if hasattr(d, "get") else None
