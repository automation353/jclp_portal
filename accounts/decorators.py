from django.contrib.auth.decorators import login_required, user_passes_test


def _is_super_admin(user):
    return user.is_authenticated and user.role == user.Role.SUPER_ADMIN


def super_admin_required(view_func):
    """Only Super Admin accounts may pass; everyone else is bounced to the dashboard."""
    decorated = user_passes_test(_is_super_admin, login_url="dashboard:home")(view_func)
    return login_required(decorated)
