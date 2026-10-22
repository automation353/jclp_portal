from django.conf import settings
from django.contrib.auth.views import redirect_to_login


class LoginRequiredMiddleware:
    """Every portal page needs a signed-in user (switch off with NONGRN_REQUIRE_LOGIN=0)."""

    OPEN_PREFIXES = ("/login/", "/admin/", "/static/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (settings.NONGRN_REQUIRE_LOGIN and not request.user.is_authenticated
                and not request.path.startswith(self.OPEN_PREFIXES)):
            return redirect_to_login(request.get_full_path())
        return self.get_response(request)
