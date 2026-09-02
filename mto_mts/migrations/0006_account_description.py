"""Add MtoMtsItem.account_description — the "Item A/C Description" column
Rasika added to the source xlsx after the 11-Aug review meeting."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mto_mts", "0005_batch_one_changes"),
    ]

    operations = [
        migrations.AddField(
            model_name="mtomtsitem",
            name="account_description",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
