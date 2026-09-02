from django.core.management.base import BaseCommand

from portal.models import RawMaterial

# The five materials from the approved prototype. Chosen so the reorder rule
# is visible at a glance: three trigger a purchase, two sit comfortably above
# their reorder level.
STARTER_MATERIALS = [
    {"name": "SS 304 Strip 0.8mm", "on_hand": 2100, "reorder_level": 2500, "reorder_qty": 5000, "sort_order": 10},
    {"name": "SS 316 Strip 1.0mm", "on_hand": 3800, "reorder_level": 2000, "reorder_qty": 4000, "sort_order": 20},
    {"name": "M6 Hex Bolt", "on_hand": 12000, "reorder_level": 15000, "reorder_qty": 30000, "sort_order": 30},
    {"name": "Rubber Lining Sheet", "on_hand": 640, "reorder_level": 800, "reorder_qty": 1500, "sort_order": 40},
    {"name": "Zinc Plating Salt", "on_hand": 950, "reorder_level": 600, "reorder_qty": 1000, "sort_order": 50},
]


class Command(BaseCommand):
    help = "Load the starter raw-material list for the Purchase department."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Overwrite stock/reorder figures on materials that already exist.",
        )

    def handle(self, *args, **options):
        for data in STARTER_MATERIALS:
            name = data["name"]
            material, created = RawMaterial.objects.get_or_create(name=name, defaults=data)

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created {name}."))
            elif options["reset"]:
                for field, value in data.items():
                    setattr(material, field, value)
                material.save()
                self.stdout.write(self.style.WARNING(f"Reset {name} to starter figures."))
            else:
                self.stdout.write(f"'{name}' already exists - skipped (use --reset to overwrite).")
