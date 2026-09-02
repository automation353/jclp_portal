from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.JCPLLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("team/", views.team_list, name="team_list"),
    path("team/add/", views.team_create, name="team_create"),
    path("team/<int:pk>/edit/", views.team_edit, name="team_edit"),
    path("team/<int:pk>/toggle/", views.team_toggle_active, name="team_toggle_active"),
    path("activity/", views.login_activity, name="login_activity"),
]
