"""The requirement-age register — the clock Control 2 runs on.

Kept out of the control module on purpose. Computation modules stay pure
functions of their input; stamping the register is a side effect, so it
happens once per run here and the resulting ages are injected into the rows
before any module sees them.

The only guarantee that matters: ``first_seen`` is written once and never
moved. Spec §Control 2 — "Match on item code, keep the earliest date ever
seen, and never delete a stamp." A requirement that vanishes for a day
because of a lookup failure and comes back must not read as brand new.
"""

from django.utils import timezone

from .models import RequirementAge

PLACEHOLDERS = {"item code required", "tbd", "n/a", "na"}


def item_key(data):
    """Item Code where usable, else Item Name — the same precedence the PO
    join uses, so both agree on what "this item" means."""
    for field in ("tally_code", "rm_code"):
        v = str(data.get(field) or "").strip()
        if v and v != "0" and v.lower() not in PLACEHOLDERS:
            return v
    return ""


def _num(v):
    try:
        return float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def stamp_and_enrich(rows):
    """Stamp every current requirement, then write the age back onto each row.

    Returns (rows, meta). Rows are enriched in place with:
        requirement_first_seen  ISO date the item was first seen requiring
        requirement_age_days    whole days since then
    Rows without a requirement, or without a usable key, get blanks — never
    a zero, which would read as "brand new".
    """
    now = timezone.now()
    existing = {r.item_key: r for r in RequirementAge.objects.all()}
    created = 0

    for row in rows:
        data = row["data"]
        qty = _num(data.get("to_be_ordered_qty")) or 0
        key = item_key(data)
        if qty <= 0 or not key:
            data["requirement_first_seen"] = ""
            data["requirement_age_days"] = ""
            continue

        rec = existing.get(key)
        if rec is None:
            rec, was_new = RequirementAge.objects.get_or_create(
                item_key=key, defaults={"first_qty": qty},
            )
            existing[key] = rec
            if was_new:
                created += 1
        else:
            # last_seen/times_seen only — first_seen is never touched.
            RequirementAge.objects.filter(pk=rec.pk).update(
                times_seen=rec.times_seen + 1, last_seen=now,
            )

        data["requirement_first_seen"] = rec.first_seen.date().isoformat()
        data["requirement_age_days"] = str((now.date() - rec.first_seen.date()).days)

    oldest = RequirementAge.objects.order_by("first_seen").first()
    return rows, {
        "register_size": RequirementAge.objects.count(),
        "created_this_run": created,
        "register_started": oldest.first_seen.date().isoformat() if oldest else "",
        "register_age_days": (now.date() - oldest.first_seen.date()).days if oldest else 0,
    }
