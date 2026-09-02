from django.contrib.auth.models import AbstractUser
from django.db import models

from portal.data import DEPARTMENT_NAMES, MANAGEMENT

# One choice per real JCPL department (portal.data is the single source of
# truth for the org structure), plus "Management" for accounts like the Super
# Admin that aren't scoped to a single department.
DEPARTMENT_CHOICES = [(name, name) for name in DEPARTMENT_NAMES] + [(MANAGEMENT, MANAGEMENT)]


class User(AbstractUser):
    """JCPL staff account. Two access levels only: Super Admin and Admin."""

    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ADMIN)
    department = models.CharField(
        max_length=100,
        blank=True,
        choices=DEPARTMENT_CHOICES,
        help_text=(
            "Which single department this Admin account can access — it drives "
            "the sidebar and blocks direct links to other modules. Ignored for "
            "Super Admin, who always sees everything."
        ),
    )

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN

    def save(self, *args, **kwargs):
        # is_staff/is_superuser always mirror the current role — kept in sync
        # both ways. Without the else branch, demoting a Super Admin back to
        # Admin left those flags stuck at True, so the "demoted" account could
        # still reach Django's /admin/ site and edit its own role field back
        # to Super Admin, undoing the demotion entirely.
        is_super = self.role == self.Role.SUPER_ADMIN
        self.is_staff = is_super
        self.is_superuser = is_super
        super().save(*args, **kwargs)

    def __str__(self):
        full_name = self.get_full_name()
        return f"{full_name or self.username} — {self.get_role_display()}"


class LoginEvent(models.Model):
    """One row per successful sign-in / sign-out, written automatically by the
    signal handlers in accounts.signals — this is what the Super Admin's
    Login Activity page reads from. Never written to directly by view code,
    so it can't be skipped by forgetting to call it somewhere."""

    class EventType(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_events")
    event_type = models.CharField(max_length=10, choices=EventType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user.username} — {self.get_event_type_display()} — {self.timestamp:%Y-%m-%d %H:%M}"
