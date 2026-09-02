from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import super_admin_required
from .forms import AdminAccountForm, StyledAuthenticationForm
from .models import LoginEvent

User = get_user_model()


class JCPLLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True


@super_admin_required
def team_list(request):
    team = User.objects.all().order_by("-is_active", "-role", "username")
    return render(request, "accounts/team_list.html", {"team": team})


@super_admin_required
def team_create(request):
    if request.method == "POST":
        form = AdminAccountForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Account “{form.instance.username}” created.")
            return redirect("team_list")
    else:
        form = AdminAccountForm()
    return render(
        request,
        "accounts/team_form.html",
        {"form": form, "heading": "Add team account"},
    )


@super_admin_required
def team_edit(request, pk):
    account = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = AdminAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, f"Account “{account.username}” updated.")
            return redirect("team_list")
    else:
        form = AdminAccountForm(instance=account)
    return render(
        request,
        "accounts/team_form.html",
        {"form": form, "heading": f"Edit {account.username}", "account": account},
    )


@super_admin_required
def login_activity(request):
    events = LoginEvent.objects.select_related("user").all()

    username = request.GET.get("user", "").strip()
    if username:
        events = events.filter(user__username=username)

    paginator = Paginator(events, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "accounts/login_activity.html",
        {
            "page_obj": page_obj,
            "team": User.objects.all().order_by("username"),
            "selected_username": username,
        },
    )


@super_admin_required
def team_toggle_active(request, pk):
    account = get_object_or_404(User, pk=pk)
    if account == request.user:
        messages.error(request, "You can't deactivate your own account.")
    else:
        account.is_active = not account.is_active
        account.save()
        state = "reactivated" if account.is_active else "deactivated"
        messages.success(request, f"Account “{account.username}” {state}.")
    return redirect("team_list")
