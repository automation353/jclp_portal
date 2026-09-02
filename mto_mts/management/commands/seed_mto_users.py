"""Seed one Operations user and one OEM Sales user for demo/testing.

Idempotent — running it twice does not create duplicates or reset passwords.
Rename or delete these accounts through the admin once real user creds land.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


DEMO_USERS = [
    {
        "username": "ops_user",
        "password": "JCPL@Ops2026",
        "department": "Operations",
        "email": "ops@jollyclamps.local",
    },
    {
        "username": "sales_user",
        "password": "JCPL@Sales2026",
        "department": "OEM Sales",
        "email": "oemsales@jollyclamps.local",
    },
]


class Command(BaseCommand):
    help = "Seed demo Operations and OEM Sales user accounts."

    def handle(self, *args, **options):
        User = get_user_model()
        for spec in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "department": spec["department"],
                    "email": spec["email"],
                    "role": User.Role.ADMIN,
                },
            )
            if created:
                user.set_password(spec["password"])
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f"Created {spec['username']} ({spec['department']}) — "
                    f"password: {spec['password']}"
                ))
            else:
                self.stdout.write(
                    f"'{spec['username']}' already exists — skipped."
                )
