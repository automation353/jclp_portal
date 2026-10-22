from django.core.management.base import BaseCommand, CommandError

from nongrn import services


class Command(BaseCommand):
    help = "Refresh All: re-read the 4 source folders (Power Query replica) and store the tables."

    def handle(self, *args, **options):
        run = services.run_refresh(triggered_by="manage.py refresh_data")
        if run.status != run.OK:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
