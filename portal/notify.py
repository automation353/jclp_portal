"""Shared "send an activity/warning email" helper.

The single place every app's upload/fetch/login/error touch-point calls
into, so the alerting behaviour (recipient, from-address, styling, failure
handling) lives in one spot instead of being copy-pasted per app. Every
call site elsewhere just imports `notify(subject, body)` and calls it —
that signature hasn't changed, so nothing about those call sites needed
touching to pick up the HTML template below.

Never raises — a notification failure must never break the activity that
triggered it. Until JCLP_SMTP_HOST is set in the shared /root/.env, this
lands in the console/log backend instead of a real inbox; the call is safe
to leave in place either way.
"""

import html
import os

from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

ALERT_EMAIL = os.environ.get("JCLP_ALERT_EMAIL", "automation@jollyclamps.com")
PORTAL_URL = os.environ.get("JCLP_PORTAL_BASE_URL", "")

# Brand colours lifted straight from frontend/src/index.css :root — the
# email should look like it came from the same product, not a cron job.
STEEL = "#1f3a5f"
STEEL2 = "#2c5a8c"
ACCENT = "#0f7bd4"

# Subject-line keyword -> badge. Checked in order; first match wins. This
# is a classification of the SUBJECT text every call site already writes,
# not a new field they need to pass — existing calls "just work."
_KINDS = [
    (("rejected", "failed", "unresolvable", "no file", "wrong"), {
        "label": "ACTION NEEDED", "fg": "#ffffff", "bg": "#c62828", "soft": "#fdecea",
    }),
    (("login",), {
        "label": "LOGIN", "fg": "#ffffff", "bg": STEEL, "soft": "#eaf1f8",
    }),
    (("recomputed", "upload ok", "fetch ok"), {
        "label": "SUCCESS", "fg": "#ffffff", "bg": "#2e7d32", "soft": "#eaf5ea",
    }),
]
_DEFAULT_KIND = {"label": "NOTICE", "fg": "#ffffff", "bg": "#546e7a", "soft": "#eceff1"}


def _classify(subject):
    s = subject.lower()
    for keywords, kind in _KINDS:
        if any(k in s for k in keywords):
            return kind
    return _DEFAULT_KIND


def _paragraphs_html(body):
    """Plain text -> safe HTML paragraphs. Splits on blank lines the way
    every call site already writes its message; escapes everything since
    body text often embeds a filename or username we didn't choose."""
    blocks = [b.strip() for b in body.split("\n\n") if b.strip()]
    out = []
    for block in blocks:
        escaped = html.escape(block).replace("\n", "<br>")
        out.append(
            f'<p style="margin:0 0 14px 0;color:#33414d;font-size:14px;'
            f'line-height:1.6;">{escaped}</p>'
        )
    return "".join(out) or '<p style="margin:0;color:#33414d;font-size:14px;">(no detail provided)</p>'


def _html_email(subject, body):
    kind = _classify(subject)
    when = timezone.now().strftime("%d %b %Y, %H:%M")
    footer_link = (
        f'<a href="{html.escape(PORTAL_URL)}" style="color:{ACCENT};text-decoration:none;">'
        f'Open the JCPL Portal →</a>' if PORTAL_URL else ""
    )
    return f"""\
<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f0f3f7;font-family:Segoe UI,Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0f3f7;padding:28px 0;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(20,30,45,0.12);">
        <tr>
          <td bgcolor="{STEEL}" style="background-color:{STEEL};background-image:linear-gradient(90deg,{STEEL},{STEEL2});padding:18px 24px;">
            <span style="color:#ffffff;font-size:15px;font-weight:700;letter-spacing:.02em;">
              JCPL Enterprise Portal
            </span>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 24px 8px 24px;">
            <span style="display:inline-block;background:{kind['bg']};color:{kind['fg']};
                         font-size:10.5px;font-weight:800;letter-spacing:.04em;
                         padding:3px 9px;border-radius:10px;">{kind['label']}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:6px 24px 4px 24px;">
            <h1 style="margin:0;color:#12202f;font-size:18px;font-weight:700;line-height:1.35;">
              {html.escape(subject)}
            </h1>
          </td>
        </tr>
        <tr>
          <td style="padding:14px 24px 6px 24px;background:{kind['soft']};margin:0 24px;">
          </td>
        </tr>
        <tr>
          <td style="padding:18px 24px 6px 24px;">
            {_paragraphs_html(body)}
          </td>
        </tr>
        <tr>
          <td style="padding:8px 24px 22px 24px;">
            {footer_link}
          </td>
        </tr>
        <tr>
          <td style="padding:14px 24px;background:#f7f9fb;border-top:1px solid #e5e9ee;">
            <span style="color:#8a97a6;font-size:11px;">
              Automated message from the JCPL Enterprise Portal · {html.escape(when)} ·
              sent to {html.escape(ALERT_EMAIL)} · this address doesn't accept replies
            </span>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def notify(subject, body):
    try:
        full_subject = f"[JCPL Portal] {subject}"
        msg = EmailMultiAlternatives(
            subject=full_subject,
            body=body,  # plain-text fallback for clients that don't render HTML
            from_email=None,  # falls back to DEFAULT_FROM_EMAIL
            to=[ALERT_EMAIL],
        )
        msg.attach_alternative(_html_email(subject, body), "text/html")
        msg.send(fail_silently=True)
    except Exception:
        # fail_silently=True already covers send()'s own exceptions; this
        # belt-and-braces catch is for anything unexpected around it (e.g.
        # settings misconfiguration) so alerting can never break the
        # activity that triggered it.
        pass
