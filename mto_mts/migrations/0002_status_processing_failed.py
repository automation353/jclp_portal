"""Add 'processing' and 'failed' to MtoMtsUpload.status choices."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mto_mts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mtomtsupload",
            name="status",
            field=models.CharField(
                choices=[
                    ("processing", "Processing"),
                    ("active", "Active"),
                    ("failed", "Failed"),
                    ("superseded", "Superseded"),
                ],
                default="processing",
                max_length=16,
            ),
        ),
    ]
