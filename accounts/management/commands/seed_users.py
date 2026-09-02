from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

DEFAULT_ACCOUNTS = [
    dict(
        username="superadmin",
        password="JCPL@Super2026",
        role=User.Role.SUPER_ADMIN,
        first_name="Ashish",
        last_name="Apte",
        email="superadmin@jollyclamps.com",
        department="Management",
    ),
    dict(
        username="admin",
        password="JCPL@Admin2026",
        role=User.Role.ADMIN,
        first_name="Staff",
        last_name="Admin",
        email="admin@jollyclamps.com",
        department="Operations",
    ),
]


class Command(BaseCommand):
    help = "Create the starter Super Admin and Admin accounts for the JCPL dashboard."

    def handle(self, *args, **options):
        for data in DEFAULT_ACCOUNTS:
            username = data.pop("username")
            password = data.pop("password")
            user, created = User.objects.get_or_create(username=username, defaults=data)
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created {username} / {password} ({user.get_role_display()})"))
            else:
                self.stdout.write(f"'{username}' already exists — skipped.")
