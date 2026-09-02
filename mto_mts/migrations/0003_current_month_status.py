"""Add shared 'current_month_status' field for inline editing in the
current-month cell (see Phase 1 UX)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mto_mts", "0002_status_processing_failed"),
    ]

    operations = [
        migrations.AddField(
            model_name="mtomtsitem",
            name="current_month_status",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AlterField(
            model_name="mtomtschange",
            name="field",
            field=models.CharField(
                choices=[
                    ("current_month_status", "Current month status"),
                    ("sales_reason", "Sales reason"),
                    ("ops_reason", "Operations reason"),
                    ("sales_status", "Sales status"),
                    ("ops_status", "Operations status"),
                ],
                max_length=32,
            ),
        ),
    ]
