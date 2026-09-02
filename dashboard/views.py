from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from .data import get_accessible_modules, get_module


@login_required
def home(request):
    return render(request, "dashboard/home.html", {"modules": get_accessible_modules(request.user)})


@login_required
def module_detail(request, slug):
    module = get_module(slug)
    if module is None:
        raise Http404("Unknown department")
    accessible_slugs = {m["slug"] for m in get_accessible_modules(request.user)}
    if slug not in accessible_slugs:
        messages.error(request, f"You don't have access to the {module['name']} department.")
        return redirect("dashboard:home")
    return render(request, "dashboard/module.html", {"module": module})
