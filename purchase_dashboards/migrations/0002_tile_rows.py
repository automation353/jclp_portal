"""Per-tile drill-through rows — every card on every board gets its own
row list instead of one fixed table per dashboard."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchase_dashboards", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasedashresult",
            name="tile_rows",
            field=models.JSONField(default=dict),
        ),
    ]
