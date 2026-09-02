from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from portal.notify import notify

from .models import LoginEvent


def _client_ip(request):
    # Behind a reverse proxy, REMOTE_ADDR is the proxy's own address — the
    # standard X-Forwarded-For header (set by nginx/etc.) carries the real
    # client IP as the first entry in that case.
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
    LoginEvent.objects.create(
        user=user,
        event_type=LoginEvent.EventType.LOGIN,
        ip_address=_client_ip(request),
    )
    notify(
        f"Login — {user.get_username()}",
        f"{user.get_username()} ({user.get_full_name() or 'no full name set'}) "
        f"logged in from {_client_ip(request)}.",
    )


@receiver(user_logged_out)
def record_logout(sender, request, user, **kwargs):
    # Django fires this even when there was no authenticated user in the
    # session (e.g. hitting /logout/ while already logged out) — user is
    # None in that case, and there's nothing to log.
    if user is None:
        return
    LoginEvent.objects.create(
        user=user,
        event_type=LoginEvent.EventType.LOGOUT,
        ip_address=_client_ip(request),
    )
