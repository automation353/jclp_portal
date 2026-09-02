"""Email + in-app notification fan-out for the MTO/MTS module.

Two kinds of emails go out:

* **Publication** — Stage E of the brief. On successful upload, both Ops and
  OEM Sales get one email each, containing the month being planned, a link
  to the portal, a summary of what's inside, and the review-by date.

* **Change** — Stages F/G. Every time someone saves an edit, the *other*
  side is emailed (and gets an in-app notification for the bell + toast).

Both kinds are recorded in ``MtoMtsEmailLog`` — the audit trail Section 5
of the brief calls for. Nothing is silently dropped.

Emails route through Django's ``send_messages()``. If the SMTP env is
blank in ``/root/.env``, the console backend prints the body into
``jcpl/logs/django.log`` — the log still records the attempt.
"""

import datetime as dt
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.utils import timezone

from .models import MtoMtsChange, MtoMtsEmailLog, MtoMtsNotification


User = get_user_model()

# Departments whose users need to be told about every change / publication.
INVOLVED_DEPARTMENTS = ("Operations", "OEM Sales")

FIELD_HUMAN = {
    "current_month_status": "Current month status",
    "sales_reason": "Sales reason",
    "ops_reason": "Operations reason",
    "sales_status": "Sales status",
    "ops_status": "Operations status",
}


def _portal_base_url() -> str:
    """Where the SPA lives, for links inside emails. Overrideable via env."""
    return os.environ.get(
        "JCLP_PORTAL_BASE_URL", "http://200.141.14.164:4000"
    ).rstrip("/")


def _department_users():
    """Every active user in Operations or OEM Sales — the module's audience."""
    return User.objects.filter(
        department__in=INVOLVED_DEPARTMENTS, is_active=True
    )


def _send_and_log(*, subject, body, to_addresses, kind, upload=None, change=None):
    """Fire the email and always record the attempt in MtoMtsEmailLog."""
    delivered = True
    if to_addresses:
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "no-reply@jollyclamps.local"
            ),
            to=list(to_addresses),
        )
        try:
            email.send(fail_silently=False)
        except Exception:
            delivered = False

    MtoMtsEmailLog.objects.create(
        upload=upload,
        change=change,
        kind=kind,
        subject=subject[:255],
        recipients=", ".join(to_addresses) if to_addresses else "",
        body_preview="\n".join(body.splitlines()[:8]),
        delivered=delivered,
    )


# ---------------------------------------------------------------- publication


def _summary_from_upload(upload):
    """Count items by their most-recent-completed-month value. Used in the
    publication email's one-line summary (see Stage E of the brief).

    Computed in Python off ``upload.items``' prefetched cells rather than
    saved anywhere — the classifier proper (Stage B) is a separate stage.
    """
    mts = mto = blank = 0
    for item in upload.items.prefetch_related("cells").all():
        last_value = ""
        for cell in item.cells.all():          # ordering=['month_index']
            if cell.value:
                last_value = cell.value
        if last_value == "MTS":
            mts += 1
        elif last_value == "MTO":
            mto += 1
        else:
            blank += 1
    return {"total": mts + mto + blank, "mts": mts, "mto": mto, "blank": blank}


def send_publication_email(upload, review_by_days: int = 7):
    """Stage E — email Sales + Ops that a new working file is ready.

    Called at the end of ``process_mto_mts_upload`` once the upload is
    ACTIVE. Also runnable by hand via ``manage.py send_mto_mts_publication_email``.
    Idempotent-friendly: each call writes a fresh log row, so re-sending
    is deliberate and traceable.
    """
    to_addresses = [
        u.email for u in _department_users().exclude(email="")
    ]

    summary = _summary_from_upload(upload)
    month = upload.month_label or "the current month"
    review_by = (
        timezone.now() + dt.timedelta(days=review_by_days)
    ).strftime("%A, %d %B %Y")
    portal = _portal_base_url()

    subject = f"[JCPL MTO/MTS] Working file for {month} is ready for review"
    body = "\n".join([
        f"The MTO / MTS working file for {month} has been published on the",
        "portal and is ready for your review.",
        "",
        f"Uploaded by      : {upload.uploader.username if upload.uploader else '—'}",
        f"Uploaded at (UTC): {upload.uploaded_at:%Y-%m-%d %H:%M}",
        f"Total items      : {summary['total']}",
        f"Review by        : {review_by}",
        "",
        "Recent-month breakdown (based on the last completed month's value",
        "for each item in the source sheet):",
        f"  • MTS   : {summary['mts']}",
        f"  • MTO   : {summary['mto']}",
        f"  • Blank : {summary['blank']}",
        "",
        f"Working file : {portal}/mto-mts",
        f"Change log   : {portal}/mto-mts/changes",
        "",
        "Both Operations and OEM Sales can review this file at the same time.",
        "Every edit is logged and notifies the other department automatically.",
    ])

    _send_and_log(
        subject=subject,
        body=body,
        to_addresses=to_addresses,
        kind=MtoMtsEmailLog.Kind.PUBLICATION,
        upload=upload,
    )


# ---------------------------------------------------------------- changes


def fan_out(change: MtoMtsChange, portal_url: str = "") -> None:
    """Create in-app notifications for everyone in either department (except
    the user who made the change) and send them a change-notification email.
    Idempotent per-recipient — one row per (change, recipient) in the
    notifications table.
    """
    recipients = _department_users().exclude(pk=change.changed_by_id)

    notifications = [
        MtoMtsNotification(change=change, recipient=recipient)
        for recipient in recipients
    ]
    if notifications:
        MtoMtsNotification.objects.bulk_create(notifications, ignore_conflicts=True)

    _send_change_email(change, recipients, portal_url)


def _send_change_email(change, recipients, portal_url):
    to_addresses = [r.email for r in recipients if r.email]
    if not to_addresses and not portal_url:
        return

    field_label = FIELD_HUMAN.get(change.field, change.field)
    old = change.old_value or "(empty)"
    new = change.new_value or "(empty)"
    portal = portal_url or _portal_base_url()

    subject = (
        f"[JCPL MTO/MTS] {change.item.item_code} — "
        f"{field_label} changed by {change.changed_by.username}"
    )
    body = "\n".join([
        f"Item        : {change.item.item_code} ({change.item.item_group})",
        f"Field       : {field_label}",
        f"Changed from: {old}",
        f"Changed to  : {new}",
        f"By          : {change.changed_by.username} ({change.department or '—'})",
        f"When        : {change.changed_at:%Y-%m-%d %H:%M UTC}",
        "",
        f"Open the portal: {portal}/mto-mts",
        f"Change log     : {portal}/mto-mts/changes",
    ])

    _send_and_log(
        subject=subject,
        body=body,
        to_addresses=to_addresses,
        kind=MtoMtsEmailLog.Kind.CHANGE,
        upload=change.item.upload,
        change=change,
    )
