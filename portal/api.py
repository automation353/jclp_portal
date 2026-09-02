"""JSON API consumed by the React front end.

Auth is plain Django sessions (not tokens): the SPA is served same-origin, so
the session cookie is the simplest correct choice — it stays HttpOnly and
there's no access token sitting in localStorage for a stray script to read.
The cost is that unsafe requests must carry the CSRF header, which is what
``csrf`` below exists to bootstrap.
"""

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .data import DEPARTMENTS, PURCHASE_PORTALS
from .models import RawMaterial
from .serializers import EBQRequestSerializer, RawMaterialSerializer, UserSerializer
from .services import EBQError, economic_batch_quantity


# ---------------------------------------------------------------- auth

@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    """Hit once on app load so the browser holds a csrftoken cookie before the
    SPA tries its first POST."""
    return Response({"detail": "CSRF cookie set."})


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""

    if not username or not password:
        return Response(
            {"detail": "Enter both your user ID and password."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        # Deliberately does not distinguish "no such user" from "wrong
        # password" from "account disabled" — that difference is only useful
        # to someone probing for valid usernames.
        return Response(
            {"detail": "That user ID and password don't match a JCPL account."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    auth_login(request, user)
    return Response(UserSerializer(user).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout(request):
    auth_logout(request)
    return Response({"detail": "Signed out."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


# ---------------------------------------------------------------- portal

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def departments(request):
    return Response(DEPARTMENTS)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def purchase_portals(request):
    return Response(PURCHASE_PORTALS)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def raw_materials(request):
    queryset = RawMaterial.objects.filter(is_active=True)
    return Response(RawMaterialSerializer(queryset, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ebq(request):
    form = EBQRequestSerializer(data=request.data)
    if not form.is_valid():
        return Response(
            {"detail": "Enter positive values."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        result = economic_batch_quantity(**form.validated_data)
    except EBQError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(result)
