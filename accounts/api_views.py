"""Super Admin panel API views.

Every view here is restricted to super_admin users via the
IsSuperAdmin permission class.
"""

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from portal.data import DEPARTMENTS

from .models import LoginEvent, UserModuleAccess
from .serializers import (
    LoginEventSerializer,
    ModuleSerializer,
    UserDetailSerializer,
    UserListSerializer,
)

User = get_user_model()


class IsSuperAdmin(permissions.BasePermission):
    """Only super_admin role can access these endpoints."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", "") == "super_admin"
        )


# ── Stats ──────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def admin_stats(request):
    """Dashboard headline stats."""
    today = timezone.localdate()
    total = User.objects.count()
    active = User.objects.filter(is_active=True).count()
    logins_today = LoginEvent.objects.filter(
        event_type="login", timestamp__date=today,
    ).count()
    modules_live = sum(1 for d in DEPARTMENTS if d["is_open"])

    return Response({
        "total_users": total,
        "active_users": active,
        "logins_today": logins_today,
        "modules_live": modules_live,
        "modules_total": len(DEPARTMENTS),
    })


# ── Modules list ───────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def module_list(request):
    """All available portal modules."""
    return Response(ModuleSerializer(DEPARTMENTS, many=True).data)


# ── User CRUD ──────────────────────────────────────────────────────────


class UserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsSuperAdmin]
    queryset = User.objects.all().order_by("-is_active", "-role", "username")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserDetailSerializer
        return UserListSerializer


class UserDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsSuperAdmin]
    queryset = User.objects.all()
    serializer_class = UserDetailSerializer


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def user_toggle_active(request, pk):
    """Activate / deactivate a user. Cannot deactivate yourself."""
    try:
        account = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({"detail": "User not found."}, status=404)

    if account == request.user:
        return Response(
            {"detail": "You cannot deactivate your own account."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    account.is_active = not account.is_active
    account.save()
    state = "activated" if account.is_active else "deactivated"
    return Response({"detail": f"{account.username} {state}.", "is_active": account.is_active})


# ── Activity log ───────────────────────────────────────────────────────


class ActivityListView(generics.ListAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = LoginEventSerializer

    def get_queryset(self):
        qs = LoginEvent.objects.select_related("user").all()
        username = self.request.query_params.get("user")
        if username:
            qs = qs.filter(user__username=username)
        return qs[:200]
